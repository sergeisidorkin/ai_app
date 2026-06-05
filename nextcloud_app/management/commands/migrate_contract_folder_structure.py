from __future__ import annotations

import re
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.cloud_paths import CONTRACTS_PERFORMERS_FOLDER, CONTRACTS_SECTION_FOLDER, join_cloud_path, normalize_cloud_path
from core.models import CloudStorageSettings
from contracts_app.services import (
    build_contract_file_name,
    contract_executor_short_name,
    contract_project_folder_name,
    contract_project_number_display,
    contract_project_registration_display_id,
    contract_registration_folder_name,
)
from nextcloud_app.api import NextcloudApiClient, NextcloudApiError
from projects_app.models import Performer
from yandexdisk_app.models import YandexDiskAccount


@dataclass(frozen=True)
class FolderChange:
    source_path: str
    target_path: str
    performer_ids: tuple[int, ...]


@dataclass(frozen=True)
class FileRename:
    source_path: str
    target_path: str
    old_name: str
    new_name: str
    performer_ids: tuple[int, ...]


class Command(BaseCommand):
    help = "Migrates performer contract folders to the nested contract folder structure."

    def add_arguments(self, parser):
        parser.add_argument("--storage", choices=("primary", "nextcloud", "yandex_disk", "both"), default="primary")
        parser.add_argument("--yandex-user", default="", help="Username/email for Yandex.Disk move operations.")
        parser.add_argument("--overwrite", action="store_true", help="Allow replacing target folders/files during move.")
        parser.add_argument("--apply", action="store_true", help="Apply folder/file moves and database updates.")

    def handle(self, *args, **options):
        performers = self._load_performers()
        folder_changes, file_renames, skipped_files = self._collect_changes(performers)

        mode = "APPLY" if options["apply"] else "DRY-RUN"
        self.stdout.write(
            f"{mode}: {len(folder_changes)} folder move(s), "
            f"{len(file_renames)} file rename(s), {len(skipped_files)} skipped file(s)."
        )
        for change in folder_changes:
            self.stdout.write(f"MOVE {change.source_path} -> {change.target_path}")
        for rename in file_renames:
            self.stdout.write(f"RENAME {rename.source_path} -> {rename.target_path}")
        for performer_id, file_name in skipped_files:
            self.stdout.write(f"SKIP projects_app.Performer#{performer_id}.contract_file: {file_name}")

        if not options["apply"]:
            self.stdout.write(self.style.WARNING("Dry-run only. Re-run with --apply to perform changes."))
            return

        storage = self._resolve_storage(options["storage"])
        self._apply_folder_moves(storage, folder_changes, options)
        self._apply_file_renames(storage, file_renames, options)
        self._apply_database_changes(folder_changes, file_renames)
        self.stdout.write(self.style.SUCCESS("Contract folder structure migration completed."))

    def _load_performers(self):
        return list(
            Performer.objects
            .select_related(
                "registration",
                "registration__type",
                "registration__contract_project_registration",
                "registration__group_member",
            )
            .prefetch_related("registration__product_links__product")
            .exclude(contract_project_disk_folder="")
            .order_by("contract_project_disk_folder", "registration__agreement_sequence", "registration_id", "id")
        )

    def _collect_changes(self, performers):
        performers_by_folder = {}
        for performer in performers:
            folder = normalize_cloud_path(performer.contract_project_disk_folder)
            performers_by_folder.setdefault(folder, []).append(performer)

        grouped = []
        for source_path, folder_performers in performers_by_folder.items():
            parsed = self._parse_current_contract_folder(source_path)
            if parsed is None:
                continue
            representative = folder_performers[0]
            label_performers = self._label_performers(representative, folder_performers)
            project = representative.registration
            target_base = join_cloud_path(
                parsed["root"],
                CONTRACTS_SECTION_FOLDER,
                parsed["year"],
                contract_project_folder_name(project, label_performers),
                contract_registration_folder_name(project, label_performers),
                CONTRACTS_PERFORMERS_FOLDER,
            )
            grouped.append(
                {
                    "source_path": source_path,
                    "target_base": target_base,
                    "old_number": self._old_folder_number(parsed["performer_folder"]),
                    "executor_name": contract_executor_short_name(representative.executor),
                    "contract_id": contract_project_registration_display_id(project) or "Unknown",
                    "performers": folder_performers,
                    "label_performers": label_performers,
                }
            )

        counters = {}
        folder_changes = []
        file_renames = []
        skipped_files = []
        for item in sorted(grouped, key=lambda value: (value["target_base"], value["old_number"], value["source_path"])):
            target_base = item["target_base"]
            counters[target_base] = counters.get(target_base, 0) + 1
            target_folder_name = f"{item['contract_id']} {counters[target_base]:03d} {item['executor_name']}"
            target_path = join_cloud_path(target_base, target_folder_name)
            performer_ids = tuple(performer.pk for performer in item["performers"])
            if normalize_cloud_path(item["source_path"]) != target_path:
                folder_changes.append(FolderChange(item["source_path"], target_path, performer_ids))
            file_renames.extend(
                self._collect_file_renames(item["performers"], item["label_performers"], target_path, skipped_files)
            )
        return folder_changes, file_renames, skipped_files

    def _collect_file_renames(self, performers, label_performers, target_folder_path, skipped_files):
        renames_by_path = {}
        for performer in performers:
            old_name = (performer.contract_file or "").strip()
            if not old_name:
                continue
            new_name = build_contract_file_name(
                performer,
                extension=self._file_extension(old_name),
                is_addendum=bool(performer.contract_is_addendum),
                addendum_number=performer.contract_addendum_number,
                batch_performers=label_performers,
            )
            if old_name == new_name:
                continue
            if old_name not in self._legacy_contract_file_names(performer, label_performers, old_name):
                skipped_files.append((performer.pk, old_name))
                continue
            source_path = join_cloud_path(target_folder_path, old_name)
            target_path = join_cloud_path(target_folder_path, new_name)
            key = (source_path, target_path, old_name, new_name)
            existing = renames_by_path.get(key)
            if existing is not None:
                renames_by_path[key] = FileRename(
                    existing.source_path,
                    existing.target_path,
                    existing.old_name,
                    existing.new_name,
                    existing.performer_ids + (performer.pk,),
                )
                continue
            renames_by_path[key] = FileRename(
                source_path,
                target_path,
                old_name,
                new_name,
                (performer.pk,),
            )
        return list(renames_by_path.values())

    def _legacy_contract_file_names(self, performer, batch_performers, file_name):
        project = getattr(performer, "registration", None)
        executor_name = contract_executor_short_name(getattr(performer, "executor", ""))
        ext = self._file_extension(file_name)
        kind_suffix = ""
        if performer.contract_is_addendum:
            kind_suffix = f"_ДС{performer.contract_addendum_number or ''}".strip()
        candidates = []
        for prefix in (
            getattr(project, "short_uid", "") or "",
            contract_project_number_display(project),
        ):
            if prefix:
                candidates.append(f"Договор {prefix}_{executor_name}{kind_suffix}{ext}")
        return set(candidates)

    def _label_performers(self, representative, folder_performers):
        if representative.participation_batch_id:
            rows = list(
                Performer.objects
                .select_related(
                    "registration",
                    "registration__type",
                    "registration__contract_project_registration",
                    "registration__group_member",
                )
                .prefetch_related("registration__product_links__product")
                .filter(
                    participation_batch_id=representative.participation_batch_id,
                    executor=representative.executor,
                    participation_response=Performer.ParticipationResponse.CONFIRMED,
                )
                .order_by("registration__agreement_sequence", "registration_id", "position", "id")
            )
            return rows or folder_performers
        if representative.contract_batch_id:
            rows = list(
                Performer.objects
                .select_related(
                    "registration",
                    "registration__type",
                    "registration__contract_project_registration",
                    "registration__group_member",
                )
                .prefetch_related("registration__product_links__product")
                .filter(contract_batch_id=representative.contract_batch_id)
                .order_by("registration__agreement_sequence", "registration_id", "position", "id")
            )
            return rows or folder_performers
        return folder_performers

    def _parse_current_contract_folder(self, path):
        normalized = normalize_cloud_path(path)
        parts = normalized.strip("/").split("/")
        try:
            section_index = parts.index(CONTRACTS_SECTION_FOLDER)
        except ValueError:
            return None
        if len(parts) <= section_index + 4:
            return None
        if parts[section_index + 3] != CONTRACTS_PERFORMERS_FOLDER:
            return None
        root_parts = parts[:section_index]
        return {
            "root": "/" + "/".join(root_parts) if root_parts else "/",
            "year": parts[section_index + 1],
            "performer_folder": parts[section_index + 4],
        }

    @staticmethod
    def _old_folder_number(folder_name):
        match = re.match(r"^(\d{3})\s", folder_name or "")
        return int(match.group(1)) if match else 10_000

    @staticmethod
    def _file_extension(file_name):
        match = re.search(r"(\.[^./\\]+)$", file_name or "")
        return match.group(1) if match else ".docx"

    def _apply_folder_moves(self, storage, folder_changes, options):
        self._apply_moves(storage, [(change.source_path, change.target_path) for change in folder_changes], options)

    def _apply_file_renames(self, storage, file_renames, options):
        self._apply_moves(storage, [(rename.source_path, rename.target_path) for rename in file_renames], options)

    def _apply_moves(self, storage, moves, options):
        if storage in {"nextcloud", "both"}:
            client = NextcloudApiClient()
            if not client.is_configured:
                raise CommandError("Nextcloud is not configured for physical move operations.")
            for source_path, target_path in moves:
                try:
                    client.move_resource(client.username, source_path, target_path, overwrite=options["overwrite"])
                except NextcloudApiError as exc:
                    raise CommandError(str(exc)) from exc

        if storage in {"yandex_disk", "both"}:
            from yandexdisk_app.service import move_resource

            user = self._resolve_yandex_user(options.get("yandex_user") or "")
            for source_path, target_path in moves:
                if not move_resource(user, source_path, target_path, overwrite=options["overwrite"]):
                    raise CommandError(f"Could not move Yandex.Disk resource {source_path} -> {target_path}.")

    def _apply_database_changes(self, folder_changes, file_renames):
        with transaction.atomic():
            for change in folder_changes:
                Performer.objects.filter(pk__in=change.performer_ids).update(
                    contract_project_disk_folder=change.target_path,
                    contract_project_folder_file_id="",
                )
            for rename in file_renames:
                Performer.objects.filter(pk__in=rename.performer_ids, contract_file=rename.old_name).update(
                    contract_file=rename.new_name,
                    contract_project_file_id="",
                )

    @staticmethod
    def _resolve_storage(storage):
        if storage != "primary":
            return storage
        return CloudStorageSettings.get_solo().primary_storage

    def _resolve_yandex_user(self, username):
        User = get_user_model()
        if username:
            user = User.objects.filter(username=username).first() or User.objects.filter(email=username).first()
            if user is None:
                raise CommandError(f"Yandex.Disk user `{username}` not found.")
            if not YandexDiskAccount.objects.filter(user=user, access_token__gt="").exists():
                raise CommandError(f"Yandex.Disk user `{username}` does not have an access token.")
            return user

        account = YandexDiskAccount.objects.filter(access_token__gt="").select_related("user").first()
        if account is None:
            raise CommandError("No Yandex.Disk account with an access token found. Pass --yandex-user.")
        return account.user
