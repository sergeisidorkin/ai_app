from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from checklists_app.models import (
    ChecklistItemFolder,
    ProjectWorkspace,
    SourceDataItemFolder,
    SourceDataSectionFolder,
    SourceDataWorkspace,
)
from core.cloud_paths import (
    CONTRACTS_PERFORMERS_FOLDER,
    CONTRACTS_SECTION_FOLDER,
    LEGACY_PROJECTS_SECTION_FOLDER,
    LEGACY_PROPOSALS_SECTION_FOLDER,
    PROJECTS_SECTION_FOLDER,
    PROPOSALS_SECTION_FOLDER,
    join_cloud_path,
    normalize_cloud_path,
    replace_cloud_path_prefix,
)
from core.models import CloudStorageSettings
from nextcloud_app.api import NextcloudApiClient, NextcloudApiError
from projects_app.models import Performer
from proposals_app.models import ProposalRegistration
from yandexdisk_app.models import YandexDiskAccount, YandexDiskSelection


@dataclass(frozen=True)
class PathChange:
    model_label: str
    pk: int
    field: str
    old_path: str
    new_path: str


@dataclass(frozen=True)
class MoveOperation:
    source_path: str
    target_path: str


PATH_FIELDS = (
    (ProposalRegistration, ("proposal_workspace_disk_path", "proposal_workspace_target_path", "docx_file_link", "pdf_file_link")),
    (ProjectWorkspace, ("disk_path",)),
    (ChecklistItemFolder, ("disk_path",)),
    (SourceDataWorkspace, ("disk_path",)),
    (SourceDataSectionFolder, ("disk_path",)),
    (SourceDataItemFolder, ("disk_path",)),
    (Performer, ("contract_project_disk_folder",)),
    (YandexDiskSelection, ("resource_path",)),
)


