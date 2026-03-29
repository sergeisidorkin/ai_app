from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import CloudStorageSettings

User = get_user_model()


class PrimaryCloudStorageConnectionsTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="root@example.com",
            email="root@example.com",
            password="Secret123!",
        )
        self.staff_user = User.objects.create_user(
            username="staff@example.com",
            email="staff@example.com",
            password="Secret123!",
            is_staff=True,
        )

    def test_connections_partial_shows_global_storage_card(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("onedrive_connections_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Основное облачное хранилище")
        self.assertContains(response, "Яндекс Диск")
        self.assertContains(response, "Nextcloud")
        self.assertContains(response, "disabled")

    def test_superuser_can_change_primary_cloud_storage(self):
        self.client.force_login(self.superuser)

        response = self.client.post(
            reverse("primary_cloud_storage_update"),
            {"primary_storage": CloudStorageSettings.PrimaryStorage.NEXTCLOUD},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            CloudStorageSettings.get_solo().primary_storage,
            CloudStorageSettings.PrimaryStorage.NEXTCLOUD,
        )
        self.assertContains(response, "Nextcloud")

    def test_non_superuser_cannot_change_primary_cloud_storage(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("primary_cloud_storage_update"),
            {"primary_storage": CloudStorageSettings.PrimaryStorage.NEXTCLOUD},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            CloudStorageSettings.get_solo().primary_storage,
            CloudStorageSettings.PrimaryStorage.YANDEX_DISK,
        )

    def test_connections_partial_shows_nextcloud_root_card(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("onedrive_connections_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Глобальное корпоративное пространство Nextcloud")
        self.assertContains(response, "Корневой каталог Nextcloud")

    def test_superuser_can_save_nextcloud_root_path(self):
        self.client.force_login(self.superuser)

        response = self.client.post(
            reverse("nextcloud_root_update"),
            {"nextcloud_root_path": "/Corporate/Projects"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            CloudStorageSettings.get_solo().nextcloud_root_path,
            "/Corporate/Projects",
        )
        self.assertContains(response, "/Corporate/Projects")

    def test_non_superuser_cannot_change_nextcloud_root_path(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("nextcloud_root_update"),
            {"nextcloud_root_path": "/Corporate/Projects"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(CloudStorageSettings.get_solo().nextcloud_root_path, "")

    def test_invalid_nextcloud_root_path_returns_bad_request(self):
        self.client.force_login(self.superuser)

        response = self.client.post(
            reverse("nextcloud_root_update"),
            {"nextcloud_root_path": "/Corporate/../Projects"},
        )

        self.assertEqual(response.status_code, 400)
