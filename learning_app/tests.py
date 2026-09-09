from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import Client
from django.test import TestCase, override_settings
from django.urls import reverse

from learning_app.models import (
    LearningCourse,
    LearningCourseResult,
    LearningEnrollment,
    LearningSyncRun,
    LearningUserLink,
)
from learning_app.moodle_api import MoodleApiError
from learning_app.provisioning import ensure_moodle_account
from learning_app.sync import sync_staff_learning, sync_user_learning

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


class MoodleLearningSyncTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="learner@example.com",
            email="learner@example.com",
            password="Secret123!",
            is_staff=True,
            is_active=True,
        )
        self.link = LearningUserLink.objects.create(
            user=self.user,
            moodle_user_id=56,
            moodle_username=self.user.username,
            moodle_email=self.user.email,
        )

    def _client(self):
        client = Mock()
        client.config.base_url = "https://learn.example.com"
        client.get_user_courses.return_value = [
            {
                "id": 3,
                "shortname": "DB",
                "fullname": "Database basics",
                "visible": True,
                "progress": 50,
            }
        ]
        client.get_users_by_id.return_value = [
            {
                "id": 56,
                "username": self.user.username,
                "email": self.user.email,
            }
        ]
        client.get_activities_completion_status.return_value = {
            "statuses": [{"state": 1}, {"state": 0}]
        }
        return client

    @patch("learning_app.sync.ensure_moodle_account")
    def test_saves_activity_progress_when_course_completion_api_is_unavailable(self, mocked_ensure):
        mocked_ensure.return_value = self.link
        client = self._client()
        client.get_course_completion_status.side_effect = MoodleApiError(
            "Course does not have completion criteria."
        )

        stats = sync_user_learning(self.user, client=client)

        course = LearningCourse.objects.get(moodle_course_id=3)
        self.assertTrue(LearningEnrollment.objects.filter(user=self.user, course=course).exists())
        result = LearningCourseResult.objects.get(user=self.user, course=course)
        self.assertEqual(result.status, LearningCourseResult.Status.IN_PROGRESS)
        self.assertEqual(result.progress_percent, 50)
        self.assertEqual(stats["enrollments_upserted"], 1)
        self.assertEqual(stats["results_upserted"], 1)
        self.assertEqual(stats["results_skipped"], 0)

    @patch("learning_app.sync.ensure_moodle_account")
    def test_keeps_enrollment_when_all_completion_apis_are_unavailable(self, mocked_ensure):
        mocked_ensure.return_value = self.link
        client = self._client()
        client.get_course_completion_status.side_effect = MoodleApiError(
            "Course does not have completion criteria."
        )
        client.get_activities_completion_status.side_effect = MoodleApiError(
            "Activity completion is unavailable."
        )

        stats = sync_user_learning(self.user, client=client)

        course = LearningCourse.objects.get(moodle_course_id=3)
        self.assertTrue(LearningEnrollment.objects.filter(user=self.user, course=course).exists())
        self.assertFalse(LearningCourseResult.objects.filter(user=self.user, course=course).exists())
        self.assertEqual(stats["results_upserted"], 0)
        self.assertEqual(stats["results_skipped"], 1)

    @patch("learning_app.sync.ensure_moodle_account")
    def test_course_list_api_error_still_fails_user_sync(self, mocked_ensure):
        mocked_ensure.return_value = self.link
        client = self._client()
        client.get_user_courses.side_effect = MoodleApiError("Course list unavailable.")

        with self.assertRaisesMessage(MoodleApiError, "Course list unavailable."):
            sync_user_learning(self.user, client=client)

        self.assertFalse(LearningEnrollment.objects.filter(user=self.user).exists())

    @patch("learning_app.sync.ensure_moodle_account")
    def test_sync_run_records_activity_result_without_course_completion(self, mocked_ensure):
        mocked_ensure.return_value = self.link
        client = self._client()
        client.get_course_completion_status.side_effect = MoodleApiError(
            "Course does not have completion criteria."
        )
        run = LearningSyncRun.objects.create(
            scope=LearningSyncRun.Scope.FULL,
            status=LearningSyncRun.Status.STARTED,
        )

        stats = sync_staff_learning(
            users=User.objects.filter(pk=self.user.pk),
            client=client,
            run=run,
        )

        run.refresh_from_db()
        self.assertEqual(run.status, LearningSyncRun.Status.SUCCESS)
        self.assertEqual(stats["results_upserted"], 1)
        self.assertEqual(stats["results_skipped"], 0)
        self.assertEqual(run.stats["results_upserted"], 1)
        self.assertEqual(run.stats["results_skipped"], 0)
