import json
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from urllib.parse import quote

from policy_app.models import EXPERT_GROUP, Product, TypicalSection
from projects_app.models import LegalEntity, Performer, ProjectRegistration, SourceDataTargetFolder, WorkVolume
from users_app.models import Employee
from notifications_app.models import Notification, NotificationPerformerLink
from core.models import CloudStorageSettings

from checklists_app.models import (
    ChecklistCustomerStatus,
    ChecklistItem,
    ChecklistItemAuditLog,
    ChecklistSortChunk,
    ChecklistSortProposal,
    ChecklistSortRun,
    ChecklistStatus,
    ProjectWorkspace,
    SharedChecklistLink,
    SourceDataItemFolder,
    SourceDataWorkspace,
)
from checklists_app.views import SOURCE_DATA_SELECT_ASSET_HINT, _project_options


class ChecklistFilterTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="checklists-user",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
        )
        self.project_low = ProjectRegistration.objects.create(
            number=4001,
            type=self.product,
            name="Проект ниже",
            year=2026,
        )
        self.project_high = ProjectRegistration.objects.create(
            number=5002,
            type=self.product,
            name="Проект выше",
            year=2026,
        )
        self.section_accounting = TypicalSection.objects.create(
            product=self.product,
            code="SEC",
            short_name="Section",
            short_name_ru="Раздел",
            name_en="Section",
            name_ru="Раздел",
            accounting_type="Раздел",
        )
        self.section_service = TypicalSection.objects.create(
            product=self.product,
            code="SRV",
            short_name="Service",
            short_name_ru="Услуга",
            name_en="Service",
            name_ru="Услуга",
            accounting_type="Услуги",
        )
        Performer.objects.create(
            registration=self.project_high,
            asset_name="Asset A",
            executor="Иванов Иван Иванович",
            typical_section=self.section_accounting,
        )
        Performer.objects.create(
            registration=self.project_high,
            asset_name="Asset A",
            executor="Иванов Иван Иванович",
            typical_section=self.section_service,
        )
        self.shared_link = SharedChecklistLink.objects.create(
            project=self.project_high,
            created_by=self.user,
        )

    def test_project_options_are_sorted_by_project_number_desc(self):
        options = _project_options()

        self.assertGreaterEqual(len(options), 2)
        self.assertEqual(options[0]["id"], self.project_high.id)
        self.assertEqual(options[1]["id"], self.project_low.id)

    def test_expert_panel_project_options_show_only_confirmed_participation_projects(self):
        expert_user = get_user_model().objects.create_user(
            username="checklists-expert",
            password="secret",
            is_staff=True,
            first_name="Иван",
            last_name="Эксперт",
        )
        expert_employee = Employee.objects.create(
            user=expert_user,
            patronymic="Иванович",
            role=EXPERT_GROUP,
        )
        Performer.objects.create(
            registration=self.project_high,
            asset_name="Asset B",
            executor=Performer.employee_full_name(expert_employee),
            employee=expert_employee,
            typical_section=self.section_accounting,
            participation_response=Performer.ParticipationResponse.CONFIRMED,
        )
        Performer.objects.create(
            registration=self.project_low,
            asset_name="Asset C",
            executor=Performer.employee_full_name(expert_employee),
            employee=expert_employee,
            typical_section=self.section_accounting,
            participation_response=Performer.ParticipationResponse.DECLINED,
        )
        self.client.force_login(expert_user)

        response = self.client.get(reverse("checklists_app:panel_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.project_high.name)
        self.assertNotContains(response, self.project_low.name)

    def test_internal_project_meta_sections_show_only_accounting_type_section_rows(self):
        response = self.client.get(
            reverse("checklists_app:project_meta", args=[self.project_high.short_uid]),
            {"asset": "Asset A"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["sections"],
            [{"id": self.section_accounting.id, "name": f"{self.section_accounting} {self.section_accounting.short_name_ru}"}],
        )

    def test_shared_project_meta_sections_show_only_accounting_type_section_rows(self):
        response = self.client.get(
            reverse("checklists_app:shared_project_meta", args=[self.shared_link.token]),
            {"asset": "Asset A"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["sections"],
            [{"id": self.section_accounting.id, "name": f"{self.section_accounting} {self.section_accounting.short_name_ru}"}],
        )


class ChecklistStatusPermissionTests(TestCase):
    def setUp(self):
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
            name="Проект прав доступа",
            year=2026,
        )
        self.section_allowed = TypicalSection.objects.create(
            product=self.product,
            code="ALW",
            short_name="Allowed",
            short_name_ru="Разрешенный",
            name_en="Allowed",
            name_ru="Разрешенный",
            accounting_type="Раздел",
        )
        self.section_other = TypicalSection.objects.create(
            product=self.product,
            code="OTH",
            short_name="Other",
            short_name_ru="Чужой",
            name_en="Other",
            name_ru="Чужой",
            accounting_type="Раздел",
        )
        self.work_allowed = WorkVolume.objects.create(
            project=self.project,
            name="Asset A",
            asset_name="Asset A",
        )
        self.work_other = WorkVolume.objects.create(
            project=self.project,
            name="Asset B",
            asset_name="Asset B",
        )
        self.legal_allowed = LegalEntity.objects.filter(work_item=self.work_allowed).first()
        self.legal_other = LegalEntity.objects.filter(work_item=self.work_other).first()

        self.item_allowed = ChecklistItem.objects.create(
            project=self.project,
            section=self.section_allowed,
            code="ALW",
            number=1,
            short_name="Allowed item",
            name="Allowed item",
        )
        self.item_other_section = ChecklistItem.objects.create(
            project=self.project,
            section=self.section_other,
            code="OTH",
            number=1,
            short_name="Other item",
            name="Other item",
        )

        self.expert_user = get_user_model().objects.create_user(
            username="status-expert",
            password="secret",
            is_staff=True,
            first_name="Иван",
            last_name="Эксперт",
        )
        self.expert_employee = Employee.objects.create(
            user=self.expert_user,
            patronymic="Иванович",
            role=EXPERT_GROUP,
        )
        self.performer_allowed = Performer.objects.create(
            work_item=self.work_allowed,
            registration=self.project,
            asset_name="Asset A",
            executor=Performer.employee_full_name(self.expert_employee),
            employee=self.expert_employee,
            typical_section=self.section_allowed,
            participation_response=Performer.ParticipationResponse.CONFIRMED,
        )
        self.shared_link = SharedChecklistLink.objects.create(project=self.project)

    def _post_json(self, url, payload):
        return self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def _status_payload(self, item, legal_entity, status):
        return {
            "asset_name": "all",
            "updates": [{
                "checklist_item": item.id,
                "legal_entity": legal_entity.id,
                "status": status,
            }],
        }

    def test_expert_grid_marks_only_confirmed_section_asset_imcm_cells_editable(self):
        self.client.force_login(self.expert_user)

        response = self.client.get(reverse("checklists_app:grid_data"), {
            "project_uid": self.project.short_uid,
            "asset": "all",
            "section": "all",
        })

        self.assertEqual(response.status_code, 200)
        rows = [row for row in response.json()["rows"] if row.get("kind") == "item"]
        allowed_row = next(row for row in rows if row["id"] == self.item_allowed.id)
        other_section_row = next(row for row in rows if row["id"] == self.item_other_section.id)

        allowed_cell = next(cell for cell in allowed_row["cells"] if cell["entityId"] == self.legal_allowed.id)
        wrong_asset_cell = next(cell for cell in allowed_row["cells"] if cell["entityId"] == self.legal_other.id)
        other_section_cell = next(cell for cell in other_section_row["cells"] if cell["entityId"] == self.legal_allowed.id)
        allowed_customer_cell = next(
            cell for cell in allowed_row["customerCells"] if cell["entityId"] == self.legal_allowed.id
        )

        self.assertTrue(allowed_cell["editable"])
        self.assertFalse(wrong_asset_cell["editable"])
        self.assertFalse(other_section_cell["editable"])
        self.assertFalse(allowed_customer_cell["editable"])

    def test_expert_section_filter_keeps_create_url_for_pending_own_section(self):
        notification = Notification.objects.create(
            notification_type=Notification.NotificationType.PROJECT_INFO_REQUEST_APPROVAL,
            recipient=self.expert_user,
            project=self.project,
            title_text="Согласуйте запрос",
        )
        NotificationPerformerLink.objects.create(
            notification=notification,
            performer=self.performer_allowed,
        )
        self.client.force_login(self.expert_user)

        response = self.client.get(reverse("checklists_app:grid_data"), {
            "project_uid": self.project.short_uid,
            "asset": "all",
            "section": str(self.section_allowed.id),
        })

        self.assertEqual(response.status_code, 200)
        create_url = response.json()["ui"]["createUrl"]
        self.assertIn(reverse("checklists_app:item_form_create"), create_url)
        self.assertIn(f"section={self.section_allowed.id}", create_url)

    def test_batch_edit_renumbers_items_after_reorder(self):
        second = ChecklistItem.objects.create(
            project=self.project,
            section=self.section_allowed,
            code="ALW",
            number=2,
            position=2,
            short_name="Second item",
            name="Second item",
        )
        third = ChecklistItem.objects.create(
            project=self.project,
            section=self.section_allowed,
            code="ALW",
            number=3,
            position=3,
            short_name="Third item",
            name="Third item",
        )
        self.client.force_login(self.expert_user)

        response = self._post_json(reverse("checklists_app:item_batch_edit"), {
            "order": [
                {"id": third.id, "position": 0},
                {"id": self.item_allowed.id, "position": 1},
                {"id": second.id, "position": 2},
            ],
        })

        self.assertEqual(response.status_code, 204)
        self.item_allowed.refresh_from_db()
        second.refresh_from_db()
        third.refresh_from_db()
        self.assertEqual(third.number, 1)
        self.assertEqual(self.item_allowed.number, 2)
        self.assertEqual(second.number, 3)

    def test_batch_edit_rejects_implicit_delete_payload(self):
        self.client.force_login(self.expert_user)

        response = self._post_json(reverse("checklists_app:item_batch_edit"), {
            "deleted": [self.item_allowed.id],
        })

        self.assertEqual(response.status_code, 400)
        self.assertTrue(ChecklistItem.objects.filter(pk=self.item_allowed.pk).exists())
        self.assertFalse(
            ChecklistItemAuditLog.objects.filter(
                checklist_item=self.item_allowed,
                action=ChecklistItemAuditLog.Action.SOFT_DELETED,
            ).exists()
        )

    def test_batch_edit_explicit_delete_soft_deletes_item_and_keeps_related_data(self):
        status = ChecklistStatus.objects.create(
            checklist_item=self.item_allowed,
            legal_entity=self.legal_allowed,
            status=ChecklistStatus.Status.PROVIDED,
            updated_by=self.expert_user,
        )
        self.client.force_login(self.expert_user)

        response = self._post_json(reverse("checklists_app:item_batch_edit"), {
            "deleted": [self.item_allowed.id],
            "explicit_delete": True,
        })

        self.assertEqual(response.status_code, 204)
        self.assertFalse(ChecklistItem.objects.filter(pk=self.item_allowed.pk).exists())
        deleted_item = ChecklistItem.all_objects.get(pk=self.item_allowed.pk)
        self.assertIsNotNone(deleted_item.deleted_at)
        self.assertEqual(deleted_item.deleted_by, self.expert_user)
        self.assertTrue(ChecklistStatus.objects.filter(pk=status.pk, checklist_item=deleted_item).exists())
        self.assertTrue(
            ChecklistItemAuditLog.objects.filter(
                checklist_item=deleted_item,
                action=ChecklistItemAuditLog.Action.SOFT_DELETED,
                actor=self.expert_user,
            ).exists()
        )

    def test_expert_can_update_only_confirmed_imcm_status_and_not_customer_status(self):
        self.client.force_login(self.expert_user)

        allowed_response = self._post_json(
            reverse("checklists_app:update_status_batch"),
            self._status_payload(self.item_allowed, self.legal_allowed, ChecklistStatus.Status.PROVIDED),
        )
        denied_asset_response = self._post_json(
            reverse("checklists_app:update_status_batch"),
            self._status_payload(self.item_allowed, self.legal_other, ChecklistStatus.Status.PROVIDED),
        )
        denied_customer_response = self._post_json(
            reverse("checklists_app:update_customer_status_batch"),
            self._status_payload(
                self.item_allowed,
                self.legal_allowed,
                ChecklistCustomerStatus.Status.TRANSFERRED,
            ),
        )

        self.assertEqual(allowed_response.status_code, 200)
        self.assertTrue(
            ChecklistStatus.objects.filter(
                checklist_item=self.item_allowed,
                legal_entity=self.legal_allowed,
                status=ChecklistStatus.Status.PROVIDED,
            ).exists()
        )
        self.assertEqual(denied_asset_response.status_code, 400)
        self.assertFalse(
            ChecklistStatus.objects.filter(
                checklist_item=self.item_allowed,
                legal_entity=self.legal_other,
            ).exists()
        )
        self.assertEqual(denied_customer_response.status_code, 400)
        self.assertFalse(
            ChecklistCustomerStatus.objects.filter(
                checklist_item=self.item_allowed,
                legal_entity=self.legal_allowed,
            ).exists()
        )

    def test_public_link_cannot_update_imcm_but_can_update_customer_status(self):
        self.client.logout()

        grid_response = self.client.get(reverse("checklists_app:shared_grid_data", args=[self.shared_link.token]), {
            "asset": "all",
            "section": "all",
        })
        imcm_response = self._post_json(
            reverse("checklists_app:shared_update_status_batch", args=[self.shared_link.token]),
            self._status_payload(self.item_allowed, self.legal_allowed, ChecklistStatus.Status.PROVIDED),
        )
        customer_response = self._post_json(
            reverse("checklists_app:shared_update_customer_status_batch", args=[self.shared_link.token]),
            self._status_payload(
                self.item_allowed,
                self.legal_allowed,
                ChecklistCustomerStatus.Status.TRANSFERRED,
            ),
        )

        self.assertEqual(grid_response.status_code, 200)
        rows = [row for row in grid_response.json()["rows"] if row.get("kind") == "item"]
        allowed_row = next(row for row in rows if row["id"] == self.item_allowed.id)
        imcm_cell = next(cell for cell in allowed_row["cells"] if cell["entityId"] == self.legal_allowed.id)
        customer_cell = next(cell for cell in allowed_row["customerCells"] if cell["entityId"] == self.legal_allowed.id)
        self.assertFalse(imcm_cell["editable"])
        self.assertTrue(customer_cell["editable"])

        self.assertEqual(imcm_response.status_code, 403)
        self.assertFalse(
            ChecklistStatus.objects.filter(
                checklist_item=self.item_allowed,
                legal_entity=self.legal_allowed,
            ).exists()
        )
        self.assertEqual(customer_response.status_code, 200)
        self.assertTrue(
            ChecklistCustomerStatus.objects.filter(
                checklist_item=self.item_allowed,
                legal_entity=self.legal_allowed,
                status=ChecklistCustomerStatus.Status.TRANSFERRED,
            ).exists()
        )


class ChecklistSourceDataFilesScopeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="files-scope-staff",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
        )
        self.project = ProjectRegistration.objects.create(
            number=7001,
            type=self.product,
            name="Несколько активов",
            year=2026,
        )
        self.section = TypicalSection.objects.create(
            product=self.product,
            code="FIN",
            short_name="Finance",
            short_name_ru="Финансы",
            name_en="Finance",
            name_ru="Финансы",
            accounting_type="Раздел",
        )
        self.work_a = WorkVolume.objects.create(
            project=self.project,
            name="Asset A",
            asset_name="Asset A",
        )
        self.work_b = WorkVolume.objects.create(
            project=self.project,
            name="Asset B",
            asset_name="Asset B",
        )
        Performer.objects.create(
            registration=self.project,
            work_item=self.work_a,
            asset_name="Asset A",
            typical_section=self.section,
        )
        Performer.objects.create(
            registration=self.project,
            work_item=self.work_b,
            asset_name="Asset B",
            typical_section=self.section,
        )
        self.item = ChecklistItem.objects.create(
            project=self.project,
            section=self.section,
            code="REQ",
            number=1,
            short_name="ОСВ",
            name="Оборотно-сальдовая ведомость",
        )
        SourceDataItemFolder.objects.create(
            project=self.project,
            checklist_item=self.item,
            asset_name="Asset A",
            disk_path="/a/REQ-01 ОСВ",
            public_url="https://cloud.example.com/s/asset-a",
            file_count=3,
            last_upload_at=timezone.now(),
        )
        SourceDataItemFolder.objects.create(
            project=self.project,
            checklist_item=self.item,
            asset_name="Asset B",
            disk_path="/b/REQ-01 ОСВ",
            public_url="https://cloud.example.com/s/asset-b",
            file_count=7,
            last_upload_at=timezone.now(),
        )

    def _item_row(self, asset):
        response = self.client.get(reverse("checklists_app:grid_data"), {
            "project_uid": self.project.short_uid,
            "asset": asset,
            "section": "all",
        })
        self.assertEqual(response.status_code, 200)
        rows = [row for row in response.json()["rows"] if row.get("kind") == "item"]
        return next(row for row in rows if row["id"] == self.item.id)

    def test_all_assets_hides_file_stats_and_source_data_link(self):
        row = self._item_row("all")

        self.assertIsNone(row["fileCount"])
        self.assertIsNone(row["lastUploadAt"])
        self.assertEqual(row["sourceDataUrl"], "")
        self.assertEqual(row["filesHint"], SOURCE_DATA_SELECT_ASSET_HINT)

    def test_selected_asset_shows_that_asset_file_stats(self):
        row = self._item_row("asset:Asset A")

        self.assertEqual(row["fileCount"], 3)
        self.assertEqual(row["sourceDataUrl"], "https://cloud.example.com/s/asset-a")
        self.assertEqual(row["filesHint"], "")

    def test_single_asset_project_still_shows_files_for_all_filter(self):
        single_project = ProjectRegistration.objects.create(
            number=7002,
            type=self.product,
            name="Один актив",
            year=2026,
        )
        work = WorkVolume.objects.create(
            project=single_project,
            name="Only Asset",
            asset_name="Only Asset",
        )
        Performer.objects.create(
            registration=single_project,
            work_item=work,
            asset_name="Only Asset",
            typical_section=self.section,
        )
        item = ChecklistItem.objects.create(
            project=single_project,
            section=self.section,
            code="REQ",
            number=1,
            short_name="ОСВ",
            name="Оборотно-сальдовая ведомость",
        )
        SourceDataItemFolder.objects.create(
            project=single_project,
            checklist_item=item,
            asset_name="Only Asset",
            disk_path="/only/REQ-01 ОСВ",
            public_url="https://cloud.example.com/s/only",
            file_count=4,
            last_upload_at=timezone.now(),
        )

        response = self.client.get(reverse("checklists_app:grid_data"), {
            "project_uid": single_project.short_uid,
            "asset": "all",
            "section": "all",
        })
        self.assertEqual(response.status_code, 200)
        row = next(row for row in response.json()["rows"] if row.get("kind") == "item" and row["id"] == item.id)
        self.assertEqual(row["fileCount"], 4)
        self.assertEqual(row["sourceDataUrl"], "https://cloud.example.com/s/only")
        self.assertEqual(row["filesHint"], "")


@override_settings(
    NEXTCLOUD_BASE_URL="https://cloud.example.com",
    NEXTCLOUD_PROVISIONING_BASE_URL="https://cloud.example.com",
)
class SourceDataFileshareRedirectTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="fileshare-staff",
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
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
        )
        self.project = ProjectRegistration.objects.create(
            number=8101,
            type=self.product,
            name="Файлообменник",
            year=2026,
        )

    def _files_url(self, path):
        return f"https://cloud.example.com/apps/files/files?dir={quote(path, safe='/')}"

    def test_panel_points_fileshare_button_to_redirect_endpoint(self):
        response = self.client.get(reverse("checklists_app:panel_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("checklists_app:source_data_fileshare"))
        self.assertContains(response, 'data-fileshare-url=')
        self.assertNotContains(response, "data-yadisk-url")
        self.assertNotContains(response, "/apps/user_oidc/login/1")

    def test_redirects_to_created_source_data_workspace(self):
        disk_path = (
            "/Corporate Root/03 Проекты/2026/"
            f"{self.project.short_uid} DD Файлообменник/"
            "05 Исходные данные/01 Запросы"
        )
        SourceDataWorkspace.objects.create(project=self.project, disk_path=disk_path, created_by=self.user)
        SourceDataTargetFolder.objects.create(user=self.user, folder_name="05 Исходные данные")

        response = self.client.get(
            reverse("checklists_app:source_data_fileshare"),
            {"project_uid": self.project.short_uid},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self._files_url(disk_path))

    def test_uses_project_workspace_plus_target_folder_when_source_data_is_missing(self):
        ProjectWorkspace.objects.create(
            project=self.project,
            disk_path="/Corporate Root/03 Проекты/2026/447500RU TDD Тест 5",
            created_by=self.user,
        )
        SourceDataTargetFolder.objects.create(
            user=self.user,
            folder_name="05 Исходные данные/01 Запросы",
        )
        expected_path = (
            "/Corporate Root/03 Проекты/2026/447500RU TDD Тест 5/"
            "05 Исходные данные/01 Запросы"
        )

        response = self.client.get(
            reverse("checklists_app:source_data_fileshare"),
            {"project_uid": self.project.short_uid},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self._files_url(expected_path))

    def test_computes_target_folder_from_settings_when_workspace_is_missing(self):
        SourceDataTargetFolder.objects.create(
            user=self.user,
            folder_name="05 Исходные данные/01 Запросы",
        )
        expected_path = (
            "/Corporate Root/03 Проекты/2026/"
            f"{self.project.short_uid} DD Файлообменник/"
            "05 Исходные данные/01 Запросы"
        )

        response = self.client.get(
            reverse("checklists_app:source_data_fileshare"),
            {"project_uid": self.project.short_uid},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self._files_url(expected_path))

    def test_uses_default_source_data_folder_without_user_setting(self):
        expected_path = (
            "/Corporate Root/03 Проекты/2026/"
            f"{self.project.short_uid} DD Файлообменник/"
            "05 Исходные данные"
        )

        response = self.client.get(
            reverse("checklists_app:source_data_fileshare"),
            {"project_uid": self.project.short_uid},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self._files_url(expected_path))

    def test_rejects_non_staff_user(self):
        outsider = get_user_model().objects.create_user(
            username="fileshare-guest",
            password="secret",
            is_staff=False,
        )
        self.client.force_login(outsider)

        response = self.client.get(
            reverse("checklists_app:source_data_fileshare"),
            {"project_uid": self.project.short_uid},
        )

        self.assertEqual(response.status_code, 403)

    def test_requires_project(self):
        response = self.client.get(reverse("checklists_app:source_data_fileshare"))

        self.assertEqual(response.status_code, 400)

    def test_redirects_to_viewer_share_path_without_granting_new_access(self):
        from unittest.mock import Mock, patch

        from nextcloud_app.models import NextcloudUserLink

        self.user.email = "fileshare-staff@example.com"
        self.user.save(update_fields=["email"])
        NextcloudUserLink.objects.create(
            user=self.user,
            nextcloud_user_id="ncstaff-fileshare",
            nextcloud_username="ncstaff-fileshare",
            nextcloud_email=self.user.email,
        )
        project_path = "/Corporate Root/03 Проекты/2026/447500RU TDD Тест 5"
        ProjectWorkspace.objects.create(
            project=self.project,
            disk_path=project_path,
            created_by=self.user,
        )
        SourceDataTargetFolder.objects.create(user=self.user, folder_name="05 Исходные данные")
        share = Mock(
            target_path="/447500RU TDD Тест 5",
        )

        with patch("nextcloud_app.workspace.NextcloudApiClient") as client_cls:
            client = client_cls.return_value
            client.base_url = "https://cloud.example.com"
            client.is_configured = True
            client.username = "cloud-admin"
            client.build_files_url.side_effect = (
                lambda path: f"https://cloud.example.com/apps/files/files?dir={quote(path, safe='/')}"
            )
            client.list_user_shares.return_value = {project_path: share}

            response = self.client.get(
                reverse("checklists_app:source_data_fileshare"),
                {"project_uid": self.project.short_uid},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            self._files_url("/447500RU TDD Тест 5/05 Исходные данные"),
        )
        client.ensure_user_share.assert_not_called()


class ChecklistSortParseTests(TestCase):
    def test_compact_id_only_json_row_is_parsed(self):
        from checklists_app.sort_parse import parse_json_proposals

        rows = parse_json_proposals(
            '[{"id":"k-0123456789ab","dest":"dest/01 A/CODE-01 X",'
            '"confidence":"высокая","action":"move"}]'
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kit_id"], "k-0123456789ab")
        self.assertEqual(rows[0]["kit_path"], "")

    def test_section_children_without_match_become_review_rows(self):
        from types import SimpleNamespace

        from checklists_app.sort_service import (
            _add_request_name_rows,
            _add_section_review_rows,
            _kit_matches_section_label,
            _kit_under_section_label,
        )

        section = SimpleNamespace(code="GEO", short_name_ru="Геология", name_ru="")
        self.assertTrue(
            _kit_matches_section_label(
                {"kit_path": "03 GEO Геология"},
                section,
            )
        )
        self.assertTrue(
            _kit_under_section_label(
                {"kit_path": "Геология/Неопределенный комплект"},
                section,
            )
        )
        rows = _add_section_review_rows(
            [],
            [
                {
                    "kit_path": "Геология/Неопределенный комплект",
                    "file_count": 3,
                },
                {
                    "kit_path": "Другой раздел/Комплект",
                    "file_count": 2,
                },
            ],
            section,
            "03 GEO Геология",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["dest_path"], "dest/03 GEO Геология")
        self.assertEqual(rows[0]["action"], "review")
        exact_rows = _add_request_name_rows(
            [],
            [{
                "kit_path": "Смежная папка/1",
                "file_count": 2,
                "samples": ["Календарь работ.xlsx"],
                "text_excerpts": [],
            }],
            [{
                "folder": "SEC-01 Календарь лицензий",
                "request_name": "Календарь лицензий",
                "quote": "Актуальный календарный план",
            }],
            "01 SEC Раздел",
        )
        self.assertEqual(exact_rows[0]["confidence"], "высокая")
        self.assertEqual(exact_rows[0]["action"], "move")

    def test_kit_key_normalizes_unicode_composition(self):
        from checklists_app.sort_parse import _kit_key

        self.assertEqual(
            _kit_key("Охрана окружающей среды"),
            _kit_key("Охрана окружающей среды"),
        )

    def test_dedupe_rows_prefers_classified_destination(self):
        from checklists_app.sort_validate import dedupe_rows

        rows = dedupe_rows([
            {"kit_path": "A.pdf", "action": "review", "position": 1},
            {"kit_path": "A.pdf", "action": "move", "position": 2},
        ])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["action"], "move")
        self.assertEqual(rows[0]["position"], 1)

    def test_prefers_json_block(self):
        from checklists_app.sort_parse import parse_sort_response

        text = """
| комплект | файлов | папка dest | наименование запроса | цитата | уверенность | действие |
|---|---|---|---|---|---|---|
| Декларация.pdf | 1 | dest/old | Старое | цитата | высокая | move |

```json
[{"kit":"Декларация.pdf","files":1,"dest":"dest/07 TSF/TSF-05","name":"Документы по безопасности","quote":"Декларация безопасности ГТС","confidence":"высокая","action":"move"}]
```
"""
        rows = parse_sort_response(text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kit_path"], "Декларация.pdf")
        self.assertEqual(rows[0]["dest_path"], "dest/07 TSF/TSF-05")
        self.assertEqual(rows[0]["action"], "move")
        self.assertEqual(rows[0]["file_count"], 1)

    def test_file_count_ignores_byte_sizes_and_cadastral_digits(self):
        from checklists_app.sort_parse import parse_sort_response

        text = """
```json
[
  {"kit":"ЕГРН/41 09 0010115 401.zip","files":3221225472,"dest":"dest/06 LGL Право/LGL-16 ЕГРН","name":"ЕГРН","quote":"выписки","confidence":"высокая","action":"move"},
  {"kit":"ЕГРН/второй.zip","files":"41 09 0010115 401.zip","dest":"dest/06 LGL Право/LGL-16 ЕГРН","name":"ЕГРН","quote":"выписки","confidence":"средняя","action":"review"},
  {"kit":"Устав/BGK_Ustav.pdf","files":"12 файлов","dest":"dest/06 LGL Право/LGL-05 Устав","name":"Устав","quote":"устав","confidence":"высокая","action":"move"}
]
```
"""
        rows = parse_sort_response(text)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["file_count"], 1)
        self.assertEqual(rows[1]["file_count"], 41)
        self.assertEqual(rows[2]["file_count"], 12)
        self.assertTrue(all(row["file_count"] <= 2147483647 for row in rows))

    def test_file_count_from_name_list_does_not_concatenate_license_numbers(self):
        from checklists_app.sort_parse import parse_sort_response

        text = """
```json
[
  {
    "kit": "K1",
    "files": [
      "ПТР 005328 ТЭ",
      "ПТР 005329 ТЭ",
      "ПТР 007246 БП",
      "ПТР 007247 БП",
      "ПТР 009464 ТР",
      "ПТР 014702 ТП",
      "ПТР 016057 ВЭ",
      "ПТР 019156 ТР",
      "ПТР 026086 ТР",
      "ПТР 10606 БЭ"
    ],
    "dest": "LGL-01 Лицензии на недра",
    "name": "Лицензии на недра",
    "quote": "Лицензии на недропользование",
    "confidence": "high",
    "action": "move"
  },
  {
    "kit": "K16",
    "files": ["Empty"],
    "dest": "LGL-03 Бизнес-планы",
    "name": "",
    "quote": "",
    "confidence": "review",
    "action": "review"
  }
]
```
"""
        rows = parse_sort_response(text)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["kit_path"], "LGL-01 Лицензии на недра")
        self.assertEqual(rows[0]["file_count"], 10)
        self.assertEqual(rows[1]["kit_path"], "LGL-03 Бизнес-планы")
        self.assertEqual(rows[1]["file_count"], 0)
        self.assertTrue(all(row["file_count"] <= 2147483647 for row in rows))

    def test_dest_leaf_name_strips_workspace_prefix(self):
        from checklists_app.sort_parse import dest_leaf_name

        self.assertEqual(
            dest_leaf_name(
                "/Users/sergei/PycharmProjects/ai_app/deploy/dsh/data/sort-runs/8/dest/02 LGL Право/LGL-01 Лицензии на недра"
            ),
            "LGL-01 Лицензии на недра",
        )
        self.assertEqual(
            dest_leaf_name("dest/02 LGL Право/LGL-01 Лицензии на недра"),
            "LGL-01 Лицензии на недра",
        )
        self.assertEqual(dest_leaf_name(""), "")

    def test_decorate_dest_rows_groups_and_follows_checklist_order(self):
        from checklists_app.sort_parse import decorate_dest_rows

        rows = decorate_dest_rows(
            [
                {
                    "kit_path": "ООС/Лицензия.pdf",
                    "dest_path": "/tmp/sort-runs/8/dest/02 LGL Право/LGL-01 Лицензии на недра",
                    "request_name": "Лицензии",
                    "quote": "лицензии на недра",
                    "file_count": 1,
                    "confidence": "высокая",
                    "action": "move",
                },
                {
                    "kit_path": "Хвостохранилище/ПД/ИРД/Лицензии/",
                    "dest_path": "dest/02 LGL Право/LGL-01 Лицензии на недра",
                    "request_name": "Лицензии",
                    "quote": "лицензии на недра",
                    "file_count": 4,
                    "confidence": "высокая",
                    "action": "move",
                },
                {
                    "kit_path": "ООС/ЗУ.pdf",
                    "dest_path": "dest/02 LGL Право/LGL-17 Правоустанавливающая документация на ЗУ",
                    "request_name": "ЗУ",
                    "quote": "аренда ЗУ",
                    "file_count": 1,
                    "confidence": "высокая",
                    "action": "move",
                },
            ],
            [
                "LGL-01 Лицензии на недра",
                "LGL-02 Договоры",
                "LGL-17 Правоустанавливающая документация на ЗУ",
            ],
        )
        self.assertEqual(
            [row["dest_folder"] for row in rows],
            [
                "LGL-01 Лицензии на недра",
                "LGL-01 Лицензии на недра",
                "LGL-02 Договоры",
                "LGL-17 Правоустанавливающая документация на ЗУ",
            ],
        )
        self.assertEqual(
            [row["kit_path"] for row in rows],
            [
                "ООС/Лицензия.pdf",
                "Хвостохранилище/ПД/ИРД/Лицензии/",
                "",
                "ООС/ЗУ.pdf",
            ],
        )
        self.assertEqual(rows[2]["action"], "")
        self.assertTrue(rows[2]["placeholder"])
        self.assertEqual(rows[0]["dest_order"], rows[1]["dest_order"])
        self.assertLess(rows[0]["dest_order"], rows[2]["dest_order"])
        self.assertLess(rows[2]["dest_order"], rows[3]["dest_order"])

    def test_medium_confidence_cannot_move(self):
        from checklists_app.sort_parse import parse_sort_response

        text = """
```json
[{"kit":"Акт.pdf","files":1,"dest":"dest/02 LGL Право/LGL-01 Лицензии на недра","name":"Лицензии","quote":"лицензии на недра","confidence":"средняя","action":"move"}]
```
"""
        rows = parse_sort_response(text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["action"], "review")
        self.assertEqual(rows[0]["dest_path"], "dest/02 LGL Право/LGL-01 Лицензии на недра")

    def test_section_level_dest_is_review_even_if_high(self):
        from checklists_app.sort_parse import parse_sort_response

        text = """
```json
[{"kit":"ООС/Договор аренды.pdf","files":1,"dest":"dest/02 LGL Право","name":"","quote":"","confidence":"высокая","action":"move"}]
```
"""
        rows = parse_sort_response(text)
        self.assertEqual(rows[0]["action"], "review")

    def test_unmatched_dest_rows_attach_to_section_folder(self):
        from checklists_app.sort_parse import decorate_dest_rows

        rows = decorate_dest_rows(
            [
                {
                    "kit_path": "ООС/неясный.pdf",
                    "dest_path": "dest/02 LGL Право",
                    "confidence": "низкая",
                    "action": "review",
                    "request_name": "",
                    "quote": "",
                    "file_count": 1,
                }
            ],
            ["LGL-01 Лицензии на недра"],
            section_folder="LGL Право",
        )
        self.assertEqual(rows[0]["dest_folder"], "LGL-01 Лицензии на недра")
        self.assertEqual(rows[0]["kit_path"], "")
        self.assertEqual(rows[1]["dest_folder"], "LGL Право")
        self.assertEqual(rows[1]["kit_path"], "ООС/неясный.pdf")
        self.assertEqual(rows[1]["action"], "review")

    def test_json_missing_review_rows_are_filled_from_table(self):
        from checklists_app.sort_parse import parse_sort_response

        text = """
| комплект (путь относительно inbox) | файлов | папка dest (точный путь) | наименование запроса | цитата из requests.md | уверенность | действие |
|---|---|---|---|---|---|---|
| 4/ | 3 | dest/03 GEO Геология/GEO-01 Госотчетность по запасам | Госотчетность по запасам | Формы 2-гр, 5-гр | высокая | move |
| QAQC/ | 3 | — | — | — | низкая | review |

```json
[{"kit":"4/","files":3,"dest":"dest/03 GEO Геология/GEO-01 Госотчетность по запасам","name":"Госотчетность по запасам","quote":"Формы 2-гр, 5-гр","confidence":"высокая","action":"move"}]
```
"""
        rows = parse_sort_response(text)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["kit_path"], "4/")
        self.assertEqual(rows[0]["action"], "move")
        self.assertEqual(rows[1]["kit_path"], "QAQC/")
        self.assertEqual(rows[1]["action"], "review")
        self.assertEqual(rows[1]["dest_path"], "")

    def test_parses_markdown_table(self):
        from checklists_app.sort_parse import parse_sort_response

        text = """
| комплект (путь относительно inbox) | файлов | папка dest (точный путь) | наименование запроса | цитата из requests.md | уверенность | действие |
|---|---|---|---|---|---|---|
| Наполнение.xlsx | 1 | dest/07 TSF Хвостохранилище/TSF-04 | Прогнозная емкость ХХ | динамика заполнения | высокая | move |
| Проект мониторинга.pdf | 1 | _needs_review/ | — | нет якоря | низкая | review |
"""
        rows = parse_sort_response(text)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["dest_path"], "dest/07 TSF Хвостохранилище/TSF-04")
        self.assertEqual(rows[1]["action"], "review")


