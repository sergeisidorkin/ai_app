from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import Client
from django.test import TestCase, override_settings
from django.urls import reverse

from learning_app.models import LearningUserLink
from learning_app.moodle_api import MoodleApiError
from learning_app.provisioning import ensure_moodle_account

User = get_user_model()


class MoodleProvisioningTests(TestCase):
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
        client.get_users_by_id.return_value = []
        client.get_users_by_idnumber.return_value = []
        client.get_users_by_email.return_value = []
        client.get_users_by_username.return_value = []
        client.create_users.return_value = []
        client.update_users.return_value = None
        return client

    def test_create_moodle_user_for_new_staff_account(self):
        client = self._client()
        client.create_users.return_value = [
            {"id": 42, "username": "staff@example.com", "email": "staff@example.com"}
        ]
        client.get_users_by_id.return_value = [
            {"id": 42, "username": "staff@example.com", "email": "staff@example.com"}
        ]

        link = ensure_moodle_account(self.user, client=client)

        self.assertEqual(link.moodle_user_id, 42)
        self.assertEqual(link.moodle_username, "staff@example.com")
        self.assertEqual(LearningUserLink.objects.get(user=self.user).moodle_user_id, 42)
        client.create_users.assert_called_once()
        create_payload = client.create_users.call_args.args[0][0]
        self.assertEqual(create_payload["username"], self.user.email)
        self.assertEqual(create_payload["email"], self.user.email)
        self.assertNotIn("suspended", create_payload)
        client.update_users.assert_called_once()

    @override_settings(MOODLE_USER_AUTH_PLUGIN="oidc")
    def test_switches_staff_user_to_oidc_auth_on_followup_update(self):
        client = self._client()
        client.create_users.return_value = [
            {"id": 42, "username": "staff@example.com", "email": "staff@example.com", "auth": "manual"}
        ]
        client.get_users_by_id.return_value = [
            {"id": 42, "username": "staff@example.com", "email": "staff@example.com", "auth": "oidc"}
        ]

        ensure_moodle_account(self.user, client=client)

        create_payload = client.create_users.call_args.args[0][0]
        update_payload = client.update_users.call_args.args[0][0]
        self.assertEqual(create_payload["auth"], "manual")
        self.assertEqual(update_payload["auth"], "oidc")

    def test_update_existing_moodle_user_for_linked_staff_account(self):
        LearningUserLink.objects.create(
            user=self.user,
            moodle_user_id=42,
            moodle_username="staff@example.com",
            moodle_email="staff@example.com",
        )
        client = self._client()
        client.get_users_by_id.side_effect = [
            [{"id": 42, "username": "staff@example.com", "email": "staff@example.com"}],
            [{"id": 42, "username": "staff@example.com", "email": "staff@example.com"}],
        ]

        link = ensure_moodle_account(self.user, client=client)

        self.assertEqual(link.moodle_user_id, 42)
        client.update_users.assert_called_once()
        payload = client.update_users.call_args.args[0][0]
        self.assertEqual(payload["id"], 42)
        self.assertEqual(payload["idnumber"], f"django:{self.user.pk}")
        self.assertEqual(payload["email"], self.user.email)

    @override_settings(MOODLE_USER_AUTH_PLUGIN="oidc")
    def test_updates_existing_moodle_user_auth_plugin_to_oidc(self):
        LearningUserLink.objects.create(
            user=self.user,
            moodle_user_id=42,
            moodle_username="staff@example.com",
            moodle_email="staff@example.com",
        )
        client = self._client()
        client.get_users_by_id.side_effect = [
            [{"id": 42, "username": "staff@example.com", "email": "staff@example.com", "auth": "manual"}],
            [{"id": 42, "username": "staff@example.com", "email": "staff@example.com", "auth": "oidc"}],
        ]

        ensure_moodle_account(self.user, client=client)

        payload = client.update_users.call_args.args[0][0]
        self.assertEqual(payload["auth"], "oidc")

    def test_raise_clear_error_when_other_django_user_owns_same_moodle_user(self):
        other = User.objects.create_user(
            username="other@example.com",
            email="other@example.com",
            password="Secret123!",
            is_staff=True,
            is_active=True,
        )
        LearningUserLink.objects.create(
            user=other,
            moodle_user_id=77,
            moodle_username="other@example.com",
            moodle_email="other@example.com",
        )
        client = self._client()
        client.get_users_by_email.return_value = [
            {"id": 77, "username": "staff@example.com", "email": self.user.email}
        ]

        with self.assertRaises(MoodleApiError):
            ensure_moodle_account(self.user, client=client)


