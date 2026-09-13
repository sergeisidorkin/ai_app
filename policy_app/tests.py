import csv
import copy
import io
import json
import re
import unittest
from unittest import mock
from html import unescape
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from docx import Document
from openpyxl import Workbook, load_workbook

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import caches
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import QueryDict
from django.test import (
    Client,
    RequestFactory,
    TestCase,
    TransactionTestCase,
    override_settings,
)
from django.test.utils import CaptureQueriesContext
from django.template.loader import render_to_string
from django.urls import reverse
from redis.exceptions import RedisError

from classifiers_app.models import OKVCurrency
from experts_app.models import ExpertProfile, ExpertProfileSpecialty, ExpertSpecialty
from group_app.models import GroupMember, OrgUnit
from policy_app.forms import (
    ProductForm,
    ReportStructureForm,
    SectionStructureForm,
    ServiceGoalReportForm,
    TariffForm,
    TypicalServiceCompositionForm,
)
from policy_app.models import (
    ConsultingDirection,
    ConsultingDirectionType,
    ConsultingServiceSubtype,
    ConsultingServiceType,
    DEPARTMENT_HEAD_GROUP,
    ExpertiseDirection,
    Product,
    ReportStructure,
    SectionStructure,
    ServiceGoalReport,
    SpecialtyTariff,
    Tariff,
    TypicalSection,
    TypicalSectionSpecialty,
    TypicalServiceComposition,
    TypicalServiceTerm,
    ensure_system_dsc_section,
)
from users_app.models import Employee
from policy_app import cache as policy_cache
from policy_app import signals as policy_signals
from policy_app import views as policy_views
from core import context_processors as core_context_processors


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
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                columns = {
                    column.name
                    for column in connection.introspection.get_table_description(
                        cursor,
                        "experts_app_expertspecialty",
                    )
                }
                if "specialization_area" in columns:
                    cursor.execute(
                        "ALTER TABLE experts_app_expertspecialty "
                        "ALTER COLUMN specialization_area SET DEFAULT ''"
                    )

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


class SystemDscMigrationTests(TransactionTestCase):
    migrate_from = ("policy_app", "0044_typicalserviceterm_source_data_weeks")
    migrate_to = ("policy_app", "0045_typicalsection_is_system_dsc")

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.migrate([self.migrate_from])
        old_apps = self.executor.loader.project_state([self.migrate_from]).apps

        Product = old_apps.get_model("policy_app", "Product")
        TypicalSection = old_apps.get_model("policy_app", "TypicalSection")

        product = Product.objects.create(
            short_name="MIG-DSC",
            name_en="Migration DSC",
            display_name="Migration DSC",
            name_ru="Миграция DSC",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
            position=1,
        )
        self.lower_dsc_id = TypicalSection.objects.create(
            product_id=product.pk,
            code="dsc",
            short_name="manual-lower",
            short_name_ru="ручной lower",
            name_en="Manual lower",
            name_ru="Ручной lower",
            accounting_type="Услуги",
            position=1,
        ).pk
        self.upper_dsc_id = TypicalSection.objects.create(
            product_id=product.pk,
            code="DSC",
            short_name="manual-upper",
            short_name_ru="ручной upper",
            name_en="Manual upper",
            name_ru="Ручной upper",
            accounting_type="Услуги",
            position=2,
        ).pk
        TypicalSection.objects.create(
            product_id=product.pk,
            code="REG",
            short_name="regular",
            short_name_ru="обычный",
            name_en="Regular",
            name_ru="Обычный",
            accounting_type="Раздел",
            position=3,
        )

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_migration_deduplicates_case_insensitive_dsc_before_canonical_save(self):
        self.executor.loader.build_graph()
        self.executor.migrate([self.migrate_to])
        new_apps = self.executor.loader.project_state([self.migrate_to]).apps

        TypicalSection = new_apps.get_model("policy_app", "TypicalSection")

        sections = list(TypicalSection.objects.order_by("position", "id"))
        self.assertEqual([section.code for section in sections], ["DSC", "REG"])
        self.assertEqual(sections[0].pk, self.lower_dsc_id)
        self.assertTrue(sections[0].is_system)
        self.assertEqual(sections[0].name_ru, "Описание продукта")
        self.assertFalse(TypicalSection.objects.filter(pk=self.upper_dsc_id).exists())


class ConsultingCatalogBackfillMigrationTests(TransactionTestCase):
    migrate_from = ("policy_app", "0038_product_consulting_service_fields")
    migrate_to = ("policy_app", "0040_backfill_consulting_catalog_refs")

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.migrate([self.migrate_from])
        old_apps = self.executor.loader.project_state([self.migrate_from]).apps

        Product = old_apps.get_model("policy_app", "Product")
        self.product = Product.objects.create(
            short_name="MIG-CAT",
            name_en="Migration catalog",
            display_name="Migration catalog",
            name_ru="Миграционный каталог",
            consulting_type="Горный",
            service_category="Аудит",
            service_code="A",
            service_subtype="Аудит проектных решений",
            position=1,
        )

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_migration_seeds_catalog_and_links_products(self):
        self.executor.loader.build_graph()
        self.executor.migrate([self.migrate_to])
        new_apps = self.executor.loader.project_state([self.migrate_to]).apps

        Product = new_apps.get_model("policy_app", "Product")
        ConsultingDirection = new_apps.get_model("policy_app", "ConsultingDirection")
        ConsultingDirectionType = new_apps.get_model("policy_app", "ConsultingDirectionType")
        ConsultingServiceType = new_apps.get_model("policy_app", "ConsultingServiceType")
        ConsultingServiceSubtype = new_apps.get_model("policy_app", "ConsultingServiceSubtype")

        migrated = Product.objects.get(pk=self.product.pk)
        self.assertIsNotNone(migrated.consulting_type_ref_id)
        self.assertIsNotNone(migrated.service_category_ref_id)
        self.assertIsNotNone(migrated.service_subtype_ref_id)
        self.assertEqual(ConsultingDirection.objects.count(), 1)
        self.assertTrue(ConsultingDirectionType.objects.filter(name="Горный").exists())
        self.assertTrue(
            ConsultingServiceType.objects.filter(name="Аудит", code="A").exists()
        )
        self.assertTrue(
            ConsultingServiceSubtype.objects.filter(name="Аудит проектных решений").exists()
        )


class PolicyTablePartialEndpointsTests(TestCase):
    endpoint_cases = (
        ("policy_consulting_directions_table", "policy-consulting-directions-section", "Направления консалтинга"),
        ("policy_expertise_directions_table", "policy-expertise-directions-section", "Направления экспертизы"),
        ("policy_expert_specialties_table", "policy-expert-specialties-section", "Специальности исполнителей"),
        ("policy_products_table", "policy-products-section", "Типовые продукты"),
        ("policy_service_goal_reports_table", "policy-service-goal-reports-section", "Цели услуг и названия отчетов"),
        ("policy_typical_sections_table", "policy-typical-sections-section", "Типовые разделы (услуги)"),
        (
            "policy_section_structures_table",
            "policy-section-structures-section",
            "Типовая структура раздела (состава услуг)",
        ),
        ("policy_report_structures_table", "policy-report-structures-section", "Типовая структура отчета"),
        (
            "policy_typical_service_compositions_table",
            "policy-typical-service-compositions-section",
            "Типовой состав услуг в ТКП",
        ),
        ("policy_typical_service_terms_table", "policy-typical-service-terms-section", "Типовые сроки оказания услуг"),
        ("policy_grades_table", "policy-grades-section", "Грейды"),
        ("policy_specialty_tariffs_table", "policy-specialty-tariffs-section", "Тарифы специальностей"),
        ("policy_tariffs_table", "policy-tariffs-section", "Тарифы разделов (услуг)"),
    )

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="policy-table-partials-staff",
            password="secret123",
            is_staff=True,
        )
        self.client.force_login(self.user)

    def test_each_table_endpoint_renders_its_wrapper_and_heading(self):
        for endpoint_name, wrapper_id, heading in self.endpoint_cases:
            with self.subTest(endpoint=endpoint_name):
                response = self.client.get(reverse(endpoint_name))

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, f'id="{wrapper_id}"', html=False)
                self.assertContains(response, heading)
                self.assertNotContains(response, 'id="policy-pane"', html=False)

    def test_policy_partial_still_contains_every_table_section(self):
        response = self.client.get(reverse("policy_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="policy-pane"', html=False)
        self.assertContains(response, "Спецификации продуктов")
        self.assertContains(response, "Общие настройки продуктов")
        for _, wrapper_id, heading in self.endpoint_cases:
            with self.subTest(wrapper=wrapper_id):
                self.assertContains(response, f'id="{wrapper_id}"', html=False)
                self.assertContains(response, heading)

    def test_anonymous_user_is_redirected_from_each_table_endpoint(self):
        anonymous_client = Client()

        for endpoint_name, _, _ in self.endpoint_cases:
            with self.subTest(endpoint=endpoint_name):
                response = anonymous_client.get(reverse(endpoint_name))

                self.assertEqual(response.status_code, 302)

    def test_table_endpoints_reject_non_get_requests(self):
        for endpoint_name, _, _ in self.endpoint_cases:
            with self.subTest(endpoint=endpoint_name):
                response = self.client.post(reverse(endpoint_name))

                self.assertEqual(response.status_code, 405)

    def test_report_structure_endpoint_preserves_computed_numbering(self):
        product = Product.objects.create(
            short_name="RPT-PARTIAL",
            name_en="Report partial",
            display_name="Report partial",
            name_ru="Структура отчета",
            position=1,
        )
        ReportStructure.objects.create(
            product=product,
            level=1,
            code="SEC",
            name="Раздел",
            position=1,
        )
        ReportStructure.objects.create(
            product=product,
            level=2,
            code="SUB",
            name="Подраздел",
            position=2,
        )

        response = self.client.get(reverse("policy_report_structures_table"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1.1")


class PolicyStageFiveQueryBudgetTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="policy-stage-five-admin",
            password="secret123",
            email="stage-five@example.test",
        )
        self.client.force_login(self.user)
        self.owner = GroupMember.objects.create(
            short_name="Stage Five Owner",
            country_name="Test",
            position=1,
        )

    def _endpoint_query_count(self, url_name):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse(url_name))
        self.assertEqual(response.status_code, 200)
        return len(queries), response

    def test_products_query_budget_is_constant_for_one_and_fifty_rows(self):
        def create_products(start, stop):
            products = Product.objects.bulk_create(
                [
                    Product(
                        short_name=f"S5-P-{index:03d}",
                        name_en=f"Product {index}",
                        name_ru=f"Продукт {index}",
                        position=index,
                    )
                    for index in range(start, stop)
                ]
            )
            for product in products:
                product.owners.add(self.owner)

        create_products(1, 2)
        one_count, _ = self._endpoint_query_count("policy_products_table")
        create_products(2, 51)
        fifty_count, response = self._endpoint_query_count("policy_products_table")

        self.assertEqual((one_count, fifty_count), (5, 5))
        self.assertEqual(len(response.context["products"]), 25)
        self.assertLessEqual(len(response.context["products"]), policy_views.POLICY_TABLE_PAGE_SIZE)

    def test_owner_display_fallbacks_keep_deterministic_order(self):
        later_owner = GroupMember.objects.create(
            short_name="Later Owner",
            country_name="Test",
            position=2,
        )
        product = Product.objects.create(
            short_name="S5-FALLBACK-P",
            name_en="Fallback",
            name_ru="Fallback",
            position=1,
        )
        expertise = ExpertiseDirection.objects.create(
            name="Fallback",
            short_name="S5-FALLBACK-E",
            position=1,
        )
        product.owners.add(later_owner, self.owner)
        expertise.owners.add(later_owner, self.owner)

        with self.assertNumQueries(1):
            self.assertEqual(product.owner_display, "Stage Five Owner, Later Owner")
        with self.assertNumQueries(1):
            self.assertEqual(expertise.owner_display, "Stage Five Owner, Later Owner")

    def test_expertise_query_budget_is_constant_for_one_and_fifty_rows(self):
        def create_directions(start, stop):
            directions = ExpertiseDirection.objects.bulk_create(
                [
                    ExpertiseDirection(
                        name=f"Stage five direction {index}",
                        short_name=f"S5-E-{index:03d}",
                        position=index,
                    )
                    for index in range(start, stop)
                ]
            )
            for direction in directions:
                direction.owners.add(self.owner)

        create_directions(1, 2)
        one_count, _ = self._endpoint_query_count("policy_expertise_directions_table")
        create_directions(2, 51)
        fifty_count, _ = self._endpoint_query_count("policy_expertise_directions_table")

        self.assertEqual((one_count, fifty_count), (4, 4))

    def test_consulting_query_budget_is_constant_for_one_and_fifty_rows(self):
        def create_directions(start, stop):
            for index in range(start, stop):
                direction = ConsultingDirection.objects.create(position=index)
                consulting_type = ConsultingDirectionType.objects.create(
                    direction=direction,
                    name=f"Stage five consulting {index}",
                    position=1,
                )
                service_type = ConsultingServiceType.objects.create(
                    direction=direction,
                    consulting_type=consulting_type,
                    name=f"Stage five service {index}",
                    code=f"S5-{index}",
                    position=1,
                )
                ConsultingServiceSubtype.objects.create(
                    direction=direction,
                    service_type=service_type,
                    name=f"Stage five subtype {index}",
                    position=1,
                )

        create_directions(1, 2)
        one_count, _ = self._endpoint_query_count("policy_consulting_directions_table")
        create_directions(2, 51)
        fifty_count, _ = self._endpoint_query_count("policy_consulting_directions_table")

        self.assertEqual((one_count, fifty_count), (6, 6))
        with self.assertNumQueries(4):
            directions = list(
                policy_views._policy_consulting_directions_context(None)[
                    "consulting_directions"
                ]
            )
        with self.assertNumQueries(0):
            for direction in directions:
                self.assertTrue(direction.consulting_types_display)
                self.assertTrue(direction.service_types_display)
                self.assertTrue(direction.service_codes_display)
                self.assertTrue(direction.service_subtypes_display)
                self.assertTrue(direction.table_rows)

    def test_specialty_tariff_query_budget_is_constant_for_one_and_fifty_rows(self):
        expertise = ExpertiseDirection.objects.create(
            name="Stage five tariff expertise",
            short_name="S5-T",
            position=1,
        )

        def create_tariffs(start, stop):
            for index in range(start, stop):
                specialty = ExpertSpecialty.objects.create(
                    specialty=f"Stage five specialty {index}",
                    expertise_dir=expertise,
                    position=index,
                )
                tariff = SpecialtyTariff.objects.create(
                    specialty_group=f"Stage five group {index}",
                    created_by=self.user,
                    position=index,
                )
                tariff.specialties.add(specialty)

        create_tariffs(1, 2)
        one_count, _ = self._endpoint_query_count("policy_specialty_tariffs_table")
        create_tariffs(2, 51)
        fifty_count, response = self._endpoint_query_count("policy_specialty_tariffs_table")

        self.assertEqual((one_count, fifty_count), (4, 4))
        self.assertContains(response, "S5-T")
        with self.assertNumQueries(2):
            tariffs = list(policy_views._get_specialty_tariffs_for_user(self.user))
        with self.assertNumQueries(0):
            for tariff in tariffs:
                self.assertTrue(tariff.display_specialties)
                self.assertEqual(tariff.expertise_direction_display, "S5-T")


class PolicyStageFiveRoutingAndReorderTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="policy-stage-five-routing",
            password="secret123",
            is_staff=True,
        )
        self.client.force_login(self.user)

    def test_context_processor_fast_path_is_route_scoped(self):
        factory = RequestFactory()

        table_request = factory.get("/policy/policy/tables/products/")
        lazy_request = factory.get(
            "/policy/policy/partial/",
            HTTP_HX_REQUEST="true",
        )
        catalog_request = factory.get("/policy/policy/filter-catalog/")
        workspace_request = factory.get("/policy/policy/product/12/")
        legacy_partial_request = factory.get("/policy/policy/partial/")
        product_form_request = factory.get("/policy/policy/product/create/")
        product_edit_request = factory.get("/policy/policy/product/12/edit/")
        home_request = factory.get("/")
        requests_request = factory.get("/requests/partial/")

        for request in (table_request, lazy_request, catalog_request, workspace_request):
            with self.subTest(path=request.path, htmx=request.headers.get("HX-Request")):
                self.assertTrue(core_context_processors._is_policy_lightweight_request(request))
        for request in (
            legacy_partial_request,
            product_form_request,
            product_edit_request,
            home_request,
            requests_request,
        ):
            with self.subTest(path=request.path):
                self.assertFalse(core_context_processors._is_policy_lightweight_request(request))

    def test_product_reorder_normalizes_in_bulk_and_keeps_boundaries(self):
        products = Product.objects.bulk_create(
            [
                Product(
                    short_name=f"S5-MOVE-P-{index:03d}",
                    name_en=f"Product {index}",
                    name_ru=f"Продукт {index}",
                    position=index * 2,
                )
                for index in range(1, 52)
            ]
        )

        with CaptureQueriesContext(connection) as queries:
            response = self.client.post(
                reverse("product_move_up", args=[products[0].pk]),
                HTTP_HX_REQUEST="true",
            )

        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 8)
        self.assertEqual(
            list(Product.objects.order_by("position", "id").values_list("position", flat=True)),
            list(range(1, 52)),
        )
        self.assertEqual(Product.objects.order_by("position", "id").first().pk, products[0].pk)

        response = self.client.post(
            reverse("product_move_down", args=[products[-1].pk]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Product.objects.order_by("position", "id").last().pk, products[-1].pk)

    def test_section_reorder_is_product_scoped_and_bulk_normalized(self):
        product = Product.objects.create(
            short_name="S5-MOVE-SECTIONS",
            name_en="Sections",
            name_ru="Разделы",
            position=1,
        )
        other_product = Product.objects.create(
            short_name="S5-MOVE-OTHER",
            name_en="Other",
            name_ru="Другой",
            position=2,
        )
        sections = TypicalSection.objects.bulk_create(
            [
                TypicalSection(
                    product=product,
                    code=f"S5-{index:03d}",
                    short_name=f"s5-{index:03d}",
                    name_en=f"Section {index}",
                    name_ru=f"Раздел {index}",
                    position=index * 2,
                )
                for index in range(1, 52)
            ]
        )
        other = TypicalSection.objects.create(
            product=other_product,
            code="OTHER",
            short_name="other",
            name_en="Other",
            name_ru="Другой",
            position=99,
        )

        with CaptureQueriesContext(connection) as queries:
            response = self.client.post(
                reverse("section_move_up", args=[sections[-1].pk]),
                HTTP_HX_REQUEST="true",
            )

        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 10)
        ordered = list(
            TypicalSection.objects.filter(product=product)
            .order_by("position", "id")
            .values_list("pk", "position")
        )
        self.assertEqual([position for _, position in ordered], list(range(1, 52)))
        self.assertEqual(ordered[-2][0], sections[-1].pk)
        other.refresh_from_db()
        self.assertEqual(other.position, 99)


@unittest.skipUnless(connection.vendor == "postgresql", "PostgreSQL planner test")
class PolicyPostgreSQLPlannerTests(TestCase):
    def test_filtered_typical_section_query_supports_analyze_buffers(self):
        product = Product.objects.create(
            short_name="S5-PLAN",
            name_en="Planner",
            name_ru="Планировщик",
            position=1,
        )
        TypicalSection.objects.create(
            product=product,
            code="S5-PLAN",
            short_name="plan",
            name_en="Planner",
            name_ru="Планировщик",
            position=1,
        )

        plan = (
            policy_views._policy_typical_sections_queryset()
            .filter(product=product)
            .explain(analyze=True, buffers=True)
        )

        self.assertIn("Planning Time", plan)
        self.assertIn("Execution Time", plan)
        self.assertIn("Scan", plan)


class PolicyLazyLoadingContractTests(TestCase):
    ordered_keys = [
        "products",
        "service-goal-reports",
        "typical-sections",
        "section-structures",
        "report-structures",
        "typical-service-compositions",
        "typical-service-terms",
        "tariffs",
        "consulting-directions",
        "expertise-directions",
        "expert-specialties",
        "specialty-tariffs",
        "grades",
    ]

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="policy-lazy-staff",
            password="secret123",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.product = Product.objects.create(
            short_name="LAZY",
            name_en="Lazy loading",
            display_name="Lazy loading",
            name_ru="Ленивая загрузка",
            position=1,
        )

    def test_htmx_partial_is_small_ordered_placeholder_shell(self):
        response = self.client.get(
            reverse("policy_partial"),
            HTTP_HX_REQUEST="true",
        )
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-policy-lazy-shell="1"', html=False)
        self.assertEqual(html.count('data-policy-lazy-placeholder="1"'), 13)
        self.assertNotIn("<table", html)
        self.assertNotIn('data-policy-filter-row="1"', html)
        self.assertNotIn("data-edit-url=", html)
        keys = re.findall(r'data-policy-table-key="([^"]+)"', html)
        self.assertEqual(keys, self.ordered_keys)
        self.assertEqual(html.count('data-policy-lazy-priority="immediate"'), 1)
        self.assertEqual(html.count('data-policy-lazy-priority="deferred"'), 12)
        self.assertEqual(html.count("table-section-title"), 13)
        self.assertEqual(html.count("bi-table me-2"), 13)
        self.assertEqual(html.count('class="card shadow-sm policy-group-card"'), 2)
        self.assertEqual(html.count("bi-box-seam me-2"), 1)
        self.assertEqual(html.count("bi-sliders me-2"), 1)
        self.assertIn("Спецификации продуктов", html)
        self.assertIn("Общие настройки продуктов", html)
        self.assertIn("Типовые продукты", html)
        self.assertNotIn("fw-semibold", html)

    def test_non_htmx_partial_remains_full_legacy_compositor(self):
        response = self.client.get(reverse("policy_partial"))
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="policy-pane"', html=False)
        self.assertContains(response, 'id="policy-products-section"', html=False)
        self.assertContains(response, "LAZY")
        self.assertIn("<table", html)
        self.assertNotIn('data-policy-lazy-placeholder="1"', html)

        shell = self.client.get(
            reverse("policy_partial"),
            HTTP_HX_REQUEST="true",
        )
        self.assertLess(len(shell.content), len(response.content))

    def test_panel_has_show_only_trigger_contract(self):
        html = render_to_string("policy_app/panel.html")

        self.assertIn('data-policy-shell-url="', html)
        self.assertIn('data-policy-shell-state="pending"', html)
        self.assertNotIn('hx-trigger="load"', html)
        self.assertNotIn('hx-get="', html)

    def test_lazy_js_has_filtered_queue_retry_and_once_guards(self):
        root = Path(__file__).resolve().parents[1]
        source = (
            root / "core" / "static" / "core" / "js" / "policy-panels.js"
        ).read_text()
        css = (root / "core" / "static" / "core" / "css" / "site.css").read_text()

        self.assertIn("POLICY_LAZY_REFRESH_CONCURRENCY = 2", source)
        self.assertIn("new IntersectionObserver", source)
        self.assertIn("rootMargin: '500px 0px'", source)
        self.assertIn("data-policy-lazy-retry", source)
        self.assertIn("policyLazyPlaceholderUrl(placeholder)", source)
        self.assertIn("updateAllPolicyLazyPlaceholderStates()", source)
        self.assertIn("wrapper.matches('[data-policy-lazy-placeholder=\"1\"]')", source)
        self.assertIn("document.addEventListener('shown.bs.tab'", source)
        self.assertIn("window.location.hash === '#policy'", source)
        self.assertIn("policyLazyObserver.unobserve(placeholder)", source)
        self.assertIn("min-height: 360px", css)
        self.assertIn("contain-intrinsic-size: auto 360px", css)
        self.assertIn(".policy-table-placeholder > .table-section-header", css)

    def test_product_catalog_requires_authoritative_json_for_lazy_panel(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "core"
            / "static"
            / "core"
            / "js"
            / "policy-panels.js"
        ).read_text()

        self.assertIn("window.__policyProductCatalogAuthoritative === true", source)
        self.assertIn("return isLegacyFullPanel ? products : []", source)
        self.assertNotIn("window.__policyProductCatalog = products", source)
        self.assertIn("requiresAuthoritativePolicyProductCatalog(root)", source)
        self.assertIn("schedulePolicyProductCatalogRetry()", source)
        self.assertIn("policyProductCatalogRequest", source)
        self.assertIn("policyProductCatalogNeedsRefresh", source)
        self.assertIn("Math.min(30000", source)

    def test_stale_lazy_response_is_token_guarded_and_requeued(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "core"
            / "static"
            / "core"
            / "js"
            / "policy-panels.js"
        ).read_text()

        self.assertIn("const policyLazyRequestTokens = new Map()", source)
        self.assertIn("const policyLazyRequestControllers = new Map()", source)
        self.assertIn("policyLazyRequestControllers.get(tableKey)?.abort()", source)
        self.assertIn("nextPolicyLazyRequestToken(tableKey)", source)
        self.assertIn("policyLazyRequestTokens.get(tableKey) !== requestToken", source)
        self.assertIn("current.dataset.policyLazyRequestToken !== String(requestToken)", source)
        self.assertIn("invalidateLoading: true", source)
        self.assertIn("requeueNear: true", source)
        self.assertIn("isPolicyLazyPlaceholderNearViewport", source)
        self.assertIn("headers: { 'HX-Request': 'true'", source)
        self.assertIn("current.replaceWith(replacement)", source)
        self.assertIn("initializeArrivingPolicyFragment(replacement)", source)
        self.assertIn("getPolicyTablePageSize(placeholder)", source)
        self.assertIn("params.set('page_size', pageSize)", source)
        self.assertIn("getPolicyTablePageSize(wrapper)", source)

    def test_dependency_queue_preserves_keys_and_aborts_stale_loaded_requests(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "core"
            / "static"
            / "core"
            / "js"
            / "policy-panels.js"
        ).read_text()

        self.assertIn("const policyManagedOutstandingTableKeys = new Set()", source)
        self.assertIn("const policyLoadedFragmentRequests = new Map()", source)
        self.assertIn("requested.add(tableKey)", source)
        self.assertIn("abortOlderPolicyLoadedFragmentRequests(generation)", source)
        self.assertIn("request.controller.abort()", source)
        self.assertIn("requestGeneration !== policyManagedRefreshGeneration", source)
        self.assertIn("activeRequest.token !== requestToken", source)
        self.assertIn("current.replaceWith(refreshed)", source)
        self.assertIn("initializeArrivingPolicyFragment(refreshed)", source)
        self.assertIn("priority: true", source)
        self.assertNotIn(
            "htmx.ajax('GET', requestUrl,",
            source,
        )

    def test_product_edit_modal_clears_row_selection_on_hide(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "core"
            / "static"
            / "core"
            / "js"
            / "policy-panels.js"
        ).read_text()

        self.assertIn("function forgetPolicyTableSelection(name)", source)
        self.assertIn("function clearPolicyTableSelectionByName(name)", source)
        self.assertIn("function markPolicyModalClearSelectionOnHide(name)", source)
        self.assertIn("modalEl.dataset.policyClearSelectionName = name", source)
        self.assertIn("if (name === 'product-select') {", source)
        self.assertIn("markPolicyModalClearSelectionOnHide(name)", source)
        self.assertIn("document.addEventListener('hidden.bs.modal'", source)
        self.assertIn("modalEl.id !== 'policy-modal'", source)
        self.assertIn("clearPolicyTableSelectionByName(name)", source)