class Command(BaseCommand):
    help = "Migrates cloud folder paths to the 01 ТКП / 02 Договоры / 03 Проекты structure."

    def add_arguments(self, parser):
        parser.add_argument("--old-root", required=True, help="Current/legacy root path, for example /Projects.")
        parser.add_argument(
            "--new-root",
            default="",
            help="Target root path. Defaults to the configured Nextcloud root path.",
        )
        parser.add_argument(
            "--storage",
            choices=("primary", "nextcloud", "yandex_disk", "both"),
            default="primary",
            help="Which cloud backend should receive physical move operations.",
        )
        parser.add_argument("--yandex-user", default="", help="Username/email for Yandex.Disk move operations.")
        parser.add_argument("--overwrite", action="store_true", help="Allow replacing target folders during move.")
        parser.add_argument("--apply", action="store_true", help="Apply folder moves and database path updates.")

    def handle(self, *args, **options):
        old_root = normalize_cloud_path(options["old_root"])
        settings_obj = CloudStorageSettings.get_solo()
        raw_new_root = options["new_root"] or settings_obj.nextcloud_root_path or ""
        if not str(raw_new_root).strip():
            raise CommandError("Target root is empty. Pass --new-root or configure Nextcloud root path.")
        new_root = normalize_cloud_path(raw_new_root)

        changes = self._collect_path_changes(old_root, new_root)
        moves = self._collect_move_operations(changes, old_root, new_root)

        mode = "APPLY" if options["apply"] else "DRY-RUN"
        self.stdout.write(f"{mode}: {len(moves)} folder move(s), {len(changes)} database path update(s).")
        for move in moves:
            self.stdout.write(f"MOVE {move.source_path} -> {move.target_path}")
        for change in changes:
            self.stdout.write(
                f"DB {change.model_label}#{change.pk}.{change.field}: "
                f"{change.old_path} -> {change.new_path}"
            )

        if not options["apply"]:
            self.stdout.write(self.style.WARNING("Dry-run only. Re-run with --apply to perform changes."))
            return

        storage = self._resolve_storage(options["storage"], settings_obj)
        if moves:
            self._apply_moves(storage, moves, options)
        self._apply_database_changes(changes)
        self.stdout.write(self.style.SUCCESS("Cloud storage structure migration completed."))

    def _collect_path_changes(self, old_root: str, new_root: str) -> list[PathChange]:
        changes: list[PathChange] = []
        for model, fields in PATH_FIELDS:
            model_label = model._meta.label
            for field in fields:
                for pk, raw_value in model.objects.exclude(**{field: ""}).values_list("pk", field):
                    old_value = str(raw_value or "").strip()
                    if not old_value:
                        continue
                    new_value = self._transform_path(old_value, old_root, new_root, field=field)
                    if new_value != normalize_cloud_path(old_value):
                        changes.append(PathChange(model_label, pk, field, old_value, new_value))
        return changes

    def _transform_path(self, path: str, old_root: str, new_root: str, *, field: str = "") -> str:
        normalized = normalize_cloud_path(path)
        if normalized == old_root:
            return new_root

        if field == "proposal_workspace_target_path":
            rootless_legacy_tkp = join_cloud_path("/", LEGACY_PROPOSALS_SECTION_FOLDER)
            transformed = replace_cloud_path_prefix(
                normalized,
                rootless_legacy_tkp,
                join_cloud_path("/", PROPOSALS_SECTION_FOLDER),
            )
            if transformed != normalized:
                return transformed

        if field == "contract_project_disk_folder":
            transformed = self._transform_contract_project_path(normalized, old_root, new_root)
            if transformed != normalized:
                return transformed

        legacy_tkp = join_cloud_path(old_root, LEGACY_PROPOSALS_SECTION_FOLDER)
        target_tkp = join_cloud_path(new_root, PROPOSALS_SECTION_FOLDER)
        transformed = replace_cloud_path_prefix(normalized, legacy_tkp, target_tkp)
        if transformed != normalized:
            return transformed

        legacy_projects = join_cloud_path(old_root, LEGACY_PROJECTS_SECTION_FOLDER)
        target_projects = join_cloud_path(new_root, PROJECTS_SECTION_FOLDER)
        transformed = replace_cloud_path_prefix(normalized, legacy_projects, target_projects)
        if transformed != normalized:
            return transformed

        for section in (PROPOSALS_SECTION_FOLDER, PROJECTS_SECTION_FOLDER, CONTRACTS_SECTION_FOLDER):
            transformed = replace_cloud_path_prefix(
                normalized,
                join_cloud_path(old_root, section),
                join_cloud_path(new_root, section),
            )
            if transformed != normalized:
                return transformed

        relative = self._relative_to_root(normalized, old_root)
        if relative is None:
            return normalized

        first_part = relative.split("/", 1)[0]
        if self._is_project_year_segment(first_part):
            return join_cloud_path(new_root, PROJECTS_SECTION_FOLDER, relative)
        return normalized

    def _transform_contract_project_path(self, normalized: str, old_root: str, new_root: str) -> str:
        relative = self._relative_to_root(normalized, old_root)
        if relative is None:
            return normalized

        parts = [part for part in relative.split("/") if part]
        if parts and parts[0] in {LEGACY_PROJECTS_SECTION_FOLDER, PROJECTS_SECTION_FOLDER, CONTRACTS_SECTION_FOLDER}:
            parts = parts[1:]

        if len(parts) < 4:
            return normalized

        year, project_folder, _legacy_target_folder = parts[:3]
        if not self._is_project_year_segment(year):
            return normalized

        return join_cloud_path(
            new_root,
            CONTRACTS_SECTION_FOLDER,
            year,
            project_folder,
            CONTRACTS_PERFORMERS_FOLDER,
            *parts[3:],
        )

    def _collect_move_operations(
        self,
        changes: list[PathChange],
        old_root: str,
        new_root: str,
    ) -> list[MoveOperation]:
        operations: dict[tuple[str, str], MoveOperation] = {}
        for change in changes:
            if not self._is_physical_path_field(change.field):
                continue
            operation = MoveOperation(
                normalize_cloud_path(change.old_path),
                normalize_cloud_path(change.new_path),
            )
            if operation.source_path == operation.target_path:
                continue
            operations[(operation.source_path, operation.target_path)] = operation
        return self._prune_nested_move_operations(operations.values())

    def _move_operation_for_path(self, path: str, old_root: str, new_root: str) -> MoveOperation | None:
        normalized = normalize_cloud_path(path)
        legacy_tkp = join_cloud_path(old_root, LEGACY_PROPOSALS_SECTION_FOLDER)
        if normalized == legacy_tkp or normalized.startswith(f"{legacy_tkp}/"):
            return MoveOperation(legacy_tkp, join_cloud_path(new_root, PROPOSALS_SECTION_FOLDER))

        for section in (PROPOSALS_SECTION_FOLDER, PROJECTS_SECTION_FOLDER, CONTRACTS_SECTION_FOLDER):
            section_root = join_cloud_path(old_root, section)
            if normalized == section_root or normalized.startswith(f"{section_root}/"):
                return MoveOperation(section_root, join_cloud_path(new_root, section))

        legacy_projects = join_cloud_path(old_root, LEGACY_PROJECTS_SECTION_FOLDER)
        if normalized == legacy_projects or normalized.startswith(f"{legacy_projects}/"):
            return MoveOperation(legacy_projects, join_cloud_path(new_root, PROJECTS_SECTION_FOLDER))

        relative = self._relative_to_root(normalized, old_root)
        if relative is None:
            return None

        first_part = relative.split("/", 1)[0]
        if self._is_project_year_segment(first_part):
            return MoveOperation(
                join_cloud_path(old_root, first_part),
                join_cloud_path(new_root, PROJECTS_SECTION_FOLDER, first_part),
            )
        return None

    def _apply_moves(self, storage: str, moves: list[MoveOperation], options: dict) -> None:
        if storage in {"nextcloud", "both"}:
            client = NextcloudApiClient()
            if not client.is_configured:
                raise CommandError("Nextcloud is not configured for physical move operations.")
            for move in moves:
                try:
                    client.move_resource(
                        client.username,
                        move.source_path,
                        move.target_path,
                        overwrite=options["overwrite"],
                    )
                except NextcloudApiError as exc:
                    raise CommandError(str(exc)) from exc

        if storage in {"yandex_disk", "both"}:
            from yandexdisk_app.service import move_resource

            user = self._resolve_yandex_user(options.get("yandex_user") or "")
            for move in moves:
                if not move_resource(user, move.source_path, move.target_path, overwrite=options["overwrite"]):
                    raise CommandError(f"Could not move Yandex.Disk resource {move.source_path} -> {move.target_path}.")

    def _apply_database_changes(self, changes: list[PathChange]) -> None:
        model_map = {model._meta.label: model for model, _fields in PATH_FIELDS}
        with transaction.atomic():
            for change in changes:
                model = model_map[change.model_label]
                model.objects.filter(pk=change.pk).update(**{change.field: change.new_path})

    def _resolve_storage(self, storage: str, settings_obj: CloudStorageSettings) -> str:
        if storage != "primary":
            return storage
        return settings_obj.primary_storage

    def _resolve_yandex_user(self, username: str):
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

    @staticmethod
    def _is_project_year_segment(value: str) -> bool:
        return value == "Без года" or value.isdigit()

    @staticmethod
    def _is_physical_path_field(field: str) -> bool:
        return field != "proposal_workspace_target_path"

    def _prune_nested_move_operations(self, operations) -> list[MoveOperation]:
        selected: list[MoveOperation] = []
        for operation in sorted(
            operations,
            key=lambda item: (self._path_depth(item.source_path), item.source_path),
        ):
            if any(self._operation_covers(parent, operation) for parent in selected):
                continue
            selected.append(operation)
        return selected

    @staticmethod
    def _operation_covers(parent: MoveOperation, child: MoveOperation) -> bool:
        if parent.source_path == child.source_path:
            return True
        if not child.source_path.startswith(f"{parent.source_path.rstrip('/')}/"):
            return False
        suffix = child.source_path[len(parent.source_path.rstrip("/")):]
        return child.target_path == f"{parent.target_path.rstrip('/')}{suffix}"

    @staticmethod
    def _path_depth(path: str) -> int:
        return len(normalize_cloud_path(path).strip("/").split("/"))

    @staticmethod
    def _relative_to_root(path: str, root: str) -> str | None:
        normalized_path = normalize_cloud_path(path)
        normalized_root = normalize_cloud_path(root)
        if normalized_path == normalized_root:
            return ""
        if normalized_root == "/":
            return normalized_path.lstrip("/")
        if normalized_path.startswith(f"{normalized_root}/"):
            return normalized_path[len(normalized_root):].lstrip("/")
        return None