class MoodleProvisioningSignalTests(TestCase):
    @override_settings(MOODLE_BASE_URL="https://learn.example.com", MOODLE_WEB_SERVICE_TOKEN="token")
    @patch("learning_app.signals.sync_moodle_account_for_user")
    def test_staff_user_save_triggers_moodle_provisioning(self, mocked_sync):
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

    @override_settings(MOODLE_BASE_URL="https://learn.example.com", MOODLE_WEB_SERVICE_TOKEN="token")
    @patch("learning_app.signals.sync_moodle_account_for_user")
    def test_non_staff_user_save_does_not_trigger_moodle_provisioning(self, mocked_sync):
        with self.captureOnCommitCallbacks(execute=True):
            User.objects.create_user(
                username="external@example.com",
                email="external@example.com",
                password="Secret123!",
                is_staff=False,
                is_active=True,
            )

        mocked_sync.assert_not_called()


class MoodleLaunchFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="launch@example.com",
            email="launch@example.com",
            password="Secret123!",
            is_staff=True,
            is_active=True,
        )
        self.client = Client()
        self.client.force_login(self.user)

    @override_settings(
        MOODLE_BASE_URL="https://learn.example.com",
        MOODLE_LAUNCH_PATH="/my/",
        MOODLE_SSO_LAUNCH_MODE="oidc",
        MOODLE_LOGOUT_FIRST_PATH="/local/imc_sso/logout_first.php",
        MOODLE_OIDC_LOGIN_PATH="/auth/oidc/",
        MOODLE_OIDC_LOGIN_SOURCE="django",
        MOODLE_OIDC_PROMPT_LOGIN=False,
    )
    def test_launch_redirects_to_moodle_oidc_entrypoint_by_default(self):
        response = self.client.get(reverse("learning_app:launch"))

        self.assertRedirects(
            response,
            "https://learn.example.com/local/imc_sso/logout_first.php?next=%2Fauth%2Foidc%2F%3Fsource%3Ddjango",
            fetch_redirect_response=False,
        )

    @override_settings(
        MOODLE_BASE_URL="https://learn.example.com",
        MOODLE_LAUNCH_PATH="/my/",
        MOODLE_SSO_LAUNCH_MODE="page",
    )
    def test_launch_can_redirect_directly_to_target_page(self):
        response = self.client.get(reverse("learning_app:launch"))

        self.assertRedirects(response, "https://learn.example.com/my/", fetch_redirect_response=False)

    @override_settings(
        MOODLE_BASE_URL="https://learn.example.com",
        MOODLE_SSO_LAUNCH_MODE="page",
    )
    def test_launch_accepts_explicit_next_path(self):
        response = self.client.get(reverse("learning_app:launch"), {"next": "/course/view.php?id=7"})

        self.assertRedirects(
            response,
            "https://learn.example.com/course/view.php?id=7",
            fetch_redirect_response=False,
        )

    @override_settings(MOODLE_BASE_URL="")
    def test_launch_returns_to_dashboard_when_moodle_not_configured(self):
        response = self.client.get(reverse("learning_app:launch"))

        self.assertRedirects(response, "/#learning", fetch_redirect_response=False)
