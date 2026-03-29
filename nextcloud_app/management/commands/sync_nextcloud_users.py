from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db.models import Q

from nextcloud_app.provisioning import sync_nextcloud_account_for_user

User = get_user_model()


class Command(BaseCommand):
    help = "Sync staff users from Django to Nextcloud."

    def add_arguments(self, parser):
        parser.add_argument("--email", help="Sync a single Django user by email.")

    def handle(self, *args, **options):
        email = (options.get("email") or "").strip()
        queryset = User.objects.all()
        if email:
            queryset = queryset.filter(email__iexact=email)
        else:
            queryset = queryset.filter(Q(is_staff=True) | Q(nextcloud_link__isnull=False)).distinct()

        synced = 0
        for user in queryset.order_by("pk"):
            sync_nextcloud_account_for_user(user.pk)
            synced += 1
            self.stdout.write(self.style.SUCCESS(f"Synced Nextcloud account for {user.get_username()}"))

        self.stdout.write(self.style.SUCCESS(f"Processed {synced} user(s)."))
