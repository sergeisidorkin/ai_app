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
from group_app.models import GroupMember
from policy_app.models import Product

from .forms import ProposalRegistrationForm
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
