from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from policy_app.models import Product, TypicalSection
from projects_app.models import Performer, ProjectRegistration

from checklists_app.models import SharedChecklistLink
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
