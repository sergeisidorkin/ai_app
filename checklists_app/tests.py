import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from policy_app.models import EXPERT_GROUP, Product, TypicalSection
from projects_app.models import LegalEntity, Performer, ProjectRegistration, WorkVolume
from users_app.models import Employee
from notifications_app.models import Notification, NotificationPerformerLink

from checklists_app.models import (
    ChecklistCustomerStatus,
    ChecklistItem,
    ChecklistItemAuditLog,
    ChecklistStatus,
    SharedChecklistLink,
)
from checklists_app.views import _project_options


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

