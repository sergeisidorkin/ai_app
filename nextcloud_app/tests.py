from io import StringIO
from unittest.mock import Mock, call, patch

from checklists_app.models import ProjectWorkspace, SourceDataWorkspace
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase, override_settings

from contacts_app.models import PersonRecord
from core.models import CloudStorageSettings
from contracts_app.models import ContractProjectRegistration
from experts_app.models import ExpertProfile
from group_app.models import GroupMember, OrgUnit
from policy_app.models import DEPARTMENT_HEAD_GROUP, Product
from proposals_app.models import ProposalRegistration
from projects_app.models import Performer, ProjectRegistration, RegistrationWorkspaceFolder
from users_app.models import Employee
from yandexdisk_app.workspace import _build_project_folder_name, WorkspaceResult
from nextcloud_app.api import NextcloudApiError
from nextcloud_app.api import NextcloudApiClient
from nextcloud_app.api import NextcloudShare
from nextcloud_app.models import NextcloudUserLink
from nextcloud_app.provisioning import ensure_nextcloud_account
from nextcloud_app.workspace import (
    create_basic_project_workspace_stream,
    create_proposal_workspace,
    grant_project_workspace_editor_access_for_performers,
    revoke_contract_folder_access_for_user,
)

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
class NextcloudContractSharePruneCommandTests(TestCase):
    def test_prune_nextcloud_contract_shares_reports_stale_direct_contract_share(self):
        user = User.objects.create_user(
            username="smirnova@example.com",
            email="smirnova@example.com",
            password="Secret123!",
            is_staff=True,
            is_active=True,
        )
        employee = Employee.objects.create(user=user)
        link = NextcloudUserLink.objects.create(
            user=user,
            nextcloud_user_id=f"ncstaff-{user.pk}",
            nextcloud_username=f"ncstaff-{user.pk}",
            nextcloud_email=user.email,
        )
        active_folder = (
            "/Corporate Root/02 Договоры/2026/Проект/Договор/02 Исполнители/"
            "6001010RU 001 Смирнова ЭЮ"
        )
        stale_folder = (
            "/Corporate Root/02 Договоры/2026/Проект/Договор/02 Исполнители/"
            "6001010RU 012 Смирнова ЭЮ"
        )
        project = ProjectRegistration.objects.create(number=6101, name="Проект", year=2026)
        Performer.objects.create(
            registration=project,
            employee=employee,
            executor="Смирнова Элеонора Юрьевна",
            contract_project_disk_folder=active_folder,
        )

        out = StringIO()
        with patch("nextcloud_app.api.NextcloudApiClient.list_user_shares") as mocked_list_shares:
            mocked_list_shares.return_value = {
                active_folder: NextcloudShare(
                    share_id="91",
                    path=active_folder,
                    share_with=link.nextcloud_user_id,
                    permissions=1,
                    target_path="/6001010RU 001 Смирнова ЭЮ",
                ),
                stale_folder: NextcloudShare(
                    share_id="92",
                    path=stale_folder,
                    share_with=link.nextcloud_user_id,
                    permissions=1,
                    target_path="/6001010RU 012 Смирнова ЭЮ",
                ),
            }

            call_command("prune_nextcloud_contract_shares", "--email", user.email, stdout=out)

        output = out.getvalue()
        self.assertIn("1 stale contract share(s)", output)
        self.assertIn("STALE 92", output)
        self.assertIn(stale_folder, output)
        self.assertNotIn("STALE 91", output)