class ChecklistSortAccessTests(TestCase):
    def setUp(self):
        super().setUp()
        from django.contrib.auth.models import Group

        from policy_app.models import ADMIN_GROUP

        User = get_user_model()
        self.admin_group, _ = Group.objects.get_or_create(name=ADMIN_GROUP)
        self.admin = User.objects.create_user(
            username="chk-sort-admin",
            password="secret",
            is_staff=True,
        )
        self.admin.groups.add(self.admin_group)
        Employee.objects.create(user=self.admin, role=ADMIN_GROUP)
        self.staff = User.objects.create_user(
            username="chk-sort-staff",
            password="secret",
            is_staff=True,
        )
        Employee.objects.create(user=self.staff, role=EXPERT_GROUP)
        self.product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
        )
        self.project = ProjectRegistration.objects.create(
            number=6101,
            type=self.product,
            name="Сортировка",
            year=2026,
        )
        self.section = TypicalSection.objects.create(
            product=self.product,
            code="TSF",
            short_name="TSF",
            short_name_ru="Хвостохранилище",
            name_en="TSF",
            name_ru="Хвостохранилище",
            accounting_type="Раздел",
            position=1,
        )
        Performer.objects.create(
            registration=self.project,
            asset_name="Asset A",
            executor="Иванов Иван Иванович",
            typical_section=self.section,
        )
        ChecklistItem.objects.create(
            project=self.project,
            section=self.section,
            code="TSF",
            number=5,
            short_name="Документы по безопасности",
            name="Декларация безопасности ГТС хвостохранилища",
            position=1,
        )
        self._sort_workspace = tempfile.TemporaryDirectory()
        self._sort_workspace_settings = override_settings(
            DSH_SORT_WORKSPACE=self._sort_workspace.name,
        )
        self._sort_workspace_settings.enable()

    def tearDown(self):
        self._sort_workspace_settings.disable()
        self._sort_workspace.cleanup()
        super().tearDown()

    @staticmethod
    def _cloud_materializer(*relative_paths):
        def materialize(inbox_dir, user, source_folder, section_label, **kwargs):
            root = Path(inbox_dir) / section_label
            root.mkdir(parents=True, exist_ok=True)
            for raw in relative_paths:
                value = str(raw)
                target = root / value.rstrip("/")
                if value.endswith("/"):
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text("stub", encoding="utf-8")
            return len(relative_paths)

        return materialize

    def test_non_admin_home_keeps_single_checklists_page(self):
        self.client.force_login(self.staff)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertNotIn("checklists-second-sidebar-list", content)
        self.assertNotIn("Чек-листы: Сортировка", content)
        self.assertIn('href="#checklists"', content)

    def test_admin_home_shows_checklists_subsections(self):
        self.client.force_login(self.admin)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("checklists-second-sidebar-list", content)
        self.assertIn("Чек-листы: Статусы", content)
        self.assertIn("Чек-листы: Сортировка", content)

    def test_sort_urls_forbidden_for_non_admin(self):
        self.client.force_login(self.staff)
        panel = self.client.get(reverse("checklists_app:sort_panel_partial"))
        start = self.client.post(reverse("checklists_app:sort_start"), {"project_uid": self.project.short_uid})
        status = self.client.get(reverse("checklists_app:sort_status"))
        verify = self.client.post(reverse("checklists_app:sort_verify"), {"proposal_id": "1"})
        self.assertEqual(panel.status_code, 403)
        self.assertEqual(start.status_code, 403)
        self.assertEqual(status.status_code, 403)
        self.assertEqual(verify.status_code, 403)

    def test_admin_sort_panel_renders_chooser(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("checklists_app:sort_panel_partial"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Выбор рабочей области")
        self.assertContains(response, "Все разделы")
        self.assertContains(response, "Распределить")
        self.assertContains(response, 'colspan="6"')
        self.assertContains(response, "chk-sort-action-cell")
        self.assertContains(response, "chk-sort-proposal-btn")
        self.assertContains(response, "Переместить")
        self.assertContains(response, "Проверить")
        self.assertContains(response, "Подтвердить")
        self.assertContains(response, 'data-sort-proposal-action="review"')
        self.assertContains(response, 'data-sort-proposal-action="confirm"')
        self.assertContains(response, "data-verify-url")
        self.assertContains(response, "csrfmiddlewaretoken")
        self.assertContains(response, "__chkSortOnVerifyButton")
        self.assertContains(response, "anyVerifying(run)")
        self.assertContains(response, "Предлагаемый dest")
        self.assertContains(response, "chk-sort-proposal-row")
        self.assertContains(response, "Краткое наименование")
        self.assertContains(response, "Наименование запроса")
        self.assertContains(response, "Предлагаемые перемещения")
        self.assertContains(response, "Локальная папка")
        self.assertNotContains(response, "Запустить сортировку раздела")

    def test_local_inbox_outside_allowlist_is_rejected(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("checklists_app:sort_start"),
            {
                "project_uid": self.project.short_uid,
                "section": str(self.section.id),
                "asset": "Asset A",
                "source_kind": "local",
                "local_inbox_path": "/etc",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("разрешённых", response.json()["error"])

    @override_settings(
        DSH_SORT_INLINE=True,
        DSH_SORT_ALLOW_LOCAL_INBOX=True,
        DSH_HEADLESS_CMD="dsh --profile headless",
    )
    def test_local_inbox_scans_all_top_level_folders_for_dest_section(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from checklists_app.models import ChecklistSortRun

        self.client.force_login(self.admin)
        legal = TypicalSection.objects.create(
            product=self.product,
            code="LGL",
            short_name="LGL",
            short_name_ru="Право",
            name_en="Legal",
            name_ru="Право",
            accounting_type="Раздел",
            position=2,
        )
        Performer.objects.create(
            registration=self.project,
            asset_name="Asset A",
            executor="Петров Петр Петрович",
            typical_section=legal,
        )
        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp) / "inbox"
            (inbox / "Хвостохранилище" / "ПД" / "ИРД").mkdir(parents=True)
            (inbox / "Геология").mkdir()
            fake_output = """
```json
[
  {"kit":"Хвостохранилище/ПД/ИРД/Лицензия.pdf","files":1,"dest":"dest/02 LGL Право/LGL-01 Лицензии","name":"Лицензии","quote":"лицензии на недра","confidence":"высокая","action":"move"},
  {"kit":"Геология","files":0,"dest":"","name":"","quote":"","confidence":"","action":"ignore"}
]
```
"""
            captured = {}

            def _fake_headless(prompt, cwd=None, **kwargs):
                captured["prompt"] = prompt
                captured["cwd"] = cwd
                return fake_output

            with override_settings(DSH_SORT_LOCAL_ROOTS=(tmp,)), patch(
                "checklists_app.sort_service.run_headless", side_effect=_fake_headless
            ):
                response = self.client.post(
                    reverse("checklists_app:sort_start"),
                    {
                        "project_uid": self.project.short_uid,
                        "section": str(legal.id),
                        "asset": "Asset A",
                        "source_kind": "local",
                        "local_inbox_path": str(inbox),
                    },
                )
            self.assertEqual(response.status_code, 200, response.content)
            payload = response.json()["run"]
            workspace_inbox = Path(ChecklistSortRun.objects.get(pk=payload["id"]).workspace_path) / "inbox"
            names = {child.name for child in workspace_inbox.iterdir() if not child.name.startswith(".")}
        self.assertEqual(payload["status"], "done")
        self.assertEqual(payload["source_kind"], "local")
        self.assertEqual(payload["inbox_section_name"], "LGL Право")
        self.assertIn("Раздел dest уже выбран: LGL Право", captured["prompt"])
        self.assertIn("Не спрашивай, какой раздел обрабатывать", captured["prompt"])
        self.assertIn("inbox-inventory.json", captured["prompt"])
        self.assertIn("<chunk-json>", captured["prompt"])
        self.assertIn("chunks/sort-chunk-", captured["prompt"])
        self.assertIn("Не вызывай ls", captured["prompt"])
        self.assertNotIn("Начни с inbox/Право", captured["prompt"])
        self.assertEqual(names, {"Хвостохранилище", "Геология"})

    @override_settings(
        DSH_SORT_INLINE=True,
        DSH_SORT_ALLOW_LOCAL_INBOX=True,
        DSH_HEADLESS_CMD="dsh --profile headless",
    )
    def test_local_inbox_uses_whole_dump_not_named_section_folder(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        self.client.force_login(self.admin)
        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp) / "inbox"
            section_dir = inbox / "Хвостохранилище"
            section_dir.mkdir(parents=True)
            (section_dir / "Декларация.pdf").write_text("stub", encoding="utf-8")
            fake_output = """
```json
[{"kit":"Хвостохранилище/Декларация.pdf","files":1,"dest":"dest/01 TSF Хвостохранилище/TSF-05 Документы по безопасности","name":"Документы по безопасности","quote":"Декларация безопасности ГТС хвостохранилища","confidence":"высокая","action":"move"}]
```
"""
            with override_settings(DSH_SORT_LOCAL_ROOTS=(tmp,)), patch(
                "checklists_app.sort_service.run_headless", return_value=fake_output
            ):
                response = self.client.post(
                    reverse("checklists_app:sort_start"),
                    {
                        "project_uid": self.project.short_uid,
                        "section": str(self.section.id),
                        "asset": "Asset A",
                        "source_kind": "local",
                        "local_inbox_path": str(inbox),
                    },
                )
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()["run"]
        self.assertEqual(payload["status"], "done")
        self.assertEqual(payload["source_kind"], "local")
        self.assertEqual(payload["inbox_section_name"], "TSF Хвостохранилище")
        self.assertEqual(payload["proposals"][0]["kit_path"], "Хвостохранилище/Декларация.pdf")

    @override_settings(DSH_SORT_INLINE=True, DSH_HEADLESS_CMD="dsh --profile headless")
    def test_admin_can_start_sort_and_see_parsed_rows(self):
        from unittest.mock import patch

        self.client.force_login(self.admin)
        fake_output = """
```json
[{"kit":"Декларация.pdf","files":1,"dest":"dest/01 TSF Хвостохранилище/TSF-05 Документы по безопасности","name":"Документы по безопасности","quote":"Декларация безопасности ГТС хвостохранилища","confidence":"высокая","action":"move"}]
```
"""
        with patch(
            "checklists_app.sort_service.materialize_inbox_tree",
            side_effect=self._cloud_materializer("Декларация.pdf"),
        ), patch("checklists_app.sort_service.run_headless", return_value=fake_output):
            response = self.client.post(
                reverse("checklists_app:sort_start"),
                {
                    "project_uid": self.project.short_uid,
                    "section": str(self.section.id),
                    "asset": "Asset A",
                },
            )
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()["run"]
        self.assertEqual(payload["status"], "done")
        self.assertEqual(len(payload["proposals"]), 1)
        self.assertEqual(payload["proposals"][0]["kit_path"], "Декларация.pdf")
        self.assertTrue(payload["proposals"][0]["id"])
        self.assertEqual(payload["proposals"][0]["proposal_id"], payload["proposals"][0]["id"])
        self.assertFalse(payload["proposals"][0]["verifying"])
        self.assertEqual(payload["proposals"][0]["action"], "move")
        self.assertEqual(
            payload["proposals"][0]["dest_folder"],
            "TSF-05 Документы по безопасности",
        )
        self.assertNotIn("sort-runs", payload["proposals"][0]["dest_folder"])

        status = self.client.get(
            reverse("checklists_app:sort_status"),
            {
                "project_uid": self.project.short_uid,
                "section": str(self.section.id),
                "asset": "Asset A",
            },
        )
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["run"]["id"], payload["id"])

        grouped = self.client.get(
            reverse("checklists_app:sort_status"),
            {
                "project_uid": self.project.short_uid,
                "section": "all",
                "asset": "Asset A",
            },
        )
        self.assertEqual(grouped.status_code, 200)
        groups = grouped.json()["groups"]
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["section_id"], self.section.id)
        self.assertEqual(groups[0]["run"]["id"], payload["id"])
        self.assertEqual(groups[0]["run"]["proposals"][0]["request_name"], "Документы по безопасности")

    @override_settings(DSH_SORT_INLINE=True, DSH_HEADLESS_CMD="dsh --profile headless")
    def test_sort_payload_orders_and_groups_dest_like_statuses(self):
        from unittest.mock import patch

        ChecklistItem.objects.create(
            project=self.project,
            section=self.section,
            code="TSF",
            number=6,
            short_name="Годовой отчет ГТС",
            name="Годовой отчет",
            position=2,
        )
        self.client.force_login(self.admin)
        fake_output = """
```json
[
  {"kit":"Отчет.pdf","files":1,"dest":"/tmp/sort-runs/8/dest/01 TSF Хвостохранилище/TSF-06 Годовой отчет ГТС","name":"Годовой отчет ГТС","quote":"годовой отчет","confidence":"высокая","action":"move"},
  {"kit":"Хвостохранилище/ПД/ИРД/Лицензии/","files":2,"dest":"dest/01 TSF Хвостохранилище/TSF-05 Документы по безопасности","name":"Документы по безопасности","quote":"Декларация","confidence":"высокая","action":"move"},
  {"kit":"Декларация.pdf","files":1,"dest":"dest/01 TSF Хвостохранилище/TSF-05 Документы по безопасности","name":"Документы по безопасности","quote":"Декларация","confidence":"высокая","action":"move"}
]
```
"""
        with patch(
            "checklists_app.sort_service.materialize_inbox_tree",
            side_effect=self._cloud_materializer(
                "Отчет.pdf",
                "Хвостохранилище/ПД/ИРД/Лицензии/",
                "Декларация.pdf",
            ),
        ), patch("checklists_app.sort_service.run_headless", return_value=fake_output):
            response = self.client.post(
                reverse("checklists_app:sort_start"),
                {
                    "project_uid": self.project.short_uid,
                    "section": str(self.section.id),
                    "asset": "Asset A",
                },
            )
        self.assertEqual(response.status_code, 200, response.content)
        rows = response.json()["run"]["proposals"]
        self.assertEqual(
            [row["dest_folder"] for row in rows],
            [
                "TSF-05 Документы по безопасности",
                "TSF-05 Документы по безопасности",
                "TSF-06 Годовой отчет ГТС",
            ],
        )
        self.assertEqual(
            [row["kit_path"] for row in rows],
            [
                "Хвостохранилище/ПД/ИРД/Лицензии/",
                "Декларация.pdf",
                "Отчет.pdf",
            ],
        )

    @override_settings(DSH_SORT_INLINE=True, DSH_HEADLESS_CMD="dsh --profile headless")
    def test_sort_payload_includes_dest_items_without_inbox(self):
        from unittest.mock import patch

        ChecklistItem.objects.create(
            project=self.project,
            section=self.section,
            code="TSF",
            number=6,
            short_name="Годовой отчет ГТС",
            name="Годовой отчет",
            position=2,
        )
        self.client.force_login(self.admin)
        fake_output = """
```json
[{"kit":"Декларация.pdf","files":1,"dest":"dest/01 TSF Хвостохранилище/TSF-05 Документы по безопасности","name":"Документы по безопасности","quote":"Декларация","confidence":"высокая","action":"move"}]
```
"""
        with patch(
            "checklists_app.sort_service.materialize_inbox_tree",
            side_effect=self._cloud_materializer("Декларация.pdf"),
        ), patch("checklists_app.sort_service.run_headless", return_value=fake_output):
            response = self.client.post(
                reverse("checklists_app:sort_start"),
                {
                    "project_uid": self.project.short_uid,
                    "section": str(self.section.id),
                    "asset": "Asset A",
                },
            )
        self.assertEqual(response.status_code, 200, response.content)
        rows = response.json()["run"]["proposals"]
        self.assertEqual(
            [row["dest_folder"] for row in rows],
            [
                "TSF-05 Документы по безопасности",
                "TSF-06 Годовой отчет ГТС",
            ],
        )
        self.assertEqual(rows[0]["kit_path"], "Декларация.pdf")
        self.assertEqual(rows[0]["action"], "move")
        self.assertEqual(rows[1]["kit_path"], "")
        self.assertEqual(rows[1]["action"], "")
        self.assertEqual(rows[1]["request_name"], "Годовой отчет ГТС")
        self.assertEqual(rows[1]["quote"], "Годовой отчет")
        self.assertTrue(rows[1]["placeholder"])

    def test_sort_status_all_sections_returns_groups_without_run(self):
        self.client.force_login(self.admin)
        legal = TypicalSection.objects.create(
            product=self.product,
            code="LGL",
            short_name="LGL",
            short_name_ru="Право",
            name_en="Legal",
            name_ru="Право",
            accounting_type="Раздел",
            position=2,
        )
        Performer.objects.create(
            registration=self.project,
            asset_name="Asset A",
            executor="Петров Петр Петрович",
            typical_section=legal,
        )
        response = self.client.get(
            reverse("checklists_app:sort_status"),
            {
                "project_uid": self.project.short_uid,
                "section": "all",
                "asset": "Asset A",
            },
        )
        self.assertEqual(response.status_code, 200)
        groups = response.json()["groups"]
        self.assertEqual([row["section_id"] for row in groups], [self.section.id, legal.id])
        self.assertTrue(all(row["run"] is None for row in groups))

    def test_sort_start_rejects_all_sections(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("checklists_app:sort_start"),
            {
                "project_uid": self.project.short_uid,
                "section": "all",
                "asset": "Asset A",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("раздел", response.json()["error"].lower())

    def test_requests_markdown_uses_exact_dest_section_folder(self):
        from checklists_app.sort_workspace import build_requests_markdown, section_folder_name

        item = ChecklistItem.objects.get(project=self.project, section=self.section)
        expected = f"{section_folder_name(self.project, self.section)}/TSF-05 Документы по безопасности"
        self.assertIn(f"| {expected} |", build_requests_markdown(self.project))

    @override_settings(DSH_SORT_INLINE=False, DSH_HEADLESS_CMD="dsh --profile headless")
    def test_non_inline_sort_is_left_for_durable_worker(self):
        from unittest.mock import patch

        self.client.force_login(self.admin)
        with patch("checklists_app.sort_service.run_headless") as headless:
            response = self.client.post(
                reverse("checklists_app:sort_start"),
                {
                    "project_uid": self.project.short_uid,
                    "section": str(self.section.id),
                    "asset": "Asset A",
                },
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["run"]["status"], ChecklistSortRun.Status.QUEUED)
        headless.assert_not_called()

    @override_settings(DSH_HEADLESS_TIMEOUT=10)
    def test_stale_running_sort_no_longer_blocks_section(self):
        from datetime import timedelta

        from checklists_app.sort_service import active_run_for

        run = ChecklistSortRun.objects.create(
            project=self.project,
            section=self.section,
            asset_name="Asset A",
            started_by=self.admin,
            status=ChecklistSortRun.Status.RUNNING,
            started_at=timezone.now() - timedelta(minutes=30),
        )

        self.assertIsNone(active_run_for(self.project, self.section, "Asset A"))
        run.refresh_from_db()
        self.assertEqual(run.status, ChecklistSortRun.Status.ERROR)
        self.assertIn("не завершилась", run.error_message)

    def test_active_worker_keeps_expired_run_recoverable(self):
        from datetime import timedelta

        from checklists_app.models import ChecklistSortWorkerState
        from checklists_app.sort_service import active_run_for

        ChecklistSortWorkerState.objects.create(
            key="default",
            worker_id="worker",
            started_at=timezone.now(),
            heartbeat_at=timezone.now(),
        )
        run = ChecklistSortRun.objects.create(
            project=self.project,
            section=self.section,
            asset_name="Asset A",
            started_by=self.admin,
            status=ChecklistSortRun.Status.RUNNING,
            started_at=timezone.now() - timedelta(minutes=30),
            lease_expires_at=timezone.now() - timedelta(seconds=1),
            worker_id="old-worker",
        )
        self.assertEqual(
            active_run_for(self.project, self.section, "Asset A").id,
            run.id,
        )
        run.refresh_from_db()
        self.assertEqual(run.status, ChecklistSortRun.Status.RUNNING)

    @override_settings(DSH_HEADLESS_TIMEOUT=10)
    def test_status_poll_reclaims_stale_running_sort(self):
        from datetime import timedelta

        from checklists_app.sort_service import serialize_run

        run = ChecklistSortRun.objects.create(
            project=self.project,
            section=self.section,
            asset_name="Asset A",
            started_by=self.admin,
            status=ChecklistSortRun.Status.RUNNING,
            started_at=timezone.now() - timedelta(minutes=30),
        )
        payload = serialize_run(run)
        self.assertEqual(payload["status"], ChecklistSortRun.Status.ERROR)
        self.assertIn("не завершилась", payload["error_message"])

    @override_settings(
        DSH_SORT_INLINE=True,
        DSH_HEADLESS_CMD="dsh --profile headless",
    )
    def test_code_nn_inbox_kits_skip_dsh(self):
        from unittest.mock import patch

        from yandexdisk_app.workspace import _build_item_folder_name

        item = ChecklistItem.objects.get(project=self.project, section=self.section)
        kit_name = _build_item_folder_name(item)

        def _materialize(inbox_dir, user, source_folder, section_label, **kwargs):
            kit = Path(inbox_dir) / section_label / kit_name
            kit.mkdir(parents=True)
            (kit / "a.pdf").write_text("x", encoding="utf-8")

        self.client.force_login(self.admin)
        with patch(
            "checklists_app.sort_service.materialize_inbox_tree",
            side_effect=_materialize,
        ), patch("checklists_app.sort_service.run_headless") as headless:
            response = self.client.post(
                reverse("checklists_app:sort_start"),
                {
                    "project_uid": self.project.short_uid,
                    "section": str(self.section.id),
                    "asset": "Asset A",
                },
            )
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()["run"]
        self.assertEqual(payload["status"], "done")
        headless.assert_not_called()
        row = next(item for item in payload["proposals"] if item.get("kit_path"))
        self.assertIn(kit_name, row["kit_path"])
        self.assertEqual(row["action"], "move")
        self.assertEqual(row["confidence"], "высокая")

    @override_settings(DSH_SORT_INLINE=True, DSH_HEADLESS_CMD="dsh --profile headless")
    def test_code_only_name_is_sent_to_dsh(self):
        from unittest.mock import patch

        fake_output = """
```json
[{"kit":"TSF-05 Старое имя","files":1,"dest":"dest/01 TSF Хвостохранилище/TSF-05 Документы по безопасности","name":"Документы по безопасности","quote":"Декларация безопасности ГТС хвостохранилища","confidence":"высокая","action":"move"}]
```
"""
        self.client.force_login(self.admin)
        with patch(
            "checklists_app.sort_service.materialize_inbox_tree",
            side_effect=self._cloud_materializer(
                "TSF-05 Старое имя/a.pdf",
                "TSF-05 Старое имя/b.pdf",
            ),
        ), patch(
            "checklists_app.sort_service.run_headless",
            return_value=fake_output,
        ) as headless:
            response = self.client.post(
                reverse("checklists_app:sort_start"),
                {
                    "project_uid": self.project.short_uid,
                    "section": str(self.section.id),
                    "asset": "Asset A",
                },
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["run"]["status"], "done")
        self.assertEqual(headless.call_count, 1)

    @override_settings(DSH_SORT_INLINE=True, DSH_HEADLESS_CMD="dsh --profile headless")
    def test_empty_inventory_skips_dsh(self):
        from unittest.mock import patch

        self.client.force_login(self.admin)
        with patch("checklists_app.sort_service.run_headless") as headless:
            response = self.client.post(
                reverse("checklists_app:sort_start"),
                {
                    "project_uid": self.project.short_uid,
                    "section": str(self.section.id),
                    "asset": "Asset A",
                },
            )
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()["run"]
        self.assertEqual(payload["status"], "done")
        self.assertEqual(payload["progress"]["kits_total"], 0)
        headless.assert_not_called()

    @override_settings(
        DSH_SORT_INLINE=True,
        DSH_SORT_ALLOW_LOCAL_INBOX=True,
        DSH_HEADLESS_CMD="dsh --profile headless",
        DSH_SORT_CHUNK_SIZE=5,
        DSH_SORT_CHUNK_RETRIES=1,
    )
    def test_truncated_chunk_retries_then_splits(self):
        from unittest.mock import patch

        from core.dsh_run import DshRunError

        calls = []

        def _headless(prompt, cwd=None, **kwargs):
            calls.append(prompt)
            if len(calls) <= 2:
                raise DshRunError("Stream ended without finish_reason")
            payload = json.loads(
                prompt.split("<chunk-json>\n", 1)[1].split("\n</chunk-json>", 1)[0]
            )
            rows = [
                {
                    "kit": kit["kit_path"],
                    "files": kit["file_count"],
                    "dest": "dest/01 TSF Хвостохранилище/TSF-05 Документы по безопасности",
                    "name": "Документы по безопасности",
                    "quote": "Декларация безопасности ГТС хвостохранилища",
                    "confidence": "высокая",
                    "action": "move",
                }
                for kit in payload["kits"]
            ]
            return "```json\n" + json.dumps(rows, ensure_ascii=False) + "\n```"

        self.client.force_login(self.admin)
        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp) / "inbox"
            inbox.mkdir()
            for index in range(5):
                (inbox / f"Документ {index}.pdf").write_text("stub", encoding="utf-8")
            with override_settings(DSH_SORT_LOCAL_ROOTS=(tmp,)), patch(
                "checklists_app.sort_service.run_headless",
                side_effect=_headless,
            ):
                response = self.client.post(
                    reverse("checklists_app:sort_start"),
                    {
                        "project_uid": self.project.short_uid,
                        "section": str(self.section.id),
                        "asset": "Asset A",
                        "source_kind": "local",
                        "local_inbox_path": str(inbox),
                    },
                )
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()["run"]
        self.assertEqual(payload["status"], "done")
        self.assertEqual(len([row for row in payload["proposals"] if row.get("kit_path")]), 5)
        self.assertEqual(len(calls), 4)
        run = ChecklistSortRun.objects.get(pk=payload["id"])
        self.assertTrue(run.chunks.filter(status=ChecklistSortChunk.Status.SPLIT).exists())

    @override_settings(
        DSH_SORT_INLINE=True,
        DSH_SORT_ALLOW_LOCAL_INBOX=True,
        DSH_HEADLESS_CMD="dsh --profile headless",
    )
    def test_unknown_dest_is_persisted_as_review(self):
        from unittest.mock import patch

        fake_output = """
```json
[{"kit":"Неизвестный.pdf","files":9999999999,"dest":"dest/99 XXX/XXX-99 Выдумка","name":"Выдумка","quote":"нет","confidence":"высокая","action":"move"}]
```
"""
        self.client.force_login(self.admin)
        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp) / "inbox"
            inbox.mkdir()
            (inbox / "Неизвестный.pdf").write_text("stub", encoding="utf-8")
            with override_settings(DSH_SORT_LOCAL_ROOTS=(tmp,)), patch(
                "checklists_app.sort_service.run_headless",
                return_value=fake_output,
            ):
                response = self.client.post(
                    reverse("checklists_app:sort_start"),
                    {
                        "project_uid": self.project.short_uid,
                        "section": str(self.section.id),
                        "asset": "Asset A",
                        "source_kind": "local",
                        "local_inbox_path": str(inbox),
                    },
                )
        self.assertEqual(response.status_code, 200, response.content)
        row = ChecklistSortProposal.objects.get(run_id=response.json()["run"]["id"])
        self.assertEqual(row.action, "review")
        self.assertEqual(row.file_count, 1)
        self.assertEqual(row.dest_path, "dest/01 TSF Хвостохранилище")

    @override_settings(
        DSH_SORT_INLINE=True,
        DSH_SORT_ALLOW_LOCAL_INBOX=True,
        DSH_HEADLESS_CMD="dsh --profile headless",
        DSH_SORT_CHUNK_SIZE=12,
        DSH_SORT_MAX_PROPOSAL_FILES=1,
        DSH_SORT_MAX_REFINEMENT_DEPTH=4,
    )
    def test_broad_match_is_refined_before_publication(self):
        from unittest.mock import patch

        calls = []

        def _headless(prompt, cwd=None, **kwargs):
            payload = json.loads(
                prompt.split("<chunk-json>\n", 1)[1].split("\n</chunk-json>", 1)[0]
            )
            calls.append([kit["kit_path"] for kit in payload["kits"]])
            rows = [
                {
                    "id": kit["id"],
                    "kit": kit["kit_path"],
                    "files": kit["file_count"],
                    "dest": "dest/01 TSF Хвостохранилище/TSF-05 Документы по безопасности",
                    "name": "Документы по безопасности",
                    "quote": "Декларация безопасности ГТС хвостохранилища",
                    "confidence": "высокая",
                    "action": "move",
                }
                for kit in payload["kits"]
            ]
            return "```json\n" + json.dumps(rows, ensure_ascii=False) + "\n```"

        self.client.force_login(self.admin)
        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp) / "inbox"
            (inbox / "Геология" / "1").mkdir(parents=True)
            (inbox / "Геология" / "1" / "форма 2-гр.pdf").write_text("x", encoding="utf-8")
            (inbox / "Геология" / "2.pdf").write_text("x", encoding="utf-8")
            with override_settings(DSH_SORT_LOCAL_ROOTS=(tmp,)), patch(
                "checklists_app.sort_service.run_headless",
                side_effect=_headless,
            ):
                response = self.client.post(
                    reverse("checklists_app:sort_start"),
                    {
                        "project_uid": self.project.short_uid,
                        "section": str(self.section.id),
                        "asset": "Asset A",
                        "source_kind": "local",
                        "local_inbox_path": str(inbox),
                    },
                )
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()["run"]
        self.assertEqual(payload["status"], "done")
        paths = [
            row["kit_path"]
            for row in payload["proposals"]
            if row.get("kit_path")
        ]
        self.assertNotIn("Геология", paths)
        self.assertEqual(set(paths), {"Геология/1", "Геология/2.pdf"})
        self.assertEqual(len(calls), 2)

    @override_settings(
        DSH_SORT_INLINE=True,
        DSH_SORT_ALLOW_LOCAL_INBOX=True,
        DSH_HEADLESS_CMD="dsh --profile headless",
        DSH_SORT_FAST_FIRST_MAX_KITS=200,
    )
    def test_matching_section_folder_uses_one_fast_first_call_and_keeps_reviews(self):
        from unittest.mock import patch

        calls = []

        def _headless(prompt, cwd=None, **kwargs):
            payload = json.loads(
                prompt.split("<chunk-json>\n", 1)[1].split("\n</chunk-json>", 1)[0]
            )
            calls.append(payload)
            kit = next(
                kit for kit in payload["kits"]
                if kit["kit_path"].endswith("Декларация.pdf")
            )
            return "```json\n" + json.dumps([{
                "id": kit["id"],
                "dest": "dest/01 TSF Хвостохранилище/TSF-05 Документы по безопасности",
                "confidence": "высокая",
                "action": "move",
            }], ensure_ascii=False) + "\n```"

        self.client.force_login(self.admin)
        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp) / "inbox"
            source = inbox / "Хвостохранилище"
            source.mkdir(parents=True)
            (source / "Декларация.pdf").write_text("x", encoding="utf-8")
            (source / "Неопределенный.pdf").write_text("x", encoding="utf-8")
            with override_settings(DSH_SORT_LOCAL_ROOTS=(tmp,)), patch(
                "checklists_app.sort_service.run_headless",
                side_effect=_headless,
            ):
                response = self.client.post(
                    reverse("checklists_app:sort_start"),
                    {
                        "project_uid": self.project.short_uid,
                        "section": str(self.section.id),
                        "asset": "Asset A",
                        "source_kind": "local",
                        "local_inbox_path": str(inbox),
                    },
                )
        self.assertEqual(response.status_code, 200, response.content)
        run = response.json()["run"]
        self.assertEqual(run["status"], "done")
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            {kit["kit_path"] for kit in calls[0]["kits"]},
            {
                "Хвостохранилище/Декларация.pdf",
                "Хвостохранилище/Неопределенный.pdf",
            },
        )
        proposals = {row["kit_path"]: row for row in run["proposals"]}
        self.assertEqual(proposals["Хвостохранилище/Декларация.pdf"]["confidence"], "высокая")
        unresolved = proposals["Хвостохранилище/Неопределенный.pdf"]
        self.assertEqual(unresolved["dest_path"], "dest/01 TSF Хвостохранилище")
        self.assertEqual(unresolved["action"], "review")

    @override_settings(
        DSH_SORT_INLINE=True,
        DSH_SORT_ALLOW_LOCAL_INBOX=True,
        DSH_HEADLESS_CMD="dsh --profile headless",
    )
    def test_omitted_irrelevant_kits_do_not_trigger_retry(self):
        from unittest.mock import patch

        self.client.force_login(self.admin)
        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp) / "inbox"
            inbox.mkdir()
            (inbox / "Чужой раздел.pdf").write_text("x", encoding="utf-8")
            with override_settings(DSH_SORT_LOCAL_ROOTS=(tmp,)), patch(
                "checklists_app.sort_service.run_headless",
                return_value="```json\n[]\n```",
            ) as headless:
                response = self.client.post(
                    reverse("checklists_app:sort_start"),
                    {
                        "project_uid": self.project.short_uid,
                        "section": str(self.section.id),
                        "asset": "Asset A",
                        "source_kind": "local",
                        "local_inbox_path": str(inbox),
                    },
                )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["run"]["status"], "done")
        self.assertEqual(headless.call_count, 1)

    def test_finalize_sort_run_rolls_back_proposal_replace(self):
        from unittest.mock import patch

        from checklists_app.sort_service import finalize_sort_run

        run = ChecklistSortRun.objects.create(
            project=self.project,
            section=self.section,
            asset_name="Asset A",
            started_by=self.admin,
            status=ChecklistSortRun.Status.RUNNING,
            worker_id="test-worker",
            started_at=timezone.now(),
        )
        old = ChecklistSortProposal.objects.create(
            run=run,
            kit_path="Старый.pdf",
            kit_key="старый.pdf",
            action="review",
        )
        ChecklistSortChunk.objects.create(
            run=run,
            order_key="000001",
            status=ChecklistSortChunk.Status.DONE,
            input_kits=[{"id": "k-1", "kit_path": "Новый.pdf", "file_count": 1}],
            result_rows=[{
                "kit_path": "Новый.pdf",
                "file_count": 1,
                "dest_path": "dest/01 TSF Хвостохранилище",
                "request_name": "",
                "quote": "",
                "confidence": "",
                "action": "review",
                "position": 1,
            }],
        )
        with patch.object(
            ChecklistSortProposal.objects,
            "bulk_create",
            side_effect=RuntimeError("database write failed"),
        ):
            with self.assertRaises(RuntimeError):
                finalize_sort_run(run.id, "test-worker")
        self.assertTrue(ChecklistSortProposal.objects.filter(pk=old.pk).exists())
        run.refresh_from_db()
        self.assertEqual(run.status, ChecklistSortRun.Status.RUNNING)

    def test_sort_step_stops_on_orphaned_running_chunk(self):
        from datetime import timedelta

        from checklists_app.sort_service import process_sort_step

        run = ChecklistSortRun.objects.create(
            project=self.project,
            section=self.section,
            asset_name="Asset A",
            started_by=self.admin,
            status=ChecklistSortRun.Status.RUNNING,
            worker_id="test-worker",
            started_at=timezone.now(),
            heartbeat_at=timezone.now(),
            lease_expires_at=timezone.now() + timedelta(minutes=2),
        )
        ChecklistSortChunk.objects.create(
            run=run,
            order_key="000001",
            status=ChecklistSortChunk.Status.RUNNING,
            input_kits=[{"id": "k-1", "kit_path": "A.pdf", "file_count": 1}],
        )
        self.assertFalse(process_sort_step(run.id, "test-worker"))
        run.refresh_from_db()
        self.assertEqual(run.status, ChecklistSortRun.Status.RUNNING)

    @override_settings(
        DSH_SORT_INLINE=True,
        DSH_SORT_ALLOW_LOCAL_INBOX=True,
        DSH_HEADLESS_CMD="dsh --profile headless",
    )
    def test_leftover_dsh_failure_becomes_review_not_hanging(self):
        from unittest.mock import patch

        from core.dsh_run import DshRunError

        self.client.force_login(self.admin)
        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp) / "inbox"
            inbox.mkdir()
            (inbox / "Сырая выгрузка.pdf").write_text("stub", encoding="utf-8")
            with override_settings(DSH_SORT_LOCAL_ROOTS=(tmp,)), patch(
                "checklists_app.sort_service.run_headless",
                side_effect=DshRunError("Сессия DSH оборвалась (стрим закрылся без ответа)."),
            ):
                response = self.client.post(
                    reverse("checklists_app:sort_start"),
                    {
                        "project_uid": self.project.short_uid,
                        "section": str(self.section.id),
                        "asset": "Asset A",
                        "source_kind": "local",
                        "local_inbox_path": str(inbox),
                    },
                )
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()["run"]
        self.assertEqual(payload["status"], "partial")
        self.assertIn("оборвалась", payload["error_message"])
        row = next(item for item in payload["proposals"] if item.get("kit_path"))
        self.assertEqual(row["kit_path"], "Сырая выгрузка.pdf")
        self.assertEqual(row["action"], "review")


