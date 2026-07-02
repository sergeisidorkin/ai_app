from __future__ import annotations

import re

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from core.cloud_paths import CONTRACTS_PERFORMERS_FOLDER, CONTRACTS_SECTION_FOLDER, normalize_cloud_path
from nextcloud_app.api import NextcloudApiClient, NextcloudApiError, NextcloudShare
from nextcloud_app.models import NextcloudUserLink
from projects_app.models import Performer


class Command(BaseCommand):
    help = "Prune stale direct Nextcloud shares for performer contract folders."

    def add_arguments(self, parser):
        parser.add_argument("--email", default="", help="Django user email to clean.")
        parser.add_argument("--username", default="", help="Django username to clean.")
        parser.add_argument("--nextcloud-user-id", default="", help="Nextcloud user id to clean.")
        parser.add_argument("--apply", action="store_true", help="Actually delete stale shares.")

    def handle(self, *args, **options):
        links = self._resolve_links(options)
        if not links:
            raise CommandError("No matching Nextcloud user links found.")

        client = NextcloudApiClient()
        if not client.is_configured:
            raise CommandError("Nextcloud is not configured.")

        total_stale = 0
        total_deleted = 0
        for link in links:
            expected_paths = self._expected_contract_share_paths(link.user_id)
            stale_shares = self._stale_contract_shares(
                client.list_user_shares(client.username, link.nextcloud_user_id),
                expected_paths,
            )
            total_stale += len(stale_shares)
            self.stdout.write(
                f"{link.user.get_username()} ({link.nextcloud_user_id}): "
                f"{len(stale_shares)} stale contract share(s)."
            )
            for share in stale_shares:
                self.stdout.write(f"STALE {share.share_id}: {share.path} -> {share.target_path or '-'}")
                if not options["apply"]:
                    continue
                try:
                    if client.delete_share(share.share_id):
                        total_deleted += 1
                        self.stdout.write(self.style.SUCCESS(f"DELETED {share.share_id}: {share.path}"))
                except NextcloudApiError as exc:
                    raise CommandError(f"Could not delete share {share.share_id}: {exc}") from exc

        if options["apply"]:
            self.stdout.write(self.style.SUCCESS(f"Deleted {total_deleted} stale share(s)."))
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Dry-run only. Found {total_stale} stale share(s). Re-run with --apply to delete them."
                )
            )

    def _resolve_links(self, options) -> list[NextcloudUserLink]:
        email = str(options.get("email") or "").strip()
        username = str(options.get("username") or "").strip()
        nextcloud_user_id = str(options.get("nextcloud_user_id") or "").strip()
        if not any((email, username, nextcloud_user_id)):
            raise CommandError("Pass --email, --username, or --nextcloud-user-id.")

        queryset = NextcloudUserLink.objects.select_related("user").order_by("user_id")
        if email:
            queryset = queryset.filter(user__email__iexact=email)
        if username:
            queryset = queryset.filter(user__username__iexact=username)
        if nextcloud_user_id:
            queryset = queryset.filter(nextcloud_user_id=nextcloud_user_id)
        return list(queryset)

    @staticmethod
    def _expected_contract_share_paths(user_id: int) -> set[str]:
        return {
            normalize_cloud_path(path)
            for path in (
                Performer.objects
                .filter(employee__user_id=user_id)
                .exclude(contract_project_disk_folder="")
                .values_list("contract_project_disk_folder", flat=True)
            )
            if path
        }

    def _stale_contract_shares(
        self,
        shares_by_path: dict[str, NextcloudShare],
        expected_paths: set[str],
    ) -> list[NextcloudShare]:
        stale = []
        for share in shares_by_path.values():
            normalized_path = normalize_cloud_path(share.path)
            if normalized_path in expected_paths:
                continue
            if self._looks_like_contract_performer_share(normalized_path):
                stale.append(share)
        return stale

    @staticmethod
    def _looks_like_contract_performer_share(path: str) -> bool:
        parts = normalize_cloud_path(path).strip("/").split("/")
        if not parts:
            return False
        if CONTRACTS_SECTION_FOLDER not in parts and "09 Договоры" not in parts:
            return False
        if CONTRACTS_PERFORMERS_FOLDER not in parts and "09 Договоры" not in parts:
            return False
        leaf = parts[-1]
        return bool(re.match(r"^(?:\d{3}|[0-9A-Z]+RU\s+\d{3})\s+", leaf))
