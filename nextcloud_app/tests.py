from unittest.mock import Mock, call, patch

from checklists_app.models import ProjectWorkspace
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase, override_settings

from core.models import CloudStorageSettings
from group_app.models import GroupMember
from policy_app.models import Product
from proposals_app.models import ProposalRegistration
from projects_app.models import ProjectRegistration, RegistrationWorkspaceFolder
from users_app.models import Employee
from yandexdisk_app.workspace import _build_project_folder_name, WorkspaceResult
from nextcloud_app.api import NextcloudApiError
from nextcloud_app.api import NextcloudApiClient
from nextcloud_app.models import NextcloudUserLink
from nextcloud_app.provisioning import ensure_nextcloud_account
from nextcloud_app.workspace import create_basic_project_workspace_stream, create_proposal_workspace

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


@override_settings(
    NEXTCLOUD_PROVISIONING_BASE_URL="https://cloud.example.com",
    NEXTCLOUD_PROVISIONING_USERNAME="cloud-admin",
    NEXTCLOUD_PROVISIONING_TOKEN="token",
    NEXTCLOUD_OIDC_PROVIDER_ID=1,
)
class NextcloudApiClientFileOpsTests(TestCase):
    def test_list_resources_parses_webdav_depth_response(self):
        session = Mock()
        session.request.return_value = Mock(
            status_code=207,
            content=(
                b'<?xml version="1.0"?>'
                b'<d:multistatus xmlns:d="DAV:">'
                b'  <d:response>'
                b'    <d:href>/remote.php/dav/files/cloud-admin/Corporate%20Root/2026/</d:href>'
                b'    <d:propstat><d:prop><d:displayname>2026</d:displayname><d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat>'
                b'  </d:response>'
                b'  <d:response>'
                b'    <d:href>/remote.php/dav/files/cloud-admin/Corporate%20Root/2026/000%20Ivanov%20II/</d:href>'
                b'    <d:propstat><d:prop><d:displayname>000 Ivanov II</d:displayname><d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat>'
                b'  </d:response>'
                b'  <d:response>'
                b'    <d:href>/remote.php/dav/files/cloud-admin/Corporate%20Root/2026/contract.docx</d:href>'
                b'    <d:propstat><d:prop><d:displayname>contract.docx</d:displayname><d:resourcetype/>'
                b'    <d:getcontentlength>42</d:getcontentlength><d:getlastmodified>Mon, 30 Mar 2026 10:00:00 GMT</d:getlastmodified>'
                b'    </d:prop></d:propstat>'
                b'  </d:response>'
                b'</d:multistatus>'
            ),
            text="",
        )
        client = NextcloudApiClient(session=session)

        items = client.list_resources("cloud-admin", "/Corporate Root/2026", limit=100)

        self.assertEqual(
            items,
            [
                {
                    "name": "000 Ivanov II",
                    "path": "/Corporate Root/2026/000 Ivanov II",
                    "type": "dir",
                    "size": None,
                    "modified": None,
                },
                {
                    "name": "contract.docx",
                    "path": "/Corporate Root/2026/contract.docx",
                    "type": "file",
                    "size": 42,
                    "modified": "Mon, 30 Mar 2026 10:00:00 GMT",
                },
            ],
        )

    def test_ensure_public_link_share_returns_created_url(self):
        session = Mock()
        session.request.side_effect = [
            Mock(
                status_code=200,
                content=(b'{"ocs":{"meta":{"status":"ok","statuscode":100},"data":[]}}'),
                json=lambda: {
                    "ocs": {
                        "meta": {"status": "ok", "statuscode": 100},
                        "data": [],
                    }
                },
                text="",
                headers={},
            ),
            Mock(
                status_code=200,
                content=(
                    b'{"ocs":{"meta":{"status":"ok","statuscode":100},"data":{"id":"15","url":"https://cloud.example.com/s/public-doc"}}}'
                ),
                json=lambda: {
                    "ocs": {
                        "meta": {"status": "ok", "statuscode": 100},
                        "data": {"id": "15", "url": "https://cloud.example.com/s/public-doc"},
                    }
                },
                text="",
                headers={},
            ),
        ]
        client = NextcloudApiClient(session=session)

        public_url = client.ensure_public_link_share("cloud-admin", "/Corporate Root/2026/contract.docx")

        self.assertEqual(public_url, "https://cloud.example.com/s/public-doc")
        self.assertEqual(session.request.call_count, 2)

    @patch("nextcloud_app.api.time.sleep")
    def test_ensure_public_link_share_retries_after_429(self, mocked_sleep):
        session = Mock()
        empty_list = Mock(
            status_code=200,
            content=(b'{"ocs":{"meta":{"status":"ok","statuscode":100},"data":[]}}'),
            json=lambda: {
                "ocs": {
                    "meta": {"status": "ok", "statuscode": 100},
                    "data": [],
                }
            },
            text="",
            headers={},
        )
        too_many = Mock(
            status_code=429,
            content=b'{"ocs":{"meta":{"status":"failure","statuscode":429,"message":"Too many requests"}}}',
            json=lambda: {
                "ocs": {
                    "meta": {"status": "failure", "statuscode": 429, "message": "Too many requests"},
                    "data": {},
                }
            },
            text="Too many requests",
            headers={"Retry-After": "0"},
        )
        success = Mock(
            status_code=200,
            content=(
                b'{"ocs":{"meta":{"status":"ok","statuscode":100},"data":{"id":"16","url":"https://cloud.example.com/s/retried-doc"}}}'
            ),
            json=lambda: {
                "ocs": {
                    "meta": {"status": "ok", "statuscode": 100},
                    "data": {"id": "16", "url": "https://cloud.example.com/s/retried-doc"},
                }
            },
            text="",
            headers={},
        )
        session.request.side_effect = [empty_list, too_many, success]
        client = NextcloudApiClient(session=session)
        client.SHARE_CREATE_INTERVAL_SECONDS = 0

        public_url = client.ensure_public_link_share("cloud-admin", "/Corporate Root/2026/retry.docx")

        self.assertEqual(public_url, "https://cloud.example.com/s/retried-doc")
        self.assertEqual(session.request.call_count, 3)
        self.assertGreaterEqual(mocked_sleep.call_count, 1)

    def test_list_public_link_shares_builds_cache(self):
        session = Mock()
        session.request.return_value = Mock(
            status_code=200,
            content=(
                b'{"ocs":{"meta":{"status":"ok","statuscode":100},"data":['
                b'{"id":"15","path":"/Corporate Root/2026/contract.docx","share_type":3,"permissions":1,"url":"https://cloud.example.com/s/public-doc"},'
                b'{"id":"16","path":"/Corporate Root/2026/private","share_type":0,"permissions":15}'
                b']}}'
            ),
            json=lambda: {
                "ocs": {
                    "meta": {"status": "ok", "statuscode": 100},
                    "data": [
                        {
                            "id": "15",
                            "path": "/Corporate Root/2026/contract.docx",
                            "share_type": 3,
                            "permissions": 1,
                            "url": "https://cloud.example.com/s/public-doc",
                        },
                        {
                            "id": "16",
                            "path": "/Corporate Root/2026/private",
                            "share_type": 0,
                            "permissions": 15,
                        },
                    ],
                }
            },
            text="",
            headers={},
        )
        client = NextcloudApiClient(session=session)

        shares = client.list_public_link_shares("cloud-admin")

        self.assertEqual(list(shares.keys()), ["/Corporate Root/2026/contract.docx"])
        self.assertEqual(shares["/Corporate Root/2026/contract.docx"].url, "https://cloud.example.com/s/public-doc")

    @patch("nextcloud_app.api.time.sleep")
    def test_dav_request_retries_on_429(self, mocked_sleep):
        session = Mock()
        too_many = Mock(status_code=429, text="Too Many Requests", headers={"Retry-After": "0"}, content=b"")
        ok = Mock(status_code=201, text="Created", headers={}, content=b"")
        session.request.side_effect = [too_many, ok]
        client = NextcloudApiClient(session=session)

        response = client._dav_request("MKCOL", "https://cloud.example.com/remote.php/dav/files/admin/test")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(session.request.call_count, 2)
        self.assertGreaterEqual(mocked_sleep.call_count, 1)

    @patch("nextcloud_app.api.time.sleep")
    def test_dav_request_retries_on_network_error(self, mocked_sleep):
        import requests as req
        session = Mock()
        session.request.side_effect = [
            req.ConnectionError("connection reset"),
            Mock(status_code=201, text="Created", headers={}, content=b""),
        ]
        client = NextcloudApiClient(session=session)

        response = client._dav_request("MKCOL", "https://cloud.example.com/remote.php/dav/files/admin/test")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(session.request.call_count, 2)


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
        self.assertIn("bi bi-cloud", content)
        self.assertIn("Облако", content)
        self.assertLess(content.find("Обучение"), content.find("Облако"))

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