class SortWorkspaceRootTests(SimpleTestCase):
    def test_inventory_parser_rejects_invalid_schema(self):
        from checklists_app.sort_workspace import (
            SortWorkspaceError,
            parse_inbox_inventory,
        )

        with self.assertRaises(SortWorkspaceError):
            parse_inbox_inventory('{"version": 999, "kits": []}')

    def test_cloud_tree_reads_all_pages(self):
        from unittest.mock import patch

        from checklists_app.sort_workspace import list_cloud_tree

        entries = [
            {"name": f"f{index}.pdf", "path": f"/root/f{index}.pdf", "type": "file", "size": index}
            for index in range(5)
        ]

        def _list(user, path, *, limit, offset):
            return entries[offset : offset + limit]

        with patch("checklists_app.sort_workspace.INVENTORY_PAGE_SIZE", 2), patch(
            "checklists_app.sort_workspace.list_folder_resources",
            side_effect=_list,
        ) as listed:
            rows = list_cloud_tree(object(), "/root")
        self.assertEqual(len(rows), 5)
        self.assertEqual(
            [call.kwargs["offset"] for call in listed.call_args_list],
            [0, 2, 4],
        )

    def test_cloud_tree_does_not_treat_listing_error_as_empty(self):
        from unittest.mock import patch

        from checklists_app.sort_workspace import list_cloud_tree
        from core.cloud_storage import CloudStorageNotReadyError

        with patch(
            "checklists_app.sort_workspace.list_folder_resources",
            side_effect=CloudStorageNotReadyError("offline"),
        ):
            with self.assertRaises(CloudStorageNotReadyError):
                list_cloud_tree(object(), "/root")

    def test_prod_requires_explicit_workspace(self):
        from checklists_app.sort_workspace import SortWorkspaceError, workspace_root_for

        with override_settings(DEBUG=False, DSH_SORT_WORKSPACE=""):
            with self.assertRaises(SortWorkspaceError):
                workspace_root_for(1)

    def test_debug_falls_back_to_repo_data_dir(self):
        from checklists_app.sort_workspace import workspace_root_for

        with override_settings(DEBUG=True, DSH_SORT_WORKSPACE=""):
            root = workspace_root_for(9)
        self.assertTrue(str(root).replace("\\", "/").endswith("sort-runs/9"))

    def test_materialize_local_inbox_replaces_dangling_symlink(self):
        from checklists_app.sort_workspace import materialize_local_inbox

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "source"
            (source / "Геология").mkdir(parents=True)
            inbox = tmp_path / "run" / "inbox"
            inbox.parent.mkdir(parents=True)
            inbox.symlink_to(tmp_path / "missing-target")
            self.assertTrue(inbox.is_symlink())
            self.assertFalse(inbox.exists())
            materialize_local_inbox(inbox, source)
            self.assertTrue(inbox.is_symlink())
            self.assertTrue((inbox / "Геология").is_dir())

    def test_inbox_inventory_counts_first_level_kits_without_listing_files(self):
        from checklists_app.sort_workspace import INVENTORY_NAME, write_inbox_inventory

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "run"
            inbox = workspace / "inbox" / "06 LGL Право"
            (inbox / "LGL-01 Лицензии на недра" / "inner" / "a.pdf").parent.mkdir(parents=True)
            (inbox / "LGL-01 Лицензии на недра" / "inner" / "a.pdf").write_text("x", encoding="utf-8")
            (inbox / "LGL-01 Лицензии на недра" / "inner" / "b.pdf").write_text("x", encoding="utf-8")
            (inbox / "LGL-03 Бизнес-планы").mkdir()
            (inbox / ".cloud-file-sizes.json").write_text("{}", encoding="utf-8")
            write_inbox_inventory(workspace, workspace / "inbox", inbox)
            text = (workspace / INVENTORY_NAME).read_text(encoding="utf-8")
        self.assertNotIn(".cloud-file-sizes.json", text)
        from checklists_app.sort_workspace import parse_inbox_inventory

        kits = parse_inbox_inventory(text)
        self.assertEqual(
            [(row["kit_path"], row["file_count"]) for row in kits],
            [
                ("LGL-01 Лицензии на недра", 2),
                ("LGL-03 Бизнес-планы", 0),
            ],
        )
        self.assertEqual(kits[0]["extensions"], {".pdf": 2})
        self.assertIn("inner/a.pdf", kits[0]["samples"])
        self.assertTrue(kits[0]["fingerprint"])

    def test_inbox_inventory_reads_only_small_text_excerpts(self):
        from checklists_app.sort_workspace import (
            INVENTORY_NAME,
            parse_inbox_inventory,
            write_inbox_inventory,
        )

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "run"
            inbox = workspace / "inbox"
            kit = inbox / "Раздел" / "Комплект"
            kit.mkdir(parents=True)
            (kit / "hint.txt").write_text("Содержательная подсказка", encoding="utf-8")
            (kit / "binary.docx").write_bytes(b"PK\x03\x04\x00binary")
            write_inbox_inventory(workspace, inbox, inbox / "Раздел")
            rows = parse_inbox_inventory(
                (workspace / INVENTORY_NAME).read_text(encoding="utf-8")
            )
        self.assertEqual(
            rows[0]["text_excerpts"],
            [{"path": "hint.txt", "text": "Содержательная подсказка"}],
        )

    def test_cloud_placeholder_manifest_preserves_remote_size_limit(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        from checklists_app.sort_verify import (
            MAX_FILE_BYTES,
            VerifyError,
            _download_selected_file,
            build_kit_manifest,
        )
        from checklists_app.sort_workspace import materialize_inbox_tree

        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp) / "inbox"
            source = SimpleNamespace(disk_path="/cloud/source")
            entries = [{
                "name": "large.pdf",
                "path": "/cloud/source/large.pdf",
                "rel": "large.pdf",
                "is_dir": False,
                "size": MAX_FILE_BYTES + 1,
            }]
            with patch("checklists_app.sort_workspace.list_cloud_tree", return_value=entries):
                materialize_inbox_tree(inbox, object(), source, "01 TSF Хвостохранилище")

            placeholder = inbox / "01 TSF Хвостохранилище" / "large.pdf"
            self.assertEqual(placeholder.stat().st_size, 0)
            self.assertEqual(
                build_kit_manifest(placeholder),
                [{
                    "path": "large.pdf",
                    "size": MAX_FILE_BYTES + 1,
                    "ext": ".pdf",
                    "skipped": True,
                }],
            )
            with patch("checklists_app.sort_verify.download_file") as download:
                with self.assertRaises(VerifyError):
                    _download_selected_file(
                        SimpleNamespace(source_kind="cloud"),
                        object(),
                        placeholder,
                        "large.pdf",
                        Path(tmp) / "download.pdf",
                    )
            download.assert_not_called()


