from django.contrib.auth import get_user_model
from django.test import Client, TestCase
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
from users_app.models import Employee


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
        self.assertContains(response, "<th>ТКП</th>", html=False)
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

    def test_non_staff_user_cannot_reorder_service_goal_reports(self):
        first = ServiceGoalReport.objects.create(
            product=self.product,
            service_goal="Первая цель",
            report_title="Первый отчет",
            position=1,
        )
        second = ServiceGoalReport.objects.create(
            product=self.product,
            service_goal="Вторая цель",
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