@override_settings(
    NEXTCLOUD_PROVISIONING_BASE_URL="https://cloud.example.com",
    NEXTCLOUD_PROVISIONING_USERNAME="cloud-admin",
    NEXTCLOUD_PROVISIONING_TOKEN="token",
    NEXTCLOUD_OIDC_PROVIDER_ID=1,
)
class NextcloudWorkspaceTests(TestCase):
    def setUp(self):
        settings_obj = CloudStorageSettings.get_solo()
        settings_obj.primary_storage = CloudStorageSettings.PrimaryStorage.NEXTCLOUD
        settings_obj.nextcloud_root_path = "/Corporate Root"
        settings_obj.save()

        self.creator = User.objects.create_user(
            username="creator@example.com",
            email="creator@example.com",
            password="Secret123!",
            is_staff=True,
            is_active=True,
        )
        self.manager = User.objects.create_user(
            username="manager@example.com",
            email="manager@example.com",
            password="Secret123!",
            first_name="Иван",
            last_name="Иванов",
            is_staff=True,
            is_active=True,
        )
        Employee.objects.create(user=self.manager, patronymic="Иванович", role="Руководитель проектов")
        NextcloudUserLink.objects.create(
            user=self.manager,
            nextcloud_user_id=f"ncstaff-{self.manager.pk}",
            nextcloud_username=f"ncstaff-{self.manager.pk}",
            nextcloud_email="manager@example.com",
        )
        RegistrationWorkspaceFolder.objects.bulk_create(
            [
                RegistrationWorkspaceFolder(user=self.creator, level=1, name="01 Документы", position=0),
                RegistrationWorkspaceFolder(user=self.creator, level=2, name="02 Письма", position=1),
            ]
        )
        self.product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            service_type="service",
        )
        self.project = ProjectRegistration.objects.create(
            number=6001,
            type=self.product,
            name="Проект Nextcloud",
            year=2026,
            project_manager="Иванов Иван Иванович",
        )

    def test_create_basic_project_workspace_creates_folders_and_grants_editor_access(self):
        project_folder = _build_project_folder_name(self.project)
        project_path = f"/Corporate Root/2026/{project_folder}"
        client = Mock()
        client.is_configured = True
        client.username = "cloud-admin"
        client.ensure_folder.side_effect = lambda _owner, path: "/" + "/".join(
            part for part in str(path).replace("\\", "/").split("/") if part
        )
        client.ensure_user_share.return_value = Mock()
        client.build_files_url.return_value = f"https://cloud.example.com/apps/files/files?dir={project_path}"

        items = list(create_basic_project_workspace_stream(self.creator, self.project, client=client))

        self.assertIsInstance(items[-1], WorkspaceResult)
        self.assertTrue(items[-1].ok)
        self.assertIn("Nextcloud", items[-1].message)
        self.assertEqual(
            client.ensure_folder.call_args_list,
            [
                call("cloud-admin", "/Corporate Root/2026"),
                call("cloud-admin", project_path),
                call("cloud-admin", f"{project_path}/01 Документы"),
                call("cloud-admin", f"{project_path}/01 Документы/02 Письма"),
            ],
        )
        client.ensure_user_share.assert_called_once_with(
            "cloud-admin",
            project_path,
            f"ncstaff-{self.manager.pk}",
            permissions=15,
        )
        workspace = ProjectWorkspace.objects.get(project=self.project)
        self.assertEqual(workspace.disk_path, project_path)
        self.assertEqual(workspace.public_url, f"https://cloud.example.com/apps/files/files?dir={project_path}")

    def test_create_basic_project_workspace_accepts_slash_as_root_path(self):
        settings_obj = CloudStorageSettings.get_solo()
        settings_obj.nextcloud_root_path = "/"
        settings_obj.save()

        project_folder = _build_project_folder_name(self.project)
        project_path = f"/2026/{project_folder}"
        client = Mock()
        client.is_configured = True
        client.username = "cloud-admin"
        client.ensure_folder.side_effect = lambda _owner, path: "/" + "/".join(
            part for part in str(path).replace("\\", "/").split("/") if part
        )
        client.enable_user.return_value = None
        client.set_user_email.return_value = None
        client.set_user_display_name.return_value = None
        client.ensure_user_share.return_value = Mock()
        client.build_files_url.return_value = f"https://cloud.example.com/apps/files/files?dir={project_path}"

        items = list(create_basic_project_workspace_stream(self.creator, self.project, client=client))

        self.assertTrue(items[-1].ok)
        self.assertEqual(
            client.ensure_folder.call_args_list,
            [
                call("cloud-admin", "/2026"),
                call("cloud-admin", project_path),
                call("cloud-admin", f"{project_path}/01 Документы"),
                call("cloud-admin", f"{project_path}/01 Документы/02 Письма"),
            ],
        )

    def test_create_basic_project_workspace_returns_workspace_error_when_manager_sync_api_fails(self):
        client = Mock()
        client.is_configured = True
        client.username = "cloud-admin"
        client.enable_user.side_effect = NextcloudApiError("temporary nextcloud failure")

        items = list(create_basic_project_workspace_stream(self.creator, self.project, client=client))

        self.assertIsInstance(items[-1], WorkspaceResult)
        self.assertFalse(items[-1].ok)
        self.assertIn("temporary nextcloud failure", items[-1].message)

    @patch("nextcloud_app.workspace.time.sleep")
    def test_create_basic_project_workspace_retries_folder_creation_with_heartbeats(self, mocked_sleep):
        client = Mock()
        client.is_configured = True
        client.username = "cloud-admin"
        client.ensure_folder.side_effect = [
            NextcloudApiError("429 rate limit"),
            "/Corporate Root/2026",
            lambda _o, p: "/" + "/".join(part for part in str(p).split("/") if part),
        ]
        # After retry success, remaining calls should succeed
        def _folder_ok(_owner, path):
            return "/" + "/".join(part for part in str(path).replace("\\", "/").split("/") if part)
        client.ensure_folder.side_effect = [
            NextcloudApiError("429 rate limit"),
            "/Corporate Root/2026",
            "/Corporate Root/2026/Проект 6001 DD Проект Nextcloud",
            "/Corporate Root/2026/Проект 6001 DD Проект Nextcloud/01 Документы",
            "/Corporate Root/2026/Проект 6001 DD Проект Nextcloud/01 Документы/02 Письма",
        ]
        client.ensure_user_share.return_value = Mock()
        client.build_files_url.return_value = "https://cloud.example.com/apps/files/files?dir=/test"

        items = list(create_basic_project_workspace_stream(self.creator, self.project, client=client))

        self.assertIsInstance(items[-1], WorkspaceResult)
        self.assertTrue(items[-1].ok)
        heartbeats = [i for i in items if isinstance(i, dict) and "current" in i and "total" in i]
        self.assertTrue(len(heartbeats) > 0)
        self.assertTrue(mocked_sleep.call_count >= 1)


