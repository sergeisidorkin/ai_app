import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
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

from core.dsh import build_dsh_overview
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
from policy_app.models import ADMIN_GROUP, DEPARTMENT_HEAD_GROUP, EXPERT_GROUP, LAWYER_GROUP
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


class SidebarDshLinkTests(TestCase):
    def _staff(self, username, **kwargs):
        return User.objects.create_user(
            username=username,
            email=username,
            password="Secret123!",
            is_staff=True,
            is_active=True,
            **kwargs,
        )

    def _admin(self, username):
        user = self._staff(username)
        group, _ = Group.objects.get_or_create(name=ADMIN_GROUP)
        user.groups.add(group)
        Employee.objects.create(user=user, role=ADMIN_GROUP)
        return user

    @override_settings(DSH_BASE_URL="http://127.0.0.1:3080", DSH_LAUNCH_URL_FILE="")
    def test_home_sidebar_contains_dsh_link_after_logs(self):
        client = Client()
        client.force_login(self._admin("dsh-admin@example.com"))

        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn('href="/dsh/"', content)
        self.assertIn("bi-robot", content)
        self.assertIn("Консоль ИИ", content)
        self.assertLess(content.find("Логи"), content.find("Консоль ИИ"))

    @override_settings(DSH_BASE_URL="", DSH_LAUNCH_URL_FILE="")
    def test_home_sidebar_hides_dsh_link_when_url_is_empty(self):
        client = Client()
        client.force_login(self._admin("dsh-hidden@example.com"))

        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Консоль ИИ")

    @override_settings(DSH_BASE_URL="http://127.0.0.1:3080", DSH_LAUNCH_URL_FILE="")
    def test_home_sidebar_hides_dsh_link_for_expert(self):
        user = self._staff("dsh-expert@example.com")
        Group.objects.get_or_create(name=EXPERT_GROUP)
        user.groups.add(Group.objects.get(name=EXPERT_GROUP))
        Employee.objects.create(user=user, role=EXPERT_GROUP)
        client = Client()
        client.force_login(user)

        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Консоль ИИ")

    def test_build_dsh_overview_strips_trailing_slash(self):
        with override_settings(DSH_BASE_URL="http://127.0.0.1:3080/", DSH_LAUNCH_URL_FILE=""):
            overview = build_dsh_overview()
        self.assertEqual(overview["dsh_launch_url"], "http://127.0.0.1:3080/")
        self.assertEqual(overview["dsh_open_url"], "/dsh/")
        self.assertTrue(overview["dsh_enabled"])

    def test_build_dsh_overview_prefers_launch_file(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write("http://127.0.0.1:3080/?token=test-token\n")
            path = handle.name
        try:
            with override_settings(
                DSH_BASE_URL="http://127.0.0.1:3080",
                DSH_LAUNCH_URL_FILE=path,
            ):
                overview = build_dsh_overview()
        finally:
            os.unlink(path)
        self.assertEqual(
            overview["dsh_launch_url"],
            "http://127.0.0.1:3080/?token=test-token",
        )
        self.assertTrue(overview["dsh_enabled"])

    def test_build_dsh_overview_rewrites_loopback_host_to_match_request(self):
        factory = RequestFactory()
        request = factory.get("/", HTTP_HOST="localhost:8000")
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write("http://127.0.0.1:3080/?token=test-token\n")
            path = handle.name
        try:
            with override_settings(
                DSH_BASE_URL="http://127.0.0.1:3080",
                DSH_LAUNCH_URL_FILE=path,
            ):
                overview = build_dsh_overview(request)
        finally:
            os.unlink(path)
        self.assertEqual(
            overview["dsh_launch_url"],
            "http://localhost:3080/?token=test-token",
        )

    def test_dsh_open_redirects_admin_to_token_url(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write("http://127.0.0.1:3080/?token=test-token\n")
            path = handle.name
        client = Client()
        client.force_login(self._admin("dsh-open@example.com"))
        try:
            with override_settings(DSH_LAUNCH_URL_FILE=path, ALLOWED_HOSTS=["localhost", "127.0.0.1", "testserver"]):
                response = client.get("/dsh/", HTTP_HOST="localhost:8000")
        finally:
            os.unlink(path)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "http://localhost:3080/?token=test-token")

    @override_settings(DSH_BASE_URL="http://127.0.0.1:3080", DSH_LAUNCH_URL_FILE="")
    def test_dsh_open_rejects_non_admin_staff(self):
        client = Client()
        client.force_login(self._staff("dsh-open-staff@example.com"))

        response = client.get("/dsh/")

        self.assertEqual(response.status_code, 403)

    @override_settings(DSH_BASE_URL="http://127.0.0.1:3080", DSH_LAUNCH_URL_FILE="")
    def test_dsh_open_rejects_expert(self):
        user = self._staff("dsh-open-expert@example.com")
        Group.objects.get_or_create(name=EXPERT_GROUP)
        user.groups.add(Group.objects.get(name=EXPERT_GROUP))
        Employee.objects.create(user=user, role=EXPERT_GROUP)
        client = Client()
        client.force_login(user)

        response = client.get("/dsh/")

        self.assertEqual(response.status_code, 403)


class ChecklistSortSidebarTests(TestCase):
    def test_admin_sees_checklists_subsections(self):
        user = get_user_model().objects.create_user(
            username="chk-admin@example.com",
            email="chk-admin@example.com",
            password="Secret123!",
            is_staff=True,
            is_active=True,
        )
        Group.objects.get_or_create(name=ADMIN_GROUP)
        user.groups.add(Group.objects.get(name=ADMIN_GROUP))
        Employee.objects.create(user=user, role=ADMIN_GROUP)
        client = Client()
        client.force_login(user)

        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Чек-листы: Сортировка")
        self.assertContains(response, 'id="checklists-second-sidebar-list"')

    def test_staff_without_admin_role_sees_single_checklists_page(self):
        user = get_user_model().objects.create_user(
            username="chk-staff@example.com",
            email="chk-staff@example.com",
            password="Secret123!",
            is_staff=True,
            is_active=True,
        )
        client = Client()
        client.force_login(user)

        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="checklists-second-sidebar-list"')
        self.assertContains(response, 'href="#checklists"')


class DshHeadlessRunTests(SimpleTestCase):
    def test_explicit_command_is_used_as_is(self):
        from core.dsh_run import command_parts

        with override_settings(
            DSH_HEADLESS_CMD="/usr/local/bin/dsh --profile headless",
            DSH_HEADLESS_CONTAINER_CWD="",
            DSH_SORT_WORKSPACE="/tmp/sort-runs",
        ):
            self.assertEqual(
                command_parts("/tmp/sort-runs/1"),
                ["/usr/local/bin/dsh", "--profile", "headless"],
            )

    def test_npx_is_not_rewritten(self):
        from core.dsh_run import command_parts

        with override_settings(
            DSH_HEADLESS_CMD="npx --yes @deepseek-ai/dsh@0.1.5-rc.1 --profile headless",
            DSH_HEADLESS_CONTAINER_CWD="",
        ):
            self.assertEqual(
                command_parts("/tmp/run"),
                ["npx", "--yes", "@deepseek-ai/dsh@0.1.5-rc.1", "--profile", "headless"],
            )

    def test_docker_command_maps_host_cwd_into_container(self):
        from core.dsh_run import command_parts, headless_env

        host_root = "/opt/dsh/workspace/sort-runs"
        host_cwd = "/opt/dsh/workspace/sort-runs/42"
        with override_settings(
            DSH_HEADLESS_CMD=(
                "docker compose --project-directory /opt/dsh exec -T "
                "-w {cwd} dsh dsh --profile headless"
            ),
            DSH_SORT_WORKSPACE=host_root,
            DSH_HEADLESS_CONTAINER_CWD="/workspace/sort-runs",
            DSH_HOME="/opt/dsh/home",
            DSH_NODE_BIN="/home/deploy/.nvm/versions/node/v22.20.0/bin",
            DSH_NPM_CACHE="/tmp/should-not-be-used",
        ):
            parts = command_parts(host_cwd)
            self.assertEqual(parts[0], "docker")
            self.assertIn("-w", parts)
            self.assertEqual(parts[parts.index("-w") + 1], "/workspace/sort-runs/42")
            self.assertNotIn(str(host_cwd), parts)
            env = headless_env(parts)
            self.assertNotEqual(env.get("DSH_HOME"), "/opt/dsh/home")
            self.assertFalse(
                env["PATH"].startswith("/home/deploy/.nvm/versions/node/v22.20.0/bin")
            )
            self.assertNotEqual(env.get("npm_config_cache"), "/tmp/should-not-be-used")

    def test_native_env_uses_configured_node_and_home(self):
        from core.dsh_run import headless_env

        with override_settings(
            DSH_HOME="/tmp/dsh-home",
            DSH_NODE_BIN="/tmp/nvm/bin",
            DSH_NPM_CACHE="",
        ):
            env = headless_env(["/tmp/dsh", "--profile", "headless"])
            self.assertEqual(env["DSH_HOME"], "/tmp/dsh-home")
            self.assertTrue(env["PATH"].startswith("/tmp/nvm/bin"))

    def test_empty_command_mentions_both_environments(self):
        from core.dsh_run import DshRunError, command_parts

        with override_settings(DSH_HEADLESS_CMD="", DSH_HEADLESS_CONTAINER_CWD=""):
            with self.assertRaises(DshRunError) as raised:
                command_parts("/tmp/run")
        message = str(raised.exception)
        self.assertIn("./scripts/dev_dsh.sh", message)
        self.assertIn("/opt/dsh", message)

    def test_summarize_failure_hides_npm_engine_wall(self):
        from core.dsh_run import _summarize_failure

        stderr = (
            "npm warn EBADENGINE Unsupported engine { package: 'sharp@0.35.4', "
            "required: { node: '>=20.9.0' }, current: { node: 'v18.20.8' } }\n"
            * 20
            + "npm error EACCES: permission denied, rename '/Users/sergei/.npm/_cacache/tmp/x'\n"
        )
        text = _summarize_failure("", stderr, 1)
        self.assertIn("EACCES", text)
        self.assertNotIn("EBADENGINE", text)
        self.assertIn("Node >= 20", text)


class DshBrandingTests(SimpleTestCase):
    repo_root = Path(__file__).resolve().parents[1]
    branding_dir = repo_root / "deploy" / "dsh" / "branding"

    def test_branding_files_use_imc_montan_ai_and_app_favicon(self):
        brand = (self.branding_dir / "brand.yaml").read_text(encoding="utf-8")
        logo = self.branding_dir / "logo.svg"
        favicon = self.repo_root / "core" / "static" / "core" / "icons" / "favicon.svg"
        self.assertIn("productName: IMC Montan AI", brand)
        self.assertIn("plugin: imc-dsh-brand", brand)
        self.assertTrue(logo.is_file())
        plugin = self.repo_root / "deploy" / "dsh" / "plugins" / "imc-brand" / "package.json"
        self.assertTrue(plugin.is_file())
        self.assertEqual(json.loads(plugin.read_text(encoding="utf-8"))["name"], "imc-dsh-brand")
        self.assertTrue(favicon.is_file())
        self.assertEqual(logo.read_bytes(), favicon.read_bytes())

    def test_apply_and_sync_scripts_are_valid_bash(self):
        for rel in ("deploy/dsh/apply-brand.sh", "deploy/dsh/sync-sidecar.sh"):
            script = self.repo_root / rel
            result = subprocess.run(
                ["bash", "-n", str(script)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_django_deploy_syncs_dsh_sidecar_when_it_changes(self):
        workflow = (self.repo_root / ".github" / "workflows" / "deploy.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("sync-sidecar.sh", workflow)
        self.assertIn("SIDECAR_CHANGED=1", workflow)
        self.assertIn("dsh-healthcheck.sh", workflow)

    def test_sync_sidecar_copies_branding_into_an_existing_root(self):
        with tempfile.TemporaryDirectory() as raw:
            dest = Path(raw)
            (dest / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
            result = subprocess.run(
                [
                    "bash",
                    str(self.repo_root / "deploy" / "dsh" / "sync-sidecar.sh"),
                    str(self.repo_root),
                    str(dest),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("SIDECAR_CHANGED=1", result.stdout)
            copied = dest / "branding" / "logo.svg"
            self.assertTrue((dest / "apply-brand.sh").is_file())
            self.assertTrue((dest / "plugins" / "imc-brand" / "index.js").is_file())
            self.assertTrue(copied.is_file())
            self.assertEqual(
                copied.read_bytes(),
                (self.repo_root / "core" / "static" / "core" / "icons" / "favicon.svg").read_bytes(),
            )
            again = subprocess.run(
                [
                    "bash",
                    str(self.repo_root / "deploy" / "dsh" / "sync-sidecar.sh"),
                    str(self.repo_root),
                    str(dest),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertIn("SIDECAR_CHANGED=0", again.stdout)

