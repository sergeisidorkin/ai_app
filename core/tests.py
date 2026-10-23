import re
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
        self.assertContains(response, 'data-projects-section="report-submission"', html=False)
        self.assertContains(response, 'data-notification-counter-subsection="report_submission"', html=False)
        self.assertContains(response, 'id="projects-section-title">Проекты</h5>', html=False)
        self.assertContains(response, 'id="projects-content-launch" class="projects-section-content"', html=False)
        self.assertContains(response, 'id="projects-content-scope" class="projects-section-content d-none"', html=False)
        self.assertContains(response, 'id="projects-content-team" class="projects-section-content d-none"', html=False)
        self.assertContains(response, 'id="projects-content-info-request" class="projects-section-content d-none"', html=False)
        self.assertContains(response, 'id="projects-content-report-submission" class="projects-section-content d-none"', html=False)
        self.assertContains(response, 'id="master-project-filter-dropdown"', html=False)
        self.assertContains(
            response,
            'class="btn btn-outline-primary btn-sm dropdown-toggle" type="button"\n'
            '                            id="master-project-filter-toggle"',
            html=False,
        )
        self.assertNotContains(
            response,
            'class="btn btn-primary btn-sm dropdown-toggle" type="button"\n'
            '                            id="master-project-filter-toggle"',
            html=False,
        )
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

    def test_command_can_override_profile(self):
        from core.dsh_run import command_parts

        with override_settings(
            DSH_HEADLESS_CMD="/usr/local/bin/dsh --profile headless",
            DSH_HEADLESS_CONTAINER_CWD="",
        ):
            self.assertEqual(
                command_parts("/tmp/run", profile="report-check"),
                ["/usr/local/bin/dsh", "--profile", "report-check"],
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

    def test_run_headless_treats_truncated_stream_as_error(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        from core.dsh_run import DshRunError, run_headless

        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(
                DSH_HEADLESS_CMD="dsh --profile headless",
                DSH_HEADLESS_CONTAINER_CWD="",
            ):
                with patch(
                    "core.dsh_run.subprocess.Popen",
                    return_value=SimpleNamespace(
                        returncode=0,
                        communicate=lambda timeout: (
                            "partial table\nStream ended without finish_reason",
                            "",
                        ),
                    ),
                ):
                    with self.assertRaises(DshRunError) as raised:
                        run_headless("prompt", cwd=tmp)
        self.assertIn("оборвалась", str(raised.exception))

    def test_run_headless_renews_heartbeat_while_waiting(self):
        from unittest.mock import Mock, patch

        from core.dsh_run import run_headless

        class Process:
            returncode = 0

            def __init__(self):
                self.calls = 0

            def communicate(self, timeout):
                self.calls += 1
                if self.calls == 1:
                    raise subprocess.TimeoutExpired("dsh", timeout)
                return ("```json\n[]\n```", "")

        heartbeat = Mock(return_value=True)
        with tempfile.TemporaryDirectory() as tmp, override_settings(
            DSH_HEADLESS_CMD="dsh --profile headless",
            DSH_HEADLESS_CONTAINER_CWD="",
        ), patch("core.dsh_run.subprocess.Popen", return_value=Process()):
            output = run_headless(
                "prompt",
                cwd=tmp,
                heartbeat=heartbeat,
                heartbeat_interval=1,
            )
        self.assertIn("[]", output)
        heartbeat.assert_called_once()


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

    def test_local_dsh_registers_siliconflow_qwen_default(self):
        import yaml

        script = (self.repo_root / "scripts" / "dev_dsh.sh").read_text(encoding="utf-8")
        example = yaml.safe_load(
            (self.repo_root / "deploy" / "dsh" / "settings.yaml.example").read_text(
                encoding="utf-8"
            )
        )
        models = example["llm-pi-ai"]["providers"]["siliconflow"]["models"]
        model_ids = [model["id"] for model in models]
        self.assertIn("SILICONFLOW_API_KEY", script)
        self.assertIn("settings.yaml.example", script)
        self.assertIn('"provider": "siliconflow"', script)
        self.assertEqual(
            example["agent-default-model"],
            {"provider": "siliconflow", "model": "Qwen/Qwen3.5-27B"},
        )
        self.assertEqual(
            model_ids,
            [
                "Qwen/Qwen3.8-2.4T-A95B",
                "deepseek-ai/DeepSeek-V4-Pro-0813",
                "moonshotai/Kimi-K3",
                "zai-org/GLM-5.3",
                "MiniMaxAI/MiniMax-M3",
                "deepseek-ai/DeepSeek-V4-Flash-0731",
                "Qwen/Qwen3.5-122B-A10B",
                "Qwen/Qwen3.6-35B-A3B",
                "moonshotai/Kimi-K2.6",
                "zai-org/GLM-5.3-Flash",
                "Qwen/Qwen3.5-27B",
                "Qwen/Qwen3.6-27B",
                "Qwen/Qwen3.5-9B",
            ],
        )
        prefixes = [model["name"].split(" · ", 1)[0] for model in models]
        self.assertEqual(prefixes, ["Flagship"] * 5 + ["Balanced"] * 5 + ["Efficient"] * 3)
        default_model = next(model for model in models if model["id"] == "Qwen/Qwen3.5-27B")
        self.assertIn("off", default_model["reasoningEfforts"])
        self.assertNotIn(False, default_model["reasoningEfforts"])

    def test_reasoning_levels_follow_installed_model_scale(self):
        from unittest.mock import patch

        from core import dsh_catalog
        from core.dsh_catalog import catalog_reasoning_levels, reasoning_levels_for_entry

        payload = {
            "models": [
                {
                    "id": "qwen3.8-max",
                    "thinkingLevelMap": {
                        "off": None,
                        "minimal": None,
                        "low": "low",
                        "medium": "medium",
                        "high": None,
                        "xhigh": "xhigh",
                        "max": None,
                    },
                }
            ]
        }
        with tempfile.TemporaryDirectory() as raw:
            catalog_dir = Path(raw)
            (catalog_dir / "qwen-token-plan.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            dsh_catalog._catalog_reasoning_index.cache_clear()
            try:
                with patch("core.dsh_catalog._pi_ai_catalog_dir", return_value=catalog_dir):
                    catalog = [level for level, _wire in catalog_reasoning_levels("qwen3.8-max")]
                    self.assertEqual(catalog, ["low", "medium", "xhigh"])
                    offered = reasoning_levels_for_entry(
                        {"compat": {"thinkingFormat": "qwen"}},
                        {"id": "qwen3.8-max"},
                    )
                    self.assertEqual(offered, ["off", "low", "medium", "xhigh"])
            finally:
                dsh_catalog._catalog_reasoning_index.cache_clear()
        declared = reasoning_levels_for_entry(
            {"compat": {"thinkingFormat": "qwen"}},
            {"id": "Qwen/Qwen3.5-27B", "reasoningEfforts": {"off": None, "low": "low"}},
        )
        self.assertEqual(declared, ["off", "low"])

    def test_local_dsh_registers_alibaba_payg_catalog(self):
        import yaml

        script = (self.repo_root / "scripts" / "dev_dsh.sh").read_text(encoding="utf-8")
        example = yaml.safe_load(
            (self.repo_root / "deploy" / "dsh" / "settings.yaml.example").read_text(
                encoding="utf-8"
            )
        )
        alibaba = example["llm-pi-ai"]["providers"]["alibaba"]
        env_example = (self.repo_root / "deploy" / "dsh" / "dsh.env.example").read_text(
            encoding="utf-8"
        )
        compose = (self.repo_root / "deploy" / "dsh" / "docker-compose.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("DASHSCOPE_WS_API_KEY", script)
        self.assertIn("DASHSCOPE_WS_API_KEY=", env_example)
        self.assertIn("DASHSCOPE_WS_API_KEY:", compose)
        self.assertEqual(alibaba["displayName"], "Alibaba Cloud")
        self.assertEqual(alibaba["apiKeyEnv"], "DASHSCOPE_WS_API_KEY")
        self.assertEqual(alibaba["api"], "openai-completions")
        self.assertEqual(
            alibaba["baseURL"],
            "https://ws-3ypc7qxql8fr66i7.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
        )
        self.assertIn("fetch_openai_models", script)
        self.assertIn("/models", script)
        model_ids = [model["id"] for model in alibaba["models"]]
        self.assertGreaterEqual(len(model_ids), 150)
        self.assertEqual(len(model_ids), len(set(model_ids)))
        for required in ("qwen3.8-max", "qwen3.5-27b", "qwen-plus", "deepseek-v4.1-flash"):
            self.assertIn(required, model_ids)
        self.assertTrue(all(model["name"] == model["id"] for model in alibaba["models"]))
        self.assertFalse(
            any(
                " · " in str(model.get("name") or "")
                for model in alibaba["models"]
            )
        )
        self.assertEqual(
            example["agent-default-model"],
            {"provider": "siliconflow", "model": "Qwen/Qwen3.5-27B"},
        )

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
            sort_skill = dest / "skills" / "checklist-file-sort" / "SKILL.md"
            self.assertTrue(sort_skill.is_file())
            from checklists_app.sort_service import SORT_SKILL_VERSION

            self.assertIn(f"version: {SORT_SKILL_VERSION}", sort_skill.read_text(encoding="utf-8"))
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


class DshCatalogTests(SimpleTestCase):
    def test_lists_bundled_skills_and_models(self):
        from core.dsh_catalog import list_dsh_models, list_dsh_skills

        skills = dict(list_dsh_skills())
        self.assertIn("checklist-file-sort", skills)
        self.assertIn("checklist-file-verify", skills)
        self.assertIn("report-final-check", skills)
        models = dict(list_dsh_models())
        self.assertIn("Qwen/Qwen3.5-27B", models)
        self.assertTrue(models["Qwen/Qwen3.5-27B"])

    def test_prefers_dsh_home_skills_and_settings(self):
        from core.dsh_catalog import list_dsh_models, list_dsh_skills

        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            skill_dir = home / "skills" / "custom-check"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: custom-check\n---\n\n# custom-check\n",
                encoding="utf-8",
            )
            (home / "settings.yaml").write_text(
                "llm-pi-ai:\n  providers:\n    test:\n      models:\n"
                "        - id: test/model-1\n          name: Test Model\n",
                encoding="utf-8",
            )
            with override_settings(DSH_HOME=str(home)):
                skills = dict(list_dsh_skills())
                self.assertIn("custom-check", skills)
                self.assertIn("checklist-file-sort", skills)
                models = dict(list_dsh_models())
                self.assertEqual(models, {"test/model-1": "Test Model"})

    def test_groups_models_by_provider_display_name(self):
        from core.dsh_catalog import list_dsh_model_groups, list_dsh_models

        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            (home / "settings.yaml").write_text(
                "llm-pi-ai:\n  providers:\n"
                "    siliconflow:\n      displayName: SiliconFlow\n      models:\n"
                "        - id: sf/model-a\n          name: Model A\n"
                "    openrouter:\n      displayName: OpenRouter\n      models:\n"
                "        - id: or/model-b\n          name: Model B\n"
                "    empty:\n      displayName: Empty\n",
                encoding="utf-8",
            )
            with override_settings(DSH_HOME=str(home)):
                groups = list_dsh_model_groups()
                self.assertEqual(
                    groups,
                    [
                        ("SiliconFlow", [("sf/model-a", "Model A")]),
                        ("OpenRouter", [("or/model-b", "Model B")]),
                    ],
                )
                self.assertEqual(
                    list_dsh_models(),
                    [("sf/model-a", "Model A"), ("or/model-b", "Model B")],
                )




# ---------------------------------------------------------------------------
# Generic bulk row-order endpoint (core.row_order)
# ---------------------------------------------------------------------------


class RowOrderSaveViewTests(TestCase):
    """Behaviour of the shared /core/row-order/<key>/ endpoint."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="row-order-user", password="pass", is_staff=False)
        cls.staff = User.objects.create_user(username="row-order-staff", password="pass", is_staff=True)
        cls.superuser = User.objects.create_superuser(username="row-order-admin", password="pass")

    def _url(self, key):
        return reverse("row_order_save", args=[key])

    def _post(self, key, payload, user=None):
        client = Client()
        if user is not None:
            client.force_login(user)
        return client.post(
            self._url(key),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def _make_countries(self, count=4):
        from classifiers_app.models import OKSMCountry

        rows = []
        for idx in range(1, count + 1):
            rows.append(
                OKSMCountry.objects.create(
                    number=idx,
                    code=f"{idx:03d}",
                    short_name=f"Страна {idx}",
                    alpha2=f"A{idx}",
                    alpha3=f"AA{idx}",
                    position=idx,
                )
            )
        return rows

    def _ids_in_order(self, model):
        return list(model.objects.order_by("position", "id").values_list("pk", flat=True))

    def test_every_registered_spec_resolves_and_has_position_field(self):
        from core.row_order import get_row_order_spec, registered_row_order_keys

        keys = registered_row_order_keys()
        self.assertGreaterEqual(len(keys), 50)
        for key in keys:
            spec = get_row_order_spec(key)
            self.assertIsNotNone(spec, key)
            spec.model._meta.get_field(spec.position_field)
            spec.only_fields()
            self.assertEqual(reverse("row_order_save", args=[key]), f"/core/row-order/{key}/")

    def test_unknown_key_returns_404(self):
        response = self._post("no-such-table", {"ordered_ids": [1]}, user=self.staff)
        self.assertEqual(response.status_code, 404)

    def test_requires_login_and_post(self):
        rows = self._make_countries(2)
        response = self._post("oksm", {"ordered_ids": [rows[1].pk, rows[0].pk]})
        # EnforceLoginMiddleware redirects anonymous users; the view itself answers 403.
        self.assertIn(response.status_code, (302, 403))
        client = Client()
        client.force_login(self.user)
        self.assertEqual(client.get(self._url("oksm")).status_code, 405)

    def test_permission_hook_is_enforced(self):
        from users_app.models import Employee

        response = self._post("employee", {"ordered_ids": [1]}, user=self.user)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Employee.objects.exists())

    def test_full_reorder_renumbers_positions(self):
        from classifiers_app.models import OKSMCountry

        rows = self._make_countries(4)
        ids = [row.pk for row in rows]
        new_order = [ids[2], ids[0], ids[1], ids[3]]
        response = self._post("oksm", {"ordered_ids": new_order, "base_order_ids": ids}, user=self.user)
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["order_ids"], new_order)
        self.assertEqual(self._ids_in_order(OKSMCountry), new_order)
        self.assertEqual(
            list(OKSMCountry.objects.order_by("position").values_list("position", flat=True)),
            [1, 2, 3, 4],
        )

    def test_partial_set_permutes_only_listed_slots(self):
        from classifiers_app.models import OKSMCountry

        rows = self._make_countries(5)
        ids = [row.pk for row in rows]
        # A filtered table shows rows 2 and 4 only; the user moves row 4 above row 2.
        response = self._post(
            "oksm",
            {"ordered_ids": [ids[3], ids[1]], "base_order_ids": [ids[1], ids[3]]},
            user=self.user,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self._ids_in_order(OKSMCountry), [ids[0], ids[3], ids[2], ids[1], ids[4]])

    def test_noop_order_is_accepted_without_changes(self):
        from classifiers_app.models import OKSMCountry

        rows = self._make_countries(3)
        ids = [row.pk for row in rows]
        response = self._post("oksm", {"ordered_ids": ids, "base_order_ids": ids}, user=self.user)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["moved_ids"], [])
        self.assertEqual(self._ids_in_order(OKSMCountry), ids)

    def test_conflict_when_base_order_differs_from_database(self):
        from classifiers_app.models import OKSMCountry

        rows = self._make_countries(3)
        ids = [row.pk for row in rows]
        # Someone else already swapped rows 1 and 2.
        OKSMCountry.objects.filter(pk=ids[0]).update(position=2)
        OKSMCountry.objects.filter(pk=ids[1]).update(position=1)
        response = self._post(
            "oksm",
            {"ordered_ids": [ids[2], ids[0], ids[1]], "base_order_ids": ids},
            user=self.user,
        )
        self.assertEqual(response.status_code, 409)
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["current_ids"], [ids[1], ids[0], ids[2]])
        self.assertEqual(self._ids_in_order(OKSMCountry), [ids[1], ids[0], ids[2]])

    def test_conflict_when_rows_were_deleted(self):
        rows = self._make_countries(2)
        ids = [row.pk for row in rows]
        rows[1].delete()
        response = self._post("oksm", {"ordered_ids": [ids[1], ids[0]], "base_order_ids": ids}, user=self.user)
        self.assertEqual(response.status_code, 409)

    def test_invalid_payloads_return_400(self):
        rows = self._make_countries(2)
        ids = [row.pk for row in rows]
        cases = [
            {"ordered_ids": "oops"},
            {"ordered_ids": []},
            {"ordered_ids": [ids[0], ids[0]]},
            {"ordered_ids": ids, "base_order_ids": [ids[0]]},
        ]
        for payload in cases:
            response = self._post("oksm", payload, user=self.user)
            self.assertEqual(response.status_code, 400, payload)
        client = Client()
        client.force_login(self.user)
        response = client.post(self._url("oksm"), data="not json", content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_scoped_rows_are_reordered_inside_each_scope(self):
        from policy_app.models import Product, TypicalSection
        from requests_app.models import RequestItem, RequestTable

        product = Product.objects.create(short_name="RO-P", name_en="P", name_ru="П")
        section_a = TypicalSection.objects.create(product=product, code="A", short_name="A", name_en="A", name_ru="А")
        section_b = TypicalSection.objects.create(product=product, code="B", short_name="B", name_en="B", name_ru="Б")
        table_a = RequestTable.objects.create(product=product, section=section_a)
        table_b = RequestTable.objects.create(product=product, section=section_b)
        a1 = RequestItem.objects.create(table=table_a, position=1, code="A1", number=1)
        a2 = RequestItem.objects.create(table=table_a, position=2, code="A2", number=2)
        b1 = RequestItem.objects.create(table=table_b, position=1, code="B1", number=1)
        b2 = RequestItem.objects.create(table=table_b, position=2, code="B2", number=2)

        # The «все разделы» view lists both tables; the user swaps rows in table B only.
        response = self._post(
            "request-item",
            {
                "ordered_ids": [a1.pk, a2.pk, b2.pk, b1.pk],
                "base_order_ids": [a1.pk, a2.pk, b1.pk, b2.pk],
            },
            user=self.user,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            list(RequestItem.objects.filter(table=table_a).order_by("position").values_list("pk", flat=True)),
            [a1.pk, a2.pk],
        )
        self.assertEqual(
            list(RequestItem.objects.filter(table=table_b).order_by("position").values_list("pk", flat=True)),
            [b2.pk, b1.pk],
        )
        self.assertEqual(sorted(response.json()["moved_ids"]), sorted([b1.pk, b2.pk]))

    def test_locked_rows_cannot_be_displaced(self):
        from policy_app.models import Product, TypicalSection

        product = Product.objects.create(short_name="RO-L", name_en="P", name_ru="П")
        dsc = TypicalSection.objects.create(
            product=product, code="DSC", short_name="DSC", name_en="DSC", name_ru="ДСХ", is_system=True, position=1
        )
        s1 = TypicalSection.objects.create(product=product, code="S1", short_name="S1", name_en="S1", name_ru="С1", position=2)
        s2 = TypicalSection.objects.create(product=product, code="S2", short_name="S2", name_en="S2", name_ru="С2", position=3)

        # Moving S1 above the system DSC section is refused ...
        response = self._post(
            "typical-section",
            {"ordered_ids": [s1.pk, dsc.pk, s2.pk], "base_order_ids": [dsc.pk, s1.pk, s2.pk]},
            user=self.user,
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("ДСХ", response.json()["error"])
        self.assertEqual(
            list(TypicalSection.objects.filter(product=product).order_by("position").values_list("pk", flat=True)),
            [dsc.pk, s1.pk, s2.pk],
        )
        # ... while reordering below it works.
        response = self._post(
            "typical-section",
            {"ordered_ids": [dsc.pk, s2.pk, s1.pk], "base_order_ids": [dsc.pk, s1.pk, s2.pk]},
            user=self.user,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["events"]["policy-updated"]["reorderedTable"], "typical-sections")
        self.assertEqual(
            list(TypicalSection.objects.filter(product=product).order_by("position").values_list("pk", flat=True)),
            [dsc.pk, s2.pk, s1.pk],
        )

    def test_row_permission_applies_only_to_displaced_rows(self):
        from policy_app.models import Grade

        own1 = Grade.objects.create(grade_en="o1", grade_ru="с1", created_by=self.user, position=1)
        own2 = Grade.objects.create(grade_en="o2", grade_ru="с2", created_by=self.user, position=2)
        other1 = Grade.objects.create(grade_en="x1", grade_ru="ч1", created_by=self.staff, position=1)
        other2 = Grade.objects.create(grade_en="x2", grade_ru="ч2", created_by=self.staff, position=2)

        # Other owners' rows are listed (the table shows them) but stay in place: allowed.
        response = self._post(
            "grade",
            {
                "ordered_ids": [own2.pk, own1.pk, other1.pk, other2.pk],
                "base_order_ids": [own1.pk, own2.pk, other1.pk, other2.pk],
            },
            user=self.user,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            list(Grade.objects.filter(created_by=self.user).order_by("position").values_list("pk", flat=True)),
            [own2.pk, own1.pk],
        )
        # Displacing another owner's rows is forbidden for a regular user ...
        response = self._post(
            "grade",
            {"ordered_ids": [other2.pk, other1.pk], "base_order_ids": [other1.pk, other2.pk]},
            user=self.user,
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            list(Grade.objects.filter(created_by=self.staff).order_by("position").values_list("pk", flat=True)),
            [other1.pk, other2.pk],
        )
        # ... but allowed for a superuser.
        response = self._post(
            "grade",
            {"ordered_ids": [other2.pk, other1.pk], "base_order_ids": [other1.pk, other2.pk]},
            user=self.superuser,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            list(Grade.objects.filter(created_by=self.staff).order_by("position").values_list("pk", flat=True)),
            [other2.pk, other1.pk],
        )

    def test_base_filter_restricts_universe(self):
        from classifiers_app.models import LegalEntityRecord

        legal = LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS
        a = LegalEntityRecord.objects.create(attribute=legal, position=1)
        b = LegalEntityRecord.objects.create(attribute=legal, position=2)
        other = LegalEntityRecord.objects.create(attribute="Иное", position=3)

        response = self._post("bea", {"ordered_ids": [b.pk, a.pk], "base_order_ids": [a.pk, b.pk]}, user=self.user)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            list(LegalEntityRecord.objects.filter(attribute=legal).order_by("position").values_list("pk", flat=True)),
            [b.pk, a.pk],
        )
        other.refresh_from_db()
        self.assertEqual(other.position, 3)
        # A row outside the base filter is unknown to this key.
        response = self._post("bea", {"ordered_ids": [other.pk, a.pk], "base_order_ids": [a.pk, other.pk]}, user=self.user)
        self.assertEqual(response.status_code, 409)

    def test_after_save_and_events_hooks(self):
        from group_app.models import GroupMember

        m1 = GroupMember.objects.create(short_name="M1", country_name="Россия", country_code="643", position=1)
        m2 = GroupMember.objects.create(short_name="M2", country_name="Россия", country_code="643", position=2)
        with patch("group_app.row_order.resequence_group_members") as resequence:
            response = self._post(
                "group-member",
                {"ordered_ids": [m2.pk, m1.pk], "base_order_ids": [m1.pk, m2.pk]},
                user=self.staff,
            )
        self.assertEqual(response.status_code, 200, response.content)
        resequence.assert_called_once_with()
        self.assertNotIn("events", response.json())

        from contracts_app.models import ContractSubject
        from policy_app.models import Product

        product = Product.objects.create(short_name="RO-CS", name_en="P", name_ru="П")
        c1 = ContractSubject.objects.create(product=product, position=1)
        c2 = ContractSubject.objects.create(product=product, position=2)
        response = self._post(
            "contract-subject",
            {"ordered_ids": [c2.pk, c1.pk], "base_order_ids": [c1.pk, c2.pk]},
            user=self.staff,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["events"], {"field-params-updated": True})

    def test_validation_error_rolls_back_all_scopes(self):
        from core.row_order import RowOrderSpec, apply_row_order
        from classifiers_app.models import OKSMCountry
        from django.db import transaction
        from django.test import RequestFactory

        rows = self._make_countries(2)
        ids = [row.pk for row in rows]
        calls = []

        def _validate(request, scope):
            calls.append(scope.scope_key)
            return "nope"

        spec = RowOrderSpec(key="tmp-oksm", model=OKSMCountry, validate=_validate)
        request = RequestFactory().post("/")
        request.user = self.user
        with transaction.atomic():
            result, error = apply_row_order(request, spec, [ids[1], ids[0]], ids)
            self.assertIsNone(result)
            self.assertEqual(error.status_code, 409)
        self.assertEqual(calls, [()])
        self.assertEqual(self._ids_in_order(OKSMCountry), ids)


class LockedFieldHelpersTests(SimpleTestCase):
    """core.forms: единые параметры заблокированных полей."""

    def test_locked_attrs_defaults(self):
        from core.forms import locked_attrs

        attrs = locked_attrs()
        self.assertEqual(attrs["class"], "form-control readonly-field")
        self.assertIs(attrs["readonly"], True)
        self.assertEqual(attrs["tabindex"], "-1")
        self.assertNotIn("style", attrs)
        self.assertNotIn("disabled", attrs)

    def test_locked_attrs_extra_classes_base_and_attrs(self):
        from core.forms import locked_attrs

        attrs = locked_attrs("js-stage1-end", id="f1", placeholder="Код", min=0)
        self.assertEqual(attrs["class"], "form-control readonly-field js-stage1-end")
        self.assertEqual(attrs["id"], "f1")
        self.assertEqual(attrs["placeholder"], "Код")
        self.assertEqual(attrs["min"], 0)

        self.assertEqual(locked_attrs(base=None)["class"], "readonly-field")
        self.assertEqual(
            locked_attrs(base="form-control form-control-sm")["class"],
            "form-control form-control-sm readonly-field",
        )

    def test_locked_attrs_select_uses_disabled(self):
        from core.forms import locked_attrs

        attrs = locked_attrs(base="form-select", select=True)
        self.assertEqual(attrs["class"], "form-select readonly-field")
        self.assertIs(attrs["disabled"], True)
        self.assertEqual(attrs["tabindex"], "-1")
        self.assertNotIn("readonly", attrs)

    def test_lock_field_text_input(self):
        from django import forms

        from core.forms import lock_field

        field = forms.CharField(widget=forms.TextInput(attrs={"class": "form-control", "style": "color:red"}))
        lock_field(field, id="x1")
        self.assertEqual(field.widget.attrs["class"], "form-control readonly-field")
        self.assertIs(field.widget.attrs["readonly"], True)
        self.assertEqual(field.widget.attrs["tabindex"], "-1")
        self.assertEqual(field.widget.attrs["id"], "x1")
        self.assertNotIn("style", field.widget.attrs)
        self.assertFalse(field.disabled)

        lock_field(field)  # повторный вызов не дублирует класс
        self.assertEqual(field.widget.attrs["class"], "form-control readonly-field")

    def test_lock_field_disabled_and_select(self):
        from django import forms

        from core.forms import lock_field

        field = forms.ChoiceField(choices=[("a", "A")], widget=forms.Select(attrs={"class": "form-select"}))
        lock_field(field, disabled=True, use_disabled_attr=True)
        self.assertTrue(field.disabled)
        self.assertEqual(field.widget.attrs["class"], "form-select readonly-field")
        self.assertIs(field.widget.attrs["disabled"], True)
        self.assertNotIn("readonly", field.widget.attrs)

    def test_no_inline_locked_field_style_in_project_sources(self):
        """Вид заблокированного поля задаётся только классом readonly-field."""
        root = Path(__file__).resolve().parent.parent
        offenders = []
        for pattern in ("*/templates/**/*.html", "*/forms.py", "core/static/core/js/*.js"):
            for path in root.glob(pattern):
                if "node_modules" in path.parts or "staticfiles" in path.parts:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
                # Любой инлайн «серый фон + приглушённый текст» — признак ручной блокировки поля.
                if re.search(r"background-color:\s*#(?:f8f9fa|e9ecef);\s*color:\s*#6c757d", text):
                    offenders.append(str(path.relative_to(root)))
        self.assertEqual(offenders, [])

    def test_site_css_defines_single_locked_field_source(self):
        css = Path(__file__).resolve().parent.joinpath("static", "core", "css", "site.css").read_text(encoding="utf-8")
        self.assertIn("--locked-field-bg: #f8f9fa;", css)
        self.assertIn("--locked-field-fg: #6c757d;", css)
        self.assertIn("background-color: var(--locked-field-bg) !important;", css)
        self.assertNotIn("#proposals-pane .readonly-field {", css)
        self.assertNotIn("#proposals-modal .readonly-field {", css)
        self.assertNotIn("#policy-modal .policy-product-select-display.readonly-field {", css)


class ModalBackdropGuardTests(SimpleTestCase):
    """core/js/modal-backdrop-guard.js: затемнение открывающейся модалки не удаляется."""

    root = Path(__file__).resolve().parent.parent

    def test_base_template_loads_guard_right_after_bootstrap(self):
        base_html = self.root.joinpath("core", "templates", "core", "base.html").read_text(encoding="utf-8")
        bootstrap_pos = base_html.index("bootstrap.bundle.min.js")
        guard_pos = base_html.index("core/js/modal-backdrop-guard.js")
        cleanup_pos = base_html.index("function cleanupDanglingModalState()")
        self.assertLess(bootstrap_pos, guard_pos)
        self.assertLess(guard_pos, cleanup_pos)
        self.assertNotIn("defer src=\"{% static 'core/js/modal-backdrop-guard.js'", base_html)
        cleanup_body = base_html[cleanup_pos:base_html.index("function scheduleModalCleanup()")]
        self.assertIn("window.ModalBackdropGuard.isAnyModalActive()", cleanup_body)

    def test_guard_tracks_opening_modals_and_restores_backdrop(self):
        js = self.root.joinpath("core", "static", "core", "js", "modal-backdrop-guard.js").read_text(encoding="utf-8")
        self.assertIn("document.addEventListener('show.bs.modal'", js)
        self.assertIn("instance._isShown === true", js)
        self.assertIn("new MutationObserver(", js)
        self.assertIn("window.ModalBackdropGuard = {", js)

    def test_backdrop_cleanups_consult_guard(self):
        """Любой код, удаляющий .modal-backdrop, обязан спрашивать ModalBackdropGuard."""
        offenders = []
        for pattern in ("templates/**/*.html", "*/templates/**/*.html", "core/static/core/js/*.js"):
            for path in self.root.glob(pattern):
                if "node_modules" in path.parts or "staticfiles" in path.parts:
                    continue
                if path.name == "modal-backdrop-guard.js":
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
                if re.search(r"querySelectorAll\(['\"]\.modal-backdrop['\"]\)\.forEach", text) and "ModalBackdropGuard" not in text:
                    offenders.append(str(path.relative_to(self.root)))
        self.assertEqual(offenders, [])