class PolicyProductWorkspaceTests(TestCase):
    workspace_keys = [
        "products",
        "service-goal-reports",
        "typical-sections",
        "section-structures",
        "report-structures",
        "typical-service-compositions",
        "typical-service-terms",
        "tariffs",
    ]

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="policy-workspace-staff",
            password="secret123",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.product = Product.objects.create(
            short_name="WS",
            name_en="Workspace product",
            display_name="Workspace display",
            name_ru="Продукт workspace",
            position=1,
        )
        self.other_product = Product.objects.create(
            short_name="OTHER-WS",
            name_en="Other workspace product",
            display_name="Other display",
            name_ru="Другой продукт workspace",
            position=2,
        )
        ServiceGoalReport.objects.create(
            product=self.product,
            service_goal="Цель WS",
            service_goal_genitive="Цели WS",
            report_title="Титул WS",
            product_name="Имя WS",
            position=1,
        )

    def test_workspace_renders_product_scoped_lazy_shell(self):
        response = self.client.get(reverse("product_workspace", args=[self.product.pk]))
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-policy-workspace="1"', html=False)
        self.assertContains(
            response,
            f'data-policy-workspace-product-id="{self.product.pk}"',
            html=False,
        )
        self.assertContains(response, 'data-header-root-label="Продукты"', html=False)
        self.assertContains(response, 'data-header-current-label="WS Workspace display"', html=False)
        self.assertContains(response, reverse("policy_partial"), html=False)
        self.assertContains(
            response,
            reverse("product_workspace", args=[self.product.pk]),
            html=False,
        )
        self.assertContains(
            response,
            reverse("product_workspace_save", args=[self.product.pk]),
            html=False,
        )
        self.assertContains(response, 'data-policy-workspace-save-url="', html=False)
        self.assertEqual(html.count('data-policy-lazy-placeholder="1"'), 8)
        self.assertNotIn("<table", html)
        keys = re.findall(r'data-policy-table-key="([^"]+)"', html)
        self.assertEqual(keys, self.workspace_keys)
        self.assertNotIn("expertise-directions", keys)
        self.assertNotIn("consulting-directions", keys)
        self.assertNotIn("grades", keys)
        self.assertNotIn("specialty-tariffs", keys)
        self.assertNotIn("expert-specialties", keys)
        self.assertEqual(html.count('data-policy-lazy-priority="immediate"'), 1)
        self.assertEqual(html.count('data-policy-lazy-priority="deferred"'), 7)
        self.assertEqual(html.count("table-section-title"), 8)
        self.assertEqual(html.count("bi-table me-2"), 8)
        self.assertEqual(html.count('class="card shadow-sm policy-group-card"'), 1)
        self.assertEqual(html.count("bi-box-seam me-2"), 1)
        self.assertNotIn("bi-sliders me-2", html)
        self.assertIn("Спецификации продуктов", html)
        self.assertNotIn("Общие настройки продуктов", html)
        self.assertIn("Типовые продукты", html)

    def test_workspace_requires_staff_and_existing_product(self):
        missing = self.client.get(reverse("product_workspace", args=[self.product.pk + 1000]))
        self.assertEqual(missing.status_code, 404)

        anonymous = Client()
        anonymous_response = anonymous.get(reverse("product_workspace", args=[self.product.pk]))
        self.assertEqual(anonymous_response.status_code, 302)

        nonstaff = get_user_model().objects.create_user(
            username="policy-workspace-nonstaff",
            password="secret123",
            is_staff=False,
        )
        self.client.force_login(nonstaff)
        forbidden = self.client.get(reverse("product_workspace", args=[self.product.pk]))
        self.assertEqual(forbidden.status_code, 302)

    def test_products_table_includes_workspace_edit_icon_for_staff(self):
        response = self.client.get(reverse("policy_products_table"))
        html = response.content.decode()

        self.assertContains(response, "product-quick-edit", html=False)
        self.assertContains(response, "product-workspace-edit-cell", html=False)
        self.assertContains(
            response,
            f'data-workspace-url="{reverse("product_workspace", args=[self.product.pk])}"',
            html=False,
        )
        self.assertIn("bi-pencil-square", html)
        self.assertIn("Наименование на английском языке", html)
        short_name_index = html.index("Краткое имя")
        english_index = html.index("Наименование на английском языке")
        pencil_index = html.index("product-workspace-edit-cell")
        self.assertLess(short_name_index, pencil_index)
        self.assertLess(pencil_index, english_index)

        nonstaff = get_user_model().objects.create_user(
            username="policy-workspace-table-nonstaff",
            password="secret123",
            is_staff=False,
        )
        self.client.force_login(nonstaff)
        nonstaff_response = self.client.get(reverse("policy_products_table"))
        self.assertNotContains(nonstaff_response, "product-quick-edit")
        self.assertContains(nonstaff_response, "product-workspace-edit-cell", html=False)

    def test_products_table_filter_keeps_single_product_page(self):
        response = self.client.get(
            reverse("policy_products_table"),
            {"product": self.product.pk},
        )
        html = response.content.decode()

        self.assertContains(response, "WS")
        self.assertNotContains(response, "OTHER-WS")
        self.assertIn(f'data-product-id="{self.product.pk}"', html)
        self.assertNotIn(f'data-product-id="{self.other_product.pk}"', html)

    def test_workspace_js_and_css_contracts(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "core" / "static" / "core" / "js" / "policy-panels.js").read_text()
        css = (root / "core" / "static" / "core" / "css" / "site.css").read_text()

        self.assertIn("function updatePolicyHeaderPath()", source)
        self.assertIn("function getPolicyWorkspaceProduct(root)", source)
        self.assertIn("function ensurePolicyWorkspaceSession(root)", source)
        self.assertIn("function savePolicyWorkspace()", source)
        self.assertIn("function bindPolicyWorkspaceInlineTables(root)", source)
        self.assertIn("service-goal-reports", source)
        self.assertIn("refreshPolicyWorkspaceInlineFragments", source)
        self.assertIn("function cancelPolicyWorkspace()", source)
        self.assertIn("if (!session.isDirty()) {\n      destroyPolicyWorkspaceSession();\n      await loadPolicyCatalogShell();", source)
        self.assertIn("e.detail.parameters.workspace = '1'", source)
        self.assertIn("parsed.searchParams.set('workspace', '1')", source)
        self.assertIn("dataset.policyWorkspace === '1'", source)
        self.assertIn("closest('.product-quick-edit')", source)
        self.assertIn("tr?.dataset?.workspaceUrl", source)
        self.assertIn("leavingWorkspace", source)
        self.assertIn("params.set('workspace', '1')", source)
        self.assertIn("function loadPolicyCatalogShell()", source)
        self.assertIn("display.classList.toggle('readonly-field', !!select.disabled)", source)
        self.assertIn("#policy-modal .policy-product-select-display.readonly-field", css)
        self.assertIn("function scrollPolicyWorkspaceToTop(root)", source)
        self.assertIn('a.nav-link[href="#policy"][data-bs-toggle="tab"]', source)
        self.assertIn("data-policy-workspace-save-btn", source)
        self.assertIn("WorkspaceInlineEditor", source)
        editor_js = (root / "core" / "static" / "core" / "js" / "inline-table-editor.js").read_text()
        self.assertIn("createSession", editor_js)
        self.assertIn("createPolicyProductsAdapter", editor_js)
        self.assertIn("createPolicyServiceGoalReportsAdapter", editor_js)
        self.assertIn("createPolicyReportStructuresAdapter", editor_js)
        self.assertIn("createPolicyReportStructuresAdapter", source)
        self.assertIn("createPolicyTypicalSectionsAdapter", editor_js)
        self.assertIn("createPolicyTypicalSectionsAdapter", source)
        self.assertIn("function attachTypicalSectionRowInsert(section, session)", source)
        self.assertIn("function attachPolicyWorkspaceRowInsert(section, session)", source)
        self.assertIn("function createSectionStructureWorkspaceRow(section, rowId, referenceRow)", source)
        self.assertIn("function createTypicalServiceCompositionWorkspaceRow(section, rowId, referenceRow)", source)
        self.assertIn("function createTariffWorkspaceRow(section, rowId, referenceRow)", source)
        self.assertIn("createPolicyRowInsertButton", source)
        self.assertIn("rowRect.right - iconRect.right", source)
        self.assertIn("wrap.appendChild(rowInsertButton)", source)
        self.assertIn("getTypicalSectionInsertHoverRight", source)
        self.assertIn("getPolicyRowInsertHoverRight", source)
        self.assertIn("function removePolicyInlineNewRow(row)", source)
        self.assertIn("function queuePolicyWorkspaceTypicalSectionDelete(row)", source)
        self.assertIn("forgetPolicyTableSelection(name);\n        ensureActionsVisibility(name);", source)
        self.assertIn("forgetPolicyTableSelection('section-select');", source)
        self.assertIn("markDeletedRow", editor_js)
        self.assertIn("deleted: true", editor_js)
        self.assertIn("function syncTypicalSectionNewRowAfterIds(tbody)", source)
        self.assertIn("isPolicyInlineNewRow(row)", source)
        self.assertIn("button.innerHTML = '<i class=\"bi bi-plus-circle\" aria-hidden=\"true\"></i>';", source)
        self.assertIn("markNewRow", editor_js)
        self.assertIn("removeRow: function (tableKey, rowId)", editor_js)
        self.assertIn("_create_typical_section", (root / "policy_app" / "views.py").read_text())
        self.assertIn("_create_section_structure", (root / "policy_app" / "views.py").read_text())
        self.assertIn("_create_typical_service_composition", (root / "policy_app" / "views.py").read_text())
        self.assertIn("_create_workspace_tariff", (root / "policy_app" / "views.py").read_text())
        self.assertIn("createPolicySectionStructuresAdapter", editor_js)
        self.assertIn("createPolicySectionStructuresAdapter", source)
        self.assertIn("createPolicyTariffsAdapter", editor_js)
        self.assertIn("createPolicyTariffsAdapter", source)
        self.assertIn("createPolicyTypicalServiceTermsAdapter", editor_js)
        self.assertIn("createPolicyTypicalServiceTermsAdapter", source)
        self.assertIn("createPolicyTypicalServiceCompositionsAdapter", editor_js)
        self.assertIn("createPolicyTypicalServiceCompositionsAdapter", source)
        self.assertIn("'typical-service-compositions'", source)
        self.assertIn("function attachPolicyTableHeaderStickyState(section)", source)
        self.assertIn("function initPolicyTableHeaderStickyState(root)", source)
        self.assertIn("function openRichEditor(cell)", editor_js)
        self.assertIn('data-inline-type="rich"', editor_js)
        self.assertIn("expandTypicalServiceCompositionRows", editor_js)
        self.assertIn("setCompositionToolbarVisible", editor_js)
        self.assertIn("inline-table-rich-wrap", editor_js)
        editor_mod = (root / "core" / "static" / "core" / "js" / "service-composition-editor.js").read_text()
        self.assertIn("global.ServiceCompositionEditor", editor_mod)
        self.assertIn("function mount(options)", editor_mod)
        self.assertIn("selectTypicalServiceTermWorkspaceRow", source)
        self.assertIn("typical-service-term-workspace-selected", source)
        self.assertNotIn("item.classList.toggle('table-active', item === row)", source)
        self.assertIn("function sectionOptionLabel", editor_js)
        self.assertNotIn("useVisibleMenu", editor_js)
        self.assertNotIn("inline-table-select-menu", editor_js)
        self.assertIn("section-structures", source)
        self.assertIn("'report-structures'", source)
        self.assertIn("'tariffs'", source)
        self.assertIn("'typical-service-terms'", source)
        self.assertIn("expand: 'left'", editor_js)
        self.assertIn("inline-table-text-input", editor_js)
        self.assertIn("inline-table-number-input", editor_js)
        self.assertIn("inline-table-number-wrap", editor_js)
        self.assertIn("if (textEdit && textEdit.cell === cell) return", editor_js)
        self.assertIn("function getNumberCellRange", editor_js)
        self.assertIn("function applyBulkNumberValue", editor_js)
        self.assertIn("function snapshotBulkNumberOriginals", editor_js)
        self.assertIn("function placeNumberCaretAtEnd", editor_js)
        self.assertIn("textarea.type = 'number'", editor_js)
        self.assertIn("textarea.lang = document.documentElement.getAttribute('lang') || 'ru'", editor_js)
        self.assertIn("if (isNumber) {\n      cell.style.width = cellW + 'px';", editor_js)
        self.assertIn("cell.style.maxWidth = cellW + 'px';", editor_js)
        self.assertNotIn("inline-table-number-spinner", editor_js)
        self.assertNotIn("textarea.type = 'text'", editor_js)
        self.assertIn("if (lockCaretAtEnd) placeNumberCaretAtEnd(textarea);", editor_js)
        self.assertNotIn("if (suppressNumberSelect) placeNumberCaretAtEnd(textarea);", editor_js)
        self.assertIn("{ seed: event.key === ',' ? '.' : event.key }", editor_js)
        self.assertNotIn("skipDisplay: true", editor_js)
        self.assertNotIn("function collapseNumberCaretToEnd", editor_js)
        self.assertIn("function setSelectedCells", editor_js)
        self.assertIn("function syncSelectionEdges", editor_js)
        self.assertIn("function shouldDrawSelectionEdge", editor_js)
        self.assertNotIn("function isEditingSelectionCell", editor_js)
        self.assertIn("if (!isNumber) {", editor_js)
        self.assertIn("textarea.select();", editor_js)
        self.assertNotIn("if (!isNumber) textarea.select();", editor_js)
        self.assertIn("inline-cell-sel-r", editor_js)
        self.assertNotIn("proposal-commercial-cell-selected", editor_js)
        self.assertIn("isNumber ? 3 : 0", editor_js)
        self.assertIn("inline-table-layout-sizer", editor_js)
        self.assertNotIn("freezeTableColumns", editor_js)
        self.assertNotIn("unfreezeTableColumns", editor_js)
        self.assertNotIn("inline-table-editing-scroller", editor_js)
        self.assertNotIn(
            "tr.style.height = tr.getBoundingClientRect().height",
            editor_js,
        )
        self.assertNotIn("cell.textContent = '';", editor_js)
        self.assertIn("overflow-wrap: break-word", css)
        self.assertIn(".typical-section-system-row > td", css)
        self.assertIn(".typical-section-code-col", css)
        self.assertIn(".report-structure-compact-col", css)
        self.assertIn(
            "#policy-pane[data-policy-workspace=\"1\"] #report-structures-table .report-structure-compact-col {\n  width: 1%;\n  white-space: nowrap;\n  text-align: left;\n}",
            css,
        )
        self.assertIn(".inline-table-layout-sizer", css)
        self.assertIn(".inline-table-number-input {", css)
        self.assertIn(".inline-table-number-wrap {", css)
        self.assertIn("padding-right: 3px", css)
        self.assertIn(
            ".inline-table-number-wrap {\n  padding-right: 3px;\n  outline: none;\n  box-shadow: none;\n  border: none;\n  display: flex;\n  align-items: center;\n}",
            css,
        )
        self.assertIn(".inline-table-number-input::-webkit-inner-spin-button", css)
        self.assertIn("margin: auto 2px auto 0", css)
        self.assertNotIn("inline-table-editing-scroller", css)
        self.assertNotIn("max-width: max-content", css)
        self.assertIn("top: calc(0.25rem + (1lh - 12px) / 2 + 2px)", css)
        self.assertIn(".inline-cell-editing {\n  position: relative;\n  z-index: 2;\n  overflow: visible !important;", css)
        self.assertIn(".inline-cell-selected.inline-cell-sel-t::after", css)
        self.assertIn(".inline-cell-selected.inline-cell-sel-r::after", css)
        self.assertIn("box-shadow: inset 0 0 0 2px var(--bs-primary, #0d6efd);", css)
        self.assertIn("resizeWrap(false)", editor_js)
        self.assertIn("isCheckedValue", editor_js)
        self.assertIn("type === 'checkbox'", editor_js)
        self.assertIn("type === 'number'", editor_js)
        self.assertIn("normalizeSpecialtyIds", editor_js)
        self.assertIn("inline-specialty-row", editor_js)
        self.assertIn("data-specialty-action", editor_js)
        self.assertIn("bi-arrow-up", editor_js)
        self.assertIn("bi-arrow-down", editor_js)
        self.assertIn("inline-specialty-chevron", editor_js)
        self.assertNotIn("if (newRow) openSelectEditor", editor_js)
        self.assertIn(".inline-specialty-row {", css)
        self.assertIn(".inline-specialty-actions {", css)
        self.assertIn(".inline-specialty-actions {\n  display: none;\n  align-items: center;\n  gap: var(--inline-specialty-icon-gap);\n  background: transparent;\n  box-shadow: none;", css)
        self.assertIn(
            ".inline-specialties[data-count]:not([data-count=\"0\"]):not([data-count=\"1\"]) .inline-specialty-actions {\n  display: inline-flex;\n  opacity: 0;",
            css,
        )
        self.assertIn(".inline-specialty-add {", css)
        self.assertIn(".typical-section-executor-col {\n  min-width: 16rem;", css)
        self.assertIn("#policy-pane[data-policy-workspace=\"1\"] [data-policy-row-insert=\"1\"] .proposal-row-insert {", css)
        self.assertIn("--policy-workspace-row-insert-gutter: 0.875rem;", css)
        self.assertNotIn(
            "#policy:has(#policy-pane[data-policy-workspace=\"1\"]) > .templates-bleed > .ps-3 {",
            css,
        )
        self.assertNotIn(
            "#policy:has(#policy-pane[data-policy-workspace=\"1\"]) > .templates-bleed > .section-header > .px-3 {",
            css,
        )
        self.assertIn("overflow-y: hidden;", css)
        self.assertIn("padding-bottom: 0.875rem;", css)
        self.assertIn("margin-bottom: -0.875rem;", css)
        self.assertIn("#policy-pane[data-policy-workspace=\"1\"] [data-policy-row-insert=\"1\"] .policy-table-footer {\n  margin-top: calc(24px - .75rem);\n}", css)
        self.assertIn(".policy-row-check-cell {", css)
        self.assertIn(".proposal-row-insert > .bi {", css)
        self.assertIn("[data-policy-row-insert=\"1\"] .table-responsive {\n  position: relative;", css)
        self.assertIn("[data-policy-row-insert=\"1\"] .proposal-row-insert {\n  position: absolute;\n  left: 0;\n  top: 0;\n  z-index: 30;", css)
        self.assertNotIn(
            "tr.proposal-service-insert-before > td {\n  box-shadow:",
            css,
        )
        self.assertNotIn(
            "[data-policy-row-insert=\"1\"] tbody.policy-row-insert-active",
            css,
        )
        self.assertIn("repeating-linear-gradient(\n    to right,\n    rgba(33, 37, 41, .22) 0,", css)
        self.assertIn(".inline-editing-row > td", css)
        base_html = (root / "core" / "templates" / "core" / "base.html").read_text()
        self.assertIn("inline-table-editor.js", base_html)
        self.assertIn("service-composition-editor.js", base_html)
        index_html = (root / "templates" / "index.html").read_text()
        self.assertIn('id="policy-workspace-actions"', index_html)
        self.assertIn("data-policy-workspace-save-btn", index_html)
        self.assertIn("data-policy-workspace-cancel-btn", index_html)
        self.assertIn("#policy-section-heading .proposal-header-separator", css)
        self.assertIn(".product-quick-edit", css)
        self.assertIn('#policy-pane[data-policy-workspace="1"] .product-workspace-edit-cell', css)
        self.assertIn(".product-workspace-checkbox-cell", css)
        self.assertIn(".policy-workspace-checkbox-cell", css)
        self.assertIn(".policy-workspace-product-cell", css)
        self.assertNotIn(
            "#policy-pane[data-policy-workspace=\"1\"] .product-workspace-short-name-cell",
            css,
        )
        self.assertIn(
            "#policy-pane[data-policy-workspace=\"1\"] #policy-products-section .table-section-header",
            css,
        )
        self.assertIn("#policy-pane .table-section-header", css)
        self.assertIn("margin-top: 24px !important", css)
        self.assertIn(
            "#policy-pane .policy-group-card > .card-body > :first-child > .table-section-header",
            css,
        )
        self.assertIn(
            "#policy-pane .policy-group-card {\n  --bs-card-border-radius: .75rem;\n  --bs-card-border-color: #ced4da;\n  margin-bottom: 1.25rem;\n  overflow: visible;\n  border: 1px solid #ced4da;\n  border-radius: .75rem;",
            css,
        )
        self.assertIn("#policy-pane .policy-group-card-header {\n  background: #e7f1ff;", css)
        self.assertIn("#policy-pane .policy-group-card-title {\n  margin: 0;\n  display: flex;\n  align-items: center;\n  padding-left: 5px;\n  font-weight: 600;\n  font-size: 1.3rem;", css)
        self.assertIn("#policy-pane .policy-group-card-title > .bi,\n#policy-pane .policy-group-card .table-section-title > .bi {", css)
        self.assertIn(".policy-table-placeholder > .table-section-header {\n  margin-top: 24px;", css)
        self.assertIn(
            "#policy-pane .policy-group-card > .card-body > .policy-table-placeholder:first-child > .table-section-header",
            css,
        )
        products_table = (root / "policy_app" / "templates" / "policy_app" / "policy_products_table.html").read_text()
        self.assertIn('style="margin-top: 24px;"', products_table)
        self.assertNotIn('style="margin-top: 50px;"', products_table)
        self.assertIn(".inline-cell-dirty", css)
        self.assertIn("rgba(7, 93, 148, .07)", css)
        self.assertNotIn("background-color: #fff8e1;", css)
        self.assertIn(".inline-table-select-editor,\n.inline-table-select-editor:focus", css)
        self.assertIn("padding-left: .625rem", css)
        self.assertIn("background-size: 16px 12px", css)
        self.assertIn("addEventListener('pointerdown'", editor_js)
        self.assertIn("selectEl.blur()", editor_js)
        self.assertIn("showPicker", editor_js)
        self.assertIn("dataset.inlineOpen", editor_js)
        self.assertIn("overflow: hidden", css)
        self.assertIn(".policy-workspace-catalog-only", css)
        self.assertIn("#typical-service-terms-gantt-edit-btn", css)
        self.assertIn(
            "#policy-pane[data-policy-workspace=\"1\"] #typical-service-terms-gantt-edit-btn {\n"
            "  display: inline-flex !important;\n"
            "  color: #fff !important;\n"
            "  background-color: var(--bs-primary, #075D94) !important;\n"
            "  border-color: var(--bs-primary, #075D94) !important;\n"
            "}",
            css,
        )
        self.assertIn(".typical-service-term-unit-col", css)
        self.assertIn(".typical-service-term-value-col", css)
        self.assertIn("#policy-typical-service-compositions-section thead th", css)
        self.assertIn("--policy-sticky-thead-top", css)
        self.assertIn(".policy-service-composition-inline-toolbar", css)
        self.assertIn(".policy-service-composition-edit-actions", css)
        self.assertIn(
            "#policy-pane[data-policy-workspace=\"1\"] #policy-typical-service-compositions-section thead th {\n  position: sticky;\n  top: var(--policy-sticky-thead-top, 76px);\n  z-index: 21;\n  background: #fff;\n  box-shadow: none;\n  overflow: visible;\n  padding-top: .5rem;\n  padding-bottom: .65rem;\n}",
            css,
        )
        self.assertIn(
            "#policy-pane[data-policy-workspace=\"1\"] #policy-typical-service-compositions-section thead.is-stuck th::after",
            css,
        )
        self.assertIn("background: #dee2e6", css)
        self.assertNotIn("inset 0 -1px 0 #ced4da, 0 1px 0 #ced4da", css)
        self.assertNotIn(
            "#policy-pane[data-policy-workspace=\"1\"] #typical-service-compositions-table {\n  border-collapse: separate;",
            css,
        )
        self.assertIn(
            "#typical-service-compositions-table .policy-service-composition-section-col {\n  width: 1%;\n  max-width: none;\n  white-space: nowrap;\n}",
            css,
        )
        self.assertIn(".inline-table-rich-wrap .ql-editor .ql-font-cambria", css)
        self.assertIn(".inline-table-rich-wrap", css)
        self.assertIn('td[data-inline-type="rich"]', css)
        self.assertIn("applyFontToDocument", editor_mod)
        self.assertIn("formatText(0, len - 1, 'font'", editor_mod)
        self.assertIn("[data-rich-edit-action]", editor_js)
        self.assertIn("richPointerStartedInEditor", editor_js)
        self.assertIn("function lockCompositionTableColumns", editor_js)
        self.assertIn("function unlockCompositionTableColumns", editor_js)
        self.assertIn("wrap.style.fontSize = displayFontSize", editor_js)
        self.assertIn(
            ".policy-service-composition-header.is-rich-editing .policy-service-composition-inline-toolbar {\n  visibility: visible;\n  pointer-events: auto;\n}",
            css,
        )
        self.assertIn(".policy-service-composition-inline-toolbar {\n  display: flex;\n  align-items: center;\n  visibility: hidden;", css)
        self.assertIn(
            "#proposals-pane .proposal-service-text-toolbar__btn.is-active,\n"
            "#policy-modal .proposal-service-text-toolbar__btn.is-active,\n"
            "#policy-pane .proposal-service-text-toolbar__btn.is-active {",
            css,
        )
        self.assertNotIn(
            "#proposals-pane .proposal-service-text-toolbar__btn.is-active,\n"
            "#policy-modal .proposal-service-text-toolbar__btn,\n"
            "#policy-pane .proposal-service-text-toolbar__btn.is-active {",
            css,
        )
        self.assertIn("editState.hadUserChange", editor_js)
        self.assertIn(
            "#typical-service-compositions-table .policy-service-composition-content--rich ol,\n"
            "#typical-service-compositions-table .policy-service-composition-content--rich ul,\n"
            ".inline-table-rich-wrap .ql-editor ol,\n"
            ".inline-table-rich-wrap .ql-editor ul {\n  margin: 0;\n  padding-left: 1.5em;\n}",
            css,
        )
        self.assertIn(
            "#typical-service-compositions-table .policy-service-composition-content--rich li.ql-indent-1:not(.ql-direction-rtl),\n"
            ".inline-table-rich-wrap .ql-editor li.ql-indent-1:not(.ql-direction-rtl) { padding-left: 4.5em; }",
            css,
        )
        self.assertIn(
            "#typical-service-compositions-table .policy-service-composition-content--rich p,\n"
            ".inline-table-rich-wrap .ql-editor p {\n  margin: 0;\n  padding: 0;\n  min-height: 1.25em;\n}",
            css,
        )
        self.assertIn("editState.baselineCaptured", editor_js)
        self.assertIn("function richContentsChanged", editor_js)
        self.assertIn("displayContent.innerHTML", editor_js)
        self.assertIn("function restoreEmptyParagraphs", editor_mod)
        self.assertIn("function applyListFormat", editor_mod)
        self.assertIn("function closeListMenu", editor_mod)
        self.assertIn("function openListMenu", editor_mod)
        self.assertIn("document.body.appendChild(listMenu)", editor_mod)
        self.assertIn("function openColorPopover", editor_mod)
        self.assertIn("document.body.appendChild(popover)", editor_mod)
        self.assertIn("composition-color-popover-", editor_mod)
        self.assertIn("#policy-modal .proposal-service-text-toolbar__color input[type=\"color\"]", css)
        self.assertNotIn(
            "#policy-modal .proposal-service-text-toolbar__color,\n#policy-pane .proposal-service-text-toolbar__color input[type=\"color\"]",
            css,
        )
        self.assertNotIn(
            "#policy-modal .proposal-service-text-toolbar__color-popover,\n#policy-pane .proposal-service-text-toolbar__color-popover input[type=\"color\"]",
            css,
        )
        self.assertIn('data-bs-popper="static"', (root / "policy_app" / "templates" / "policy_app" / "_service_composition_toolbar.html").read_text())
        self.assertIn("source === 'user'", editor_mod)
        self.assertIn(".inline-table-rich-wrap .ql-container {\n  height: auto;\n  font-size: inherit !important;\n}", css)
        self.assertNotIn(".policy-service-composition-header__main", css)
        self.assertNotIn(
            "activeQuill.setContents(delta, 'silent');\n      }\n      activeQuill.format('font', 'calibri', 'silent');",
            editor_mod,
        )
        self.assertIn(
            "#policy-pane[data-policy-workspace=\"1\"] #policy-typical-service-terms-section td.typical-service-term-value-col {\n  width: 1%;\n  white-space: nowrap;\n  text-align: left;\n  min-width: calc(4ch + 1.15em + 8px);",
            css,
        )
        self.assertIn(
            "#policy-pane[data-policy-workspace=\"1\"] #policy-typical-service-terms-section td.typical-service-term-unit-col {\n  text-align: left;",
            css,
        )
        self.assertNotIn(
            "#policy-pane[data-policy-workspace=\"1\"] #policy-typical-service-terms-section td.typical-service-term-value-col {\n  text-align: right;",
            css,
        )
        self.assertIn('td[data-inline-type="number"]', css)

    def test_workspace_table_requests_return_all_rows_without_pagination(self):
        for index in range(1, 32):
            TypicalSection.objects.create(
                product=self.product,
                code=f"WS-{index:02d}",
                short_name=f"ws-{index:02d}",
                short_name_ru=f"вс-{index:02d}",
                name_en=f"Workspace section {index}",
                name_ru=f"Раздел workspace {index}",
                accounting_type="Раздел",
                position=index,
            )

        catalog = self.client.get(reverse("policy_typical_sections_table"), {"product": self.product.pk})
        workspace = self.client.get(
            reverse("policy_typical_sections_table"),
            {"product": self.product.pk, "workspace": "1"},
        )

        self.assertTrue(catalog.context["policy_pagination_enabled"])
        self.assertEqual(len(catalog.context["sections"]), 25)
        self.assertContains(catalog, "policy-table-pagination")

        self.assertFalse(workspace.context["policy_pagination_enabled"])
        self.assertEqual(len(workspace.context["sections"]), 31)
        self.assertNotContains(workspace, "policy-table-pagination")
        self.assertNotContains(workspace, 'aria-label="Страницы таблицы"')

        products = self.client.get(
            reverse("policy_products_table"),
            {"product": self.product.pk, "workspace": "1"},
        )
        self.assertFalse(products.context["policy_pagination_enabled"])
        self.assertEqual(len(products.context["products"]), 1)
        self.assertNotContains(products, "policy-table-pagination")
        self.assertTrue(products.context["policy_inline_edit"])
        self.assertContains(products, 'data-policy-inline="1"', html=False)
        self.assertContains(products, 'data-inline-type="text"', html=False)
        self.assertContains(products, 'data-inline-type="select"', html=False)
        self.assertContains(products, 'data-inline-type="owners"', html=False)
        self.assertContains(products, "policy-workspace-catalog-only", html=False)
        self.assertContains(products, "product-workspace-checkbox-cell", html=False)
        self.assertContains(products, "product-workspace-short-name-cell", html=False)

        goals = self.client.get(
            reverse("policy_service_goal_reports_table"),
            {"product": self.product.pk, "workspace": "1"},
        )
        self.assertTrue(goals.context["policy_inline_edit"])
        self.assertContains(goals, 'data-policy-inline="1"', html=False)
        self.assertContains(goals, 'data-inline-field="service_goal"', html=False)
        self.assertContains(goals, 'data-inline-field="service_goal_genitive"', html=False)
        self.assertContains(goals, 'data-inline-field="report_title"', html=False)
        self.assertContains(goals, 'data-inline-field="product_name"', html=False)
        self.assertContains(goals, "policy-workspace-checkbox-cell", html=False)
        self.assertContains(goals, "policy-workspace-product-cell", html=False)
        self.assertContains(goals, "policy-workspace-catalog-only", html=False)
        goals_html = goals.content.decode()
        goals_add_idx = goals_html.find("Добавить строку")
        self.assertGreater(goals_add_idx, 0)
        self.assertIn("policy-workspace-catalog-only", goals_html[goals_add_idx - 500:goals_add_idx])
        self.assertNotContains(goals, "Пока нет данных.")

        catalog_goals = self.client.get(reverse("policy_service_goal_reports_table"))
        self.assertNotContains(catalog_goals, 'data-policy-inline="1"')
        self.assertNotContains(catalog_goals, 'data-inline-type="text"')
        self.assertContains(catalog_goals, "Добавить строку")

        sections = self.client.get(
            reverse("policy_typical_sections_table"),
            {"product": self.product.pk, "workspace": "1"},
        )
        sections_html = sections.content.decode()
        self.assertTrue(sections.context["policy_inline_edit"])
        self.assertContains(sections, 'data-policy-inline="1"', html=False)
        self.assertContains(sections, 'data-inline-field="code"', html=False)
        self.assertContains(sections, 'data-inline-field="short_name"', html=False)
        self.assertContains(sections, 'data-inline-field="name_ru"', html=False)
        self.assertContains(sections, 'data-inline-field="accounting_type"', html=False)
        self.assertContains(sections, 'data-inline-field="expertise_dir"', html=False)
        self.assertContains(sections, 'data-inline-field="expertise_direction"', html=False)
        self.assertContains(sections, 'data-inline-field="exclude_from_tkp_autofill"', html=False)
        self.assertContains(sections, 'data-inline-type="checkbox"', html=False)
        self.assertContains(sections, 'data-inline-type="select"', html=False)
        self.assertContains(sections, 'data-inline-field="specialty_ids"', html=False)
        self.assertContains(sections, 'data-inline-type="specialties"', html=False)
        self.assertContains(sections, "inline-specialty-row", html=False)
        self.assertIn('"specialties"', sections.context["policy_inline_options_json"])
        self.assertContains(sections, "policy-workspace-product-cell", html=False)
        self.assertContains(sections, "policy-row-check-cell", html=False)
        self.assertContains(sections, 'data-policy-row-insert="1"', html=False)
        self.assertContains(sections, "Добавить строку")
        add_idx = sections_html.find("Добавить строку")
        self.assertGreater(add_idx, 0)
        self.assertNotIn("policy-workspace-catalog-only", sections_html[add_idx - 500:add_idx])
        csv_idx = sections_html.find("Скачать CSV")
        self.assertGreater(csv_idx, 0)
        self.assertIn("policy-workspace-catalog-only", sections_html[csv_idx - 400:csv_idx])
        self.assertContains(sections, 'id="sections-actions"', html=False)

        catalog_sections = self.client.get(reverse("policy_typical_sections_table"))
        self.assertNotContains(catalog_sections, 'data-policy-inline="1"')
        self.assertNotContains(catalog_sections, 'data-inline-type="text"')
        self.assertNotContains(catalog_sections, 'data-inline-type="checkbox"')
        self.assertNotContains(catalog_sections, 'data-inline-type="specialties"')
        self.assertContains(catalog_sections, "Добавить строку")
        self.assertContains(catalog_sections, "Скачать CSV")
        self.assertContains(catalog_sections, "Загрузить CSV")

        section = TypicalSection.objects.create(
            product=self.product,
            code="STR-WS",
            short_name="str-ws",
            short_name_ru="стр-ws",
            name_en="Structure section EN",
            name_ru="Раздел структуры",
            accounting_type="Раздел",
            position=100,
        )
        structure = SectionStructure.objects.create(
            product=self.product,
            section=section,
            subsections="Старые подразделы",
            position=1,
        )
        structures = self.client.get(
            reverse("policy_section_structures_table"),
            {"product": self.product.pk, "workspace": "1"},
        )
        structures_html = structures.content.decode()
        self.assertTrue(structures.context["policy_inline_edit"])
        self.assertContains(structures, 'data-policy-inline="1"', html=False)
        self.assertContains(structures, f'data-inline-row-id="{structure.pk}"', html=False)
        self.assertContains(structures, 'data-inline-field="section"', html=False)
        self.assertContains(structures, 'data-inline-type="select"', html=False)
        self.assertContains(structures, 'data-inline-field="subsections"', html=False)
        self.assertContains(structures, 'data-inline-type="text"', html=False)
        self.assertContains(structures, "typical-section-dsc-code", html=False)
        self.assertContains(structures, "policy-workspace-product-cell", html=False)
        self.assertContains(structures, "policy-row-check-cell", html=False)
        self.assertContains(structures, 'data-policy-row-insert="1"', html=False)
        self.assertIn('"sections"', structures.context["policy_inline_options_json"])
        self.assertIn(f'"id": {section.pk}', structures.context["policy_inline_options_json"])
        self.assertIn('"label": "STR-WS Раздел структуры"', structures.context["policy_inline_options_json"])
        self.assertIn('"displayLabel": "Раздел структуры"', structures.context["policy_inline_options_json"])
        self.assertContains(structures, "typical-section-code-col", html=False)
        self.assertContains(structures, "Добавить строку")
        add_idx = structures_html.find("Добавить строку")
        self.assertGreater(add_idx, 0)
        self.assertNotIn("policy-workspace-catalog-only", structures_html[add_idx - 500:add_idx])
        csv_idx = structures_html.find("Скачать CSV")
        self.assertGreater(csv_idx, 0)
        self.assertIn("policy-workspace-catalog-only", structures_html[csv_idx - 400:csv_idx])
        self.assertContains(structures, 'id="structures-actions"', html=False)

        catalog_structures = self.client.get(reverse("policy_section_structures_table"))
        self.assertNotContains(catalog_structures, 'data-policy-inline="1"')
        self.assertNotContains(catalog_structures, 'data-inline-type="text"')
        self.assertNotContains(catalog_structures, 'data-inline-type="select"')
        self.assertContains(catalog_structures, "typical-section-dsc-code")
        self.assertContains(catalog_structures, "Добавить строку")
        self.assertContains(catalog_structures, "Скачать CSV")
        self.assertContains(catalog_structures, "Загрузить CSV")

        report_structure = ReportStructure.objects.create(
            product=self.product,
            level=1,
            code="RS-WS",
            name="Старое наименование отчета",
            position=1,
        )
        reports = self.client.get(
            reverse("policy_report_structures_table"),
            {"product": self.product.pk, "workspace": "1"},
        )
        self.assertTrue(reports.context["policy_inline_edit"])
        self.assertContains(reports, 'data-policy-inline="1"', html=False)
        self.assertContains(reports, 'id="report-structures-table"', html=False)
        self.assertContains(reports, f'data-inline-row-id="{report_structure.pk}"', html=False)
        self.assertContains(reports, 'data-inline-field="name"', html=False)
        self.assertContains(reports, 'data-inline-type="text"', html=False)
        self.assertContains(reports, "policy-workspace-product-cell", html=False)
        self.assertContains(reports, "report-structure-compact-col", html=False)
        reports_html = reports.content.decode()
        self.assertContains(reports, "Добавить строку")
        add_idx = reports_html.find("Добавить строку")
        self.assertGreater(add_idx, 0)
        self.assertNotIn("policy-workspace-catalog-only", reports_html[add_idx - 500:add_idx])
        csv_idx = reports_html.find("Скачать CSV")
        self.assertGreater(csv_idx, 0)
        self.assertIn("policy-workspace-catalog-only", reports_html[csv_idx - 400:csv_idx])
        upload_idx = reports_html.find("Загрузить CSV")
        self.assertGreater(upload_idx, 0)
        self.assertIn("policy-workspace-catalog-only", reports_html[upload_idx - 400:upload_idx])

        catalog_reports = self.client.get(reverse("policy_report_structures_table"))
        self.assertNotContains(catalog_reports, 'data-policy-inline="1"')
        self.assertNotContains(catalog_reports, 'data-inline-type="text"')
        self.assertContains(catalog_reports, "policy-workspace-product-cell")
        self.assertContains(catalog_reports, "Добавить строку")
        self.assertContains(catalog_reports, "Скачать CSV")
        self.assertContains(catalog_reports, "Загрузить CSV")

        tariff = Tariff.objects.create(
            product=self.product,
            section=section,
            base_rate_vpm="10.50",
            service_hours=8,
            service_days_tkp=5,
            created_by=self.user,
            position=1,
        )
        tariffs = self.client.get(
            reverse("policy_tariffs_table"),
            {"product": self.product.pk, "workspace": "1"},
        )
        tariffs_html = tariffs.content.decode()
        self.assertTrue(tariffs.context["policy_inline_edit"])
        self.assertContains(tariffs, 'data-policy-inline="1"', html=False)
        self.assertContains(tariffs, f'data-inline-row-id="{tariff.pk}"', html=False)
        self.assertContains(tariffs, 'data-inline-field="section"', html=False)
        self.assertContains(tariffs, 'data-inline-type="select"', html=False)
        self.assertContains(tariffs, 'data-inline-field="base_rate_vpm"', html=False)
        self.assertContains(tariffs, 'data-inline-type="number"', html=False)
        self.assertContains(tariffs, 'data-inline-field="service_hours"', html=False)
        self.assertContains(tariffs, 'data-inline-field="service_days_tkp"', html=False)
        self.assertNotContains(tariffs, 'data-inline-field="owner"')
        self.assertContains(tariffs, "typical-section-dsc-code", html=False)
        self.assertContains(tariffs, "typical-section-code-col", html=False)
        self.assertContains(tariffs, "policy-workspace-product-cell", html=False)
        self.assertContains(tariffs, "policy-row-check-cell", html=False)
        self.assertContains(tariffs, 'data-policy-row-insert="1"', html=False)
        self.assertIn('"sections"', tariffs.context["policy_inline_options_json"])
        self.assertIn('"owners"', tariffs.context["policy_inline_options_json"])
        self.assertIn(f'"id": {section.pk}', tariffs.context["policy_inline_options_json"])
        self.assertIn('"label": "STR-WS Раздел структуры"', tariffs.context["policy_inline_options_json"])
        self.assertContains(tariffs, "Добавить строку")
        add_idx = tariffs_html.find("Добавить строку")
        self.assertGreater(add_idx, 0)
        self.assertNotIn("policy-workspace-catalog-only", tariffs_html[add_idx - 500:add_idx])
        csv_idx = tariffs_html.find("Скачать CSV")
        self.assertGreater(csv_idx, 0)
        self.assertIn("policy-workspace-catalog-only", tariffs_html[csv_idx - 400:csv_idx])
        upload_idx = tariffs_html.find("Загрузить CSV")
        self.assertGreater(upload_idx, 0)
        self.assertIn("policy-workspace-catalog-only", tariffs_html[upload_idx - 400:upload_idx])
        self.assertContains(tariffs, 'id="tariffs-actions"', html=False)

        catalog_tariffs = self.client.get(reverse("policy_tariffs_table"))
        self.assertNotContains(catalog_tariffs, 'data-policy-inline="1"')
        self.assertNotContains(catalog_tariffs, 'data-inline-type="number"')
        self.assertNotContains(catalog_tariffs, 'data-inline-type="select"')
        self.assertContains(catalog_tariffs, "typical-section-dsc-code")
        self.assertContains(catalog_tariffs, "Добавить строку")
        self.assertContains(catalog_tariffs, "Скачать CSV")
        self.assertContains(catalog_tariffs, "Загрузить CSV")

        term = TypicalServiceTerm.objects.create(
            product=self.product,
            source_data_weeks="2.0",
            source_data_term_unit=TypicalServiceTerm.TermUnit.WEEKS,
            preliminary_report_months="1.5",
            preliminary_report_term_unit=TypicalServiceTerm.TermUnit.MONTHS,
            final_report_weeks="3.0",
            final_report_term_unit=TypicalServiceTerm.TermUnit.WEEKS,
            position=1,
        )
        terms = self.client.get(
            reverse("policy_typical_service_terms_table"),
            {"product": self.product.pk, "workspace": "1"},
        )
        terms_html = terms.content.decode()
        self.assertTrue(terms.context["policy_inline_edit"])
        self.assertContains(terms, 'data-policy-inline="1"', html=False)
        self.assertContains(terms, f'data-inline-row-id="{term.pk}"', html=False)
        self.assertContains(terms, 'data-inline-field="source_data_weeks"', html=False)
        self.assertContains(terms, 'data-inline-field="source_data_term_unit"', html=False)
        self.assertContains(terms, 'data-inline-field="preliminary_report_months"', html=False)
        self.assertContains(terms, 'data-inline-field="preliminary_report_term_unit"', html=False)
        self.assertContains(terms, 'data-inline-field="final_report_weeks"', html=False)
        self.assertContains(terms, 'data-inline-field="final_report_term_unit"', html=False)
        self.assertContains(terms, 'data-inline-type="number"', html=False)
        self.assertContains(terms, 'data-inline-type="select"', html=False)
        self.assertContains(terms, "policy-workspace-checkbox-cell", html=False)
        self.assertContains(terms, "policy-workspace-product-cell", html=False)
        self.assertContains(terms, "typical-service-term-value-col", html=False)
        self.assertContains(terms, "typical-service-term-unit-col", html=False)
        self.assertContains(terms, 'id="typical-service-terms-gantt-edit-btn"', html=False)
        self.assertNotContains(terms, ">2,0 нед.<")
        self.assertContains(terms, ">2,0<", html=False)
        self.assertContains(terms, ">нед.<", html=False)
        self.assertContains(terms, ">1,5<", html=False)
        self.assertContains(terms, ">мес.<", html=False)
        self.assertIn('"units"', terms.context["policy_inline_options_json"])
        self.assertIn('"value": "days"', terms.context["policy_inline_options_json"])
        self.assertIn('"label": "дн."', terms.context["policy_inline_options_json"])
        self.assertContains(terms, "Добавить строку")
        add_idx = terms_html.find("Добавить строку")
        self.assertGreater(add_idx, 0)
        self.assertIn("policy-workspace-catalog-only", terms_html[add_idx - 500:add_idx])
        gantt_idx = terms_html.find("Редактировать")
        self.assertGreater(gantt_idx, 0)
        self.assertNotIn("policy-workspace-catalog-only", terms_html[gantt_idx - 400:gantt_idx])
        csv_idx = terms_html.find("Скачать CSV")
        self.assertGreater(csv_idx, 0)
        self.assertIn("policy-workspace-catalog-only", terms_html[csv_idx - 400:csv_idx])
        upload_idx = terms_html.find("Загрузить CSV")
        self.assertGreater(upload_idx, 0)
        self.assertIn("policy-workspace-catalog-only", terms_html[upload_idx - 400:upload_idx])
        self.assertContains(terms, 'id="typical-service-terms-actions"', html=False)

        catalog_terms = self.client.get(reverse("policy_typical_service_terms_table"))
        self.assertNotContains(catalog_terms, 'data-policy-inline="1"')
        self.assertNotContains(catalog_terms, 'data-inline-type="number"')
        self.assertNotContains(catalog_terms, 'data-inline-type="select"')
        self.assertNotContains(catalog_terms, 'data-inline-field="source_data_weeks"')
        self.assertContains(catalog_terms, ">2,0 нед.<", html=False)
        self.assertContains(catalog_terms, ">1,5 мес.<", html=False)
        self.assertContains(catalog_terms, ">3,0 нед.<", html=False)
        self.assertContains(catalog_terms, "Добавить строку")
        self.assertContains(catalog_terms, "Скачать CSV")
        self.assertContains(catalog_terms, "Загрузить CSV")
        self.assertContains(catalog_terms, 'id="typical-service-terms-gantt-edit-btn"', html=False)

        composition = TypicalServiceComposition.objects.create(
            product=self.product,
            section=section,
            service_composition="Старый состав",
            service_composition_editor_state={
                "html": "<p>Старый состав</p>",
                "plain_text": "Старый состав",
            },
            position=1,
        )
        compositions = self.client.get(
            reverse("policy_typical_service_compositions_table"),
            {"product": self.product.pk, "workspace": "1"},
        )
        compositions_html = compositions.content.decode()
        self.assertTrue(compositions.context["policy_inline_edit"])
        self.assertContains(compositions, 'data-policy-inline="1"', html=False)
        self.assertContains(compositions, f'data-inline-row-id="{composition.pk}"', html=False)
        self.assertContains(compositions, 'data-inline-field="section"', html=False)
        self.assertContains(compositions, 'data-inline-type="select"', html=False)
        self.assertContains(compositions, 'data-inline-field="service_composition_editor_state"', html=False)
        self.assertContains(compositions, 'data-inline-type="rich"', html=False)
        self.assertContains(compositions, "typical-section-dsc-code", html=False)
        self.assertContains(compositions, "typical-section-code-col", html=False)
        self.assertContains(compositions, "policy-workspace-product-cell", html=False)
        self.assertContains(compositions, "policy-row-check-cell", html=False)
        self.assertContains(compositions, 'data-policy-row-insert="1"', html=False)
        self.assertContains(compositions, "policy-workspace-catalog-only", html=False)
        self.assertContains(compositions, 'id="typical-service-composition-inline-toolbar"', html=False)
        self.assertContains(compositions, "policy-service-composition-section-col", html=False)
        self.assertContains(compositions, '<col class="typical-section-code-col">', html=False)
        self.assertNotContains(compositions, 'style="width: 8%;"', html=False)
        self.assertContains(compositions, 'data-rich-edit-action="commit"', html=False)
        self.assertContains(compositions, 'data-rich-edit-action="cancel"', html=False)
        self.assertIn('"sections"', compositions.context["policy_inline_options_json"])
        self.assertIn(f'"id": {section.pk}', compositions.context["policy_inline_options_json"])
        self.assertContains(compositions, "Добавить строку")
        add_idx = compositions_html.find("Добавить строку")
        self.assertGreater(add_idx, 0)
        self.assertNotIn("policy-workspace-catalog-only", compositions_html[add_idx - 500:add_idx])
        csv_idx = compositions_html.find("Скачать CSV")
        self.assertGreater(csv_idx, 0)
        self.assertIn("policy-workspace-catalog-only", compositions_html[csv_idx - 400:csv_idx])
        docx_idx = compositions_html.find("Скачать DOCX")
        self.assertGreater(docx_idx, 0)
        self.assertIn("policy-workspace-catalog-only", compositions_html[docx_idx - 400:docx_idx])
        self.assertContains(compositions, 'id="typical-service-compositions-actions"', html=False)
        self.assertNotIn(
            'id="typical-service-compositions-actions" class="d-none d-flex policy-workspace-catalog-only"',
            compositions_html,
        )

        catalog_compositions = self.client.get(reverse("policy_typical_service_compositions_table"))
        self.assertNotContains(catalog_compositions, 'data-policy-inline="1"')
        self.assertNotContains(catalog_compositions, 'data-inline-type="rich"')
        self.assertNotContains(catalog_compositions, 'data-inline-type="select"')
        self.assertNotContains(catalog_compositions, 'id="typical-service-composition-inline-toolbar"')
        self.assertNotContains(catalog_compositions, 'data-rich-edit-action="commit"')
        self.assertContains(catalog_compositions, "policy-service-composition-section-col")
        self.assertContains(catalog_compositions, "typical-section-dsc-code")
        self.assertContains(catalog_compositions, "Добавить строку")
        self.assertContains(catalog_compositions, "Скачать CSV")
        self.assertContains(catalog_compositions, "Загрузить CSV")
        self.assertContains(catalog_compositions, "Скачать DOCX")
        self.assertContains(catalog_compositions, "Загрузить DOCX")

        catalog = self.client.get(reverse("policy_products_table"))
        self.assertNotContains(catalog, 'data-policy-inline="1"')
        self.assertNotContains(catalog, 'data-inline-type="text"')
        self.assertContains(catalog, "Добавить строку")

    def test_workspace_service_goal_add_button_shown_only_when_empty(self):
        empty = self.client.get(
            reverse("policy_service_goal_reports_table"),
            {"product": self.other_product.pk, "workspace": "1"},
        )
        empty_html = empty.content.decode()
        self.assertTrue(empty.context["policy_inline_edit"])
        self.assertContains(empty, "Пока нет данных.")
        self.assertContains(empty, "Добавить строку")
        add_idx = empty_html.find("Добавить строку")
        self.assertGreater(add_idx, 0)
        self.assertNotIn("policy-workspace-catalog-only", empty_html[add_idx - 500:add_idx])
        csv_idx = empty_html.find("Скачать CSV")
        self.assertGreater(csv_idx, 0)
        self.assertIn("policy-workspace-catalog-only", empty_html[csv_idx - 400:csv_idx])

        filled = self.client.get(
            reverse("policy_service_goal_reports_table"),
            {"product": self.product.pk, "workspace": "1"},
        )
        filled_html = filled.content.decode()
        filled_add_idx = filled_html.find("Добавить строку")
        self.assertGreater(filled_add_idx, 0)
        self.assertIn("policy-workspace-catalog-only", filled_html[filled_add_idx - 500:filled_add_idx])

    def test_workspace_create_service_goal_report_uses_locked_product(self):
        response = self.client.post(
            reverse("service_goal_report_form_create")
            + f"?workspace=1&product={self.other_product.pk}",
            {
                "product": self.product.pk,
                "service_goal": "Цель empty WS",
                "service_goal_genitive": "Цели empty WS",
                "report_title": "Титул empty WS",
                "product_name": "Имя empty WS",
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        created = ServiceGoalReport.objects.get(product=self.other_product)
        self.assertEqual(created.service_goal, "Цель empty WS")
        self.assertEqual(created.product_id, self.other_product.pk)

    def test_workspace_typical_service_term_add_button_shown_only_when_empty(self):
        empty = self.client.get(
            reverse("policy_typical_service_terms_table"),
            {"product": self.other_product.pk, "workspace": "1"},
        )
        empty_html = empty.content.decode()
        self.assertTrue(empty.context["policy_inline_edit"])
        self.assertContains(empty, "Пока нет данных.")
        self.assertContains(empty, "Добавить строку")
        add_idx = empty_html.find("Добавить строку")
        self.assertGreater(add_idx, 0)
        self.assertNotIn("policy-workspace-catalog-only", empty_html[add_idx - 500:add_idx])
        csv_idx = empty_html.find("Скачать CSV")
        self.assertGreater(csv_idx, 0)
        self.assertIn("policy-workspace-catalog-only", empty_html[csv_idx - 400:csv_idx])

        TypicalServiceTerm.objects.create(
            product=self.other_product,
            source_data_weeks="1.0",
            source_data_term_unit=TypicalServiceTerm.TermUnit.WEEKS,
            preliminary_report_months="1.0",
            preliminary_report_term_unit=TypicalServiceTerm.TermUnit.MONTHS,
            final_report_weeks="2.0",
            final_report_term_unit=TypicalServiceTerm.TermUnit.WEEKS,
            position=1,
        )
        filled = self.client.get(
            reverse("policy_typical_service_terms_table"),
            {"product": self.other_product.pk, "workspace": "1"},
        )
        filled_html = filled.content.decode()
        filled_add_idx = filled_html.find("Добавить строку")
        self.assertGreater(filled_add_idx, 0)
        self.assertIn("policy-workspace-catalog-only", filled_html[filled_add_idx - 500:filled_add_idx])

    def test_workspace_create_typical_service_term_uses_locked_product(self):
        response = self.client.post(
            reverse("typical_service_term_form_create")
            + f"?workspace=1&product={self.other_product.pk}",
            {
                "product": self.product.pk,
                "source_data_weeks": "1.0",
                "source_data_term_unit": TypicalServiceTerm.TermUnit.WEEKS,
                "preliminary_report_months": "2.0",
                "preliminary_report_term_unit": TypicalServiceTerm.TermUnit.MONTHS,
                "final_report_weeks": "3.0",
                "final_report_term_unit": TypicalServiceTerm.TermUnit.WEEKS,
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        created = TypicalServiceTerm.objects.get(product=self.other_product)
        self.assertEqual(created.preliminary_report_months, Decimal("2.0"))
        self.assertEqual(created.product_id, self.other_product.pk)

    def test_workspace_create_modals_lock_product_field(self):
        params = {"product": self.product.pk, "workspace": "1"}
        create_names = [
            "section_form_create",
            "structure_form_create",
            "report_structure_form_create",
            "service_goal_report_form_create",
            "typical_service_composition_form_create",
            "typical_service_term_form_create",
            "tariff_form_create",
        ]
        for name in create_names:
            with self.subTest(name=name):
                response = self.client.get(reverse(name), params)
                self.assertEqual(response.status_code, 200, response.content)
                form = response.context["form"]
                self.assertTrue(form.fields["product"].disabled)
                self.assertEqual(form.initial.get("product"), self.product.pk)
                widget = form["product"].as_widget()
                self.assertIn("disabled", widget)
                self.assertIn("readonly-field", widget)
                self.assertIn(
                    f"?workspace=1&amp;product={self.product.pk}",
                    response.content.decode(),
                )
                self.assertNotIn(f'value="{self.other_product.pk}"', widget)

    def test_catalog_create_modal_keeps_product_editable(self):
        response = self.client.get(
            reverse("section_form_create"),
            {"product": self.product.pk},
        )
        form = response.context["form"]
        self.assertFalse(form.fields["product"].disabled)
        self.assertNotIn("disabled", form["product"].as_widget())
        self.assertNotIn("readonly-field", form["product"].as_widget())

    def test_workspace_create_ignores_tampered_product(self):
        response = self.client.post(
            reverse("section_form_create") + f"?workspace=1&product={self.product.pk}",
            {
                "product": self.other_product.pk,
                "code": "SEC-LOCK-WS",
                "short_name": "lock-en",
                "short_name_ru": "lock-ru",
                "name_en": "Locked EN",
                "name_ru": "Locked RU",
                "accounting_type": "Раздел",
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        created = TypicalSection.objects.get(code="SEC-LOCK-WS")
        self.assertEqual(created.product_id, self.product.pk)


class PolicyProductWorkspaceSaveTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="policy-workspace-save-staff",
            password="secret123",
            is_staff=True,
        )
        self.client.force_login(self.user)
        direction = ConsultingDirection.objects.create(position=1)
        self.consulting_type = ConsultingDirectionType.objects.create(
            direction=direction,
            name="Горный WS",
            position=1,
        )
        self.other_type = ConsultingDirectionType.objects.create(
            direction=direction,
            name="Экология WS",
            position=2,
        )
        self.service_type = ConsultingServiceType.objects.create(
            direction=direction,
            consulting_type=self.consulting_type,
            name="Аудит WS",
            code="AWS",
            position=1,
        )
        self.other_service_type = ConsultingServiceType.objects.create(
            direction=direction,
            consulting_type=self.other_type,
            name="ОВОС WS",
            code="EWS",
            position=1,
        )
        self.service_subtype = ConsultingServiceSubtype.objects.create(
            direction=direction,
            service_type=self.service_type,
            name="Аудит проектных решений WS",
            position=1,
        )
        self.other_subtype = ConsultingServiceSubtype.objects.create(
            direction=direction,
            service_type=self.other_service_type,
            name="Оценка воздействия WS",
            position=1,
        )
        self.owner = GroupMember.objects.create(
            short_name="IMC WS",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
            position=1,
        )
        self.product = Product.objects.create(
            short_name="SAVE-WS",
            name_en="Save workspace product",
            display_name="Save display",
            name_ru="Продукт сохранения",
            consulting_type_ref=self.consulting_type,
            service_category_ref=self.service_type,
            service_subtype_ref=self.service_subtype,
            position=1,
        )
        self.product.owners.set([self.owner])
        self.goal_report = ServiceGoalReport.objects.create(
            product=self.product,
            service_goal="Старая цель",
            service_goal_genitive="Старой цели",
            report_title="Старый титул",
            product_name="Старое имя",
            position=1,
        )
        self.other_product = Product.objects.create(
            short_name="OTHER-SAVE",
            name_en="Other save product",
            display_name="Other save",
            name_ru="Другой продукт сохранения",
            consulting_type_ref=self.consulting_type,
            service_category_ref=self.service_type,
            service_subtype_ref=self.service_subtype,
            position=2,
        )

    def _save(self, payload, product=None):
        product = product or self.product
        return self.client.post(
            reverse("product_workspace_save", args=[product.pk]),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_workspace_save_updates_text_fields_and_label(self):
        response = self._save(
            {
                "tables": {
                    "products": [
                        {
                            "id": self.product.pk,
                            "fields": {
                                "short_name": "SAVE-NEW",
                                "name_en": "Updated EN",
                                "name_ru": "Обновлённый RU",
                                "display_name": "New display",
                            },
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["label"], "SAVE-NEW New display")
        self.assertEqual(payload["tables"], ["products"])
        self.product.refresh_from_db()
        self.assertEqual(self.product.short_name, "SAVE-NEW")
        self.assertEqual(self.product.name_en, "Updated EN")
        self.assertEqual(self.product.name_ru, "Обновлённый RU")
        self.assertEqual(self.product.display_name, "New display")

    def test_workspace_save_rejects_duplicate_short_name(self):
        response = self._save(
            {
                "tables": {
                    "products": [
                        {
                            "id": self.product.pk,
                            "fields": {"short_name": self.other_product.short_name},
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertTrue(any(item["field"] == "short_name" for item in payload["errors"]))
        self.product.refresh_from_db()
        self.assertEqual(self.product.short_name, "SAVE-WS")

    def test_workspace_save_validates_catalog_cascade(self):
        response = self._save(
            {
                "tables": {
                    "products": [
                        {
                            "id": self.product.pk,
                            "fields": {
                                "consulting_type_ref": self.other_type.pk,
                                "service_category_ref": self.service_type.pk,
                                "service_subtype_ref": self.service_subtype.pk,
                            },
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        fields = {item["field"] for item in payload["errors"]}
        self.assertTrue(fields & {"service_category_ref", "service_subtype_ref"})

        success = self._save(
            {
                "tables": {
                    "products": [
                        {
                            "id": self.product.pk,
                            "fields": {
                                "consulting_type_ref": self.other_type.pk,
                                "service_category_ref": self.other_service_type.pk,
                                "service_subtype_ref": self.other_subtype.pk,
                            },
                        }
                    ]
                }
            }
        )
        self.assertEqual(success.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.consulting_type_ref_id, self.other_type.pk)
        self.assertEqual(self.product.service_category_ref_id, self.other_service_type.pk)
        self.assertEqual(self.product.service_subtype_ref_id, self.other_subtype.pk)
        self.assertEqual(self.product.service_code, "EWS")

    def test_workspace_save_sets_group_owner(self):
        response = self._save(
            {
                "tables": {
                    "products": [
                        {
                            "id": self.product.pk,
                            "fields": {"owner_ids": ["__group__"]},
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_group_owner)
        self.assertEqual(list(self.product.owners.all()), [])

    def test_workspace_save_rejects_foreign_product_row(self):
        response = self._save(
            {
                "tables": {
                    "products": [
                        {
                            "id": self.other_product.pk,
                            "fields": {"short_name": "HACK"},
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertTrue(any(item["field"] == "id" for item in payload["errors"]))
        self.other_product.refresh_from_db()
        self.assertEqual(self.other_product.short_name, "OTHER-SAVE")

    def test_workspace_save_updates_service_goal_report_text_fields(self):
        response = self._save(
            {
                "tables": {
                    "service-goal-reports": [
                        {
                            "id": self.goal_report.pk,
                            "fields": {
                                "service_goal": "Новая цель",
                                "service_goal_genitive": "Новой цели",
                                "report_title": "Новый титул",
                                "product_name": "Новое имя",
                            },
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("service-goal-reports", payload["tables"])
        self.goal_report.refresh_from_db()
        self.assertEqual(self.goal_report.service_goal, "Новая цель")
        self.assertEqual(self.goal_report.service_goal_genitive, "Новой цели")
        self.assertEqual(self.goal_report.report_title, "Новый титул")
        self.assertEqual(self.goal_report.product_name, "Новое имя")
        self.assertEqual(self.goal_report.product_id, self.product.pk)

    def test_workspace_save_rejects_foreign_service_goal_report_row(self):
        foreign = ServiceGoalReport.objects.create(
            product=self.other_product,
            service_goal="Чужая цель",
            position=1,
        )
        response = self._save(
            {
                "tables": {
                    "service-goal-reports": [
                        {
                            "id": foreign.pk,
                            "fields": {"service_goal": "HACK"},
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertTrue(any(item["table"] == "service-goal-reports" for item in payload["errors"]))
        foreign.refresh_from_db()
        self.assertEqual(foreign.service_goal, "Чужая цель")

    def test_workspace_save_updates_typical_section_fields(self):
        expertise = ExpertiseDirection.objects.create(
            name="Налоги WS",
            short_name="TAX",
            position=1,
        )
        other_expertise = ExpertiseDirection.objects.create(
            name="Экология WS",
            short_name="ECO",
            position=2,
        )
        department = OrgUnit.objects.create(
            company=self.owner,
            level=1,
            department_name="Налоговый департамент",
            short_name="TAX-DEPT",
            unit_type="expertise",
            position=1,
        )
        other_department = OrgUnit.objects.create(
            company=self.owner,
            level=1,
            department_name="Экологический департамент",
            short_name="ECO-DEPT",
            unit_type="expertise",
            position=2,
        )
        section = TypicalSection.objects.create(
            product=self.product,
            code="SEC-WS",
            short_name="sec-ws",
            short_name_ru="разд-ws",
            name_en="Section EN",
            name_ru="Раздел RU",
            accounting_type="Раздел",
            expertise_dir=expertise,
            expertise_direction=department,
            exclude_from_tkp_autofill=True,
            position=1,
        )
        specialty = ExpertSpecialty.objects.create(
            expertise_direction=department,
            expertise_dir=expertise,
            specialty="Налоги workspace",
            position=1,
        )
        TypicalSectionSpecialty.objects.create(section=section, specialty=specialty, rank=1)

        response = self._save(
            {
                "tables": {
                    "typical-sections": [
                        {
                            "id": section.pk,
                            "fields": {
                                "code": "SEC-NEW",
                                "short_name": "sec-new",
                                "short_name_ru": "разд-new",
                                "name_en": "New EN",
                                "name_ru": "Новый RU",
                                "accounting_type": "Услуги",
                                "expertise_dir": other_expertise.pk,
                                "expertise_direction": other_department.pk,
                            },
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("typical-sections", payload["tables"])
        section.refresh_from_db()
        self.assertEqual(section.code, "SEC-NEW")
        self.assertEqual(section.short_name, "sec-new")
        self.assertEqual(section.short_name_ru, "разд-new")
        self.assertEqual(section.name_en, "New EN")
        self.assertEqual(section.name_ru, "Новый RU")
        self.assertEqual(section.accounting_type, "Услуги")
        self.assertEqual(section.expertise_dir_id, other_expertise.pk)
        self.assertEqual(section.expertise_direction_id, other_department.pk)
        self.assertEqual(section.product_id, self.product.pk)
        self.assertTrue(section.exclude_from_tkp_autofill)
        self.assertEqual(
            list(section.ranked_specialties.values_list("specialty_id", flat=True)),
            [specialty.pk],
        )

    def test_workspace_save_rejects_foreign_typical_section_row(self):
        foreign = TypicalSection.objects.create(
            product=self.other_product,
            code="SEC-FOR",
            short_name="sec-for",
            name_en="Foreign EN",
            name_ru="Чужой RU",
            accounting_type="Раздел",
            position=1,
        )
        response = self._save(
            {
                "tables": {
                    "typical-sections": [
                        {
                            "id": foreign.pk,
                            "fields": {"code": "HACK"},
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertTrue(any(item["table"] == "typical-sections" for item in payload["errors"]))
        foreign.refresh_from_db()
        self.assertEqual(foreign.code, "SEC-FOR")

    def test_workspace_save_rejects_system_dsc_typical_section(self):
        dsc = ensure_system_dsc_section(self.product)
        response = self._save(
            {
                "tables": {
                    "typical-sections": [
                        {
                            "id": dsc.pk,
                            "fields": {"name_ru": "HACK"},
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertTrue(any(item["table"] == "typical-sections" for item in payload["errors"]))
        dsc.refresh_from_db()
        self.assertEqual(dsc.name_ru, "Описание продукта")

    def test_workspace_save_typical_section_tkp_checkbox(self):
        section = TypicalSection.objects.create(
            product=self.product,
            code="SEC-TKP",
            short_name="sec-tkp",
            short_name_ru="разд-tkp",
            name_en="TKP EN",
            name_ru="ТКП RU",
            accounting_type="Раздел",
            exclude_from_tkp_autofill=True,
            position=1,
        )
        response = self._save(
            {
                "tables": {
                    "typical-sections": [
                        {
                            "id": section.pk,
                            "fields": {"exclude_from_tkp_autofill": False},
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        section.refresh_from_db()
        self.assertFalse(section.exclude_from_tkp_autofill)

        response = self._save(
            {
                "tables": {
                    "typical-sections": [
                        {
                            "id": section.pk,
                            "fields": {"exclude_from_tkp_autofill": "true"},
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 200)
        section.refresh_from_db()
        self.assertTrue(section.exclude_from_tkp_autofill)

    def test_workspace_save_deletes_typical_section(self):
        ensure_system_dsc_section(self.product)
        section = TypicalSection.objects.create(
            product=self.product,
            code="SEC-DEL",
            short_name="sec-del",
            short_name_ru="разд-del",
            name_en="Delete EN",
            name_ru="Удаляемый RU",
            accounting_type="Раздел",
            position=2,
        )
        structure = SectionStructure.objects.create(
            product=self.product,
            section=section,
            subsections="Подразделы удаления",
            position=1,
        )
        composition = TypicalServiceComposition.objects.create(
            product=self.product,
            section=section,
            service_composition="Состав удаления",
            position=1,
        )
        tariff = Tariff.objects.create(
            product=self.product,
            section=section,
            base_rate_vpm="10.00",
            service_hours=4,
            service_days_tkp=2,
            created_by=self.user,
            position=1,
        )
        response = self._save(
            {
                "tables": {
                    "typical-sections": [
                        {"id": section.pk, "deleted": True},
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("typical-sections", payload["tables"])
        self.assertIn("section-structures", payload["tables"])
        self.assertIn("typical-service-compositions", payload["tables"])
        self.assertIn("tariffs", payload["tables"])
        self.assertFalse(TypicalSection.objects.filter(pk=section.pk).exists())
        self.assertFalse(SectionStructure.objects.filter(pk=structure.pk).exists())
        self.assertFalse(TypicalServiceComposition.objects.filter(pk=composition.pk).exists())
        self.assertFalse(Tariff.objects.filter(pk=tariff.pk).exists())
        dsc = TypicalSection.objects.get(product=self.product, code="DSC")
        self.assertTrue(dsc.is_system_dsc)

    def test_workspace_save_rejects_system_dsc_typical_section_delete(self):
        dsc = ensure_system_dsc_section(self.product)
        response = self._save(
            {
                "tables": {
                    "typical-sections": [
                        {"id": dsc.pk, "deleted": True},
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertTrue(any(item["table"] == "typical-sections" for item in payload["errors"]))
        self.assertTrue(TypicalSection.objects.filter(pk=dsc.pk).exists())

    def test_workspace_save_creates_typical_section_after_existing(self):
        ensure_system_dsc_section(self.product)
        current = TypicalSection.objects.create(
            product=self.product,
            code="SEC-CUR",
            short_name="sec-cur",
            short_name_ru="разд-тек",
            name_en="Current section EN",
            name_ru="Текущий раздел",
            accounting_type="Раздел",
            position=2,
        )
        ensure_system_dsc_section(self.product)
        current.refresh_from_db()
        response = self._save(
            {
                "tables": {
                    "typical-sections": [
                        {
                            "id": "new-1",
                            "new": True,
                            "after_id": current.pk,
                            "fields": {
                                "code": "SEC-INS",
                                "short_name": "sec-ins",
                                "short_name_ru": "разд-вст",
                                "name_en": "Inserted EN",
                                "name_ru": "Вставленный RU",
                                "accounting_type": "Раздел",
                            },
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("typical-sections", payload["tables"])
        self.assertIn("section-structures", payload["tables"])
        self.assertIn("typical-service-compositions", payload["tables"])
        self.assertIn("tariffs", payload["tables"])
        created = TypicalSection.objects.get(product=self.product, code="SEC-INS")
        current.refresh_from_db()
        self.assertEqual(created.name_ru, "Вставленный RU")
        self.assertEqual(created.product_id, self.product.pk)
        self.assertGreater(created.position, current.position)

    def test_workspace_save_typical_section_specialty_ids(self):
        geology = ExpertSpecialty.objects.create(specialty="Геология WS", position=1)
        mining = ExpertSpecialty.objects.create(specialty="Горное дело WS", position=2)
        ecology = ExpertSpecialty.objects.create(specialty="Экология WS", position=3)
        section = TypicalSection.objects.create(
            product=self.product,
            code="SEC-SPEC",
            short_name="sec-spec",
            name_en="Spec EN",
            name_ru="Спец RU",
            accounting_type="Раздел",
            position=1,
        )
        TypicalSectionSpecialty.objects.create(section=section, specialty=geology, rank=1)
        TypicalSectionSpecialty.objects.create(section=section, specialty=mining, rank=2)
        response = self._save(
            {
                "tables": {
                    "typical-sections": [
                        {
                            "id": section.pk,
                            "fields": {
                                "specialty_ids": [mining.pk, ecology.pk, geology.pk],
                            },
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(
            list(section.ranked_specialties.values_list("specialty_id", "rank")),
            [(mining.pk, 1), (ecology.pk, 2), (geology.pk, 3)],
        )

        cleared = self._save(
            {
                "tables": {
                    "typical-sections": [
                        {
                            "id": section.pk,
                            "fields": {"specialty_ids": []},
                        }
                    ]
                }
            }
        )
        self.assertEqual(cleared.status_code, 200)
        self.assertFalse(section.ranked_specialties.exists())

    def test_workspace_save_updates_section_structure_fields(self):
        current = TypicalSection.objects.create(
            product=self.product,
            code="STR-CUR",
            short_name="str-cur",
            short_name_ru="стр-тек",
            name_en="Current structure section",
            name_ru="Текущий раздел структуры",
            accounting_type="Раздел",
            position=1,
        )
        target = TypicalSection.objects.create(
            product=self.product,
            code="STR-NEW",
            short_name="str-new",
            short_name_ru="стр-нов",
            name_en="New structure section",
            name_ru="Новый раздел структуры",
            accounting_type="Раздел",
            position=2,
        )
        structure = SectionStructure.objects.create(
            product=self.product,
            section=current,
            subsections="Старые подразделы",
            position=1,
        )
        response = self._save(
            {
                "tables": {
                    "section-structures": [
                        {
                            "id": structure.pk,
                            "fields": {
                                "section": target.pk,
                                "subsections": "Новые подразделы",
                            },
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("section-structures", payload["tables"])
        structure.refresh_from_db()
        self.assertEqual(structure.section_id, target.pk)
        self.assertEqual(structure.subsections, "Новые подразделы")
        self.assertEqual(structure.product_id, self.product.pk)

    def test_workspace_save_creates_section_structure_after_existing(self):
        current_section = TypicalSection.objects.create(
            product=self.product,
            code="STR-CUR",
            short_name="str-cur",
            name_en="Current structure section",
            name_ru="Текущий раздел структуры",
            accounting_type="Раздел",
            position=1,
        )
        current = SectionStructure.objects.create(
            product=self.product,
            section=current_section,
            subsections="Текущие подразделы",
            position=1,
        )
        response = self._save(
            {
                "tables": {
                    "section-structures": [
                        {
                            "id": "new-1",
                            "new": True,
                            "after_id": current.pk,
                            "fields": {
                                "section": current_section.pk,
                                "subsections": "Вставленные подразделы",
                            },
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("section-structures", payload["tables"])
        created = SectionStructure.objects.get(product=self.product, subsections="Вставленные подразделы")
        current.refresh_from_db()
        self.assertEqual(created.section_id, current_section.pk)
        self.assertGreater(created.position, current.position)
        foreign_section = TypicalSection.objects.create(
            product=self.other_product,
            code="STR-FOR",
            short_name="str-for",
            name_en="Foreign structure section",
            name_ru="Чужой раздел структуры",
            accounting_type="Раздел",
            position=1,
        )
        foreign = SectionStructure.objects.create(
            product=self.other_product,
            section=foreign_section,
            subsections="Чужие подразделы",
            position=1,
        )
        response = self._save(
            {
                "tables": {
                    "section-structures": [
                        {
                            "id": foreign.pk,
                            "fields": {"subsections": "HACK"},
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertTrue(any(item["table"] == "section-structures" for item in payload["errors"]))
        foreign.refresh_from_db()
        self.assertEqual(foreign.subsections, "Чужие подразделы")

    def test_workspace_save_rejects_section_from_another_product(self):
        current = TypicalSection.objects.create(
            product=self.product,
            code="STR-OWN",
            short_name="str-own",
            name_en="Own structure section",
            name_ru="Свой раздел структуры",
            accounting_type="Раздел",
            position=1,
        )
        foreign_section = TypicalSection.objects.create(
            product=self.other_product,
            code="STR-OTH",
            short_name="str-oth",
            name_en="Other product section",
            name_ru="Раздел другого продукта",
            accounting_type="Раздел",
            position=1,
        )
        structure = SectionStructure.objects.create(
            product=self.product,
            section=current,
            subsections="Свои подразделы",
            position=1,
        )
        response = self._save(
            {
                "tables": {
                    "section-structures": [
                        {
                            "id": structure.pk,
                            "fields": {"section": foreign_section.pk},
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertTrue(any(item["field"] == "section" for item in payload["errors"]))
        structure.refresh_from_db()
        self.assertEqual(structure.section_id, current.pk)

    def test_workspace_save_updates_report_structure_name(self):
        report = ReportStructure.objects.create(
            product=self.product,
            level=2,
            code="RS-CUR",
            name="Старое наименование отчета",
            position=1,
        )
        response = self._save(
            {
                "tables": {
                    "report-structures": [
                        {
                            "id": report.pk,
                            "fields": {"name": "Новое наименование отчета"},
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("report-structures", payload["tables"])
        report.refresh_from_db()
        self.assertEqual(report.name, "Новое наименование отчета")
        self.assertEqual(report.code, "RS-CUR")
        self.assertEqual(report.level, 2)
        self.assertEqual(report.product_id, self.product.pk)

    def test_workspace_save_rejects_foreign_report_structure_row(self):
        foreign = ReportStructure.objects.create(
            product=self.other_product,
            level=1,
            code="RS-FOR",
            name="Чужое наименование",
            position=1,
        )
        response = self._save(
            {
                "tables": {
                    "report-structures": [
                        {
                            "id": foreign.pk,
                            "fields": {"name": "HACK"},
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertTrue(any(item["table"] == "report-structures" for item in payload["errors"]))
        foreign.refresh_from_db()
        self.assertEqual(foreign.name, "Чужое наименование")

    def test_workspace_save_updates_tariff_fields(self):
        current = TypicalSection.objects.create(
            product=self.product,
            code="TAR-CUR",
            short_name="tar-cur",
            name_en="Current tariff section",
            name_ru="Текущий раздел тарифа",
            accounting_type="Раздел",
            position=1,
        )
        target = TypicalSection.objects.create(
            product=self.product,
            code="TAR-NEW",
            short_name="tar-new",
            name_en="New tariff section",
            name_ru="Новый раздел тарифа",
            accounting_type="Раздел",
            position=2,
        )
        tariff = Tariff.objects.create(
            product=self.product,
            section=current,
            base_rate_vpm="10.50",
            service_hours=8,
            service_days_tkp=5,
            created_by=self.user,
            position=1,
        )
        response = self._save(
            {
                "tables": {
                    "tariffs": [
                        {
                            "id": tariff.pk,
                            "fields": {
                                "section": target.pk,
                                "base_rate_vpm": "12.75",
                                "service_hours": "16",
                                "service_days_tkp": "9",
                            },
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("tariffs", payload["tables"])
        tariff.refresh_from_db()
        self.assertEqual(tariff.section_id, target.pk)
        self.assertEqual(tariff.base_rate_vpm, Decimal("12.75"))
        self.assertEqual(tariff.service_hours, 16)
        self.assertEqual(tariff.service_days_tkp, 9)
        self.assertEqual(tariff.product_id, self.product.pk)
        self.assertEqual(tariff.created_by_id, self.user.pk)

    def test_workspace_save_creates_tariff_after_existing(self):
        current_section = TypicalSection.objects.create(
            product=self.product,
            code="TAR-CUR",
            short_name="tar-cur",
            name_en="Current tariff section",
            name_ru="Текущий раздел тарифа",
            accounting_type="Раздел",
            position=1,
        )
        current = Tariff.objects.create(
            product=self.product,
            section=current_section,
            base_rate_vpm="10.50",
            service_hours=8,
            service_days_tkp=5,
            created_by=self.user,
            position=1,
        )
        response = self._save(
            {
                "tables": {
                    "tariffs": [
                        {
                            "id": "new-1",
                            "new": True,
                            "after_id": current.pk,
                            "fields": {
                                "section": current_section.pk,
                                "base_rate_vpm": "1.00",
                                "service_hours": "0",
                                "service_days_tkp": "0",
                            },
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("tariffs", payload["tables"])
        created = Tariff.objects.exclude(pk=current.pk).get(product=self.product, section=current_section)
        current.refresh_from_db()
        self.assertEqual(created.created_by_id, self.user.pk)
        self.assertEqual(created.base_rate_vpm, Decimal("1.00"))
        self.assertGreater(created.position, current.position)
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        manager_group, _ = Group.objects.get_or_create(name=DEPARTMENT_HEAD_GROUP)
        self.user.groups.add(manager_group)
        other = get_user_model().objects.create_user(
            username="policy-tariff-owner",
            password="secret123",
            is_staff=True,
            first_name="Иван",
            last_name="Петров",
        )
        other.groups.add(manager_group)
        Employee.objects.create(user=other, job_title="Руководитель направления ТДД")
        section = TypicalSection.objects.create(
            product=self.product,
            code="TAR-OWN",
            short_name="tar-own",
            name_en="Owner tariff section",
            name_ru="Раздел тарифа владельца",
            accounting_type="Раздел",
            position=1,
        )
        tariff = Tariff.objects.create(
            product=self.product,
            section=section,
            base_rate_vpm="4.00",
            service_hours=3,
            service_days_tkp=2,
            created_by=self.user,
            position=1,
        )
        table = self.client.get(
            reverse("policy_tariffs_table"),
            {"product": self.product.pk, "workspace": "1"},
        )
        self.assertContains(table, 'data-inline-field="owner"', html=False)
        self.assertContains(table, 'data-inline-type="select"', html=False)
        self.assertIn('"owners"', table.context["policy_inline_options_json"])
        self.assertIn(f'"id": {other.pk}', table.context["policy_inline_options_json"])
        self.assertIn("Руководитель направления ТДД", table.context["policy_inline_options_json"])

        response = self._save(
            {
                "tables": {
                    "tariffs": [
                        {
                            "id": tariff.pk,
                            "fields": {"owner": other.pk},
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        tariff.refresh_from_db()
        self.assertEqual(tariff.created_by_id, other.pk)

    def test_workspace_save_rejects_foreign_tariff_row(self):
        foreign_section = TypicalSection.objects.create(
            product=self.other_product,
            code="TAR-FOR",
            short_name="tar-for",
            name_en="Foreign tariff section",
            name_ru="Чужой раздел тарифа",
            accounting_type="Раздел",
            position=1,
        )
        foreign = Tariff.objects.create(
            product=self.other_product,
            section=foreign_section,
            base_rate_vpm="3.00",
            service_hours=2,
            service_days_tkp=1,
            created_by=self.user,
            position=1,
        )
        response = self._save(
            {
                "tables": {
                    "tariffs": [
                        {
                            "id": foreign.pk,
                            "fields": {"service_hours": "99"},
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertTrue(any(item["table"] == "tariffs" for item in payload["errors"]))
        foreign.refresh_from_db()
        self.assertEqual(foreign.service_hours, 2)

    def test_workspace_save_rejects_tariff_section_from_another_product(self):
        current = TypicalSection.objects.create(
            product=self.product,
            code="TAR-OWN",
            short_name="tar-own",
            name_en="Own tariff section",
            name_ru="Свой раздел тарифа",
            accounting_type="Раздел",
            position=1,
        )
        foreign_section = TypicalSection.objects.create(
            product=self.other_product,
            code="TAR-OTH",
            short_name="tar-oth",
            name_en="Other product tariff section",
            name_ru="Раздел тарифа другого продукта",
            accounting_type="Раздел",
            position=1,
        )
        tariff = Tariff.objects.create(
            product=self.product,
            section=current,
            base_rate_vpm="4.00",
            service_hours=3,
            service_days_tkp=2,
            created_by=self.user,
            position=1,
        )
        response = self._save(
            {
                "tables": {
                    "tariffs": [
                        {
                            "id": tariff.pk,
                            "fields": {"section": foreign_section.pk},
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertTrue(any(item["field"] == "section" for item in payload["errors"]))
        tariff.refresh_from_db()
        self.assertEqual(tariff.section_id, current.pk)

    def test_workspace_save_updates_typical_service_term_fields(self):
        term = TypicalServiceTerm.objects.create(
            product=self.product,
            source_data_weeks="2.0",
            source_data_term_unit=TypicalServiceTerm.TermUnit.WEEKS,
            preliminary_report_months="1.5",
            preliminary_report_term_unit=TypicalServiceTerm.TermUnit.MONTHS,
            final_report_weeks="3.0",
            final_report_term_unit=TypicalServiceTerm.TermUnit.WEEKS,
            position=1,
        )
        response = self._save(
            {
                "tables": {
                    "typical-service-terms": [
                        {
                            "id": term.pk,
                            "fields": {
                                "source_data_weeks": "4.0",
                                "source_data_term_unit": TypicalServiceTerm.TermUnit.DAYS,
                                "preliminary_report_months": "2.5",
                                "preliminary_report_term_unit": TypicalServiceTerm.TermUnit.WEEKS,
                                "final_report_weeks": "6",
                                "final_report_term_unit": TypicalServiceTerm.TermUnit.MONTHS,
                                "product": self.other_product.pk,
                            },
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("typical-service-terms", payload["tables"])
        term.refresh_from_db()
        self.assertEqual(term.source_data_weeks, Decimal("4.0"))
        self.assertEqual(term.source_data_term_unit, TypicalServiceTerm.TermUnit.DAYS)
        self.assertEqual(term.preliminary_report_months, Decimal("2.5"))
        self.assertEqual(term.preliminary_report_term_unit, TypicalServiceTerm.TermUnit.WEEKS)
        self.assertEqual(term.final_report_weeks, Decimal("6"))
        self.assertEqual(term.final_report_term_unit, TypicalServiceTerm.TermUnit.MONTHS)
        self.assertEqual(term.product_id, self.product.pk)

    def test_workspace_save_rejects_typical_service_term_fractional_days(self):
        term = TypicalServiceTerm.objects.create(
            product=self.product,
            source_data_weeks="2.0",
            source_data_term_unit=TypicalServiceTerm.TermUnit.WEEKS,
            preliminary_report_months="1.5",
            preliminary_report_term_unit=TypicalServiceTerm.TermUnit.MONTHS,
            final_report_weeks="3.0",
            position=1,
        )
        response = self._save(
            {
                "tables": {
                    "typical-service-terms": [
                        {
                            "id": term.pk,
                            "fields": {
                                "source_data_weeks": "2.5",
                                "source_data_term_unit": TypicalServiceTerm.TermUnit.DAYS,
                            },
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertTrue(
            any(
                item["table"] == "typical-service-terms" and item["field"] == "source_data_weeks"
                for item in payload["errors"]
            )
        )
        term.refresh_from_db()
        self.assertEqual(term.source_data_weeks, Decimal("2.0"))
        self.assertEqual(term.source_data_term_unit, TypicalServiceTerm.TermUnit.WEEKS)

    def test_workspace_save_rejects_foreign_typical_service_term_row(self):
        foreign = TypicalServiceTerm.objects.create(
            product=self.other_product,
            source_data_weeks="1.0",
            preliminary_report_months="1.0",
            final_report_weeks="1.0",
            position=1,
        )
        response = self._save(
            {
                "tables": {
                    "typical-service-terms": [
                        {
                            "id": foreign.pk,
                            "fields": {"final_report_weeks": "99"},
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertTrue(any(item["table"] == "typical-service-terms" for item in payload["errors"]))
        foreign.refresh_from_db()
        self.assertEqual(foreign.final_report_weeks, Decimal("1.0"))

    def test_workspace_save_updates_typical_service_composition_fields(self):
        current = TypicalSection.objects.create(
            product=self.product,
            code="CMP-CUR",
            short_name="cmp-cur",
            name_en="Current composition section",
            name_ru="Текущий раздел состава",
            accounting_type="Раздел",
            position=1,
        )
        target = TypicalSection.objects.create(
            product=self.product,
            code="CMP-NEW",
            short_name="cmp-new",
            name_en="New composition section",
            name_ru="Новый раздел состава",
            accounting_type="Раздел",
            position=2,
        )
        item = TypicalServiceComposition.objects.create(
            product=self.product,
            section=current,
            service_composition="Старый состав",
            service_composition_editor_state={
                "html": "<p>Старый состав</p>",
                "plain_text": "Старый состав",
            },
            position=1,
        )
        editor_state = {
            "html": "<p><strong>Новый состав</strong></p>",
            "plain_text": "Новый состав",
        }
        response = self._save(
            {
                "tables": {
                    "typical-service-compositions": [
                        {
                            "id": item.pk,
                            "fields": {
                                "section": target.pk,
                                "service_composition_editor_state": editor_state,
                            },
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("typical-service-compositions", payload["tables"])
        item.refresh_from_db()
        self.assertEqual(item.section_id, target.pk)
        self.assertEqual(item.service_composition, "Новый состав")
        self.assertEqual(item.service_composition_editor_state, editor_state)
        self.assertEqual(item.product_id, self.product.pk)

    def test_workspace_save_creates_typical_service_composition_after_existing(self):
        current_section = TypicalSection.objects.create(
            product=self.product,
            code="CMP-CUR",
            short_name="cmp-cur",
            name_en="Current composition section",
            name_ru="Текущий раздел состава",
            accounting_type="Раздел",
            position=1,
        )
        current = TypicalServiceComposition.objects.create(
            product=self.product,
            section=current_section,
            service_composition="Текущий состав",
            position=1,
        )
        editor_state = {"html": "<p>Вставленный состав</p>", "plain_text": "Вставленный состав"}
        response = self._save(
            {
                "tables": {
                    "typical-service-compositions": [
                        {
                            "id": "new-1",
                            "new": True,
                            "after_id": current.pk,
                            "fields": {
                                "section": current_section.pk,
                                "service_composition_editor_state": editor_state,
                            },
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("typical-service-compositions", payload["tables"])
        created = TypicalServiceComposition.objects.get(
            product=self.product,
            service_composition="Вставленный состав",
        )
        current.refresh_from_db()
        self.assertEqual(created.section_id, current_section.pk)
        self.assertEqual(created.service_composition_editor_state, editor_state)
        self.assertGreater(created.position, current.position)
        foreign_section = TypicalSection.objects.create(
            product=self.other_product,
            code="CMP-FOR",
            short_name="cmp-for",
            name_en="Foreign composition section",
            name_ru="Чужой раздел состава",
            accounting_type="Раздел",
            position=1,
        )
        foreign = TypicalServiceComposition.objects.create(
            product=self.other_product,
            section=foreign_section,
            service_composition="Чужой состав",
            service_composition_editor_state={
                "html": "<p>Чужой состав</p>",
                "plain_text": "Чужой состав",
            },
            position=1,
        )
        response = self._save(
            {
                "tables": {
                    "typical-service-compositions": [
                        {
                            "id": foreign.pk,
                            "fields": {
                                "service_composition_editor_state": {
                                    "html": "<p>Взлом</p>",
                                    "plain_text": "Взлом",
                                },
                            },
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertTrue(
            any(item["table"] == "typical-service-compositions" for item in payload["errors"])
        )
        foreign.refresh_from_db()
        self.assertEqual(foreign.service_composition, "Чужой состав")

    def test_workspace_save_rejects_other_product_section_for_composition(self):
        current = TypicalSection.objects.create(
            product=self.product,
            code="CMP-OWN",
            short_name="cmp-own",
            name_en="Own composition section",
            name_ru="Свой раздел состава",
            accounting_type="Раздел",
            position=1,
        )
        foreign_section = TypicalSection.objects.create(
            product=self.other_product,
            code="CMP-X",
            short_name="cmp-x",
            name_en="Other product section",
            name_ru="Раздел другого продукта",
            accounting_type="Раздел",
            position=1,
        )
        item = TypicalServiceComposition.objects.create(
            product=self.product,
            section=current,
            service_composition="Состав",
            service_composition_editor_state={"html": "<p>Состав</p>", "plain_text": "Состав"},
            position=1,
        )
        response = self._save(
            {
                "tables": {
                    "typical-service-compositions": [
                        {
                            "id": item.pk,
                            "fields": {"section": foreign_section.pk},
                        }
                    ]
                }
            }
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertTrue(
            any(
                item["table"] == "typical-service-compositions" and item["field"] == "section"
                for item in payload["errors"]
            )
        )
        item.refresh_from_db()
        self.assertEqual(item.section_id, current.pk)

    def test_workspace_save_requires_staff(self):
        anonymous = Client()
        response = anonymous.post(
            reverse("product_workspace_save", args=[self.product.pk]),
            data=json.dumps({"tables": {"products": []}}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 302)

        nonstaff = get_user_model().objects.create_user(
            username="policy-workspace-save-nonstaff",
            password="secret123",
            is_staff=False,
        )
        self.client.force_login(nonstaff)
        forbidden = self._save({"tables": {"products": []}})
        self.assertEqual(forbidden.status_code, 302)


class PolicyFragmentMutationContractTests(TestCase):
    product_dependencies = [
        "consulting-directions",
        "products",
        "service-goal-reports",
        "typical-sections",
        "section-structures",
        "report-structures",
        "typical-service-compositions",
        "typical-service-terms",
        "tariffs",
    ]
    dependencies = {
        "consulting-direction": product_dependencies,
        "product": product_dependencies,
        "typical-section": [
            "typical-sections",
            "section-structures",
            "typical-service-compositions",
            "tariffs",
        ],
        "section-structure": ["section-structures"],
        "report-structure": ["report-structures"],
        "service-goal-report": ["service-goal-reports"],
        "typical-service-composition": ["typical-service-compositions"],
        "typical-service-term": ["typical-service-terms"],
        "expertise-direction": [
            "expertise-directions",
            "typical-sections",
            "specialty-tariffs",
        ],
        "grade": ["grades"],
        "expert-specialty": [
            "expert-specialties",
            "specialty-tariffs",
            "typical-sections",
        ],
        "specialty-tariff": ["specialty-tariffs"],
        "tariff": ["tariffs"],
    }

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="policy-fragment-contract",
            password="secret123",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.product = Product.objects.create(
            short_name="FC1",
            name_en="Fragment contract",
            display_name="Fragment contract",
            name_ru="Фрагментный контракт",
            position=1,
        )
        self.section = TypicalSection.objects.create(
            product=self.product,
            code="FC-1",
            short_name="fc-section",
            short_name_ru="фрагмент",
            name_en="Fragment section",
            name_ru="Фрагментный раздел",
            accounting_type="Раздел",
            position=1,
        )

    def _assert_small_response(self, response, expected):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")
        self.assertEqual(response["HX-Reswap"], "none")
        self.assertEqual(json.loads(response["HX-Trigger"]), {"policy-updated": expected})
        self.assertNotContains(response, 'id="policy-pane"', html=False)

    def test_central_url_entity_map_has_exact_dependencies(self):
        for url_name, entity in policy_views.POLICY_MUTATION_URL_ENTITY.items():
            with self.subTest(url_name=url_name, entity=entity):
                request = SimpleNamespace(
                    resolver_match=SimpleNamespace(url_name=url_name)
                )
                detail = policy_views._policy_mutation_detail(request)
                self.assertEqual(detail["tables"], self.dependencies[entity])
                self.assertEqual(
                    detail["refreshFilters"],
                    entity in {"product", "consulting-direction"},
                )
                self.assertEqual(
                    detail.get("productsReordered", False),
                    url_name in {"product_move_up", "product_move_down"},
                )
                if url_name.endswith(("_move_up", "_move_down")):
                    self.assertEqual(
                        detail["reorderedTable"],
                        policy_views.POLICY_ENTITY_TABLE_KEY[entity],
                    )
                else:
                    self.assertNotIn("reorderedTable", detail)

    def test_product_reorder_and_section_cascade_use_exact_contracts(self):
        second = Product.objects.create(
            short_name="FC2",
            name_en="Second fragment contract",
            display_name="Second fragment contract",
            name_ru="Второй фрагментный контракт",
            position=2,
        )
        product_response = self.client.post(
            reverse("product_move_up", args=[second.pk]),
            HTTP_HX_REQUEST="true",
        )
        self._assert_small_response(
            product_response,
            {
                "tables": self.product_dependencies,
                "refreshFilters": True,
                "reorderedTable": "products",
                "productsReordered": True,
            },
        )
        caches["policy"].clear()
        catalog = self.client.get(reverse("policy_filter_catalog")).json()["products"]
        self.assertEqual([item["id"] for item in catalog[:2]], [second.pk, self.product.pk])

        section_response = self.client.post(
            reverse("section_delete", args=[self.section.pk]),
            HTTP_HX_REQUEST="true",
        )
        self._assert_small_response(
            section_response,
            {
                "tables": self.dependencies["typical-section"],
                "refreshFilters": False,
            },
        )

    def test_invalid_htmx_form_and_non_htmx_fallback_stay_compatible(self):
        invalid = self.client.post(
            reverse("product_form_create"),
            {},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertEqual(invalid["HX-Retarget"], "#policy-modal .modal-content")
        self.assertEqual(invalid["HX-Reswap"], "innerHTML")
        self.assertContains(invalid, 'hx-target="#policy-modal .modal-content"', html=False)
        self.assertNotContains(invalid, 'id="policy-pane"', html=False)

        fallback = self.client.post(
            reverse("product_move_down", args=[self.product.pk]),
        )
        self.assertEqual(fallback.status_code, 200)
        self.assertEqual(fallback["HX-Trigger"], "policy-updated")
        self.assertContains(fallback, 'id="policy-pane"', html=False)

    def test_tariff_fragment_remains_user_scoped_after_mutation(self):
        manager_group, _ = Group.objects.get_or_create(name=DEPARTMENT_HEAD_GROUP)
        self.user.groups.add(manager_group)
        other = get_user_model().objects.create_user(
            username="policy-fragment-other",
            password="secret123",
        )
        own_tariff = Tariff.objects.create(
            product=self.product,
            section=self.section,
            created_by=self.user,
            position=1,
        )
        Tariff.objects.create(
            product=self.product,
            section=self.section,
            created_by=other,
            position=1,
        )

        fragment = self.client.get(reverse("policy_tariffs_table"))
        self.assertEqual(fragment.context["paginator"].count, 1)
        self.assertEqual(fragment.context["tariffs"][0], own_tariff)

        response = self.client.post(
            reverse("tariff_delete", args=[own_tariff.pk]),
            HTTP_HX_REQUEST="true",
        )
        self._assert_small_response(
            response,
            {"tables": ["tariffs"], "refreshFilters": False},
        )

    def test_forms_uploads_sidebars_and_gantt_are_fragment_scoped(self):
        templates_dir = Path(__file__).resolve().parent / "templates" / "policy_app"
        for form_name in (
            "product_form.html",
            "section_form.html",
            "structure_form.html",
            "report_structure_form.html",
            "service_goal_report_form.html",
            "typical_service_composition_form.html",
            "typical_service_term_form.html",
            "consulting_direction_form.html",
            "expertise_direction_form.html",
            "grade_form.html",
            "specialty_tariff_form.html",
            "tariff_form.html",
        ):
            with self.subTest(form=form_name):
                source = (templates_dir / form_name).read_text()
                self.assertIn('hx-target="#policy-modal .modal-content"', source)
                self.assertIn('hx-swap="innerHTML"', source)
                self.assertNotIn('hx-target="#policy-pane"', source)

        specialty_form = (
            Path(__file__).resolve().parent.parent
            / "experts_app"
            / "templates"
            / "experts_app"
            / "specialty_form.html"
        ).read_text()
        self.assertIn('hx-target="#policy-modal .modal-content"', specialty_form)
        self.assertIn('data-policy-modal-size="xl"', specialty_form)
        self.assertNotIn('hx-target="#policy-pane"', specialty_form)
        self.assertNotIn('hx-target="#experts-pane"', specialty_form)

        root = Path(__file__).resolve().parents[1]
        policy_js = (
            root / "core" / "static" / "core" / "js" / "policy-panels.js"
        ).read_text()
        index_html = (root / "templates" / "index.html").read_text()
        self.assertIn("handlePolicyUpdated(data.policyUpdate)", policy_js)
        self.assertNotIn("htmx.ajax('GET', '/policy/policy/partial/'", policy_js)
        self.assertIn("root.id === 'policy-pane' && data.policyUpdate", policy_js)
        self.assertIn("e.target.id === 'projects-pane'", policy_js)
        self.assertIn("POLICY_MANAGED_REFRESH_CONCURRENCY = 2", policy_js)
        self.assertNotIn("#policy-pane tbody tr[data-product-id]", index_html)
        self.assertEqual(index_html.count("event?.detail?.catalog || window.__policyProductCatalog"), 2)


class TypicalSectionPaginationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="typical-sections-pagination-staff",
            password="secret123",
            is_staff=True,
        )
        self.client.force_login(self.user)

    def _create_product(
        self,
        short_name,
        *,
        position=1,
        consulting="Пилот Горный",
        category="Пилот Аудит",
        subtype="Пилот Проверка",
    ):
        return Product.objects.create(
            short_name=short_name,
            name_en=f"{short_name} product",
            display_name=f"{short_name} display",
            name_ru=f"Продукт {short_name}",
            consulting_type=consulting,
            service_category=category,
            service_subtype=subtype,
            position=position,
        )

    def _create_sections(self, product, count, *, prefix="SEC", start_position=1):
        return [
            TypicalSection.objects.create(
                product=product,
                code=f"{prefix}-{index:03d}",
                short_name=f"{prefix.lower()}-{index:03d}",
                short_name_ru=f"{prefix.lower()}-ru-{index:03d}",
                name_en=f"{prefix} section {index}",
                name_ru=f"Раздел {prefix} {index}",
                accounting_type="Раздел",
                position=start_position + index - 1,
            )
            for index in range(1, count + 1)
        ]

    def test_zero_one_twenty_five_and_twenty_six_rows(self):
        endpoint = reverse("policy_typical_sections_table")

        response = self.client.get(endpoint)
        self.assertEqual(response.context["paginator"].count, 0)
        self.assertContains(response, "0–0 из 0")
        self.assertNotContains(response, "Показаны")
        self.assertContains(response, 'aria-label="Страницы таблицы"', html=False)

        product = self._create_product("COUNT")
        self._create_sections(product, 1)
        response = self.client.get(endpoint)
        self.assertEqual(response.context["paginator"].count, 1)
        self.assertContains(response, "1–1 из 1")
        self.assertContains(response, 'aria-label="Страницы таблицы"', html=False)

        self._create_sections(product, 24, prefix="MORE", start_position=2)
        response = self.client.get(endpoint)
        self.assertEqual(response.context["paginator"].count, 25)
        self.assertContains(response, "1–25 из 25")
        self.assertContains(response, 'aria-label="Страницы таблицы"', html=False)

        self._create_sections(product, 1, prefix="LAST", start_position=26)
        response = self.client.get(endpoint)
        self.assertEqual(response.context["paginator"].count, 26)
        self.assertEqual(len(response.context["sections"]), 25)
        self.assertContains(response, "1–25 из 26")
        self.assertContains(response, 'aria-label="Страницы таблицы"', html=False)
        self.assertContains(
            response,
            'class="pagination pagination-sm mb-0 classifiers-pagination"',
            html=False,
        )

    def test_third_page_range_and_invalid_pages_are_clamped(self):
        product = self._create_product("PAGES")
        sections = self._create_sections(product, 68)
        endpoint = reverse("policy_typical_sections_table")

        third_page = self.client.get(endpoint, {"page": "3"})
        self.assertEqual(third_page.context["page_obj"].number, 3)
        self.assertEqual(list(third_page.context["sections"]), sections[50:])
        self.assertContains(third_page, "51–68 из 68")
        self.assertNotContains(third_page, "Показаны")

        invalid_page = self.client.get(endpoint, {"page": "invalid"})
        self.assertEqual(invalid_page.context["page_obj"].number, 1)

        empty_page = self.client.get(endpoint, {"page": ""})
        self.assertEqual(empty_page.context["page_obj"].number, 1)

        oversized_page = self.client.get(endpoint, {"page": "999"})
        self.assertEqual(oversized_page.context["page_obj"].number, 3)

    def test_page_size_control_normalizes_values_and_targets_current_wrapper(self):
        product = self._create_product("PAGE-SIZE")
        self._create_sections(product, 68)
        endpoint = reverse("policy_typical_sections_table")

        default = self.client.get(endpoint, {"product": product.pk})
        self.assertEqual(default.context["policy_page_size"], 25)
        self.assertEqual(default.context["policy_page_size_options"], (25, 50, 100))
        self.assertEqual(len(default.context["sections"]), 25)
        self.assertContains(default, 'data-policy-table-page-size="25"', html=False)
        self.assertContains(default, 'name="page_size"', html=False)
        self.assertContains(default, '<option value="25" selected>', html=False)
        self.assertContains(default, '<option value="50">', html=False)
        self.assertContains(default, '<option value="100">', html=False)
        self.assertContains(default, 'hx-trigger="change"', html=False)
        self.assertContains(default, 'hx-target="#policy-typical-sections-section"', html=False)
        self.assertContains(default, 'hx-swap="outerHTML"', html=False)
        page_size_query = parse_qs(
            urlparse(unescape(default.context["policy_page_size_url"])).query
        )
        self.assertEqual(page_size_query["product"], [str(product.pk)])
        self.assertEqual(page_size_query["page"], ["1"])
        self.assertNotIn("page_size", page_size_query)

        invalid = self.client.get(endpoint, {"product": product.pk, "page_size": "27"})
        self.assertEqual(invalid.context["policy_page_size"], 25)
        self.assertEqual(len(invalid.context["sections"]), 25)

        fifty = self.client.get(
            endpoint,
            {"product": product.pk, "page_size": 50, "page": 2},
        )
        self.assertEqual(fifty.context["policy_page_size"], 50)
        self.assertEqual(len(fifty.context["sections"]), 18)
        self.assertContains(fifty, "51–68 из 68")

        hundred = self.client.get(endpoint, {"product": product.pk, "page_size": 100})
        self.assertEqual(hundred.context["policy_page_size"], 100)
        self.assertEqual(len(hundred.context["sections"]), 68)
        self.assertContains(hundred, "1–68 из 68")

    def test_combined_filters_and_repeated_products(self):
        first = self._create_product(
            "FILTER-A",
            consulting="Пилот Горный",
            category="Пилот Аудит",
            subtype="Пилот Проверка",
        )
        second = self._create_product(
            "FILTER-B",
            position=2,
            consulting="Пилот Горный",
            category="Пилот Инжиниринг",
            subtype="Пилот Проектирование",
        )
        third = self._create_product(
            "FILTER-C",
            position=3,
            consulting="Пилот Финансовый",
            category="Пилот Аудит",
            subtype="Пилот Проверка",
        )
        self._create_sections(first, 1, prefix="FIRST")
        self._create_sections(second, 1, prefix="SECOND")
        self._create_sections(third, 1, prefix="THIRD")
        endpoint = reverse("policy_typical_sections_table")

        combined = self.client.get(
            endpoint,
            {
                "consulting": "Пилот Горный",
                "category": "Пилот Аудит",
                "subtype": "Пилот Проверка",
                "product": [first.pk, third.pk],
            },
        )
        self.assertEqual(combined.context["paginator"].count, 1)
        self.assertEqual(combined.context["sections"][0].product_id, first.pk)

        repeated_products = self.client.get(
            endpoint,
            {"product": [first.pk, second.pk]},
        )
        self.assertEqual(repeated_products.context["paginator"].count, 2)
        self.assertEqual(
            {section.product_id for section in repeated_products.context["sections"]},
            {first.pk, second.pk},
        )

    def test_filters_are_applied_before_pagination(self):
        matching = self._create_product("MATCH", consulting="Пилот Горный")
        other = self._create_product("OTHER", position=2, consulting="Пилот Финансовый")
        self._create_sections(matching, 2, prefix="MATCH")
        self._create_sections(other, 55, prefix="OTHER")

        response = self.client.get(
            reverse("policy_typical_sections_table"),
            {"consulting": "Пилот Горный"},
        )

        self.assertEqual(response.context["paginator"].count, 2)
        self.assertEqual(len(response.context["sections"]), 2)
        self.assertContains(response, 'aria-label="Страницы таблицы"', html=False)

    def test_pagination_links_preserve_all_filters(self):
        first = self._create_product(
            "LINK-A",
            consulting="Пилот Горный",
            category="Пилот Аудит",
            subtype="Пилот Проверка",
        )
        second = self._create_product(
            "LINK-B",
            position=2,
            consulting="Пилот Горный",
            category="Пилот Аудит",
            subtype="Пилот Проверка",
        )
        self._create_sections(first, 30, prefix="LINKA")
        self._create_sections(second, 30, prefix="LINKB")

        response = self.client.get(
            reverse("policy_typical_sections_table"),
            {
                "consulting": "Пилот Горный",
                "category": "Пилот Аудит",
                "subtype": "Пилот Проверка",
                "product": [first.pk, second.pk],
                "page_size": 25,
            },
        )

        html = unescape(response.content.decode())
        match = re.search(r'hx-get="([^"]*[?&]page=2)"', html)
        self.assertIsNotNone(match)
        query = parse_qs(urlparse(match.group(1)).query)
        self.assertEqual(query["consulting"], ["Пилот Горный"])
        self.assertEqual(query["category"], ["Пилот Аудит"])
        self.assertEqual(query["subtype"], ["Пилот Проверка"])
        self.assertEqual(query["product"], [str(first.pk), str(second.pk)])
        self.assertEqual(query["page_size"], ["25"])
        self.assertEqual(query["page"], ["2"])
        self.assertContains(response, 'hx-target="#policy-typical-sections-section"', html=False)
        self.assertContains(response, 'hx-swap="outerHTML"', html=False)
        download_match = re.search(
            r'<a href="([^"]+)"\s+id="sections-csv-download-btn"',
            html,
        )
        self.assertIsNotNone(download_match)
        download_query = parse_qs(urlparse(download_match.group(1)).query)
        self.assertNotIn("page", download_query)
        self.assertNotIn("page_size", download_query)
        self.assertEqual(download_query["product"], [str(first.pk), str(second.pk)])

    def test_system_dsc_section_is_rendered(self):
        product = self._create_product("DSC-PAGE")
        dsc = ensure_system_dsc_section(product)

        response = self.client.get(
            reverse("policy_typical_sections_table"),
            {"product": product.pk},
        )

        self.assertContains(response, f'id="section-sel-{dsc.pk}"', html=False)
        self.assertContains(response, 'data-system-section="1"', html=False)
        self.assertContains(response, "typical-section-dsc-code")
        self.assertContains(response, "typical-section-system-row")

    def test_csv_exports_full_filtered_set_without_pagination(self):
        matching = self._create_product("CSV-PAGE", consulting="Пилот Горный")
        other = self._create_product("CSV-OTHER", position=2, consulting="Пилот Финансовый")
        self._create_sections(matching, 55, prefix="CSV")
        self._create_sections(other, 2, prefix="OTHER")

        fragment = self.client.get(
            reverse("policy_typical_sections_table"),
            {"consulting": "Пилот Горный", "product": matching.pk},
        )
        self.assertEqual(len(fragment.context["sections"]), 25)
        self.assertEqual(fragment.context["paginator"].count, 55)

        response = self.client.get(
            reverse("section_csv_download"),
            {
                "consulting": "Пилот Горный",
                "product": matching.pk,
                "page": 2,
                "page_size": 25,
            },
        )
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(len(rows), 56)
        self.assertEqual({row[0] for row in rows[1:]}, {"CSV-PAGE"})

    def test_typical_sections_use_stable_product_name_position_id_order(self):
        product_b = self._create_product("B-PRODUCT", position=1)
        product_a = self._create_product("A-PRODUCT", position=2)
        b_section = self._create_sections(product_b, 1, prefix="B", start_position=1)[0]
        a_second = self._create_sections(product_a, 1, prefix="A2", start_position=2)[0]
        a_first_older = self._create_sections(product_a, 1, prefix="A1", start_position=1)[0]
        a_first_newer = self._create_sections(product_a, 1, prefix="A1B", start_position=1)[0]

        response = self.client.get(reverse("policy_typical_sections_table"))

        self.assertEqual(
            [section.pk for section in response.context["sections"]],
            [a_first_older.pk, a_first_newer.pk, a_second.pk, b_section.pk],
        )

    def test_legacy_policy_partial_remains_unpaginated(self):
        product = self._create_product("LEGACY")
        sections = self._create_sections(product, 51)

        response = self.client.get(reverse("policy_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["sections"]), sections)
        self.assertNotContains(response, "1–25 из 51")
        self.assertContains(response, sections[-1].code)

    def test_filter_catalog_is_complete_and_globally_ordered(self):
        later = self._create_product(
            "CAT-LATER",
            position=2,
            consulting="Пилот Финансовый",
            category="Пилот Оценка",
            subtype="Пилот Активы",
        )
        first = self._create_product(
            "CAT-FIRST",
            position=1,
            consulting="Пилот Горный",
            category="Пилот Аудит",
            subtype="Пилот Проверка",
        )

        caches["policy"].clear()
        response = self.client.get(reverse("policy_filter_catalog"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([item["id"] for item in payload["products"]], [first.pk, later.pk])
        self.assertEqual(payload["products"][0]["label"], "CAT-FIRST CAT-FIRST display")
        self.assertEqual(payload["products"][0]["consulting"], "Пилот Горный")
        self.assertIn("consulting_ref_id", payload["products"][0])
        self.assertIn("category_ref_id", payload["products"][0])
        self.assertIn("subtype_ref_id", payload["products"][0])
        self.assertEqual(payload["options"]["consulting"], ["Пилот Горный", "Пилот Финансовый"])
        self.assertEqual(payload["options"]["category"], ["Пилот Аудит", "Пилот Оценка"])
        self.assertEqual(payload["options"]["subtype"], ["Пилот Проверка", "Пилот Активы"])
        self.assertEqual(
            payload["options"]["product"],
            [
                {"id": first.pk, "label": "CAT-FIRST CAT-FIRST display"},
                {"id": later.pk, "label": "CAT-LATER CAT-LATER display"},
            ],
        )

    def test_fragment_and_catalog_require_login(self):
        anonymous = Client()

        for endpoint_name in ("policy_typical_sections_table", "policy_filter_catalog"):
            with self.subTest(endpoint=endpoint_name):
                response = anonymous.get(reverse(endpoint_name))
                self.assertEqual(response.status_code, 302)


class PolicyManagedTablePaginationTests(TestCase):
    managed_endpoints = (
        ("policy_products_table", "products"),
        ("policy_service_goal_reports_table", "service_goal_reports"),
        ("policy_section_structures_table", "structures"),
        ("policy_report_structures_table", "report_structures"),
        ("policy_typical_service_compositions_table", "typical_service_compositions"),
        ("policy_typical_service_terms_table", "typical_service_terms"),
        ("policy_tariffs_table", "tariffs"),
    )

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="managed-policy-tables-staff",
            password="secret123",
            is_staff=True,
        )
        self.client.force_login(self.user)

    def _product(
        self,
        short_name,
        *,
        position=1,
        consulting="Managed Consulting",
        category="Managed Category",
        subtype="Managed Subtype",
    ):
        return Product.objects.create(
            short_name=short_name,
            name_en=f"{short_name} product",
            display_name=f"{short_name} display",
            name_ru=f"Продукт {short_name}",
            consulting_type=consulting,
            service_category=category,
            service_subtype=subtype,
            position=position,
        )

    def _section(self, product, code):
        return TypicalSection.objects.create(
            product=product,
            code=code,
            short_name=code.lower(),
            short_name_ru=f"{code.lower()}-ru",
            name_en=f"{code} section",
            name_ru=f"Раздел {code}",
            accounting_type="Раздел",
            position=1,
        )

    def test_all_paginated_tables_use_unified_footer_and_page_size_data(self):
        endpoint_names = (
            "policy_products_table",
            "policy_service_goal_reports_table",
            "policy_typical_sections_table",
            "policy_section_structures_table",
            "policy_report_structures_table",
            "policy_typical_service_compositions_table",
            "policy_typical_service_terms_table",
            "policy_tariffs_table",
            "policy_expert_specialties_table",
        )
        for endpoint_name in endpoint_names:
            with self.subTest(endpoint=endpoint_name):
                response = self.client.get(reverse(endpoint_name))
                self.assertContains(response, 'class="policy-table-editor"', html=False)
                self.assertContains(response, 'class="policy-table-footer"', html=False)
                self.assertContains(response, 'class="policy-table-footer-actions', html=False)
                self.assertContains(response, 'class="policy-table-pagination"', html=False)
                self.assertContains(response, 'data-policy-table-page-size="25"', html=False)
                self.assertContains(response, 'aria-label="Страницы таблицы"', html=False)
                self.assertContains(response, "Показано строк")
                self.assertContains(response, 'bi-chevron-left', html=False)
                self.assertContains(response, 'bi-chevron-right', html=False)
                self.assertNotContains(response, "&laquo;")
                self.assertNotContains(response, "&raquo;")
                self.assertNotContains(response, "Строк на странице")
                self.assertRegex(
                    response.content.decode(),
                    r"</table>\s*</div>\s*<div class=\"policy-table-footer\">",
                )

        nonstaff = get_user_model().objects.create_user(
            username="managed-policy-tables-nonstaff",
            password="secret123",
            is_staff=False,
        )
        self.client.force_login(nonstaff)
        response = self.client.get(reverse("policy_products_table"))
        self.assertContains(response, 'class="policy-table-footer"', html=False)
        self.assertContains(response, 'class="policy-table-footer-actions"></div>', html=False)
        self.assertContains(response, 'class="policy-table-pagination"', html=False)
        self.assertNotContains(response, "Добавить строку")

    def test_policy_table_footer_sticky_css_and_js_helpers(self):
        root = Path(__file__).resolve().parents[1]
        css = (root / "core" / "static" / "core" / "css" / "site.css").read_text()
        js = (root / "core" / "static" / "core" / "js" / "policy-panels.js").read_text()
        self.assertIn("#policy-pane .policy-table-editor {", css)
        self.assertIn("#policy-pane .policy-table-footer {\n  position: sticky;", css)
        self.assertIn("#policy-pane .policy-table-footer.is-stuck", css)
        self.assertIn(".policy-sticky-actions-marker", css)
        self.assertIn("function attachPolicyTableFooterStickyState(footer)", js)
        self.assertIn("initPolicyTableFooterStickyState(fragment)", js)

    def test_reusable_paginator_boundaries_links_order_and_page_clamp(self):
        endpoint = reverse("policy_products_table")
        response = self.client.get(endpoint)
        self.assertEqual(response.context["paginator"].count, 0)
        self.assertContains(response, "0–0 из 0")
        self.assertContains(response, 'aria-label="Страницы таблицы"', html=False)

        products = Product.objects.bulk_create(
            [
                Product(
                    short_name=f"PAGE-{index:03d}",
                    name_en=f"Product {index}",
                    display_name=f"Product {index}",
                    name_ru=f"Продукт {index}",
                    consulting_type="Managed Consulting",
                    service_category="Managed Category",
                    service_subtype="Managed Subtype",
                    position=69 - index,
                )
                for index in range(1, 69)
            ]
        )

        one = self.client.get(endpoint, {"product": products[0].pk})
        self.assertEqual(one.context["paginator"].count, 1)
        self.assertContains(one, 'aria-label="Страницы таблицы"', html=False)

        fifty = self.client.get(
            endpoint,
            {"product": [product.pk for product in products[:50]]},
        )
        self.assertEqual(fifty.context["paginator"].count, 50)
        self.assertContains(fifty, 'aria-label="Страницы таблицы"', html=False)

        first_page = self.client.get(
            endpoint,
            {
                "consulting": "Managed Consulting",
                "category": "Managed Category",
                "subtype": "Managed Subtype",
                "product": [product.pk for product in products],
            },
        )
        self.assertEqual(first_page.context["paginator"].count, 68)
        self.assertEqual(len(first_page.context["products"]), 25)
        self.assertEqual(
            [product.position for product in first_page.context["products"]],
            list(range(1, 26)),
        )
        self.assertContains(first_page, "1–25 из 68")
        self.assertNotContains(first_page, "Показаны")
        self.assertContains(first_page, 'hx-target="#policy-products-section"', html=False)

        third_page = self.client.get(endpoint, {"page": 3})
        self.assertEqual(third_page.context["page_obj"].number, 3)
        self.assertEqual(third_page.context["products"][0].position, 51)
        self.assertEqual(len(third_page.context["products"]), 18)
        self.assertContains(third_page, "51–68 из 68")

        invalid_page = self.client.get(endpoint, {"page": "invalid"})
        self.assertEqual(invalid_page.context["page_obj"].number, 1)
        empty_page = self.client.get(endpoint, {"page": ""})
        self.assertEqual(empty_page.context["page_obj"].number, 1)
        oversized_page = self.client.get(endpoint, {"page": "999"})
        self.assertEqual(oversized_page.context["page_obj"].number, 3)

        html = unescape(first_page.content.decode())
        page_two_link = re.search(r'hx-get="([^"]*[?&]page=2)"', html)
        self.assertIsNotNone(page_two_link)
        query = parse_qs(urlparse(page_two_link.group(1)).query)
        self.assertEqual(query["consulting"], ["Managed Consulting"])
        self.assertEqual(query["category"], ["Managed Category"])
        self.assertEqual(query["subtype"], ["Managed Subtype"])
        self.assertEqual(query["product"], [str(product.pk) for product in products])
        self.assertEqual(query["page_size"], ["25"])

    def test_combined_filters_apply_to_each_managed_model_and_csv_export(self):
        matching = self._product("MANAGED-MATCH")
        other = self._product(
            "MANAGED-OTHER",
            position=2,
            consulting="Other Consulting",
            category="Other Category",
            subtype="Other Subtype",
        )
        matching_section = self._section(matching, "MATCH")
        other_section = self._section(other, "OTHER")

        ServiceGoalReport.objects.create(product=matching, service_goal="Match", position=1)
        ServiceGoalReport.objects.create(product=other, service_goal="Other", position=2)
        SectionStructure.objects.create(product=matching, section=matching_section, subsections="Match", position=1)
        SectionStructure.objects.create(product=other, section=other_section, subsections="Other", position=2)
        ReportStructure.objects.create(product=matching, level=1, code="MATCH", position=1)
        ReportStructure.objects.create(product=other, level=1, code="OTHER", position=1)
        TypicalServiceComposition.objects.create(
            product=matching,
            section=matching_section,
            service_composition="Match",
            position=1,
        )
        TypicalServiceComposition.objects.create(
            product=other,
            section=other_section,
            service_composition="Other",
            position=2,
        )
        TypicalServiceTerm.objects.create(product=matching, position=1)
        TypicalServiceTerm.objects.create(product=other, position=2)
        Tariff.objects.create(
            product=matching,
            section=matching_section,
            created_by=self.user,
            position=1,
        )
        Tariff.objects.create(
            product=other,
            section=other_section,
            created_by=self.user,
            position=2,
        )

        filters = {
            "consulting": "Managed Consulting",
            "category": "Managed Category",
            "subtype": "Managed Subtype",
            "product": [matching.pk, other.pk],
        }
        for endpoint_name, context_key in self.managed_endpoints:
            with self.subTest(endpoint=endpoint_name):
                response = self.client.get(reverse(endpoint_name), filters)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["paginator"].count, 1)
                item = response.context[context_key][0]
                if context_key == "products":
                    self.assertEqual(item.pk, matching.pk)
                else:
                    self.assertEqual(item.product_id, matching.pk)

        csv_endpoints = (
            "product_csv_download",
            "service_goal_report_csv_download",
            "structure_csv_download",
            "report_structure_csv_download",
            "typical_service_composition_csv_download",
            "typical_service_term_csv_download",
            "tariff_csv_download",
        )
        for endpoint_name in csv_endpoints:
            with self.subTest(download=endpoint_name):
                response = self.client.get(reverse(endpoint_name), filters)
                self.assertEqual(response.status_code, 200)
                rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
                self.assertEqual(len(rows), 2)
                self.assertEqual(rows[1][0], matching.short_name)

    def test_report_numbering_continues_across_page_boundary(self):
        product = self._product("REPORT-PAGE")
        ReportStructure.objects.bulk_create(
            [
                ReportStructure(
                    product=product,
                    level=1,
                    code=f"R-{index:03d}",
                    name=f"Раздел {index}",
                    position=index,
                )
                for index in range(1, 52)
            ]
        )

        response = self.client.get(
            reverse("policy_report_structures_table"),
            {"product": product.pk, "page": 3},
        )

        self.assertEqual(response.context["page_obj"].number, 3)
        self.assertEqual(len(response.context["report_structures"]), 1)
        self.assertEqual(response.context["report_structures"][0].display_number, "51")
        self.assertContains(response, ">51<", html=False)

    def test_composition_exports_include_full_filtered_set(self):
        product = self._product("COMPOSITION-EXPORT")
        section = self._section(product, "EXPORT")
        TypicalServiceComposition.objects.bulk_create(
            [
                TypicalServiceComposition(
                    product=product,
                    section=section,
                    service_composition=f"Composition {index}",
                    position=index,
                )
                for index in range(1, 52)
            ]
        )
        filters = {"product": product.pk}

        fragment = self.client.get(reverse("policy_typical_service_compositions_table"), filters)
        self.assertEqual(fragment.context["paginator"].count, 51)
        self.assertEqual(len(fragment.context["typical_service_compositions"]), 25)

        csv_response = self.client.get(reverse("typical_service_composition_csv_download"), filters)
        csv_rows = list(csv.reader(io.StringIO(csv_response.content.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(len(csv_rows), 52)

        docx_response = self.client.get(reverse("typical_service_composition_docx_download"), filters)
        document = Document(io.BytesIO(docx_response.content))
        self.assertEqual(len(document.tables[0].rows), 52)

        xlsx_response = self.client.get(reverse("typical_service_composition_xlsx_download"), filters)
        workbook = load_workbook(io.BytesIO(xlsx_response.content))
        self.assertEqual(workbook.active.max_row, 52)

    def test_tariff_fragment_preserves_role_scope(self):
        department_head = get_user_model().objects.create_user(
            username="managed-tariff-head",
            password="secret123",
            is_staff=True,
        )
        other_head = get_user_model().objects.create_user(
            username="managed-tariff-other",
            password="secret123",
            is_staff=True,
        )
        manager_group, _ = Group.objects.get_or_create(name=DEPARTMENT_HEAD_GROUP)
        department_head.groups.add(manager_group)
        other_head.groups.add(manager_group)
        product = self._product("ROLE-TARIFF")
        section = self._section(product, "ROLE")
        own_tariff = Tariff.objects.create(
            product=product,
            section=section,
            created_by=department_head,
            position=1,
        )
        Tariff.objects.create(
            product=product,
            section=section,
            created_by=other_head,
            position=1,
        )
        self.client.force_login(department_head)

        response = self.client.get(reverse("policy_tariffs_table"))

        self.assertEqual(response.context["paginator"].count, 1)
        self.assertEqual(list(response.context["tariffs"]), [own_tariff])

    def test_legacy_policy_partial_keeps_all_managed_rows_unpaginated(self):
        Product.objects.bulk_create(
            [
                Product(
                    short_name=f"LEGACY-MANAGED-{index:03d}",
                    name_en=f"Legacy {index}",
                    display_name=f"Legacy {index}",
                    name_ru=f"Legacy {index}",
                    position=index,
                )
                for index in range(1, 52)
            ]
        )

        response = self.client.get(reverse("policy_partial"))

        self.assertEqual(len(response.context["products"]), 51)
        self.assertNotContains(response, "policy-table-pagination")
        self.assertContains(response, "LEGACY-MANAGED-051")


class ProductCsvUploadTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="policy-products-admin",
            password="secret123",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.owner = GroupMember.objects.create(
            short_name="IMC Montan",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
            position=1,
        )

    def test_product_csv_upload_creates_products_and_derives_code(self):
        csv_file = SimpleUploadedFile(
            "products.csv",
            (
                "Краткое имя;Наименование на английском языке;Наименование на русском языке;"
                "Отображаемое в системе имя;Вид консалтинга;Тип услуг;Код;Подтип услуги;Владелец\n"
                "AUD;Audit;Аудит;Аудит продукта;Горный;Аудит;Z;Аудит проектных решений;IMC Montan\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(reverse("product_csv_upload"), {"csv_file": csv_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 1)
        self.assertEqual(len(response.json()["warnings"]), 1)
        product = Product.objects.get(short_name="AUD")
        self.assertEqual(product.name_en, "Audit")
        self.assertEqual(product.name_ru, "Аудит")
        self.assertEqual(product.display_name, "Аудит продукта")
        self.assertEqual(product.consulting_type, "Горный")
        self.assertEqual(product.service_category, "Аудит")
        self.assertEqual(product.service_code, "A")
        self.assertEqual(product.service_subtype, "Аудит проектных решений")
        self.assertIsNotNone(product.consulting_type_ref_id)
        self.assertIsNotNone(product.service_category_ref_id)
        self.assertIsNotNone(product.service_subtype_ref_id)
        self.assertFalse(product.is_group_owner)
        self.assertEqual(list(product.owners.values_list("short_name", flat=True)), ["IMC Montan"])

    def test_policy_partial_renders_product_csv_download_button(self):
        response = self.client.get(reverse("policy_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Типовые продукты")
        self.assertContains(response, 'id="products-csv-download-btn"', html=False)

    def test_policy_partial_renders_expertise_direction_specialization_area(self):
        ExpertiseDirection.objects.create(
            short_name="ГЭ",
            name="Горная экспертиза",
            pricing_method="vpm",
            specialization_area="Специалисты по горным работам",
            position=1,
        )

        response = self.client.get(reverse("policy_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Направления экспертизы")
        self.assertContains(response, "Расчет стоимости услуг")
        self.assertContains(response, "Область специализации")
        self.assertContains(response, "Специалисты по горным работам")

    def test_expertise_direction_form_renders_specialization_area_suffix(self):
        response = self.client.get(reverse("expertise_dir_form_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Область специализации")
        self.assertContains(response, "Специалисты по")
        self.assertContains(response, 'name="specialization_area_suffix"', html=False)

    def test_expertise_direction_form_saves_specialization_area_with_locked_prefix(self):
        response = self.client.post(
            reverse("expertise_dir_form_create"),
            {
                "short_name": "ГЭ",
                "name": "Горная экспертиза",
                "pricing_method": "vpm",
                "specialization_area_suffix": "горным работам",
                "owner_ids": "__group__",
            },
        )

        self.assertEqual(response.status_code, 200)
        direction = ExpertiseDirection.objects.get(short_name="ГЭ")
        self.assertEqual(direction.specialization_area, "Специалисты по горным работам")
        self.assertContains(response, "Специалисты по горным работам")

    def test_expertise_direction_edit_form_prefills_specialization_area_suffix(self):
        direction = ExpertiseDirection.objects.create(
            short_name="ГЭ",
            name="Горная экспертиза",
            specialization_area="Специалисты по горным работам",
            position=1,
        )

        response = self.client.get(reverse("expertise_dir_form_edit", args=[direction.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Специалисты по")
        self.assertContains(response, 'value="горным работам"', html=False)

    def test_product_csv_download_exports_current_table_columns(self):
        product = Product.objects.create(
            short_name="AUD",
            name_en="Audit",
            name_ru="Аудит",
            display_name="Аудит продукта",
            consulting_type="Горный",
            service_category="Аудит",
            service_code="A",
            service_subtype="Аудит проектных решений",
            position=1,
        )
        product.owners.set([self.owner])

        response = self.client.get(reverse("product_csv_download"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("typical_products.csv", response["Content-Disposition"])
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(
            rows[0],
            [
                "Краткое имя",
                "Наименование на английском языке",
                "Наименование на русском языке",
                "Отображаемое в системе имя",
                "Вид консалтинга",
                "Тип услуг",
                "Код",
                "Подтип услуги",
                "Владелец",
            ],
        )
        self.assertEqual(
            rows[1],
            [
                "AUD",
                "Audit",
                "Аудит",
                "Аудит продукта",
                "Горный",
                "Аудит",
                "A",
                "Аудит проектных решений",
                "IMC Montan",
            ],
        )

    def test_product_csv_download_respects_product_filter(self):
        tax_product = Product.objects.create(
            short_name="TAX",
            name_en="Tax",
            name_ru="Налоги",
            display_name="Налоговый продукт",
            consulting_type="Горный",
            service_category="Инжиниринг",
            service_code="I",
            service_subtype="По международным стандартам",
            position=1,
        )
        Product.objects.create(
            short_name="AUD",
            name_en="Audit",
            name_ru="Аудит",
            display_name="Аудит продукта",
            consulting_type="Горный",
            service_category="Аудит",
            service_code="A",
            service_subtype="Аудит проектных решений",
            position=2,
        )

        response = self.client.get(
            reverse("product_csv_download"),
            {"product": [tax_product.pk]},
        )

        self.assertEqual(response.status_code, 200)
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][0], "TAX")


class ProductFormTests(TestCase):
    def setUp(self):
        self.consulting_type = ConsultingDirectionType.objects.create(
            name="Горный ProductForm",
            position=1,
            direction=ConsultingDirection.objects.create(position=1),
        )
        self.service_type = ConsultingServiceType.objects.create(
            direction=self.consulting_type.direction,
            consulting_type=self.consulting_type,
            name="Аудит ProductForm",
            code="A",
            position=1,
        )
        self.service_subtype = ConsultingServiceSubtype.objects.create(
            direction=self.consulting_type.direction,
            service_type=self.service_type,
            name="Аудит проектных решений ProductForm",
            position=1,
        )

    def test_init_ignores_non_numeric_dependent_catalog_ids(self):
        data = QueryDict("", mutable=True)
        data.update(
            {
                "short_name": "AUD",
                "name_en": "Audit",
                "display_name": "Audit",
                "name_ru": "Аудит",
                "consulting_type_ref": "oops",
                "service_category_ref": "nan",
                "service_subtype_ref": str(self.service_subtype.pk),
            }
        )
        form = ProductForm(data=data)

        self.assertEqual(list(form.fields["service_category_ref"].queryset), [])
        self.assertEqual(list(form.fields["service_subtype_ref"].queryset), [])


class PolicyMasterFilterTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="policy-master-filter-admin",
            password="secret123",
            is_staff=True,
        )
        self.client.force_login(self.user)
        direction = ConsultingDirection.objects.create(position=1)
        self.consulting_type = ConsultingDirectionType.objects.create(
            direction=direction,
            name="Горный Master",
            position=1,
        )
        self.service_type = ConsultingServiceType.objects.create(
            direction=direction,
            consulting_type=self.consulting_type,
            name="Аудит Master",
            code="AM",
            position=1,
        )
        self.service_subtype = ConsultingServiceSubtype.objects.create(
            direction=direction,
            service_type=self.service_type,
            name="Аудит проектных решений Master",
            position=1,
        )
        self.product = Product.objects.create(
            short_name="MF",
            name_en="Master filter product",
            display_name="Master filter product",
            name_ru="Продукт мастер-фильтра",
            consulting_type_ref=self.consulting_type,
            service_category_ref=self.service_type,
            service_subtype_ref=self.service_subtype,
            position=1,
        )
        self.other_product = Product.objects.create(
            short_name="OTHER-MF",
            name_en="Other product",
            display_name="Other product",
            name_ru="Другой продукт",
            consulting_type_ref=self.consulting_type,
            service_category_ref=self.service_type,
            service_subtype_ref=self.service_subtype,
            position=2,
        )
        self.section = TypicalSection.objects.create(
            product=self.product,
            code="MF-1",
            short_name="mf-1",
            short_name_ru="мф-1",
            name_en="Master section",
            name_ru="Раздел мастер-фильтра",
            accounting_type="Раздел",
            position=1,
        )
        self.other_section = TypicalSection.objects.create(
            product=self.other_product,
            code="OMF-1",
            short_name="omf-1",
            short_name_ru="омф-1",
            name_en="Other section",
            name_ru="Другой раздел",
            accounting_type="Раздел",
            position=1,
        )
        ServiceGoalReport.objects.create(
            product=self.product,
            service_goal="Цель",
            service_goal_genitive="Цели",
            report_title="Отчет",
            product_name="Название",
            position=1,
        )
        Tariff.objects.create(
            product=self.product,
            section=self.section,
            base_rate_vpm=Decimal("1.00"),
            service_hours=1,
            service_days_tkp=1,
            created_by=self.user,
            position=1,
        )

    def test_policy_partial_renders_master_filter_row_metadata(self):
        response = self.client.get(reverse("policy_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-target-name="product-select"', html=False)
        self.assertContains(response, 'name="product-select"', html=False)
        self.assertContains(response, 'data-policy-filter-row="1"', html=False)
        self.assertContains(response, f'data-product-id="{self.product.pk}"', html=False)
        self.assertContains(response, 'data-product-label="MF Master filter product"', html=False)
        self.assertContains(response, 'data-consulting-type="Горный Master"', html=False)
        self.assertContains(response, 'data-service-category="Аудит Master"', html=False)
        self.assertContains(response, 'data-service-subtype="Аудит проектных решений Master"', html=False)

    def test_product_create_prefills_catalog_fields_from_selected_product(self):
        response = self.client.get(reverse("product_form_create"), {"product": self.product.pk})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'<option value="{self.consulting_type.pk}" selected', html=False)
        self.assertContains(response, f'<option value="{self.service_type.pk}" selected', html=False)
        self.assertContains(response, f'<option value="{self.service_subtype.pk}" selected', html=False)

    def test_product_create_prefills_catalog_fields_from_direct_refs(self):
        response = self.client.get(
            reverse("product_form_create"),
            {
                "consulting_type_ref": self.consulting_type.pk,
                "service_category_ref": self.service_type.pk,
                "service_subtype_ref": self.service_subtype.pk,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'<option value="{self.consulting_type.pk}" selected', html=False)
        self.assertContains(response, f'<option value="{self.service_type.pk}" selected', html=False)
        self.assertContains(response, f'<option value="{self.service_subtype.pk}" selected', html=False)

    def test_create_forms_prefill_product_from_master_filter_param(self):
        url_names = [
            "section_form_create",
            "structure_form_create",
            "service_goal_report_form_create",
            "typical_service_composition_form_create",
            "typical_service_term_form_create",
            "tariff_form_create",
        ]

        for url_name in url_names:
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name), {"product": self.product.pk})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, f'<option value="{self.product.pk}" selected', html=False)

    def test_dependent_section_fields_are_limited_by_selected_product(self):
        structure_form = SectionStructureForm(initial={"product": self.product.pk})
        tariff_form = TariffForm(initial={"product": self.product.pk}, request_user=self.user)

        self.assertEqual(list(structure_form.fields["section"].queryset), [self.section])
        self.assertEqual(list(tariff_form.fields["section"].queryset), [self.section])

    def test_dependent_section_forms_reject_malformed_bound_ids_without_crashing(self):
        form_configs = [
            (
                "structure",
                SectionStructureForm,
                {"subsections": "Подраздел"},
                {},
            ),
            (
                "service_composition",
                TypicalServiceCompositionForm,
                {"service_composition": "Состав услуг", "service_composition_editor_state": ""},
                {},
            ),
            (
                "tariff",
                TariffForm,
                {"base_rate_vpm": "1.00", "service_hours": "1", "service_days_tkp": "1"},
                {"request_user": self.user},
            ),
        ]
        malformed_cases = [
            ({"product": "abc", "section": str(self.section.pk)}, "product"),
            ({"product": str(self.product.pk), "section": "abc"}, "section"),
        ]

        for form_name, form_class, base_data, form_kwargs in form_configs:
            for malformed_data, error_field in malformed_cases:
                with self.subTest(form_name=form_name, error_field=error_field):
                    form = form_class(data={**base_data, **malformed_data}, **form_kwargs)

                    self.assertFalse(form.is_valid())
                    self.assertIn(error_field, form.errors)


class ConsultingDirectionViewsTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="policy-consulting-admin",
            password="secret123",
            is_staff=True,
        )
        self.client.force_login(self.user)
        ConsultingDirection.objects.all().delete()

    def test_policy_partial_renders_consulting_direction_table(self):
        response = self.client.get(reverse("policy_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Направления консалтинга")
        self.assertContains(response, 'id="consulting-dir-actions"', html=False)
        self.assertContains(response, 'data-policy-actions-always-visible="1"', html=False)
        self.assertContains(response, 'id="consulting-dir-master"', html=False)

    def test_consulting_directions_edit_button_uses_sticky_footer(self):
        response = self.client.get(reverse("policy_consulting_directions_table"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="policy-table-editor"', html=False)
        self.assertContains(response, 'class="policy-table-footer"', html=False)
        self.assertContains(response, 'id="consulting-dir-actions"', html=False)
        self.assertContains(response, "Редактировать")
        self.assertRegex(
            response.content.decode(),
            r"</table>\s*</div>\s*<div class=\"policy-table-footer\">",
        )
        response = self.client.post(
            reverse("consulting_dir_form_create"),
            {
                "consulting_types_payload": json.dumps(
                    [{"id": "", "name": "Финансовый"}], ensure_ascii=False
                ),
                "service_types_payload": json.dumps(
                    [
                        {
                            "id": "",
                            "consulting_type": "Финансовый",
                            "name": "Due diligence",
                            "code": "D",
                        }
                    ],
                    ensure_ascii=False,
                ),
                "service_subtypes_payload": json.dumps(
                    [
                        {
                            "id": "",
                            "consulting_type": "Финансовый",
                            "service_type": "Due diligence",
                            "name": "Экспресс",
                        }
                    ],
                    ensure_ascii=False,
                ),
            },
        )

        self.assertEqual(response.status_code, 200)
        direction = ConsultingDirection.objects.get(
            consulting_types__name="Финансовый"
        )
        self.assertEqual(direction.service_types.get().code, "D")
        self.assertEqual(direction.service_subtypes.get().name, "Экспресс")

    def test_move_up_reorders_consulting_directions(self):
        first = ConsultingDirection.objects.create(position=1)
        second = ConsultingDirection.objects.create(position=2)

        response = self.client.post(reverse("consulting_dir_move_up", args=[second.pk]))

        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.position, 2)
        self.assertEqual(second.position, 1)


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
            consulting_type="Горный",
            service_category="Инжиниринг",
            service_subtype="По международным стандартам",
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
        self.assertContains(response, 'id="sections-csv-download-btn"', html=False)

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

    def test_create_section_auto_creates_system_dsc_first(self):
        response = self.client.post(
            reverse("section_form_create"),
            {
                "product": self.product.pk,
                "code": "SEC-AUTO",
                "short_name": "auto-en",
                "short_name_ru": "auto-ru",
                "name_en": "Auto EN",
                "name_ru": "Авто RU",
                "accounting_type": "Раздел",
            },
        )

        self.assertEqual(response.status_code, 200)
        sections = list(self.product.sections.order_by("position", "id"))
        self.assertEqual([section.code for section in sections], ["DSC", "SEC-AUTO"])
        dsc = sections[0]
        self.assertTrue(dsc.is_system)
        self.assertEqual(dsc.short_name, "Description")
        self.assertEqual(dsc.short_name_ru, "Описание")
        self.assertEqual(dsc.name_en, "Product description")
        self.assertEqual(dsc.name_ru, "Описание продукта")
        self.assertEqual(dsc.accounting_type, "Раздел")
        self.assertFalse(dsc.exclude_from_tkp_autofill)
        self.assertFalse(dsc.ranked_specialties.exists())

    def test_ensure_system_dsc_canonicalizes_existing_row(self):
        existing = TypicalSection.objects.create(
            product=self.product,
            code="dsc",
            short_name="manual",
            short_name_ru="ручной",
            name_en="Manual",
            name_ru="Ручной",
            accounting_type="Услуги",
            exclude_from_tkp_autofill=True,
            position=5,
        )
        TypicalSection.objects.create(
            product=self.product,
            code="SEC-BACKFILL",
            short_name="backfill-en",
            short_name_ru="backfill-ru",
            name_en="Backfill EN",
            name_ru="Backfill RU",
            accounting_type="Раздел",
            position=1,
        )

        dsc = ensure_system_dsc_section(self.product)

        self.assertEqual(dsc.pk, existing.pk)
        self.assertEqual(dsc.code, "DSC")
        self.assertTrue(dsc.is_system)
        self.assertEqual(dsc.short_name, "Description")
        self.assertFalse(dsc.exclude_from_tkp_autofill)
        self.assertEqual(
            list(self.product.sections.order_by("position", "id").values_list("code", flat=True)),
            ["DSC", "SEC-BACKFILL"],
        )

    def test_create_section_rejects_manual_dsc_code(self):
        response = self.client.post(
            reverse("section_form_create"),
            {
                "product": self.product.pk,
                "code": "DSC",
                "short_name": "manual",
                "short_name_ru": "manual",
                "name_en": "Manual",
                "name_ru": "Ручной",
                "accounting_type": "Раздел",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Раздел DSC является системным")
        self.assertFalse(TypicalSection.objects.filter(product=self.product, code="DSC").exists())

    def test_system_dsc_cannot_be_deleted_or_moved(self):
        dsc = ensure_system_dsc_section(self.product)
        regular = TypicalSection.objects.create(
            product=self.product,
            code="SEC-LOCK",
            short_name="lock-en",
            short_name_ru="lock-ru",
            name_en="Lock EN",
            name_ru="Блок RU",
            accounting_type="Раздел",
            position=2,
        )
        ensure_system_dsc_section(self.product)

        delete_response = self.client.post(reverse("section_delete", args=[dsc.pk]))
        move_response = self.client.post(reverse("section_move_down", args=[dsc.pk]))
        regular_move_response = self.client.post(reverse("section_move_up", args=[regular.pk]))

        self.assertEqual(delete_response.status_code, 400)
        self.assertEqual(move_response.status_code, 200)
        self.assertEqual(regular_move_response.status_code, 200)
        self.assertEqual(
            list(self.product.sections.order_by("position", "id").values_list("code", flat=True)),
            ["DSC", "SEC-LOCK"],
        )

    def test_section_form_renders_product_options_with_display_name(self):
        response = self.client.get(reverse("section_form_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<select name="product"', html=False)
        self.assertContains(response, "policy-product-select")
        self.assertContains(response, 'data-short-label="SEC"', html=False)
        self.assertContains(response, "SEC Sections")

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

    def test_section_csv_upload_skips_manual_dsc_and_updates_system_row(self):
        csv_file = SimpleUploadedFile(
            "sections.csv",
            (
                "Продукт;Код;Краткое имя EN;Краткое имя RU;Наименование EN;Наименование RU;Тип учета;Направление экспертизы\n"
                "SEC;DSC;manual;ручной;Manual;Ручной;Услуги;\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(reverse("section_csv_upload"), {"csv_file": csv_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 0)
        self.assertIn("раздел DSC является системным", response.json()["warnings"][0])
        dsc = TypicalSection.objects.get(product=self.product, code="DSC")
        self.assertTrue(dsc.is_system)
        self.assertEqual(dsc.short_name, "Description")
        self.assertEqual(dsc.position, 1)

    def test_section_csv_download_exports_current_table_columns(self):
        owner = GroupMember.objects.create(
            short_name="IMC",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
            position=1,
        )
        department = OrgUnit.objects.create(
            company=owner,
            level=1,
            department_name="Налоговый департамент",
            short_name="TAX-DEPT",
            unit_type="expertise",
            position=1,
        )
        expertise = ExpertiseDirection.objects.create(
            name="Налоги",
            short_name="TAX",
            position=1,
        )
        specialty = ExpertSpecialty.objects.create(
            expertise_direction=department,
            expertise_dir=expertise,
            specialty="Налоговый due diligence",
            position=1,
        )
        section = TypicalSection.objects.create(
            product=self.product,
            code="SEC-4",
            short_name="tax-dd",
            short_name_ru="нал-dd",
            name_en="Tax DD",
            name_ru="Налоговый ДД",
            accounting_type="Услуги",
            expertise_dir=expertise,
            expertise_direction=department,
            exclude_from_tkp_autofill=True,
            position=1,
        )
        TypicalSectionSpecialty.objects.create(section=section, specialty=specialty, rank=1)

        response = self.client.get(reverse("section_csv_download"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("typical_sections.csv", response["Content-Disposition"])
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(
            rows[0],
            [
                "Продукт",
                "Код",
                "Краткое имя EN",
                "Краткое имя RU",
                "Наименование раздела (услуги) EN",
                "Наименование раздела (услуги) RU",
                "Тип учета",
                "Исполнитель",
                "Экспертиза",
                "Подразделение",
                "ТКП",
            ],
        )
        self.assertEqual(
            next(row for row in rows[1:] if row[1] == "SEC-4"),
            [
                "SEC",
                "SEC-4",
                "tax-dd",
                "нал-dd",
                "Tax DD",
                "Налоговый ДД",
                "Услуги",
                "Налоговый due diligence",
                "TAX",
                "Налоговый департамент",
                "Да",
            ],
        )

    def test_section_csv_download_respects_product_filter(self):
        other_product = Product.objects.create(
            short_name="SEC2",
            name_en="Sections 2",
            display_name="Sections 2",
            name_ru="Разделы 2",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
            position=2,
        )
        TypicalSection.objects.create(
            product=self.product,
            code="SEC-A",
            short_name="section-a",
            short_name_ru="section-a-ru",
            name_en="Section A",
            name_ru="Раздел A",
            accounting_type="Раздел",
            position=1,
        )
        TypicalSection.objects.create(
            product=other_product,
            code="SEC-B",
            short_name="section-b",
            short_name_ru="section-b-ru",
            name_en="Section B",
            name_ru="Раздел B",
            accounting_type="Раздел",
            position=1,
        )

        response = self.client.get(
            reverse("section_csv_download"),
            {"product": [self.product.pk]},
        )

        self.assertEqual(response.status_code, 200)
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][0], "SEC")
        self.assertEqual(rows[1][1], "SEC-A")

    def test_section_csv_upload_accepts_current_table_export_columns(self):
        owner = GroupMember.objects.create(
            short_name="IMC",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
            position=1,
        )
        department = OrgUnit.objects.create(
            company=owner,
            level=1,
            department_name="Налоговый департамент",
            short_name="TAX-DEPT",
            unit_type="expertise",
            position=1,
        )
        expertise = ExpertiseDirection.objects.create(
            name="Налоги",
            short_name="TAX",
            position=1,
        )
        first_specialty = ExpertSpecialty.objects.create(
            expertise_direction=department,
            expertise_dir=expertise,
            specialty="Налоговый due diligence",
            position=1,
        )
        second_specialty = ExpertSpecialty.objects.create(
            expertise_direction=department,
            expertise_dir=expertise,
            specialty="Трансфертное ценообразование",
            position=2,
        )
        csv_file = SimpleUploadedFile(
            "sections.csv",
            (
                "Продукт;Код;Краткое имя EN;Краткое имя RU;"
                "Наименование раздела (услуги) EN;Наименование раздела (услуги) RU;"
                "Тип учета;Исполнитель;Экспертиза;Подразделение;ТКП\n"
                "SEC;SEC-5;tax-dd;нал-dd;Tax DD;Налоговый ДД;Услуги;"
                "Налоговый due diligence, Трансфертное ценообразование;TAX;Налоговый департамент;Да\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(reverse("section_csv_upload"), {"csv_file": csv_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 1)
        self.assertEqual(response.json()["warnings"], [])
        section = TypicalSection.objects.get(code="SEC-5")
        self.assertEqual(section.expertise_dir, expertise)
        self.assertEqual(section.expertise_direction, department)
        self.assertTrue(section.exclude_from_tkp_autofill)
        self.assertEqual(
            list(section.ranked_specialties.values_list("specialty", flat=True)),
            [first_specialty.pk, second_specialty.pk],
        )

    def test_section_csv_upload_updates_existing_section_by_product_and_code(self):
        section = TypicalSection.objects.create(
            product=self.product,
            code="SEC-UPD",
            short_name="old-en",
            short_name_ru="old-ru",
            name_en="Old EN",
            name_ru="Старый раздел",
            accounting_type="Раздел",
            exclude_from_tkp_autofill=False,
            position=1,
        )
        csv_file = SimpleUploadedFile(
            "sections.csv",
            (
                "Продукт;Код;Краткое имя EN;Краткое имя RU;"
                "Наименование раздела (услуги) EN;Наименование раздела (услуги) RU;"
                "Тип учета;Исполнитель;Экспертиза;Подразделение;ТКП\n"
                "SEC;SEC-UPD;new-en;new-ru;New EN;Новый раздел;Услуги;;;;Да\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(reverse("section_csv_upload"), {"csv_file": csv_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 0)
        self.assertEqual(response.json()["updated"], 1)
        section.refresh_from_db()
        self.assertEqual(section.short_name, "new-en")
        self.assertEqual(section.short_name_ru, "new-ru")
        self.assertEqual(section.name_en, "New EN")
        self.assertEqual(section.name_ru, "Новый раздел")
        self.assertEqual(section.accounting_type, "Услуги")
        self.assertTrue(section.exclude_from_tkp_autofill)

    def test_section_csv_upload_rolls_back_row_when_specialty_insert_fails(self):
        owner = GroupMember.objects.create(
            short_name="IMC",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
            position=1,
        )
        department = OrgUnit.objects.create(
            company=owner,
            level=1,
            department_name="Налоговый департамент",
            short_name="TAX-DEPT",
            unit_type="expertise",
            position=1,
        )
        expertise = ExpertiseDirection.objects.create(
            name="Налоги",
            short_name="TAX",
            position=1,
        )
        specialty = ExpertSpecialty.objects.create(
            expertise_direction=department,
            expertise_dir=expertise,
            specialty="Налоговый due diligence",
            position=1,
        )
        csv_file = SimpleUploadedFile(
            "sections.csv",
            (
                "Продукт;Код;Краткое имя EN;Краткое имя RU;"
                "Наименование раздела (услуги) EN;Наименование раздела (услуги) RU;"
                "Тип учета;Исполнитель;Экспертиза;Подразделение;ТКП\n"
                "SEC;SEC-6;tax-dd;нал-dd;Tax DD;Налоговый ДД;Услуги;"
                "Налоговый due diligence, Налоговый due diligence;TAX;Налоговый департамент;Да\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(reverse("section_csv_upload"), {"csv_file": csv_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 0)
        self.assertEqual(len(response.json()["warnings"]), 1)
        self.assertIn("ошибка сохранения", response.json()["warnings"][0])
        self.assertFalse(TypicalSection.objects.filter(code="SEC-6").exists())
        self.assertFalse(TypicalSectionSpecialty.objects.filter(specialty=specialty).exists())


class SectionStructureViewsTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="policy-structures-admin",
            password="secret123",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.product = Product.objects.create(
            short_name="STR",
            name_en="Structure",
            display_name="Structure System",
            name_ru="Структура",
            consulting_type="Горный",
            service_category="Инжиниринг",
            service_subtype="По международным стандартам",
            position=1,
        )
        self.section = TypicalSection.objects.create(
            product=self.product,
            code="STR-1",
            short_name="section-en",
            short_name_ru="section-ru",
            name_en="Section EN",
            name_ru="Раздел RU",
            accounting_type="Раздел",
            position=1,
        )

    def test_policy_partial_renders_structure_csv_buttons(self):
        SectionStructure.objects.create(
            product=self.product,
            section=self.section,
            subsections="Подраздел 1\nПодраздел 2",
            position=1,
        )

        response = self.client.get(reverse("policy_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Типовая структура раздела (состава услуг)")
        self.assertContains(response, ">Код<", html=False)
        self.assertContains(response, "STR-1")
        self.assertContains(response, "Подраздел 1")
        self.assertContains(response, 'id="structures-csv-download-btn"', html=False)
        self.assertContains(response, 'id="structures-csv-upload-btn"', html=False)

    def test_structure_form_renders_product_options_with_display_name(self):
        response = self.client.get(reverse("structure_form_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<select name="product"', html=False)
        self.assertContains(response, "policy-product-select")
        self.assertContains(response, 'data-short-label="STR"', html=False)
        self.assertContains(response, "STR Structure System")
        self.assertContains(response, 'name="section_code"', html=False)
        self.assertContains(response, "readonly-field", html=False)
        self.assertContains(response, 'tabindex="-1"', html=False)
        self.assertContains(response, "policy-section-select")
        self.assertContains(response, '"label": "STR-1 Раздел RU"', html=False)
        self.assertContains(response, '"displayLabel": "Раздел RU"', html=False)

    def test_structure_csv_download_exports_current_table_columns(self):
        SectionStructure.objects.create(
            product=self.product,
            section=self.section,
            subsections="Подраздел 1\nПодраздел 2",
            position=1,
        )

        response = self.client.get(reverse("structure_csv_download"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("section_structures.csv", response["Content-Disposition"])
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(rows[0], ["Продукт", "Код", "Раздел (услуга)", "Подразделы"])
        self.assertEqual(rows[1], ["STR", "STR-1", "Раздел RU", "Подраздел 1\nПодраздел 2"])

    def test_structure_csv_download_respects_product_filter(self):
        other_product = Product.objects.create(
            short_name="STR2",
            name_en="Structure 2",
            display_name="Structure 2",
            name_ru="Структура 2",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
            position=2,
        )
        other_section = TypicalSection.objects.create(
            product=other_product,
            code="STR-2",
            short_name="other-en",
            short_name_ru="other-ru",
            name_en="Other EN",
            name_ru="Другой раздел",
            accounting_type="Раздел",
            position=1,
        )
        SectionStructure.objects.create(
            product=self.product,
            section=self.section,
            subsections="Подраздел 1",
            position=1,
        )
        SectionStructure.objects.create(
            product=other_product,
            section=other_section,
            subsections="Подраздел A",
            position=2,
        )

        response = self.client.get(
            reverse("structure_csv_download"),
            {"product": [self.product.pk]},
        )

        self.assertEqual(response.status_code, 200)
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][0], "STR")

    def test_structure_csv_upload_creates_rows(self):
        csv_file = SimpleUploadedFile(
            "section_structures.csv",
            (
                "Продукт;Код;Раздел (услуга);Подразделы\n"
                "STR;STR-1;Раздел RU;Подраздел 1\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(reverse("structure_csv_upload"), {"csv_file": csv_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 1)
        self.assertEqual(response.json()["warnings"], [])
        self.assertEqual(
            response.json()["policyUpdate"],
            {"tables": ["section-structures"], "refreshFilters": False},
        )
        item = SectionStructure.objects.get()
        self.assertEqual(item.product, self.product)
        self.assertEqual(item.section, self.section)
        self.assertEqual(item.subsections, "Подраздел 1")
        self.assertEqual(item.position, 1)

    def test_structure_csv_upload_accepts_legacy_rows_without_code(self):
        csv_file = SimpleUploadedFile(
            "section_structures.csv",
            (
                "Продукт;Раздел (услуга);Подразделы\n"
                "STR;Раздел RU;Подраздел 1\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(reverse("structure_csv_upload"), {"csv_file": csv_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 1)
        self.assertEqual(response.json()["warnings"], [])
        self.assertEqual(SectionStructure.objects.get().section, self.section)

    def _assert_structure_fragment_trigger(self, response, extra=None):
        expected = {
            "tables": ["section-structures"],
            "refreshFilters": False,
        }
        if extra:
            expected.update(extra)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")
        self.assertEqual(response["HX-Reswap"], "none")
        self.assertEqual(
            json.loads(response["HX-Trigger"]),
            {"policy-updated": expected},
        )
        self.assertNotContains(response, 'id="policy-pane"', html=False)
        self.assertNotContains(response, "Типовая структура отчета")

    def test_htmx_create_and_edit_return_small_fragment_event(self):
        create_response = self.client.post(
            reverse("structure_form_create"),
            {
                "product": self.product.pk,
                "section": self.section.pk,
                "subsections": "Первый подраздел",
            },
            HTTP_HX_REQUEST="true",
        )

        self._assert_structure_fragment_trigger(create_response)
        structure = SectionStructure.objects.get()
        self.assertEqual(structure.subsections, "Первый подраздел")

        edit_response = self.client.post(
            reverse("structure_form_edit", args=[structure.pk]),
            {
                "product": self.product.pk,
                "section": self.section.pk,
                "subsections": "Измененный подраздел",
            },
            HTTP_HX_REQUEST="true",
        )

        self._assert_structure_fragment_trigger(edit_response)
        structure.refresh_from_db()
        self.assertEqual(structure.subsections, "Измененный подраздел")

    def test_htmx_delete_and_move_return_small_fragment_event(self):
        first = SectionStructure.objects.create(
            product=self.product,
            section=self.section,
            subsections="Первый",
            position=1,
        )
        second = SectionStructure.objects.create(
            product=self.product,
            section=self.section,
            subsections="Второй",
            position=2,
        )
        third = SectionStructure.objects.create(
            product=self.product,
            section=self.section,
            subsections="Третий",
            position=3,
        )

        move_up_response = self.client.post(
            reverse("structure_move_up", args=[second.pk]),
            HTTP_HX_REQUEST="true",
        )
        self._assert_structure_fragment_trigger(
            move_up_response,
            {"reorderedTable": "section-structures"},
        )
        second.refresh_from_db()
        self.assertEqual(second.position, 1)

        move_down_response = self.client.post(
            reverse("structure_move_down", args=[second.pk]),
            HTTP_HX_REQUEST="true",
        )
        self._assert_structure_fragment_trigger(
            move_down_response,
            {"reorderedTable": "section-structures"},
        )
        second.refresh_from_db()
        self.assertEqual(second.position, 2)

        delete_response = self.client.post(
            reverse("structure_delete", args=[third.pk]),
            HTTP_HX_REQUEST="true",
        )
        self._assert_structure_fragment_trigger(delete_response)
        self.assertFalse(SectionStructure.objects.filter(pk=third.pk).exists())
        self.assertTrue(SectionStructure.objects.filter(pk=first.pk).exists())

    def test_invalid_htmx_form_stays_in_modal_with_errors(self):
        response = self.client.post(
            reverse("structure_form_create"),
            {
                "product": self.product.pk,
                "section": "",
                "subsections": "Подраздел",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'hx-target="#policy-modal .modal-content"', html=False)
        self.assertContains(response, 'hx-swap="innerHTML"', html=False)
        self.assertContains(response, "Проверьте введённые данные")
        self.assertContains(response, 'class="invalid-feedback d-block"', html=False)
        self.assertContains(response, "This field is required.")
        self.assertNotIn("HX-Trigger", response)
        self.assertFalse(SectionStructure.objects.exists())

    def test_non_htmx_create_keeps_legacy_full_partial_response(self):
        response = self.client.post(
            reverse("structure_form_create"),
            {
                "product": self.product.pk,
                "section": self.section.pk,
                "subsections": "Legacy подраздел",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Trigger"], "policy-updated")
        self.assertContains(response, 'id="policy-pane"', html=False)
        self.assertContains(response, "Типовая структура отчета")

    def test_delete_last_item_clamps_fragment_page(self):
        structures = SectionStructure.objects.bulk_create(
            [
                SectionStructure(
                    product=self.product,
                    section=self.section,
                    subsections=f"Подраздел {index}",
                    position=index,
                )
                for index in range(1, 52)
            ]
        )
        endpoint = reverse("policy_section_structures_table")
        page_three = self.client.get(endpoint, {"page": 3})
        self.assertEqual(page_three.context["page_obj"].number, 3)
        self.assertEqual(list(page_three.context["structures"]), [structures[-1]])

        delete_response = self.client.post(
            reverse("structure_delete", args=[structures[-1].pk]),
            HTTP_HX_REQUEST="true",
        )
        self._assert_structure_fragment_trigger(delete_response)

        clamped = self.client.get(endpoint, {"page": 3})
        self.assertEqual(clamped.context["paginator"].count, 50)
        self.assertEqual(clamped.context["page_obj"].number, 2)
        self.assertContains(clamped, "26–50 из 50")

    def test_structure_csv_upload_response_never_contains_full_policy(self):
        csv_file = SimpleUploadedFile(
            "section_structures.csv",
            (
                "Продукт;Код;Раздел (услуга);Подразделы\n"
                "STR;STR-1;Раздел RU;Импортированный подраздел\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(reverse("structure_csv_upload"), {"csv_file": csv_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 1)
        self.assertNotContains(response, 'id="policy-pane"', html=False)
        self.assertNotIn("HX-Trigger", response)

    def test_structure_batch_js_uses_fragment_scoped_hx_requests(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "core"
            / "static"
            / "core"
            / "js"
            / "policy-panels.js"
        ).read_text()

        self.assertEqual(
            source.count("document.body.addEventListener('policy-updated'"),
            1,
        )
        self.assertIn("headers['HX-Request'] = 'true'", source)
        self.assertIn("fragmentScopedPolicy ? '#' + managedWrapper.id", source)
        self.assertIn("handlePolicyUpdated(data.policyUpdate)", source)
        self.assertIn(
            "row.dataset.moveUpUrl || row.dataset.moveDownUrl || isPolicyInlineNewRow(row)",
            source,
        )
        self.assertIn("enqueuePolicyReorderPersist", source)
        self.assertIn("skipSourceRefresh", source)
        self.assertIn("skipTables", source)
        self.assertIn(
            "'input.form-check-input[name=\"' + CSS.escape(name) + '\"]:checked:not(:disabled)'",
            source,
        )
        self.assertNotIn(
            "return !!row.querySelector('input.form-check-input:checked:not(:disabled)');",
            source,
        )
        self.assertNotIn("htmx.ajax('GET', '/policy/policy/partial/'", source)


class ReportStructureViewsTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="policy-report-structures-admin",
            password="secret123",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.product = Product.objects.create(
            short_name="REP",
            name_en="Report",
            display_name="Report Product",
            name_ru="Отчет",
            consulting_type="Горный",
            service_category="Инжиниринг",
            service_subtype="По международным стандартам",
            position=1,
        )

    def _create_report_structure(self, level, code, name, position):
        return ReportStructure.objects.create(
            product=self.product,
            level=level,
            code=code,
            name=name,
            position=position,
        )

    def test_policy_partial_renders_report_structure_table_and_actions(self):
        self._create_report_structure(0, "RPT", "Итоговый отчет", 1)
        self._create_report_structure(1, "SEC", "Раздел", 2)
        self._create_report_structure(2, "SUB", "Подраздел", 3)

        response = self.client.get(reverse("policy_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Типовая структура отчета")
        self.assertContains(response, 'id="report-structures-master"', html=False)
        self.assertContains(response, 'name="report-structure-select"', html=False)
        self.assertContains(response, 'id="report-structures-actions"', html=False)
        self.assertContains(response, 'id="report-structures-csv-download-btn"', html=False)
        self.assertContains(response, 'id="report-structures-csv-upload-btn"', html=False)
        self.assertContains(response, "Итоговый отчет")
        self.assertContains(response, "1.1")

    def test_report_structure_form_and_level_validation(self):
        response = self.client.get(reverse("report_structure_form_create"), {"product": self.product.pk})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<select name="product"', html=False)
        self.assertContains(response, "policy-product-select")
        self.assertContains(response, 'name="level"', html=False)
        self.assertContains(response, 'name="number"', html=False)
        self.assertContains(response, "readonly-field", html=False)
        self.assertContains(response, "var itemsByProduct", html=False)

        form = ReportStructureForm(data={
            "product": self.product.pk,
            "level": 10,
            "code": "BAD",
            "name": "Недопустимый уровень",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("level", form.errors)

    def test_create_and_edit_report_structure_rows(self):
        response = self.client.post(
            reverse("report_structure_form_create"),
            {
                "product": self.product.pk,
                "level": 0,
                "code": "RPT",
                "name": "Итоговый отчет",
            },
        )

        self.assertEqual(response.status_code, 200)
        item = ReportStructure.objects.get()
        self.assertEqual(item.position, 1)
        self.assertEqual(item.level, 0)

        response = self.client.post(
            reverse("report_structure_form_edit", args=[item.pk]),
            {
                "product": self.product.pk,
                "level": 1,
                "code": "SEC",
                "name": "Раздел отчета",
            },
        )

        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.level, 1)
        self.assertEqual(item.code, "SEC")
        self.assertEqual(item.name, "Раздел отчета")

    def test_report_structure_numbering_resets_after_level_zero(self):
        self._create_report_structure(0, "RPT1", "Первый отчет", 1)
        self._create_report_structure(1, "SEC1", "Первый раздел", 2)
        self._create_report_structure(2, "SUB1", "Первый подраздел", 3)
        self._create_report_structure(1, "SEC2", "Второй раздел", 4)
        self._create_report_structure(0, "RPT2", "Второй отчет", 5)
        self._create_report_structure(1, "SEC3", "Раздел второго отчета", 6)

        response = self.client.get(reverse("report_structure_csv_download"))

        self.assertEqual(response.status_code, 200)
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(rows[0], [
            "Продукт",
            "Уровень",
            "Номер",
            "Код",
            "Наименование отчета, раздела (подраздела)",
        ])
        self.assertEqual([row[2] for row in rows[1:]], ["0", "1", "1.1", "2", "0", "1"])

    def test_report_structure_csv_upload_and_download_filter(self):
        other_product = Product.objects.create(
            short_name="REP2",
            name_en="Report 2",
            display_name="Report Product 2",
            name_ru="Отчет 2",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
            position=2,
        )
        ReportStructure.objects.create(
            product=other_product,
            level=0,
            code="OTHER",
            name="Другой отчет",
            position=1,
        )
        csv_file = SimpleUploadedFile(
            "report_structures.csv",
            (
                "Продукт;Уровень;Номер;Код;Наименование отчета, раздела (подраздела)\n"
                "REP;0;0;RPT;Итоговый отчет\n"
                "REP;1;1;SEC;Раздел отчета\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(reverse("report_structure_csv_upload"), {"csv_file": csv_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 2)
        self.assertEqual(response.json()["warnings"], [])
        self.assertEqual(ReportStructure.objects.filter(product=self.product).count(), 2)

        response = self.client.get(
            reverse("report_structure_csv_download"),
            {"product": [self.product.pk]},
        )

        self.assertEqual(response.status_code, 200)
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(len(rows), 3)
        self.assertEqual({row[0] for row in rows[1:]}, {"REP"})

    def test_report_structure_move_down_reorders_within_product(self):
        first = self._create_report_structure(0, "RPT", "Отчет", 1)
        second = self._create_report_structure(1, "SEC", "Раздел", 2)
        other_product = Product.objects.create(
            short_name="REP2",
            name_en="Report 2",
            display_name="Report Product 2",
            name_ru="Отчет 2",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
            position=2,
        )
        other = ReportStructure.objects.create(
            product=other_product,
            level=0,
            code="OTHER",
            name="Другой отчет",
            position=1,
        )

        response = self.client.post(reverse("report_structure_move_down", args=[first.pk]))

        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(first.position, 2)
        self.assertEqual(second.position, 1)
        self.assertEqual(other.position, 1)


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
            consulting_type="Горный",
            service_category="Инжиниринг",
            service_subtype="По международным стандартам",
            position=1,
        )

    def test_policy_partial_renders_service_goal_reports_table(self):
        ServiceGoalReport.objects.create(
            product=self.product,
            service_goal="Подготовка заключения",
            service_goal_genitive="Подготовки заключения",
            report_title="Итоговый отчет",
            product_name="Налоговый обзор",
            position=1,
        )

        response = self.client.get(reverse("policy_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Цели услуг и названия отчетов")
        self.assertContains(response, "Титул отчета/ТКП")
        self.assertContains(response, "Название продукта")
        self.assertContains(response, "Подготовка заключения")
        self.assertContains(response, "Подготовки заключения")
        self.assertContains(response, "Налоговый обзор")
        self.assertContains(response, 'id="service-goal-reports-actions"', html=False)
        self.assertContains(response, 'id="service-goal-reports-csv-download-btn"', html=False)
        self.assertContains(response, 'id="service-goal-reports-csv-upload-btn"', html=False)

    def test_create_service_goal_report_saves_row(self):
        response = self.client.post(
            reverse("service_goal_report_form_create"),
            {
                "product": self.product.pk,
                "service_goal": "Подготовка документов",
                "service_goal_genitive": "Подготовки документов",
                "report_title": "Отчет по документам",
                "product_name": "Документарная проверка",
            },
        )

        self.assertEqual(response.status_code, 200)
        item = ServiceGoalReport.objects.get()
        self.assertEqual(item.product, self.product)
        self.assertEqual(item.service_goal, "Подготовка документов")
        self.assertEqual(item.service_goal_genitive, "Подготовки документов")
        self.assertEqual(item.report_title, "Отчет по документам")
        self.assertEqual(item.product_name, "Документарная проверка")
        self.assertEqual(item.position, 1)

    def test_service_goal_report_form_renders_product_picker_with_display_name(self):
        response = self.client.get(reverse("service_goal_report_form_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<select name="product"', html=False)
        self.assertContains(response, "policy-product-select")
        self.assertContains(response, 'data-short-label="TAX"', html=False)
        self.assertContains(response, "TAX Tax")
        self.assertContains(response, "Титул отчета/ТКП")
        self.assertContains(response, "Название продукта")

        form = ServiceGoalReportForm()
        labels = [label for _, label in form.fields["product"].choices]
        self.assertIn("TAX Tax", labels)

    def test_service_goal_report_csv_download_exports_current_table_columns(self):
        ServiceGoalReport.objects.create(
            product=self.product,
            service_goal="Подготовка заключения",
            service_goal_genitive="Подготовки заключения",
            report_title="Итоговый отчет",
            product_name="Налоговый обзор",
            position=1,
        )

        response = self.client.get(reverse("service_goal_report_csv_download"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("service_goal_reports.csv", response["Content-Disposition"])
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(
            rows[0],
            [
                "Продукт",
                "Цели оказания услуг",
                "Цели оказания услуг в родительном падеже",
                "Титул отчета/ТКП",
                "Название продукта",
            ],
        )
        self.assertEqual(
            rows[1],
            [
                "TAX",
                "Подготовка заключения",
                "Подготовки заключения",
                "Итоговый отчет",
                "Налоговый обзор",
            ],
        )

    def test_service_goal_report_csv_download_respects_product_filter(self):
        other_product = Product.objects.create(
            short_name="AUD",
            name_en="Audit",
            display_name="Audit",
            name_ru="Аудит",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
            position=2,
        )
        ServiceGoalReport.objects.create(
            product=self.product,
            service_goal="Цель TAX",
            service_goal_genitive="Цели TAX",
            report_title="Отчет TAX",
            product_name="Продукт TAX",
            position=1,
        )
        ServiceGoalReport.objects.create(
            product=other_product,
            service_goal="Цель AUD",
            service_goal_genitive="Цели AUD",
            report_title="Отчет AUD",
            product_name="Продукт AUD",
            position=2,
        )

        response = self.client.get(
            reverse("service_goal_report_csv_download"),
            {"product": [self.product.pk]},
        )

        self.assertEqual(response.status_code, 200)
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][0], "TAX")

    def test_service_goal_report_csv_upload_creates_rows(self):
        csv_file = SimpleUploadedFile(
            "service_goal_reports.csv",
            (
                "Продукт;Цели оказания услуг;Цели оказания услуг в родительном падеже;Титул отчета/ТКП;Название продукта\n"
                "TAX;Подготовка документов;Подготовки документов;Отчет по документам;Документарная проверка\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(reverse("service_goal_report_csv_upload"), {"csv_file": csv_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 1)
        self.assertEqual(response.json()["warnings"], [])
        item = ServiceGoalReport.objects.get()
        self.assertEqual(item.product, self.product)
        self.assertEqual(item.service_goal, "Подготовка документов")
        self.assertEqual(item.service_goal_genitive, "Подготовки документов")
        self.assertEqual(item.report_title, "Отчет по документам")
        self.assertEqual(item.product_name, "Документарная проверка")
        self.assertEqual(item.position, 1)

    def test_service_goal_report_csv_upload_updates_existing_product_row(self):
        item = ServiceGoalReport.objects.create(
            product=self.product,
            service_goal="Старая цель",
            service_goal_genitive="Старой цели",
            report_title="Старый титул",
            product_name="Старый продукт",
            position=1,
        )
        csv_file = SimpleUploadedFile(
            "service_goal_reports.csv",
            (
                "Продукт;Цели оказания услуг;Цели оказания услуг в родительном падеже;Титул отчета/ТКП;Название продукта\n"
                "TAX;Новая цель;Новой цели;Новый титул;Новый продукт\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(reverse("service_goal_report_csv_upload"), {"csv_file": csv_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 0)
        self.assertEqual(response.json()["updated"], 1)
        self.assertEqual(ServiceGoalReport.objects.count(), 1)
        item.refresh_from_db()
        self.assertEqual(item.service_goal, "Новая цель")
        self.assertEqual(item.service_goal_genitive, "Новой цели")
        self.assertEqual(item.report_title, "Новый титул")
        self.assertEqual(item.product_name, "Новый продукт")

    def test_move_up_reorders_globally_across_table(self):
        other_product = Product.objects.create(
            short_name="AUD",
            name_en="Audit",
            display_name="Audit",
            name_ru="Аудит",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
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
            consulting_type="Горный",
            service_category="Инжиниринг",
            service_subtype="По международным стандартам",
            position=1,
        )
        self.other_product = Product.objects.create(
            short_name="AUD2",
            name_en="Audit 2",
            display_name="Audit 2",
            name_ru="Аудит 2",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
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

    def _docx_upload_file(self, sections, include_code=True):
        document = Document()
        for section in sections:
            document.add_heading(section["product"], level=1)
            headers = ["ID", "Продукт", "Код", "Раздел (услуга)", "Состав услуг"] if include_code else [
                "ID",
                "Продукт",
                "Раздел (услуга)",
                "Состав услуг",
            ]
            table = document.add_table(rows=1, cols=len(headers))
            for index, header in enumerate(headers):
                table.rows[0].cells[index].text = header
            for row in section["rows"]:
                cells = table.add_row().cells
                cells[0].text = str(row.get("id", ""))
                cells[1].text = row.get("product", section["product"])
                if include_code:
                    cells[2].text = row.get("section_code", "")
                    cells[3].text = row.get("section", "")
                    cells[4].text = row.get("service_composition", "")
                else:
                    cells[2].text = row.get("section", "")
                    cells[3].text = row.get("service_composition", "")
        buffer = io.BytesIO()
        document.save(buffer)
        return SimpleUploadedFile(
            "typical_service_compositions.docx",
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
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
        self.assertContains(response, "Типовой состав услуг в ТКП")
        self.assertContains(response, ">Код<", html=False)
        self.assertContains(response, "S1")
        self.assertContains(response, "Раздел RU")
        self.assertContains(response, "<p>Подготовка,<br>анализ,<br>выпуск отчета</p>", html=False)
        self.assertContains(response, 'id="typical-service-compositions-wrap-toggle"', html=False)
        self.assertContains(response, 'id="typical-service-compositions-table"', html=False)
        self.assertContains(response, 'class="policy-service-composition-cell"', html=False)
        self.assertContains(
            response,
            'class="policy-service-composition-content policy-service-composition-content--rich ql-editor"',
            html=False,
        )
        self.assertContains(response, 'id="typical-service-compositions-csv-download-btn"', html=False)
        self.assertContains(response, 'id="typical-service-compositions-csv-upload-btn"', html=False)
        self.assertContains(response, 'id="typical-service-compositions-docx-download-btn"', html=False)
        self.assertContains(response, 'id="typical-service-compositions-docx-upload-btn"', html=False)
        self.assertNotContains(response, 'id="typical-service-compositions-xlsx-download-btn"', html=False)
        self.assertNotContains(response, 'id="typical-service-compositions-xlsx-upload-btn"', html=False)

    def test_policy_partial_renders_typical_service_composition_rich_html(self):
        editor_state = {
            "html": (
                '<p class="ql-align-justify"><strong>Подготовка</strong></p>'
                '<ol><li data-list="ordered">Этап 1</li>'
                '<li class="ql-indent-1" data-list="ordered">Подэтап 1.1</li></ol>'
                '<ul><li data-list="bullet">Маркер</li>'
                '<li data-list="dash"><span class="ql-ui" contenteditable="false"></span>Дефис</li></ul>'
            ),
            "plain_text": "Подготовка\nЭтап 1\nПодэтап 1.1\nМаркер\nДефис",
        }
        TypicalServiceComposition.objects.create(
            product=self.product,
            section=self.section,
            service_composition=editor_state["plain_text"],
            service_composition_editor_state=editor_state,
            position=1,
        )

        response = self.client.get(reverse("policy_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<p class="ql-align-justify"><strong>Подготовка</strong></p>',
            html=False,
        )
        self.assertContains(
            response,
            '<li data-list="ordered"><span class="ql-ui"></span>Этап 1</li>',
            html=False,
        )
        self.assertContains(
            response,
            '<li class="ql-indent-1" data-list="ordered"><span class="ql-ui"></span>Подэтап 1.1</li>',
            html=False,
        )
        self.assertContains(
            response,
            '<li data-list="bullet"><span class="ql-ui"></span>Маркер</li>',
            html=False,
        )
        self.assertContains(
            response,
            '<li data-list="dash"><span class="ql-ui"></span>Дефис</li>',
            html=False,
        )
        self.assertNotContains(response, 'contenteditable="false"', html=False)

    def test_policy_partial_renders_typical_service_composition_plain_text_fallback(self):
        TypicalServiceComposition.objects.create(
            product=self.product,
            section=self.section,
            service_composition="Первый блок\nстрока\n\nВторой блок",
            service_composition_editor_state={},
            position=1,
        )

        response = self.client.get(reverse("policy_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "<p>Первый блок<br>строка</p><p>Второй блок</p>",
            html=False,
        )

    def test_policy_partial_sanitizes_typical_service_composition_html(self):
        editor_state = {
            "html": (
                '<p onclick="alert(1)">'
                '<script>alert(1)</script>'
                '<span class="ql-font-calibri bad-class" '
                'style="color: #ff0000; background-image: url(javascript:alert(1)); background-color: rgb(1, 2, 3)">'
                'Безопасно'
                '</span>'
                '</p>'
            ),
            "plain_text": "Безопасно",
        }
        TypicalServiceComposition.objects.create(
            product=self.product,
            section=self.section,
            service_composition=editor_state["plain_text"],
            service_composition_editor_state=editor_state,
            position=1,
        )

        response = self.client.get(reverse("policy_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<span class="ql-font-calibri" style="color: #ff0000; background-color: rgb(1, 2, 3)">Безопасно</span>',
            html=False,
        )
        self.assertNotContains(response, "<script", html=False)
        self.assertNotContains(response, "alert(1)", html=False)
        self.assertNotContains(response, "onclick", html=False)
        self.assertNotContains(response, "bad-class", html=False)
        self.assertNotContains(response, "background-image", html=False)
        self.assertNotContains(response, "javascript:", html=False)

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

    def test_create_typical_service_composition_preserves_custom_list_markers(self):
        editor_state = {
            "html": (
                '<ol><li data-list="dash">Этап с дефисом</li>'
                '<li data-list="check">Этап с галочкой</li></ol>'
            ),
            "plain_text": "Этап с дефисом\nЭтап с галочкой",
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
        self.assertEqual(item.service_composition, "Этап с дефисом\nЭтап с галочкой")
        self.assertEqual(item.service_composition_editor_state, editor_state)

    def test_typical_service_composition_form_renders_product_options_with_display_name(self):
        response = self.client.get(reverse("typical_service_composition_form_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<select name="product"', html=False)
        self.assertContains(response, "policy-product-select")
        self.assertContains(response, 'data-short-label="TAX2"', html=False)
        self.assertContains(response, "TAX2 Tax 2")
        self.assertContains(response, 'name="section_code"', html=False)
        self.assertContains(response, "readonly-field", html=False)
        self.assertContains(response, 'tabindex="-1"', html=False)
        self.assertContains(response, "policy-section-select")
        self.assertContains(response, '"label": "S1 Раздел RU"', html=False)
        self.assertContains(response, '"displayLabel": "Раздел RU"', html=False)

    def test_typical_service_composition_csv_download_exports_current_table_columns(self):
        TypicalServiceComposition.objects.create(
            product=self.product,
            section=self.section,
            service_composition="Подготовка\nАнализ\nВыпуск отчета",
            position=1,
        )

        response = self.client.get(reverse("typical_service_composition_csv_download"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("typical_service_compositions.csv", response["Content-Disposition"])
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(rows[0], ["Продукт", "Код", "Раздел (услуга)", "Состав услуг"])
        self.assertEqual(rows[1], ["TAX2", "S1", "Раздел RU", "Подготовка\nАнализ\nВыпуск отчета"])

    def test_typical_service_composition_csv_upload_creates_rows(self):
        csv_file = SimpleUploadedFile(
            "typical_service_compositions.csv",
            (
                "Продукт;Код;Раздел (услуга);Состав услуг\n"
                "TAX2;S1;Раздел RU;Подготовка и выпуск отчета\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(reverse("typical_service_composition_csv_upload"), {"csv_file": csv_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 1)
        self.assertEqual(response.json()["warnings"], [])
        item = TypicalServiceComposition.objects.get()
        self.assertEqual(item.product, self.product)
        self.assertEqual(item.section, self.section)
        self.assertEqual(item.service_composition, "Подготовка и выпуск отчета")
        self.assertEqual(
            item.service_composition_editor_state,
            {"html": "", "plain_text": "Подготовка и выпуск отчета"},
        )
        self.assertEqual(item.position, 1)

    def test_typical_service_composition_csv_upload_accepts_legacy_rows_without_code(self):
        csv_file = SimpleUploadedFile(
            "typical_service_compositions.csv",
            (
                "Продукт;Раздел (услуга);Состав услуг\n"
                "TAX2;Раздел RU;Подготовка и выпуск отчета\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(reverse("typical_service_composition_csv_upload"), {"csv_file": csv_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 1)
        self.assertEqual(response.json()["warnings"], [])
        self.assertEqual(TypicalServiceComposition.objects.get().section, self.section)

    def test_typical_service_composition_docx_download_exports_editable_table(self):
        editor_state = {
            "html": (
                '<p><strong>Подготовка</strong></p>'
                '<ol><li data-list="ordered">Анализ</li>'
                '<li class="ql-indent-1" data-list="ordered">Выпуск отчета</li></ol>'
            ),
            "plain_text": "Подготовка\nАнализ\nВыпуск отчета",
        }
        item = TypicalServiceComposition.objects.create(
            product=self.product,
            section=self.section,
            service_composition=editor_state["plain_text"],
            service_composition_editor_state=editor_state,
            position=1,
        )

        response = self.client.get(reverse("typical_service_composition_docx_download"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("typical_service_compositions.docx", response["Content-Disposition"])
        document = Document(io.BytesIO(response.content))
        self.assertEqual(document.paragraphs[0].text, "TAX2")
        self.assertIn(document.paragraphs[0].style.name.lower(), {"heading 1", "заголовок 1"})
        self.assertEqual(len(document.tables), 1)
        table = document.tables[0]
        self.assertEqual([cell.text for cell in table.rows[0].cells], ["ID", "Продукт", "Код", "Раздел (услуга)", "Состав услуг"])
        self.assertEqual(table.rows[1].cells[0].text, str(item.pk))
        self.assertEqual(table.rows[1].cells[1].text, "TAX2")
        self.assertEqual(table.rows[1].cells[2].text, "S1")
        self.assertEqual(table.rows[1].cells[3].text, "Раздел RU")
        self.assertEqual(table.rows[1].cells[4].text, editor_state["plain_text"])
        self.assertIn('w:tblW w:type="pct" w:w="5000"', table._tbl.xml)
        for width in ("300", "650", "500", "1100", "2450"):
            self.assertIn(f'w:tcW w:type="pct" w:w="{width}"', table._tbl.xml)
        list_paragraphs = table.rows[1].cells[4].paragraphs[1:]
        self.assertTrue(all("w:numPr" in paragraph._element.xml for paragraph in list_paragraphs))

    def test_typical_service_composition_docx_download_restarts_numbering_per_cell(self):
        editor_state = {
            "html": (
                '<ol><li data-list="ordered">Первый пункт</li>'
                '<li class="ql-indent-1" data-list="ordered">Подпункт</li></ol>'
            ),
            "plain_text": "Первый пункт\nПодпункт",
        }
        for position in (1, 2):
            TypicalServiceComposition.objects.create(
                product=self.product,
                section=self.section,
                service_composition=editor_state["plain_text"],
                service_composition_editor_state=editor_state,
                position=position,
            )

        response = self.client.get(reverse("typical_service_composition_docx_download"))

        self.assertEqual(response.status_code, 200)
        document = Document(io.BytesIO(response.content))
        table = document.tables[0]
        first_cell_num_id = table.rows[1].cells[4].paragraphs[0]._p.pPr.numPr.numId.val
        second_cell_num_id = table.rows[2].cells[4].paragraphs[0]._p.pPr.numPr.numId.val
        self.assertNotEqual(first_cell_num_id, second_cell_num_id)

    def test_typical_service_composition_docx_download_groups_rows_by_product(self):
        editor_state = {
            "html": "<p>Состав TAX2</p>",
            "plain_text": "Состав TAX2",
        }
        other_editor_state = {
            "html": "<p>Состав AUD2</p>",
            "plain_text": "Состав AUD2",
        }
        TypicalServiceComposition.objects.create(
            product=self.product,
            section=self.section,
            service_composition=editor_state["plain_text"],
            service_composition_editor_state=editor_state,
            position=1,
        )
        TypicalServiceComposition.objects.create(
            product=self.other_product,
            section=self.other_section,
            service_composition=other_editor_state["plain_text"],
            service_composition_editor_state=other_editor_state,
            position=1,
        )

        response = self.client.get(reverse("typical_service_composition_docx_download"))

        self.assertEqual(response.status_code, 200)
        document = Document(io.BytesIO(response.content))
        self.assertEqual(len(document.tables), 2)
        self.assertEqual(document.paragraphs[0].text, "TAX2")
        self.assertEqual(document.paragraphs[1].text, "AUD2")
        self.assertEqual(document.tables[0].rows[1].cells[1].text, "TAX2")
        self.assertEqual(document.tables[1].rows[1].cells[1].text, "AUD2")

    def test_typical_service_composition_csv_download_respects_product_filter(self):
        TypicalServiceComposition.objects.create(
            product=self.product,
            section=self.section,
            service_composition="TAX2 состав",
            position=1,
        )
        TypicalServiceComposition.objects.create(
            product=self.other_product,
            section=self.other_section,
            service_composition="AUD2 состав",
            position=1,
        )

        response = self.client.get(
            reverse("typical_service_composition_csv_download"),
            {"product": [self.product.pk]},
        )

        self.assertEqual(response.status_code, 200)
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][0], "TAX2")

    def test_typical_service_composition_docx_download_respects_product_filter(self):
        TypicalServiceComposition.objects.create(
            product=self.product,
            section=self.section,
            service_composition="TAX2 состав",
            position=1,
        )
        TypicalServiceComposition.objects.create(
            product=self.other_product,
            section=self.other_section,
            service_composition="AUD2 состав",
            position=1,
        )

        response = self.client.get(
            reverse("typical_service_composition_docx_download"),
            {"product": [self.product.pk, self.other_product.pk]},
        )

        self.assertEqual(response.status_code, 200)
        document = Document(io.BytesIO(response.content))
        self.assertEqual(len(document.tables), 2)
        self.assertEqual(document.paragraphs[0].text, "TAX2")
        self.assertEqual(document.paragraphs[1].text, "AUD2")

    def test_typical_service_composition_csv_download_respects_consulting_filter(self):
        TypicalServiceComposition.objects.create(
            product=self.product,
            section=self.section,
            service_composition="TAX2 состав",
            position=1,
        )
        TypicalServiceComposition.objects.create(
            product=self.other_product,
            section=self.other_section,
            service_composition="AUD2 состав",
            position=1,
        )

        response = self.client.get(
            reverse("typical_service_composition_csv_download"),
            {"category": ["Аудит"]},
        )

        self.assertEqual(response.status_code, 200)
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][0], "AUD2")

    def test_typical_service_composition_docx_upload_reads_multiple_product_tables(self):
        tax_item = TypicalServiceComposition.objects.create(
            product=self.product,
            section=self.section,
            service_composition="TAX2 старый",
            service_composition_editor_state={"html": "<p>TAX2 старый</p>", "plain_text": "TAX2 старый"},
            position=1,
        )
        aud_item = TypicalServiceComposition.objects.create(
            product=self.other_product,
            section=self.other_section,
            service_composition="AUD2 старый",
            service_composition_editor_state={"html": "<p>AUD2 старый</p>", "plain_text": "AUD2 старый"},
            position=1,
        )
        docx_file = self._docx_upload_file([
            {
                "product": "TAX2",
                "rows": [{
                    "id": tax_item.pk,
                    "section": "Раздел RU",
                    "service_composition": "TAX2 новый",
                }],
            },
            {
                "product": "AUD2",
                "rows": [{
                    "id": aud_item.pk,
                    "section": "Другой раздел RU",
                    "service_composition": "AUD2 новый",
                }],
            },
        ])

        response = self.client.post(reverse("typical_service_composition_docx_upload"), {"csv_file": docx_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 0)
        self.assertEqual(response.json()["updated"], 2)
        tax_item.refresh_from_db()
        aud_item.refresh_from_db()
        self.assertEqual(tax_item.service_composition, "TAX2 новый")
        self.assertEqual(aud_item.service_composition, "AUD2 новый")

    def test_typical_service_composition_docx_upload_updates_existing_row_by_id(self):
        item = TypicalServiceComposition.objects.create(
            product=self.product,
            section=self.section,
            service_composition="Старый текст",
            service_composition_editor_state={"html": "<p>Старый текст</p>", "plain_text": "Старый текст"},
            position=1,
        )
        docx_file = self._docx_upload_file([
            {
                "product": "TAX2",
                "rows": [{
                    "id": item.pk,
                    "section": "Раздел RU",
                    "service_composition": "Новый текст из Word",
                }],
            },
        ])

        response = self.client.post(reverse("typical_service_composition_docx_upload"), {"csv_file": docx_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 0)
        self.assertEqual(response.json()["updated"], 1)
        self.assertEqual(response.json()["warnings"], [])
        item.refresh_from_db()
        self.assertEqual(item.service_composition, "Новый текст из Word")
        self.assertEqual(
            item.service_composition_editor_state,
            {"html": "<p>Новый текст из Word</p>", "plain_text": "Новый текст из Word"},
        )

    def test_typical_service_composition_docx_upload_creates_row_when_id_is_blank(self):
        docx_file = self._docx_upload_file([
            {
                "product": "TAX2",
                "rows": [{
                    "id": "",
                    "section_code": "S1",
                    "section": "Раздел RU",
                    "service_composition": "Новая строка из Word",
                }],
            },
        ])

        response = self.client.post(reverse("typical_service_composition_docx_upload"), {"csv_file": docx_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 1)
        self.assertEqual(response.json()["updated"], 0)
        item = TypicalServiceComposition.objects.get()
        self.assertEqual(item.product, self.product)
        self.assertEqual(item.section, self.section)
        self.assertEqual(item.service_composition, "Новая строка из Word")
        self.assertEqual(item.position, 1)

    def test_typical_service_composition_docx_upload_accepts_legacy_table_without_code(self):
        docx_file = self._docx_upload_file(
            [
                {
                    "product": "TAX2",
                    "rows": [{
                        "id": "",
                        "section": "Раздел RU",
                        "service_composition": "Старая структура Word",
                    }],
                },
            ],
            include_code=False,
        )

        response = self.client.post(reverse("typical_service_composition_docx_upload"), {"csv_file": docx_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 1)
        self.assertEqual(response.json()["warnings"], [])
        self.assertEqual(TypicalServiceComposition.objects.get().section, self.section)

    def test_typical_service_composition_docx_upload_preserves_multilevel_lists(self):
        editor_state = {
            "html": (
                '<ol><li data-list="ordered">Основной пункт</li>'
                '<li class="ql-indent-1" data-list="ordered">Подпункт</li></ol>'
                '<ul><li data-list="dash">Пункт с дефисом</li></ul>'
            ),
            "plain_text": "Основной пункт\nПодпункт\nПункт с дефисом",
        }
        item = TypicalServiceComposition.objects.create(
            product=self.product,
            section=self.section,
            service_composition=editor_state["plain_text"],
            service_composition_editor_state=editor_state,
            position=1,
        )
        download_response = self.client.get(reverse("typical_service_composition_docx_download"))
        docx_file = SimpleUploadedFile(
            "typical_service_compositions.docx",
            download_response.content,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

        response = self.client.post(reverse("typical_service_composition_docx_upload"), {"csv_file": docx_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["updated"], 1)
        item.refresh_from_db()
        self.assertEqual(item.service_composition, editor_state["plain_text"])
        self.assertIn('data-list="ordered"', item.service_composition_editor_state["html"])
        self.assertIn('class="ql-indent-1" data-list="ordered"', item.service_composition_editor_state["html"])
        self.assertIn('data-list="dash"', item.service_composition_editor_state["html"])

    def test_typical_service_composition_docx_upload_warns_on_invalid_references(self):
        docx_file = self._docx_upload_file([
            {
                "product": "TAX2",
                "rows": [
                    {
                        "id": "not-id",
                        "section": "Раздел RU",
                        "service_composition": "Некорректный ID",
                    },
                    {
                        "id": "",
                        "product": "UNKNOWN",
                        "section": "Раздел RU",
                        "service_composition": "Некорректный продукт",
                    },
                ],
            },
        ])

        response = self.client.post(reverse("typical_service_composition_docx_upload"), {"csv_file": docx_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 0)
        self.assertEqual(response.json()["updated"], 0)
        self.assertEqual(len(response.json()["warnings"]), 2)
        self.assertFalse(TypicalServiceComposition.objects.exists())

    def test_typical_service_composition_xlsx_download_preserves_editor_state(self):
        editor_state = {
            "html": (
                '<p><strong>Подготовка</strong></p>'
                '<ol><li data-list="dash">Анализ</li>'
                '<li class="ql-indent-1" data-list="check">Выпуск отчета</li></ol>'
            ),
            "plain_text": "Подготовка\nАнализ\nВыпуск отчета",
        }
        TypicalServiceComposition.objects.create(
            product=self.product,
            section=self.section,
            service_composition=editor_state["plain_text"],
            service_composition_editor_state=editor_state,
            position=1,
        )

        response = self.client.get(reverse("typical_service_composition_xlsx_download"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("typical_service_compositions.xlsx", response["Content-Disposition"])
        workbook = load_workbook(io.BytesIO(response.content))
        sheet = workbook.active
        self.assertEqual(sheet["A1"].value, "Продукт")
        self.assertEqual(sheet["B1"].value, "Код")
        self.assertEqual(sheet["C1"].value, "Раздел (услуга)")
        self.assertEqual(sheet["D1"].value, "Состав услуг")
        self.assertEqual(sheet["E1"].value, "Состояние редактора (JSON)")
        self.assertTrue(sheet.column_dimensions["E"].hidden)
        self.assertEqual(sheet["A2"].value, "TAX2")
        self.assertEqual(sheet["B2"].value, "S1")
        self.assertEqual(sheet["C2"].value, "Раздел RU")
        self.assertEqual(sheet["D2"].value, editor_state["plain_text"])
        self.assertEqual(json.loads(sheet["E2"].value), editor_state)

    def test_typical_service_composition_xlsx_upload_preserves_editor_state(self):
        editor_state = {
            "html": (
                '<p><span style="color:#ff0000"><strong>Подготовка</strong></span></p>'
                '<ol><li data-list="dash">Анализ</li>'
                '<li class="ql-indent-1" data-list="check">Выпуск отчета</li></ol>'
            ),
            "plain_text": "Подготовка\nАнализ\nВыпуск отчета",
        }
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Продукт", "Код", "Раздел (услуга)", "Состав услуг", "Состояние редактора (JSON)"])
        sheet.column_dimensions["E"].hidden = True
        sheet.append([
            "TAX2",
            "S1",
            "Раздел RU",
            editor_state["plain_text"],
            json.dumps(editor_state, ensure_ascii=False),
        ])
        buffer = io.BytesIO()
        workbook.save(buffer)
        xlsx_file = SimpleUploadedFile(
            "typical_service_compositions.xlsx",
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        response = self.client.post(reverse("typical_service_composition_xlsx_upload"), {"xlsx_file": xlsx_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 1)
        self.assertEqual(response.json()["warnings"], [])
        item = TypicalServiceComposition.objects.get()
        self.assertEqual(item.product, self.product)
        self.assertEqual(item.section, self.section)
        self.assertEqual(item.service_composition, editor_state["plain_text"])
        self.assertEqual(item.service_composition_editor_state, editor_state)

    def test_typical_service_composition_xlsx_upload_falls_back_to_plain_text(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Продукт", "Раздел (услуга)", "Состав услуг"])
        sheet.append(["TAX2", "Раздел RU", "Подготовка без скрытого состояния"])
        buffer = io.BytesIO()
        workbook.save(buffer)
        xlsx_file = SimpleUploadedFile(
            "typical_service_compositions.xlsx",
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        response = self.client.post(reverse("typical_service_composition_xlsx_upload"), {"xlsx_file": xlsx_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 1)
        item = TypicalServiceComposition.objects.get()
        self.assertEqual(item.service_composition, "Подготовка без скрытого состояния")
        self.assertEqual(
            item.service_composition_editor_state,
            {"html": "", "plain_text": "Подготовка без скрытого состояния"},
        )

    def test_typical_service_composition_xlsx_upload_uses_visible_text_when_state_is_stale(self):
        editor_state = {
            "html": "<p><strong>Старый текст</strong></p>",
            "plain_text": "Старый текст",
        }
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Продукт", "Код", "Раздел (услуга)", "Состав услуг", "Состояние редактора (JSON)"])
        sheet.column_dimensions["E"].hidden = True
        sheet.append([
            "TAX2",
            "S1",
            "Раздел RU",
            "Новый текст из Excel",
            json.dumps(editor_state, ensure_ascii=False),
        ])
        buffer = io.BytesIO()
        workbook.save(buffer)
        xlsx_file = SimpleUploadedFile(
            "typical_service_compositions.xlsx",
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        response = self.client.post(reverse("typical_service_composition_xlsx_upload"), {"xlsx_file": xlsx_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 1)
        self.assertEqual(len(response.json()["warnings"]), 1)
        item = TypicalServiceComposition.objects.get()
        self.assertEqual(item.service_composition, "Новый текст из Excel")
        self.assertEqual(
            item.service_composition_editor_state,
            {"html": "", "plain_text": "Новый текст из Excel"},
        )

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
            consulting_type="Горный",
            service_category="Инжиниринг",
            service_subtype="По международным стандартам",
            position=1,
        )
        self.other_product = Product.objects.create(
            short_name="TERM2",
            name_en="Terms 2",
            display_name="Terms 2",
            name_ru="Сроки 2",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
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
        self.assertContains(response, "Сроки предоставления исходных данных")
        self.assertContains(response, "Срок подготовки Предварительного отчёта")
        self.assertContains(response, "Срок подготовки Итогового отчёта")
        self.assertContains(response, ">0,0 нед.<", html=False)
        self.assertContains(response, ">1,5 мес.<", html=False)
        self.assertContains(response, ">3,0 нед.<", html=False)
        self.assertContains(response, 'id="typical-service-terms-actions"', html=False)
        self.assertContains(response, 'id="typical-service-terms-gantt-edit-btn"', html=False)
        self.assertContains(response, 'id="typical-service-term-gantt-editor"', html=False)
        self.assertContains(response, 'id="typical-service-term-gantt-cancel-btn"', html=False)
        self.assertContains(response, 'id="typical-service-term-gantt-resources-btn"', html=False)
        self.assertContains(response, 'id="typical-service-term-gantt-resources"', html=False)
        self.assertContains(response, reverse("typical_service_term_gantt", args=[TypicalServiceTerm.objects.get().pk]))
        self.assertContains(response, 'id="typical-service-terms-csv-download-btn"', html=False)
        self.assertContains(response, 'id="typical-service-terms-csv-upload-btn"', html=False)

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

    def test_typical_service_term_form_renders_product_options_with_display_name(self):
        response = self.client.get(reverse("typical_service_term_form_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<select name="product"', html=False)
        self.assertContains(response, "policy-product-select")
        self.assertContains(response, 'data-short-label="TERM"', html=False)
        self.assertContains(response, "TERM Terms")

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

    def test_typical_service_term_gantt_get_returns_default_diagram(self):
        item = TypicalServiceTerm.objects.create(
            product=self.product,
            preliminary_report_months=Decimal("1.5"),
            final_report_weeks=3,
            position=1,
        )
        TypicalSection.objects.create(
            product=self.product,
            code="TERM-S1",
            short_name="term-s1",
            short_name_ru="term-s1",
            name_en="Term section",
            name_ru="Раздел продукта",
            accounting_type="Раздел",
            position=1,
        )
        TypicalSection.objects.create(
            product=self.other_product,
            code="TERM2-S1",
            short_name="term2-s1",
            short_name_ru="term2-s1",
            name_en="Other term section",
            name_ru="Раздел другого продукта",
            accounting_type="Раздел",
            position=1,
        )

        response = self.client.get(reverse("typical_service_term_gantt", args=[item.pk]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["term"]["product"], "TERM")
        tasks = payload["gantt"]["data"]
        self.assertEqual(
            {task["system_key"] for task in tasks},
            {
                "source_data",
                "source_data_asset",
                "preliminary_report",
                "preliminary_report_asset",
                "preliminary_report_submission",
                "final_report",
            },
        )
        source_data = next(task for task in tasks if task["system_key"] == "source_data")
        source_asset = next(task for task in tasks if task["system_key"] == "source_data_asset")
        preliminary = next(task for task in tasks if task["system_key"] == "preliminary_report")
        asset = next(task for task in tasks if task["system_key"] == "preliminary_report_asset")
        submission = next(task for task in tasks if task["system_key"] == "preliminary_report_submission")
        self.assertEqual(source_asset["text"], "Актив")
        self.assertEqual(source_asset["parent"], source_data["id"])
        self.assertEqual(asset["text"], "Актив")
        self.assertEqual(asset["parent"], preliminary["id"])
        self.assertEqual(asset["start_date"], preliminary["start_date"])
        self.assertEqual(asset["end_date"], preliminary["end_date"])
        self.assertEqual(submission["text"], "Отправка Предварительного отчёта")
        self.assertEqual(submission["type"], "milestone")
        self.assertEqual(submission["start_date"], preliminary["end_date"])
        self.assertEqual(submission["end_date"], preliminary["end_date"])
        self.assertEqual(len(payload["gantt"]["links"]), 3)
        self.assertEqual(payload["gantt"]["meta"]["project_start"], payload["gantt"]["meta"]["base_date"])
        self.assertIn("project_end", payload["gantt"]["meta"])
        self.assertEqual(payload["gantt"]["meta"]["calendar_kind"], "abstract")
        self.assertEqual(payload["gantt"]["meta"]["executor_display"], "resource_name")
        self.assertEqual(
            payload["section_options"],
            [{"id": TypicalSection.objects.get(product=self.product).pk, "label": "Раздел продукта", "specialties": []}],
        )

    def test_typical_service_term_gantt_get_adds_asset_task_to_existing_diagram_without_saving(self):
        source_gantt = {
            "data": [
                {
                    "id": "preliminary",
                    "text": "Предварительный отчёт",
                    "system_key": "preliminary_report",
                    "start_date": "2026-01-01",
                    "end_date": "2026-02-01",
                    "type": "task",
                },
                {
                    "id": "final",
                    "text": "Итоговый отчёт",
                    "system_key": "final_report",
                    "start_date": "2026-02-01",
                    "end_date": "2026-02-15",
                    "type": "task",
                },
            ],
            "links": [],
            "meta": {"base_date": "2026-01-01", "calendar_kind": "abstract"},
        }
        item = TypicalServiceTerm.objects.create(
            product=self.product,
            preliminary_report_months=Decimal("1.0"),
            final_report_weeks=2,
            position=1,
            gantt_data=copy.deepcopy(source_gantt),
        )

        response = self.client.get(reverse("typical_service_term_gantt", args=[item.pk]))

        self.assertEqual(response.status_code, 200)
        tasks = response.json()["gantt"]["data"]
        source_data = next(task for task in tasks if task.get("system_key") == "source_data")
        source_asset = next(task for task in tasks if task.get("system_key") == "source_data_asset")
        self.assertEqual(source_data["text"], "Исходные данные")
        self.assertEqual(source_asset["text"], "Актив")
        self.assertEqual(source_asset["parent"], source_data["id"])
        submission = next(task for task in tasks if task.get("system_key") == "preliminary_report_submission")
        self.assertEqual(submission["text"], "Отправка Предварительного отчёта")
        self.assertEqual(submission["type"], "milestone")
        asset = next(task for task in tasks if task.get("system_key") == "preliminary_report_asset")
        self.assertEqual(asset["text"], "Актив")
        self.assertEqual(asset["parent"], "preliminary")
        item.refresh_from_db()
        self.assertEqual(item.gantt_data, source_gantt)

    def test_typical_service_term_gantt_post_rejects_production_calendar_payload(self):
        item = TypicalServiceTerm.objects.create(
            product=self.product,
            preliminary_report_months=Decimal("1.0"),
            final_report_weeks=2,
            position=1,
        )
        payload = {
            "data": [
                {
                    "id": "preliminary",
                    "text": "Предварительный отчёт",
                    "system_key": "preliminary_report",
                    "start_date": "2026-01-01",
                    "end_date": "2026-02-01",
                    "type": "task",
                },
                {
                    "id": "final",
                    "text": "Итоговый отчёт",
                    "system_key": "final_report",
                    "start_date": "2026-02-01",
                    "end_date": "2026-02-15",
                    "type": "task",
                },
            ],
            "links": [],
            "meta": {"base_date": "2026-01-01", "calendar_kind": "production"},
        }

        response = self.client.post(
            reverse("typical_service_term_gantt", args=[item.pk]),
            data=json.dumps(payload, ensure_ascii=False),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("условном календаре", response.json()["error"])

    def test_typical_service_term_gantt_returns_assignment_options_and_autofills_section_specialty(self):
        item = TypicalServiceTerm.objects.create(
            product=self.product,
            preliminary_report_months=Decimal("1.0"),
            final_report_weeks=2,
            position=1,
        )
        geology = ExpertSpecialty.objects.create(specialty="Геология", position=1)
        mining = ExpertSpecialty.objects.create(specialty="Горное дело", position=2)
        section = TypicalSection.objects.create(
            product=self.product,
            code="TERM-S1",
            short_name="term-s1",
            short_name_ru="term-s1",
            name_en="Term section",
            name_ru="Раздел продукта",
            accounting_type="Раздел",
            position=1,
        )
        TypicalSectionSpecialty.objects.create(section=section, specialty=geology, rank=2)
        TypicalSectionSpecialty.objects.create(section=section, specialty=mining, rank=1)
        executor_user = get_user_model().objects.create_user(
            username="executor-terms",
            first_name="Иван",
            last_name="Иванов",
        )
        employee = Employee.objects.create(user=executor_user, patronymic="Петрович")
        profile = ExpertProfile.objects.create(employee=employee, position=1)
        ExpertProfileSpecialty.objects.create(profile=profile, specialty=mining, rank=1)
        other_executor_user = get_user_model().objects.create_user(
            username="executor-terms-geology",
            first_name="Петр",
            last_name="Петров",
        )
        other_employee = Employee.objects.create(user=other_executor_user, patronymic="Сергеевич")
        other_profile = ExpertProfile.objects.create(employee=other_employee, position=2)
        ExpertProfileSpecialty.objects.create(profile=other_profile, specialty=geology, rank=1)

        response = self.client.get(reverse("typical_service_term_gantt", args=[item.pk]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["specialty_options"], ["Геология", "Горное дело"])
        self.assertEqual(
            payload["executor_options"],
            [
                {
                    "id": profile.pk,
                    "value": f"expert-profile:{profile.pk}",
                    "label": "Иванов И.П.",
                    "specialties": ["Горное дело"],
                },
                {
                    "id": other_profile.pk,
                    "value": f"expert-profile:{other_profile.pk}",
                    "label": "Петров П.С.",
                    "specialties": ["Геология"],
                },
            ],
        )
        self.assertEqual(
            payload["section_options"][0]["specialties"],
            [{"label": "Горное дело", "rank": 1}, {"label": "Геология", "rank": 2}],
        )

        save_payload = {
            "data": [
                {
                    "id": "section-task",
                    "text": "Раздел продукта",
                    "type": "service_section",
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-08",
                    "specialty": "",
                    "executor": f"expert-profile:{profile.pk}",
                },
                {
                    "id": "preliminary",
                    "text": "Предварительный отчёт",
                    "system_key": "preliminary_report",
                    "start_date": "2026-01-01",
                    "end_date": "2026-02-01",
                    "type": "task",
                },
                {
                    "id": "final",
                    "text": "Итоговый отчёт",
                    "system_key": "final_report",
                    "start_date": "2026-02-01",
                    "end_date": "2026-02-15",
                    "type": "task",
                },
            ],
            "links": [],
            "meta": {"base_date": "2026-01-01"},
        }

        response = self.client.post(
            reverse("typical_service_term_gantt", args=[item.pk]),
            data=json.dumps(save_payload, ensure_ascii=False),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["policyUpdate"],
            {"tables": ["typical-service-terms"], "refreshFilters": False},
        )
        item.refresh_from_db()
        self.assertEqual(item.gantt_data["data"][0]["specialty"], "Горное дело")
        self.assertEqual(item.gantt_data["data"][0]["executor"], f"expert-profile:{profile.pk}")

    def test_typical_service_term_gantt_distinguishes_duplicate_executor_labels(self):
        item = TypicalServiceTerm.objects.create(
            product=self.product,
            preliminary_report_months=Decimal("1.0"),
            final_report_weeks=2,
            position=1,
        )
        mining = ExpertSpecialty.objects.create(specialty="Горное дело", position=1)
        geology = ExpertSpecialty.objects.create(specialty="Геология", position=2)
        mining_user = get_user_model().objects.create_user(
            username="duplicate-executor-mining",
            first_name="Иван",
            last_name="Иванов",
        )
        mining_employee = Employee.objects.create(user=mining_user, patronymic="Петрович")
        mining_profile = ExpertProfile.objects.create(employee=mining_employee, position=1)
        ExpertProfileSpecialty.objects.create(profile=mining_profile, specialty=mining, rank=1)
        geology_user = get_user_model().objects.create_user(
            username="duplicate-executor-geology",
            first_name="Иван",
            last_name="Иванов",
        )
        geology_employee = Employee.objects.create(user=geology_user, patronymic="Петрович")
        geology_profile = ExpertProfile.objects.create(employee=geology_employee, position=2)
        ExpertProfileSpecialty.objects.create(profile=geology_profile, specialty=geology, rank=1)

        response = self.client.get(reverse("typical_service_term_gantt", args=[item.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["executor_options"],
            [
                {
                    "id": mining_profile.pk,
                    "value": f"expert-profile:{mining_profile.pk}",
                    "label": "Иванов И.П.",
                    "specialties": ["Горное дело"],
                },
                {
                    "id": geology_profile.pk,
                    "value": f"expert-profile:{geology_profile.pk}",
                    "label": "Иванов И.П.",
                    "specialties": ["Геология"],
                },
            ],
        )

        payload = {
            "data": [
                {
                    "id": "task",
                    "text": "Проектная задача",
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-08",
                    "type": "task",
                    "specialty": mining.specialty,
                    "executor": f"expert-profile:{geology_profile.pk}",
                },
                {
                    "id": "preliminary",
                    "text": "Предварительный отчёт",
                    "system_key": "preliminary_report",
                    "start_date": "2026-01-08",
                    "end_date": "2026-02-01",
                    "type": "task",
                },
                {
                    "id": "final",
                    "text": "Итоговый отчёт",
                    "system_key": "final_report",
                    "start_date": "2026-02-01",
                    "end_date": "2026-02-15",
                    "type": "task",
                },
            ],
            "links": [],
            "meta": {"base_date": "2026-01-01"},
        }

        response = self.client.post(
            reverse("typical_service_term_gantt", args=[item.pk]),
            data=json.dumps(payload, ensure_ascii=False),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Выберите исполнителя, связанного с выбранной специальностью.", response.json()["error"])

    def test_typical_service_term_gantt_post_saves_project_resources_meta(self):
        item = TypicalServiceTerm.objects.create(
            product=self.product,
            preliminary_report_months=Decimal("1.0"),
            final_report_weeks=2,
            position=1,
        )
        mining = ExpertSpecialty.objects.create(specialty="Горное дело", position=1)
        executor_user = get_user_model().objects.create_user(
            username="resource-executor-terms",
            first_name="Иван",
            last_name="Иванов",
        )
        employee = Employee.objects.create(user=executor_user, patronymic="Петрович")
        profile = ExpertProfile.objects.create(employee=employee, position=1)
        ExpertProfileSpecialty.objects.create(profile=profile, specialty=mining, rank=1)
        payload = {
            "data": [
                {
                    "id": "resource-task",
                    "text": "Проектная задача",
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-08",
                    "type": "task",
                    "specialty": "Горное дело",
                    "executor": "Иванов И.П.",
                    "resource_id": "resource-1",
                    "resource_name": "Сотрудник 1",
                },
                {
                    "id": "preliminary",
                    "text": "Предварительный отчёт",
                    "system_key": "preliminary_report",
                    "start_date": "2026-01-01",
                    "end_date": "2026-02-01",
                    "type": "task",
                },
                {
                    "id": "final",
                    "text": "Итоговый отчёт",
                    "system_key": "final_report",
                    "start_date": "2026-02-01",
                    "end_date": "2026-02-15",
                    "type": "task",
                },
            ],
            "links": [],
            "meta": {
                "base_date": "2026-01-01",
                "resources": [
                    {
                        "id": "resource-1",
                        "specialty": "Горное дело",
                        "executor": "Иванов И.П.",
                        "resource_name": "Горный эксперт",
                        "task_ids": ["resource-task"],
                    }
                ],
            },
        }

        response = self.client.post(
            reverse("typical_service_term_gantt", args=[item.pk]),
            data=json.dumps(payload, ensure_ascii=False),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(
            item.gantt_data["meta"]["resources"],
            [
                {
                    "id": "resource-1",
                    "specialty": "Горное дело",
                    "executor": "Иванов И.П.",
                    "resource_name": "Сотрудник 1",
                    "task_ids": ["resource-task"],
                    "position": 1,
                }
            ],
        )
        self.assertEqual(item.gantt_data["data"][0]["resource_name"], "Сотрудник 1")

    def test_typical_service_term_gantt_post_renames_duplicate_resource_ids(self):
        item = TypicalServiceTerm.objects.create(
            product=self.product,
            preliminary_report_months=Decimal("1.0"),
            final_report_weeks=2,
            position=1,
        )
        mining = ExpertSpecialty.objects.create(specialty="Горное дело", position=1)
        geology = ExpertSpecialty.objects.create(specialty="Геология", position=2)
        first_user = get_user_model().objects.create_user(
            username="resource-dup-first",
            first_name="Иван",
            last_name="Иванов",
        )
        second_user = get_user_model().objects.create_user(
            username="resource-dup-second",
            first_name="Петр",
            last_name="Петров",
        )
        first_employee = Employee.objects.create(user=first_user, patronymic="Петрович")
        second_employee = Employee.objects.create(user=second_user, patronymic="Петрович")
        first_profile = ExpertProfile.objects.create(employee=first_employee, position=1)
        second_profile = ExpertProfile.objects.create(employee=second_employee, position=2)
        ExpertProfileSpecialty.objects.create(profile=first_profile, specialty=mining, rank=1)
        ExpertProfileSpecialty.objects.create(profile=second_profile, specialty=geology, rank=1)
        payload = {
            "data": [
                {
                    "id": "resource-task-1",
                    "text": "Первая задача",
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-08",
                    "type": "task",
                    "specialty": "Горное дело",
                    "executor": "Иванов И.П.",
                    "resource_id": "resource-1",
                },
                {
                    "id": "resource-task-2",
                    "text": "Вторая задача",
                    "start_date": "2026-01-08",
                    "end_date": "2026-01-15",
                    "type": "task",
                    "specialty": "Геология",
                    "executor": "Петров П.П.",
                    "resource_id": "resource-1",
                },
                {
                    "id": "preliminary",
                    "text": "Предварительный отчёт",
                    "system_key": "preliminary_report",
                    "start_date": "2026-01-01",
                    "end_date": "2026-02-01",
                    "type": "task",
                },
                {
                    "id": "final",
                    "text": "Итоговый отчёт",
                    "system_key": "final_report",
                    "start_date": "2026-02-01",
                    "end_date": "2026-02-15",
                    "type": "task",
                },
            ],
            "links": [],
            "meta": {
                "base_date": "2026-01-01",
                "resources": [
                    {
                        "id": "resource-1",
                        "specialty": "Горное дело",
                        "executor": "Иванов И.П.",
                        "task_ids": ["resource-task-1"],
                    },
                    {
                        "id": "resource-1",
                        "specialty": "Геология",
                        "executor": "Петров П.П.",
                        "task_ids": ["resource-task-2"],
                    },
                ],
            },
        }

        response = self.client.post(
            reverse("typical_service_term_gantt", args=[item.pk]),
            data=json.dumps(payload, ensure_ascii=False),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content.decode("utf-8"))
        item.refresh_from_db()
        resource_ids = [resource["id"] for resource in item.gantt_data["meta"]["resources"]]
        self.assertEqual(resource_ids, ["resource-1", "resource-1-2"])
        second_task = next(task for task in item.gantt_data["data"] if task["id"] == "resource-task-2")
        self.assertEqual(second_task["resource_id"], "resource-1-2")

    def test_typical_service_term_gantt_post_rejects_resource_executor_from_other_specialty(self):
        item = TypicalServiceTerm.objects.create(
            product=self.product,
            preliminary_report_months=Decimal("1.0"),
            final_report_weeks=2,
            position=1,
        )
        mining = ExpertSpecialty.objects.create(specialty="Горное дело", position=1)
        geology = ExpertSpecialty.objects.create(specialty="Геология", position=2)
        executor_user = get_user_model().objects.create_user(
            username="resource-executor-invalid",
            first_name="Петр",
            last_name="Петров",
        )
        employee = Employee.objects.create(user=executor_user, patronymic="Сергеевич")
        profile = ExpertProfile.objects.create(employee=employee, position=1)
        ExpertProfileSpecialty.objects.create(profile=profile, specialty=geology, rank=1)
        payload = {
            "data": [
                {
                    "id": "preliminary",
                    "text": "Предварительный отчёт",
                    "system_key": "preliminary_report",
                    "start_date": "2026-01-01",
                    "end_date": "2026-02-01",
                    "type": "task",
                },
                {
                    "id": "final",
                    "text": "Итоговый отчёт",
                    "system_key": "final_report",
                    "start_date": "2026-02-01",
                    "end_date": "2026-02-15",
                    "type": "task",
                },
            ],
            "links": [],
            "meta": {
                "base_date": "2026-01-01",
                "resources": [
                    {
                        "id": "resource-1",
                        "specialty": mining.specialty,
                        "executor": "Петров П.С.",
                        "resource_name": "Некорректный ресурс",
                        "task_ids": [],
                    }
                ],
            },
        }

        response = self.client.post(
            reverse("typical_service_term_gantt", args=[item.pk]),
            data=json.dumps(payload, ensure_ascii=False),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Выберите исполнителя, связанного с выбранной специальностью.", response.json()["error"])
        item.refresh_from_db()
        self.assertEqual(item.gantt_data, {})

    def test_typical_service_term_gantt_post_rejects_duplicate_project_resource_pair(self):
        item = TypicalServiceTerm.objects.create(
            product=self.product,
            preliminary_report_months=Decimal("1.0"),
            final_report_weeks=2,
            position=1,
        )
        mining = ExpertSpecialty.objects.create(specialty="Горное дело", position=1)
        executor_user = get_user_model().objects.create_user(
            username="resource-duplicate-pair",
            first_name="Иван",
            last_name="Иванов",
        )
        employee = Employee.objects.create(user=executor_user, patronymic="Петрович")
        profile = ExpertProfile.objects.create(employee=employee, position=1)
        ExpertProfileSpecialty.objects.create(profile=profile, specialty=mining, rank=1)
        payload = {
            "data": [
                {
                    "id": "preliminary",
                    "text": "Предварительный отчёт",
                    "system_key": "preliminary_report",
                    "start_date": "2026-01-01",
                    "end_date": "2026-02-01",
                    "type": "task",
                },
                {
                    "id": "final",
                    "text": "Итоговый отчёт",
                    "system_key": "final_report",
                    "start_date": "2026-02-01",
                    "end_date": "2026-02-15",
                    "type": "task",
                },
            ],
            "links": [],
            "meta": {
                "base_date": "2026-01-01",
                "resources": [
                    {"id": "resource-1", "specialty": mining.specialty, "executor": "Иванов И.П.", "task_ids": []},
                    {"id": "resource-2", "specialty": mining.specialty, "executor": "Иванов И.П.", "task_ids": []},
                ],
            },
        }

        response = self.client.post(
            reverse("typical_service_term_gantt", args=[item.pk]),
            data=json.dumps(payload, ensure_ascii=False),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Ресурс с такой специальностью и ФИО уже есть в таблице.", response.json()["error"])

    def test_typical_service_term_gantt_post_rejects_resource_task_from_unavailable_section_specialty(self):
        item = TypicalServiceTerm.objects.create(
            product=self.product,
            preliminary_report_months=Decimal("1.0"),
            final_report_weeks=2,
            position=1,
        )
        mining = ExpertSpecialty.objects.create(specialty="Горное дело", position=1)
        geology = ExpertSpecialty.objects.create(specialty="Геология", position=2)
        section = TypicalSection.objects.create(
            product=self.product,
            code="TERM-S2",
            short_name="term-s2",
            short_name_ru="term-s2",
            name_en="Term section 2",
            name_ru="Раздел геологов",
            accounting_type="Раздел",
            position=1,
        )
        TypicalSectionSpecialty.objects.create(section=section, specialty=geology, rank=1)
        executor_user = get_user_model().objects.create_user(
            username="resource-unavailable-section",
            first_name="Иван",
            last_name="Иванов",
        )
        employee = Employee.objects.create(user=executor_user, patronymic="Петрович")
        profile = ExpertProfile.objects.create(employee=employee, position=1)
        ExpertProfileSpecialty.objects.create(profile=profile, specialty=mining, rank=1)
        payload = {
            "data": [
                {
                    "id": "section-task",
                    "text": "Раздел геологов",
                    "type": "service_section",
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-08",
                },
                {
                    "id": "child-task",
                    "text": "Операция раздела",
                    "parent": "section-task",
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-08",
                    "type": "task",
                },
                {
                    "id": "preliminary",
                    "text": "Предварительный отчёт",
                    "system_key": "preliminary_report",
                    "start_date": "2026-01-08",
                    "end_date": "2026-02-01",
                    "type": "task",
                },
                {
                    "id": "final",
                    "text": "Итоговый отчёт",
                    "system_key": "final_report",
                    "start_date": "2026-02-01",
                    "end_date": "2026-02-15",
                    "type": "task",
                },
            ],
            "links": [],
            "meta": {
                "base_date": "2026-01-01",
                "resources": [
                    {
                        "id": "resource-1",
                        "specialty": mining.specialty,
                        "executor": "Иванов И.П.",
                        "task_ids": ["child-task"],
                    }
                ],
            },
        }

        response = self.client.post(
            reverse("typical_service_term_gantt", args=[item.pk]),
            data=json.dumps(payload, ensure_ascii=False),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "Выберите задачу из раздела (услуги), доступного выбранной специальности ресурса.",
            response.json()["error"],
        )

    def test_typical_service_term_gantt_post_rejects_resource_parent_task_assignment(self):
        item = TypicalServiceTerm.objects.create(
            product=self.product,
            preliminary_report_months=Decimal("1.0"),
            final_report_weeks=2,
            position=1,
        )
        mining = ExpertSpecialty.objects.create(specialty="Горное дело", position=1)
        executor_user = get_user_model().objects.create_user(
            username="resource-parent-assignment",
            first_name="Иван",
            last_name="Иванов",
        )
        employee = Employee.objects.create(user=executor_user, patronymic="Петрович")
        profile = ExpertProfile.objects.create(employee=employee, position=1)
        ExpertProfileSpecialty.objects.create(profile=profile, specialty=mining, rank=1)
        payload = {
            "data": [
                {
                    "id": "parent-task",
                    "text": "Родительская задача",
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-08",
                    "type": "project",
                    "specialty": mining.specialty,
                    "executor": "Иванов И.П.",
                    "resource_id": "resource-1",
                },
                {
                    "id": "child-task",
                    "text": "Дочерняя задача",
                    "parent": "parent-task",
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-08",
                    "type": "task",
                },
                {
                    "id": "preliminary",
                    "text": "Предварительный отчёт",
                    "system_key": "preliminary_report",
                    "start_date": "2026-01-08",
                    "end_date": "2026-02-01",
                    "type": "task",
                },
                {
                    "id": "final",
                    "text": "Итоговый отчёт",
                    "system_key": "final_report",
                    "start_date": "2026-02-01",
                    "end_date": "2026-02-15",
                    "type": "task",
                },
            ],
            "links": [],
            "meta": {
                "base_date": "2026-01-01",
                "resources": [
                    {
                        "id": "resource-1",
                        "specialty": mining.specialty,
                        "executor": "Иванов И.П.",
                        "resource_name": "Горный эксперт",
                        "task_ids": ["parent-task"],
                    }
                ],
            },
        }

        response = self.client.post(
            reverse("typical_service_term_gantt", args=[item.pk]),
            data=json.dumps(payload, ensure_ascii=False),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Родительскую задачу нельзя назначить ресурсу проекта.", response.json()["error"])
        item.refresh_from_db()
        self.assertEqual(item.gantt_data, {})

    def test_typical_service_term_gantt_post_saves_diagram_and_updates_terms(self):
        item = TypicalServiceTerm.objects.create(
            product=self.product,
            preliminary_report_months=Decimal("1.0"),
            final_report_weeks=2,
            position=1,
        )
        payload = {
            "data": [
                {
                    "id": "preliminary",
                    "text": "Переименованный предварительный отчёт",
                    "system_key": "preliminary_report",
                    "start_date": "2026-02-01",
                    "end_date": "2026-04-01",
                    "progress": 0,
                    "type": "task",
                },
                {
                    "id": "final",
                    "text": "Переименованный итоговый отчёт",
                    "system_key": "final_report",
                    "start_date": "2026-04-01",
                    "end_date": "2026-05-13",
                    "progress": 0,
                    "type": "task",
                },
            ],
            "links": [{"id": "link-1", "source": "preliminary", "target": "final", "type": "0"}],
            "meta": {
                "base_date": "2026-01-01",
                "project_start": "2026-01-01",
                "project_end": "2026-06-01",
            },
        }

        response = self.client.post(
            reverse("typical_service_term_gantt", args=[item.pk]),
            data=json.dumps(payload, ensure_ascii=False),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        item.refresh_from_db()
        self.assertEqual(item.source_data_weeks, 0)
        self.assertEqual(item.preliminary_report_months, Decimal("2.0"))
        self.assertEqual(item.final_report_weeks, 6)
        source_data = next(
            task for task in item.gantt_data["data"]
            if task.get("system_key") == "source_data"
        )
        self.assertEqual(source_data["text"], "Исходные данные")
        preliminary = next(
            task for task in item.gantt_data["data"]
            if task.get("system_key") == "preliminary_report"
        )
        self.assertEqual(preliminary["text"], "Предварительный отчёт")
        asset = next(
            task for task in item.gantt_data["data"]
            if task.get("system_key") == "preliminary_report_asset"
        )
        self.assertEqual(asset["text"], "Актив")
        self.assertEqual(asset["parent"], "preliminary")
        self.assertEqual(asset["start_date"], preliminary["start_date"])
        self.assertEqual(asset["end_date"], preliminary["end_date"])
        submission = next(
            task for task in item.gantt_data["data"]
            if task.get("system_key") == "preliminary_report_submission"
        )
        self.assertEqual(submission["text"], "Отправка Предварительного отчёта")
        self.assertEqual(submission["type"], "milestone")
        final = next(
            task for task in item.gantt_data["data"]
            if task.get("system_key") == "final_report"
        )
        self.assertEqual(final["text"], "Итоговый отчёт")
        self.assertEqual(item.gantt_data["links"][0]["source"], "preliminary")
        self.assertEqual(item.gantt_data["meta"]["project_start"], "2026-01-01")
        self.assertEqual(item.gantt_data["meta"]["project_end"], "2026-06-01")

    def test_typical_service_term_gantt_post_accepts_product_section_task_type(self):
        item = TypicalServiceTerm.objects.create(
            product=self.product,
            preliminary_report_months=Decimal("1.0"),
            final_report_weeks=2,
            position=1,
        )
        TypicalSection.objects.create(
            product=self.product,
            code="TERM-S1",
            short_name="term-s1",
            short_name_ru="term-s1",
            name_en="Term section",
            name_ru="Раздел продукта",
            accounting_type="Раздел",
            position=1,
        )
        payload = {
            "data": [
                {
                    "id": "section-task",
                    "text": "Раздел продукта",
                    "type": "service_section",
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-08",
                },
                {
                    "id": "preliminary",
                    "text": "Предварительный отчёт",
                    "system_key": "preliminary_report",
                    "start_date": "2026-01-01",
                    "end_date": "2026-02-01",
                    "type": "task",
                },
                {
                    "id": "final",
                    "text": "Итоговый отчёт",
                    "system_key": "final_report",
                    "start_date": "2026-02-01",
                    "end_date": "2026-02-15",
                    "type": "task",
                },
            ],
            "links": [],
            "meta": {"base_date": "2026-01-01"},
        }

        response = self.client.post(
            reverse("typical_service_term_gantt", args=[item.pk]),
            data=json.dumps(payload, ensure_ascii=False),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.gantt_data["data"][0]["type"], "service_section")
        self.assertEqual(item.gantt_data["data"][0]["text"], "Раздел продукта")

    def test_typical_service_term_gantt_post_rejects_section_from_other_product(self):
        item = TypicalServiceTerm.objects.create(
            product=self.product,
            preliminary_report_months=Decimal("1.0"),
            final_report_weeks=2,
            position=1,
        )
        TypicalSection.objects.create(
            product=self.other_product,
            code="TERM2-S1",
            short_name="term2-s1",
            short_name_ru="term2-s1",
            name_en="Other term section",
            name_ru="Чужой раздел",
            accounting_type="Раздел",
            position=1,
        )
        payload = {
            "data": [
                {
                    "id": "section-task",
                    "text": "Чужой раздел",
                    "type": "service_section",
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-08",
                },
                {
                    "id": "preliminary",
                    "text": "Предварительный отчёт",
                    "system_key": "preliminary_report",
                    "start_date": "2026-01-01",
                    "end_date": "2026-02-01",
                    "type": "task",
                },
                {
                    "id": "final",
                    "text": "Итоговый отчёт",
                    "system_key": "final_report",
                    "start_date": "2026-02-01",
                    "end_date": "2026-02-15",
                    "type": "task",
                },
            ],
            "links": [],
            "meta": {"base_date": "2026-01-01"},
        }

        response = self.client.post(
            reverse("typical_service_term_gantt", args=[item.pk]),
            data=json.dumps(payload, ensure_ascii=False),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Выберите раздел", response.json()["error"])
        item.refresh_from_db()
        self.assertEqual(item.gantt_data, {})

    def test_typical_service_term_gantt_post_rolls_up_parent_dates_from_children(self):
        item = TypicalServiceTerm.objects.create(
            product=self.product,
            preliminary_report_months=Decimal("1.0"),
            final_report_weeks=2,
            position=1,
        )
        payload = {
            "data": [
                {
                    "id": "preliminary",
                    "text": "Предварительный отчёт",
                    "system_key": "preliminary_report",
                    "start_date": "2026-01-01",
                    "end_date": "2026-02-01",
                    "progress": 0,
                    "type": "task",
                },
                {
                    "id": "preliminary-child",
                    "text": "Подзадача предварительного отчёта",
                    "parent": "preliminary",
                    "start_date": "2026-01-15",
                    "end_date": "2026-04-01",
                    "progress": 0,
                    "type": "task",
                },
                {
                    "id": "final",
                    "text": "Итоговый отчёт",
                    "system_key": "final_report",
                    "start_date": "2026-04-01",
                    "end_date": "2026-04-15",
                    "progress": 0,
                    "type": "task",
                },
            ],
            "links": [],
            "meta": {"base_date": "2026-01-01"},
        }

        response = self.client.post(
            reverse("typical_service_term_gantt", args=[item.pk]),
            data=json.dumps(payload, ensure_ascii=False),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        parent_task = next(
            task for task in item.gantt_data["data"]
            if task.get("system_key") == "preliminary_report"
        )
        self.assertEqual(parent_task["end_date"], "2026-04-01")
        self.assertEqual(parent_task["type"], "project")
        asset_task = next(
            task for task in item.gantt_data["data"]
            if task.get("system_key") == "preliminary_report_asset"
        )
        self.assertEqual(asset_task["start_date"], parent_task["start_date"])
        self.assertEqual(asset_task["end_date"], parent_task["end_date"])
        self.assertEqual(item.preliminary_report_months, Decimal("3.0"))

    def test_typical_service_term_gantt_post_rejects_cyclic_parent_chain(self):
        item = TypicalServiceTerm.objects.create(
            product=self.product,
            preliminary_report_months=Decimal("1.0"),
            final_report_weeks=2,
            position=1,
        )
        payload = {
            "data": [
                {
                    "id": "preliminary",
                    "text": "Предварительный отчёт",
                    "system_key": "preliminary_report",
                    "parent": "final",
                    "start_date": "2026-01-01",
                    "end_date": "2026-02-01",
                    "type": "task",
                },
                {
                    "id": "final",
                    "text": "Итоговый отчёт",
                    "system_key": "final_report",
                    "parent": "preliminary",
                    "start_date": "2026-02-01",
                    "end_date": "2026-02-15",
                    "type": "task",
                },
            ],
            "links": [],
            "meta": {"base_date": "2026-01-01"},
        }

        response = self.client.post(
            reverse("typical_service_term_gantt", args=[item.pk]),
            data=json.dumps(payload, ensure_ascii=False),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("циклическая связь", response.json()["error"])
        item.refresh_from_db()
        self.assertEqual(item.gantt_data, {})

    def test_typical_service_term_gantt_post_requires_system_tasks(self):
        item = TypicalServiceTerm.objects.create(
            product=self.product,
            preliminary_report_months=Decimal("1.0"),
            final_report_weeks=2,
            position=1,
        )

        response = self.client.post(
            reverse("typical_service_term_gantt", args=[item.pk]),
            data=json.dumps({"data": [{"id": "task", "start_date": "2026-01-01", "end_date": "2026-01-08"}]}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        item.refresh_from_db()
        self.assertEqual(item.preliminary_report_months, Decimal("1.0"))
        self.assertEqual(item.final_report_weeks, 2)

    def test_non_staff_user_cannot_edit_typical_service_term_gantt(self):
        item = TypicalServiceTerm.objects.create(
            product=self.product,
            preliminary_report_months=Decimal("1.0"),
            final_report_weeks=2,
            position=1,
        )
        non_staff = get_user_model().objects.create_user(
            username="policy-user-terms-gantt",
            password="secret123",
            is_staff=False,
        )
        client = self.client_class()
        client.force_login(non_staff)

        response = client.post(
            reverse("typical_service_term_gantt", args=[item.pk]),
            data=json.dumps({"data": []}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.gantt_data, {})

    def test_typical_service_term_csv_download_exports_current_table_columns(self):
        TypicalServiceTerm.objects.create(
            product=self.product,
            preliminary_report_months=Decimal("1.5"),
            final_report_weeks=3,
            position=1,
        )

        response = self.client.get(reverse("typical_service_term_csv_download"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("typical_service_terms.csv", response["Content-Disposition"])
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(
            rows[0],
            [
                "Продукт",
                "Сроки предоставления исходных данных",
                "Единица срока предоставления исходных данных",
                "Срок подготовки Предварительного отчёта",
                "Единица срока подготовки Предварительного отчёта",
                "Срок подготовки Итогового отчёта",
                "Единица срока подготовки Итогового отчёта",
            ],
        )
        self.assertEqual(rows[1], ["TERM", "0,0", "нед.", "1,5", "мес.", "3,0", "нед."])

    def test_typical_service_term_csv_download_respects_product_filter(self):
        TypicalServiceTerm.objects.create(
            product=self.product,
            preliminary_report_months=Decimal("1.5"),
            final_report_weeks=3,
            position=1,
        )
        TypicalServiceTerm.objects.create(
            product=self.other_product,
            preliminary_report_months=Decimal("2.0"),
            final_report_weeks=5,
            position=2,
        )

        response = self.client.get(
            reverse("typical_service_term_csv_download"),
            {"product": [self.product.pk]},
        )

        self.assertEqual(response.status_code, 200)
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][0], "TERM")

    def test_typical_service_term_csv_upload_creates_rows(self):
        csv_file = SimpleUploadedFile(
            "typical_service_terms.csv",
            (
                "Продукт;Срок подготовки Предварительного отчёта, мес.;Срок подготовки Итогового отчёта, нед.\n"
                "TERM;2,5;4\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(reverse("typical_service_term_csv_upload"), {"csv_file": csv_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 1)
        self.assertEqual(response.json()["warnings"], [])
        item = TypicalServiceTerm.objects.get()
        self.assertEqual(item.product, self.product)
        self.assertEqual(item.source_data_weeks, 0)
        self.assertEqual(item.preliminary_report_months, Decimal("2.5"))
        self.assertEqual(item.final_report_weeks, 4)
        self.assertEqual(item.position, 1)

    def test_typical_service_term_csv_upload_accepts_source_data_weeks(self):
        csv_file = SimpleUploadedFile(
            "typical_service_terms.csv",
            (
                "Продукт;Сроки предоставления исходных данных;Единица срока предоставления исходных данных;"
                "Срок подготовки Предварительного отчёта;Единица срока подготовки Предварительного отчёта;"
                "Срок подготовки Итогового отчёта;Единица срока подготовки Итогового отчёта\n"
                "TERM;3;дн.;2,5;нед.;4;мес.\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(reverse("typical_service_term_csv_upload"), {"csv_file": csv_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 1)
        item = TypicalServiceTerm.objects.get()
        self.assertEqual(item.source_data_weeks, 3)
        self.assertEqual(item.source_data_term_unit, "days")
        self.assertEqual(item.preliminary_report_months, Decimal("2.5"))
        self.assertEqual(item.preliminary_report_term_unit, "weeks")
        self.assertEqual(item.final_report_weeks, 4)
        self.assertEqual(item.final_report_term_unit, "months")

    def test_typical_service_term_csv_upload_updates_existing_product_row(self):
        item = TypicalServiceTerm.objects.create(
            product=self.product,
            source_data_weeks=1,
            preliminary_report_months=Decimal("1.0"),
            final_report_weeks=2,
            position=1,
        )
        csv_file = SimpleUploadedFile(
            "typical_service_terms.csv",
            (
                "Продукт;Сроки предоставления исходных данных, нед.;Срок подготовки Предварительного отчёта, мес.;Срок подготовки Итогового отчёта, нед.\n"
                "TERM;4;3,5;7\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(reverse("typical_service_term_csv_upload"), {"csv_file": csv_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 0)
        self.assertEqual(response.json()["updated"], 1)
        self.assertEqual(TypicalServiceTerm.objects.count(), 1)
        item.refresh_from_db()
        self.assertEqual(item.source_data_weeks, 4)
        self.assertEqual(item.preliminary_report_months, Decimal("3.5"))
        self.assertEqual(item.final_report_weeks, 7)

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
            consulting_type="Горный",
            service_category="Инжиниринг",
            service_subtype="По международным стандартам",
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
        self.assertContains(response, ">Код<", html=False)
        self.assertContains(response, "TS1")
        self.assertContains(response, ">5<", html=False)
        self.assertContains(response, 'id="tariffs-csv-download-btn"', html=False)
        self.assertContains(response, 'id="tariffs-csv-upload-btn"', html=False)

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

    def test_tariff_form_renders_product_options_with_display_name(self):
        response = self.client.get(reverse("tariff_form_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<select name="product"', html=False)
        self.assertContains(response, "policy-product-select")
        self.assertContains(response, 'data-short-label="TAR"', html=False)
        self.assertContains(response, "TAR Tariff product")
        self.assertContains(response, 'name="section_code"', html=False)
        self.assertContains(response, "readonly-field", html=False)
        self.assertContains(response, 'tabindex="-1"', html=False)
        self.assertContains(response, "policy-section-select")
        self.assertContains(response, '"label": "TS1 Тарифный раздел"', html=False)
        self.assertContains(response, '"displayLabel": "Тарифный раздел"', html=False)

    def test_tariff_csv_download_exports_current_table_columns(self):
        Tariff.objects.create(
            product=self.product,
            section=self.section,
            base_rate_vpm=Decimal("10.00"),
            service_hours=8,
            service_days_tkp=5,
            created_by=self.user,
            position=1,
        )

        response = self.client.get(reverse("tariff_csv_download"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("section_tariffs.csv", response["Content-Disposition"])
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(
            rows[0],
            [
                "Продукт",
                "Код",
                "Раздел (услуга)",
                "Базовая ставка в ВПМ",
                "Объем услуг в часах",
                "Объем услуг в днях для ТКП",
                "Руководитель направления",
            ],
        )
        self.assertEqual(rows[1], ["TAR", "TS1", "Тарифный раздел", "10,00", "8", "5", "policy-admin-4"])

    def test_tariff_csv_download_respects_product_filter(self):
        other_product = Product.objects.create(
            short_name="AUD",
            name_en="Audit product",
            display_name="Audit product",
            name_ru="Аудитный продукт",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
            position=2,
        )
        other_section = TypicalSection.objects.create(
            product=other_product,
            code="AS1",
            short_name="audit-section",
            short_name_ru="audit-section-ru",
            name_en="Audit section EN",
            name_ru="Аудитный раздел",
            accounting_type="Раздел",
            position=1,
        )
        Tariff.objects.create(
            product=self.product,
            section=self.section,
            base_rate_vpm=Decimal("10.00"),
            service_hours=8,
            service_days_tkp=5,
            created_by=self.user,
            position=1,
        )
        Tariff.objects.create(
            product=other_product,
            section=other_section,
            base_rate_vpm=Decimal("20.00"),
            service_hours=16,
            service_days_tkp=10,
            created_by=self.user,
            position=2,
        )

        response = self.client.get(
            reverse("tariff_csv_download"),
            {"product": [self.product.pk]},
        )

        self.assertEqual(response.status_code, 200)
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][0], "TAR")

    def test_tariff_csv_upload_creates_rows_for_current_user(self):
        csv_file = SimpleUploadedFile(
            "section_tariffs.csv",
            (
                "Продукт;Код;Раздел (услуга);Базовая ставка в ВПМ;Объем услуг в часах;Объем услуг в днях для ТКП\n"
                "TAR;TS1;Тарифный раздел;12,50;16;6\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(reverse("tariff_csv_upload"), {"csv_file": csv_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 1)
        self.assertEqual(response.json()["warnings"], [])
        tariff = Tariff.objects.get()
        self.assertEqual(tariff.product, self.product)
        self.assertEqual(tariff.section, self.section)
        self.assertEqual(tariff.base_rate_vpm, Decimal("12.50"))
        self.assertEqual(tariff.service_hours, 16)
        self.assertEqual(tariff.service_days_tkp, 6)
        self.assertEqual(tariff.created_by, self.user)
        self.assertEqual(tariff.position, 1)

    def test_tariff_csv_upload_updates_existing_product_section_owner_row(self):
        tariff = Tariff.objects.create(
            product=self.product,
            section=self.section,
            base_rate_vpm=Decimal("10.00"),
            service_hours=8,
            service_days_tkp=5,
            created_by=self.user,
            position=1,
        )
        csv_file = SimpleUploadedFile(
            "section_tariffs.csv",
            (
                "Продукт;Код;Раздел (услуга);Базовая ставка в ВПМ;Объем услуг в часах;Объем услуг в днях для ТКП\n"
                "TAR;TS1;Тарифный раздел;22,50;18;9\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(reverse("tariff_csv_upload"), {"csv_file": csv_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 0)
        self.assertEqual(response.json()["updated"], 1)
        self.assertEqual(Tariff.objects.count(), 1)
        tariff.refresh_from_db()
        self.assertEqual(tariff.base_rate_vpm, Decimal("22.50"))
        self.assertEqual(tariff.service_hours, 18)
        self.assertEqual(tariff.service_days_tkp, 9)
        self.assertEqual(tariff.position, 1)

    def test_tariff_csv_upload_accepts_legacy_rows_without_code(self):
        csv_file = SimpleUploadedFile(
            "section_tariffs.csv",
            (
                "Продукт;Раздел (услуга);Базовая ставка в ВПМ;Объем услуг в часах;Объем услуг в днях для ТКП\n"
                "TAR;Тарифный раздел;12,50;16;6\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(reverse("tariff_csv_upload"), {"csv_file": csv_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 1)
        self.assertEqual(response.json()["warnings"], [])
        self.assertEqual(Tariff.objects.get().section, self.section)

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
            consulting_type="Горный",
            service_category="Инжиниринг",
            service_subtype="По международным стандартам",
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


POLICY_TEST_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "policy-stage-six-default",
    },
    "policy": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "policy-stage-six",
        "KEY_PREFIX": "tests:policy",
        "TIMEOUT": 300,
    },
}


@override_settings(CACHES=POLICY_TEST_CACHES)
class PolicyStageSixCacheTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="policy-cache-user",
            password="secret123",
            is_staff=True,
        )
        self.client.force_login(self.user)
        caches["default"].clear()
        caches["policy"].clear()

    def _create_product(self, suffix="1", position=1):
        return Product.objects.create(
            short_name=f"CACHE-{suffix}",
            name_en=f"Cache product {suffix}",
            display_name=f"Cache product {suffix}",
            name_ru=f"Кэш-продукт {suffix}",
            consulting_type="Consulting",
            service_category="Category",
            service_subtype="Subtype",
            position=position,
        )

    def _catalog(self, params=None):
        return self.client.get(reverse("policy_filter_catalog"), params or {})

    def _warm_catalog(self):
        first = self._catalog()
        self.assertIn(
            first.headers["X-Policy-Cache"],
            {policy_cache.POLICY_CACHE_MISS, policy_cache.POLICY_CACHE_HIT},
        )
        second = self._catalog()
        self.assertEqual(
            second.headers["X-Policy-Cache"],
            policy_cache.POLICY_CACHE_HIT,
        )
        return second

    @staticmethod
    def _product_select_count(queries):
        return sum(
            '"policy_app_product"' in query["sql"]
            and query["sql"].lstrip().upper().startswith("SELECT")
            for query in queries
        )

    def test_catalog_cold_and_warm_query_behavior(self):
        with self.captureOnCommitCallbacks(execute=True):
            self._create_product()
        caches["policy"].clear()

        with CaptureQueriesContext(connection) as cold_queries:
            cold = self._catalog()
        with CaptureQueriesContext(connection) as warm_queries:
            warm = self._catalog()

        self.assertEqual(cold.status_code, 200)
        self.assertEqual(cold.headers["X-Policy-Cache"], policy_cache.POLICY_CACHE_MISS)
        self.assertEqual(warm.headers["X-Policy-Cache"], policy_cache.POLICY_CACHE_HIT)
        self.assertEqual(self._product_select_count(cold_queries), 1)
        self.assertEqual(self._product_select_count(warm_queries), 0)
        self.assertEqual(cold.json(), warm.json())
        self.assertIn(
            'policy-cache;desc="hit"',
            warm.headers["Server-Timing"],
        )
        self.assertIn("app;dur=", warm.headers["Server-Timing"])

    def test_create_edit_delete_invalidate_after_commit(self):
        self._warm_catalog()

        with self.captureOnCommitCallbacks(execute=True):
            product = self._create_product()
        created = self._catalog()
        self.assertEqual(created.headers["X-Policy-Cache"], policy_cache.POLICY_CACHE_MISS)
        self.assertEqual(created.json()["products"][0]["id"], product.pk)
        self._warm_catalog()

        with self.captureOnCommitCallbacks(execute=True):
            product.display_name = "Changed cache product"
            product.save(update_fields=["display_name"])
        edited = self._catalog()
        self.assertEqual(edited.headers["X-Policy-Cache"], policy_cache.POLICY_CACHE_MISS)
        self.assertEqual(edited.json()["products"][0]["label"], "CACHE-1 Changed cache product")
        self._warm_catalog()

        with self.captureOnCommitCallbacks(execute=True):
            product.delete()
        deleted = self._catalog()
        self.assertEqual(deleted.headers["X-Policy-Cache"], policy_cache.POLICY_CACHE_MISS)
        self.assertEqual(deleted.json()["products"], [])

    def test_m2m_and_external_display_dependency_invalidate(self):
        self.assertSetEqual(
            policy_signals.POLICY_M2M_THROUGH_MODELS,
            {
                Product.owners.through,
                ExpertiseDirection.owners.through,
                SpecialtyTariff.specialties.through,
                TypicalSection.specialties.through,
            },
        )
        self.assertSetEqual(
            policy_signals.EXTERNAL_POLICY_DISPLAY_MODELS,
            {GroupMember, OrgUnit, ExpertSpecialty, OKVCurrency},
        )
        with self.captureOnCommitCallbacks(execute=True):
            product = self._create_product()
            owner = GroupMember.objects.create(
                short_name="Owner",
                country_name="Russia",
                position=1,
            )
        self._warm_catalog()

        with self.captureOnCommitCallbacks(execute=True):
            product.owners.add(owner)
        after_m2m = self._catalog()
        self.assertEqual(after_m2m.headers["X-Policy-Cache"], policy_cache.POLICY_CACHE_MISS)
        self._warm_catalog()

        with self.captureOnCommitCallbacks(execute=True):
            owner.short_name = "Changed owner"
            owner.save(update_fields=["short_name"])
        after_external_edit = self._catalog()
        self.assertEqual(
            after_external_edit.headers["X-Policy-Cache"],
            policy_cache.POLICY_CACHE_MISS,
        )

    def test_rollback_does_not_change_generation(self):
        self._warm_catalog()
        generation_before = caches["policy"].get(policy_cache.POLICY_GENERATION_KEY)

        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self._create_product()
                raise RuntimeError("rollback")

        generation_after = caches["policy"].get(policy_cache.POLICY_GENERATION_KEY)
        response = self._catalog()
        self.assertEqual(generation_after, generation_before)
        self.assertEqual(response.headers["X-Policy-Cache"], policy_cache.POLICY_CACHE_HIT)
        self.assertEqual(response.json()["products"], [])

    def test_reorder_and_import_helpers_invalidate_bulk_mutations(self):
        with self.captureOnCommitCallbacks(execute=True):
            first = self._create_product("1", 1)
            second = self._create_product("2", 2)
        self._warm_catalog()

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("product_move_up", args=[second.pk]))
        self.assertEqual(response.status_code, 200)
        after_reorder = self._catalog()
        self.assertEqual(
            after_reorder.headers["X-Policy-Cache"],
            policy_cache.POLICY_CACHE_MISS,
        )
        self._warm_catalog()

        csv_file = SimpleUploadedFile(
            "service_goal_reports.csv",
            (
                "Продукт;Цели оказания услуг;Цели оказания услуг в родительном падеже;"
                "Титул отчета/ТКП;Название продукта\n"
                f"{first.short_name};Цель;Цели;Отчет;Продукт\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )
        with self.captureOnCommitCallbacks(execute=True):
            imported = self.client.post(
                reverse("service_goal_report_csv_upload"),
                {"csv_file": csv_file},
            )
        self.assertEqual(imported.status_code, 200)
        self.assertEqual(imported.json()["created"], 1)
        after_import = self._catalog()
        self.assertEqual(
            after_import.headers["X-Policy-Cache"],
            policy_cache.POLICY_CACHE_MISS,
        )

    def test_redis_get_and_set_failures_return_fresh_payload(self):
        backend = caches["policy"]

        with mock.patch.object(
            backend,
            "get",
            side_effect=RedisError("get unavailable"),
        ) as failed_get:
            get_response = self._catalog()
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(
            get_response.headers["X-Policy-Cache"],
            policy_cache.POLICY_CACHE_ERROR,
        )
        self.assertEqual(failed_get.call_count, 1)

        backend.clear()
        backend.set(policy_cache.POLICY_GENERATION_KEY, "stable-generation", timeout=None)
        with mock.patch.object(
            backend,
            "set",
            side_effect=RedisError("set unavailable"),
        ) as failed_set:
            set_response = self._catalog()
        self.assertEqual(set_response.status_code, 200)
        self.assertEqual(
            set_response.headers["X-Policy-Cache"],
            policy_cache.POLICY_CACHE_ERROR,
        )
        self.assertEqual(failed_set.call_count, 1)

    def test_renderer_exception_is_not_hidden_by_fail_open(self):
        request = RequestFactory().get(reverse("policy_filter_catalog"))
        caches["policy"].clear()

        with self.assertRaisesMessage(ValueError, "catalog renderer failed"):
            policy_cache.get_or_build_policy_catalog(
                request,
                lambda: (_ for _ in ()).throw(
                    ValueError("catalog renderer failed")
                ),
            )

    def test_catalog_is_shared_non_personal_and_ignores_page(self):
        with self.captureOnCommitCallbacks(execute=True):
            self._create_product()
        caches["policy"].clear()

        first = self._catalog({"page": "1"})
        first_payload = first.json()
        second_user = get_user_model().objects.create_user(
            username="policy-cache-user-two",
            password="secret123",
        )
        self.client.force_login(second_user)
        second = self._catalog({"page": "999"})

        self.assertEqual(first.headers["X-Policy-Cache"], policy_cache.POLICY_CACHE_MISS)
        self.assertEqual(second.headers["X-Policy-Cache"], policy_cache.POLICY_CACHE_HIT)
        self.assertEqual(first_payload, second.json())
        self.assertEqual(
            policy_cache.normalized_policy_catalog_key("generation"),
            "filter-catalog:v1:generation",
        )

    def test_personalized_tables_do_not_use_catalog_cache(self):
        with mock.patch(
            "policy_app.views.get_or_build_policy_catalog"
        ) as catalog_cache:
            for url_name in (
                "policy_grades_table",
                "policy_specialty_tariffs_table",
                "policy_tariffs_table",
            ):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("X-Policy-Cache", response.headers)
        catalog_cache.assert_not_called()

    def test_policy_alias_is_separate_from_default(self):
        self.assertIsNot(caches["default"], caches["policy"])
        caches["default"].set("shared-key", "default")
        self.assertIsNone(caches["policy"].get("shared-key"))
        self.assertEqual(
            settings.CACHES["policy"]["KEY_PREFIX"],
            "tests:policy",
        )

    def test_performance_command_reports_repeat_summary(self):
        output = io.StringIO()
        caches["policy"].clear()

        call_command(
            "policy_performance",
            username=self.user.username,
            endpoints=["policy_filter_catalog"],
            repeat=3,
            stdout=output,
        )

        payload = json.loads(output.getvalue())
        summary = payload["summary"]["policy_filter_catalog"]
        self.assertEqual(payload["repeat"], 3)
        self.assertEqual(summary["runs"], 3)
        self.assertEqual(summary["cache_statuses"], {"MISS": 1, "HIT": 2})
        self.assertEqual(len(payload["results"]), 3)
        self.assertIn("p50", summary["milliseconds"])
        self.assertIn("p95", summary["milliseconds"])

    @override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            },
            "policy": {
                "BACKEND": "django.core.cache.backends.dummy.DummyCache",
            },
        }
    )
    def test_dummy_backend_reports_bypass(self):
        response = self._catalog()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["X-Policy-Cache"],
            policy_cache.POLICY_CACHE_BYPASS,
        )