@override_settings(
    NEXTCLOUD_PROVISIONING_BASE_URL="https://cloud.example.com",
    NEXTCLOUD_PROVISIONING_USERNAME="cloud-admin",
    NEXTCLOUD_PROVISIONING_TOKEN="token",
    NEXTCLOUD_OIDC_PROVIDER_ID=1,
)
class NextcloudProposalWorkspaceTests(TestCase):
    def setUp(self):
        settings_obj = CloudStorageSettings.get_solo()
        settings_obj.primary_storage = CloudStorageSettings.PrimaryStorage.NEXTCLOUD
        settings_obj.nextcloud_root_path = "/Corporate Root"
        settings_obj.save()

        self.author = User.objects.create_user(
            username="proposal-author@example.com",
            email="proposal-author@example.com",
            password="Secret123!",
            is_staff=True,
            is_active=True,
        )
        self.group_member = GroupMember.objects.create(
            short_name="IMC Montan",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
            position=1,
        )
        self.product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            service_type="service",
        )
        self.proposal = ProposalRegistration.objects.create(
            number=3333,
            group_member=self.group_member,
            type=self.product,
            name="Сделка / Восток",
            year=2026,
        )

    @patch("nextcloud_app.workspace.ensure_nextcloud_account")
    def test_create_proposal_workspace_creates_tkp_tree_and_grants_editor_access(self, mocked_ensure_account):
        mocked_ensure_account.return_value = Mock(nextcloud_user_id=f"ncstaff-{self.author.pk}")
        client = Mock()
        client.is_configured = True
        client.username = "cloud-admin"
        client.ensure_folder.side_effect = lambda _owner, path: "/" + "/".join(
            part for part in str(path).replace("\\", "/").split("/") if part
        )
        client.ensure_user_share.return_value = Mock()

        folder_name = f"{self.proposal.short_uid} {self.product.short_name} Сделка _ Восток"
        workspace_path = create_proposal_workspace(self.author, self.proposal, client=client)

        self.assertEqual(workspace_path, f"/Corporate Root/ТКП/2026/{folder_name}")
        self.assertEqual(
            client.ensure_folder.call_args_list,
            [
                call("cloud-admin", "/Corporate Root/ТКП"),
                call("cloud-admin", "/Corporate Root/ТКП/2026"),
                call("cloud-admin", f"/Corporate Root/ТКП/2026/{folder_name}"),
            ],
        )
        client.ensure_user_share.assert_called_once_with(
            "cloud-admin",
            f"/Corporate Root/ТКП/2026/{folder_name}",
            f"ncstaff-{self.author.pk}",
            permissions=15,
        )

    def test_create_proposal_workspace_requires_year(self):
        self.proposal.year = None

        client = Mock()
        client.is_configured = True
        client.username = "cloud-admin"

        with self.assertRaises(NextcloudApiError) as ctx:
            create_proposal_workspace(self.author, self.proposal, client=client)

        self.assertIn("поле «Год»", str(ctx.exception))
        client.ensure_folder.assert_not_called()


