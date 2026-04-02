from django.contrib.auth import get_user_model
from django.test import TestCase
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
)


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
            report_title="Итоговый отчет",
            position=1,
        )

        response = self.client.get(reverse("policy_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Цели услуг и названия отчетов")
        self.assertContains(response, "Подготовка заключения")
        self.assertContains(response, 'id="service-goal-reports-actions"', html=False)

    def test_create_service_goal_report_saves_row(self):
        response = self.client.post(
            reverse("service_goal_report_form_create"),
            {
                "product": self.product.pk,
                "service_goal": "Подготовка документов",
                "report_title": "Отчет по документам",
            },
        )

        self.assertEqual(response.status_code, 200)
        item = ServiceGoalReport.objects.get()
        self.assertEqual(item.product, self.product)
        self.assertEqual(item.service_goal, "Подготовка документов")
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
            report_title="Первый отчет",
            position=1,
        )
        second = ServiceGoalReport.objects.create(
            product=other_product,
            service_goal="Вторая цель",
            report_title="Второй отчет",
            position=2,
        )

        response = self.client.post(reverse("service_goal_report_move_up", args=[second.pk]))

        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.position, 2)
        self.assertEqual(second.position, 1)


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
        response = self.client.post(
            reverse("typical_service_composition_form_create"),
            {
                "product": self.product.pk,
                "section": self.section.pk,
                "service_composition": "Этап 1\nЭтап 2",
            },
        )

        self.assertEqual(response.status_code, 200)
        item = TypicalServiceComposition.objects.get()
        self.assertEqual(item.product, self.product)
        self.assertEqual(item.section, self.section)
        self.assertEqual(item.service_composition, "Этап 1\nЭтап 2")
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
