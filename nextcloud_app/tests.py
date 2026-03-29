from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase, override_settings

from nextcloud_app.api import NextcloudApiError
from nextcloud_app.models import NextcloudUserLink
from nextcloud_app.provisioning import ensure_nextcloud_account

User = get_user_model()


class NextcloudProvisioningTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="staff@example.com",
            email="staff@example.com",
            password="Secret123!",
            first_name="Staff",
            last_name="User",
            is_staff=True,
            is_active=True,
        )

    def _client(self):
        client = Mock()
        client.is_configured = True
        client.provision_user.return_value = Mock(
            user_id=f"ncstaff-{self.user.pk}",
            display_name="Staff User",
            email="staff@example.com",
        )
        client.enable_user.return_value = None
        client.disable_user.return_value = None
        client.set_user_email.return_value = None
        client.set_user_display_name.return_value = None
        return client

    def test_create_nextcloud_user_for_new_staff_account(self):
        client = self._client()

        link = ensure_nextcloud_account(self.user, client=client)

        self.assertEqual(link.nextcloud_user_id, f"ncstaff-{self.user.pk}")
        self.assertEqual(link.nextcloud_email, "staff@example.com")
        self.assertEqual(NextcloudUserLink.objects.get(user=self.user).nextcloud_user_id, f"ncstaff-{self.user.pk}")
        client.provision_user.assert_called_once_with(
            user_id=f"ncstaff-{self.user.pk}",
            display_name="Staff User",
            email="staff@example.com",
        )
        client.enable_user.assert_called_once_with(f"ncstaff-{self.user.pk}")

    def test_disable_existing_nextcloud_user_when_user_loses_staff_access(self):
        self.user.is_staff = False
        self.user.save(update_fields=["is_staff"])
        NextcloudUserLink.objects.create(
            user=self.user,
            nextcloud_user_id=f"ncstaff-{self.user.pk}",
            nextcloud_username=f"ncstaff-{self.user.pk}",
            nextcloud_email="staff@example.com",
        )
        client = self._client()

        link = ensure_nextcloud_account(self.user, client=client)

        self.assertEqual(link.nextcloud_user_id, f"ncstaff-{self.user.pk}")
        client.disable_user.assert_called_once_with(f"ncstaff-{self.user.pk}")
        client.provision_user.assert_not_called()

    def test_raise_clear_error_when_other_django_user_owns_same_nextcloud_user(self):
        other = User.objects.create_user(
            username="other@example.com",
            email="other@example.com",
            password="Secret123!",
            is_staff=True,
            is_active=True,
        )
        NextcloudUserLink.objects.create(
            user=other,
            nextcloud_user_id=f"ncstaff-{self.user.pk}",
            nextcloud_username=f"ncstaff-{self.user.pk}",
            nextcloud_email="other@example.com",
        )
        client = self._client()

        with self.assertRaises(NextcloudApiError):
            ensure_nextcloud_account(self.user, client=client)


class NextcloudProvisioningSignalTests(TestCase):
    @override_settings(
        NEXTCLOUD_PROVISIONING_BASE_URL="https://cloud.example.com",
        NEXTCLOUD_PROVISIONING_USERNAME="admin",
        NEXTCLOUD_PROVISIONING_TOKEN="token",
        NEXTCLOUD_OIDC_PROVIDER_ID=1,
    )
    @patch("nextcloud_app.signals.sync_nextcloud_account_for_user")
    def test_staff_user_save_triggers_nextcloud_provisioning(self, mocked_sync):
        with self.captureOnCommitCallbacks(execute=True):
            user = User.objects.create_user(
                username="signal@example.com",
                email="signal@example.com",
                password="Secret123!",
                first_name="Signal",
                last_name="User",
                is_staff=True,
                is_active=True,
            )

        mocked_sync.assert_called_once_with(user.pk)

    @override_settings(
        NEXTCLOUD_PROVISIONING_BASE_URL="https://cloud.example.com",
        NEXTCLOUD_PROVISIONING_USERNAME="admin",
        NEXTCLOUD_PROVISIONING_TOKEN="token",
        NEXTCLOUD_OIDC_PROVIDER_ID=1,
    )
    @patch("nextcloud_app.signals.sync_nextcloud_account_for_user")
    def test_non_staff_user_save_does_not_trigger_nextcloud_provisioning(self, mocked_sync):
        with self.captureOnCommitCallbacks(execute=True):
            User.objects.create_user(
                username="external@example.com",
                email="external@example.com",
                password="Secret123!",
                is_staff=False,
                is_active=True,
            )

        mocked_sync.assert_not_called()


class NextcloudCommandTests(TestCase):
    @patch("nextcloud_app.management.commands.sync_nextcloud_users.sync_nextcloud_account_for_user")
    def test_sync_command_processes_staff_users(self, mocked_sync):
        staff_user = User.objects.create_user(
            username="sync@example.com",
            email="sync@example.com",
            password="Secret123!",
            is_staff=True,
            is_active=True,
        )
        User.objects.create_user(
            username="external@example.com",
            email="external@example.com",
            password="Secret123!",
            is_staff=False,
            is_active=True,
        )

        call_command("sync_nextcloud_users")

        mocked_sync.assert_called_once_with(staff_user.pk)


class SidebarNextcloudLinkTests(TestCase):
    @override_settings(NEXTCLOUD_BASE_URL="https://cloud.imcmontanai.ru")
    def test_home_sidebar_contains_nextcloud_link_after_learning(self):
        user = User.objects.create_user(
            username="sidebar@example.com",
            email="sidebar@example.com",
            password="Secret123!",
            is_staff=True,
            is_active=True,
        )
        client = Client()
        client.force_login(user)

        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("https://cloud.imcmontanai.ru", content)
        self.assertLess(content.find("Обучение"), content.find("Nextcloud"))

    @override_settings(
        NEXTCLOUD_BASE_URL="https://cloud.imcmontanai.ru",
        NEXTCLOUD_SSO_ENABLED=True,
        NEXTCLOUD_OIDC_LOGIN_PATH="/apps/user_oidc/login/1",
    )
    def test_home_sidebar_uses_direct_oidc_entrypoint_when_enabled(self):
        user = User.objects.create_user(
            username="sidebar-sso@example.com",
            email="sidebar-sso@example.com",
            password="Secret123!",
            is_staff=True,
            is_active=True,
        )
        client = Client()
        client.force_login(user)

        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="https://cloud.imcmontanai.ru/apps/user_oidc/login/1"', html=False)
