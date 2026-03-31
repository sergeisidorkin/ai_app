import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from checklists_app.models import ChecklistItem, SourceDataItemFolder, SourceDataSectionFolder, SourceDataWorkspace
from core.models import CloudStorageSettings
from contracts_app.models import ContractTemplate
from nextcloud_app.models import NextcloudUserLink
from notifications_app.models import Notification
from policy_app.models import LAWYER_GROUP, Product
from projects_app.models import (
    ContractProjectTargetFolder,
    Performer,
    ProjectRegistration,
    RegistrationWorkspaceFolder,
    SourceDataTargetFolder,
    WorkVolume,
)
from projects_app.forms import ProjectRegistrationForm, WorkVolumeForm
from group_app.models import GroupMember
from users_app.models import Employee
from unittest.mock import call, patch


class SourceDataTargetFolderViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="staff-user",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)

    def test_load_excludes_unresolved_template_paths(self):
        RegistrationWorkspaceFolder.objects.bulk_create(
            [
                RegistrationWorkspaceFolder(user=self.user, level=1, name="05 Исходные данные", position=0),
                RegistrationWorkspaceFolder(user=self.user, level=2, name="{project_label}", position=1),
                RegistrationWorkspaceFolder(user=self.user, level=2, name="01 Запросы", position=2),
            ]
        )

        response = self.client.get(reverse("source_data_target_folder_load"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["options"], ["05 Исходные данные", "05 Исходные данные/01 Запросы"])

    def test_save_rejects_unresolved_template_paths(self):
        response = self.client.post(
            reverse("source_data_target_folder_save"),
            data=json.dumps({"folder_name": "05 Исходные данные/{project_label}"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        self.assertFalse(SourceDataTargetFolder.objects.filter(user=self.user).exists())

    def test_load_keeps_second_level_options_when_nextcloud_selected(self):
        settings_obj = CloudStorageSettings.get_solo()
        settings_obj.primary_storage = CloudStorageSettings.PrimaryStorage.NEXTCLOUD
        settings_obj.save()
        RegistrationWorkspaceFolder.objects.bulk_create(
            [
                RegistrationWorkspaceFolder(user=self.user, level=1, name="05 Исходные данные", position=0),
                RegistrationWorkspaceFolder(user=self.user, level=2, name="01 Запросы", position=1),
            ]
        )

        response = self.client.get(reverse("source_data_target_folder_load"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["options"], ["05 Исходные данные", "05 Исходные данные/01 Запросы"])


class ProjectRegistrationFormTests(TestCase):
    def setUp(self):
        self.group_member = GroupMember.objects.create(
            short_name="IMC",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
            position=0,
        )
        self.product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            service_type="service",
        )

    def test_type_and_deadline_are_required(self):
        form = ProjectRegistrationForm(
            data={
                "number": 4444,
                "group_member": self.group_member.pk,
                "agreement_type": "MAIN",
                "type": "",
                "name": "Проект Альфа",
                "status": "Не начат",
                "deadline": "",
                "year": 2026,
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("type", form.errors)
        self.assertIn("deadline", form.errors)


class WorkVolumePerformerCreationTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            service_type="service",
        )
        self.project_manager_employee = self._create_employee(
            username="project.manager",
            first_name="Иван",
            last_name="Иванов",
            patronymic="Иванович",
        )
        self.first_manager_employee = self._create_employee(
            username="asset.manager.one",
            first_name="Петр",
            last_name="Петров",
            patronymic="Петрович",
        )
        self.second_manager_employee = self._create_employee(
            username="asset.manager.two",
            first_name="Сидор",
            last_name="Сидоров",
            patronymic="Сидорович",
        )
        self.project_manager_name = "Иванов Иван Иванович"
        self.first_manager_name = "Петров Петр Петрович"
        self.second_manager_name = "Сидоров Сидор Сидорович"
        self.project = ProjectRegistration.objects.create(
            number=6001,
            type=self.product,
            name="Проект активов",
            year=2026,
            project_manager=self.project_manager_name,
        )
        self.product.sections.create(
            code="PRD",
            short_name="Project Director",
            short_name_ru="Руководитель проекта",
            name_en="Project Director",
            name_ru="Руководитель проекта",
            accounting_type="Раздел",
            position=1,
        )
        self.product.sections.create(
            code="PRJ",
            short_name="Project Manager",
            short_name_ru="Менеджер проекта",
            name_en="Project Manager",
            name_ru="Менеджер проекта",
            accounting_type="Раздел",
            position=2,
        )
        self.product.sections.create(
            code="CRD",
            short_name="Coordinator",
            short_name_ru="Координатор",
            name_en="Coordinator",
            name_ru="Координатор",
            accounting_type="Раздел",
            position=3,
        )

    def _create_employee(self, *, username, first_name, last_name, patronymic):
        user = get_user_model().objects.create_user(
            username=username,
            password="secret",
            first_name=first_name,
            last_name=last_name,
            is_staff=True,
        )
        return Employee.objects.create(user=user, patronymic=patronymic)

    def test_work_volume_form_uses_project_manager_label(self):
        form = WorkVolumeForm()

        self.assertEqual(form.fields["manager"].label, "Менеджер проекта")

    def test_equal_project_manager_and_manager_skips_prj_and_assigns_prd_to_project_manager(self):
        work_item = WorkVolume.objects.create(
            project=self.project,
            name="Актив 1",
            asset_name="Актив 1",
            manager=self.project_manager_name,
        )

        self.assertFalse(
            Performer.objects.filter(work_item=work_item, typical_section__code="PRJ").exists()
        )
        prd = Performer.objects.get(work_item=work_item, typical_section__code="PRD")
        self.assertEqual(prd.executor, self.project_manager_name)
        self.assertEqual(prd.employee, self.project_manager_employee)

    def test_different_manager_creates_prj_and_does_not_duplicate_prd_or_crd(self):
        first_work_item = WorkVolume.objects.create(
            project=self.project,
            name="Актив 1",
            asset_name="Актив 1",
            manager=self.first_manager_name,
        )

        self.assertTrue(
            Performer.objects.filter(work_item=first_work_item, typical_section__code="PRD").exists()
        )
        self.assertTrue(
            Performer.objects.filter(work_item=first_work_item, typical_section__code="PRJ").exists()
        )

        second_work_item = WorkVolume.objects.create(
            project=self.project,
            name="Актив 2",
            asset_name="Актив 2",
            manager=self.second_manager_name,
        )

        self.assertEqual(
            Performer.objects.filter(registration=self.project, typical_section__code="PRD").count(),
            1,
        )
        self.assertEqual(
            Performer.objects.filter(registration=self.project, typical_section__code="CRD").count(),
            1,
        )
        self.assertEqual(
            Performer.objects.filter(registration=self.project, typical_section__code="PRJ").count(),
            2,
        )

        first_prj = Performer.objects.get(work_item=first_work_item, typical_section__code="PRJ")
        second_prj = Performer.objects.get(work_item=second_work_item, typical_section__code="PRJ")
        prd = Performer.objects.get(registration=self.project, typical_section__code="PRD")

        self.assertEqual(first_prj.executor, self.first_manager_name)
        self.assertEqual(first_prj.employee, self.first_manager_employee)
        self.assertEqual(second_prj.executor, self.second_manager_name)
        self.assertEqual(second_prj.employee, self.second_manager_employee)
        self.assertEqual(prd.executor, self.project_manager_name)
        self.assertEqual(prd.employee, self.project_manager_employee)


class CloudStorageProjectRoutingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="project-staff",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            service_type="service",
        )
        self.project = ProjectRegistration.objects.create(
            number=5001,
            type=self.product,
            name="Проект маршрутизации",
            year=2026,
        )

    def test_create_workspace_returns_controlled_error_when_nextcloud_selected(self):
        settings_obj = CloudStorageSettings.get_solo()
        settings_obj.primary_storage = CloudStorageSettings.PrimaryStorage.NEXTCLOUD
        settings_obj.save()

        response = self.client.post(
            reverse("create_workspace"),
            {"project_id": self.project.pk},
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertIn("Nextcloud", payload["error"])

    def test_projects_partial_uses_current_primary_cloud_label_in_workspace_modal(self):
        settings_obj = CloudStorageSettings.get_solo()
        settings_obj.primary_storage = CloudStorageSettings.PrimaryStorage.NEXTCLOUD
        settings_obj.save()

        response = self.client.get(reverse("projects_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="reg-create-workspace-storage-label">Nextcloud', html=False)

    def test_workspace_folders_list_returns_current_primary_cloud_label(self):
        settings_obj = CloudStorageSettings.get_solo()
        settings_obj.primary_storage = CloudStorageSettings.PrimaryStorage.NEXTCLOUD
        settings_obj.save()

        response = self.client.get(reverse("workspace_folders_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["storage_label"], "Nextcloud")

    def test_performers_partial_uses_current_primary_cloud_label_in_contract_modal(self):
        settings_obj = CloudStorageSettings.get_solo()
        settings_obj.primary_storage = CloudStorageSettings.PrimaryStorage.NEXTCLOUD
        settings_obj.save()

        response = self.client.get(reverse("performers_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "На Nextcloud в целевой папке будут созданы папки исполнителей с проектами договоров.",
            html=False,
        )

    def test_performers_partial_uses_current_primary_cloud_label_in_source_data_modal(self):
        settings_obj = CloudStorageSettings.get_solo()
        settings_obj.primary_storage = CloudStorageSettings.PrimaryStorage.NEXTCLOUD
        settings_obj.save()

        response = self.client.get(reverse("performers_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "На Nextcloud в целевой директории будет создана структура папок для выбранного проекта в соответствии с согласованным информационным запросом.",
            html=False,
        )


@override_settings(
    NEXTCLOUD_PROVISIONING_BASE_URL="https://cloud.example.com",
    NEXTCLOUD_PROVISIONING_USERNAME="cloud-admin",
    NEXTCLOUD_PROVISIONING_TOKEN="token",
    NEXTCLOUD_OIDC_PROVIDER_ID=1,
)
class NextcloudSourceDataWorkspaceFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="source-data-staff",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)
        settings_obj = CloudStorageSettings.get_solo()
        settings_obj.primary_storage = CloudStorageSettings.PrimaryStorage.NEXTCLOUD
        settings_obj.nextcloud_root_path = "/Corporate Root"
        settings_obj.save()
        self.product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            service_type="service",
        )
        self.project = ProjectRegistration.objects.create(
            number=5003,
            type=self.product,
            name="Исходные данные",
            year=2026,
        )
        self.section = self.product.sections.create(
            code="FIN",
            short_name="Finance",
            short_name_ru="Финансы",
            name_en="Finance",
            name_ru="Финансы",
            accounting_type="Раздел",
            position=1,
        )
        self.item = ChecklistItem.objects.create(
            project=self.project,
            section=self.section,
            code="REQ",
            number=1,
            short_name="ОСВ",
            name="Оборотно-сальдовая ведомость",
            position=1,
        )
        Performer.objects.create(
            registration=self.project,
            asset_name="ООО Ромашка",
            typical_section=self.section,
            info_approval_status=Performer.InfoApprovalStatus.APPROVED,
        )
        SourceDataTargetFolder.objects.create(user=self.user, folder_name="05 Исходные данные/01 Запросы")

    @patch("nextcloud_app.api.NextcloudApiClient.ensure_public_link_share")
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_folder")
    def test_create_source_data_workspace_uses_nextcloud_and_stores_public_links(
        self,
        mocked_ensure_folder,
        mocked_public_share,
    ):
        expected_project_folder = f"{self.project.short_uid} DD Исходные данные"
        base_path = f"/Corporate Root/2026/{expected_project_folder}/05 Исходные данные/01 Запросы"
        section_path = f"{base_path}/01 FIN Финансы"
        item_path = f"{section_path}/REQ-01 ОСВ"
        mocked_ensure_folder.side_effect = [section_path, item_path]
        mocked_public_share.return_value = "https://cloud.example.com/s/item-folder"

        response = self.client.post(
            reverse("create_source_data_workspace"),
            {"project_id": self.project.pk},
        )

        self.assertEqual(response.status_code, 200)
        chunks = [json.loads(chunk.decode("utf-8").strip()) for chunk in response.streaming_content]
        self.assertTrue(chunks[-1]["ok"])
        self.assertIn("Nextcloud", chunks[-1]["message"])

        mocked_ensure_folder.assert_has_calls(
            [
                call("cloud-admin", section_path),
                call("cloud-admin", item_path),
            ]
        )
        mocked_public_share.assert_has_calls(
            [
                call("cloud-admin", item_path, _quick=True),
            ]
        )

        section_folder = SourceDataSectionFolder.objects.get(project=self.project, section=self.section, asset_name="ООО Ромашка")
        item_folder = SourceDataItemFolder.objects.get(
            project=self.project,
            checklist_item=self.item,
            asset_name="ООО Ромашка",
        )
        workspace = SourceDataWorkspace.objects.get(project=self.project)
        self.assertEqual(section_folder.disk_path, section_path)
        self.assertEqual(section_folder.public_url, "")
        self.assertEqual(item_folder.disk_path, item_path)
        self.assertEqual(item_folder.public_url, "https://cloud.example.com/s/item-folder")
        self.assertEqual(workspace.disk_path, base_path)
        self.assertEqual(workspace.created_by, self.user)


@override_settings(
    NEXTCLOUD_PROVISIONING_BASE_URL="https://cloud.example.com",
    NEXTCLOUD_PROVISIONING_USERNAME="cloud-admin",
    NEXTCLOUD_PROVISIONING_TOKEN="token",
    NEXTCLOUD_OIDC_PROVIDER_ID=1,
)
class NextcloudContractProjectFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="contracts-staff",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)
        settings_obj = CloudStorageSettings.get_solo()
        settings_obj.primary_storage = CloudStorageSettings.PrimaryStorage.NEXTCLOUD
        settings_obj.nextcloud_root_path = "/Corporate Root"
        settings_obj.save()
        self.product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            service_type="service",
        )
        self.project = ProjectRegistration.objects.create(
            number=5002,
            type=self.product,
            name="Контрактный проект",
            year=2026,
        )
        self.recipient_user = get_user_model().objects.create_user(
            username="performer@example.com",
            email="performer@example.com",
            password="secret",
            first_name="Иван",
            last_name="Иванов",
            is_staff=True,
        )
        self.employee = Employee.objects.create(
            user=self.recipient_user,
            patronymic="Иванович",
            employment="Фрилансер",
        )
        self.lawyer_user = get_user_model().objects.create_user(
            username="lawyer@example.com",
            email="lawyer@example.com",
            password="secret",
            is_staff=True,
        )
        lawyer_group, _ = Group.objects.get_or_create(name=LAWYER_GROUP)
        self.lawyer_user.groups.add(lawyer_group)
        self.performer = Performer.objects.create(
            registration=self.project,
            employee=self.employee,
            executor="Иванов Иван Иванович",
        )
        ContractProjectTargetFolder.objects.create(user=self.user, folder_name="09 Договоры")
        self.template = ContractTemplate.objects.create(
            product=self.product,
            contract_type="gph",
            party="individual",
            country_name="",
            sample_name="Базовый шаблон",
            version="1",
            file=SimpleUploadedFile(
                "contract.docx",
                b"fake-docx-content",
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            is_all_sections=True,
        )
        self.executor_link = NextcloudUserLink.objects.create(
            user=self.recipient_user,
            nextcloud_user_id=f"ncstaff-{self.recipient_user.pk}",
            nextcloud_username=f"ncstaff-{self.recipient_user.pk}",
            nextcloud_email=self.recipient_user.email,
        )
        self.lawyer_link = NextcloudUserLink.objects.create(
            user=self.lawyer_user,
            nextcloud_user_id=f"ncstaff-{self.lawyer_user.pk}",
            nextcloud_username=f"ncstaff-{self.lawyer_user.pk}",
            nextcloud_email=self.lawyer_user.email,
        )

    @patch("nextcloud_app.provisioning.ensure_nextcloud_account")
    @patch("contracts_app.variable_resolver.resolve_variables", return_value=({}, {}))
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_user_share")
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_public_link_share", return_value="https://cloud.example.com/s/public-doc")
    @patch("nextcloud_app.api.NextcloudApiClient.upload_file", return_value=True)
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_folder", return_value="/Corporate Root/2026/5002 DD Контрактный проект/09 Договоры/000 Иванов ИИ")
    @patch("nextcloud_app.api.NextcloudApiClient.list_resources", return_value=[])
    def test_create_contract_project_uses_nextcloud_and_stores_public_link(
        self,
        mocked_list_resources,
        mocked_ensure_folder,
        mocked_upload_file,
        mocked_public_share,
        mocked_ensure_user_share,
        mocked_resolve_variables,
        mocked_ensure_nextcloud_account,
    ):
        mocked_ensure_nextcloud_account.side_effect = lambda user, client=None: (
            self.executor_link if user.pk == self.recipient_user.pk else self.lawyer_link
        )
        response = self.client.post(
            reverse("create_contract_project"),
            {"performer_ids[]": [self.performer.pk]},
        )

        self.assertEqual(response.status_code, 200)
        chunks = [json.loads(chunk.decode("utf-8").strip()) for chunk in response.streaming_content]
        self.assertEqual(chunks[-1]["ok"], True)

        self.performer.refresh_from_db()
        expected_project_folder = f"{self.project.short_uid} DD Контрактный проект"
        expected_base_path = f"/Corporate Root/2026/{expected_project_folder}/09 Договоры"
        expected_folder_path = f"{expected_base_path}/000 Иванов ИИ"
        expected_upload_path = f"{expected_folder_path}/Договор 5002_Иванов ИИ.docx"

        mocked_list_resources.assert_called_once_with("cloud-admin", expected_base_path, limit=1000)
        mocked_ensure_folder.assert_called_once_with("cloud-admin", expected_folder_path)
        mocked_upload_file.assert_called_once()
        self.assertEqual(mocked_upload_file.call_args.args[0], "cloud-admin")
        self.assertEqual(mocked_upload_file.call_args.args[1], expected_upload_path)
        mocked_public_share.assert_called_once_with("cloud-admin", expected_upload_path)
        mocked_ensure_user_share.assert_has_calls(
            [
                call("cloud-admin", expected_folder_path, self.executor_link.nextcloud_user_id, permissions=1),
                call("cloud-admin", expected_folder_path, self.lawyer_link.nextcloud_user_id, permissions=1),
            ],
            any_order=True,
        )
        self.assertTrue(self.performer.contract_project_created)
        self.assertEqual(self.performer.contract_project_link, "https://cloud.example.com/s/public-doc")
        self.assertEqual(self.performer.contract_project_disk_folder, expected_folder_path)
        self.assertIsNotNone(self.performer.contract_project_created_at)
        self.assertIsNotNone(self.performer.contract_date)

    def test_contract_request_notification_uses_existing_nextcloud_link(self):
        self.performer.contract_project_link = "https://cloud.example.com/s/public-doc"
        self.performer.save(update_fields=["contract_project_link"])
        request_sent_at = timezone.localtime().replace(second=0, microsecond=0)

        response = self.client.post(
            reverse("contract_request"),
            {
                "performer_ids[]": [self.performer.pk],
                "duration_hours": "24",
                "request_sent_at": request_sent_at.isoformat(),
                "delivery_channels[]": ["platform"],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.performer.refresh_from_db()
        self.assertEqual(self.performer.contract_sent_at, request_sent_at)
        notification = Notification.objects.get(notification_type=Notification.NotificationType.PROJECT_CONTRACT_CONCLUSION)
        self.assertEqual(notification.payload["document_link"], "https://cloud.example.com/s/public-doc")
        self.assertIn("https://cloud.example.com/s/public-doc", notification.content_text)
