import importlib

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase
from django.urls import reverse

from group_app.models import GroupMember
from policy_app.models import Product

from projects_app.models import ProjectRegistration, WorkVolume

convert_existing_registrations = importlib.import_module(
    "projects_app.migrations.0122_convert_project_stages"
).convert_existing_registrations


class StageProjectTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="stage-projects-user",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.group_member = GroupMember.objects.create(
            short_name="IMC",
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
            position=1,
        )
        self.second_product = Product.objects.create(
            short_name="QA",
            name_en="QA",
            name_ru="QA",
            consulting_type="Горный",
            service_category="Контроль",
            service_subtype="Контроль качества",
            position=2,
        )

    def _create_row(self, **overrides):
        values = {
            "number": 55,
            "group_member": self.group_member,
            "agreement_type": ProjectRegistration.AgreementType.MAIN,
            "name": "Проект",
            "type": self.product,
            "position": 1,
        }
        values.update(overrides)
        return ProjectRegistration.objects.create(**values)

    def test_stage_code_inserts_digit_after_seventh_character(self):
        self.assertEqual(ProjectRegistration.stage_code("00550000RU", "1"), "005500010RU")
        self.assertEqual(ProjectRegistration.stage_code("00550000RU", "0"), "005500000RU")
        self.assertEqual(ProjectRegistration.stage_code("00550010RU", "2"), "005500120RU")

    def test_stage_conversion_migration_ignores_columns_added_later(self):
        loader = MigrationLoader(connection)
        state = loader.project_state(("projects_app", "0121_project_stage_link"))
        historical = state.apps.get_model("projects_app", "ProjectRegistration")
        field_names = {field.name for field in historical._meta.local_fields}
        self.assertIn("stage_project", field_names)
        self.assertIn("summary_deferred", field_names)
        self.assertNotIn("status_date", field_names)
        self.assertNotIn("summary_status_date", field_names)
        self.assertNotIn("terms_columns_json", field_names)
        self.assertNotIn("contract_end_enabled", field_names)
        query = str(historical.objects.order_by("position", "id").query)
        self.assertNotIn("status_date", query)
        self.assertNotIn("terms_columns_json", query)
        self.assertNotIn("contract_end_enabled", query)

    def test_service_scope_backfill_uses_historical_models(self):
        loader = MigrationLoader(connection)
        state = loader.project_state(("projects_app", "0124_service_scope_key"))
        historical = state.apps.get_model("projects_app", "ProjectRegistration")
        field_names = {field.name for field in historical._meta.local_fields}
        self.assertIn("status_date", field_names)
        self.assertNotIn("terms_columns_json", field_names)
        self.assertNotIn("contract_end_enabled", field_names)
        work_fields = {field.name for field in state.apps.get_model("projects_app", "WorkVolume")._meta.local_fields}
        self.assertIn("scope_key", work_fields)
        query = str(historical.objects.values_list("pk", "stage_project_id").query)
        self.assertNotIn("terms_columns_json", query)
        self.assertNotIn("contract_end_enabled", query)

        row = self._create_row()
        volume = WorkVolume.objects.create(
            project=row,
            name="Карьер",
            asset_name="Карьер",
            position=1,
        )
        backfill = importlib.import_module(
            "projects_app.migrations.0124_service_scope_key"
        ).backfill_service_scopes
        backfill(state.apps, None)
        volume.refresh_from_db()
        self.assertIsNotNone(volume.scope_key)

    def test_convert_keeps_single_project_id_and_writes_stage_code(self):
        row = self._create_row()
        original = row.short_uid

        convert_existing_registrations()

        row.refresh_from_db()
        parent = row.stage_project
        self.assertIsNotNone(parent)
        self.assertEqual(parent.short_uid, original)
        self.assertEqual(len(parent.short_uid), 10)
        self.assertEqual(row.short_uid, ProjectRegistration.stage_code(original, "0"))

    def test_convert_rewrites_summary_group_and_leaves_other_group(self):
        first = self._create_row(position=1, name="Сводный")
        second = self._create_row(position=2, type=self.second_product, name="Сводный")
        other_group = GroupMember.objects.create(
            short_name="IMC KZ",
            country_name="Казахстан",
            country_code="398",
            country_alpha2="KZ",
            position=2,
        )
        separate = self._create_row(position=3, group_member=other_group, name="Отдельный")
        separate_uid = separate.short_uid

        convert_existing_registrations()

        first.refresh_from_db()
        second.refresh_from_db()
        separate.refresh_from_db()
        self.assertEqual(first.stage_project_id, second.stage_project_id)
        parent = first.stage_project
        self.assertEqual(len(parent.short_uid), 10)
        self.assertEqual(first.short_uid, ProjectRegistration.stage_code(parent.short_uid, "1"))
        self.assertEqual(second.short_uid, ProjectRegistration.stage_code(parent.short_uid, "2"))
        self.assertNotEqual(separate.stage_project_id, parent.pk)
        self.assertEqual(separate.stage_project.short_uid, separate_uid)

    def test_new_single_project_is_not_merged_into_existing_group(self):
        first = self._create_row(position=1)
        second = self._create_row(position=2, type=self.second_product)
        convert_existing_registrations()
        first.refresh_from_db()
        parent = first.stage_project

        response = self.client.post(
            reverse("registration_form_create"),
            {
                "number": "55",
                "group_member": str(self.group_member.pk),
                "agreement_type": ProjectRegistration.AgreementType.MAIN,
                "status": "Не начат",
                "name": "Новый одиночный",
                "type_id": [str(self.product.pk)],
                "year": "2026",
            },
        )

        self.assertEqual(response.status_code, 200)
        created_stage = ProjectRegistration.objects.exclude(
            pk__in=[first.pk, second.pk, parent.pk]
        ).get(stage_project__isnull=False, name="Новый одиночный")
        self.assertNotEqual(created_stage.stage_project_id, parent.pk)
        self.assertEqual(created_stage.stage_project.stages.count(), 1)

    def test_registry_shows_project_id_and_stage_numbers(self):
        response = self.client.post(
            reverse("registration_form_create"),
            {
                "number": "55",
                "group_member": str(self.group_member.pk),
                "agreement_type": ProjectRegistration.AgreementType.MAIN,
                "status": "Не начат",
                "name": "Два этапа",
                "type_id": [str(self.product.pk), str(self.second_product.pk)],
                "year": "2026",
            },
        )
        self.assertEqual(response.status_code, 200)
        parent = ProjectRegistration.objects.get(stage_project__isnull=True, name="Два этапа")
        stages = list(parent.stages.order_by("position", "id"))
        page = self.client.get(reverse("projects_partial"))
        self.assertContains(page, parent.short_uid)
        self.assertContains(page, stages[0].short_uid)
        self.assertContains(page, stages[1].short_uid)
        self.assertContains(page, "Этап")