@override_settings(
    NEXTCLOUD_PROVISIONING_BASE_URL="https://cloud.example.com",
    NEXTCLOUD_PROVISIONING_USERNAME="cloud-admin",
    NEXTCLOUD_PROVISIONING_TOKEN="token",
    NEXTCLOUD_OIDC_PROVIDER_ID=1,
)
class HeartbeatRetryTests(TestCase):
    @patch("nextcloud_app.workspace.time.sleep")
    def test_ensure_folder_with_heartbeat_retries_and_yields_heartbeats(self, mocked_sleep):
        from nextcloud_app.workspace import _ensure_folder_with_heartbeat

        client = Mock()
        client.ensure_folder.side_effect = [
            NextcloudApiError("429 rate limit"),
            NextcloudApiError("429 rate limit"),
            "/test/folder",
        ]

        gen = _ensure_folder_with_heartbeat(client, "admin", "/test/folder", 5, 20)
        events = []
        result = None
        try:
            while True:
                events.append(next(gen))
        except StopIteration as e:
            result = e.value

        self.assertEqual(result, "/test/folder")
        self.assertEqual(client.ensure_folder.call_count, 3)
        self.assertTrue(len(events) > 0)
        for ev in events:
            self.assertEqual(ev["current"], 5)
            self.assertEqual(ev["total"], 20)

    @patch("nextcloud_app.workspace.time.sleep")
    def test_ensure_link_with_heartbeat_retries_and_yields_heartbeats(self, mocked_sleep):
        from nextcloud_app.workspace import _ensure_link_with_heartbeat

        client = Mock()
        client.ensure_public_link_share.side_effect = [
            NextcloudApiError("429 rate limit"),
            "https://cloud.example.com/s/abc123",
        ]

        gen = _ensure_link_with_heartbeat(client, "admin", "/test/folder", 10, 50)
        events = []
        result = None
        try:
            while True:
                events.append(next(gen))
        except StopIteration as e:
            result = e.value

        self.assertEqual(result, "https://cloud.example.com/s/abc123")
        client.ensure_public_link_share.assert_any_call("admin", "/test/folder", _quick=True)
        self.assertTrue(len(events) > 0)
        for ev in events:
            self.assertEqual(ev["current"], 10)
            self.assertEqual(ev["total"], 50)

    @patch("nextcloud_app.workspace.time.sleep")
    def test_ensure_folder_with_heartbeat_raises_after_max_retries(self, mocked_sleep):
        from nextcloud_app.workspace import _ensure_folder_with_heartbeat, _FOLDER_MAX_RETRIES

        client = Mock()
        client.ensure_folder.side_effect = NextcloudApiError("permission denied")

        gen = _ensure_folder_with_heartbeat(client, "admin", "/bad/path", 1, 10)
        with self.assertRaises(NextcloudApiError):
            while True:
                next(gen)

        self.assertEqual(client.ensure_folder.call_count, _FOLDER_MAX_RETRIES)

    @patch("nextcloud_app.workspace.time.sleep")
    def test_ensure_link_with_heartbeat_raises_after_max_retries(self, mocked_sleep):
        from nextcloud_app.workspace import _ensure_link_with_heartbeat, _LINK_MAX_RETRIES

        client = Mock()
        client.ensure_public_link_share.side_effect = NextcloudApiError("persistent 429")

        gen = _ensure_link_with_heartbeat(client, "admin", "/test/path", 1, 10)
        with self.assertRaises(NextcloudApiError):
            while True:
                next(gen)

        self.assertEqual(client.ensure_public_link_share.call_count, _LINK_MAX_RETRIES)

    def test_quick_mode_uses_single_attempt(self):
        session = Mock()
        empty_list = Mock(
            status_code=200,
            content=b'{"ocs":{"meta":{"status":"ok","statuscode":100},"data":[]}}',
            json=lambda: {"ocs": {"meta": {"status": "ok", "statuscode": 100}, "data": []}},
            text="",
            headers={},
        )
        too_many = Mock(
            status_code=429,
            text="Too many requests",
            headers={"Retry-After": "0"},
        )
        session.request.side_effect = [empty_list, too_many]
        client = NextcloudApiClient(session=session)
        client.SHARE_CREATE_INTERVAL_SECONDS = 0

        with self.assertRaises(NextcloudApiError) as ctx:
            client.ensure_public_link_share("cloud-admin", "/test", _quick=True)

        self.assertIn("429", str(ctx.exception))
        self.assertEqual(session.request.call_count, 2)