class ChecklistSortVerifyParseTests(SimpleTestCase):
    def test_select_keeps_peek_paths(self):
        from checklists_app.sort_parse import parse_verify_select_response

        text = """
reason first

```json
{"peek": ["ПД/ПЗ.pdf", "ИРД/Лицензия.pdf", "ПД/ПЗ.pdf"], "reason": "титул"}
```
"""
        self.assertEqual(
            parse_verify_select_response(text),
            ["ПД/ПЗ.pdf", "ИРД/Лицензия.pdf"],
        )

    def test_accept_peek_paths_strips_unknown_and_caps(self):
        from checklists_app.sort_verify import accept_peek_paths

        manifest = [
            {"path": "a.pdf", "skipped": False},
            {"path": "b.pdf", "skipped": False},
            {"path": "c.pdf", "skipped": False},
            {"path": "huge.pdf", "skipped": True},
        ]
        accepted = accept_peek_paths(
            ["../secret.pdf", "huge.pdf", "kit/a.pdf", "b.pdf", "c.pdf", "a.pdf"],
            manifest,
            kit_prefix="kit",
        )
        self.assertEqual(accepted, ["a.pdf", "b.pdf", "c.pdf"])

    def test_classify_forces_review_without_item_folder(self):
        from checklists_app.sort_parse import parse_verify_classify_response

        text = """
```json
{"kit":"Акт.pdf","files":1,"dest":"dest/02 LGL Право","name":"","quote":"","confidence":"высокая","action":"move"}
```
"""
        row = parse_verify_classify_response(text, kit_path="Акт.pdf")
        self.assertEqual(row["action"], "review")

    def test_finalize_verify_keeps_move_or_asks_to_confirm(self):
        from checklists_app.sort_parse import finalize_verify_action

        dest = "dest/02 LGL Право/LGL-09 Реестр договоров"
        self.assertEqual(finalize_verify_action("средняя", "высокая", dest, "move"), "move")
        self.assertEqual(finalize_verify_action("средняя", "средняя", dest, "review"), "confirm")
        self.assertEqual(finalize_verify_action("низкая", "средняя", dest, "review"), "confirm")
        self.assertEqual(
            finalize_verify_action("средняя", "высокая", "dest/02 LGL Право", "move"),
            "confirm",
        )

    def test_extracts_docx_and_ignores_unknown(self):
        import io

        from docx import Document

        from checklists_app.sort_verify import extract_text_from_bytes

        document = Document()
        document.add_paragraph("Декларация безопасности ГТС")
        buffer = io.BytesIO()
        document.save(buffer)
        text = extract_text_from_bytes("титул.docx", buffer.getvalue(), budget=1000)
        self.assertIn("Декларация безопасности ГТС", text)
        self.assertEqual(extract_text_from_bytes("scan.bin", b"\x00\x01", budget=1000), "")


