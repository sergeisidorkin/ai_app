from __future__ import annotations

import tempfile
from io import BytesIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from docx import Document

from classifiers_app.models import OKSMCountry, OKVCurrency
from experts_app.models import ExpertProfile, ExpertProfileSpecialty, ExpertSpecialty
from group_app.models import GroupMember, OrgUnit
from policy_app.models import (
    ExpertiseDirection,
    Grade,
    Product,
    ServiceGoalReport,
    SpecialtyTariff,
    Tariff,
    TypicalSection,
    TypicalServiceComposition,
)
from users_app.models import Employee

from .document_generation import get_generated_docx_path
from .forms import ProposalRegistrationForm
from .forms import ProposalVariableForm
from .models import (
    ProposalAsset,
    ProposalCommercialOffer,
    ProposalLegalEntity,
    ProposalObject,
    ProposalRegistration,
    ProposalTemplate,
    ProposalVariable,
)
from .variable_resolver import resolve_variables


@override_settings(MEDIA_URL="/media/")
class ProposalDocumentGenerationTests(TestCase):
    def setUp(self):
        self.temp_media = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_media.cleanup)
        self.override = override_settings(MEDIA_ROOT=self.temp_media.name)
        self.override.enable()
        self.addCleanup(self.override.disable)

        self.user = get_user_model().objects.create_user(
            username="proposal-staff",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)

        self.country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            full_name="Российская Федерация",
            alpha2="RU",
            alpha3="RUS",
            position=1,
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
            service_type="service",
            position=1,
        )
        self.proposal = ProposalRegistration.objects.create(
            number=3333,
            group_member=self.group_member,
            type=self.product,
            name="Приморское",
            year=2026,
            customer='ООО "Приморское"',
            country=self.country,
            identifier="ОГРН",
            registration_number="1174910001683",
        )

        template_doc = Document()
        template_doc.add_paragraph("Заказчик: {{name}}")
        template_doc.add_paragraph("Страна: {{country_full_name}}")
        buffer = BytesIO()
        template_doc.save(buffer)
        buffer.seek(0)

        self.template = ProposalTemplate.objects.create(
            group_member=self.group_member,
            product=self.product,
            sample_name="RU Шаблон ТКП_IMC_DD",
            version="2",
            file=SimpleUploadedFile(
                "proposal-template.docx",
                buffer.getvalue(),
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            position=1,
        )

        ProposalVariable.objects.create(
            key="{{name}}",
            description="Наименование Заказчика",
            source_section="proposals",
            source_table="registry",
            source_column="customer",
            position=1,
        )
        ProposalVariable.objects.create(
            key="{{country_full_name}}",
            description="Наименование страны (полное)",
            source_section="proposals",
            source_table="registry",
            source_column="country_full_name",
            position=2,
        )

    def test_create_documents_generates_docx_and_updates_dispatch_fields(self):
        response = self.client.post(
            reverse("proposal_dispatch_create_documents"),
            {"proposal_ids[]": [self.proposal.pk]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["generated"], 1)

        self.proposal.refresh_from_db()
        self.assertTrue(self.proposal.docx_file_name.endswith(".docx"))
        self.assertEqual(self.proposal.docx_file_link, "")
        self.assertEqual(self.proposal.pdf_file_name, "")
        self.assertEqual(self.proposal.pdf_file_link, "")

        docx_path = Path(self.temp_media.name) / "proposal_documents" / "2026" / self.proposal.short_uid / self.proposal.docx_file_name
        self.assertTrue(docx_path.exists())

        generated_doc = Document(str(docx_path))
        full_text = "\n".join(paragraph.text for paragraph in generated_doc.paragraphs)
        self.assertIn('Заказчик: ООО "Приморское"', full_text)
        self.assertIn("Страна: Российская Федерация", full_text)

        download_response = self.client.get(reverse("proposal_generated_docx_download", args=[self.proposal.pk]))
        self.assertEqual(download_response.status_code, 200)
        self.assertIn("attachment;", download_response["Content-Disposition"])

    def test_generated_docx_download_survives_proposal_metadata_edits(self):
        self.client.post(
            reverse("proposal_dispatch_create_documents"),
            {"proposal_ids[]": [self.proposal.pk]},
        )
        self.proposal.refresh_from_db()
        original_docx_name = self.proposal.docx_file_name

        self.proposal.year = 2027
        self.proposal.number = 4444
        self.proposal.group_member = GroupMember.objects.create(
            short_name="IMC Alt",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
            position=2,
        )
        self.proposal.save()

        resolved_path = get_generated_docx_path(self.proposal)
        self.assertIsNotNone(resolved_path)
        self.assertEqual(resolved_path.name, original_docx_name)

        download_response = self.client.get(reverse("proposal_generated_docx_download", args=[self.proposal.pk]))
        self.assertEqual(download_response.status_code, 200)


class ProposalRegistrationFormTests(TestCase):
    def test_new_form_uses_rub_as_default_currency(self):
        OKVCurrency.objects.create(
            code_numeric="643",
            code_alpha="RUB",
            name="Российский рубль",
            position=1,
        )

        form = ProposalRegistrationForm()

        currency_id = form.fields["currency"].initial
        self.assertIsNotNone(currency_id)
        self.assertEqual(form.fields["currency"].queryset.get(pk=currency_id).code_alpha, "RUB")

    def test_new_form_initializes_single_empty_asset_row(self):
        form = ProposalRegistrationForm()

        self.assertEqual(
            form.fields["assets_payload"].initial,
            '[{"short_name": "", "country_id": "", "country_name": "", "identifier": "", "registration_number": "", "registration_date": ""}]',
        )

    def test_invalid_bound_percent_does_not_raise_during_init(self):
        form = ProposalRegistrationForm(
            data={
                "advance_percent": "abc",
                "preliminary_report_percent": "20",
            }
        )

        self.assertIsNone(form.initial.get("final_report_percent"))
        self.assertFalse(form.is_valid())
        self.assertIn("advance_percent", form.errors)

    def test_proposal_variable_form_accepts_registry_binding(self):
        form = ProposalVariableForm(
            data={
                "key": "{{country}}",
                "description": "Страна",
                "source_section": "proposals",
                "source_table": "registry",
                "source_column": "country",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_asset_owner_copies_customer_when_checkbox_enabled(self):
        country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            full_name="Российская Федерация",
            alpha2="RU",
            alpha3="RUS",
            position=1,
        )
        group_member = GroupMember.objects.create(
            short_name="IMC Montan",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
            position=1,
        )
        product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            service_type="service",
            position=1,
        )

        form = ProposalRegistrationForm(
            data={
                "number": 3333,
                "group_member": group_member.pk,
                "type": product.pk,
                "name": "Тестовое ТКП",
                "kind": ProposalRegistration.ProposalKind.REGULAR,
                "year": 2026,
                "customer": 'ООО "Приморское"',
                "country": country.pk,
                "identifier": "ОГРН",
                "registration_number": "1174910001683",
                "registration_date": "01.04.2026",
                "asset_owner": 'ООО "Другое"',
                "asset_owner_country": "",
                "asset_owner_identifier": "",
                "asset_owner_registration_number": "",
                "asset_owner_registration_date": "",
                "asset_owner_matches_customer": "on",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        proposal = form.save()

        self.assertEqual(proposal.asset_owner, proposal.customer)
        self.assertEqual(proposal.asset_owner_country, proposal.country)
        self.assertEqual(proposal.asset_owner_identifier, proposal.identifier)
        self.assertEqual(proposal.asset_owner_registration_number, proposal.registration_number)
        self.assertEqual(proposal.asset_owner_registration_date, proposal.registration_date)

    def test_service_sections_payload_saves_code_by_selected_service(self):
        group_member = GroupMember.objects.create(
            short_name="IMC Montan",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
            position=1,
        )
        product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            service_type="service",
            position=1,
        )
        TypicalSection.objects.create(
            product=product,
            code="S-101",
            short_name="service-1",
            short_name_ru="Услуга 1",
            name_en="Service 1",
            name_ru="Раздел 1",
            accounting_type="Услуги",
            position=1,
        )

        form = ProposalRegistrationForm(
            data={
                "number": 3333,
                "group_member": group_member.pk,
                "type": product.pk,
                "name": "Тестовое ТКП",
                "kind": ProposalRegistration.ProposalKind.REGULAR,
                "year": 2026,
                "service_sections_payload": '[{"service_name":"Раздел 1","code":""}]',
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        proposal = form.save()

        self.assertEqual(
            proposal.service_sections_json,
            [{"service_name": "Раздел 1", "code": "S-101"}],
        )

    def test_resolve_variables_for_new_registry_columns(self):
        country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            full_name="Российская Федерация",
            alpha2="RU",
            alpha3="RUS",
            position=1,
        )
        group_member = GroupMember.objects.create(
            short_name="IMC Montan",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
            position=1,
        )
        currency = OKVCurrency.objects.create(
            code_numeric="643",
            code_alpha="RUB",
            name="Российский рубль",
            position=1,
        )
        product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            service_type="service",
            position=1,
        )
        proposal = ProposalRegistration.objects.create(
            number=3333,
            group_member=group_member,
            type=product,
            name="Приморское",
            proposal_project_name="Проект Приморское",
            country=country,
            purpose="Проверка актива",
            service_composition="Этап 1\nЭтап 2",
            evaluation_date="2026-04-01",
            service_term_months="4.5",
            preliminary_report_date="2026-04-15",
            final_report_date="2026-05-20",
            report_languages="RU, EN",
            service_cost="1250000.50",
            currency=currency,
            advance_percent="50",
            advance_term_days=5,
            preliminary_report_percent="20",
            preliminary_report_term_days=10,
            final_report_percent="30",
            final_report_term_days=15,
        )
        variables = [
            ProposalVariable(
                key="{{proposal_project_name}}",
                source_section="proposals",
                source_table="registry",
                source_column="proposal_project_name",
            ),
            ProposalVariable(key="{{purpose}}", source_section="proposals", source_table="registry", source_column="purpose"),
            ProposalVariable(
                key="{{service_cost}}",
                source_section="proposals",
                source_table="registry",
                source_column="service_cost",
            ),
            ProposalVariable(
                key="{{evaluation_date}}",
                source_section="proposals",
                source_table="registry",
                source_column="evaluation_date",
            ),
            ProposalVariable(
                key="{{advance_percent}}",
                source_section="proposals",
                source_table="registry",
                source_column="advance_percent",
            ),
            ProposalVariable(
                key="{{currency}}",
                source_section="proposals",
                source_table="registry",
                source_column="currency",
            ),
            ProposalVariable(
                key="{{country}}",
                source_section="proposals",
                source_table="registry",
                source_column="country",
            ),
            ProposalVariable(
                key="{{country_full_name}}",
                source_section="proposals",
                source_table="registry",
                source_column="country_full_name",
            ),
        ]

        replacements, _ = resolve_variables(proposal, variables)

        self.assertEqual(replacements["{{proposal_project_name}}"], "Проект Приморское")
        self.assertEqual(replacements["{{purpose}}"], "Проверка актива")
        self.assertEqual(replacements["{{service_cost}}"], "1\u00a0250\u00a0000,50")
        self.assertEqual(replacements["{{evaluation_date}}"], "01.04.2026")
        self.assertEqual(replacements["{{advance_percent}}"], "50")
        self.assertEqual(replacements["{{currency}}"], "RUB")
        self.assertEqual(replacements["{{country}}"], "Россия")
        self.assertEqual(replacements["{{country_full_name}}"], "Российская Федерация")

    def test_form_saves_assets_from_payload(self):
        country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            full_name="Российская Федерация",
            alpha2="RU",
            alpha3="RUS",
            position=1,
        )
        group_member = GroupMember.objects.create(
            short_name="IMC Montan",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
            position=1,
        )
        product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            service_type="service",
            position=1,
        )

        form = ProposalRegistrationForm(
            data={
                "number": 3333,
                "group_member": group_member.pk,
                "type": product.pk,
                "name": "Тестовое ТКП",
                "kind": ProposalRegistration.ProposalKind.REGULAR,
                "year": 2026,
                "customer": 'ООО "Приморское"',
                "country": country.pk,
                "identifier": "ОГРН",
                "registration_number": "1174910001683",
                "registration_date": "01.04.2026",
                "assets_payload": (
                    '[{"short_name":"ООО \\"Актив\\"","country_id":"%s","identifier":"ОГРН",'
                    '"registration_number":"123","registration_date":"02.04.2026"}]'
                ) % country.pk,
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        proposal = form.save()
        form.save_assets(proposal)

        asset = ProposalAsset.objects.get(proposal=proposal)
        self.assertEqual(asset.short_name, 'ООО "Актив"')
        self.assertEqual(asset.country, country)
        self.assertEqual(asset.identifier, "ОГРН")
        self.assertEqual(asset.registration_number, "123")
        self.assertEqual(asset.registration_date.isoformat(), "2026-04-02")

    def test_form_saves_legal_entities_from_payload(self):
        country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            full_name="Российская Федерация",
            alpha2="RU",
            alpha3="RUS",
            position=1,
        )
        group_member = GroupMember.objects.create(
            short_name="IMC Montan",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
            position=1,
        )
        product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            service_type="service",
            position=1,
        )

        form = ProposalRegistrationForm(
            data={
                "number": 3333,
                "group_member": group_member.pk,
                "type": product.pk,
                "name": "Тестовое ТКП",
                "kind": ProposalRegistration.ProposalKind.REGULAR,
                "year": 2026,
                "customer": 'ООО "Приморское"',
                "country": country.pk,
                "identifier": "ОГРН",
                "registration_number": "1174910001683",
                "registration_date": "01.04.2026",
                "assets_payload": '[{"short_name":"ООО \\"Актив\\""}]',
                "legal_entities_payload": (
                    '[{"asset_short_name":"ООО \\"Актив\\"","short_name":"ООО \\"Юрлицо\\"","country_id":"%s",'
                    '"identifier":"ОГРН","registration_number":"456","registration_date":"03.04.2026"}]'
                ) % country.pk,
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        proposal = form.save()
        form.save_assets(proposal)
        form.save_legal_entities(proposal)

        legal_entity = ProposalLegalEntity.objects.get(proposal=proposal)
        self.assertEqual(legal_entity.asset_short_name, 'ООО "Актив"')
        self.assertEqual(legal_entity.short_name, 'ООО "Юрлицо"')
        self.assertEqual(legal_entity.country, country)
        self.assertEqual(legal_entity.identifier, "ОГРН")
        self.assertEqual(legal_entity.registration_number, "456")
        self.assertEqual(legal_entity.registration_date.isoformat(), "2026-04-03")

    def test_form_saves_objects_from_payload(self):
        country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            full_name="Российская Федерация",
            alpha2="RU",
            alpha3="RUS",
            position=1,
        )
        group_member = GroupMember.objects.create(
            short_name="IMC Montan",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
            position=1,
        )
        product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            service_type="service",
            position=1,
        )

        form = ProposalRegistrationForm(
            data={
                "number": 3333,
                "group_member": group_member.pk,
                "type": product.pk,
                "name": "Тестовое ТКП",
                "kind": ProposalRegistration.ProposalKind.REGULAR,
                "year": 2026,
                "customer": 'ООО "Приморское"',
                "country": country.pk,
                "identifier": "ОГРН",
                "registration_number": "1174910001683",
                "registration_date": "01.04.2026",
                "assets_payload": '[{"short_name":"ООО \\"Актив\\""}]',
                "legal_entities_payload": '[{"asset_short_name":"ООО \\"Актив\\"","short_name":"ООО \\"Юрлицо\\""}]',
                "objects_payload": (
                    '[{"legal_entity_short_name":"ООО \\"Юрлицо\\"","short_name":"Объект 1","region":"Россия",'
                    '"object_type":"ОГРН","license":"Лицензия 123","registration_date":"04.04.2026"}]'
                ),
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        proposal = form.save()
        form.save_assets(proposal)
        form.save_legal_entities(proposal)
        form.save_objects(proposal)

        proposal_object = ProposalObject.objects.get(proposal=proposal)
        self.assertEqual(proposal_object.legal_entity_short_name, 'ООО "Юрлицо"')
        self.assertEqual(proposal_object.short_name, "Объект 1")
        self.assertEqual(proposal_object.region, "Россия")
        self.assertEqual(proposal_object.object_type, "ОГРН")
        self.assertEqual(proposal_object.license, "Лицензия 123")
        self.assertEqual(proposal_object.registration_date.isoformat(), "2026-04-04")

    def test_form_saves_commercial_offer_from_payload(self):
        country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            full_name="Российская Федерация",
            alpha2="RU",
            alpha3="RUS",
            position=1,
        )
        group_member = GroupMember.objects.create(
            short_name="IMC Montan",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
            position=1,
        )
        product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            service_type="service",
            position=1,
        )

        form = ProposalRegistrationForm(
            data={
                "number": 3333,
                "group_member": group_member.pk,
                "type": product.pk,
                "name": "Тестовое ТКП",
                "kind": ProposalRegistration.ProposalKind.REGULAR,
                "year": 2026,
                "customer": 'ООО "Приморское"',
                "country": country.pk,
                "identifier": "ОГРН",
                "registration_number": "1174910001683",
                "registration_date": "01.04.2026",
                "commercial_offer_payload": (
                    '[{"specialist":"Иванов","job_title":"Партнер","professional_status":"ACCA","service_name":"Финансы",'
                    '"rate_eur_per_day":"1200.50","asset_day_counts":["2","3"],'
                    '"total_eur_without_vat":"6002.50"}]'
                ),
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        proposal = form.save()
        form.save_commercial_offers(proposal)

        offer = ProposalCommercialOffer.objects.get(proposal=proposal)
        self.assertEqual(offer.specialist, "Иванов")
        self.assertEqual(offer.job_title, "Партнер")
        self.assertEqual(offer.professional_status, "ACCA")
        self.assertEqual(offer.service_name, "Финансы")
        self.assertEqual(str(offer.rate_eur_per_day), "1200.50")
        self.assertEqual(offer.asset_day_counts, [2, 3])
        self.assertEqual(str(offer.total_eur_without_vat), "6002.50")


class ProposalFormContextTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="proposal-context-staff",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.group_member = GroupMember.objects.create(
            short_name="IMC Montan",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
            position=1,
        )

    def _create_staff_employee(self, *, username, first_name, last_name, patronymic="", department=None, role=""):
        user = get_user_model().objects.create_user(
            username=username,
            password="secret",
            first_name=first_name,
            last_name=last_name,
            is_staff=True,
        )
        employee = Employee.objects.create(
            user=user,
            patronymic=patronymic,
            department=department,
            role=role,
        )
        return user, employee

    def test_typical_sections_json_prefers_highest_grade_within_best_rank(self):
        product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            service_type="service",
            position=1,
        )
        section = TypicalSection.objects.create(
            product=product,
            code="FIN",
            short_name="FIN",
            name_en="Finance",
            name_ru="Финансы",
            executor="Партнер",
            position=1,
        )
        specialty = ExpertSpecialty.objects.create(specialty="Партнер", position=1)
        grade_low = Grade.objects.create(
            grade_en="G1",
            grade_ru="G1",
            qualification=1,
            qualification_levels=5,
            created_by=self.user,
            position=1,
        )
        grade_high = Grade.objects.create(
            grade_en="G3",
            grade_ru="G3",
            qualification=3,
            qualification_levels=5,
            created_by=self.user,
            position=2,
        )
        grade_top_other_rank = Grade.objects.create(
            grade_en="G5",
            grade_ru="G5",
            qualification=5,
            qualification_levels=5,
            created_by=self.user,
            position=3,
        )

        _, employee_low = self._create_staff_employee(
            username="candidate-low",
            first_name="Иван",
            last_name="Петров",
        )
        profile_low = ExpertProfile.objects.create(
            employee=employee_low,
            professional_status="ACCA",
            grade=grade_low,
            position=1,
        )
        ExpertProfileSpecialty.objects.create(profile=profile_low, specialty=specialty, rank=1)

        _, employee_high = self._create_staff_employee(
            username="candidate-high",
            first_name="Анна",
            last_name="Сидорова",
        )
        profile_high = ExpertProfile.objects.create(
            employee=employee_high,
            professional_status="CFA",
            grade=grade_high,
            position=2,
        )
        ExpertProfileSpecialty.objects.create(profile=profile_high, specialty=specialty, rank=1)

        _, employee_other_rank = self._create_staff_employee(
            username="candidate-rank-two",
            first_name="Петр",
            last_name="Иванов",
        )
        profile_other_rank = ExpertProfile.objects.create(
            employee=employee_other_rank,
            professional_status="FRM",
            grade=grade_top_other_rank,
            position=3,
        )
        ExpertProfileSpecialty.objects.create(profile=profile_other_rank, specialty=specialty, rank=2)

        response = self.client.get(reverse("proposal_form_create"))

        self.assertEqual(response.status_code, 200)
        entries = response.context["typical_sections_json"][str(product.pk)]
        finance_entry = next(item for item in entries if item["name"] == section.name_ru)
        self.assertEqual(finance_entry["default_specialist"], "Анна Сидорова")
        self.assertEqual(finance_entry["default_professional_status"], "CFA")
        self.assertEqual(
            [item["name"] for item in finance_entry["specialist_options"]],
            ["Анна Сидорова", "Иван Петров", "Петр Иванов"],
        )

    def test_typical_sections_json_uses_direction_head_for_special_expertise_sections(self):
        product = Product.objects.create(
            short_name="VAL",
            name_en="Valuation",
            name_ru="Оценка",
            service_type="service",
            position=2,
        )
        expertise = ExpertiseDirection.objects.create(
            name="Финансовая экспертиза",
            short_name="FIN",
            position=1,
        )
        direction = OrgUnit.objects.create(
            company=self.group_member,
            department_name="Финансовое направление",
            short_name="Финансы",
            expertise=expertise,
            unit_type="expertise",
            position=1,
        )
        section = TypicalSection.objects.create(
            product=product,
            code="VAL",
            short_name="VAL",
            name_en="Valuation",
            name_ru="Оценка бизнеса",
            executor="Оценщик",
            expertise_dir=expertise,
            expertise_direction=direction,
            position=1,
        )
        specialty = ExpertSpecialty.objects.create(specialty="Оценщик", position=2)
        _, employee_candidate = self._create_staff_employee(
            username="valuation-candidate",
            first_name="Мария",
            last_name="Экспертова",
        )
        profile_candidate = ExpertProfile.objects.create(
            employee=employee_candidate,
            professional_status="ASA",
            position=4,
        )
        ExpertProfileSpecialty.objects.create(profile=profile_candidate, specialty=specialty, rank=1)

        _, employee_head = self._create_staff_employee(
            username="direction-head",
            first_name="Олег",
            last_name="Руководитель",
            department=direction,
            role="Руководитель направления",
        )
        ExpertProfile.objects.create(
            employee=employee_head,
            professional_status="CPA",
            position=5,
        )

        response = self.client.get(reverse("proposal_form_create"))

        self.assertEqual(response.status_code, 200)
        entries = response.context["typical_sections_json"][str(product.pk)]
        section_entry = next(item for item in entries if item["name"] == section.name_ru)
        self.assertEqual(section_entry["default_specialist"], "Олег Руководитель")
        self.assertEqual(section_entry["default_professional_status"], "CPA")
        self.assertEqual(section_entry["specialist_options"][0]["name"], "Олег Руководитель")

    def test_typical_sections_json_includes_commercial_rate_and_days_autofill_data(self):
        product = Product.objects.create(
            short_name="TAX",
            name_en="Tax",
            name_ru="Налоги",
            service_type="service",
            position=5,
        )
        section = TypicalSection.objects.create(
            product=product,
            code="TX-1",
            short_name="tax-1",
            short_name_ru="Налог 1",
            name_en="Tax Service",
            name_ru="Налоговый анализ",
            executor="Партнер",
            position=1,
        )
        specialty = ExpertSpecialty.objects.create(
            specialty="Партнер",
            position=1,
        )
        grade = Grade.objects.create(
            grade_en="G2",
            grade_ru="G2",
            qualification=2,
            qualification_levels=5,
            base_rate_share=25,
            created_by=self.user,
            position=10,
        )
        _, employee = self._create_staff_employee(
            username="commercial-rate-candidate",
            first_name="Ирина",
            last_name="Смирнова",
        )
        profile = ExpertProfile.objects.create(
            employee=employee,
            professional_status="ACCA",
            grade=grade,
            position=10,
        )
        ExpertProfileSpecialty.objects.create(profile=profile, specialty=specialty, rank=1)
        SpecialtyTariff.objects.create(
            specialty_group="Партнеры",
            daily_rate_tkp_eur="1000.00",
            position=1,
        ).specialties.set([specialty])
        Tariff.objects.create(
            product=product,
            section=section,
            base_rate_vpm="1.00",
            service_hours=8,
            service_days_tkp=7,
            created_by=self.user,
            position=1,
        )

        response = self.client.get(reverse("proposal_form_create"))

        self.assertEqual(response.status_code, 200)
        entry = response.context["typical_sections_json"][str(product.pk)][0]
        self.assertEqual(entry["specialty_tariff_rate_eur"], "1000.00")
        self.assertEqual(entry["service_days_tkp"], 7)
        self.assertTrue(entry["specialty_is_director"])
        self.assertEqual(entry["default_base_rate_share"], 25)
        self.assertEqual(entry["specialist_options"][0]["base_rate_share"], 25)

    def test_service_goal_reports_json_exposes_first_product_defaults(self):
        product = Product.objects.create(
            short_name="COM",
            name_en="Commercial Offer",
            name_ru="Коммерческое предложение",
            service_type="service",
            position=3,
        )
        ServiceGoalReport.objects.create(
            product=product,
            service_goal="Подготовка коммерческого предложения",
            report_title="ТКП по проекту COM",
            position=2,
        )
        ServiceGoalReport.objects.create(
            product=product,
            service_goal="Не должно попасть в автозаполнение",
            report_title="Не использовать",
            position=3,
        )

        response = self.client.get(reverse("proposal_form_create"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["service_goal_reports_json"][str(product.pk)],
            {
                "report_title": "ТКП по проекту COM",
                "service_goal": "Подготовка коммерческого предложения",
            },
        )

    def test_typical_service_compositions_json_exposes_text_by_product_and_section(self):
        product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            service_type="service",
            position=4,
        )
        section = TypicalSection.objects.create(
            product=product,
            code="S-101",
            short_name="service-1",
            short_name_ru="Услуга 1",
            name_en="Service 1",
            name_ru="Раздел 1",
            accounting_type="Услуги",
            position=1,
        )
        TypicalServiceComposition.objects.create(
            product=product,
            section=section,
            service_composition="Этап 1\nЭтап 2",
            position=1,
        )

        response = self.client.get(reverse("proposal_form_create"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["typical_service_compositions_json"][str(product.pk)],
            [
                {
                    "code": "S-101",
                    "service_name": "Раздел 1",
                    "service_composition": "Этап 1\nЭтап 2",
                }
            ],
        )

    def test_proposal_form_renders_composite_project_name_inputs(self):
        response = self.client.get(reverse("proposal_form_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="proposal-project-name-prefix"', html=False)
        self.assertContains(response, 'id="proposal-project-name-suffix"', html=False)
        self.assertContains(response, 'type="hidden" name="proposal_project_name"', html=False)
        self.assertContains(response, 'id="proposal-purpose-prefix"', html=False)
        self.assertContains(response, 'id="proposal-purpose-suffix"', html=False)
        self.assertContains(response, 'type="hidden" name="purpose"', html=False)


class ProposalAccessTests(TestCase):
    def test_proposals_partial_requires_staff(self):
        user = get_user_model().objects.create_user(
            username="proposal-nonstaff",
            password="secret",
            is_staff=False,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("proposals_partial"))

        self.assertEqual(response.status_code, 302)
