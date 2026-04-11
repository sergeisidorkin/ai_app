import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from classifiers_app.models import OKVCurrency
from experts_app.models import ExpertSpecialty
from group_app.models import GroupMember, OrgUnit
from policy_app.models import (
    ExpertiseDirection,
    Product,
    ServiceGoalReport,
    SpecialtyTariff,
    Tariff,
    TypicalSection,
    TypicalServiceComposition,
    TypicalServiceTerm,
)
from users_app.models import Employee


class RemoveTypicalSectionExecutorMigrationTests(TransactionTestCase):
    migrate_from = ("policy_app", "0033_typicalsection_exclude_from_tkp_autofill")
    migrate_to = ("policy_app", "0034_remove_typicalsection_executor")

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.migrate([self.migrate_from])
        old_apps = self.executor.loader.project_state([self.migrate_from]).apps

        Product = old_apps.get_model("policy_app", "Product")
        TypicalSection = old_apps.get_model("policy_app", "TypicalSection")
        ExpertSpecialty = old_apps.get_model("experts_app", "ExpertSpecialty")
        TypicalSectionSpecialty = old_apps.get_model("policy_app", "TypicalSectionSpecialty")

        product = Product.objects.create(
            short_name="MIG",
            name_en="Migration product",
            display_name="Migration product",
            name_ru="Миграционный продукт",
            service_type="Консалтинг",
            position=1,
        )
        existing_specialty = ExpertSpecialty.objects.create(
            specialty="Юрист",
            specialty_en="",
            position=1,
        )
        self.section = TypicalSection.objects.create(
            product_id=product.pk,
            code="MIG-1",
            short_name="mig-1",
            short_name_ru="mig-1",
            name_en="Migration section",
            name_ru="Миграционный раздел",
            accounting_type="Раздел",
            executor="Партнер; Юрист",
            position=1,
        )
        TypicalSectionSpecialty.objects.create(
            section_id=self.section.pk,
            specialty_id=existing_specialty.pk,
            rank=1,
        )

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_migration_backfills_executor_into_ranked_specialties(self):
        self.executor.loader.build_graph()
        self.executor.migrate([self.migrate_to])
        new_apps = self.executor.loader.project_state([self.migrate_to]).apps

        ExpertSpecialty = new_apps.get_model("experts_app", "ExpertSpecialty")
        TypicalSectionSpecialty = new_apps.get_model("policy_app", "TypicalSectionSpecialty")

        created_names = list(
            ExpertSpecialty.objects.filter(specialty__in=["Партнер", "Юрист"])
            .order_by("specialty")
            .values_list("specialty", flat=True)
        )
        self.assertEqual(created_names, ["Партнер", "Юрист"])

        links = list(
            TypicalSectionSpecialty.objects.filter(section_id=self.section.pk)
            .select_related("specialty")
            .order_by("rank")
        )
        self.assertEqual([(link.specialty.specialty, link.rank) for link in links], [("Юрист", 1), ("Партнер", 2)])


class TypicalSectionViewsTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="policy-sections-admin",
            password="secret123",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.product = Product.objects.create(
            short_name="SEC",
            name_en="Sections",
            display_name="Sections",
            name_ru="Разделы",
            service_type="Консалтинг",
            position=1,
        )

    def test_policy_partial_renders_tkp_column_for_sections(self):
        TypicalSection.objects.create(
            product=self.product,
            code="SEC-1",
            short_name="section-en",
            short_name_ru="section-ru",
            name_en="Section EN",
            name_ru="Раздел RU",
            accounting_type="Раздел",
            exclude_from_tkp_autofill=True,
            position=1,
        )

        response = self.client.get(reverse("policy_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Типовые разделы (услуги)")
        self.assertContains(response, '<th><i class="bi bi-ban me-1"></i>ТКП</th>', html=False)
        self.assertContains(response, 'aria-label="Исключить из автозаполнения в ТКП"', html=False)

    def test_create_section_saves_tkp_exclusion_flag(self):
        response = self.client.post(
            reverse("section_form_create"),
            {
                "product": self.product.pk,
                "code": "SEC-2",
                "short_name": "audit-en",
                "short_name_ru": "audit-ru",
                "name_en": "Audit EN",
                "name_ru": "Аудит RU",
                "accounting_type": "Раздел",
                "exclude_from_tkp_autofill": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        section = TypicalSection.objects.get(code="SEC-2")
        self.assertTrue(section.exclude_from_tkp_autofill)

    def test_section_csv_upload_accepts_rows_without_legacy_executor_column(self):
        csv_file = SimpleUploadedFile(
            "sections.csv",
            (
                "Продукт;Код;Краткое имя EN;Краткое имя RU;Наименование EN;Наименование RU;Тип учета;Направление экспертизы\n"
                "SEC;SEC-3;section-3;section-3-ru;Section 3;Раздел 3;Раздел;\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(reverse("section_csv_upload"), {"csv_file": csv_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 1)
        self.assertEqual(response.json()["warnings"], [])
        self.assertTrue(TypicalSection.objects.filter(code="SEC-3").exists())


class ServiceGoalReportViewsTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="policy-admin",
            password="secret123",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.product = Product.objects.create(
            short_name="TAX",
            name_en="Tax",
            display_name="Tax",
            name_ru="Налоги",
            service_type="Консалтинг",
            position=1,
        )

    def test_policy_partial_renders_service_goal_reports_table(self):
        ServiceGoalReport.objects.create(
            product=self.product,
            service_goal="Подготовка заключения",
            service_goal_genitive="Подготовки заключения",
            report_title="Итоговый отчет",
            position=1,
        )

        response = self.client.get(reverse("policy_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Цели услуг и названия отчетов")
        self.assertContains(response, "Подготовка заключения")
        self.assertContains(response, "Подготовки заключения")
        self.assertContains(response, 'id="service-goal-reports-actions"', html=False)

    def test_create_service_goal_report_saves_row(self):
        response = self.client.post(
            reverse("service_goal_report_form_create"),
            {
                "product": self.product.pk,
                "service_goal": "Подготовка документов",
                "service_goal_genitive": "Подготовки документов",
                "report_title": "Отчет по документам",
            },
        )

        self.assertEqual(response.status_code, 200)
        item = ServiceGoalReport.objects.get()
        self.assertEqual(item.product, self.product)
        self.assertEqual(item.service_goal, "Подготовка документов")
        self.assertEqual(item.service_goal_genitive, "Подготовки документов")
        self.assertEqual(item.report_title, "Отчет по документам")
        self.assertEqual(item.position, 1)

    def test_move_up_reorders_globally_across_table(self):
        other_product = Product.objects.create(
            short_name="AUD",
            name_en="Audit",
            display_name="Audit",
            name_ru="Аудит",
            service_type="Аудит",
            position=2,
        )
        first = ServiceGoalReport.objects.create(
            product=self.product,
            service_goal="Первая цель",
            service_goal_genitive="Первой цели",
            report_title="Первый отчет",
            position=1,
        )
        second = ServiceGoalReport.objects.create(
            product=other_product,
            service_goal="Вторая цель",
            service_goal_genitive="Второй цели",
            report_title="Второй отчет",
            position=2,
        )

        response = self.client.post(reverse("service_goal_report_move_up", args=[second.pk]))

        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.position, 2)
        self.assertEqual(second.position, 1)

    def test_non_staff_user_cannot_reorder_service_goal_reports(self):
        first = ServiceGoalReport.objects.create(
            product=self.product,
            service_goal="Первая цель",
            service_goal_genitive="Первой цели",
            report_title="Первый отчет",
            position=1,
        )
        second = ServiceGoalReport.objects.create(
            product=self.product,
            service_goal="Вторая цель",
            service_goal_genitive="Второй цели",
            report_title="Второй отчет",
            position=2,
        )
        non_staff = get_user_model().objects.create_user(
            username="policy-user",
            password="secret123",
            is_staff=False,
        )
        client = self.client_class()
        client.force_login(non_staff)

        response = client.post(reverse("service_goal_report_move_up", args=[second.pk]))

        self.assertEqual(response.status_code, 302)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.position, 1)
        self.assertEqual(second.position, 2)


class TypicalServiceCompositionViewsTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="policy-admin-2",
            password="secret123",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.product = Product.objects.create(
            short_name="TAX2",
            name_en="Tax 2",
            display_name="Tax 2",
            name_ru="Налоги 2",
            service_type="Консалтинг",
            position=1,
        )
        self.other_product = Product.objects.create(
            short_name="AUD2",
            name_en="Audit 2",
            display_name="Audit 2",
            name_ru="Аудит 2",
            service_type="Аудит",
            position=2,
        )
        self.section = TypicalSection.objects.create(
            product=self.product,
            code="S1",
            short_name="sec-en",
            short_name_ru="sec-ru",
            name_en="Section EN",
            name_ru="Раздел RU",
            accounting_type="Раздел",
            position=1,
        )
        self.other_section = TypicalSection.objects.create(
            product=self.other_product,
            code="S2",
            short_name="other-en",
            short_name_ru="other-ru",
            name_en="Other EN",
            name_ru="Другой раздел RU",
            accounting_type="Раздел",
            position=1,
        )

    def test_policy_partial_renders_typical_service_compositions_table(self):
        TypicalServiceComposition.objects.create(
            product=self.product,
            section=self.section,
            service_composition="Подготовка,\nанализ,\nвыпуск отчета",
            position=1,
        )

        response = self.client.get(reverse("policy_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Типовой состав услуг")
        self.assertContains(response, "Раздел RU")
        self.assertContains(response, "Подготовка,\nанализ,\nвыпуск отчета")
        self.assertContains(response, 'id="typical-service-compositions-wrap-toggle"', html=False)
        self.assertContains(response, 'id="typical-service-compositions-table"', html=False)
        self.assertContains(response, 'class="policy-service-composition-cell"', html=False)
        self.assertContains(response, 'class="policy-service-composition-content"', html=False)

    def test_create_typical_service_composition_saves_row(self):
        editor_state = {
            "html": "<p><strong>Этап 1</strong></p><p>Этап 2</p>",
            "plain_text": "Этап 1\nЭтап 2",
        }
        response = self.client.post(
            reverse("typical_service_composition_form_create"),
            {
                "product": self.product.pk,
                "section": self.section.pk,
                "service_composition": "",
                "service_composition_editor_state": json.dumps(editor_state, ensure_ascii=False),
            },
        )

        self.assertEqual(response.status_code, 200)
        item = TypicalServiceComposition.objects.get()
        self.assertEqual(item.product, self.product)
        self.assertEqual(item.section, self.section)
        self.assertEqual(item.service_composition, "Этап 1\nЭтап 2")
        self.assertEqual(item.service_composition_editor_state, editor_state)
        self.assertEqual(item.position, 1)

    def test_create_typical_service_composition_rejects_section_from_other_product(self):
        response = self.client.post(
            reverse("typical_service_composition_form_create"),
            {
                "product": self.product.pk,
                "section": self.other_section.pk,
                "service_composition": "Некорректная связь",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Раздел должен относиться к выбранному продукту.")
        self.assertFalse(TypicalServiceComposition.objects.exists())

    def test_non_staff_user_cannot_reorder_typical_service_compositions(self):
        first = TypicalServiceComposition.objects.create(
            product=self.product,
            section=self.section,
            service_composition="Этап 1",
            position=1,
        )
        second = TypicalServiceComposition.objects.create(
            product=self.product,
            section=self.section,
            service_composition="Этап 2",
            position=2,
        )
        non_staff = get_user_model().objects.create_user(
            username="policy-user-2",
            password="secret123",
            is_staff=False,
        )
        client = self.client_class()
        client.force_login(non_staff)

        response = client.post(reverse("typical_service_composition_move_down", args=[first.pk]))

        self.assertEqual(response.status_code, 302)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.position, 1)
        self.assertEqual(second.position, 2)


class TypicalServiceTermViewsTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="policy-admin-terms",
            password="secret123",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.product = Product.objects.create(
            short_name="TERM",
            name_en="Terms",
            display_name="Terms",
            name_ru="Сроки",
            service_type="Консалтинг",
            position=1,
        )
        self.other_product = Product.objects.create(
            short_name="TERM2",
            name_en="Terms 2",
            display_name="Terms 2",
            name_ru="Сроки 2",
            service_type="Аудит",
            position=2,
        )

    def test_policy_partial_renders_typical_service_terms_table(self):
        TypicalServiceTerm.objects.create(
            product=self.product,
            preliminary_report_months=Decimal("1.5"),
            final_report_weeks=3,
            position=1,
        )

        response = self.client.get(reverse("policy_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Типовые сроки оказания услуг")
        self.assertContains(response, "Срок подготовки Предварительного отчёта, мес.")
        self.assertContains(response, "Срок подготовки Итогового отчёта, нед.")
        self.assertContains(response, ">1,5<", html=False)
        self.assertContains(response, ">3<", html=False)
        self.assertContains(response, 'id="typical-service-terms-actions"', html=False)

    def test_create_typical_service_term_saves_row(self):
        response = self.client.post(
            reverse("typical_service_term_form_create"),
            {
                "product": self.product.pk,
                "preliminary_report_months": "2.5",
                "final_report_weeks": "4",
            },
        )

        self.assertEqual(response.status_code, 200)
        item = TypicalServiceTerm.objects.get()
        self.assertEqual(item.product, self.product)
        self.assertEqual(item.preliminary_report_months, Decimal("2.5"))
        self.assertEqual(item.final_report_weeks, 4)
        self.assertEqual(item.position, 1)

    def test_create_typical_service_term_accepts_comma_decimal(self):
        response = self.client.post(
            reverse("typical_service_term_form_create"),
            {
                "product": self.product.pk,
                "preliminary_report_months": "1,5",
                "final_report_weeks": "2",
            },
        )

        self.assertEqual(response.status_code, 200)
        item = TypicalServiceTerm.objects.get()
        self.assertEqual(item.preliminary_report_months, Decimal("1.5"))

    def test_edit_form_renders_comma_decimal_value(self):
        item = TypicalServiceTerm.objects.create(
            product=self.product,
            preliminary_report_months=Decimal("1.5"),
            final_report_weeks=3,
            position=1,
        )

        response = self.client.get(reverse("typical_service_term_form_edit", args=[item.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="1,5"', html=False)

    def test_non_staff_user_cannot_reorder_typical_service_terms(self):
        first = TypicalServiceTerm.objects.create(
            product=self.product,
            preliminary_report_months=Decimal("1.0"),
            final_report_weeks=2,
            position=1,
        )
        second = TypicalServiceTerm.objects.create(
            product=self.other_product,
            preliminary_report_months=Decimal("2.0"),
            final_report_weeks=4,
            position=2,
        )
        non_staff = get_user_model().objects.create_user(
            username="policy-user-terms",
            password="secret123",
            is_staff=False,
        )
        client = self.client_class()
        client.force_login(non_staff)

        response = client.post(reverse("typical_service_term_move_down", args=[first.pk]))

        self.assertEqual(response.status_code, 302)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.position, 1)
        self.assertEqual(second.position, 2)


class SpecialtyTariffViewsTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="policy-admin-3",
            password="secret123",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.company = GroupMember.objects.create(
            short_name="ACME",
            country_name="Россия",
            position=1,
        )
        self.direction = OrgUnit.objects.create(
            company=self.company,
            department_name="Налоговое консультирование",
            unit_type="expertise",
            position=1,
        )
        self.direction_2 = OrgUnit.objects.create(
            company=self.company,
            department_name="Сопровождение сделок",
            unit_type="expertise",
            position=2,
        )
        self.policy_direction_1 = ExpertiseDirection.objects.create(
            name="Налоги",
            short_name="TAX",
            position=1,
        )
        self.policy_direction_2 = ExpertiseDirection.objects.create(
            name="Сделки",
            short_name="M&A",
            position=2,
        )
        self.specialty_1 = ExpertSpecialty.objects.create(
            specialty="Налоговый due diligence",
            expertise_direction=self.direction,
            expertise_dir=self.policy_direction_1,
            position=1,
        )
        self.specialty_2 = ExpertSpecialty.objects.create(
            specialty="Трансфертное ценообразование",
            expertise_direction=self.direction,
            expertise_dir=self.policy_direction_1,
            position=2,
        )
        self.specialty_3 = ExpertSpecialty.objects.create(
            specialty="M&A",
            expertise_direction=self.direction_2,
            expertise_dir=self.policy_direction_2,
            position=3,
        )
        self.currency = OKVCurrency.objects.create(
            code_numeric="978",
            code_alpha="EUR",
            name="Евро",
            position=1,
        )

    def test_policy_partial_renders_specialty_tariffs_table(self):
        item = SpecialtyTariff.objects.create(
            specialty_group="Налоговые специалисты",
            daily_rate_tkp_eur="1500.00",
            daily_rate_ss="1250.00",
            currency=self.currency,
            position=1,
        )
        item.specialties.set([self.specialty_1, self.specialty_2, self.specialty_3])

        response = self.client.get(reverse("policy_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Тарифы специальностей")
        self.assertContains(response, "Налоговые специалисты")
        self.assertContains(response, "Налоговый due diligence")
        self.assertContains(response, "Трансфертное ценообразование")
        self.assertContains(response, "TAX, M&amp;A")
        self.assertContains(response, "1\xa0250,00 EUR")
        self.assertNotContains(response, "<th style=\"vertical-align: top;\">Валюта</th>", html=False)
        self.assertContains(response, 'id="specialty-tariffs-actions"', html=False)
        self.assertContains(response, 'id="specialty-tariffs-specialties-toggle"', html=False)

    def test_create_specialty_tariff_saves_row(self):
        response = self.client.post(
            reverse("specialty_tariff_form_create"),
            {
                "specialty_group": "Сделки",
                "specialties": [str(self.specialty_1.pk), str(self.specialty_2.pk), str(self.specialty_3.pk)],
                "daily_rate_tkp_eur": "1 500,50",
                "daily_rate_ss": "1200,25",
                "currency": self.currency.pk,
            },
        )

        self.assertEqual(response.status_code, 200)
        item = SpecialtyTariff.objects.get()
        self.assertEqual(item.specialty_group, "Сделки")
        self.assertEqual(item.expertise_direction_display, "TAX, M&A")
        self.assertEqual(str(item.daily_rate_tkp_eur), "1500.50")
        self.assertEqual(str(item.daily_rate_ss), "1200.25")
        self.assertEqual(item.currency, self.currency)
        self.assertEqual(item.created_by, self.user)
        self.assertEqual(item.position, 1)
        self.assertCountEqual(
            item.specialties.values_list("pk", flat=True),
            [self.specialty_1.pk, self.specialty_2.pk, self.specialty_3.pk],
        )

    def test_create_specialty_tariff_uses_unique_expertise_values(self):
        response = self.client.post(
            reverse("specialty_tariff_form_create"),
            {
                "specialty_group": "Налоги",
                "specialties": [str(self.specialty_1.pk), str(self.specialty_2.pk)],
                "daily_rate_tkp_eur": "900,00",
                "daily_rate_ss": "800,00",
                "currency": self.currency.pk,
            },
        )

        self.assertEqual(response.status_code, 200)
        item = SpecialtyTariff.objects.get(specialty_group="Налоги")
        self.assertEqual(item.expertise_direction_display, "TAX")


class TariffViewsTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="policy-admin-4",
            password="secret123",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.product = Product.objects.create(
            short_name="TAR",
            name_en="Tariff product",
            display_name="Tariff product",
            name_ru="Тарифный продукт",
            service_type="Консалтинг",
            position=1,
        )
        self.section = TypicalSection.objects.create(
            product=self.product,
            code="TS1",
            short_name="tariff-section",
            short_name_ru="tariff-section-ru",
            name_en="Tariff section EN",
            name_ru="Тарифный раздел",
            accounting_type="Раздел",
            position=1,
        )

    def test_policy_partial_renders_tariff_days_column(self):
        Tariff.objects.create(
            product=self.product,
            section=self.section,
            base_rate_vpm="10.00",
            service_hours=8,
            service_days_tkp=5,
            created_by=self.user,
            position=1,
        )

        response = self.client.get(reverse("policy_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Объем услуг в днях для ТКП")
        self.assertContains(response, ">5<", html=False)

    def test_create_tariff_saves_service_days_tkp(self):
        response = self.client.post(
            reverse("tariff_form_create"),
            {
                "product": self.product.pk,
                "section": self.section.pk,
                "base_rate_vpm": "15.00",
                "service_hours": "12",
                "service_days_tkp": "7",
            },
        )

        self.assertEqual(response.status_code, 200)
        tariff = Tariff.objects.get()
        self.assertEqual(tariff.service_hours, 12)
        self.assertEqual(tariff.service_days_tkp, 7)

    def test_move_up_normalizes_positions_before_reorder(self):
        first = Tariff.objects.create(
            product=self.product,
            section=self.section,
            base_rate_vpm="10.00",
            service_hours=8,
            service_days_tkp=2,
            created_by=self.user,
            position=1,
        )
        second = Tariff.objects.create(
            product=self.product,
            section=self.section,
            base_rate_vpm="12.00",
            service_hours=10,
            service_days_tkp=3,
            created_by=self.user,
            position=3,
        )

        response = self.client.post(reverse("tariff_move_up", args=[second.pk]))

        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.position, 2)
        self.assertEqual(second.position, 1)

    def test_policy_partial_orders_tariff_groups_by_employee_position(self):
        other_user = get_user_model().objects.create_user(
            username="policy-admin-5",
            password="secret123",
            is_staff=True,
        )
        Employee.objects.create(user=self.user, job_title="Руководитель 1", position=2)
        Employee.objects.create(user=other_user, job_title="Руководитель 2", position=1)

        first = Tariff.objects.create(
            product=self.product,
            section=self.section,
            base_rate_vpm="10.00",
            service_hours=8,
            service_days_tkp=2,
            created_by=self.user,
            position=1,
        )
        second = Tariff.objects.create(
            product=self.product,
            section=self.section,
            base_rate_vpm="12.00",
            service_hours=10,
            service_days_tkp=3,
            created_by=other_user,
            position=1,
        )

        admin_user = get_user_model().objects.create_superuser(
            username="policy-superuser",
            email="superuser@example.com",
            password="secret123",
        )
        client = self.client_class()
        client.force_login(admin_user)

        response = client.get(reverse("policy_partial"))

        self.assertEqual(response.status_code, 200)
        tariffs = list(response.context["tariffs"])
        self.assertEqual([item.pk for item in tariffs], [second.pk, first.pk])

    def test_tariff_verbose_name_plural_matches_application(self):
        self.assertEqual(Tariff._meta.verbose_name_plural, "Тарифы разделов (услуг)")


class TariffAdminTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.superuser = user_model.objects.create_superuser(
            username="admin-root",
            email="root@example.com",
            password="secret123",
        )
        self.owner_first = user_model.objects.create_user(
            username="dept-head-first",
            password="secret123",
            is_staff=True,
        )
        self.owner_second = user_model.objects.create_user(
            username="dept-head-second",
            password="secret123",
            is_staff=True,
        )
        self.first_profile = Employee.objects.create(
            user=self.owner_first,
            job_title="Первый руководитель",
            position=1,
        )
        self.second_profile = Employee.objects.create(
            user=self.owner_second,
            job_title="Второй руководитель",
            position=2,
        )
        self.product = Product.objects.create(
            short_name="TAR-ADMIN",
            name_en="Tariff product admin",
            display_name="Tariff product admin",
            name_ru="Тарифный продукт админ",
            service_type="Консалтинг",
            position=1,
        )
        self.section = TypicalSection.objects.create(
            product=self.product,
            code="TSA",
            short_name="tariff-section-admin",
            short_name_ru="tariff-section-admin-ru",
            name_en="Tariff section admin EN",
            name_ru="Тарифный раздел админ",
            accounting_type="Раздел",
            position=1,
        )
        self.first_tariff = Tariff.objects.create(
            product=self.product,
            section=self.section,
            base_rate_vpm="10.00",
            service_hours=8,
            service_days_tkp=2,
            created_by=self.owner_first,
            position=1,
        )
        self.second_tariff = Tariff.objects.create(
            product=self.product,
            section=self.section,
            base_rate_vpm="12.00",
            service_hours=10,
            service_days_tkp=3,
            created_by=self.owner_second,
            position=1,
        )
        self.client.force_login(self.superuser)

    def test_admin_move_owner_down_swaps_group_positions(self):
        response = self.client.post(
            reverse("admin:policy_app_tariff_move_owner_down", args=[self.first_tariff.pk])
        )

        self.assertEqual(response.status_code, 302)
        self.first_profile.refresh_from_db()
        self.second_profile.refresh_from_db()
        self.assertEqual(self.first_profile.position, 2)
        self.assertEqual(self.second_profile.position, 1)

    def test_admin_move_owner_down_rejects_get(self):
        response = self.client.get(
            reverse("admin:policy_app_tariff_move_owner_down", args=[self.first_tariff.pk])
        )

        self.assertEqual(response.status_code, 405)
        self.first_profile.refresh_from_db()
        self.second_profile.refresh_from_db()
        self.assertEqual(self.first_profile.position, 1)
        self.assertEqual(self.second_profile.position, 2)

    def test_admin_move_owner_down_requires_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.superuser)

        response = csrf_client.post(
            reverse("admin:policy_app_tariff_move_owner_down", args=[self.first_tariff.pk])
        )

        self.assertEqual(response.status_code, 403)
        self.first_profile.refresh_from_db()
        self.second_profile.refresh_from_db()
        self.assertEqual(self.first_profile.position, 1)
        self.assertEqual(self.second_profile.position, 2)
