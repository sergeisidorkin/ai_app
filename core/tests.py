from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from oauth2_provider.models import get_application_model

from core.oidc import IMCOAuth2Validator
from core.oidc_settings import oidc_pkce_required

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
        request = SimpleNamespace(user=user, scopes=["openid", "profile", "email"])

        claims = IMCOAuth2Validator().get_oidc_claims(None, None, request)

        self.assertEqual(claims["sub"], f"django:{user.pk}")
        self.assertEqual(claims["preferred_username"], "staff@example.com")
        self.assertEqual(claims["email"], "staff@example.com")
        self.assertEqual(claims["given_name"], "Staff")
        self.assertEqual(claims["family_name"], "User")
        self.assertTrue(claims["email_verified"])
        self.assertTrue(claims["is_staff"])

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
