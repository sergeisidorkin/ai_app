from unittest.mock import patch
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from oauth2_provider.models import get_application_model

from core.cloud_storage import (
    CloudStorageNotReadyError,
    create_project_workspace,
    get_nextcloud_root_path,
    is_nextcloud_root_configured,
    get_primary_cloud_storage,
    get_user_cloud_launch_url,
    is_yandex_disk_primary,
    set_nextcloud_root_path,
    set_primary_cloud_storage,
    validate_nextcloud_root_path,
)
from core.oidc import IMCOAuth2Validator
from core.oidc_settings import oidc_pkce_required
from core.models import CloudStorageSettings

User = get_user_model()
Application = get_application_model()


class OIDCValidatorTests(TestCase):
    def test_adds_expected_claims_for_staff_user(self):
        user = User.objects.create_user(
            username="staff@example.com",
            email="staff@example.com",
            password="Secret123!",
            first_name="Staff",
            last_name="User",
            is_staff=True,
        )
        group = Group.objects.create(name="Nextcloud Staff")
        user.groups.add(group)
        request = SimpleNamespace(user=user, scopes=["openid", "profile", "email"])

        claims = IMCOAuth2Validator().get_oidc_claims(None, None, request)

        self.assertEqual(claims["sub"], f"django:{user.pk}")
        self.assertEqual(claims["preferred_username"], "staff@example.com")
        self.assertEqual(claims["email"], "staff@example.com")
        self.assertEqual(claims["given_name"], "Staff")
        self.assertEqual(claims["family_name"], "User")
        self.assertTrue(claims["email_verified"])
        self.assertTrue(claims["is_staff"])
        self.assertEqual(claims["nextcloud_uid"], f"ncstaff-{user.pk}")
        self.assertEqual(claims["groups"], ["Nextcloud Staff"])
        self.assertEqual(claims["quota"], "")

    def test_omits_profile_and_email_claims_without_scopes(self):
        user = User.objects.create_user(
            username="plain-user",
            email="plain@example.com",
            password="Secret123!",
            is_staff=False,
        )
        request = SimpleNamespace(user=user, scopes=["openid"])

        claims = IMCOAuth2Validator().get_oidc_claims(None, None, request)

        self.assertEqual(claims, {"sub": f"django:{user.pk}"})


class OIDCPKCEPolicyTests(TestCase):
    def test_public_clients_require_pkce(self):
        app = Application.objects.create(
            name="Public app",
            client_id="public-client",
            client_type=Application.CLIENT_PUBLIC,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        )

        self.assertTrue(oidc_pkce_required(app.client_id))

    def test_confidential_clients_do_not_require_pkce(self):
        app = Application.objects.create(
            name="Confidential app",
            client_id="confidential-client",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        )

        self.assertFalse(oidc_pkce_required(app.client_id))


class OIDCAuthorizationViewTests(TestCase):
    @override_settings(MOODLE_OIDC_CLIENT_ID="moodle-client", OIDC_STAFF_ONLY_CLIENT_IDS=("moodle-client",))
    def test_non_staff_user_is_blocked_for_staff_only_client(self):
        user = User.objects.create_user(
            username="external@example.com",
            email="external@example.com",
            password="Secret123!",
            is_staff=False,
        )
        client = Client()
        client.force_login(user)

        response = client.get(reverse("oauth2_provider:authorize"), {"client_id": "moodle-client"})

        self.assertEqual(response.status_code, 403)


class CloudStorageSettingsTests(TestCase):
    def test_defaults_to_yandex_disk_singleton(self):
        settings_obj = CloudStorageSettings.get_solo()

        self.assertEqual(settings_obj.pk, CloudStorageSettings.singleton_pk)
        self.assertEqual(settings_obj.primary_storage, CloudStorageSettings.PrimaryStorage.YANDEX_DISK)
        self.assertEqual(get_primary_cloud_storage(), CloudStorageSettings.PrimaryStorage.YANDEX_DISK)
        self.assertTrue(is_yandex_disk_primary())

    def test_set_primary_cloud_storage_updates_singleton(self):
        set_primary_cloud_storage(CloudStorageSettings.PrimaryStorage.NEXTCLOUD)

        settings_obj = CloudStorageSettings.get_solo()

        self.assertEqual(settings_obj.pk, CloudStorageSettings.singleton_pk)
        self.assertEqual(settings_obj.primary_storage, CloudStorageSettings.PrimaryStorage.NEXTCLOUD)

    def test_set_nextcloud_root_path_normalizes_and_updates_singleton(self):
        set_nextcloud_root_path(" Corporate//Projects ")

        settings_obj = CloudStorageSettings.get_solo()

        self.assertEqual(settings_obj.nextcloud_root_path, "/Corporate/Projects")
        self.assertEqual(get_nextcloud_root_path(), "/Corporate/Projects")
        self.assertTrue(is_nextcloud_root_configured())

    def test_validate_nextcloud_root_path_rejects_dot_segments(self):
        with self.assertRaises(ValueError):
            validate_nextcloud_root_path("/Corporate/../Projects")


class CloudStorageRoutingTests(TestCase):
    @override_settings(
        NEXTCLOUD_BASE_URL="https://cloud.imcmontanai.ru",
        NEXTCLOUD_SSO_ENABLED=True,
        NEXTCLOUD_OIDC_LOGIN_PATH="/apps/user_oidc/login/1",
    )
    def test_user_cloud_launch_url_uses_nextcloud_when_selected(self):
        user = User.objects.create_user(
            username="cloud-user",
            email="cloud-user@example.com",
            password="Secret123!",
            is_staff=True,
        )
        set_primary_cloud_storage(CloudStorageSettings.PrimaryStorage.NEXTCLOUD)

        launch_url = get_user_cloud_launch_url(user)

        self.assertEqual(launch_url, "https://cloud.imcmontanai.ru/apps/user_oidc/login/1")

    def test_workspace_routing_delegates_to_yandex_by_default(self):
        with self.assertRaisesMessage(RuntimeError, "boom"):
            with patch("yandexdisk_app.workspace.create_project_workspace", side_effect=RuntimeError("boom")):
                create_project_workspace(object(), object())

    def test_workspace_routing_raises_controlled_error_for_nextcloud(self):
        set_primary_cloud_storage(CloudStorageSettings.PrimaryStorage.NEXTCLOUD)

        with self.assertRaises(CloudStorageNotReadyError):
            create_project_workspace(object(), object())

    @override_settings(
        NEXTCLOUD_OIDC_CLIENT_ID="nextcloud-client",
        OIDC_STAFF_ONLY_CLIENT_IDS=("nextcloud-client",),
    )
    def test_nextcloud_client_is_also_staff_only(self):
        user = User.objects.create_user(
            username="external2@example.com",
            email="external2@example.com",
            password="Secret123!",
            is_staff=False,
        )
        client = Client()
        client.force_login(user)

        response = client.get(reverse("oauth2_provider:authorize"), {"client_id": "nextcloud-client"})

        self.assertEqual(response.status_code, 403)
