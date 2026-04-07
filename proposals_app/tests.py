from __future__ import annotations

import json
import tempfile
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from docx import Document

from classifiers_app.models import BusinessEntityRecord, OKSMCountry, OKVCurrency
from core.models import CloudStorageSettings
from experts_app.models import ExpertProfile, ExpertProfileSpecialty, ExpertSpecialty
from group_app.models import GroupMember, OrgUnit
from letters_app.models import LetterTemplate
from nextcloud_app.api import NextcloudShare
from nextcloud_app.models import NextcloudUserLink
from policy_app.models import (
    ExpertiseDirection,
    Grade,
    Product,
    ServiceGoalReport,
    SpecialtyTariff,
    Tariff,
    TypicalSection,
    TypicalSectionSpecialty,
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
from .views import PROPOSAL_NEXTCLOUD_TARGETS_SESSION_KEY
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


@override_settings(ROOT_URLCONF="proposals_app.urls")
class ProposalDispatchSendTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="proposal-dispatch-staff",
            email="staff@example.com",
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
        self.product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            service_type="service",
            position=1,
        )
        LetterTemplate.objects.update_or_create(
            template_type="proposal_sending",
            user=None,
            defaults={
                "subject_template": "Технико-коммерческое предложение IMC Montan {{tkp_id}}",
                "body_html": "<p>Направляем проект ТКП {{tkp_id}}</p>",
                "is_default": True,
            },
        )
        self.successful_proposal = ProposalRegistration.objects.create(
            number=3333,
            group_member=self.group_member,
            type=self.product,
            name="Приморское",
            year=2026,
            contact_email="recipient@example.com",
        )
        self.failed_proposal = ProposalRegistration.objects.create(
            number=3334,
            group_member=self.group_member,
            type=self.product,
            name="Балтика",
            year=2026,
            contact_email="",
        )

    @patch("ai_app.proposals_app.services.send_notification_email")
    def test_dispatch_send_updates_only_successfully_sent_rows(self, mocked_send_notification_email):
        mocked_send_notification_email.return_value = {
            "recipient_email": "recipient@example.com",
            "subject": "ignored",
            "is_html": True,
        }

        response = self.client.post(
            reverse("proposal_dispatch_send"),
            {
                "proposal_ids[]": [self.successful_proposal.pk, self.failed_proposal.pk],
                "delivery_channels[]": ["system_email"],
                "sent_at": "2026-04-04T12:30",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["updated"], 1)
        self.assertEqual(payload["email_delivery"]["sent"], 1)
        self.assertEqual(payload["email_delivery"]["failed"], 1)
        self.assertEqual(mocked_send_notification_email.call_count, 1)

        call_kwargs = mocked_send_notification_email.call_args.kwargs
        expected_tkp_id = " ".join(
            [
                self.successful_proposal.short_uid,
                self.product.short_name,
                self.successful_proposal.name,
            ]
        )
        self.assertEqual(
            call_kwargs["subject"],
            f"Технико-коммерческое предложение IMC Montan {expected_tkp_id}",
        )
        self.assertEqual(
            call_kwargs["content"],
            f"<p>Направляем проект ТКП {expected_tkp_id}</p>",
        )

        self.successful_proposal.refresh_from_db()
        self.failed_proposal.refresh_from_db()
        self.assertEqual(self.successful_proposal.sent_date, "04.04.2026 12:30")
        self.assertEqual(self.failed_proposal.sent_date, "")

    @patch("ai_app.proposals_app.services.send_notification_email")
    @patch(
        "ai_app.proposals_app.services.get_user_notification_email_options",
        return_value={},
    )
    def test_dispatch_send_marks_row_sent_when_at_least_one_channel_succeeds(
        self,
        _mocked_email_options,
        mocked_send_notification_email,
    ):
        mocked_send_notification_email.return_value = {
            "recipient_email": "recipient@example.com",
            "subject": "ignored",
            "is_html": True,
        }

        response = self.client.post(
            reverse("proposal_dispatch_send"),
            {
                "proposal_ids[]": [self.successful_proposal.pk],
                "delivery_channels[]": ["system_email", "connected_email"],
                "sent_at": "2026-04-04T12:30",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["updated"], 1)
        self.assertEqual(payload["email_delivery"]["sent"], 1)
        self.assertEqual(payload["email_delivery"]["failed"], 1)
        self.assertEqual(
            payload["email_delivery"]["channels"]["connected_email"]["errors"][0]["error"],
            "У отправителя не настроен активный внешний SMTP-аккаунт.",
        )
        self.assertEqual(mocked_send_notification_email.call_count, 1)
        self.successful_proposal.refresh_from_db()
        self.assertEqual(self.successful_proposal.sent_date, "04.04.2026 12:30")

    @patch("ai_app.proposals_app.services.send_notification_email")
    def test_dispatch_send_uses_rendered_fallback_subject_when_template_subject_empty(self, mocked_send_notification_email):
        mocked_send_notification_email.return_value = {
            "recipient_email": "recipient@example.com",
            "subject": "ignored",
            "is_html": True,
        }
        LetterTemplate.objects.filter(
            template_type="proposal_sending",
            user__isnull=True,
        ).update(
            subject_template="",
            body_html="<p>Направляем проект ТКП {{tkp_id}}</p>",
        )

        response = self.client.post(
            reverse("proposal_dispatch_send"),
            {
                "proposal_ids[]": [self.successful_proposal.pk],
                "delivery_channels[]": ["system_email"],
                "sent_at": "2026-04-04T12:30",
            },
        )

        self.assertEqual(response.status_code, 200)
        call_kwargs = mocked_send_notification_email.call_args.kwargs
        expected_tkp_id = " ".join(
            [
                self.successful_proposal.short_uid,
                self.product.short_name,
                self.successful_proposal.name,
            ]
        )
        self.assertEqual(
            call_kwargs["subject"],
            f"Технико-коммерческое предложение IMC Montan {expected_tkp_id}",
        )

    @patch("ai_app.proposals_app.services.send_notification_email")
    @patch("ai_app.proposals_app.services.get_user_notification_email_options", return_value={})
    def test_dispatch_send_returns_error_when_connected_email_unavailable(
        self,
        _mocked_email_options,
        mocked_send_notification_email,
    ):
        response = self.client.post(
            reverse("proposal_dispatch_send"),
            {
                "proposal_ids[]": [self.successful_proposal.pk],
                "delivery_channels[]": ["connected_email"],
                "sent_at": "2026-04-04T12:30",
            },
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "Не удалось отправить ни одного письма.")
        self.assertEqual(payload["email_delivery"]["failed"], 1)
        self.assertEqual(
            payload["email_delivery"]["channels"]["connected_email"]["errors"][0]["error"],
            "У отправителя не настроен активный внешний SMTP-аккаунт.",
        )
        mocked_send_notification_email.assert_not_called()
        self.successful_proposal.refresh_from_db()
        self.assertEqual(self.successful_proposal.sent_date, "")


class ProposalRegistrationFormTests(TestCase):
    def _base_form_payload(self, **overrides):
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
        payload = {
            "number": 3333,
            "group_member": group_member.pk,
            "type": product.pk,
            "name": "Тестовое ТКП",
            "kind": ProposalRegistration.ProposalKind.REGULAR,
            "status": ProposalRegistration.ProposalStatus.FINAL,
            "year": 2026,
        }
        payload.update(overrides)
        return payload

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

    def test_form_preserves_explicit_autocomplete_flags_in_related_payload(self):
        country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            full_name="Российская Федерация",
            alpha2="RU",
            alpha3="RUS",
            position=1,
        )
        form = ProposalRegistrationForm(
            data=self._base_form_payload(
                assets_payload=json.dumps(
                    [
                        {
                            "short_name": 'ООО "Актив"',
                            "country_id": str(country.pk),
                            "country_name": "Россия",
                            "identifier": "ОГРН",
                            "registration_number": "1234567890",
                            "registration_date": "01.04.2026",
                            "selected_identifier_record_id": "55",
                            "selected_from_autocomplete": True,
                        }
                    ],
                    ensure_ascii=False,
                )
            )
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_assets[0]["selected_identifier_record_id"], "55")
        self.assertTrue(form.cleaned_assets[0]["selected_from_autocomplete"])

    @patch("proposals_app.forms.get_cbr_eur_rate_for_today")
    def test_new_form_prefills_cbr_exchange_rate_in_commercial_totals(self, mocked_rate):
        mocked_rate.return_value = Decimal("96.5432")

        form = ProposalRegistrationForm()

        self.assertEqual(
            json.loads(form.fields["commercial_totals_payload"].initial),
            {
                "discount_percent": "5",
                "rub_total_service_text": f"Курс евро Банка России на {timezone.localdate().strftime('%d.%m.%Y')}:",
                "discounted_total_service_text": "Размер скидки:",
                "exchange_rate": "96.5432",
            },
        )

    @patch("proposals_app.forms.get_cbr_eur_rate_for_today")
    def test_existing_form_keeps_stored_exchange_rate_in_commercial_totals(self, mocked_rate):
        mocked_rate.return_value = Decimal("101.1111")
        group_member = GroupMember.objects.create(
            short_name="IMC Montan",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
            position=1,
        )
        product = Product.objects.create(
            short_name="FIX",
            name_en="Fixed rate",
            name_ru="Фиксированный курс",
            service_type="service",
            position=1,
        )
        proposal = ProposalRegistration.objects.create(
            number=3333,
            group_member=group_member,
            type=product,
            name="Историческое ТКП",
            kind=ProposalRegistration.ProposalKind.REGULAR,
            status=ProposalRegistration.ProposalStatus.FINAL,
            year=2026,
            customer='ООО "История"',
            commercial_totals_json={
                "exchange_rate": "95.4321",
                "discount_percent": "0",
            },
        )

        form = ProposalRegistrationForm(instance=proposal)

        self.assertEqual(
            json.loads(form.fields["commercial_totals_payload"].initial)["exchange_rate"],
            "95.4321",
        )

    @patch("proposals_app.forms.get_cbr_eur_rate_for_today")
    def test_existing_form_keeps_stored_exchange_rate_label_text(self, mocked_rate):
        mocked_rate.return_value = Decimal("101.1111")
        group_member = GroupMember.objects.create(
            short_name="IMC Montan",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
            position=1,
        )
        product = Product.objects.create(
            short_name="FIXTXT",
            name_en="Fixed text",
            name_ru="Фиксированный текст",
            service_type="service",
            position=1,
        )
        proposal = ProposalRegistration.objects.create(
            number=3334,
            group_member=group_member,
            type=product,
            name="Исторический текст курса",
            kind=ProposalRegistration.ProposalKind.REGULAR,
            status=ProposalRegistration.ProposalStatus.FINAL,
            year=2026,
            customer='ООО "История"',
            commercial_totals_json={
                "exchange_rate": "95.4321",
                "discount_percent": "0",
                "rub_total_service_text": "Курс евро Банка России на 15.01.2026:",
            },
        )

        form = ProposalRegistrationForm(instance=proposal)

        self.assertEqual(
            json.loads(form.fields["commercial_totals_payload"].initial)["rub_total_service_text"],
            "Курс евро Банка России на 15.01.2026:",
        )

    @patch("proposals_app.forms.get_cbr_eur_rate_for_today")
    def test_existing_form_does_not_autofill_missing_exchange_rate(self, mocked_rate):
        mocked_rate.return_value = Decimal("101.1111")
        group_member = GroupMember.objects.create(
            short_name="IMC Montan",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
            position=1,
        )
        product = Product.objects.create(
            short_name="FIXBLANK",
            name_en="Blank rate",
            name_ru="Пустой курс",
            service_type="service",
            position=1,
        )
        proposal = ProposalRegistration.objects.create(
            number=3335,
            group_member=group_member,
            type=product,
            name="Пустой курс",
            kind=ProposalRegistration.ProposalKind.REGULAR,
            status=ProposalRegistration.ProposalStatus.FINAL,
            year=2026,
            customer='ООО "История"',
            commercial_totals_json={
                "exchange_rate": "",
                "discount_percent": "0",
                "rub_total_service_text": "Курс евро Банка России на 15.01.2026:",
            },
        )

        form = ProposalRegistrationForm(instance=proposal)

        self.assertEqual(
            json.loads(form.fields["commercial_totals_payload"].initial)["exchange_rate"],
            "",
        )

    def test_new_form_defaults_report_languages_to_russian(self):
        form = ProposalRegistrationForm()

        self.assertEqual(form.initial["report_languages"], "русский")

    def test_new_form_defaults_status_to_final(self):
        form = ProposalRegistrationForm()

        self.assertEqual(form.fields["status"].initial, ProposalRegistration.ProposalStatus.FINAL)

    def test_new_form_requires_year(self):
        form = ProposalRegistrationForm()

        self.assertTrue(form.fields["year"].required)

    def test_form_requires_name(self):
        form = ProposalRegistrationForm()

        self.assertTrue(form.fields["name"].required)

    def test_form_uses_russian_required_error_for_required_fields(self):
        form = ProposalRegistrationForm(data={})

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["type"][0], "Обязательное поле.")

    def test_form_uses_russian_integer_error_message(self):
        form = ProposalRegistrationForm(data=self._base_form_payload(number="abc"))

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["number"][0], "Введите целое число.")

    def test_form_uses_russian_date_error_message(self):
        form = ProposalRegistrationForm(data=self._base_form_payload(registration_date="not-a-date"))

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["registration_date"][0], "Введите дату в формате ДД.ММ.ГГГГ.")

    def test_form_uses_russian_choice_error_message(self):
        form = ProposalRegistrationForm(data=self._base_form_payload(kind="unknown"))

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["kind"][0], "Выберите корректное значение.")

    def test_form_renders_non_editable_statuses_as_disabled_options(self):
        form = ProposalRegistrationForm()
        choices = form.fields["status"].widget.optgroups("status", [])
        options = [option for _group_name, group_options, _index in choices for option in group_options]
        option_by_value = {str(option["value"]): option for option in options if option.get("value") is not None}

        self.assertEqual(option_by_value["sent"]["label"], "Отправленное")
        self.assertEqual(option_by_value["completed"]["label"], "Завершённое")
        self.assertTrue(option_by_value["sent"]["attrs"].get("disabled"))
        self.assertTrue(option_by_value["completed"]["attrs"].get("disabled"))

    def test_form_rejects_manual_selection_of_non_editable_status(self):
        form = ProposalRegistrationForm(
            data=self._base_form_payload(status=ProposalRegistration.ProposalStatus.SENT)
        )

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["status"][0], "Выберите корректное значение.")

    def test_existing_form_allows_empty_year(self):
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
        proposal = ProposalRegistration.objects.create(
            number=3333,
            group_member=group_member,
            type=product,
            name="Тестовое ТКП",
            year=None,
        )

        form = ProposalRegistrationForm(instance=proposal)

        self.assertFalse(form.fields["year"].required)

    def test_new_form_defaults_percent_fields_to_40_with_integer_step(self):
        form = ProposalRegistrationForm()

        self.assertEqual(form.fields["advance_percent"].initial, 40)
        self.assertEqual(form.fields["preliminary_report_percent"].initial, 40)
        self.assertEqual(form.fields["advance_term_days"].initial, 10)
        self.assertEqual(form.fields["preliminary_report_term_days"].initial, 7)
        self.assertEqual(form.fields["final_report_term_days"].initial, 15)
        self.assertEqual(form.fields["advance_percent"].widget.attrs["step"], "1")
        self.assertEqual(form.fields["preliminary_report_percent"].widget.attrs["step"], "1")

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

    def test_report_languages_normalizes_legacy_codes(self):
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
                "status": ProposalRegistration.ProposalStatus.FINAL,
                "year": 2026,
                "report_languages": "RU, EN, zh",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["report_languages"], "русский, английский, китайский")

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
                "status": ProposalRegistration.ProposalStatus.FINAL,
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

    def test_customer_tz_mode_keeps_service_composition_in_sync(self):
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
                "status": ProposalRegistration.ProposalStatus.FINAL,
                "year": 2026,
                "customer": 'ООО "Приморское"',
                "country": country.pk,
                "identifier": "ОГРН",
                "registration_number": "1174910001683",
                "registration_date": "01.04.2026",
                "service_composition": "Старый текст разделов",
                "service_composition_customer_tz": "Новый текст ТЗ заказчика",
                "service_composition_mode": "customer_tz",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        proposal = form.save()

        self.assertEqual(proposal.service_composition_mode, "customer_tz")
        self.assertEqual(proposal.service_composition_customer_tz, "Новый текст ТЗ заказчика")
        self.assertEqual(proposal.service_composition, "Новый текст ТЗ заказчика")

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
                "status": ProposalRegistration.ProposalStatus.FINAL,
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
            status=ProposalRegistration.ProposalStatus.PRELIMINARY,
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
                key="{{status}}",
                source_section="proposals",
                source_table="registry",
                source_column="status",
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
        self.assertEqual(replacements["{{status}}"], "Предварительное")
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
                "status": ProposalRegistration.ProposalStatus.FINAL,
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
                "status": ProposalRegistration.ProposalStatus.FINAL,
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

    def test_form_allows_legal_entity_without_short_name(self):
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
                "status": ProposalRegistration.ProposalStatus.FINAL,
                "year": 2026,
                "assets_payload": '[{"short_name":"ООО \\"Актив\\""}]',
                "legal_entities_payload": '[{"asset_short_name":"ООО \\"Актив\\"","short_name":"","identifier":"ОГРН"}]',
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        proposal = form.save()
        form.save_assets(proposal)
        form.save_legal_entities(proposal)

        legal_entity = ProposalLegalEntity.objects.get(proposal=proposal)
        self.assertEqual(legal_entity.asset_short_name, 'ООО "Актив"')
        self.assertEqual(legal_entity.short_name, "")
        self.assertEqual(legal_entity.identifier, "ОГРН")

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
                "status": ProposalRegistration.ProposalStatus.FINAL,
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
                "status": ProposalRegistration.ProposalStatus.FINAL,
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

    def test_form_saves_commercial_totals_payload(self):
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
                "status": ProposalRegistration.ProposalStatus.FINAL,
                "year": 2026,
                "customer": 'ООО "Приморское"',
                "country": country.pk,
                "identifier": "ОГРН",
                "registration_number": "1174910001683",
                "registration_date": "01.04.2026",
                "commercial_totals_payload": (
                    '{"exchange_rate":"96.50","discount_percent":"7.50",'
                    '"contract_total":"1200000","contract_total_auto":"1300000",'
                    '"rub_total_service_text":"Курс ЦБ","discounted_total_service_text":"Скидка проекта"}'
                ),
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        proposal = form.save()

        self.assertEqual(
            proposal.commercial_totals_json,
            {
                "exchange_rate": "96.50",
                "discount_percent": "7.50",
                "contract_total": "1200000",
                "contract_total_auto": "1300000",
                "rub_total_service_text": "Курс ЦБ",
                "discounted_total_service_text": "Скидка проекта",
            },
        )

    def test_form_preserves_zero_values_in_commercial_totals_payload(self):
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
            short_name="ZERO",
            name_en="Zero values",
            name_ru="Нулевые значения",
            service_type="service",
            position=1,
        )

        form = ProposalRegistrationForm(
            data={
                "number": 3333,
                "group_member": group_member.pk,
                "type": product.pk,
                "name": "ТКП с нулями",
                "kind": ProposalRegistration.ProposalKind.REGULAR,
                "status": ProposalRegistration.ProposalStatus.FINAL,
                "year": 2026,
                "customer": 'ООО "Ноль"',
                "country": country.pk,
                "identifier": "ОГРН",
                "registration_number": "1174910001683",
                "registration_date": "01.04.2026",
                "commercial_totals_payload": (
                    '{"exchange_rate":"0","discount_percent":"0",'
                    '"contract_total":"0","contract_total_auto":"0",'
                    '"rub_total_service_text":"Курс ЦБ","discounted_total_service_text":"Скидка проекта"}'
                ),
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        proposal = form.save()

        self.assertEqual(
            proposal.commercial_totals_json,
            {
                "exchange_rate": "0",
                "discount_percent": "0",
                "contract_total": "0",
                "contract_total_auto": "0",
                "rub_total_service_text": "Курс ЦБ",
                "discounted_total_service_text": "Скидка проекта",
            },
        )


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
            position=1,
        )
        specialty = ExpertSpecialty.objects.create(specialty="Партнер", position=1)
        TypicalSectionSpecialty.objects.create(section=section, specialty=specialty, rank=1)
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
            professional_status="Association of Chartered Certified Accountants",
            professional_status_short="ACCA",
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
            professional_status="Chartered Financial Analyst",
            professional_status_short="CFA",
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
            professional_status="Financial Risk Manager",
            professional_status_short="FRM",
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

    def test_typical_sections_json_uses_ranked_section_specialties_for_executor_payload(self):
        product = Product.objects.create(
            short_name="CUR",
            name_en="Current specialties",
            name_ru="Актуальные специальности",
            service_type="service",
            position=1,
        )
        section = TypicalSection.objects.create(
            product=product,
            code="CUR-1",
            short_name="CUR-1",
            name_en="Current section",
            name_ru="Актуальный раздел",
            position=1,
        )
        specialty = ExpertSpecialty.objects.create(specialty="Новая специальность", position=1)
        TypicalSectionSpecialty.objects.create(section=section, specialty=specialty, rank=1)
        grade = Grade.objects.create(
            grade_en="G2",
            grade_ru="G2",
            qualification=2,
            qualification_levels=5,
            created_by=self.user,
            position=1,
        )
        _, employee = self._create_staff_employee(
            username="current-specialty-candidate",
            first_name="Елена",
            last_name="Экспертова",
        )
        profile = ExpertProfile.objects.create(
            employee=employee,
            professional_status="ACCA",
            grade=grade,
            position=1,
        )
        ExpertProfileSpecialty.objects.create(profile=profile, specialty=specialty, rank=1)

        response = self.client.get(reverse("proposal_form_create"))

        self.assertEqual(response.status_code, 200)
        entries = response.context["typical_sections_json"][str(product.pk)]
        section_entry = next(item for item in entries if item["name"] == section.name_ru)
        self.assertEqual(section_entry["executor"], "Новая специальность")
        self.assertEqual(section_entry["default_specialist"], "Елена Экспертова")

    def test_typical_sections_json_marks_sections_excluded_from_tkp_autofill(self):
        product = Product.objects.create(
            short_name="TKP",
            name_en="TKP product",
            name_ru="ТКП продукт",
            service_type="service",
            position=1,
        )
        TypicalSection.objects.create(
            product=product,
            code="IN",
            short_name="IN",
            name_en="Included",
            name_ru="Включенный раздел",
            position=1,
        )
        TypicalSection.objects.create(
            product=product,
            code="OUT",
            short_name="OUT",
            name_en="Excluded",
            name_ru="Исключенный раздел",
            exclude_from_tkp_autofill=True,
            position=2,
        )

        response = self.client.get(reverse("proposal_form_create"))

        self.assertEqual(response.status_code, 200)
        entries = response.context["typical_sections_json"][str(product.pk)]
        self.assertEqual(
            [item["name"] for item in entries],
            ["Включенный раздел", "Исключенный раздел"],
        )
        excluded_entry = next(item for item in entries if item["name"] == "Исключенный раздел")
        self.assertTrue(excluded_entry["exclude_from_tkp_autofill"])
        included_entry = next(item for item in entries if item["name"] == "Включенный раздел")
        self.assertFalse(included_entry["exclude_from_tkp_autofill"])

    def test_typical_sections_json_exposes_accounting_type_for_tz_editor(self):
        product = Product.objects.create(
            short_name="SEC",
            name_en="Section product",
            name_ru="Продукт разделов",
            service_type="service",
            position=1,
        )
        TypicalSection.objects.create(
            product=product,
            code="SEC-1",
            short_name="section-1",
            short_name_ru="Раздел 1",
            name_en="Section 1",
            name_ru="Раздел 1",
            accounting_type="Раздел",
            position=1,
        )
        TypicalSection.objects.create(
            product=product,
            code="SRV-1",
            short_name="service-1",
            short_name_ru="Услуга 1",
            name_en="Service 1",
            name_ru="Услуга 1",
            accounting_type="Услуги",
            position=2,
        )

        response = self.client.get(reverse("proposal_form_create"))

        self.assertEqual(response.status_code, 200)
        entries = response.context["typical_sections_json"][str(product.pk)]
        self.assertEqual(
            {item["name"]: item["accounting_type"] for item in entries},
            {
                "Раздел 1": "Раздел",
                "Услуга 1": "Услуги",
            },
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
            expertise_dir=expertise,
            expertise_direction=direction,
            position=1,
        )
        specialty = ExpertSpecialty.objects.create(specialty="Оценщик", position=2)
        TypicalSectionSpecialty.objects.create(section=section, specialty=specialty, rank=1)
        _, employee_candidate = self._create_staff_employee(
            username="valuation-candidate",
            first_name="Мария",
            last_name="Экспертова",
        )
        profile_candidate = ExpertProfile.objects.create(
            employee=employee_candidate,
            professional_status="Accredited Senior Appraiser",
            professional_status_short="ASA",
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
            professional_status="Certified Public Accountant",
            professional_status_short="CPA",
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
            position=1,
        )
        specialty = ExpertSpecialty.objects.create(
            specialty="Партнер",
            position=1,
        )
        TypicalSectionSpecialty.objects.create(section=section, specialty=specialty, rank=1)
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
        with patch("proposals_app.forms.get_cbr_eur_rate_for_today", return_value=Decimal("95.1111")):
            response = self.client.get(reverse("proposal_form_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="proposal-project-name-prefix"', html=False)
        self.assertContains(response, 'id="proposal-project-name-suffix"', html=False)
        self.assertContains(response, 'type="hidden" name="proposal_project_name"', html=False)
        self.assertContains(response, 'id="proposal-purpose-prefix"', html=False)
        self.assertContains(response, 'id="proposal-purpose-suffix"', html=False)
        self.assertContains(response, 'type="hidden" name="purpose"', html=False)
        self.assertContains(response, 'id="proposal-commercial-totals-payload"', html=False)
        self.assertContains(response, 'name="status"', html=False)
        self.assertContains(response, 'value="final"', html=False)
        self.assertContains(response, 'id="proposal-report-languages-dropdown"', html=False)
        self.assertContains(response, 'id="proposal-report-languages-toggle"', html=False)
        self.assertContains(response, 'id="proposal-report-language-en"', html=False)
        self.assertContains(response, 'value="русский"', html=False)
        self.assertNotContains(response, 'id="proposal-kind-filter-toggle"', html=False)


class ProposalNextcloudWorkspaceHookTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="proposal-nextcloud-staff",
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
        self.product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            service_type="service",
            position=1,
        )

    def _payload(self, **overrides):
        payload = {
            "number": "3333",
            "group_member": str(self.group_member.pk),
            "type": str(self.product.pk),
            "name": "Тестовое ТКП",
            "kind": ProposalRegistration.ProposalKind.REGULAR,
            "status": ProposalRegistration.ProposalStatus.FINAL,
            "year": "2026",
            "report_languages": "русский",
        }
        payload.update(overrides)
        return payload

    @patch("ai_app.proposals_app.views.create_proposal_workspace")
    @patch("ai_app.proposals_app.views.is_nextcloud_primary", return_value=True)
    def test_create_view_triggers_nextcloud_workspace_for_new_proposal(self, _mocked_is_nextcloud, mocked_workspace):
        mocked_workspace.return_value = "/Corporate Root/ТКП/2026/333300RU DD Тестовое ТКП"
        response = self.client.post(reverse("proposal_form_create"), self._payload())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ProposalRegistration.objects.count(), 1)
        mocked_workspace.assert_called_once()
        self.assertEqual(mocked_workspace.call_args.args[0], self.user)
        proposal = ProposalRegistration.objects.first()
        self.assertEqual(mocked_workspace.call_args.args[1].pk, proposal.pk)
        self.assertEqual(proposal.proposal_workspace_disk_path, mocked_workspace.return_value)
        self.assertEqual(proposal.proposal_workspace_public_url, "")

    def test_create_view_rejects_new_proposal_without_year(self):
        response = self.client.post(reverse("proposal_form_create"), self._payload(year=""))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ProposalRegistration.objects.count(), 0)
        self.assertContains(response, "year: Укажите год.", html=False)

    def test_create_view_does_not_duplicate_bsn_for_synced_customer_owner_and_default_asset(self):
        country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            full_name="Российская Федерация",
            alpha2="RU",
            alpha3="RUS",
            position=1,
        )

        response = self.client.post(
            reverse("proposal_form_create"),
            self._payload(
                customer='ООО "Заказчик"',
                country=str(country.pk),
                identifier="ОГРН",
                registration_number="1234567890",
                registration_date="01.04.2026",
                asset_owner='ООО "Заказчик"',
                asset_owner_country=str(country.pk),
                asset_owner_identifier="ОГРН",
                asset_owner_registration_number="1234567890",
                asset_owner_registration_date="01.04.2026",
                asset_owner_matches_customer="on",
                assets_payload=json.dumps(
                    [
                        {
                            "short_name": 'ООО "Заказчик"',
                            "country_id": str(country.pk),
                            "country_name": "Россия",
                            "identifier": "ОГРН",
                            "registration_number": "1234567890",
                            "registration_date": "01.04.2026",
                            "selected_identifier_record_id": "",
                            "selected_from_autocomplete": False,
                            "user_edited": False,
                        }
                    ],
                    ensure_ascii=False,
                ),
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(BusinessEntityRecord.objects.count(), 1)
        entity = BusinessEntityRecord.objects.get()
        self.assertEqual(entity.name, 'ООО "Заказчик"')
        self.assertEqual(entity.source, "[ТКП / Заказчик]")

    @patch("ai_app.proposals_app.views.create_proposal_workspace")
    @patch("ai_app.proposals_app.views.is_nextcloud_primary", return_value=True)
    def test_edit_view_does_not_trigger_nextcloud_workspace(self, _mocked_is_nextcloud, mocked_workspace):
        proposal = ProposalRegistration.objects.create(
            number=3333,
            group_member=self.group_member,
            type=self.product,
            name="Черновик",
            year=2026,
        )

        response = self.client.post(
            reverse("proposal_form_edit", args=[proposal.pk]),
            self._payload(name="Обновленное ТКП", year=""),
        )

        self.assertEqual(response.status_code, 200)
        mocked_workspace.assert_not_called()
        proposal.refresh_from_db()
        self.assertIsNone(proposal.year)


@override_settings(
    NEXTCLOUD_PROVISIONING_BASE_URL="https://cloud.example.com",
    NEXTCLOUD_PROVISIONING_USERNAME="cloud-admin",
    NEXTCLOUD_PROVISIONING_TOKEN="token",
    NEXTCLOUD_OIDC_PROVIDER_ID=1,
    ROOT_URLCONF="proposals_app.urls",
)
class ProposalDispatchDiskColumnTests(TestCase):
    def setUp(self):
        settings_obj = CloudStorageSettings.get_solo()
        settings_obj.primary_storage = CloudStorageSettings.PrimaryStorage.NEXTCLOUD
        settings_obj.nextcloud_root_path = "/Corporate Root"
        settings_obj.save()

        self.user = get_user_model().objects.create_user(
            username="proposal-disk-user",
            email="proposal-disk-user@example.com",
            password="secret",
            is_staff=True,
            is_active=True,
        )
        self.client.force_login(self.user)
        self.user_link = NextcloudUserLink.objects.create(
            user=self.user,
            nextcloud_user_id=f"ncstaff-{self.user.pk}",
            nextcloud_username=f"ncstaff-{self.user.pk}",
            nextcloud_email=self.user.email,
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
            name="Тестовое ТКП",
            year=2026,
            proposal_workspace_disk_path="/Corporate Root/ТКП/2026/333300RU DD Тестовое ТКП",
        )

    @patch("nextcloud_app.api.NextcloudApiClient.list_user_shares")
    def test_proposals_partial_renders_disk_icon_with_nextcloud_share_target(self, mocked_list_user_shares):
        mocked_list_user_shares.return_value = {
            self.proposal.proposal_workspace_disk_path: NextcloudShare(
                share_id="77",
                path=self.proposal.proposal_workspace_disk_path,
                share_with=self.user_link.nextcloud_user_id,
                permissions=15,
                target_path="/Shared/333300RU DD Тестовое ТКП",
            )
        }

        response = self.client.get(reverse("proposals_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ">Облако<", html=False)
        self.assertContains(response, 'title="Открыть папку на Nextcloud"', html=False)
        self.assertContains(
            response,
            "/apps/files/files?dir=/Shared/333300RU%20DD%20%D0%A2%D0%B5%D1%81%D1%82%D0%BE%D0%B2%D0%BE%D0%B5%20%D0%A2%D0%9A%D0%9F",
            html=False,
        )

    @patch("nextcloud_app.api.NextcloudApiClient.list_user_shares")
    def test_proposals_partial_uses_editor_files_url_instead_of_saved_public_link(
        self,
        mocked_list_user_shares,
    ):
        self.proposal.proposal_workspace_public_url = "https://cloud.example.com/s/readonly"
        self.proposal.save(update_fields=["proposal_workspace_public_url"])
        mocked_list_user_shares.return_value = {
            self.proposal.proposal_workspace_disk_path: NextcloudShare(
                share_id="82",
                path=self.proposal.proposal_workspace_disk_path,
                share_with=self.user_link.nextcloud_user_id,
                permissions=15,
                target_path="/Shared/333300RU DD Тестовое ТКП",
            )
        }

        response = self.client.get(reverse("proposals_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'href="https://cloud.example.com/s/readonly"', html=False)
        self.assertContains(
            response,
            "/apps/files/files?dir=/Shared/333300RU%20DD%20%D0%A2%D0%B5%D1%81%D1%82%D0%BE%D0%B2%D0%BE%D0%B5%20%D0%A2%D0%9A%D0%9F",
            html=False,
        )

    @patch("nextcloud_app.api.NextcloudApiClient.get_user_share")
    @patch("nextcloud_app.api.NextcloudApiClient.list_user_shares", return_value={})
    def test_proposals_partial_falls_back_to_direct_share_lookup_for_new_workspace(
        self,
        _mocked_list_user_shares,
        mocked_get_user_share,
    ):
        mocked_get_user_share.return_value = NextcloudShare(
            share_id="78",
            path=self.proposal.proposal_workspace_disk_path,
            share_with=self.user_link.nextcloud_user_id,
            permissions=15,
            target_path="/Shared/333300RU DD Тестовое ТКП",
        )

        response = self.client.get(reverse("proposals_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "/apps/files/files?dir=/Shared/333300RU%20DD%20%D0%A2%D0%B5%D1%81%D1%82%D0%BE%D0%B2%D0%BE%D0%B5%20%D0%A2%D0%9A%D0%9F",
            html=False,
        )

    @patch("nextcloud_app.api.NextcloudApiClient.get_user_share")
    @patch("nextcloud_app.api.NextcloudApiClient.list_user_shares", return_value={})
    def test_proposals_partial_resolves_new_workspace_from_parent_share_lookup_when_direct_share_is_missing(
        self,
        _mocked_list_user_shares,
        mocked_get_user_share,
    ):
        def _share_lookup(_owner_user_id, lookup_path, _share_with_user_id):
            normalized_lookup_path = str(lookup_path or "").strip()
            if normalized_lookup_path == self.proposal.proposal_workspace_disk_path:
                return None
            if normalized_lookup_path == "/Corporate Root/ТКП":
                return NextcloudShare(
                    share_id="78-parent",
                    path="/Corporate Root/ТКП",
                    share_with=self.user_link.nextcloud_user_id,
                    permissions=15,
                    target_path="/ТКП",
                )
            return None

        mocked_get_user_share.side_effect = _share_lookup

        response = self.client.get(reverse("proposals_partial"))

        self.assertEqual(response.status_code, 200)
        expected_suffix = self.proposal.proposal_workspace_disk_path.split("/ТКП/", 1)[1]
        expected_url = (
            "https://cloud.example.com/apps/files/files?dir="
            f"{quote(f'/ТКП/{expected_suffix}', safe='/')}"
        )
        self.assertContains(
            response,
            f'href="{expected_url}"',
            html=False,
        )

    @patch("nextcloud_app.api.NextcloudApiClient.list_user_shares")
    def test_proposals_partial_resolves_editor_cloud_link_from_parent_shared_folder_for_director(
        self,
        mocked_list_user_shares,
    ):
        Employee.objects.create(user=self.user, role="Директор")
        mocked_list_user_shares.return_value = {
            "/Corporate Root/ТКП": NextcloudShare(
                share_id="79",
                path="/Corporate Root/ТКП",
                share_with=self.user_link.nextcloud_user_id,
                permissions=15,
                target_path="/Shared/ТКП",
            )
        }

        response = self.client.get(reverse("proposals_partial"))

        self.assertEqual(response.status_code, 200)
        director_url = (
            "https://cloud.example.com/apps/files/files?dir="
            f"{quote('/Shared/ТКП/2026/333300RU DD Тестовое ТКП', safe='/')}"
        )
        self.assertContains(
            response,
            f'href="{director_url}"',
            html=False,
        )

    @patch("nextcloud_app.api.NextcloudApiClient.list_user_shares")
    def test_proposals_partial_strips_owner_root_from_direct_share_target_path_for_viewer(
        self,
        mocked_list_user_shares,
    ):
        mocked_list_user_shares.return_value = {
            self.proposal.proposal_workspace_disk_path: NextcloudShare(
                share_id="79-direct-owner-path",
                path=self.proposal.proposal_workspace_disk_path,
                share_with=self.user_link.nextcloud_user_id,
                permissions=15,
                target_path="/Corporate Root/ТКП/2026/333300RU DD Тестовое ТКП",
            )
        }

        response = self.client.get(reverse("proposals_partial"))

        self.assertEqual(response.status_code, 200)
        stripped_url = (
            "https://cloud.example.com/apps/files/files?dir="
            f"{quote('/ТКП/2026/333300RU DD Тестовое ТКП', safe='/')}"
        )
        owner_url = (
            "https://cloud.example.com/apps/files/files?dir="
            f"{quote('/Corporate Root/ТКП/2026/333300RU DD Тестовое ТКП', safe='/')}"
        )
        self.assertContains(
            response,
            f'href="{stripped_url}"',
            html=False,
        )
        self.assertNotContains(
            response,
            f'href="{owner_url}"',
            html=False,
        )

    @patch("nextcloud_app.api.NextcloudApiClient.list_user_shares")
    def test_proposals_partial_resolves_editor_cloud_link_from_parent_share_without_owner_root_prefix(
        self,
        mocked_list_user_shares,
    ):
        mocked_list_user_shares.return_value = {
            "/ТКП": NextcloudShare(
                share_id="83",
                path="/ТКП",
                share_with=self.user_link.nextcloud_user_id,
                permissions=15,
                target_path="/ТКП",
            )
        }

        response = self.client.get(reverse("proposals_partial"))

        self.assertEqual(response.status_code, 200)
        expected_suffix = self.proposal.proposal_workspace_disk_path.split("/ТКП/", 1)[1]
        expected_url = (
            "https://cloud.example.com/apps/files/files?dir="
            f"{quote(f'/ТКП/{expected_suffix}', safe='/')}"
        )
        self.assertContains(
            response,
            f'href="{expected_url}"',
            html=False,
        )

    @patch("nextcloud_app.api.NextcloudApiClient.get_user_share", return_value=None)
    @patch("nextcloud_app.api.NextcloudApiClient.list_user_shares")
    def test_proposals_partial_resolves_parent_shared_folder_when_direct_share_has_no_target_path(
        self,
        mocked_list_user_shares,
        _mocked_get_user_share,
    ):
        mocked_list_user_shares.return_value = {
            self.proposal.proposal_workspace_disk_path: NextcloudShare(
                share_id="80",
                path=self.proposal.proposal_workspace_disk_path,
                share_with=self.user_link.nextcloud_user_id,
                permissions=15,
                target_path="",
            ),
            "/Corporate Root/ТКП": NextcloudShare(
                share_id="81",
                path="/Corporate Root/ТКП",
                share_with=self.user_link.nextcloud_user_id,
                permissions=15,
                target_path="/Shared/ТКП",
            ),
        }

        response = self.client.get(reverse("proposals_partial"))

        self.assertEqual(response.status_code, 200)
        expected_suffix = self.proposal.proposal_workspace_disk_path.split("/Corporate Root/ТКП/", 1)[1]
        expected_url = (
            "https://cloud.example.com/apps/files/files?dir="
            f"{quote(f'/Shared/ТКП/{expected_suffix}', safe='/')}"
        )
        self.assertContains(
            response,
            expected_url,
            html=False,
        )

    @patch("nextcloud_app.api.NextcloudApiClient.list_user_shares")
    def test_proposals_partial_prefers_earlier_parent_share_when_same_depth_candidates_exist(
        self,
        mocked_list_user_shares,
    ):
        mocked_list_user_shares.return_value = {
            "/2026": NextcloudShare(
                share_id="84",
                path="/2026",
                share_with=self.user_link.nextcloud_user_id,
                permissions=15,
                target_path="/2026",
            ),
            "/ТКП": NextcloudShare(
                share_id="85",
                path="/ТКП",
                share_with=self.user_link.nextcloud_user_id,
                permissions=15,
                target_path="/ТКП",
            ),
        }

        response = self.client.get(reverse("proposals_partial"))

        self.assertEqual(response.status_code, 200)
        expected_suffix = self.proposal.proposal_workspace_disk_path.split("/ТКП/", 1)[1]
        competing_suffix = self.proposal.proposal_workspace_disk_path.rsplit("/2026/", 1)[1]
        expected_url = (
            "https://cloud.example.com/apps/files/files?dir="
            f"{quote(f'/ТКП/{expected_suffix}', safe='/')}"
        )
        competing_url = (
            "https://cloud.example.com/apps/files/files?dir="
            f"{quote(f'/2026/{competing_suffix}', safe='/')}"
        )
        self.assertContains(
            response,
            f'href="{expected_url}"',
            html=False,
        )
        self.assertNotContains(
            response,
            f'href="{competing_url}"',
            html=False,
        )

    @patch("nextcloud_app.api.NextcloudApiClient.ensure_public_link_share")
    def test_proposals_partial_falls_back_to_direct_cloud_link_when_viewer_has_no_nextcloud_link(
        self,
        mocked_ensure_public_link_share,
    ):
        self.user_link.delete()

        response = self.client.get(reverse("proposals_partial"))

        self.assertEqual(response.status_code, 200)
        owner_url = f"https://cloud.example.com/apps/files/files?dir={quote(self.proposal.proposal_workspace_disk_path, safe='/')}"
        self.assertContains(
            response,
            f'href="{owner_url}"',
            html=False,
        )
        mocked_ensure_public_link_share.assert_not_called()

    @patch("nextcloud_app.api.NextcloudApiClient.get_user_share", return_value=None)
    @patch("nextcloud_app.api.NextcloudApiClient.list_user_shares", return_value={})
    def test_proposals_partial_falls_back_to_root_stripped_shared_path_when_share_target_is_missing_for_viewer_with_nextcloud(
        self,
        _mocked_list_user_shares,
        _mocked_get_user_share,
    ):
        response = self.client.get(reverse("proposals_partial"))

        self.assertEqual(response.status_code, 200)
        owner_url = f"https://cloud.example.com/apps/files/files?dir={quote(self.proposal.proposal_workspace_disk_path, safe='/')}"
        stripped_url = (
            "https://cloud.example.com/apps/files/files?dir="
            f"{quote('/ТКП/2026/333300RU DD Тестовое ТКП', safe='/')}"
        )
        self.assertNotContains(
            response,
            f'href="{owner_url}"',
            html=False,
        )
        self.assertContains(
            response,
            f'href="{stripped_url}"',
            html=False,
        )

    @patch("nextcloud_app.api.NextcloudApiClient.get_user_share", return_value=None)
    @patch("nextcloud_app.api.NextcloudApiClient.list_user_shares", return_value={})
    def test_proposals_partial_uses_cached_session_target_path_when_share_api_lags(
        self,
        _mocked_list_user_shares,
        _mocked_get_user_share,
    ):
        session = self.client.session
        session[PROPOSAL_NEXTCLOUD_TARGETS_SESSION_KEY] = {
            self.proposal.proposal_workspace_disk_path: "/333300RU DD Тестовое ТКП",
        }
        session.save()

        response = self.client.get(reverse("proposals_partial"))

        self.assertEqual(response.status_code, 200)
        cached_url = (
            "https://cloud.example.com/apps/files/files?dir="
            f"{quote('/333300RU DD Тестовое ТКП', safe='/')}"
        )
        stripped_url = (
            "https://cloud.example.com/apps/files/files?dir="
            f"{quote('/ТКП/2026/333300RU DD Тестовое ТКП', safe='/')}"
        )
        self.assertContains(
            response,
            f'href="{cached_url}"',
            html=False,
        )
        self.assertNotContains(
            response,
            f'href="{stripped_url}"',
            html=False,
        )

    @patch("nextcloud_app.api.NextcloudApiClient.get_user_share", return_value=None)
    @patch("nextcloud_app.api.NextcloudApiClient.list_user_shares", return_value={})
    def test_proposals_partial_keeps_gray_icon_when_root_stripped_fallback_is_unavailable(
        self,
        _mocked_list_user_shares,
        _mocked_get_user_share,
    ):
        settings_obj = CloudStorageSettings.get_solo()
        settings_obj.nextcloud_root_path = "/Another Root"
        settings_obj.save(update_fields=["nextcloud_root_path"])

        response = self.client.get(reverse("proposals_partial"))

        self.assertEqual(response.status_code, 200)
        owner_url = f"https://cloud.example.com/apps/files/files?dir={quote(self.proposal.proposal_workspace_disk_path, safe='/')}"
        self.assertNotContains(
            response,
            f'href="{owner_url}"',
            html=False,
        )
        self.assertContains(
            response,
            'style="color: #ccc;"',
            html=False,
        )

    @patch("nextcloud_app.api.NextcloudApiClient.get_user_share", return_value=None)
    @patch("nextcloud_app.api.NextcloudApiClient.list_user_shares", return_value={})
    def test_proposals_partial_falls_back_to_saved_public_workspace_url_for_viewer_with_nextcloud(
        self,
        _mocked_list_user_shares,
        _mocked_get_user_share,
    ):
        self.proposal.proposal_workspace_public_url = "https://cloud.example.com/s/saved-proposal-folder"
        self.proposal.save(update_fields=["proposal_workspace_public_url"])
        owner_url = f"https://cloud.example.com/apps/files/files?dir={quote(self.proposal.proposal_workspace_disk_path, safe='/')}"

        response = self.client.get(reverse("proposals_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'href="https://cloud.example.com/s/saved-proposal-folder"',
            html=False,
        )
        self.assertNotContains(
            response,
            f'href="{owner_url}"',
            html=False,
        )

    def test_proposals_partial_preserves_saved_public_workspace_url_in_mixed_rows_without_viewer_link(self):
        self.proposal.proposal_workspace_public_url = "https://cloud.example.com/s/saved-proposal-folder"
        self.proposal.save(update_fields=["proposal_workspace_public_url"])
        ProposalRegistration.objects.create(
            number=3334,
            group_member=self.group_member,
            type=self.product,
            name="Второе ТКП",
            year=2026,
            proposal_workspace_disk_path="/Corporate Root/ТКП/2026/333400RU DD Второе ТКП",
        )
        self.user_link.delete()

        response = self.client.get(reverse("proposals_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'href="https://cloud.example.com/s/saved-proposal-folder"',
            html=False,
        )
        self.assertContains(
            response,
            'href="https://cloud.example.com/apps/files/files?dir=/Corporate%20Root/%D0%A2%D0%9A%D0%9F/2026/333400RU%20DD%20%D0%92%D1%82%D0%BE%D1%80%D0%BE%D0%B5%20%D0%A2%D0%9A%D0%9F"',
            html=False,
        )

    @patch("nextcloud_app.api.NextcloudApiClient.get_user_share", return_value=None)
    @patch("nextcloud_app.api.NextcloudApiClient.list_user_shares", return_value={})
    def test_proposals_partial_builds_direct_cloud_link_from_expected_workspace_path_for_legacy_rows(
        self,
        _mocked_list_user_shares,
        _mocked_get_user_share,
    ):
        self.user_link.delete()
        self.proposal.proposal_workspace_disk_path = ""
        self.proposal.save(update_fields=["proposal_workspace_disk_path"])

        response = self.client.get(reverse("proposals_partial"))

        self.assertEqual(response.status_code, 200)
        expected_workspace_path = f"/Corporate Root/ТКП/2026/{self.proposal.short_uid} DD Тестовое ТКП"
        owner_url = (
            "https://cloud.example.com/apps/files/files?dir="
            f"{quote(expected_workspace_path, safe='/')}"
        )
        self.assertContains(
            response,
            f'href="{owner_url}"',
            html=False,
        )

    def test_proposals_partial_preserves_saved_public_workspace_url_when_path_is_missing(self):
        self.user_link.delete()
        self.proposal.year = None
        self.proposal.proposal_workspace_disk_path = ""
        self.proposal.proposal_workspace_public_url = "https://cloud.example.com/s/legacy-proposal-folder"
        self.proposal.save(update_fields=["year", "proposal_workspace_disk_path", "proposal_workspace_public_url"])

        response = self.client.get(reverse("proposals_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'href="https://cloud.example.com/s/legacy-proposal-folder"',
            html=False,
        )


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
