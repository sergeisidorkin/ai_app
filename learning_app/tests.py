from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

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
