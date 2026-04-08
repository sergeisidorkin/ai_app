from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from classifiers_app.models import BusinessEntityIdentifierRecord, BusinessEntityRecord, LegalEntityRecord, OKSMCountry
from proposals_app.models import ProposalRegistration

from .forms import PositionRecordForm
from .models import CONTACT_POSITION_SOURCE, PersonRecord, PositionRecord


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
        self.person = PersonRecord.objects.create(
            last_name="Иванов",
            first_name="Иван",
            middle_name="Иванович",
            citizenship=self.country,
            identifier="Паспорт",
            number="1111 222222",
            position=1,
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

    def test_position_form_uses_only_active_short_names(self):
        self._create_active_name(short_name='ООО "Альфа"', position=1, is_active=True)
        self._create_active_name(short_name='ООО "Бета"', position=2, is_active=False)

        form = PositionRecordForm()
        choice_values = [value for value, _label in form.fields["organization_short_name"].choices]

        self.assertIn('ООО "Альфа"', choice_values)
        self.assertNotIn('ООО "Бета"', choice_values)

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
                "citizenship": self.country.pk,
                "identifier": self.person.identifier,
                "number": self.person.number,
            },
        )

        self.assertEqual(response.status_code, 200)
        position.refresh_from_db()
        self.assertEqual(position.source, "")

    def test_prs_table_partial_supports_pagination(self):
        for idx in range(2, 53):
            PersonRecord.objects.create(
                last_name=f"Фамилия {idx}",
                first_name="Имя",
                middle_name="Отчество",
                position=idx,
            )

        response = self.client.get(reverse("prs_table_partial"), {"prs_page": 2})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="prs-page-input"')
        self.assertContains(response, "Фамилия 51")
        self.assertContains(response, "Фамилия 52")
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