class ChecklistSortVerifyTests(TestCase):
    def setUp(self):
        super().setUp()
        from django.contrib.auth.models import Group

        from policy_app.models import ADMIN_GROUP

        User = get_user_model()
        self.admin_group, _ = Group.objects.get_or_create(name=ADMIN_GROUP)
        self.admin = User.objects.create_user(
            username="chk-sort-verify-admin",
            password="secret",
            is_staff=True,
        )
        self.admin.groups.add(self.admin_group)
        Employee.objects.create(user=self.admin, role=ADMIN_GROUP)
        self.product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
        )
        self.project = ProjectRegistration.objects.create(
            number=6102,
            type=self.product,
            name="Проверка",
            year=2026,
        )
        self.section = TypicalSection.objects.create(
            product=self.product,
            code="TSF",
            short_name="TSF",
            short_name_ru="Хвостохранилище",
            name_en="TSF",
            name_ru="Хвостохранилище",
            accounting_type="Раздел",
            position=1,
        )
        Performer.objects.create(
            registration=self.project,
            asset_name="Asset A",
            executor="Иванов Иван Иванович",
            typical_section=self.section,
        )
        ChecklistItem.objects.create(
            project=self.project,
            section=self.section,
            code="TSF",
            number=5,
            short_name="Документы по безопасности",
            name="Декларация безопасности ГТС хвостохранилища",
            position=1,
        )
        self._sort_workspace = tempfile.TemporaryDirectory()
        self._sort_workspace_settings = override_settings(
            DSH_SORT_WORKSPACE=self._sort_workspace.name,
            DSH_SORT_INLINE=True,
            DSH_SORT_ALLOW_LOCAL_INBOX=True,
            DSH_HEADLESS_CMD="dsh --profile headless",
        )
        self._sort_workspace_settings.enable()
        self.client.force_login(self.admin)

    def tearDown(self):
        self._sort_workspace_settings.disable()
        self._sort_workspace.cleanup()
        super().tearDown()

    def _start_local_sort(self, inbox, fake_output, headless=None):
        from unittest.mock import patch

        captured = []

        def _fake_headless(prompt, cwd=None, **kwargs):
            captured.append({"prompt": prompt, "cwd": cwd})
            if headless:
                return headless(prompt, cwd, **kwargs)
            return fake_output

        with override_settings(DSH_SORT_LOCAL_ROOTS=(str(inbox.parent),)), patch(
            "checklists_app.sort_service.run_headless", side_effect=_fake_headless
        ):
            response = self.client.post(
                reverse("checklists_app:sort_start"),
                {
                    "project_uid": self.project.short_uid,
                    "section": str(self.section.id),
                    "asset": "Asset A",
                    "source_kind": "local",
                    "local_inbox_path": str(inbox),
                },
            )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["run"], captured

    @override_settings(DSH_SORT_INLINE=True, DSH_HEADLESS_CMD="dsh --profile headless")
    def test_single_file_skips_select_and_can_move(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp) / "inbox"
            inbox.mkdir()
            (inbox / "Декларация.pdf.txt").write_text("титул декларация безопасности", encoding="utf-8")
            kit = (inbox / "Декларация.pdf.txt").name
            sort_output = f"""
```json
[{{"kit":"{kit}","files":1,"dest":"dest/01 TSF Хвостохранилище/TSF-05 Документы по безопасности","name":"Документы по безопасности","quote":"Декларация безопасности ГТС хвостохранилища","confidence":"средняя","action":"review"}}]
```
"""
            run_payload, _ = self._start_local_sort(inbox, sort_output)
            proposal_id = run_payload["proposals"][0]["id"]
            self.assertEqual(run_payload["proposals"][0]["action"], "review")
            classify = """
```json
{"kit":"%s","files":1,"dest":"dest/01 TSF Хвостохранилище/TSF-05 Документы по безопасности","name":"Документы по безопасности","quote":"Декларация безопасности ГТС хвостохранилища","confidence":"высокая","action":"move"}
```
""" % kit
            calls = []

            def _verify_headless(prompt, cwd=None, **kwargs):
                calls.append(prompt)
                return classify

            with patch("checklists_app.sort_verify.run_headless", side_effect=_verify_headless):
                response = self.client.post(
                    reverse("checklists_app:sort_verify"),
                    {"proposal_id": proposal_id},
                )
            self.assertEqual(response.status_code, 200, response.content)
            row = response.json()["run"]["proposals"][0]
            self.assertEqual(row["id"], proposal_id)
            self.assertEqual(row["action"], "move")
            self.assertEqual(row["confidence"], "высокая")
            self.assertFalse(row["verifying"])
            self.assertEqual(len(calls), 1)
            self.assertIn("Фаза: classify", calls[0])
            self.assertNotIn("Фаза: select", calls[0])
            run = ChecklistSortRun.objects.get(pk=run_payload["id"])
            self.assertFalse((Path(run.workspace_path) / "verify" / str(proposal_id)).exists())
            self.assertNotIn("титул декларация", run.raw_response)

    @override_settings(DSH_SORT_INLINE=True, DSH_HEADLESS_CMD="dsh --profile headless")
    def test_verify_same_confidence_becomes_confirm(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp) / "inbox"
            inbox.mkdir()
            (inbox / "Договор.pdf.txt").write_text("договор аффинажа", encoding="utf-8")
            kit = (inbox / "Договор.pdf.txt").name
            sort_output = f"""
```json
[{{"kit":"{kit}","files":1,"dest":"dest/01 TSF Хвостохранилище/TSF-05 Документы по безопасности","name":"Документы по безопасности","quote":"Декларация безопасности ГТС хвостохранилища","confidence":"средняя","action":"review"}}]
```
"""
            run_payload, _ = self._start_local_sort(inbox, sort_output)
            proposal_id = [row for row in run_payload["proposals"] if row.get("kit_path")][0]["id"]
            classify = f"""
```json
{{"kit":"{kit}","files":1,"dest":"dest/01 TSF Хвостохранилище/TSF-05 Документы по безопасности","name":"Документы по безопасности","quote":"Декларация безопасности ГТС хвостохранилища","confidence":"средняя","action":"review"}}
```
"""

            def _verify_headless(prompt, cwd=None, **kwargs):
                return classify

            with patch("checklists_app.sort_verify.run_headless", side_effect=_verify_headless):
                response = self.client.post(
                    reverse("checklists_app:sort_verify"),
                    {"proposal_id": proposal_id},
                )
            self.assertEqual(response.status_code, 200, response.content)
            row = [item for item in response.json()["run"]["proposals"] if item.get("id") == proposal_id][0]
            self.assertEqual(row["action"], "confirm")
            self.assertEqual(row["confidence"], "средняя")
            self.assertFalse(row["verifying"])

    @override_settings(DSH_SORT_INLINE=True, DSH_HEADLESS_CMD="dsh --profile headless")
    def test_select_then_classify_for_folder_kit(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp) / "inbox"
            kit_dir = inbox / "ПД"
            kit_dir.mkdir(parents=True)
            (kit_dir / "ПЗ.txt").write_text("пояснительная записка реконструкция", encoding="utf-8")
            (kit_dir / "Лицензия.txt").write_text("лицензия на недра", encoding="utf-8")
            (kit_dir / "huge.txt").write_text("x" * 10, encoding="utf-8")
            sort_output = """
```json
[{"kit":"ПД/","files":3,"dest":"dest/01 TSF Хвостохранилище/TSF-05 Документы по безопасности","name":"Документы по безопасности","quote":"Декларация безопасности ГТС хвостохранилища","confidence":"средняя","action":"review"}]
```
"""
            run_payload, _ = self._start_local_sort(inbox, sort_output)
            proposal_id = [row for row in run_payload["proposals"] if row["kit_path"]][0]["id"]
            calls = []

            def _verify_headless(prompt, cwd=None, **kwargs):
                calls.append(prompt)
                if "Фаза: select" in prompt:
                    return """```json
{"peek": ["../etc/passwd", "ПЗ.txt", "missing.doc", "Лицензия.txt", "huge.txt"], "reason": "титул"}
```"""
                return """```json
{"kit":"ПД/","files":3,"dest":"dest/01 TSF Хвостохранилище","name":"","quote":"","confidence":"высокая","action":"move"}
```"""

            with patch("checklists_app.sort_verify.run_headless", side_effect=_verify_headless):
                response = self.client.post(
                    reverse("checklists_app:sort_verify"),
                    {"proposal_id": proposal_id},
                )
            self.assertEqual(response.status_code, 200, response.content)
            row = [item for item in response.json()["run"]["proposals"] if item.get("id") == proposal_id][0]
            self.assertEqual(row["action"], "confirm")
            self.assertEqual(len(calls), 2)
            self.assertIn("Фаза: select", calls[0])
            self.assertIn("Фаза: classify", calls[1])
            run = ChecklistSortRun.objects.get(pk=run_payload["id"])
            verify_root = Path(run.workspace_path) / "verify"
            self.assertFalse(verify_root.exists())

    @override_settings(DSH_SORT_INLINE=True, DSH_HEADLESS_CMD="dsh --profile headless")
    def test_new_sort_removes_previous_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp) / "inbox"
            inbox.mkdir()
            (inbox / "Декларация.pdf").write_text("stub", encoding="utf-8")
            sort_output = """
```json
[{"kit":"Декларация.pdf","files":1,"dest":"dest/01 TSF Хвостохранилище/TSF-05 Документы по безопасности","name":"Документы по безопасности","quote":"Декларация безопасности ГТС хвостохранилища","confidence":"высокая","action":"move"}]
```
"""
            first, _ = self._start_local_sort(inbox, sort_output)
            first_run = ChecklistSortRun.objects.get(pk=first["id"])
            first_workspace = Path(first_run.workspace_path)
            self.assertTrue(first_workspace.exists())
            second, _ = self._start_local_sort(inbox, sort_output)
            first_run.refresh_from_db()
            self.assertEqual(first_run.workspace_path, "")
            self.assertFalse(first_workspace.exists())
            self.assertTrue(Path(ChecklistSortRun.objects.get(pk=second["id"]).workspace_path).exists())

    @override_settings(DSH_SORT_INLINE=True, DSH_HEADLESS_CMD="dsh --profile headless")
    def test_verify_can_reassign_kit_to_another_section(self):
        from unittest.mock import patch

        inf = TypicalSection.objects.create(
            product=self.product,
            code="INF",
            short_name="INF",
            short_name_ru="Инфраструктура",
            name_en="Infrastructure",
            name_ru="Инфраструктура",
            accounting_type="Раздел",
            position=2,
        )
        Performer.objects.create(
            registration=self.project,
            asset_name="Asset A",
            executor="Петров Петр Петрович",
            typical_section=inf,
        )
        ChecklistItem.objects.create(
            project=self.project,
            section=inf,
            code="INF",
            number=8,
            short_name="Потребители ЭЭ",
            name="Список потребителей электроэнергии, с указанием установленной мощности. Текущая мощность.",
            position=1,
        )
        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp) / "inbox"
            kit_dir = inbox / "Переработка" / "Новые потребители ЭЭ ЗИФ 3,5"
            kit_dir.mkdir(parents=True)
            (kit_dir / "Информация.txt").write_text("потребители электроэнергии установленная мощность", encoding="utf-8")
            kit = "Переработка/Новые потребители ЭЭ ЗИФ 3,5/"
            sort_output = f"""
```json
[{{"kit":"{kit}","files":1,"dest":"dest/01 TSF Хвостохранилище/TSF-05 Документы по безопасности","name":"Документы по безопасности","quote":"Декларация безопасности ГТС хвостохранилища","confidence":"средняя","action":"review"}}]
```
"""
            run_payload, _ = self._start_local_sort(inbox, sort_output)
            proposal_id = [row for row in run_payload["proposals"] if row.get("kit_path")][0]["id"]
            classify = f"""
```json
{{"kit":"{kit}","files":1,"dest":"dest/02 INF Инфраструктура/INF-08 Потребители ЭЭ","name":"Потребители ЭЭ","quote":"Список потребителей электроэнергии, с указанием установленной мощности. Текущая мощность.","confidence":"высокая","action":"move"}}
```
"""

            def _verify_headless(prompt, cwd=None, **kwargs):
                return classify

            with patch("checklists_app.sort_verify.run_headless", side_effect=_verify_headless):
                response = self.client.post(
                    reverse("checklists_app:sort_verify"),
                    {"proposal_id": proposal_id},
                )
            self.assertEqual(response.status_code, 200, response.content)
            payload = response.json()
            row = [item for item in payload["run"]["proposals"] if item.get("id") == proposal_id][0]
            self.assertEqual(payload["run"]["section_id"], inf.id)
            self.assertEqual(row["action"], "move")
            self.assertEqual(row["confidence"], "высокая")
            self.assertIn("INF-08", row["dest_path"])
            origin = payload.get("origin_run") or {}
            origin_kits = [item.get("kit_path") for item in origin.get("proposals") or [] if item.get("id") == proposal_id]
            self.assertEqual(origin_kits, [])

            proposal = ChecklistSortProposal.objects.get(pk=proposal_id)
            self.assertEqual(proposal.run.section_id, inf.id)
            self.assertFalse(
                ChecklistSortProposal.objects.filter(
                    run_id=run_payload["id"],
                    kit_path=proposal.kit_path,
                ).exists()
            )

            status = self.client.get(
                reverse("checklists_app:sort_status"),
                {
                    "project_uid": self.project.short_uid,
                    "section": "all",
                    "asset": "Asset A",
                },
            )
            self.assertEqual(status.status_code, 200, status.content)
            groups = {group["section_id"]: group for group in status.json()["groups"]}
            inf_row = [
                item
                for item in groups[inf.id]["run"]["proposals"]
                if item.get("id") == proposal_id
            ][0]
            self.assertEqual(inf_row["action"], "move")
            self.assertEqual(inf_row["confidence"], "высокая")
            tsf_kits = [
                item.get("kit_path")
                for item in groups[self.section.id]["run"]["proposals"]
                if item.get("id") == proposal_id or (item.get("kit_path") or "").startswith("Переработка/")
            ]
            self.assertEqual(tsf_kits, [])

    def test_status_does_not_mutate_cross_section_proposal(self):
        inf = TypicalSection.objects.create(
            product=self.product,
            code="INF",
            short_name="INF",
            short_name_ru="Инфраструктура",
            name_en="Infrastructure",
            name_ru="Инфраструктура",
            accounting_type="Раздел",
            position=2,
        )
        Performer.objects.create(
            registration=self.project,
            asset_name="Asset A",
            executor="Петров Петр Петрович",
            typical_section=inf,
        )
        ChecklistItem.objects.create(
            project=self.project,
            section=inf,
            code="INF",
            number=8,
            short_name="Потребители ЭЭ",
            name="Список потребителей электроэнергии, с указанием установленной мощности. Текущая мощность.",
            position=1,
        )
        run = ChecklistSortRun.objects.create(
            project=self.project,
            section=self.section,
            asset_name="Asset A",
            started_by=self.admin,
            status=ChecklistSortRun.Status.DONE,
            workspace_path=str(Path(self._sort_workspace.name) / "1"),
        )
        proposal = ChecklistSortProposal.objects.create(
            run=run,
            kit_path="Переработка/Новые потребители ЭЭ ЗИФ 3,5/",
            dest_path="dest/08 INF Инфраструктура/INF-08 Потребители ЭЭ",
            request_name="Потребители ЭЭ",
            quote="Список потребителей электроэнергии, с указанием установленной мощности. Текущая мощность.",
            confidence="высокая",
            action="move",
        )
        response = self.client.get(
            reverse("checklists_app:sort_status"),
            {
                "project_uid": self.project.short_uid,
                "section": "all",
                "asset": "Asset A",
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        groups = {group["section_id"]: group for group in response.json()["groups"]}
        self.assertIsNone(groups[inf.id]["run"])
        tsf_rows = [
            item
            for item in groups[self.section.id]["run"]["proposals"]
            if item.get("id") == proposal.id
        ]
        self.assertEqual(len(tsf_rows), 1)
        proposal.refresh_from_db()
        self.assertEqual(proposal.run.section_id, self.section.id)

    def test_verify_rejects_move_rows(self):
        run = ChecklistSortRun.objects.create(
            project=self.project,
            section=self.section,
            asset_name="Asset A",
            started_by=self.admin,
            status=ChecklistSortRun.Status.DONE,
            workspace_path=str(Path(self._sort_workspace.name) / "1"),
        )
        proposal = ChecklistSortProposal.objects.create(
            run=run,
            kit_path="Декларация.pdf",
            dest_path="dest/01 TSF Хвостохранилище/TSF-05 Документы по безопасности",
            confidence="высокая",
            action="move",
        )
        response = self.client.post(
            reverse("checklists_app:sort_verify"),
            {"proposal_id": proposal.id},
        )
        self.assertEqual(response.status_code, 400)

    def test_stale_running_verify_is_reclaimed_on_status(self):
        run = ChecklistSortRun.objects.create(
            project=self.project,
            section=self.section,
            asset_name="Asset A",
            started_by=self.admin,
            status=ChecklistSortRun.Status.DONE,
            workspace_path=str(Path(self._sort_workspace.name) / "1"),
        )
        proposal = ChecklistSortProposal.objects.create(
            run=run,
            kit_path="Декларация.pdf",
            dest_path="dest/01 TSF Хвостохранилище/TSF-05 Документы по безопасности",
            confidence="средняя",
            action="review",
            verify_status="running",
        )
        response = self.client.get(
            reverse("checklists_app:sort_status"),
            {
                "project_uid": self.project.short_uid,
                "section": str(self.section.id),
                "asset": "Asset A",
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        row = [item for item in response.json()["run"]["proposals"] if item.get("id") == proposal.id][0]
        self.assertFalse(row["verifying"])
        self.assertIn("не завершилась", row["verify_error"])
        proposal.refresh_from_db()
        self.assertEqual(proposal.verify_status, "running")

    def test_durable_worker_requeues_only_its_interrupted_jobs(self):
        from checklists_app.sort_worker import recover_interrupted_jobs

        running = ChecklistSortRun.objects.create(
            project=self.project,
            section=self.section,
            asset_name="Asset A",
            started_by=self.admin,
            status=ChecklistSortRun.Status.RUNNING,
            started_at=timezone.now(),
        )
        done = ChecklistSortRun.objects.create(
            project=self.project,
            section=self.section,
            asset_name="Asset B",
            started_by=self.admin,
            status=ChecklistSortRun.Status.DONE,
            started_at=timezone.now(),
            finished_at=timezone.now(),
        )
        proposal = ChecklistSortProposal.objects.create(
            run=done,
            kit_path="Декларация.pdf",
            action="review",
            verify_status="running",
            verify_started_at=timezone.now(),
            verify_started_by=self.admin,
        )

        self.assertEqual(recover_interrupted_jobs(), (1, 1))

        running.refresh_from_db()
        done.refresh_from_db()
        proposal.refresh_from_db()
        self.assertEqual(running.status, ChecklistSortRun.Status.QUEUED)
        self.assertIsNotNone(running.started_at)
        self.assertEqual(done.status, ChecklistSortRun.Status.DONE)
        self.assertEqual(proposal.verify_status, "queued")
        self.assertIsNotNone(proposal.verify_started_at)

    def test_worker_recovery_keeps_fresh_leases(self):
        from datetime import timedelta

        from checklists_app.sort_worker import recover_interrupted_jobs

        deadline = timezone.now() + timedelta(minutes=2)
        running = ChecklistSortRun.objects.create(
            project=self.project,
            section=self.section,
            asset_name="Asset A",
            started_by=self.admin,
            status=ChecklistSortRun.Status.RUNNING,
            worker_id="live-worker",
            started_at=timezone.now(),
            heartbeat_at=timezone.now(),
            lease_expires_at=deadline,
        )
        done = ChecklistSortRun.objects.create(
            project=self.project,
            section=self.section,
            asset_name="Asset B",
            started_by=self.admin,
            status=ChecklistSortRun.Status.DONE,
        )
        proposal = ChecklistSortProposal.objects.create(
            run=done,
            kit_path="Декларация.pdf",
            action="review",
            verify_status="running",
            verify_started_at=timezone.now(),
            verify_heartbeat_at=timezone.now(),
            verify_lease_expires_at=deadline,
            verify_worker_id="live-worker",
        )
        self.assertEqual(recover_interrupted_jobs("new-worker"), (0, 0))
        running.refresh_from_db()
        proposal.refresh_from_db()
        self.assertEqual(running.status, ChecklistSortRun.Status.RUNNING)
        self.assertEqual(proposal.verify_status, "running")

    def test_resumed_run_processes_only_pending_chunk(self):
        from unittest.mock import patch

        from checklists_app.sort_service import process_sort_step

        workspace = Path(self._sort_workspace.name) / "resume"
        workspace.mkdir(parents=True)
        run = ChecklistSortRun.objects.create(
            project=self.project,
            section=self.section,
            asset_name="Asset A",
            started_by=self.admin,
            status=ChecklistSortRun.Status.QUEUED,
            workspace_path=str(workspace),
        )
        ChecklistSortChunk.objects.create(
            run=run,
            order_key="000001",
            status=ChecklistSortChunk.Status.DONE,
            input_kits=[{"id": "k-1", "kit_path": "Готовый.pdf", "file_count": 1}],
            result_rows=[{
                "kit_path": "Готовый.pdf",
                "file_count": 1,
                "dest_path": "dest/01 TSF Хвостохранилище/TSF-05 Документы по безопасности",
                "request_name": "Документы по безопасности",
                "quote": "Декларация безопасности ГТС хвостохранилища",
                "confidence": "высокая",
                "action": "move",
                "position": 1,
            }],
        )
        ChecklistSortChunk.objects.create(
            run=run,
            order_key="000002",
            status=ChecklistSortChunk.Status.PENDING,
            input_kits=[{"id": "k-2", "kit_path": "Новый.pdf", "file_count": 1}],
        )
        output = """
```json
[{"kit":"Новый.pdf","files":1,"dest":"dest/01 TSF Хвостохранилище/TSF-05 Документы по безопасности","name":"Документы по безопасности","quote":"Декларация безопасности ГТС хвостохранилища","confidence":"высокая","action":"move"}]
```
"""
        with patch(
            "checklists_app.sort_service._prepare_workspace"
        ) as prepare, patch(
            "checklists_app.sort_service.run_headless",
            return_value=output,
        ) as headless:
            self.assertTrue(process_sort_step(run.id, "resume-worker"))
        prepare.assert_not_called()
        self.assertEqual(headless.call_count, 1)
        run.refresh_from_db()
        self.assertEqual(run.status, ChecklistSortRun.Status.DONE)
        self.assertEqual(run.proposals.exclude(kit_path="").count(), 2)

    def test_worker_runs_queued_verify_before_replacement_sort(self):
        from unittest.mock import patch

        from checklists_app import sort_worker
        from checklists_app.sort_worker import process_next_job

        done = ChecklistSortRun.objects.create(
            project=self.project,
            section=self.section,
            asset_name="Asset A",
            started_by=self.admin,
            status=ChecklistSortRun.Status.DONE,
            workspace_path="/tmp/old-sort",
        )
        proposal = ChecklistSortProposal.objects.create(
            run=done,
            kit_path="Декларация.pdf",
            action="review",
            verify_status="queued",
        )
        queued_sort = ChecklistSortRun.objects.create(
            project=self.project,
            section=self.section,
            asset_name="Asset A",
            started_by=self.admin,
            status=ChecklistSortRun.Status.QUEUED,
        )
        order = []

        def _verify(pk, **kwargs):
            order.append(("verify", pk))
            ChecklistSortProposal.objects.filter(pk=pk).update(verify_status="")

        def _sort(pk, worker_id):
            order.append(("sort", pk))
            return True

        sort_worker._verify_streak = 0
        with patch("checklists_app.sort_worker.execute_verify_proposal", side_effect=_verify), patch(
            "checklists_app.sort_worker.process_sort_step", side_effect=_sort
        ):
            self.assertTrue(process_next_job())
            self.assertTrue(process_next_job())
        self.assertEqual(order, [("verify", proposal.id), ("sort", queued_sort.id)])

    def test_sort_start_blocked_while_verify_queued(self):
        done = ChecklistSortRun.objects.create(
            project=self.project,
            section=self.section,
            asset_name="Asset A",
            started_by=self.admin,
            status=ChecklistSortRun.Status.DONE,
        )
        ChecklistSortProposal.objects.create(
            run=done,
            kit_path="Декларация.pdf",
            action="review",
            verify_status="queued",
        )
        response = self.client.post(
            reverse("checklists_app:sort_start"),
            {
                "project_uid": self.project.short_uid,
                "section": str(self.section.id),
                "asset": "Asset A",
            },
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("проверки", response.json()["error"].lower())

    def test_verify_start_blocked_while_sort_queued(self):
        done = ChecklistSortRun.objects.create(
            project=self.project,
            section=self.section,
            asset_name="Asset A",
            started_by=self.admin,
            status=ChecklistSortRun.Status.DONE,
        )
        proposal = ChecklistSortProposal.objects.create(
            run=done,
            kit_path="Декларация.pdf",
            action="review",
        )
        ChecklistSortRun.objects.create(
            project=self.project,
            section=self.section,
            asset_name="Asset A",
            started_by=self.admin,
            status=ChecklistSortRun.Status.QUEUED,
        )
        response = self.client.post(
            reverse("checklists_app:sort_verify"),
            {"proposal_id": str(proposal.id)},
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("выполняется", response.json()["error"].lower())
        proposal.refresh_from_db()
        self.assertNotEqual(proposal.verify_status, "queued")

    def test_cleanup_keeps_workspace_while_verify_queued(self):
        from checklists_app.sort_workspace import cleanup_stale_sort_workspaces

        old_root = Path(self._sort_workspace.name) / "old"
        (old_root / "inbox").mkdir(parents=True)
        done = ChecklistSortRun.objects.create(
            project=self.project,
            section=self.section,
            asset_name="Asset A",
            started_by=self.admin,
            status=ChecklistSortRun.Status.DONE,
            workspace_path=str(old_root),
        )
        ChecklistSortProposal.objects.create(
            run=done,
            kit_path="Декларация.pdf",
            action="review",
            verify_status="queued",
        )
        replacement = ChecklistSortRun.objects.create(
            project=self.project,
            section=self.section,
            asset_name="Asset A",
            started_by=self.admin,
            status=ChecklistSortRun.Status.QUEUED,
        )
        cleanup_stale_sort_workspaces(replacement)
        self.assertTrue(old_root.is_dir())
        done.refresh_from_db()
        self.assertEqual(done.workspace_path, str(old_root))


class ChecklistSortWorkerUnitTests(SimpleTestCase):
    def test_systemd_unit_waits_for_dsh(self):
        from django.conf import settings

        text = (Path(settings.BASE_DIR) / "deploy" / "checklist-sort-worker.service").read_text(
            encoding="utf-8"
        )
        self.assertIn("After=network-online.target docker.service dsh-compose.service", text)
        self.assertIn("ExecStartPre=/opt/dsh/dsh-healthcheck.sh", text)
        self.assertIn("TimeoutStartSec=300", text)


