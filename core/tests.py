import json
import os
import subprocess
import sys
from unittest.mock import patch
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.http import HttpResponse, StreamingHttpResponse
from django.test import (
    Client,
    RequestFactory,
    SimpleTestCase,
    TestCase,
    override_settings,
)
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
from core.middleware import PolicyObservabilityMiddleware
from core.models import CloudStorageSettings
from policy_app.models import DEPARTMENT_HEAD_GROUP, EXPERT_GROUP, LAWYER_GROUP
from users_app.models import Employee

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


class HomePagePermissionsTests(TestCase):
    FREELANCER_LABEL = "Внештатный сотрудник"

    def test_staff_gets_production_calendar_subsection(self):
        user = User.objects.create_user(
            username="staff-home",
            email="staff-home@example.com",
            password="Secret123!",
            is_staff=True,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Производственный календарь")
        self.assertContains(response, 'data-clf-section="production-calendar"', html=False)

    def test_staff_gets_projects_launch_subsection(self):
        user = User.objects.create_user(
            username="staff-projects-home",
            email="staff-projects-home@example.com",
            password="Secret123!",
            is_staff=True,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="projects-second-sidebar-list"', html=False)
        self.assertContains(response, 'data-projects-section="launch"', html=False)
        self.assertContains(response, 'data-projects-section="scope"', html=False)
        self.assertContains(response, 'data-projects-section="team"', html=False)
        self.assertContains(response, 'data-projects-section="info-request"', html=False)
        self.assertContains(response, 'id="projects-section-title">Проекты</h5>', html=False)
        self.assertContains(response, 'id="projects-content-launch" class="projects-section-content"', html=False)
        self.assertContains(response, 'id="projects-content-scope" class="projects-section-content d-none"', html=False)
        self.assertContains(response, 'id="projects-content-team" class="projects-section-content d-none"', html=False)
        self.assertContains(response, 'id="projects-content-info-request" class="projects-section-content d-none"', html=False)
        self.assertContains(response, 'id="master-project-filter-dropdown"', html=False)
        self.assertContains(response, 'id="projects-pane"', html=False)
        self.assertContains(response, 'id="performers-pane"', html=False)

    def test_staff_proposal_header_filters_match_product_filter_markup(self):
        user = User.objects.create_user(
            username="staff-proposal-filter-home",
            email="staff-proposal-filter-home@example.com",
            password="Secret123!",
            is_staff=True,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="policy-product-filter-toggle"', html=False)
        self.assertContains(response, 'id="proposal-kind-filter-toggle"', html=False)
        self.assertContains(response, 'id="proposal-status-filter-toggle"', html=False)
        self.assertContains(
            response,
            'class="btn btn-outline-primary btn-sm dropdown-toggle" type="button"\n'
            '                          id="policy-product-filter-toggle"',
            html=False,
        )
        self.assertContains(
            response,
            'class="btn btn-outline-primary btn-sm dropdown-toggle" type="button"\n'
            '                          id="proposal-kind-filter-toggle"',
            html=False,
        )
        self.assertContains(
            response,
            'class="btn btn-outline-primary btn-sm dropdown-toggle" type="button"\n'
            '                          id="proposal-status-filter-toggle"',
            html=False,
        )
        self.assertNotContains(
            response,
            'class="btn btn-primary btn-sm dropdown-toggle" type="button"\n'
            '                          id="proposal-kind-filter-toggle"',
            html=False,
        )
        self.assertNotContains(
            response,
            'class="btn btn-primary btn-sm dropdown-toggle" type="button"\n'
            '                          id="proposal-status-filter-toggle"',
            html=False,
        )

    def test_department_head_menu_hides_restricted_sections(self):
        user = User.objects.create_user(
            username="department-head-home",
            email="department-head-home@example.com",
            password="Secret123!",
            is_staff=True,
        )
        Employee.objects.create(user=user, role=DEPARTMENT_HEAD_GROUP)
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Подключения")
        self.assertNotContains(response, '<span class="link-text">Почта</span>', html=False)
        self.assertNotContains(response, '<span class="link-text">Шаблоны</span>', html=False)
        self.assertNotContains(response, '<span class="link-text">Отладка</span>', html=False)
        self.assertNotContains(response, '<span class="link-text">Логи</span>', html=False)
        self.assertNotContains(response, 'section id="templates"', html=False)
        self.assertNotContains(response, 'section id="debugger"', html=False)

    def test_freelancer_employee_does_not_get_worktime_section(self):
        user = User.objects.create_user(
            username="freelancer-home",
            email="freelancer-home@example.com",
            password="Secret123!",
            is_staff=True,
        )
        Employee.objects.create(user=user, employment=self.FREELANCER_LABEL)
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'href="#worktime"', html=False)
        self.assertNotContains(response, 'section id="worktime"', html=False)

    def test_expert_does_not_get_classifiers_section_markup(self):
        user = User.objects.create_user(
            username="expert-home",
            email="expert-home@example.com",
            password="Secret123!",
            is_staff=True,
        )
        expert_group, _ = Group.objects.get_or_create(name=EXPERT_GROUP)
        user.groups.add(expert_group)
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<span class="link-text">Справочники</span>', html=False)
        self.assertNotContains(response, 'section id="classifiers"', html=False)

    def test_expert_contracts_section_starts_with_performers_only(self):
        user = User.objects.create_user(
            username="expert-contracts-home",
            email="expert-contracts-home@example.com",
            password="Secret123!",
            is_staff=True,
        )
        expert_group, _ = Group.objects.get_or_create(name=EXPERT_GROUP)
        user.groups.add(expert_group)
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'data-contracts-section="in-development"', html=False)
        self.assertNotContains(response, 'data-contracts-section="performer-requisites"', html=False)
        self.assertNotContains(response, 'id="contracts-content-performer-requisites"', html=False)
        self.assertNotContains(response, 'id="contracts-content-in-development"', html=False)
        self.assertNotContains(response, 'id="contracts-section-title">Клиенты: заключение договора', html=False)
        self.assertContains(response, 'id="contracts-master-status-filter-dropdown"', html=False)
        self.assertContains(
            response,
            'class="list-group-item list-group-item-action active"\n'
            '                 data-contracts-section="in-progress"',
            html=False,
        )
        self.assertContains(
            response,
            'id="contracts-content-in-progress" class="contracts-section-content"',
            html=False,
        )

    def test_staff_gets_contract_requisites_subsection_after_conclusion(self):
        user = User.objects.create_user(
            username="staff-contract-requisites-home",
            email="staff-contract-requisites-home@example.com",
            password="Secret123!",
            is_staff=True,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-contracts-section="performer-requisites"', html=False)
        self.assertContains(response, 'id="contracts-content-performer-requisites"', html=False)
        self.assertLess(
            response.content.decode().index('data-contracts-section="in-progress"'),
            response.content.decode().index('data-contracts-section="performer-execution"'),
        )
        self.assertLess(
            response.content.decode().index('data-contracts-section="performer-execution"'),
            response.content.decode().index('data-contracts-section="performer-requisites"'),
        )

    def test_lawyer_gets_contract_requisites_subsection(self):
        user = User.objects.create_user(
            username="lawyer-contract-requisites-home",
            email="lawyer-contract-requisites-home@example.com",
            password="Secret123!",
            is_staff=True,
        )
        lawyer_group, _ = Group.objects.get_or_create(name=LAWYER_GROUP)
        user.groups.add(lawyer_group)
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-contracts-section="performer-requisites"', html=False)

    def test_superuser_lawyer_profile_link_opens_user_profile(self):
        user = User.objects.create_user(
            username="superuser-lawyer-home",
            email="superuser-lawyer-home@example.com",
            password="Secret123!",
            is_staff=True,
            is_superuser=True,
        )
        Employee.objects.create(user=user, role=LAWYER_GROUP)
        lawyer_group, _ = Group.objects.get_or_create(name=LAWYER_GROUP)
        user.groups.add(lawyer_group)
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{reverse("user_profile")}"', html=False)
        self.assertContains(response, "Профиль пользователя")
        self.assertNotContains(response, f'href="{reverse("admin:index")}"', html=False)


class PolicyObservabilityMiddlewareTests(SimpleTestCase):
    def _request(self, route_name):
        request = RequestFactory().get(
            "/policy/policy/tables/products/",
            {"product": "sensitive-value"},
        )
        request.resolver_match = SimpleNamespace(url_name=route_name)
        return request

    @override_settings(
        POLICY_OBSERVABILITY_LATENCY_WARNING_MS=100000,
        POLICY_OBSERVABILITY_BYTES_WARNING=100000,
    )
    def test_policy_response_adds_timing_size_and_structured_log(self):
        def get_response(request):
            response = HttpResponse(b"abc")
            response["X-Policy-Cache"] = "HIT"
            response["Server-Timing"] = 'policy-cache;desc="hit"'
            return response

        middleware = PolicyObservabilityMiddleware(get_response)
        with self.assertLogs("policy.performance", level="INFO") as logs:
            response = middleware(self._request("policy_filter_catalog"))

        self.assertEqual(response["X-Policy-Response-Bytes"], "3")
        self.assertIn('policy-cache;desc="hit"', response["Server-Timing"])
        self.assertIn("app;dur=", response["Server-Timing"])
        event = json.loads(logs.output[0].split(":", 2)[2])
        self.assertEqual(event["route"], "policy_filter_catalog")
        self.assertEqual(event["cache_status"], "HIT")
        self.assertEqual(event["response_bytes"], 3)
        self.assertNotIn("sensitive-value", logs.output[0])

    @override_settings(
        POLICY_OBSERVABILITY_LATENCY_WARNING_MS=100000,
        POLICY_OBSERVABILITY_BYTES_WARNING=1,
    )
    def test_threshold_emits_warning_without_body_or_filters(self):
        middleware = PolicyObservabilityMiddleware(
            lambda request: HttpResponse(b"oversized")
        )

        with self.assertLogs("policy.performance", level="WARNING") as logs:
            middleware(self._request("policy_products_table"))

        self.assertNotIn("oversized", logs.output[0])
        self.assertNotIn("sensitive-value", logs.output[0])

    def test_non_policy_response_is_unchanged_and_not_logged(self):
        middleware = PolicyObservabilityMiddleware(
            lambda request: HttpResponse(b"home")
        )

        with patch("core.middleware.policy_performance_logger") as logger:
            response = middleware(self._request("home"))

        self.assertNotIn("Server-Timing", response.headers)
        self.assertNotIn("X-Policy-Response-Bytes", response.headers)
        logger.info.assert_not_called()
        logger.warning.assert_not_called()

    def test_streaming_response_is_not_consumed(self):
        consumed = []

        def stream():
            consumed.append(True)
            yield b"chunk"

        middleware = PolicyObservabilityMiddleware(
            lambda request: StreamingHttpResponse(stream())
        )
        with self.assertLogs("policy.performance", level="INFO"):
            response = middleware(self._request("policy_products_table"))

        self.assertEqual(consumed, [])
        self.assertTrue(response.streaming)
        self.assertNotIn("X-Policy-Response-Bytes", response.headers)
        self.assertIn("app;dur=", response["Server-Timing"])


class ProductionSettingsTests(SimpleTestCase):
    @staticmethod
    def _snapshot(database_url):
        script = """
import json
from settings import prod
print(json.dumps({
    "conn_health_checks": prod.DATABASES["default"].get("CONN_HEALTH_CHECKS"),
    "conn_max_age": prod.DATABASES["default"].get("CONN_MAX_AGE"),
    "engine": prod.DATABASES["default"]["ENGINE"],
    "storage": prod.STATICFILES_STORAGE,
    "whitenoise_count": prod.MIDDLEWARE.count(
        "whitenoise.middleware.WhiteNoiseMiddleware"
    ),
}))
"""
        environment = os.environ.copy()
        environment.pop("DB_CONN_HEALTH_CHECKS", None)
        environment.pop("DB_CONN_MAX_AGE", None)
        environment.update(
            {
                "DATABASE_URL": database_url,
                "DEBUG": "0",
                "DJANGO_ENV": "production",
                "ENV_FILE": "",
                "POLICY_CACHE_URL": "",
                "READ_DOTENV": "0",
                "SECRET_KEY": "production-settings-test",
            }
        )
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    def test_prod_postgresql_connections_and_single_whitenoise(self):
        snapshot = self._snapshot(
            "postgresql://user:password@127.0.0.1:5432/settings_test"
        )

        self.assertEqual(snapshot["whitenoise_count"], 1)
        self.assertEqual(snapshot["conn_max_age"], 60)
        self.assertIs(snapshot["conn_health_checks"], True)
        self.assertEqual(
            snapshot["storage"],
            "whitenoise.storage.CompressedManifestStaticFilesStorage",
        )

    def test_prod_sqlite_does_not_get_persistent_connection_options(self):
        snapshot = self._snapshot("sqlite:////tmp/ai-app-settings-test.sqlite3")

        self.assertEqual(snapshot["engine"], "django.db.backends.sqlite3")
        self.assertIsNone(snapshot["conn_max_age"])
        self.assertIsNone(snapshot["conn_health_checks"])
