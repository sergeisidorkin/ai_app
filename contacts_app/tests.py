from datetime import date

from django.contrib.auth import get_user_model
from django.forms import HiddenInput
from django.test import TestCase
from django.urls import reverse

from classifiers_app.models import (
    BusinessEntityIdentifierRecord,
    BusinessEntityRecord,
    LegalEntityRecord,
    NumcapRecord,
    OKSMCountry,
    PhysicalEntityIdentifier,
    TerritorialDivision,
)
from experts_app.models import ExpertContractDetails, ExpertProfile
from group_app.models import GroupMember
from proposals_app.models import ProposalRegistration
from users_app.models import Employee

from .forms import CitizenshipRecordForm, EmailRecordForm, PersonRecordForm, PhoneRecordForm, PositionRecordForm, ResidenceAddressRecordForm
from .models import (
    CONTACT_POSITION_SOURCE,
    CitizenshipRecord,
    EmailRecord,
    PersonRecord,
    PhoneRecord,
    PositionRecord,
    ResidenceAddressRecord,
)


class ContactsAppTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="contacts-user",
            password="secret",
            is_staff=True,
            first_name="Иван",
            last_name="Админов",
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
        self.us_country = OKSMCountry.objects.create(
            number=840,
            code="840",
            short_name="США",
            full_name="Соединенные Штаты Америки",
            alpha2="US",
            alpha3="USA",
            position=2,
        )
        TerritorialDivision.objects.create(
            country=self.country,
            region_name="Москва",
            region_code="77",
            effective_date=date(2020, 1, 1),
            position=1,
        )
        TerritorialDivision.objects.create(
            country=self.country,
            region_name="Московская область",
            region_code="50",
            effective_date=date(2020, 1, 1),
            position=2,
        )
        TerritorialDivision.objects.create(
            country=self.us_country,
            region_name="California",
            region_code="CA",
            effective_date=date(2020, 1, 1),
            position=3,
        )
        self.person = PersonRecord.objects.create(
            last_name="Иванов",
            first_name="Иван",
            middle_name="Иванович",
            full_name_genitive="Иванова Ивана Ивановича",
            gender="male",
            birth_date=date(1990, 5, 17),
            citizenship=self.country,
            position=1,
        )
        self._create_numcap_range(code="495", begin="1230000", end="1239999", region="Москва", position=1)
        self._create_numcap_range(code="999", begin="1230000", end="1239999", region="Москва", position=2)

    def _create_numcap_range(self, *, code, begin, end, region, position, operator="Тестовый оператор", capacity=""):
        return NumcapRecord.objects.create(
            code=code,
            begin=begin,
            end=end,
            capacity=capacity or str(int(end) - int(begin) + 1),
            operator=operator,
            region=region,
            position=position,
        )

    def _create_active_name(self, *, short_name, position, is_active=True):
        business_entity = BusinessEntityRecord.objects.create(name=short_name, position=position)
        identifier_record = BusinessEntityIdentifierRecord.objects.create(
            business_entity=business_entity,
            identifier_type="ОГРН",
            registration_country=self.country,
            registration_region="Москва",
            number=f"7700{position}",
            registration_date=date(2025, 1, 1),
            valid_from=date(2025, 1, 1),
            valid_to=None if is_active else date(2025, 12, 31),
            position=position,
        )
        return LegalEntityRecord.objects.create(
            attribute=LegalEntityRecord.ATTRIBUTE_NAME,
            identifier_record=identifier_record,
            short_name=short_name,
            full_name=short_name,
            name_received_date=date(2025, 1, 1),
            name_changed_date=None if is_active else date(2025, 12, 31),
            position=position,
        )

    def test_position_record_resolve_source_matches_recipient_and_surname_only(self):
        ProposalRegistration.objects.create(
            number=3333,
            group="RU",
            recipient='ООО "Альфа"',
            recipient_job_title="Генеральный директор",
            contact_full_name="Иванов Петр Сергеевич",
            position=1,
        )
        record = PositionRecord(
            person=self.person,
            organization_short_name='ООО "Альфа"',
            job_title="Генеральный директор",
        )

        self.assertEqual(record.resolve_source(), CONTACT_POSITION_SOURCE)

    def test_position_record_resolve_source_returns_empty_for_other_surname(self):
        ProposalRegistration.objects.create(
            number=3333,
            group="RU",
            recipient='ООО "Альфа"',
            recipient_job_title="Генеральный директор",
            contact_full_name="Петров Петр Сергеевич",
            position=1,
        )
        record = PositionRecord(
            person=self.person,
            organization_short_name='ООО "Альфа"',
            job_title="Генеральный директор",
        )

        self.assertEqual(record.resolve_source(), "")

    def test_position_form_uses_text_input_and_prefills_org_metadata(self):
        self._create_active_name(short_name='ООО "Альфа"', position=1, is_active=True)
        self._create_active_name(short_name='ООО "Бета"', position=2, is_active=False)
        instance = PositionRecord(
            person=self.person,
            organization_short_name='ООО "Альфа"',
            job_title="Генеральный директор",
        )

        form = PositionRecordForm(instance=instance)

        self.assertEqual(form.fields["organization_short_name"].widget.__class__.__name__, "TextInput")
        self.assertEqual(form.fields["organization_short_name"].widget.attrs["id"], "psn-organization-input")
        self.assertEqual(form.fields["organization_identifier"].widget.attrs["id"], "psn-organization-identifier-field")
        self.assertEqual(
            form.fields["organization_registration_number"].widget.attrs["id"],
            "psn-organization-registration-number-field",
        )
        self.assertEqual(form.initial["organization_identifier"], "ОГРН")
        self.assertEqual(form.initial["organization_registration_number"], "77001")

    def test_position_form_prefers_group_member_org_metadata(self):
        GroupMember.objects.create(
            short_name='ООО "Альфа"',
            full_name='ООО "Альфа"',
            country_name="Россия",
            identifier="LEI",
            registration_number="REG-123",
            position=1,
        )
        self._create_active_name(short_name='ООО "Альфа"', position=1, is_active=True)
        instance = PositionRecord(
            person=self.person,
            organization_short_name='ООО "Альфа"',
            job_title="Генеральный директор",
        )

        form = PositionRecordForm(instance=instance)

        self.assertEqual(form.initial["organization_identifier"], "LEI")
        self.assertEqual(form.initial["organization_registration_number"], "REG-123")

    def test_position_form_keeps_managed_fields_readonly_and_unchanged(self):
        item = PositionRecord.objects.create(
            person=self.person,
            organization_short_name='ООО "Альфа"',
            job_title="Директор",
            is_user_managed=True,
            position=1,
        )

        form = PositionRecordForm(
            data={
                "person": self.person.pk,
                "organization_short_name": 'ООО "Бета"',
                "job_title": "Менеджер",
                "valid_from": "2026-01-01",
                "valid_to": "",
            },
            instance=item,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["organization_short_name"], 'ООО "Альфа"')
        self.assertEqual(form.cleaned_data["job_title"], "Директор")

    def test_psn_create_sets_source_and_record_metadata(self):
        self._create_active_name(short_name='ООО "Альфа"', position=1, is_active=True)
        ProposalRegistration.objects.create(
            number=3333,
            group="RU",
            recipient='ООО "Альфа"',
            recipient_job_title="Генеральный директор",
            contact_full_name="Иванов Петр Сергеевич",
            position=1,
        )

        response = self.client.post(
            reverse("psn_form_create"),
            {
                "person": self.person.pk,
                "organization_short_name": 'ООО "Альфа"',
                "job_title": "Генеральный директор",
                "valid_from": "2026-01-01",
                "valid_to": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        item = PositionRecord.objects.get()
        self.assertEqual(item.source, CONTACT_POSITION_SOURCE)
        self.assertEqual(item.record_author, "Иван Админов")
        self.assertEqual(item.record_date, date.today())

    def test_prs_edit_refreshes_sources_for_related_positions(self):
        ProposalRegistration.objects.create(
            number=3333,
            group="RU",
            recipient='ООО "Альфа"',
            recipient_job_title="Генеральный директор",
            contact_full_name="Иванов Петр Сергеевич",
            position=1,
        )
        position = PositionRecord.objects.create(
            person=self.person,
            organization_short_name='ООО "Альфа"',
            job_title="Генеральный директор",
            source=CONTACT_POSITION_SOURCE,
            position=1,
        )

        response = self.client.post(
            reverse("prs_form_edit", args=[self.person.pk]),
            {
                "last_name": "Сидоров",
                "first_name": self.person.first_name,
                "middle_name": self.person.middle_name,
                "birth_date": "17.05.1990",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('"affected": ["ctz-select", "adr-select", "psn-select", "tel-select", "eml-select"]', response.headers["HX-Trigger"])
        position.refresh_from_db()
        self.assertEqual(position.source, "")

    def test_prs_create_also_creates_default_related_contact_records(self):
        response = self.client.post(
            reverse("prs_form_create"),
            {
                "last_name": "Петров",
                "first_name": "Петр",
                "middle_name": "Петрович",
                "full_name_genitive": "Петрова Петра Петровича",
                "gender": "male",
                "birth_date": "01.02.1991",
            },
        )

        self.assertEqual(response.status_code, 200)
        person = PersonRecord.objects.get(last_name="Петров")
        self.assertEqual(person.birth_date, date(1991, 2, 1))
        self.assertEqual(person.full_name_genitive, "Петрова Петра Петровича")
        self.assertEqual(person.gender, "male")
        citizenships = list(person.citizenships.all())
        self.assertEqual(len(citizenships), 1)
        self.assertIsNone(citizenships[0].country)
        self.assertEqual(citizenships[0].identifier, "")
        self.assertEqual(citizenships[0].number, "")
        self.assertEqual(citizenships[0].record_author, "Иван Админов")
        addresses = list(person.residence_addresses.all())
        self.assertEqual(len(addresses), 1)
        self.assertIsNone(addresses[0].country)
        self.assertEqual(addresses[0].region, "")
        self.assertEqual(addresses[0].postal_code, "")
        self.assertEqual(addresses[0].record_author, "Иван Админов")
        self.assertEqual(addresses[0].record_date, date.today())
        phones = list(person.phones.all())
        self.assertEqual(len(phones), 1)
        self.assertEqual(phones[0].phone_number, "")
        self.assertEqual(phones[0].record_author, "Иван Админов")
        self.assertEqual(phones[0].record_date, date.today())
        self.assertEqual(phones[0].valid_from, date.today())
        self.assertEqual(phones[0].phone_type, PhoneRecord.PHONE_TYPE_MOBILE)
        self.assertEqual(phones[0].extension, "")
        self.assertEqual(phones[0].region, "")
        self.assertTrue(phones[0].is_primary)
        emails = list(person.emails.all())
        self.assertEqual(len(emails), 1)
        self.assertEqual(emails[0].email, "")
        self.assertEqual(emails[0].record_author, "Иван Админов")
        self.assertEqual(emails[0].record_date, date.today())
        self.assertEqual(emails[0].valid_from, date.today())

    def test_prs_edit_creates_default_related_contact_records_when_missing(self):
        self.assertFalse(self.person.citizenships.exists())
        self.assertFalse(self.person.residence_addresses.exists())
        self.assertFalse(self.person.phones.exists())
        self.assertFalse(self.person.emails.exists())

        response = self.client.post(
            reverse("prs_form_edit", args=[self.person.pk]),
            {
                "last_name": self.person.last_name,
                "first_name": self.person.first_name,
                "middle_name": self.person.middle_name,
                "birth_date": "17.05.1990",
            },
        )

        self.assertEqual(response.status_code, 200)
        citizenships = list(self.person.citizenships.all())
        self.assertEqual(len(citizenships), 1)
        self.assertEqual(citizenships[0].country, self.country)
        addresses = list(self.person.residence_addresses.all())
        self.assertEqual(len(addresses), 1)
        self.assertEqual(addresses[0].country, self.country)
        self.assertEqual(addresses[0].region, "")
        self.assertEqual(addresses[0].record_date, date.today())
        phones = list(self.person.phones.all())
        self.assertEqual(len(phones), 1)
        self.assertEqual(phones[0].phone_number, "")
        self.assertEqual(phones[0].valid_from, date.today())
        self.assertEqual(phones[0].phone_type, PhoneRecord.PHONE_TYPE_MOBILE)
        self.assertEqual(phones[0].region, "")
        self.assertTrue(phones[0].is_primary)
        emails = list(self.person.emails.all())
        self.assertEqual(len(emails), 1)
        self.assertEqual(emails[0].email, "")
        self.assertEqual(emails[0].record_date, date.today())
        self.assertEqual(emails[0].valid_from, date.today())

    def test_prs_form_uses_birth_date_field_with_datepicker(self):
        form = PersonRecordForm()

        self.assertIn("birth_date", form.fields)
        self.assertEqual(form.fields["birth_date"].widget.input_type, "date")

    def test_prs_form_uses_text_input_for_full_name_genitive(self):
        form = PersonRecordForm()

        self.assertIn("full_name_genitive", form.fields)
        self.assertEqual(form.fields["full_name_genitive"].widget.__class__.__name__, "TextInput")
        self.assertEqual(
            form.fields["full_name_genitive"].widget.attrs["placeholder"],
            "ФИО (полное) в родительном падеже",
        )

    def test_prs_form_uses_select_for_gender(self):
        form = PersonRecordForm()

        self.assertIn("gender", form.fields)
        self.assertEqual(form.fields["gender"].widget.__class__.__name__, "Select")
        self.assertEqual(form.fields["gender"].choices[1][1], "мужской")
        self.assertEqual(form.fields["gender"].choices[2][1], "женский")

    def test_prs_edit_form_shows_readonly_user_kind_field(self):
        self.person.user_kind = "employee"
        self.person.save(update_fields=["user_kind"])

        response = self.client.get(reverse("prs_form_edit", args=[self.person.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Пользователь")
        self.assertContains(response, 'class="form-control readonly-field"', html=False)
        self.assertContains(response, 'value="Сотрудник"', html=False)

    def test_prs_form_locks_name_fields_for_employee_user_kind(self):
        self.person.user_kind = "employee"
        self.person.save(update_fields=["user_kind"])

        form = PersonRecordForm(instance=self.person)

        for field_name in ("last_name", "first_name", "middle_name"):
            self.assertTrue(form.fields[field_name].disabled)
            self.assertTrue(form.fields[field_name].widget.attrs["readonly"])

    def test_prs_edit_ignores_name_changes_for_managed_person(self):
        self.person.user_kind = "employee"
        self.person.save(update_fields=["user_kind"])

        response = self.client.post(
            reverse("prs_form_edit", args=[self.person.pk]),
            {
                "last_name": "Петров",
                "first_name": "Петр",
                "middle_name": "Петрович",
                "birth_date": "1990-05-17",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.person.refresh_from_db()
        self.assertEqual(self.person.last_name, "Иванов")
        self.assertEqual(self.person.first_name, "Иван")
        self.assertEqual(self.person.middle_name, "Иванович")

    def test_ctz_delete_rejects_last_record_for_person(self):
        item = CitizenshipRecord.objects.create(
            person=self.person,
            country=self.country,
            status=CitizenshipRecordForm.STATUS_CITIZENSHIP,
            identifier="Паспорт",
            number="123456789",
            position=1,
        )

        response = self.client.post(reverse("ctz_delete", args=[item.pk]))

        self.assertEqual(response.status_code, 409)
        self.assertIn(
            "У каждой записи в реестре лиц должна оставаться хотя бы одна запись в реестре гражданств и идентификаторов.",
            response.content.decode("utf-8"),
        )
        self.assertTrue(CitizenshipRecord.objects.filter(pk=item.pk).exists())

    def test_ctz_create_sets_record_metadata(self):
        PhysicalEntityIdentifier.objects.create(
            identifier="Паспорт",
            full_name="Паспорт гражданина Российской Федерации",
            country=self.country,
            code=self.country.code,
            position=1,
        )
        response = self.client.post(
            reverse("ctz_form_create"),
            {
                "person": self.person.pk,
                "country": self.country.pk,
                "status": CitizenshipRecordForm.STATUS_CITIZENSHIP,
                "identifier": "Произвольное значение",
                "number": "123456789",
                "valid_from": "2026-01-01",
                "valid_to": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        item = CitizenshipRecord.objects.get()
        self.assertEqual(item.country, self.country)
        self.assertEqual(item.record_author, "Иван Админов")
        self.assertEqual(item.record_date, date.today())
        self.assertEqual(item.formatted_id, f"{item.pk:05d}-CTZ")
        self.assertEqual(item.identifier, "Паспорт")
        self.assertTrue(item.is_active)

    def test_ctz_identifier_for_country_returns_physical_identifier_classifier_value(self):
        PhysicalEntityIdentifier.objects.create(
            identifier="СНИЛС",
            full_name="Страховой номер индивидуального лицевого счета",
            country=self.country,
            code=self.country.code,
            position=1,
        )

        response = self.client.get(
            reverse("ctz_identifier_for_country"),
            {"country_id": self.country.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["identifier"], "СНИЛС")

    def test_ctz_form_marks_identifier_field_readonly(self):
        form = CitizenshipRecordForm()

        self.assertTrue(form.fields["identifier"].widget.attrs["readonly"])
        self.assertEqual(form.fields["identifier"].widget.attrs["id"], "ctz-identifier-field")

    def test_ctz_form_shows_disabled_birth_date_from_person_record(self):
        form = CitizenshipRecordForm(initial={"person": self.person.pk})

        self.assertIn("birth_date", form.fields)
        self.assertTrue(form.fields["birth_date"].disabled)
        self.assertTrue(form.fields["birth_date"].widget.attrs["readonly"])
        self.assertEqual(form.fields["birth_date"].widget.attrs["id"], "ctz-birth-date-field")
        self.assertEqual(form.fields["birth_date"].initial, date(1990, 5, 17))

    def test_ctz_form_uses_closed_status_select_with_blank_option(self):
        form = CitizenshipRecordForm()

        self.assertEqual(form.fields["status"].widget.__class__.__name__, "Select")
        self.assertFalse(form.fields["status"].required)
        self.assertEqual(
            list(form.fields["status"].choices),
            [
                ("", "---------"),
                (CitizenshipRecordForm.STATUS_TEMPORARY_STAY, CitizenshipRecordForm.STATUS_TEMPORARY_STAY),
                (CitizenshipRecordForm.STATUS_RESIDENCE_PERMIT, CitizenshipRecordForm.STATUS_RESIDENCE_PERMIT),
                (CitizenshipRecordForm.STATUS_CITIZENSHIP, CitizenshipRecordForm.STATUS_CITIZENSHIP),
            ],
        )

    def test_contact_related_forms_use_hidden_person_field(self):
        forms = [
            CitizenshipRecordForm(),
            ResidenceAddressRecordForm(),
            PositionRecordForm(),
            PhoneRecordForm(),
            EmailRecordForm(),
        ]

        for form in forms:
            self.assertIsInstance(form.fields["person"].widget, HiddenInput)

    def test_contact_related_form_modals_render_prs_picker(self):
        cases = [
            (reverse("ctz_form_create"), "ctz"),
            (reverse("adr_form_create"), "adr"),
            (reverse("psn_form_create"), "psn"),
            (reverse("tel_form_create"), "tel"),
            (reverse("eml_form_create"), "eml"),
        ]

        for url, prefix in cases:
            response = self.client.get(url, {"selected_prs": [str(self.person.pk)]})

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'data-prs-filter-options-url=', html=False)
            self.assertContains(response, 'placeholder="Искать по ID-PRS и ФИО"', html=False)
            self.assertContains(response, f'id="{prefix}-prs-toggle"', html=False)
            self.assertContains(response, f'id="{prefix}-prs-search"', html=False)

    def test_ctz_delete_allows_removing_non_last_record(self):
        first = CitizenshipRecord.objects.create(
            person=self.person,
            country=self.country,
            status=CitizenshipRecordForm.STATUS_CITIZENSHIP,
            identifier="Паспорт",
            number="123456789",
            position=1,
        )
        second = CitizenshipRecord.objects.create(
            person=self.person,
            country=self.country,
            status=CitizenshipRecordForm.STATUS_RESIDENCE_PERMIT,
            identifier="ВНЖ",
            number="987654321",
            position=2,
        )

        response = self.client.post(reverse("ctz_delete", args=[second.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(CitizenshipRecord.objects.filter(pk=first.pk).exists())
        self.assertFalse(CitizenshipRecord.objects.filter(pk=second.pk).exists())

    def test_adr_create_sets_record_metadata(self):
        response = self.client.post(
            reverse("adr_form_create"),
            {
                "person": self.person.pk,
                "country": self.country.pk,
                "region": "Москва",
                "postal_code": "101000",
                "locality": "Москва",
                "street": "Тверская",
                "building": "1",
                "premise": "10",
                "premise_part": "A",
                "valid_from": "2026-01-01",
                "valid_to": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        item = ResidenceAddressRecord.objects.get()
        self.assertEqual(item.country, self.country)
        self.assertEqual(item.region, "Москва")
        self.assertEqual(item.postal_code, "101000")
        self.assertEqual(item.record_author, "Иван Админов")
        self.assertEqual(item.record_date, date.today())
        self.assertEqual(item.formatted_id, f"{item.pk:05d}-ADR")
        self.assertTrue(item.is_active)

    def test_adr_form_uses_country_and_region_select_and_hides_is_active(self):
        form = ResidenceAddressRecordForm()

        self.assertIn("person", form.fields)
        self.assertIn("country", form.fields)
        self.assertIn("region", form.fields)
        self.assertNotIn("is_active", form.fields)
        self.assertEqual(form.fields["country"].widget.attrs["id"], "adr-country-select")
        self.assertEqual(form.fields["region"].widget.attrs["id"], "adr-region-select")
        self.assertEqual(form.fields["country"].initial, self.country.pk)
        self.assertIn(("Москва", "Москва"), list(form.fields["region"].choices))
        self.assertIn(("Московская область", "Московская область"), list(form.fields["region"].choices))
        self.assertNotIn(("California", "California"), list(form.fields["region"].choices))

    def test_adr_form_renders_registration_autofill_url(self):
        response = self.client.get(reverse("adr_form_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'data-adr-registration-autofill-url="%s"' % reverse("adr_registration_autofill"),
            html=False,
        )

    def test_adr_registration_autofill_returns_contract_details_for_matching_country(self):
        employee_user = get_user_model().objects.create_user(
            username="adr-autofill-user",
            password="secret",
            first_name="Иван",
            last_name="Иванов",
            is_staff=True,
        )
        employee = Employee.objects.create(
            user=employee_user,
            patronymic="Иванович",
            person_record=self.person,
        )
        profile = ExpertProfile.objects.create(employee=employee, position=1)
        citizenship_ru = CitizenshipRecord.objects.create(
            person=self.person,
            country=self.country,
            status="Гражданство",
            identifier="Паспорт",
            number="123456",
            position=1,
        )
        citizenship_us = CitizenshipRecord.objects.create(
            person=self.person,
            country=self.us_country,
            status="ВНЖ",
            identifier="ID",
            number="999999",
            position=2,
        )
        ExpertContractDetails.objects.create(
            expert_profile=profile,
            citizenship_record=citizenship_ru,
            registration_postal_code="101000",
            registration_region="Москва",
            registration_locality="Москва",
            registration_street="Тверская",
            registration_building="1",
            registration_premise="10",
            registration_premise_part="A",
            registration_date=date(2026, 4, 19),
        )
        ExpertContractDetails.objects.create(
            expert_profile=profile,
            citizenship_record=citizenship_us,
            registration_postal_code="90001",
            registration_region="California",
            registration_locality="Los Angeles",
            registration_street="Sunset Blvd",
            registration_building="100",
            registration_premise="12",
            registration_premise_part="B",
            registration_date=date(2026, 5, 20),
        )

        response = self.client.get(
            reverse("adr_registration_autofill"),
            {"person_id": self.person.pk, "country_id": self.us_country.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "postal_code": "90001",
                "region": "California",
                "locality": "Los Angeles",
                "street": "Sunset Blvd",
                "building": "100",
                "premise": "12",
                "premise_part": "B",
                "valid_from": "2026-05-20",
            },
        )

    def test_adr_delete_rejects_last_record_for_person(self):
        item = ResidenceAddressRecord.objects.create(
            person=self.person,
            country=self.country,
            region="Москва",
            position=1,
        )

        response = self.client.post(reverse("adr_delete", args=[item.pk]))

        self.assertEqual(response.status_code, 409)
        self.assertIn(
            "У каждой записи в реестре лиц должна оставаться хотя бы одна запись в реестре адресов проживания.",
            response.content.decode("utf-8"),
        )
        self.assertTrue(ResidenceAddressRecord.objects.filter(pk=item.pk).exists())

    def test_adr_delete_allows_removing_non_last_record(self):
        first = ResidenceAddressRecord.objects.create(
            person=self.person,
            country=self.country,
            region="Москва",
            position=1,
        )
        second = ResidenceAddressRecord.objects.create(
            person=self.person,
            country=self.country,
            region="Московская область",
            position=2,
        )

        response = self.client.post(reverse("adr_delete", args=[second.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(ResidenceAddressRecord.objects.filter(pk=first.pk).exists())
        self.assertFalse(ResidenceAddressRecord.objects.filter(pk=second.pk).exists())

    def test_tel_create_sets_record_metadata(self):
        response = self.client.post(
            reverse("tel_form_create"),
            {
                "person": self.person.pk,
                "country": self.country.pk,
                "code": "+7",
                "phone_number": "+7 999 123-45-67",
                "valid_from": "2026-01-01",
                "valid_to": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        item = PhoneRecord.objects.get()
        self.assertEqual(item.country, self.country)
        self.assertEqual(item.code, "+7")
        self.assertEqual(item.phone_type, PhoneRecord.PHONE_TYPE_MOBILE)
        self.assertEqual(item.extension, "")
        self.assertEqual(item.region, "Москва")
        self.assertNotIn("+7", item.phone_number)
        self.assertFalse(item.phone_number.startswith("8"))
        self.assertIn("999", item.phone_number)
        self.assertEqual(item.phone_number, "(999) 123-45-67")
        self.assertEqual(item.record_author, "Иван Админов")
        self.assertEqual(item.record_date, date.today())
        self.assertEqual(item.valid_from, date(2026, 1, 1))
        self.assertEqual(item.formatted_id, f"{item.pk:05d}-TEL")
        self.assertTrue(item.is_active)
        self.assertTrue(item.is_primary)

    def test_tel_delete_rejects_last_record_for_person(self):
        item = PhoneRecord.objects.create(
            person=self.person,
            country=self.country,
            code="+7",
            phone_number="+7 999 123-45-67",
            position=1,
        )

        response = self.client.post(reverse("tel_delete", args=[item.pk]))

        self.assertEqual(response.status_code, 409)
        self.assertIn(
            "У каждой записи в реестре лиц должна оставаться хотя бы одна запись в реестре телефонных номеров.",
            response.content.decode("utf-8"),
        )
        self.assertTrue(PhoneRecord.objects.filter(pk=item.pk).exists())

    def test_tel_delete_allows_removing_non_last_record(self):
        first = PhoneRecord.objects.create(
            person=self.person,
            country=self.country,
            code="+7",
            phone_number="+7 999 123-45-67",
            position=1,
        )
        second = PhoneRecord.objects.create(
            person=self.person,
            country=self.country,
            code="+1",
            phone_number="+1 555 123-45-67",
            position=2,
        )

        response = self.client.post(reverse("tel_delete", args=[second.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(PhoneRecord.objects.filter(pk=first.pk).exists())
        self.assertFalse(PhoneRecord.objects.filter(pk=second.pk).exists())

    def test_tel_form_uses_country_select_and_phone_fields(self):
        form = PhoneRecordForm()

        self.assertIn("phone_type", form.fields)
        self.assertIn("country", form.fields)
        self.assertIn("region", form.fields)
        self.assertIn("extension", form.fields)
        self.assertIn("is_primary", form.fields)
        self.assertEqual(form.fields["phone_type"].widget.attrs["id"], "tel-type-select")
        self.assertEqual(form.fields["country"].widget.__class__.__name__, "Select")
        self.assertEqual(form.fields["country"].widget.attrs["id"], "tel-country-select")
        self.assertEqual(form.fields["is_primary"].widget.__class__.__name__, "Select")
        self.assertEqual(form.fields["code"].widget.attrs["id"], "tel-code-field")
        self.assertEqual(form.fields["phone_number"].widget.attrs["id"], "tel-phone-field")
        self.assertEqual(form.fields["region"].widget.attrs["id"], "tel-region-field")
        self.assertEqual(form.fields["extension"].widget.attrs["id"], "tel-extension-field")
        self.assertEqual(form.fields["phone_type"].initial, PhoneRecord.PHONE_TYPE_MOBILE)
        self.assertTrue(form.fields["is_primary"].initial)
        self.assertEqual(form.fields["code"].initial, "+7")
        self.assertEqual(form.fields["valid_from"].initial, date.today())
        self.assertEqual(form.fields["code"].widget.attrs["placeholder"], "Код")
        self.assertIn('"flag": "🇷🇺"', form.country_meta_json)
        self.assertIn('"mobilePlaceholder":', form.country_meta_json)
        self.assertIn('"landlinePlaceholder":', form.country_meta_json)
        self.assertTrue(form.fields["region"].widget.attrs["readonly"])

    def test_tel_form_show_region_field_only_for_russia(self):
        default_form = PhoneRecordForm()
        us_form = PhoneRecordForm(data={"country": self.us_country.pk})

        self.assertTrue(default_form.show_region_field)
        self.assertFalse(us_form.show_region_field)

    def test_tel_form_normalizes_phone_number_by_country(self):
        form = PhoneRecordForm(
            data={
                "person": self.person.pk,
                "country": self.country.pk,
                "code": "",
                "phone_number": "9991234567",
                "valid_from": "",
                "valid_to": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["code"], "+7")
        self.assertIn("999", form.cleaned_data["phone_number"])
        self.assertNotEqual(form.cleaned_data["phone_number"], "9991234567")
        self.assertNotIn("+7", form.cleaned_data["phone_number"])
        self.assertFalse(form.cleaned_data["phone_number"].startswith("8"))
        self.assertEqual(form.cleaned_data["region"], "Москва")

    def test_tel_form_strips_country_code_from_saved_phone_number(self):
        form = PhoneRecordForm(
            data={
                "person": self.person.pk,
                "phone_type": PhoneRecord.PHONE_TYPE_MOBILE,
                "country": self.country.pk,
                "code": "+7",
                "phone_number": "+7 999 123-45-67",
                "valid_from": "",
                "valid_to": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["code"], "+7")
        self.assertNotIn("+7", form.cleaned_data["phone_number"])
        self.assertIn("999", form.cleaned_data["phone_number"])
        self.assertFalse(form.cleaned_data["phone_number"].startswith("8"))
        self.assertEqual(form.cleaned_data["phone_number"], "(999) 123-45-67")
        self.assertEqual(form.cleaned_data["region"], "Москва")

    def test_tel_form_keeps_leading_seven_when_it_is_local_number_digit(self):
        form = PhoneRecordForm(
            data={
                "person": self.person.pk,
                "phone_type": PhoneRecord.PHONE_TYPE_MOBILE,
                "country": self.country.pk,
                "code": "+7",
                "phone_number": "705 186-10-36",
                "valid_from": "",
                "valid_to": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["code"], "+7")
        self.assertEqual(form.cleaned_data["phone_number"], "(705) 186-10-36")
        self.assertEqual(form.cleaned_data["region"], "")

    def test_tel_form_keeps_landline_number_unformatted_and_stores_extension(self):
        form = PhoneRecordForm(
            data={
                "person": self.person.pk,
                "phone_type": PhoneRecord.PHONE_TYPE_LANDLINE,
                "country": self.country.pk,
                "code": "+7",
                "phone_number": "+7 (495) 123-45-67",
                "region": "Произвольный регион",
                "extension": "321",
                "valid_from": "",
                "valid_to": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["code"], "+7")
        self.assertEqual(form.cleaned_data["phone_type"], PhoneRecord.PHONE_TYPE_LANDLINE)
        self.assertEqual(form.cleaned_data["phone_number"], "(495) 123-45-67")
        self.assertEqual(form.cleaned_data["region"], "Москва")
        self.assertEqual(form.cleaned_data["extension"], "321")

    def test_tel_create_stores_landline_extension(self):
        response = self.client.post(
            reverse("tel_form_create"),
            {
                "person": self.person.pk,
                "phone_type": PhoneRecord.PHONE_TYPE_LANDLINE,
                "country": self.country.pk,
                "code": "+7",
                "phone_number": "+7 (495) 123-45-67",
                "region": "Лишнее значение",
                "extension": "321",
                "valid_from": "",
                "valid_to": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        item = PhoneRecord.objects.get()
        self.assertEqual(item.phone_type, PhoneRecord.PHONE_TYPE_LANDLINE)
        self.assertEqual(item.region, "Москва")
        self.assertEqual(item.phone_number, "(495) 123-45-67")
        self.assertEqual(item.extension, "321")

    def test_tel_form_rejects_ambiguous_ru_landline_number(self):
        self._create_numcap_range(code="495", begin="1200000", end="1299999", region="Московская область", position=2)
        form = PhoneRecordForm(
            data={
                "person": self.person.pk,
                "phone_type": PhoneRecord.PHONE_TYPE_LANDLINE,
                "country": self.country.pk,
                "code": "+7",
                "phone_number": "49512",
                "region": "",
                "extension": "",
                "valid_from": "",
                "valid_to": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("phone_number", form.errors)

    def test_tel_ru_landline_lookup_returns_unique_region_and_formatting(self):
        response = self.client.get(
            reverse("tel_ru_landline_lookup"),
            {"phone_number": "8 (495) 123-45-67"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["digits"], "4951234567")
        self.assertTrue(payload["unique"])
        self.assertTrue(payload["exact"])
        self.assertEqual(payload["region"], "Москва")
        self.assertEqual(payload["formatted_number"], "(495) 123-45-67")

    def test_tel_ru_landline_lookup_returns_mobile_region_and_formatting(self):
        response = self.client.get(
            reverse("tel_ru_landline_lookup"),
            {"phone_number": "+7 999 123-45-67"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["digits"], "9991234567")
        self.assertTrue(payload["unique"])
        self.assertTrue(payload["exact"])
        self.assertEqual(payload["region"], "Москва")
        self.assertEqual(payload["formatted_number"], "(999) 123-45-67")

    def test_tel_ru_landline_lookup_formats_4_and_5_digit_area_codes(self):
        self._create_numcap_range(code="4722", begin="120000", end="129999", region="Белгород", position=3)
        self._create_numcap_range(code="85145", begin="10000", end="19999", region="Анадырь", position=4)

        response_4 = self.client.get(
            reverse("tel_ru_landline_lookup"),
            {"phone_number": "4722123456"},
        )
        response_5 = self.client.get(
            reverse("tel_ru_landline_lookup"),
            {"phone_number": "8514512345"},
        )

        self.assertEqual(response_4.status_code, 200)
        self.assertEqual(response_5.status_code, 200)
        self.assertEqual(response_4.json()["formatted_number"], "(4722) 12-34-56")
        self.assertEqual(response_5.json()["formatted_number"], "(85145) 1-23-45")

    def test_tel_ru_landline_lookup_formats_partial_ambiguous_number_without_region(self):
        self._create_numcap_range(code="495", begin="1200000", end="1299999", region="Московская область", position=2)

        response = self.client.get(
            reverse("tel_ru_landline_lookup"),
            {"phone_number": "49512"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["unique"])
        self.assertFalse(payload["exact"])
        self.assertEqual(payload["region"], "")
        self.assertEqual(payload["formatted_number"], "(495) 12")

    def test_tel_create_sets_valid_from_to_record_date_when_missing(self):
        response = self.client.post(
            reverse("tel_form_create"),
            {
                "person": self.person.pk,
                "country": self.country.pk,
                "code": "+7",
                "phone_number": "9991234567",
                "valid_from": "",
                "valid_to": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        item = PhoneRecord.objects.get()
        self.assertEqual(item.record_date, date.today())
        self.assertEqual(item.valid_from, date.today())
        self.assertTrue(item.is_primary)

    def test_tel_create_primary_phone_unsets_previous_primary_for_same_person(self):
        first = PhoneRecord.objects.create(
            person=self.person,
            country=self.country,
            code="+7",
            phone_number="(999) 123-45-67",
            is_primary=True,
            position=1,
        )

        response = self.client.post(
            reverse("tel_form_create"),
            {
                "person": self.person.pk,
                "country": self.country.pk,
                "code": "+7",
                "phone_number": "9997654321",
                "is_primary": "on",
                "valid_from": "",
                "valid_to": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        second = PhoneRecord.objects.exclude(pk=first.pk).get()
        self.assertFalse(first.is_primary)
        self.assertTrue(second.is_primary)

    def test_tel_edit_can_make_another_phone_primary(self):
        first = PhoneRecord.objects.create(
            person=self.person,
            country=self.country,
            code="+7",
            phone_number="(999) 123-45-67",
            is_primary=True,
            position=1,
        )
        second = PhoneRecord.objects.create(
            person=self.person,
            country=self.country,
            code="+7",
            phone_number="(999) 765-43-21",
            is_primary=False,
            position=2,
        )

        response = self.client.post(
            reverse("tel_form_edit", args=[second.pk]),
            {
                "person": self.person.pk,
                "phone_type": PhoneRecord.PHONE_TYPE_MOBILE,
                "country": self.country.pk,
                "code": "+7",
                "phone_number": "(999) 765-43-21",
                "is_primary": "on",
                "valid_from": "",
                "valid_to": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_primary)
        self.assertTrue(second.is_primary)

    def test_eml_create_sets_record_metadata(self):
        response = self.client.post(
            reverse("eml_form_create"),
            {
                "person": self.person.pk,
                "email": "ivanov@example.com",
                "valid_from": "2026-01-01",
                "valid_to": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        item = EmailRecord.objects.get()
        self.assertEqual(item.person, self.person)
        self.assertEqual(item.email, "ivanov@example.com")
        self.assertEqual(item.record_author, "Иван Админов")
        self.assertEqual(item.record_date, date.today())
        self.assertEqual(item.valid_from, date(2026, 1, 1))
        self.assertEqual(item.formatted_id, f"{item.pk:05d}-EML")
        self.assertTrue(item.is_active)

    def test_eml_form_uses_person_select_and_hides_is_active(self):
        form = EmailRecordForm()

        self.assertIn("person", form.fields)
        self.assertIn("email", form.fields)
        self.assertNotIn("is_active", form.fields)
        self.assertEqual(form.fields["email"].widget.__class__.__name__, "EmailInput")
        self.assertEqual(form.fields["valid_from"].initial, date.today())

    def test_eml_form_keeps_managed_email_readonly_and_unchanged(self):
        item = EmailRecord.objects.create(
            person=self.person,
            email="managed@example.com",
            is_user_managed=True,
            user_kind="employee",
            position=1,
        )

        form = EmailRecordForm(
            data={
                "person": self.person.pk,
                "email": "changed@example.com",
                "valid_from": "2026-01-01",
                "valid_to": "",
            },
            instance=item,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["email"], "managed@example.com")

    def test_eml_create_sets_valid_from_to_record_date_when_missing(self):
        response = self.client.post(
            reverse("eml_form_create"),
            {
                "person": self.person.pk,
                "email": "ivanov@example.com",
                "valid_from": "",
                "valid_to": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        item = EmailRecord.objects.get()
        self.assertEqual(item.record_date, date.today())
        self.assertEqual(item.valid_from, date.today())

    def test_eml_table_partial_supports_pagination(self):
        for idx in range(1, 53):
            EmailRecord.objects.create(
                person=self.person,
                email=f"user{idx}@example.com",
                position=idx,
            )

        response = self.client.get(reverse("eml_table_partial"), {"eml_page": 2})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="eml-page-input"')
        self.assertContains(response, "user51@example.com")
        self.assertContains(response, "user52@example.com")
        self.assertNotContains(response, "user50@example.com")

    def test_adr_table_partial_supports_pagination(self):
        for idx in range(1, 53):
            ResidenceAddressRecord.objects.create(
                person=self.person,
                country=self.country,
                region=f"Регион {idx}",
                locality=f"НП {idx}",
                position=idx,
            )

        response = self.client.get(reverse("adr_table_partial"), {"adr_page": 2})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="adr-page-input"')
        self.assertContains(response, "Регион 51")
        self.assertContains(response, "Регион 52")
        self.assertNotContains(response, "Регион 50")

    def test_eml_templates_hide_is_active_column_and_field(self):
        form_response = self.client.get(reverse("eml_form_create"))
        table_response = self.client.get(reverse("eml_table_partial"))

        self.assertEqual(form_response.status_code, 200)
        self.assertEqual(table_response.status_code, 200)
        self.assertNotContains(form_response, "Актуален")
        self.assertNotContains(table_response, "Актуален")

    def test_eml_form_shows_readonly_user_kind_field(self):
        self.person.user_kind = "employee"
        self.person.save(update_fields=["user_kind"])
        item = EmailRecord.objects.create(
            person=self.person,
            email="linked@example.com",
            user_kind="employee",
            position=1,
        )

        create_response = self.client.get(reverse("eml_form_create"), {"prs_ids": str(self.person.pk)})
        edit_response = self.client.get(reverse("eml_form_edit", args=[item.pk]))

        self.assertContains(create_response, "Пользователь")
        self.assertContains(create_response, 'class="form-control readonly-field"', html=False)
        self.assertContains(create_response, 'value="Сотрудник"', html=False)
        self.assertContains(edit_response, 'value="Сотрудник"', html=False)

    def test_person_and_email_tables_show_user_kind_columns(self):
        linked_user = get_user_model().objects.create_user(
            username="linked@example.com",
            email="linked@example.com",
            password="secret",
            is_staff=True,
            first_name="Связанный",
            last_name="Пользователь",
        )
        managed_email = EmailRecord.objects.create(
            person=self.person,
            email="linked@example.com",
            is_user_managed=True,
            user_kind="employee",
            position=1,
        )
        employee = Employee.objects.create(
            user=linked_user,
            person_record=self.person,
            managed_email_record=managed_email,
            patronymic="",
            employment="",
            organization="",
            job_title="",
            role="",
            position=1,
        )
        self.person.user_kind = "employee"
        self.person.save(update_fields=["user_kind"])

        prs_response = self.client.get(reverse("prs_table_partial"))
        eml_response = self.client.get(reverse("eml_table_partial"))

        self.assertContains(prs_response, "<th style=\"width:26%\">Пользователь</th>", html=False)
        self.assertContains(prs_response, "Сотрудник")
        self.assertContains(eml_response, "<th>Пользователь</th>", html=False)
        self.assertContains(eml_response, "Сотрудник")
        employee.delete()

    def test_non_staff_cannot_reorder_contact_registry_rows(self):
        second_citizenship = CitizenshipRecord.objects.create(
            person=self.person,
            country=self.country,
            status="Статус 2",
            identifier="ID-2",
            number="NUM-2",
            position=2,
        )
        second_address = ResidenceAddressRecord.objects.create(
            person=self.person,
            country=self.country,
            region="Москва",
            locality="Москва",
            street="Тверская",
            building="2",
            position=2,
        )
        second_phone = PhoneRecord.objects.create(
            person=self.person,
            country=self.country,
            code="+7",
            phone_type=PhoneRecord.PHONE_TYPE_MOBILE,
            region="Москва",
            phone_number="9990000002",
            is_primary=False,
            position=2,
        )
        second_email = EmailRecord.objects.create(
            person=self.person,
            email="second@example.com",
            position=2,
        )
        non_staff_user = get_user_model().objects.create_user(
            username="contacts-nonstaff",
            email="contacts-nonstaff@example.com",
            password="secret",
            is_staff=False,
        )
        self.client.force_login(non_staff_user)

        for url_name, item in (
            ("ctz_move_up", second_citizenship),
            ("adr_move_up", second_address),
            ("tel_move_up", second_phone),
            ("eml_move_up", second_email),
        ):
            response = self.client.post(reverse(url_name, args=[item.pk]))
            self.assertEqual(response.status_code, 302)

        second_citizenship.refresh_from_db()
        second_address.refresh_from_db()
        second_phone.refresh_from_db()
        second_email.refresh_from_db()
        self.assertEqual(second_citizenship.position, 2)
        self.assertEqual(second_address.position, 2)
        self.assertEqual(second_phone.position, 2)
        self.assertEqual(second_email.position, 2)

    def test_eml_delete_rejects_last_record_for_person(self):
        item = EmailRecord.objects.create(
            person=self.person,
            email="only@example.com",
            position=1,
        )

        response = self.client.post(reverse("eml_delete", args=[item.pk]))

        self.assertEqual(response.status_code, 409)
        self.assertIn(
            "У каждой записи в реестре лиц должна оставаться хотя бы одна запись в реестре адресов электронной почты.",
            response.content.decode("utf-8"),
        )
        self.assertTrue(EmailRecord.objects.filter(pk=item.pk).exists())

    def test_eml_delete_allows_removing_non_last_record(self):
        first = EmailRecord.objects.create(
            person=self.person,
            email="first@example.com",
            position=1,
        )
        second = EmailRecord.objects.create(
            person=self.person,
            email="second@example.com",
            position=2,
        )

        response = self.client.post(reverse("eml_delete", args=[second.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(EmailRecord.objects.filter(pk=first.pk).exists())
        self.assertFalse(EmailRecord.objects.filter(pk=second.pk).exists())

    def test_contacts_records_compute_is_active_from_valid_to(self):
        position = PositionRecord.objects.create(
            person=self.person,
            organization_short_name='ООО "Альфа"',
            job_title="Генеральный директор",
            valid_to=None,
            position=1,
        )
        citizenship = CitizenshipRecord.objects.create(
            person=self.person,
            country=self.country,
            status=CitizenshipRecordForm.STATUS_CITIZENSHIP,
            valid_to=date(2026, 12, 31),
            position=1,
        )
        phone = PhoneRecord.objects.create(
            person=self.person,
            country=self.country,
            code="+7",
            phone_number="(999) 123-45-67",
            valid_to=date(2026, 12, 31),
            position=1,
        )
        email = EmailRecord.objects.create(
            person=self.person,
            email="inactive@example.com",
            valid_to=date(2026, 12, 31),
            position=1,
        )

        self.assertTrue(position.is_active)
        self.assertFalse(citizenship.is_active)
        self.assertFalse(phone.is_active)
        self.assertFalse(email.is_active)

    def test_tel_table_partial_supports_pagination(self):
        for idx in range(1, 53):
            PhoneRecord.objects.create(
                person=self.person,
                country=self.country,
                code=f"+{idx}",
                phone_number=f"7999000{idx:02d}",
                position=idx,
            )

        response = self.client.get(reverse("tel_table_partial"), {"tel_page": 2})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="tel-page-input"')
        self.assertContains(response, "799900051")
        self.assertContains(response, "799900052")
        self.assertNotContains(response, "799900050")

    def test_tel_table_partial_renders_type_and_full_phone_display(self):
        PhoneRecord.objects.create(
            person=self.person,
            country=self.country,
            code="+7",
            phone_type=PhoneRecord.PHONE_TYPE_LANDLINE,
            phone_number="(495) 123-45-67",
            extension="321",
            is_primary=True,
            position=1,
        )
        PhoneRecord.objects.create(
            person=self.person,
            country=self.country,
            code="+7",
            phone_type=PhoneRecord.PHONE_TYPE_MOBILE,
            phone_number="(999) 123-45-67",
            is_primary=False,
            position=2,
        )

        response = self.client.get(reverse("tel_table_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<th>Тип</th>", html=False)
        self.assertContains(response, "<th class=\"text-center\">Основной</th>", html=False)
        self.assertContains(response, "гор.")
        self.assertContains(response, "моб.")
        self.assertContains(response, "+7 (495) 123-45-67 доб. 321")
        self.assertContains(response, "+7 (999) 123-45-67")
        self.assertContains(response, "bi-check-square")
        self.assertContains(response, "bi-square")

    def test_ctz_table_partial_supports_pagination(self):
        for idx in range(1, 53):
            CitizenshipRecord.objects.create(
                person=self.person,
                country=self.country,
                status=f"Статус {idx}",
                identifier=f"ID {idx}",
                number=f"NUM {idx}",
                position=idx,
            )

        response = self.client.get(reverse("ctz_table_partial"), {"ctz_page": 2})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="ctz-page-input"')
        self.assertContains(response, "Статус 51")
        self.assertContains(response, "Статус 52")
        self.assertNotContains(response, "Статус 50")

    def test_prs_table_partial_supports_pagination(self):
        for idx in range(2, 53):
            PersonRecord.objects.create(
                last_name=f"Фамилия {idx}",
                first_name="Имя",
                middle_name="Отчество",
                full_name_genitive=f"Фамилии {idx} Имени Отчеству",
                gender="female" if idx % 2 else "male",
                position=idx,
            )

        response = self.client.get(reverse("prs_table_partial"), {"prs_page": 2})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="prs-page-input"')
        self.assertContains(response, "Фамилия 51")
        self.assertContains(response, "Фамилия 52")
        self.assertContains(response, "ФИО (полное) в родительном падеже")
        self.assertContains(response, "Пол")
        self.assertContains(response, "Фамилии 51 Имени Отчеству")
        self.assertContains(response, "женский")
        self.assertNotContains(response, "Фамилия 50")

    def test_prs_autocomplete_returns_full_person_name_by_surname(self):
        second_person = PersonRecord.objects.create(
            last_name="Иваненко",
            first_name="Петр",
            middle_name="Сергеевич",
            position=2,
        )

        response = self.client.get(reverse("prs_autocomplete"), {"q": "Иван"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreaterEqual(payload["total_count"], 2)
        display_names = [item["display_name"] for item in payload["results"]]
        self.assertIn(self.person.display_name, display_names)
        self.assertIn(second_person.display_name, display_names)

    def test_prs_birth_date_returns_person_birth_date(self):
        response = self.client.get(
            reverse("prs_birth_date"),
            {"person_id": self.person.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["birth_date"], "1990-05-17")

    def test_prs_filter_options_returns_all_prs_values(self):
        second_person = PersonRecord.objects.create(
            last_name="Петров",
            first_name="Петр",
            middle_name="Петрович",
            position=2,
        )

        response = self.client.get(reverse("prs_filter_options"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total_count"], 2)
        self.assertEqual(
            [item["formatted_id"] for item in payload["results"]],
            [f"{self.person.pk:05d}-PRS", f"{second_person.pk:05d}-PRS"],
        )
        self.assertEqual(payload["results"][0]["summary_label"], "Иванов И.И.")
        self.assertEqual(payload["results"][1]["summary_label"], "Петров П.П.")

    def test_prs_filter_options_supports_search_and_selected_ids(self):
        second_person = PersonRecord.objects.create(
            last_name="Петров",
            first_name="Петр",
            middle_name="Петрович",
            position=2,
        )

        search_response = self.client.get(reverse("prs_filter_options"), {"q": "Иванов"})
        ids_response = self.client.get(reverse("prs_filter_options"), {"ids": [str(second_person.pk)]})

        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(ids_response.status_code, 200)
        self.assertEqual(search_response.json()["total_count"], 1)
        self.assertEqual(search_response.json()["results"][0]["formatted_id"], f"{self.person.pk:05d}-PRS")
        self.assertEqual(ids_response.json()["total_count"], 1)
        self.assertEqual(ids_response.json()["results"][0]["formatted_id"], f"{second_person.pk:05d}-PRS")

    def test_contact_tables_filter_by_selected_prs(self):
        second_person = PersonRecord.objects.create(
            last_name="Петров",
            first_name="Петр",
            middle_name="Петрович",
            position=2,
        )
        CitizenshipRecord.objects.create(
            person=self.person,
            country=self.country,
            status="Гражданство",
            identifier="Паспорт",
            number="111",
            position=1,
        )
        CitizenshipRecord.objects.create(
            person=second_person,
            country=self.country,
            status="ВНЖ",
            identifier="ВНЖ",
            number="222",
            position=2,
        )
        PositionRecord.objects.create(
            person=self.person,
            organization_short_name='ООО "Альфа"',
            job_title="Директор",
            position=1,
        )
        PositionRecord.objects.create(
            person=second_person,
            organization_short_name='ООО "Бета"',
            job_title="Менеджер",
            position=2,
        )
        PhoneRecord.objects.create(
            person=self.person,
            country=self.country,
            code="+7",
            phone_number="(999) 123-45-67",
            position=1,
        )
        PhoneRecord.objects.create(
            person=second_person,
            country=self.country,
            code="+7",
            phone_number="(999) 765-43-21",
            position=2,
        )
        ResidenceAddressRecord.objects.create(
            person=self.person,
            country=self.country,
            region="Москва",
            locality="Москва",
            position=1,
        )
        ResidenceAddressRecord.objects.create(
            person=second_person,
            country=self.country,
            region="Московская область",
            locality="Химки",
            position=2,
        )
        EmailRecord.objects.create(
            person=self.person,
            email="first@example.com",
            position=1,
        )
        EmailRecord.objects.create(
            person=second_person,
            email="second@example.com",
            position=2,
        )

        params = {"prs_ids": str(self.person.pk)}
        prs_response = self.client.get(reverse("prs_table_partial"), params)
        ctz_response = self.client.get(reverse("ctz_table_partial"), params)
        adr_response = self.client.get(reverse("adr_table_partial"), params)
        psn_response = self.client.get(reverse("psn_table_partial"), params)
        tel_response = self.client.get(reverse("tel_table_partial"), params)
        eml_response = self.client.get(reverse("eml_table_partial"), params)

        self.assertContains(prs_response, self.person.last_name)
        self.assertContains(prs_response, self.person.first_name)
        self.assertContains(prs_response, self.person.middle_name)
        self.assertNotContains(prs_response, second_person.last_name)
        self.assertNotContains(prs_response, second_person.first_name)
        self.assertNotContains(prs_response, second_person.middle_name)
        self.assertContains(ctz_response, "111")
        self.assertNotContains(ctz_response, "222")
        self.assertContains(adr_response, "Москва")
        self.assertNotContains(adr_response, "Химки")
        self.assertContains(psn_response, "Директор")
        self.assertNotContains(psn_response, "Менеджер")
        self.assertContains(tel_response, "(999) 123-45-67")
        self.assertNotContains(tel_response, "(999) 765-43-21")
        self.assertContains(eml_response, "first@example.com")
        self.assertNotContains(eml_response, "second@example.com")

    def test_contact_create_forms_preselect_single_master_filtered_prs(self):
        params = {"prs_ids": str(self.person.pk)}
        expected_hidden = f'<input type="hidden" name="person" value="{self.person.pk}"'
        expected_label = f"{self.person.formatted_id} {self.person.display_name}"

        ctz_response = self.client.get(reverse("ctz_form_create"), params)
        adr_response = self.client.get(reverse("adr_form_create"), params)
        psn_response = self.client.get(reverse("psn_form_create"), params)
        tel_response = self.client.get(reverse("tel_form_create"), params)
        eml_response = self.client.get(reverse("eml_form_create"), params)

        self.assertContains(ctz_response, expected_hidden, html=False)
        self.assertContains(adr_response, expected_hidden, html=False)
        self.assertContains(psn_response, expected_hidden, html=False)
        self.assertContains(tel_response, expected_hidden, html=False)
        self.assertContains(eml_response, expected_hidden, html=False)
        self.assertContains(ctz_response, expected_label)
        self.assertContains(adr_response, expected_label)
        self.assertContains(psn_response, expected_label)
        self.assertContains(tel_response, expected_label)
        self.assertContains(eml_response, expected_label)