class NextcloudContractShareSignalTests(TestCase):
    @patch("nextcloud_app.signals.revoke_contract_folder_access_for_user")
    def test_deleting_performer_schedules_contract_folder_share_revoke(self, mocked_revoke):
        user = User.objects.create_user(
            username="deleted-contract-share@example.com",
            email="deleted-contract-share@example.com",
            password="Secret123!",
            is_staff=True,
            is_active=True,
        )
        employee = Employee.objects.create(user=user)
        project = ProjectRegistration.objects.create(number=6201, name="Проект", year=2026)
        folder = (
            "/Corporate Root/02 Договоры/2026/Проект/Договор/02 Исполнители/"
            "6001010RU 012 Смирнова ЭЮ"
        )
        performer = Performer.objects.create(
            registration=project,
            employee=employee,
            executor="Смирнова Элеонора Юрьевна",
            contract_project_disk_folder=folder,
        )

        with self.captureOnCommitCallbacks(execute=True):
            performer.delete()

        mocked_revoke.assert_called_once_with(user.pk, folder)


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
                    "file_id": None,
                },
                {
                    "name": "contract.docx",
                    "path": "/Corporate Root/2026/contract.docx",
                    "type": "file",
                    "size": 42,
                    "modified": "Mon, 30 Mar 2026 10:00:00 GMT",
                    "file_id": None,
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

    def test_revoke_user_share_deletes_existing_share(self):
        session = Mock()
        session.request.side_effect = [
            Mock(
                status_code=200,
                content=(
                    b'{"ocs":{"meta":{"status":"ok","statuscode":100},"data":['
                    b'{"id":"42","path":"/Corporate Root/02 Contracts/000 Ivanov",'
                    b'"share_type":0,"share_with":"ncstaff-1","permissions":1}'
                    b']}}'
                ),
                json=lambda: {
                    "ocs": {
                        "meta": {"status": "ok", "statuscode": 100},
                        "data": [
                            {
                                "id": "42",
                                "path": "/Corporate Root/02 Contracts/000 Ivanov",
                                "share_type": 0,
                                "share_with": "ncstaff-1",
                                "permissions": 1,
                            }
                        ],
                    }
                },
                text="",
                headers={},
            ),
            Mock(
                status_code=200,
                content=b'{"ocs":{"meta":{"status":"ok","statuscode":100},"data":[]}}',
                json=lambda: {"ocs": {"meta": {"status": "ok", "statuscode": 100}, "data": []}},
                text="",
                headers={},
            ),
        ]
        client = NextcloudApiClient(session=session)

        revoked = client.revoke_user_share(
            "cloud-admin",
            "/Corporate Root/02 Contracts/000 Ivanov",
            "ncstaff-1",
        )

        self.assertTrue(revoked)
        self.assertEqual(session.request.call_args_list[1].args[0], "DELETE")
        self.assertIn("/ocs/v2.php/apps/files_sharing/api/v1/shares/42", session.request.call_args_list[1].args[1])

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
        self.manager_person = PersonRecord.objects.create(
            last_name="Иванов",
            first_name="Иван",
            middle_name="Иванович",
            position=1,
        )
        self.manager_employee = Employee.objects.create(
            user=self.manager,
            person_record=self.manager_person,
            patronymic="Иванович",
            role="Руководитель проектов",
        )
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
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
        )
        self.project = ProjectRegistration.objects.create(
            number=6001,
            type=self.product,
            name="Проект Nextcloud",
            year=2026,
            project_manager="Иванов Иван Иванович",
            project_manager_prs_id=self.manager_person.formatted_id,
        )

    def _create_direction_head(self, direction_name="Горное дело"):
        company = GroupMember.objects.create(
            short_name=f"Компания {direction_name}",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
        )
        direction = OrgUnit.objects.create(
            company=company,
            department_name=direction_name,
            unit_type="expertise",
        )
        head_user = User.objects.create_user(
            username=f"head-{direction.pk}@example.com",
            email=f"head-{direction.pk}@example.com",
            password="Secret123!",
            first_name="Анна",
            last_name="Руководитель",
            is_staff=True,
            is_active=True,
        )
        head_employee = Employee.objects.create(
            user=head_user,
            department=direction,
            role=DEPARTMENT_HEAD_GROUP,
        )
        NextcloudUserLink.objects.create(
            user=head_user,
            nextcloud_user_id=f"ncstaff-{head_user.pk}",
            nextcloud_username=f"ncstaff-{head_user.pk}",
            nextcloud_email=head_user.email,
        )
        return direction, head_user, head_employee

    def test_create_basic_project_workspace_creates_folders_and_grants_editor_access(self):
        project_folder = _build_project_folder_name(self.project)
        project_path = f"/Corporate Root/03 Проекты/2026/{project_folder}"
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
                call("cloud-admin", "/Corporate Root/03 Проекты"),
                call("cloud-admin", "/Corporate Root/03 Проекты/2026"),
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

    def test_create_basic_project_workspace_grants_access_to_confirmed_performer(self):
        direction, direction_head_user, _direction_head = self._create_direction_head()
        performer_user = User.objects.create_user(
            username="performer@example.com",
            email="performer@example.com",
            password="Secret123!",
            first_name="Петр",
            last_name="Петров",
            is_staff=True,
            is_active=True,
        )
        performer_employee = Employee.objects.create(user=performer_user, patronymic="Петрович")
        Performer.objects.create(
            registration=self.project,
            employee=performer_employee,
            executor="Петров Петр Петрович",
            participation_response=Performer.ParticipationResponse.CONFIRMED,
        )
        ExpertProfile.objects.create(
            employee=performer_employee,
            expertise_direction=direction,
        )
        NextcloudUserLink.objects.create(
            user=performer_user,
            nextcloud_user_id=f"ncstaff-{performer_user.pk}",
            nextcloud_username=f"ncstaff-{performer_user.pk}",
            nextcloud_email="performer@example.com",
        )
        project_folder = _build_project_folder_name(self.project)
        project_path = f"/Corporate Root/03 Проекты/2026/{project_folder}"
        client = Mock()
        client.is_configured = True
        client.username = "cloud-admin"
        client.ensure_folder.side_effect = lambda _owner, path: "/" + "/".join(
            part for part in str(path).replace("\\", "/").split("/") if part
        )
        client.ensure_user_share.return_value = Mock()
        client.build_files_url.return_value = f"https://cloud.example.com/apps/files/files?dir={project_path}"

        items = list(create_basic_project_workspace_stream(self.creator, self.project, client=client))

        self.assertTrue(items[-1].ok)
        client.ensure_user_share.assert_has_calls(
            [
                call("cloud-admin", project_path, f"ncstaff-{self.manager.pk}", permissions=15),
                call("cloud-admin", project_path, f"ncstaff-{performer_user.pk}", permissions=15),
                call("cloud-admin", project_path, f"ncstaff-{direction_head_user.pk}", permissions=15),
            ]
        )

    def test_grant_project_workspace_editor_access_for_confirmed_performer(self):
        performer_user = User.objects.create_user(
            username="workspace-performer@example.com",
            email="workspace-performer@example.com",
            password="Secret123!",
            first_name="Сергей",
            last_name="Сергеев",
            is_staff=True,
            is_active=True,
        )
        performer_employee = Employee.objects.create(user=performer_user, patronymic="Сергеевич")
        performer = Performer.objects.create(
            registration=self.project,
            employee=performer_employee,
            executor="Сергеев Сергей Сергеевич",
            participation_response=Performer.ParticipationResponse.CONFIRMED,
        )
        NextcloudUserLink.objects.create(
            user=performer_user,
            nextcloud_user_id=f"ncstaff-{performer_user.pk}",
            nextcloud_username=f"ncstaff-{performer_user.pk}",
            nextcloud_email="workspace-performer@example.com",
        )
        ProjectWorkspace.objects.create(
            project=self.project,
            disk_path="/Corporate Root/03 Проекты/2026/Проект 6001 DD Проект Nextcloud",
            created_by=self.creator,
        )
        client = Mock()
        client.is_configured = True
        client.username = "cloud-admin"
        client.ensure_user_share.return_value = Mock()

        granted = grant_project_workspace_editor_access_for_performers([performer.pk], client=client)

        self.assertEqual(granted, 1)
        client.ensure_user_share.assert_called_once_with(
            "cloud-admin",
            "/Corporate Root/03 Проекты/2026/Проект 6001 DD Проект Nextcloud",
            f"ncstaff-{performer_user.pk}",
            permissions=15,
        )

    def test_grant_project_workspace_editor_access_for_confirmed_performer_and_direction_head(self):
        direction, direction_head_user, _direction_head = self._create_direction_head()
        performer_user = User.objects.create_user(
            username="workspace-direction-performer@example.com",
            email="workspace-direction-performer@example.com",
            password="Secret123!",
            first_name="Сергей",
            last_name="Сергеев",
            is_staff=True,
            is_active=True,
        )
        performer_employee = Employee.objects.create(user=performer_user, patronymic="Сергеевич")
        ExpertProfile.objects.create(
            employee=performer_employee,
            expertise_direction=direction,
        )
        performer = Performer.objects.create(
            registration=self.project,
            employee=performer_employee,
            executor="Сергеев Сергей Сергеевич",
            participation_response=Performer.ParticipationResponse.CONFIRMED,
        )
        NextcloudUserLink.objects.create(
            user=performer_user,
            nextcloud_user_id=f"ncstaff-{performer_user.pk}",
            nextcloud_username=f"ncstaff-{performer_user.pk}",
            nextcloud_email="workspace-direction-performer@example.com",
        )
        ProjectWorkspace.objects.create(
            project=self.project,
            disk_path="/Corporate Root/03 Проекты/2026/Проект 6001 DD Проект Nextcloud",
            created_by=self.creator,
        )
        client = Mock()
        client.is_configured = True
        client.username = "cloud-admin"
        client.ensure_user_share.return_value = Mock()

        granted = grant_project_workspace_editor_access_for_performers([performer.pk], client=client)

        self.assertEqual(granted, 2)
        client.ensure_user_share.assert_has_calls(
            [
                call(
                    "cloud-admin",
                    "/Corporate Root/03 Проекты/2026/Проект 6001 DD Проект Nextcloud",
                    f"ncstaff-{performer_user.pk}",
                    permissions=15,
                ),
                call(
                    "cloud-admin",
                    "/Corporate Root/03 Проекты/2026/Проект 6001 DD Проект Nextcloud",
                    f"ncstaff-{direction_head_user.pk}",
                    permissions=15,
                ),
            ]
        )

    def test_grant_project_workspace_editor_access_deduplicates_direction_head_for_project(self):
        direction, direction_head_user, _direction_head = self._create_direction_head()
        ProjectWorkspace.objects.create(
            project=self.project,
            disk_path="/Corporate Root/03 Проекты/2026/Проект 6001 DD Проект Nextcloud",
            created_by=self.creator,
        )
        performer_ids = []
        for index in range(2):
            performer_user = User.objects.create_user(
                username=f"workspace-direction-performer-{index}@example.com",
                email=f"workspace-direction-performer-{index}@example.com",
                password="Secret123!",
                is_staff=True,
                is_active=True,
            )
            performer_employee = Employee.objects.create(user=performer_user)
            ExpertProfile.objects.create(
                employee=performer_employee,
                expertise_direction=direction,
            )
            performer = Performer.objects.create(
                registration=self.project,
                employee=performer_employee,
                executor=performer_user.username,
                participation_response=Performer.ParticipationResponse.CONFIRMED,
            )
            performer_ids.append(performer.pk)
            NextcloudUserLink.objects.create(
                user=performer_user,
                nextcloud_user_id=f"ncstaff-{performer_user.pk}",
                nextcloud_username=f"ncstaff-{performer_user.pk}",
                nextcloud_email=performer_user.email,
            )
        client = Mock()
        client.is_configured = True
        client.username = "cloud-admin"
        client.ensure_user_share.return_value = Mock()

        granted = grant_project_workspace_editor_access_for_performers(performer_ids, client=client)

        self.assertEqual(granted, 3)
        head_share_calls = [
            share_call for share_call in client.ensure_user_share.call_args_list
            if share_call.args[2] == f"ncstaff-{direction_head_user.pk}"
        ]
        self.assertEqual(len(head_share_calls), 1)

    def test_grant_project_workspace_editor_access_skips_ineligible_nextcloud_users(self):
        ProjectWorkspace.objects.create(
            project=self.project,
            disk_path="/Corporate Root/03 Проекты/2026/Проект 6001 DD Проект Nextcloud",
            created_by=self.creator,
        )
        users = [
            User.objects.create_user(
                username="inactive-performer@example.com",
                email="inactive-performer@example.com",
                password="Secret123!",
                is_staff=True,
                is_active=False,
            ),
            User.objects.create_user(
                username="external-performer@example.com",
                email="external-performer@example.com",
                password="Secret123!",
                is_staff=False,
                is_active=True,
            ),
            User.objects.create_user(
                username="missing-email-performer",
                email="",
                password="Secret123!",
                is_staff=True,
                is_active=True,
            ),
        ]
        performer_ids = []
        for user in users:
            employee = Employee.objects.create(user=user)
            performer = Performer.objects.create(
                registration=self.project,
                employee=employee,
                executor=user.username,
                participation_response=Performer.ParticipationResponse.CONFIRMED,
            )
            performer_ids.append(performer.pk)
            NextcloudUserLink.objects.create(
                user=user,
                nextcloud_user_id=f"ncstaff-{user.pk}",
                nextcloud_username=f"ncstaff-{user.pk}",
                nextcloud_email=user.email,
            )
        client = Mock()
        client.is_configured = True
        client.username = "cloud-admin"

        granted = grant_project_workspace_editor_access_for_performers(performer_ids, client=client)

        self.assertEqual(granted, 0)
        client.enable_user.assert_not_called()
        client.ensure_user_share.assert_not_called()

    def test_revoke_contract_folder_access_for_user_removes_stale_share(self):
        performer_user = User.objects.create_user(
            username="stale-contract-share@example.com",
            email="stale-contract-share@example.com",
            password="Secret123!",
            is_staff=True,
            is_active=True,
        )
        performer_employee = Employee.objects.create(user=performer_user)
        folder = (
            "/Corporate Root/02 Договоры/2026/Проект/Договор/02 Исполнители/"
            "6001010RU 001 Сергеев СС"
        )
        NextcloudUserLink.objects.create(
            user=performer_user,
            nextcloud_user_id=f"ncstaff-{performer_user.pk}",
            nextcloud_username=f"ncstaff-{performer_user.pk}",
            nextcloud_email=performer_user.email,
        )
        performer = Performer.objects.create(
            registration=self.project,
            employee=performer_employee,
            executor="Сергеев Сергей Сергеевич",
            contract_project_disk_folder=folder,
        )
        performer.delete()
        client = Mock()
        client.is_configured = True
        client.username = "cloud-admin"
        client.revoke_user_share.return_value = True

        revoked = revoke_contract_folder_access_for_user(performer_user.pk, folder, client=client)

        self.assertTrue(revoked)
        client.revoke_user_share.assert_called_once_with(
            "cloud-admin",
            folder,
            f"ncstaff-{performer_user.pk}",
        )

    def test_revoke_contract_folder_access_keeps_share_when_folder_is_still_assigned(self):
        performer_user = User.objects.create_user(
            username="active-contract-share@example.com",
            email="active-contract-share@example.com",
            password="Secret123!",
            is_staff=True,
            is_active=True,
        )
        performer_employee = Employee.objects.create(user=performer_user)
        folder = (
            "/Corporate Root/02 Договоры/2026/Проект/Договор/02 Исполнители/"
            "6001010RU 001 Сергеев СС"
        )
        NextcloudUserLink.objects.create(
            user=performer_user,
            nextcloud_user_id=f"ncstaff-{performer_user.pk}",
            nextcloud_username=f"ncstaff-{performer_user.pk}",
            nextcloud_email=performer_user.email,
        )
        Performer.objects.create(
            registration=self.project,
            employee=performer_employee,
            executor="Сергеев Сергей Сергеевич",
            contract_project_disk_folder=folder,
        )
        client = Mock()
        client.is_configured = True
        client.username = "cloud-admin"

        revoked = revoke_contract_folder_access_for_user(performer_user.pk, folder, client=client)

        self.assertFalse(revoked)
        client.revoke_user_share.assert_not_called()

    def test_create_basic_project_workspace_accepts_slash_as_root_path(self):
        settings_obj = CloudStorageSettings.get_solo()
        settings_obj.nextcloud_root_path = "/"
        settings_obj.save()

        project_folder = _build_project_folder_name(self.project)
        project_path = f"/03 Проекты/2026/{project_folder}"
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
                call("cloud-admin", "/03 Проекты"),
                call("cloud-admin", "/03 Проекты/2026"),
                call("cloud-admin", project_path),
                call("cloud-admin", f"{project_path}/01 Документы"),
                call("cloud-admin", f"{project_path}/01 Документы/02 Письма"),
            ],
        )

    def test_create_basic_project_workspace_resolves_short_manager_label(self):
        self.project.project_manager = "Иванов И.И."
        self.project.project_manager_prs_id = ""
        self.project.save(update_fields=["project_manager", "project_manager_prs_id"])
        project_folder = _build_project_folder_name(self.project)
        project_path = f"/Corporate Root/03 Проекты/2026/{project_folder}"
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
        client.ensure_user_share.assert_called_once_with(
            "cloud-admin",
            project_path,
            f"ncstaff-{self.manager.pk}",
            permissions=15,
        )

    def test_create_basic_project_workspace_uses_manager_prs_id_not_duplicate_name(self):
        duplicate_user = User.objects.create_user(
            username="duplicate-admin@example.com",
            email="duplicate-admin@example.com",
            password="Secret123!",
            first_name="Иван",
            last_name="Иванов",
            is_staff=True,
            is_active=True,
        )
        Employee.objects.create(
            user=duplicate_user,
            person_record=self.manager_person,
            patronymic="Иванович",
            role="Администратор",
        )
        NextcloudUserLink.objects.create(
            user=duplicate_user,
            nextcloud_user_id=f"ncstaff-{duplicate_user.pk}",
            nextcloud_username=f"ncstaff-{duplicate_user.pk}",
            nextcloud_email="duplicate-admin@example.com",
        )
        project_folder = _build_project_folder_name(self.project)
        project_path = f"/Corporate Root/03 Проекты/2026/{project_folder}"
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
        client.ensure_user_share.assert_called_once_with(
            "cloud-admin",
            project_path,
            f"ncstaff-{self.manager.pk}",
            permissions=15,
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
            "/Corporate Root/03 Проекты",
            "/Corporate Root/03 Проекты/2026",
            "/Corporate Root/03 Проекты/2026/Проект 6001 DD Проект Nextcloud",
            "/Corporate Root/03 Проекты/2026/Проект 6001 DD Проект Nextcloud/01 Документы",
            "/Corporate Root/03 Проекты/2026/Проект 6001 DD Проект Nextcloud/01 Документы/02 Письма",
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
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
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

        self.assertEqual(workspace_path, f"/Corporate Root/01 ТКП/2026/{folder_name}")
        self.assertEqual(
            client.ensure_folder.call_args_list,
            [
                call("cloud-admin", "/Corporate Root/01 ТКП"),
                call("cloud-admin", "/Corporate Root/01 ТКП/2026"),
                call("cloud-admin", f"/Corporate Root/01 ТКП/2026/{folder_name}"),
            ],
        )
        client.ensure_user_share.assert_called_once_with(
            "cloud-admin",
            f"/Corporate Root/01 ТКП/2026/{folder_name}",
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

    @patch("nextcloud_app.workspace.ensure_nextcloud_account")
    def test_create_proposal_workspace_grants_editor_share_for_director(self, mocked_ensure_account):
        Employee.objects.create(user=self.author, role="Директор")
        mocked_ensure_account.return_value = Mock(nextcloud_user_id=f"ncstaff-{self.author.pk}")
        client = Mock()
        client.is_configured = True
        client.username = "cloud-admin"
        client.ensure_folder.side_effect = lambda _owner, path: "/" + "/".join(
            part for part in str(path).replace("\\", "/").split("/") if part
        )

        folder_name = f"{self.proposal.short_uid} {self.product.short_name} Сделка _ Восток"
        workspace_path = create_proposal_workspace(self.author, self.proposal, client=client)

        self.assertEqual(workspace_path, f"/Corporate Root/01 ТКП/2026/{folder_name}")
        mocked_ensure_account.assert_called_once()
        client.ensure_user_share.assert_called_once_with(
            "cloud-admin",
            f"/Corporate Root/01 ТКП/2026/{folder_name}",
            f"ncstaff-{self.author.pk}",
            permissions=15,
        )


@override_settings(
    NEXTCLOUD_PROVISIONING_BASE_URL="https://cloud.example.com",
    NEXTCLOUD_PROVISIONING_USERNAME="cloud-admin",
    NEXTCLOUD_PROVISIONING_TOKEN="token",
    NEXTCLOUD_OIDC_PROVIDER_ID=1,
)
class CloudStorageStructureMigrationTests(TestCase):
    def setUp(self):
        settings_obj = CloudStorageSettings.get_solo()
        settings_obj.primary_storage = CloudStorageSettings.PrimaryStorage.NEXTCLOUD
        settings_obj.nextcloud_root_path = "/Corporate Root"
        settings_obj.save()

        self.user = User.objects.create_user(username="migration-user")
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
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
        )
        self.proposal = ProposalRegistration.objects.create(
            number=3333,
            group_member=self.group_member,
            type=self.product,
            name="Миграция ТКП",
            year=2026,
            proposal_workspace_disk_path="/Corporate Root/ТКП/2026/333300RU DD Миграция ТКП",
            proposal_workspace_target_path="/ТКП/2026/333300RU DD Миграция ТКП",
            docx_file_link="/Corporate Root/ТКП/2026/333300RU DD Миграция ТКП/offer.docx",
        )
        self.project = ProjectRegistration.objects.create(
            number=6001,
            type=self.product,
            name="Миграция проекта",
            year=2026,
        )
        self.project_folder = f"{self.project.short_uid} DD Миграция проекта"
        ProjectWorkspace.objects.create(
            project=self.project,
            disk_path=f"/Corporate Root/2026/{self.project_folder}",
            created_by=self.user,
        )
        SourceDataWorkspace.objects.create(
            project=self.project,
            disk_path=f"/Corporate Root/2026/{self.project_folder}/05 Исходные данные",
            created_by=self.user,
        )
        self.performer = Performer.objects.create(
            registration=self.project,
            executor="Иванов Иван Иванович",
            contract_project_disk_folder=f"/Corporate Root/2026/{self.project_folder}/09 Договоры/000 Иванов ИИ",
        )

    def test_migrate_cloud_storage_structure_dry_run_does_not_update_database(self):
        out = StringIO()

        call_command(
            "migrate_cloud_storage_structure",
            "--old-root",
            "/Corporate Root",
            "--new-root",
            "/Corporate Root",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("DRY-RUN", output)
        self.assertIn(
            "MOVE /Corporate Root/ТКП/2026/333300RU DD Миграция ТКП -> "
            "/Corporate Root/01 ТКП/2026/333300RU DD Миграция ТКП",
            output,
        )
        self.assertIn(
            f"MOVE /Corporate Root/2026/{self.project_folder} -> "
            f"/Corporate Root/03 Проекты/2026/{self.project_folder}",
            output,
        )
        self.assertIn(
            f"MOVE /Corporate Root/2026/{self.project_folder}/09 Договоры/000 Иванов ИИ -> "
            f"/Corporate Root/02 Договоры/2026/{self.project_folder}/02 Исполнители/000 Иванов ИИ",
            output,
        )
        self.proposal.refresh_from_db()
        self.assertEqual(
            self.proposal.proposal_workspace_disk_path,
            "/Corporate Root/ТКП/2026/333300RU DD Миграция ТКП",
        )

    def test_migrate_cloud_storage_structure_handles_slash_old_root(self):
        self.proposal.proposal_workspace_disk_path = "/ТКП/2026/333300RU DD Миграция ТКП"
        self.proposal.proposal_workspace_target_path = "/ТКП/2026/333300RU DD Миграция ТКП"
        self.proposal.docx_file_link = "/ТКП/2026/333300RU DD Миграция ТКП/offer.docx"
        self.proposal.save(
            update_fields=[
                "proposal_workspace_disk_path",
                "proposal_workspace_target_path",
                "docx_file_link",
            ]
        )
        ProjectWorkspace.objects.filter(project=self.project).update(
            disk_path=f"/2026/{self.project_folder}"
        )
        SourceDataWorkspace.objects.filter(project=self.project).update(
            disk_path=f"/2026/{self.project_folder}/05 Исходные данные"
        )
        Performer.objects.filter(pk=self.performer.pk).update(
            contract_project_disk_folder=f"/2026/{self.project_folder}/09 Договоры/000 Иванов ИИ"
        )
        out = StringIO()

        call_command(
            "migrate_cloud_storage_structure",
            "--old-root",
            "/",
            "--new-root",
            "/",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn(
            "MOVE /ТКП/2026/333300RU DD Миграция ТКП -> "
            "/01 ТКП/2026/333300RU DD Миграция ТКП",
            output,
        )
        self.assertIn(
            f"MOVE /2026/{self.project_folder} -> "
            f"/03 Проекты/2026/{self.project_folder}",
            output,
        )
        self.assertIn(
            f"MOVE /2026/{self.project_folder}/09 Договоры/000 Иванов ИИ -> "
            f"/02 Договоры/2026/{self.project_folder}/02 Исполнители/000 Иванов ИИ",
            output,
        )
        self.assertIn(
            "proposals_app.ProposalRegistration"
            f"#{self.proposal.pk}.proposal_workspace_disk_path: "
            "/ТКП/2026/333300RU DD Миграция ТКП -> "
            "/01 ТКП/2026/333300RU DD Миграция ТКП",
            output,
        )
        self.assertIn(
            "checklists_app.ProjectWorkspace"
            f"#{self.project.yadisk_workspace.pk}.disk_path: "
            f"/2026/{self.project_folder} -> "
            f"/03 Проекты/2026/{self.project_folder}",
            output,
        )

    @patch("nextcloud_app.api.NextcloudApiClient.move_resource")
    def test_migrate_cloud_storage_structure_apply_moves_folders_and_updates_database(self, mocked_move):
        call_command(
            "migrate_cloud_storage_structure",
            "--old-root",
            "/Corporate Root",
            "--new-root",
            "/Corporate Root",
            "--apply",
            stdout=StringIO(),
        )

        mocked_move.assert_has_calls(
            [
                call(
                    "cloud-admin",
                    f"/Corporate Root/2026/{self.project_folder}",
                    f"/Corporate Root/03 Проекты/2026/{self.project_folder}",
                    overwrite=False,
                ),
                call(
                    "cloud-admin",
                    "/Corporate Root/ТКП/2026/333300RU DD Миграция ТКП",
                    "/Corporate Root/01 ТКП/2026/333300RU DD Миграция ТКП",
                    overwrite=False,
                ),
                call(
                    "cloud-admin",
                    f"/Corporate Root/2026/{self.project_folder}/09 Договоры/000 Иванов ИИ",
                    f"/Corporate Root/02 Договоры/2026/{self.project_folder}/02 Исполнители/000 Иванов ИИ",
                    overwrite=False,
                ),
            ],
            any_order=True,
        )
        self.assertEqual(mocked_move.call_count, 3)
        move_sources = [args[1] for args, _kwargs in mocked_move.call_args_list]
        self.assertLess(
            move_sources.index(f"/Corporate Root/2026/{self.project_folder}/09 Договоры/000 Иванов ИИ"),
            move_sources.index(f"/Corporate Root/2026/{self.project_folder}"),
        )
        self.proposal.refresh_from_db()
        self.assertEqual(
            self.proposal.proposal_workspace_disk_path,
            "/Corporate Root/01 ТКП/2026/333300RU DD Миграция ТКП",
        )
        self.assertEqual(
            self.proposal.proposal_workspace_target_path,
            "/01 ТКП/2026/333300RU DD Миграция ТКП",
        )
        workspace = ProjectWorkspace.objects.get(project=self.project)
        self.assertEqual(
            workspace.disk_path,
            f"/Corporate Root/03 Проекты/2026/{self.project_folder}",
        )
        self.performer.refresh_from_db()
        self.assertEqual(
            self.performer.contract_project_disk_folder,
            f"/Corporate Root/02 Договоры/2026/{self.project_folder}/02 Исполнители/000 Иванов ИИ",
        )

    def _prepare_contract_folder_structure_rows(self):
        contract_project = ContractProjectRegistration.objects.create(
            number=self.project.number,
            sub_number=1,
            group_member=self.group_member,
            type=self.product,
            name=self.project.name,
            year=2026,
        )
        self.project.contract_project_registration = contract_project
        self.project.save(update_fields=["contract_project_registration"])
        self.project.refresh_from_db()
        old_project_folder = f"{self.project.short_uid} DD Миграция проекта"
        old_base = f"/Corporate Root/02 Договоры/2026/{old_project_folder}/02 Исполнители"
        first_old_folder = f"{old_base}/000 Иванов ИИ"
        second_old_folder = f"{old_base}/001 Иванов ИИ"
        Performer.objects.filter(pk=self.performer.pk).update(
            contract_project_disk_folder=first_old_folder,
            contract_file=f"Договор {self.project.short_uid}_Иванов ИИ.docx",
        )
        second = Performer.objects.create(
            registration=self.project,
            executor="Иванов Иван Иванович",
            contract_project_disk_folder=second_old_folder,
            contract_file="custom-contract.docx",
        )
        new_base = (
            "/Corporate Root/02 Договоры/2026/"
            "60010RU DD Миграция проекта/"
            "6001010RU DD Миграция проекта/02 Исполнители"
        )
        return {
            "first_old_folder": first_old_folder,
            "second_old_folder": second_old_folder,
            "first_new_folder": f"{new_base}/6001010RU 001 Иванов ИИ",
            "second_new_folder": f"{new_base}/6001010RU 002 Иванов ИИ",
            "old_file": f"Договор {self.project.short_uid}_Иванов ИИ.docx",
            "new_file": "Договор 6001010RU_Иванов ИИ.docx",
            "second": second,
        }

    def test_migrate_contract_folder_structure_dry_run_reports_moves_and_skips_custom_file(self):
        paths = self._prepare_contract_folder_structure_rows()
        out = StringIO()

        call_command("migrate_contract_folder_structure", stdout=out)

        output = out.getvalue()
        self.assertIn("DRY-RUN: 2 folder move(s), 1 file rename(s), 1 skipped file(s).", output)
        self.assertIn(f"MOVE {paths['first_old_folder']} -> {paths['first_new_folder']}", output)
        self.assertIn(f"MOVE {paths['second_old_folder']} -> {paths['second_new_folder']}", output)
        self.assertIn(
            f"RENAME {paths['first_new_folder']}/{paths['old_file']} -> "
            f"{paths['first_new_folder']}/{paths['new_file']}",
            output,
        )
        self.assertIn("SKIP projects_app.Performer", output)
        self.performer.refresh_from_db()
        self.assertEqual(self.performer.contract_project_disk_folder, paths["first_old_folder"])

    @patch("nextcloud_app.api.NextcloudApiClient.move_resource")
    def test_migrate_contract_folder_structure_apply_moves_and_updates_database(self, mocked_move):
        paths = self._prepare_contract_folder_structure_rows()

        call_command("migrate_contract_folder_structure", "--apply", stdout=StringIO())

        mocked_move.assert_has_calls(
            [
                call("cloud-admin", paths["first_old_folder"], paths["first_new_folder"], overwrite=False),
                call("cloud-admin", paths["second_old_folder"], paths["second_new_folder"], overwrite=False),
                call(
                    "cloud-admin",
                    f"{paths['first_new_folder']}/{paths['old_file']}",
                    f"{paths['first_new_folder']}/{paths['new_file']}",
                    overwrite=False,
                ),
            ],
            any_order=False,
        )
        self.performer.refresh_from_db()
        paths["second"].refresh_from_db()
        self.assertEqual(self.performer.contract_project_disk_folder, paths["first_new_folder"])
        self.assertEqual(self.performer.contract_file, paths["new_file"])
        self.assertEqual(paths["second"].contract_project_disk_folder, paths["second_new_folder"])
        self.assertEqual(paths["second"].contract_file, "custom-contract.docx")

    @patch("nextcloud_app.api.NextcloudApiClient.move_resource")
    def test_migrate_contract_folder_structure_apply_deduplicates_shared_file_rename(self, mocked_move):
        contract_project = ContractProjectRegistration.objects.create(
            number=self.project.number,
            sub_number=1,
            group_member=self.group_member,
            type=self.product,
            name=self.project.name,
            year=2026,
        )
        self.project.contract_project_registration = contract_project
        self.project.save(update_fields=["contract_project_registration"])
        self.project.refresh_from_db()
        old_project_folder = f"{self.project.short_uid} DD Миграция проекта"
        old_folder = f"/Corporate Root/02 Договоры/2026/{old_project_folder}/02 Исполнители/000 Иванов ИИ"
        old_file = f"Договор {self.project.short_uid}_Иванов ИИ.docx"
        Performer.objects.filter(pk=self.performer.pk).update(
            contract_project_disk_folder=old_folder,
            contract_file=old_file,
        )
        second = Performer.objects.create(
            registration=self.project,
            executor="Иванов Иван Иванович",
            contract_project_disk_folder=old_folder,
            contract_file=old_file,
        )
        new_folder = (
            "/Corporate Root/02 Договоры/2026/"
            "60010RU DD Миграция проекта/"
            "6001010RU DD Миграция проекта/02 Исполнители/"
            "6001010RU 001 Иванов ИИ"
        )
        new_file = "Договор 6001010RU_Иванов ИИ.docx"

        call_command("migrate_contract_folder_structure", "--apply", stdout=StringIO())

        self.assertEqual(
            mocked_move.call_args_list,
            [
                call("cloud-admin", old_folder, new_folder, overwrite=False),
                call("cloud-admin", f"{new_folder}/{old_file}", f"{new_folder}/{new_file}", overwrite=False),
            ],
        )
        self.performer.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(self.performer.contract_project_disk_folder, new_folder)
        self.assertEqual(second.contract_project_disk_folder, new_folder)
        self.assertEqual(self.performer.contract_file, new_file)
        self.assertEqual(second.contract_file, new_file)


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
