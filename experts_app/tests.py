import csv
import io
import json
import os
import re
import shutil
import tempfile
from datetime import date
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from classifiers_app.models import OKSMCountry, TerritorialDivision
from experts_app.forms import ExpertContractDetailsForm
from contacts_app.models import CitizenshipRecord, EmailRecord, PersonRecord, PhoneRecord, SpecialtyRecord
from experts_app.models import ExpertContractDetails, ExpertProfile, ExpertProfileSpecialty, ExpertSpecialty
from group_app.models import GroupMember, OrgUnit
from policy_app.models import (
    ADMIN_GROUP,
    DEPARTMENT_HEAD_GROUP,
    DIRECTION_DIRECTOR_GROUP,
    DIRECTOR_GROUP,
    ExpertiseDirection,
    Grade,
)
from users_app.models import Employee


class ExpertProfileUiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="experts-ui-admin",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)

        employee_user = get_user_model().objects.create_user(
            username="experts-ui-user",
            password="secret",
            first_name="Иван",
            last_name="Иванов",
            email="expert@example.com",
            is_staff=True,
        )
        self.employee = Employee.objects.create(
            user=employee_user,
            patronymic="Иванович",
        )
        self.profile = ExpertProfile.objects.create(employee=self.employee, position=1)

    def test_profile_edit_form_does_not_render_yandex_mail_field(self):
        response = self.client.get(reverse("epr_form_edit", args=[self.profile.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Яндекс Почта")
        self.assertNotContains(response, 'name="yandex_mail"', html=False)

    def test_experts_partial_does_not_render_yandex_mail_column(self):
        response = self.client.get(reverse("experts_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Яндекс Почта")

    def test_experts_partial_no_longer_renders_contract_details_table(self):
        response = self.client.get(reverse("experts_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Реквизиты физлиц-исполнителей")

    def test_profile_edit_creates_contact_specialty_record(self):
        person = PersonRecord.objects.create(last_name="Иванов", first_name="Иван", position=1)
        self.employee.person_record = person
        self.employee.save(update_fields=["person_record"])
        specialty = ExpertSpecialty.objects.create(specialty="Геолог", position=1)

        response = self.client.post(
            reverse("epr_form_edit", args=[self.profile.pk]),
            {
                "expertise_direction": "",
                "professional_status": "",
                "professional_status_short": "",
                "grade": "",
                "status": "",
                "specialty_id": [str(specialty.pk)],
                "contact_specialty_record_id": [""],
            },
        )

        self.assertEqual(response.status_code, 200)
        record = SpecialtyRecord.objects.get()
        self.assertEqual(record.person, person)
        self.assertEqual(record.specialty, specialty)
        self.assertEqual(record.valid_from, date.today())
        self.assertEqual(record.valid_to, None)
        self.assertEqual(record.source, "[Исполнители / База физлиц-исполнителей]")
        link = ExpertProfileSpecialty.objects.get(profile=self.profile)
        self.assertEqual(link.specialty, specialty)
        self.assertEqual(link.contact_specialty_record, record)

    def test_profile_edit_removes_specialty_by_closing_contact_record(self):
        person = PersonRecord.objects.create(last_name="Иванов", first_name="Иван", position=1)
        self.employee.person_record = person
        self.employee.save(update_fields=["person_record"])
        specialty = ExpertSpecialty.objects.create(specialty="Геолог", position=1)
        record = SpecialtyRecord.objects.create(
            person=person,
            specialty=specialty,
            valid_from=date(2026, 1, 1),
            position=1,
        )
        ExpertProfileSpecialty.objects.create(
            profile=self.profile,
            specialty=specialty,
            contact_specialty_record=record,
            rank=1,
        )

        response = self.client.post(
            reverse("epr_form_edit", args=[self.profile.pk]),
            {
                "expertise_direction": "",
                "professional_status": "",
                "professional_status_short": "",
                "grade": "",
                "status": "",
                "specialty_id": [""],
                "contact_specialty_record_id": [str(record.pk)],
            },
        )

        self.assertEqual(response.status_code, 200)
        record.refresh_from_db()
        self.assertEqual(record.valid_to, date.today())
        self.assertFalse(record.is_active)
        self.assertFalse(ExpertProfileSpecialty.objects.filter(profile=self.profile).exists())

    def test_experts_partial_auto_fills_extra_email_and_phones_from_contacts(self):
        person = PersonRecord.objects.create(
            last_name="Иванов",
            first_name="Иван",
            middle_name="Иванович",
            position=1,
        )
        managed_email = EmailRecord.objects.create(
            person=person,
            email="expert@example.com",
            position=1,
        )
        EmailRecord.objects.create(
            person=person,
            email="extra@example.com",
            position=2,
        )
        PhoneRecord.objects.create(
            person=person,
            code="+7",
            phone_number="(999) 123-45-67",
            is_primary=True,
            position=1,
        )
        PhoneRecord.objects.create(
            person=person,
            code="+7",
            phone_number="(999) 765-43-21",
            is_primary=False,
            position=2,
        )
        self.employee.person_record = person
        self.employee.managed_email_record = managed_email
        self.employee.save(update_fields=["person_record", "managed_email_record"])
        ExpertProfile.objects.filter(pk=self.profile.pk).update(extra_email="old@example.com", extra_phone="old-phone")

        response = self.client.get(reverse("experts_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "extra@example.com")
        self.assertContains(response, "+7 (999) 123-45-67")
        self.assertContains(response, "+7 (999) 765-43-21")
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.extra_email, "extra@example.com")
        self.assertEqual(self.profile.extra_phone, "+7 (999) 765-43-21")

    def test_profile_edit_form_locks_and_ignores_auto_contact_fields(self):
        person = PersonRecord.objects.create(
            last_name="Иванов",
            first_name="Иван",
            middle_name="Иванович",
            position=1,
        )
        managed_email = EmailRecord.objects.create(
            person=person,
            email="expert@example.com",
            position=1,
        )
        EmailRecord.objects.create(
            person=person,
            email="extra@example.com",
            position=2,
        )
        PhoneRecord.objects.create(
            person=person,
            code="+7",
            phone_number="(999) 123-45-67",
            is_primary=True,
            position=1,
        )
        PhoneRecord.objects.create(
            person=person,
            code="+7",
            phone_number="(999) 765-43-21",
            is_primary=False,
            position=2,
        )
        self.employee.person_record = person
        self.employee.managed_email_record = managed_email
        self.employee.save(update_fields=["person_record", "managed_email_record"])

        form_response = self.client.get(reverse("epr_form_edit", args=[self.profile.pk]))

        self.assertEqual(form_response.status_code, 200)
        self.assertContains(form_response, 'name="extra_email"', html=False)
        self.assertContains(form_response, 'name="extra_phone"', html=False)
        self.assertContains(form_response, 'disabled', html=False)
        self.assertContains(form_response, 'value="extra@example.com"', html=False)
        self.assertContains(form_response, 'value="+7 (999) 765-43-21"', html=False)

        post_response = self.client.post(
            reverse("epr_form_edit", args=[self.profile.pk]),
            {
                "extra_email": "tampered@example.com",
                "extra_phone": "tampered-phone",
                "expertise_direction": "",
                "professional_status": "Статус",
                "professional_status_short": "",
                "grade": "",
                "country": "",
                "region": "",
                "status": "",
                "specialty_id": "",
            },
        )

        self.assertEqual(post_response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.extra_email, "extra@example.com")
        self.assertEqual(self.profile.extra_phone, "+7 (999) 765-43-21")

    def test_experts_partial_uses_only_active_contact_records(self):
        person = PersonRecord.objects.create(
            last_name="Иванов",
            first_name="Иван",
            middle_name="Иванович",
            position=1,
        )
        managed_email = EmailRecord.objects.create(
            person=person,
            email="expert@example.com",
            is_active=True,
            position=1,
        )
        EmailRecord.objects.create(
            person=person,
            email="inactive-extra@example.com",
            valid_to=date(2026, 1, 1),
            position=2,
        )
        EmailRecord.objects.create(
            person=person,
            email="active-extra@example.com",
            is_active=True,
            position=3,
        )
        PhoneRecord.objects.create(
            person=person,
            code="+7",
            phone_number="(999) 111-11-11",
            is_primary=True,
            valid_to=date(2026, 1, 1),
            position=1,
        )
        PhoneRecord.objects.create(
            person=person,
            code="+7",
            phone_number="(999) 222-22-22",
            is_primary=True,
            is_active=True,
            position=2,
        )
        PhoneRecord.objects.create(
            person=person,
            code="+7",
            phone_number="(999) 333-33-33",
            is_primary=False,
            valid_to=date(2026, 1, 1),
            position=3,
        )
        PhoneRecord.objects.create(
            person=person,
            code="+7",
            phone_number="(999) 444-44-44",
            is_primary=False,
            is_active=True,
            position=4,
        )
        self.employee.person_record = person
        self.employee.managed_email_record = managed_email
        self.employee.save(update_fields=["person_record", "managed_email_record"])

        response = self.client.get(reverse("experts_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "active-extra@example.com")
        self.assertNotContains(response, "inactive-extra@example.com")
        self.assertContains(response, "+7 (999) 222-22-22")
        self.assertContains(response, "+7 (999) 444-44-44")
        self.assertNotContains(response, "+7 (999) 111-11-11")
        self.assertNotContains(response, "+7 (999) 333-33-33")


class ExpertContractDetailsTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix="experts-tests-")
        self.addCleanup(lambda: shutil.rmtree(self.media_root, ignore_errors=True))

        self.user = get_user_model().objects.create_user(
            username="experts-admin",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)

        employee_user = get_user_model().objects.create_user(
            username="expert-user",
            password="secret",
            first_name="Иван",
            last_name="Иванов",
            is_staff=True,
        )
        self.employee = Employee.objects.create(
            user=employee_user,
            patronymic="Иванович",
        )
        self.person = PersonRecord.objects.create(
            last_name="Иванов",
            first_name="Иван",
            middle_name="Иванович",
            full_name_genitive="Иванова Ивана Ивановича",
            gender="male",
            birth_date=date(1990, 5, 17),
            position=1,
        )
        self.employee.person_record = self.person
        self.employee.save(update_fields=["person_record"])
        self.profile = ExpertProfile.objects.create(employee=self.employee, position=1)
        self.country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            short_name_genitive="России",
            full_name="Российская Федерация",
            alpha2="RU",
            alpha3="RUS",
            position=1,
        )
        self.other_country = OKSMCountry.objects.create(
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
            effective_date=date(2020, 1, 1),
            position=1,
        )
        TerritorialDivision.objects.create(
            country=self.country,
            region_name="Московская область",
            effective_date=date(2020, 1, 1),
            position=2,
        )
        TerritorialDivision.objects.create(
            country=self.other_country,
            region_name="California",
            effective_date=date(2020, 1, 1),
            position=3,
        )
        self.citizenship = CitizenshipRecord.objects.create(
            person=self.person,
            country=self.country,
            status="Гражданство",
            identifier="Паспорт",
            number="123456",
            position=1,
        )
        self.contract_detail = ExpertContractDetails.objects.create(
            expert_profile=self.profile,
            citizenship_record=self.citizenship,
        )

    def test_contract_details_edit_uploads_facsimile_and_renders_download_link(self):
        with self.settings(MEDIA_ROOT=self.media_root):
            response = self.client.post(
                reverse("epr_contract_details_edit", args=[self.contract_detail.pk]),
                {
                    "target_context": "contract-requisites",
                    "facsimile_file": SimpleUploadedFile(
                        "facsimile.pdf",
                        b"facsimile-data",
                        content_type="application/pdf",
                    ),
                },
            )

        self.assertEqual(response.status_code, 200)
        self.contract_detail.refresh_from_db()
        self.assertTrue(self.contract_detail.facsimile_file.name)
        self.assertContains(response, "Факсимиле")
        self.assertContains(
            response,
            reverse("epr_contract_facsimile_download", args=[self.contract_detail.pk]),
            html=False,
        )

    def test_contract_details_edit_can_clear_facsimile_file(self):
        with self.settings(MEDIA_ROOT=self.media_root):
            self.contract_detail.facsimile_file.save("facsimile.pdf", ContentFile(b"facsimile-data"), save=True)
            old_path = self.contract_detail.facsimile_file.path

            response = self.client.post(
                reverse("epr_contract_details_edit", args=[self.contract_detail.pk]),
                {"facsimile_file-clear": "on"},
            )

        self.assertEqual(response.status_code, 200)
        self.contract_detail.refresh_from_db()
        self.assertEqual(self.contract_detail.facsimile_file.name, "")
        self.assertFalse(os.path.exists(old_path))

    def test_contract_details_edit_shows_locked_citizenship_fields_from_registry(self):
        self.person.gender = "male"
        self.person.save(update_fields=["gender"])
        self.contract_detail.save()

        response = self.client.get(
            reverse("epr_contract_details_edit", args=[self.contract_detail.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Страна гражданства (налоговая юрисдикция)")
        self.assertContains(response, 'name="citizenship_country"', html=False)
        self.assertContains(response, 'name="citizenship_status"', html=False)
        self.assertContains(response, 'name="citizenship_identifier"', html=False)
        self.assertContains(response, 'name="citizenship_number"', html=False)
        self.assertContains(response, 'value="Россия"', html=False)
        self.assertContains(response, 'value="Гражданство"', html=False)
        self.assertContains(response, 'value="гражданин России"', html=False)
        self.assertContains(response, 'value="Паспорт"', html=False)
        self.assertContains(response, 'value="123456"', html=False)
        self.assertContains(response, 'name="full_name_genitive"', html=False)
        self.assertContains(response, 'value="Иванова Ивана Ивановича"', html=False)
        self.assertContains(response, 'name="gender"', html=False)
        self.assertContains(response, 'name="birth_date"', html=False)
        self.assertContains(response, 'name="registration_address"', html=False)
        self.assertContains(response, 'name="registration_postal_code"', html=False)
        self.assertContains(response, 'name="registration_region"', html=False)
        self.assertContains(response, 'id="ecd-registration-region-select"', html=False)
        self.assertContains(response, 'name="registration_locality"', html=False)
        self.assertContains(response, 'name="registration_street"', html=False)
        self.assertContains(response, 'name="registration_building"', html=False)
        self.assertContains(response, 'name="registration_premise"', html=False)
        self.assertContains(response, 'name="registration_premise_part"', html=False)
        self.assertContains(response, 'name="registration_date"', html=False)
        self.assertContains(response, 'data-country-id="%s"' % self.country.pk, html=False)
        self.assertContains(response, '>Москва</option>', html=False)
        self.assertContains(response, '>Московская область</option>', html=False)
        self.assertNotContains(response, '>California</option>', html=False)
        self.assertContains(response, 'readonly-field', html=False)
        self.assertContains(response, 'value="1990-05-17"', html=False)
        self.assertContains(response, '>мужской</option>', html=False)
        self.assertContains(response, 'disabled', html=False)
        self.assertNotContains(response, 'name="inn"', html=False)

    def test_contract_details_full_name_genitive_is_locked_and_synced_from_person_record(self):
        response = self.client.post(
            reverse("epr_contract_details_edit", args=[self.contract_detail.pk]),
            {
                "target_context": "contract-requisites",
                "full_name_genitive": "Подмененное значение",
                "self_employed": "",
                "tax_rate": "",
                "gender": "",
                "snils": "",
                "birth_date": "",
                "passport_series": "",
                "passport_number": "",
                "passport_issued_by": "",
                "passport_issue_date": "",
                "passport_expiry_date": "",
                "passport_division_code": "",
                "registration_address": "",
                "registration_postal_code": "",
                "registration_region": "Москва",
                "registration_locality": "",
                "registration_street": "",
                "registration_building": "",
                "registration_premise": "",
                "registration_premise_part": "",
                "registration_date": "",
                "bank_name": "",
                "bank_swift": "",
                "bank_inn": "",
                "bank_bik": "",
                "settlement_account": "",
                "corr_account": "",
                "bank_address": "",
                "corr_bank_name": "",
                "corr_bank_address": "",
                "corr_bank_bik": "",
                "corr_bank_swift": "",
                "corr_bank_settlement_account": "",
                "corr_bank_corr_account": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.contract_detail.refresh_from_db()
        self.assertEqual(self.contract_detail.full_name_genitive, "Иванова Ивана Ивановича")
        self.assertContains(response, "Иванова Ивана Ивановича")
        self.assertNotContains(response, "Подмененное значение")

    def test_contract_details_gender_is_locked_and_synced_from_person_record(self):
        response = self.client.post(
            reverse("epr_contract_details_edit", args=[self.contract_detail.pk]),
            {
                "target_context": "contract-requisites",
                "full_name_genitive": "",
                "self_employed": "",
                "tax_rate": "",
                "gender": "female",
                "snils": "",
                "birth_date": "",
                "passport_series": "",
                "passport_number": "",
                "passport_issued_by": "",
                "passport_issue_date": "",
                "passport_expiry_date": "",
                "passport_division_code": "",
                "registration_address": "",
                "registration_postal_code": "",
                "registration_region": "Москва",
                "registration_locality": "",
                "registration_street": "",
                "registration_building": "",
                "registration_premise": "",
                "registration_premise_part": "",
                "registration_date": "",
                "bank_name": "",
                "bank_swift": "",
                "bank_inn": "",
                "bank_bik": "",
                "settlement_account": "",
                "corr_account": "",
                "bank_address": "",
                "corr_bank_name": "",
                "corr_bank_address": "",
                "corr_bank_bik": "",
                "corr_bank_swift": "",
                "corr_bank_settlement_account": "",
                "corr_bank_corr_account": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.contract_detail.refresh_from_db()
        self.assertEqual(self.contract_detail.gender, "male")
        self.assertContains(response, "мужской")

    def test_contract_details_form_uses_registration_region_choices_for_citizenship_country(self):
        form = ExpertContractDetailsForm(instance=self.contract_detail)

        self.assertEqual(form.fields["registration_region"].widget.attrs["id"], "ecd-registration-region-select")
        self.assertIn(("Москва", "Москва"), list(form.fields["registration_region"].choices))
        self.assertIn(("Московская область", "Московская область"), list(form.fields["registration_region"].choices))
        self.assertNotIn(("California", "California"), list(form.fields["registration_region"].choices))
        self.assertTrue(form.fields["full_name_genitive"].disabled)
        self.assertTrue(form.fields["gender"].disabled)

    def test_contract_details_birth_date_is_locked_and_synced_from_person_record(self):
        response = self.client.post(
            reverse("epr_contract_details_edit", args=[self.contract_detail.pk]),
            {
                "target_context": "contract-requisites",
                "full_name_genitive": "",
                "self_employed": "",
                "tax_rate": "",
                "gender": "",
                "snils": "",
                "birth_date": "2001-01-01",
                "passport_series": "",
                "passport_number": "",
                "passport_issued_by": "",
                "passport_issue_date": "",
                "passport_expiry_date": "",
                "passport_division_code": "",
                "registration_address": "",
                "registration_postal_code": "",
                "registration_region": "Москва",
                "registration_locality": "",
                "registration_street": "",
                "registration_building": "",
                "registration_premise": "",
                "registration_premise_part": "",
                "registration_date": "2026-04-19",
                "bank_name": "",
                "bank_swift": "",
                "bank_inn": "",
                "bank_bik": "",
                "settlement_account": "",
                "corr_account": "",
                "bank_address": "",
                "corr_bank_name": "",
                "corr_bank_address": "",
                "corr_bank_bik": "",
                "corr_bank_swift": "",
                "corr_bank_settlement_account": "",
                "corr_bank_corr_account": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.contract_detail.refresh_from_db()
        self.assertEqual(self.contract_detail.birth_date, date(1990, 5, 17))
        self.assertEqual(self.contract_detail.registration_region, "Москва")
        self.assertEqual(self.contract_detail.registration_date, date(2026, 4, 19))
        self.assertEqual(self.contract_detail.registration_address, "")
        self.assertContains(response, "17.05.1990")

    def test_contract_details_registration_address_is_calculated_from_address_parts(self):
        response = self.client.post(
            reverse("epr_contract_details_edit", args=[self.contract_detail.pk]),
            {
                "full_name_genitive": "",
                "self_employed": "",
                "tax_rate": "",
                "gender": "",
                "snils": "",
                "birth_date": "",
                "passport_series": "",
                "passport_number": "",
                "passport_issued_by": "",
                "passport_issue_date": "",
                "passport_expiry_date": "",
                "passport_division_code": "",
                "registration_postal_code": "101000",
                "registration_region": "Москва",
                "registration_locality": "Москва",
                "registration_street": "Тверская",
                "registration_building": "1",
                "registration_premise": "",
                "registration_premise_part": "",
                "registration_date": "",
                "bank_name": "",
                "bank_swift": "",
                "bank_inn": "",
                "bank_bik": "",
                "settlement_account": "",
                "corr_account": "",
                "bank_address": "",
                "corr_bank_name": "",
                "corr_bank_address": "",
                "corr_bank_bik": "",
                "corr_bank_swift": "",
                "corr_bank_settlement_account": "",
                "corr_bank_corr_account": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.contract_detail.refresh_from_db()
        self.assertEqual(
            self.contract_detail.registration_address,
            "101000 Москва, Тверская, 1",
        )

    def test_contract_details_citizenship_is_calculated_from_gender_and_country_genitive(self):
        self.person.gender = "male"
        self.person.save(update_fields=["gender"])
        self.contract_detail.save()
        self.contract_detail.refresh_from_db()
        self.assertEqual(self.contract_detail.citizenship, "гражданин России")

        self.person.gender = "female"
        self.person.save(update_fields=["gender"])
        self.contract_detail.save()
        self.contract_detail.refresh_from_db()
        self.assertEqual(self.contract_detail.citizenship, "гражданка России")

    def test_contract_details_citizenship_is_empty_for_non_citizenship_status(self):
        self.person.gender = "male"
        self.person.save(update_fields=["gender"])
        self.citizenship.status = "Временное проживание"
        self.citizenship.save(update_fields=["status"])

        self.contract_detail.save()
        self.contract_detail.refresh_from_db()

        self.assertEqual(self.contract_detail.citizenship, "")

    def test_contract_facsimile_download_returns_attachment(self):
        with self.settings(MEDIA_ROOT=self.media_root):
            self.contract_detail.facsimile_file.save("facsimile.pdf", ContentFile(b"facsimile-data"), save=True)

            response = self.client.get(
                reverse("epr_contract_facsimile_download", args=[self.contract_detail.pk])
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertIn("facsimile.pdf", response["Content-Disposition"])
        self.assertEqual(b"".join(response.streaming_content), b"facsimile-data")

    def test_contract_requisites_partial_renders_one_contract_details_row_per_citizenship(self):
        CitizenshipRecord.objects.create(
            person=self.person,
            identifier="ВНЖ",
            number="654321",
            position=2,
        )

        response = self.client.get(reverse("contract_requisites_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'hx-trigger="contract-requisites:refresh from:body"', html=False)
        row_count = ExpertContractDetails.objects.filter(expert_profile=self.profile).count()
        self.assertGreaterEqual(row_count, 2)
        self.assertContains(response, "Иванов Иван Иванович", count=row_count)

    def test_contract_requisites_partial_syncs_full_name_genitive_from_person_record(self):
        ExpertContractDetails.objects.filter(pk=self.contract_detail.pk).update(full_name_genitive="Старое значение")
        PersonRecord.objects.filter(pk=self.person.pk).update(full_name_genitive="Нового Иванова Ивана Ивановича")

        response = self.client.get(reverse("contract_requisites_partial"))

        self.assertEqual(response.status_code, 200)
        self.contract_detail.refresh_from_db()
        self.assertEqual(self.contract_detail.full_name_genitive, "Нового Иванова Ивана Ивановича")
        self.assertContains(response, "Нового Иванова Ивана Ивановича")

    def test_contract_requisites_partial_syncs_gender_from_person_record(self):
        ExpertContractDetails.objects.filter(pk=self.contract_detail.pk).update(gender="")
        PersonRecord.objects.filter(pk=self.person.pk).update(gender="female")

        response = self.client.get(reverse("contract_requisites_partial"))

        self.assertEqual(response.status_code, 200)
        self.contract_detail.refresh_from_db()
        self.assertEqual(self.contract_detail.gender, "female")
        self.assertContains(response, "женский")

    def test_contract_requisites_partial_renders_only_active_citizenship_rows(self):
        CitizenshipRecord.objects.create(
            person=self.person,
            country=self.country,
            status="ВНЖ",
            identifier="ВНЖ",
            number="654321",
            valid_to=date(2026, 1, 1),
            position=2,
        )

        response = self.client.get(reverse("contract_requisites_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Страна гражданства")
        self.assertContains(response, "Статус")
        self.assertContains(response, "Идентификатор")
        self.assertContains(response, ">Номер<", html=False)
        self.assertContains(response, "Россия")
        self.assertContains(response, "Гражданство")
        self.assertContains(response, "Паспорт")
        self.assertContains(response, "123456")
        self.assertNotContains(response, "654321")
        self.assertNotContains(response, ">ИНН<", html=False)


class ExpertSpecialtyCsvTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="experts-csv-admin",
            password="secret123",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.user)
        self.owner = GroupMember.objects.create(
            short_name="IMC Montan",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
            position=1,
            is_management_company=True,
        )
        self.expertise_dir = ExpertiseDirection.objects.create(
            name="Горная экспертиза",
            short_name="ГЭ",
            position=1,
        )
        self.org_unit = OrgUnit.objects.create(
            company=self.owner,
            department_name="Отдел горной экспертизы",
            short_name="OGE",
            expertise=self.expertise_dir,
            unit_type="expertise",
            level=2,
            position=1,
        )
        head_user = get_user_model().objects.create_user(
            username="experts-csv-head",
            password="secret123",
            is_staff=True,
        )
        self.expertise_dir.department = self.org_unit
        self.expertise_dir.save(update_fields=["department"])
        self.head = Employee.objects.create(
            user=head_user,
            job_title="Руководитель горной экспертизы",
            role=DEPARTMENT_HEAD_GROUP,
            department=self.org_unit,
        )

    def test_experts_partial_no_longer_renders_specialties_table(self):
        response = self.client.get(reverse("experts_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "База физлиц-исполнителей")
        self.assertNotContains(response, "Специальности исполнителей")
        self.assertNotContains(response, 'id="esp-table"', html=False)
        self.assertNotContains(response, 'id="esp-csv-download-btn"', html=False)
        self.assertNotContains(response, 'id="esp-colpicker-wrap"', html=False)

    def test_policy_expert_specialties_table_renders_csv_and_colpicker(self):
        response = self.client.get(reverse("policy_expert_specialties_table"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Классификатор специальностей исполнителей")
        self.assertContains(response, 'id="esp-colpicker-wrap"', html=False)
        self.assertContains(response, 'id="esp-colpicker-btn"', html=False)
        self.assertContains(response, 'id="esp-col-all"', html=False)
        self.assertContains(response, 'id="esp-table"', html=False)
        self.assertContains(response, 'data-col="expertise-dir">Экспертиза</th>', html=False)
        self.assertContains(response, 'for="esp-col-expertise-dir">Экспертиза</label>', html=False)
        self.assertNotContains(response, ">Направление экспертизы<", html=False)
        self.assertContains(response, 'data-col="specialty"', html=False)
        self.assertContains(response, 'data-col="organization"', html=False)
        self.assertNotContains(response, 'data-col="head-of-direction"', html=False)
        self.assertContains(response, 'data-col="specialization-area"', html=False)
        self.assertContains(response, "Область специализации")
        self.assertContains(response, 'id="esp-csv-download-btn"', html=False)
        self.assertContains(response, 'id="esp-csv-upload-btn"', html=False)
        self.assertContains(response, 'hx-target="#policy-modal .modal-content"', html=False)
        self.assertContains(response, 'id="policy-expert-specialties-section"', html=False)

    def test_specialty_table_splits_department_pairs_into_grouped_rows(self):
        OrgUnit.objects.create(
            company=self.owner,
            department_name="Экологический сектор",
            short_name="ECO",
            expertise=self.expertise_dir,
            unit_type="expertise",
            level=2,
            position=2,
        )
        specialty = ExpertSpecialty.objects.create(
            specialty="Геолог",
            specialty_en="Geologist",
            expertise_dir=self.expertise_dir,
            position=1,
        )
        response = self.client.get(reverse("policy_expert_specialties_table"))
        html = response.content.decode()
        group_rows = re.findall(
            r'<tr[^>]*data-row-group="%s"[^>]*>.*?</tr>' % specialty.pk,
            html,
            flags=re.S,
        )
        self.assertEqual(len(group_rows), 2)
        self.assertIn("esp-group-has-next", group_rows[0])
        self.assertIn("esp-group-continuation", group_rows[1])
        self.assertEqual(group_rows[0].count('name="esp-select"'), 1)
        self.assertNotIn('name="esp-select"', group_rows[1])
        self.assertIn("Отдел горной экспертизы", group_rows[0])
        self.assertIn("Экологический сектор", group_rows[1])
        self.assertIn(">Геолог<", group_rows[0])
        self.assertNotIn(">Геолог<", group_rows[1])
        self.assertNotIn("Руководитель направления", html)

        edit = self.client.get(reverse("esp_form_edit", args=[specialty.pk]))
        form_html = edit.content.decode()
        self.assertIn(">1</span>", form_html)
        self.assertIn(">2</span>", form_html)
        self.assertIn('value="Отдел горной экспертизы"', form_html)
        self.assertIn('value="Экологический сектор"', form_html)
        self.assertNotIn("Руководитель направления", form_html)

    def test_separate_mode_puts_management_company_pair_first(self):
        from group_app.models import ExpertiseManagementMode

        other = GroupMember.objects.create(
            short_name="ТОО «IMC Montan»",
            country_name="Казахстан",
            country_code="398",
            country_alpha2="KZ",
            position=0,
        )
        OrgUnit.objects.create(
            company=other,
            department_name="Отдел Казахстана",
            short_name="KZ",
            expertise=self.expertise_dir,
            unit_type="expertise",
            level=2,
            position=0,
        )
        ExpertiseManagementMode.objects.filter(expertise_direction=self.expertise_dir).update(
            mode=ExpertiseManagementMode.MODE_SEPARATE,
        )
        specialty = ExpertSpecialty.objects.create(
            specialty="Геолог",
            expertise_dir=self.expertise_dir,
            position=1,
        )
        response = self.client.get(reverse("policy_expert_specialties_table"))
        html = response.content.decode()
        group_rows = re.findall(
            r'<tr[^>]*data-row-group="%s"[^>]*>.*?</tr>' % specialty.pk,
            html,
            flags=re.S,
        )
        self.assertEqual(len(group_rows), 2)
        self.assertIn("Отдел горной экспертизы", group_rows[0])
        self.assertIn("IMC Montan", group_rows[0])
        self.assertIn("Отдел Казахстана", group_rows[1])
        self.assertIn("ТОО «IMC Montan»", group_rows[1])

        edit = self.client.get(reverse("esp_form_edit", args=[specialty.pk]))
        form_html = edit.content.decode()
        first_pair = form_html.index(">1</span>")
        second_pair = form_html.index(">2</span>")
        self.assertLess(first_pair, form_html.index('value="Отдел горной экспертизы"'))
        self.assertLess(form_html.index('value="Отдел горной экспертизы"'), second_pair)
        self.assertLess(second_pair, form_html.index('value="Отдел Казахстана"'))

        self.assertContains(response, 'class="policy-table-editor"', html=False)
        self.assertContains(response, 'class="policy-table-footer"', html=False)
        self.assertContains(response, 'class="policy-table-footer-actions products-actions-row"', html=False)
        self.assertContains(response, 'class="policy-table-pagination"', html=False)
        self.assertContains(response, 'data-policy-table-page-size="25"', html=False)
        self.assertContains(response, "Показано строк")
        self.assertNotContains(response, 'id="policy-pane"', html=False)
        policy_js = (
            Path(__file__).resolve().parents[1]
            / "core"
            / "static"
            / "core"
            / "js"
            / "policy-panels.js"
        ).read_text()
        policy_css = (
            Path(__file__).resolve().parents[1]
            / "core"
            / "static"
            / "core"
            / "css"
            / "site.css"
        ).read_text()
        self.assertIn("function bindExpertSpecialtiesColumnPicker()", policy_js)
        self.assertIn("function applyExpertSpecialtiesColumnVisibility()", policy_js)
        self.assertIn("experts:espHiddenCols", policy_js)
        self.assertIn("esp-colpicker-open", policy_js)
        self.assertIn("esp-colpicker-open", policy_css)
        self.assertIn("#policy-pane .table-section-header:has(.epr-colpicker-menu.show)", policy_css)
        self.assertIn("width: max-content; min-width: 100%; max-width: none;", policy_css)
        self.assertIn("overflow-x: hidden; overflow-y: auto;", policy_css)
        self.assertIn(
            "#policy-pane .epr-colpicker .form-check,\n"
            "#policy-pane .product-map-filters .form-check {\n"
            "  padding-left: 1.5em !important;",
            policy_css,
        )
        self.assertIn(
            "#policy-pane .epr-colpicker .form-check-input,\n"
            "#policy-pane .product-map-filters .form-check-input {\n"
            "  margin-left: -1.5em !important;",
            policy_css,
        )

    def test_policy_expert_specialties_table_paginates_like_other_product_tables(self):
        ExpertSpecialty.objects.bulk_create(
            [
                ExpertSpecialty(
                    specialty=f"Paged specialty {index:02d}",
                    specialty_en=f"Paged specialty {index:02d}",
                    position=index,
                )
                for index in range(1, 27)
            ]
        )

        first_page = self.client.get(reverse("policy_expert_specialties_table"))
        self.assertEqual(first_page.status_code, 200)
        self.assertTrue(first_page.context["policy_pagination_enabled"])
        self.assertEqual(first_page.context["paginator"].count, 26)
        self.assertEqual(len(first_page.context["specialties"]), 25)
        self.assertContains(first_page, "1–25 из 26")
        self.assertContains(first_page, "Paged specialty 01")
        self.assertNotContains(first_page, "Paged specialty 26")

        second_page = self.client.get(
            reverse("policy_expert_specialties_table"),
            {"page": 2},
        )
        self.assertEqual(len(second_page.context["specialties"]), 1)
        self.assertContains(second_page, "26–26 из 26")
        self.assertContains(second_page, "Paged specialty 26")
        self.assertNotContains(second_page, "Paged specialty 01")

    def test_specialty_form_targets_policy_xl_modal(self):
        response = self.client.get(reverse("esp_form_create"))
        policy_js = (
            Path(__file__).resolve().parents[1]
            / "core"
            / "static"
            / "core"
            / "js"
            / "policy-panels.js"
        ).read_text()
        policy_panel = render_to_string("policy_app/panel.html")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-policy-modal-size="xl"', html=False)
        self.assertContains(response, 'hx-target="#policy-modal .modal-content"', html=False)
        self.assertNotContains(response, 'hx-target="#experts-pane"', html=False)
        self.assertIn('id="policy-modal"', policy_panel)
        self.assertIn("modal-dialog modal-lg modal-dialog-scrollable", policy_panel)
        self.assertIn("syncPolicyModalSize", policy_js)
        self.assertIn('data-policy-modal-size="xl"', policy_js)

    def test_experts_panel_keeps_profile_modal_backdrop_guards(self):
        html = render_to_string("experts_app/panel.html")

        self.assertIn("restoreExpertsBackdropIfMissing", html)
        self.assertIn("scheduleExpertsBackdropCheck", html)
        self.assertIn("cleanupExpertsFallbackBackdrop", html)
        self.assertIn("data-experts-fallback-backdrop", html)
        self.assertIn("hidden.bs.modal", html)

    def test_specialty_form_uses_two_column_layout(self):
        response = self.client.get(reverse("esp_form_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="row g-3"', html=False)
        self.assertContains(response, 'class="col-md-6"', count=4, html=False)
        self.assertContains(response, 'id="esp-department"', html=False)
        self.assertContains(response, 'id="esp-organization"', html=False)
        self.assertNotContains(response, 'id="esp-head"', html=False)
        self.assertContains(response, 'data-department="Отдел горной экспертизы"', html=False)
        self.assertContains(response, 'data-organization="IMC Montan"', html=False)
        self.assertNotContains(response, 'data-head="Руководитель горной экспертизы"', html=False)
        self.assertContains(response, "Связи со структурными подразделениями")
        self.assertContains(response, 'class="esp-pair-row"', html=False)
        self.assertContains(response, 'class="esp-pair-labels"', html=False)
        self.assertContains(response, ">1</span>", html=False)
        self.assertContains(response, 'class="col-12"', html=False)
        self.assertContains(response, "Направление экспертизы")
        self.assertContains(response, "Область специализации")
        self.assertContains(response, "Специалист по")
        self.assertContains(response, 'name="specialization_area_suffix"', html=False)

    def test_specialty_form_saves_specialization_area_with_locked_prefix(self):
        response = self.client.post(
            reverse("esp_form_create"),
            {
                "specialty": "Геолог",
                "specialty_en": "Geologist",
                "owner_ids": "__group__",
                "expertise_dir": "",
                "expertise_direction": "",
                "head_of_direction": "",
                "specialization_area_suffix": "подземным водам",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        specialty = ExpertSpecialty.objects.get(specialty="Геолог")
        self.assertEqual(specialty.specialization_area, "Специалист по подземным водам")
        self.assertEqual(specialty.created_by_id, self.user.pk)
        self.assertEqual(response.content, b"")
        self.assertEqual(response["HX-Reswap"], "none")
        self.assertEqual(
            json.loads(response["HX-Trigger"]),
            {
                "policy-updated": {
                    "tables": ["expert-specialties", "specialty-tariffs", "typical-sections"],
                    "refreshFilters": False,
                }
            },
        )

    def test_specialty_form_leaves_blank_specialization_area_empty(self):
        response = self.client.post(
            reverse("esp_form_create"),
            {
                "specialty": "Геолог",
                "specialty_en": "Geologist",
                "owner_ids": "__group__",
                "expertise_dir": "",
                "expertise_direction": "",
                "head_of_direction": "",
                "specialization_area_suffix": "",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        specialty = ExpertSpecialty.objects.get(specialty="Геолог")
        self.assertEqual(specialty.specialization_area, "")
        self.assertEqual(response.content, b"")

    def test_specialty_edit_form_prefills_specialization_area_suffix(self):
        specialty = ExpertSpecialty.objects.create(
            specialty="Геолог",
            specialization_area="Специалист по подземным водам",
            position=1,
        )

        response = self.client.get(reverse("esp_form_edit", args=[specialty.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Специалист по")
        self.assertContains(response, 'value="подземным водам"', html=False)

    def test_esp_csv_download_exports_table_columns(self):
        specialty = ExpertSpecialty.objects.create(
            specialty="Геолог",
            specialty_en="Geologist",
            expertise_dir=self.expertise_dir,
            expertise_direction=self.org_unit,
            head_of_direction=self.head,
            specialization_area="Специалист по подземным водам",
            position=1,
        )
        specialty.owners.set([self.owner])

        response = self.client.get(reverse("esp_csv_download"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("expert_specialties.csv", response["Content-Disposition"])
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(
            rows[0],
            [
                "Специальность",
                "Специальность на англ. языке",
                "Область специализации",
                "Направление экспертизы",
                "Подразделение",
                "Организация",
                "Владелец",
            ],
        )
        self.assertEqual(
            rows[1],
            [
                "Геолог",
                "Geologist",
                "Специалист по подземным водам",
                "ГЭ",
                "Отдел горной экспертизы",
                "IMC Montan",
                "IMC Montan",
            ],
        )

    def test_esp_csv_upload_creates_specialty_with_owner(self):
        csv_file = SimpleUploadedFile(
            "specialties.csv",
            (
                "Специальность;Специальность на англ. языке;Владелец;"
                "Направление экспертизы;Подразделение;Руководитель направления\n"
                "Геолог;Geologist;IMC Montan;ГЭ;Отдел горной экспертизы;"
                "Руководитель горной экспертизы\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(reverse("esp_csv_upload"), {"csv_file": csv_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["created"], 1)
        self.assertEqual(
            payload["policyUpdate"]["tables"],
            ["expert-specialties", "specialty-tariffs", "typical-sections"],
        )
        specialty = ExpertSpecialty.objects.get(specialty="Геолог")
        self.assertEqual(specialty.specialty_en, "Geologist")
        self.assertEqual(specialty.expertise_dir_id, self.expertise_dir.pk)
        self.assertEqual(specialty.expertise_direction_id, self.org_unit.pk)
        self.assertEqual(specialty.head_of_direction_id, self.head.pk)
        self.assertEqual(specialty.created_by_id, self.user.pk)
        self.assertFalse(specialty.is_group_owner)
        self.assertEqual(list(specialty.owners.values_list("short_name", flat=True)), ["IMC Montan"])

    def test_esp_csv_upload_creates_specialty_with_specialization_area(self):
        csv_file = SimpleUploadedFile(
            "specialties.csv",
            (
                "Специальность;Специальность на англ. языке;Владелец;"
                "Направление экспертизы;Подразделение;Руководитель направления;"
                "Область специализации\n"
                "Геолог;Geologist;Группа;;;;Специалист по подземным водам\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(reverse("esp_csv_upload"), {"csv_file": csv_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 1)
        specialty = ExpertSpecialty.objects.get(specialty="Геолог")
        self.assertEqual(specialty.specialization_area, "Специалист по подземным водам")

    def test_esp_csv_upload_skips_duplicate_specialty(self):
        ExpertSpecialty.objects.create(specialty="Геолог", position=1)
        csv_file = SimpleUploadedFile(
            "specialties.csv",
            (
                "Специальность;Специальность на англ. языке;Владелец;"
                "Направление экспертизы;Подразделение;Руководитель направления\n"
                "Геолог;Geologist;;;;\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(reverse("esp_csv_upload"), {"csv_file": csv_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 0)
        self.assertEqual(ExpertSpecialty.objects.filter(specialty="Геолог").count(), 1)
        self.assertTrue(any("уже существует" in item for item in response.json()["warnings"]))

    def test_specialty_form_derives_locked_fields_and_ignores_posted_values(self):
        response = self.client.post(
            reverse("esp_form_create"),
            {
                "specialty": "Маркшейдер",
                "specialty_en": "Surveyor",
                "owner_ids": "__group__",
                "expertise_dir": str(self.expertise_dir.pk),
                "department": "Чужое подразделение",
                "organization": "Чужая организация",
                "head_of_direction_display": "Чужой руководитель",
                "specialization_area_suffix": "",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        specialty = ExpertSpecialty.objects.get(specialty="Маркшейдер")
        self.assertEqual(specialty.expertise_direction_id, self.org_unit.pk)
        self.assertEqual(specialty.head_of_direction_id, self.head.pk)
        self.assertEqual(specialty.department_display, "Отдел горной экспертизы")
        self.assertEqual(specialty.organization_display, "IMC Montan")
        self.assertEqual(specialty.head_job_title_display, "Руководитель горной экспертизы")

    def test_specialty_edit_keeps_author(self):
        author = get_user_model().objects.create_user(
            username="specialty-author",
            password="secret123",
            is_staff=True,
        )
        specialty = ExpertSpecialty.objects.create(
            specialty="Геолог",
            expertise_dir=self.expertise_dir,
            created_by=author,
            position=1,
        )

        response = self.client.post(
            reverse("esp_form_edit", args=[specialty.pk]),
            {
                "specialty": "Геолог",
                "specialty_en": "Geologist",
                "owner_ids": "__group__",
                "expertise_dir": str(self.expertise_dir.pk),
                "specialization_area_suffix": "",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        specialty.refresh_from_db()
        self.assertEqual(specialty.created_by_id, author.pk)

    def test_several_department_heads_use_lowest_position(self):
        self.head.position = 3
        self.head.save(update_fields=["position"])
        earlier_user = get_user_model().objects.create_user(
            username="experts-csv-head-earlier",
            password="secret123",
        )
        earlier = Employee.objects.create(
            user=earlier_user,
            job_title="Первый руководитель",
            role=DEPARTMENT_HEAD_GROUP,
            department=self.org_unit,
            position=1,
        )

        specialty = ExpertSpecialty.objects.create(
            specialty="Маркшейдер",
            expertise_dir=self.expertise_dir,
            position=2,
        )

        self.assertEqual(specialty.head_of_direction_id, earlier.pk)

    def test_management_company_level_one_unit_uses_director(self):
        self.org_unit.level = 1
        self.org_unit.save(update_fields=["level"])
        self.owner.is_management_company = True
        self.owner.save(update_fields=["is_management_company"])
        director_user = get_user_model().objects.create_user(username="experts-director", password="secret123")
        director = Employee.objects.create(
            user=director_user,
            job_title="Директор компании",
            role=DIRECTOR_GROUP,
            department=self.org_unit,
            position=5,
        )
        lawyer_user = get_user_model().objects.create_user(username="experts-lawyer", password="secret123")
        Employee.objects.create(
            user=lawyer_user,
            job_title="Юрист компании",
            role="Юрист",
            department=self.org_unit,
            position=0,
        )
        other_company = GroupMember.objects.create(
            short_name="Другая компания",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
            position=2,
        )
        other_unit = OrgUnit.objects.create(
            company=other_company,
            department_name="Директор",
            level=1,
            unit_type="administrative",
            position=1,
        )
        other_user = get_user_model().objects.create_user(username="experts-other-director", password="secret123")
        Employee.objects.create(
            user=other_user,
            job_title="Другой директор",
            role=DIRECTOR_GROUP,
            department=other_unit,
            position=0,
        )

        specialty = ExpertSpecialty.objects.create(
            specialty="Координатор теста",
            expertise_dir=self.expertise_dir,
            position=4,
        )

        self.assertEqual(specialty.head_of_direction_id, director.pk)
        self.assertEqual(specialty.organization_display, "IMC Montan")

    def test_director_is_not_used_without_management_company_flag(self):
        director_user = get_user_model().objects.create_user(username="experts-director-plain", password="secret123")
        Employee.objects.create(
            user=director_user,
            job_title="Директор компании",
            role=DIRECTOR_GROUP,
            department=self.org_unit,
            position=0,
        )

        specialty = ExpertSpecialty.objects.create(
            specialty="Координатор теста",
            expertise_dir=self.expertise_dir,
            position=4,
        )

        self.assertEqual(specialty.head_of_direction_id, self.head.pk)


class ExpertProfileCsvTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="experts-epr-csv-admin",
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
        self.expertise_dir = ExpertiseDirection.objects.create(
            name="Горная экспертиза",
            short_name="ГЭ",
            position=1,
        )
        self.org_unit = OrgUnit.objects.create(
            company=self.owner,
            department_name="Отдел горной экспертизы",
            short_name="OGE",
            expertise=self.expertise_dir,
            unit_type="expertise",
            position=1,
        )
        self.grade = Grade.objects.create(
            grade_en="Senior",
            grade_ru="Старший",
            qualification=3,
            qualification_levels=5,
            created_by=self.user,
            position=1,
        )
        self.specialty = ExpertSpecialty.objects.create(
            specialty="Геолог",
            specialty_en="Geologist",
            position=1,
        )

        employee_user = get_user_model().objects.create_user(
            username="experts-epr-csv-user",
            password="secret123",
            first_name="Иван",
            last_name="Иванов",
            email="expert@example.com",
            is_staff=True,
        )
        self.person = PersonRecord.objects.create(
            last_name="Иванов",
            first_name="Иван",
            middle_name="Иванович",
            position=1,
        )
        self.employee = Employee.objects.create(
            user=employee_user,
            patronymic="Иванович",
            person_record=self.person,
        )
        self.profile = ExpertProfile.objects.create(
            employee=self.employee,
            expertise_direction=self.org_unit,
            professional_status="Статус 1",
            professional_status_short="С1",
            grade=self.grade,
            status="Активен",
            position=1,
        )
        ExpertProfileSpecialty.objects.create(
            profile=self.profile,
            specialty=self.specialty,
            rank=1,
        )

    def test_experts_partial_renders_epr_csv_buttons(self):
        response = self.client.get(reverse("experts_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "База физлиц-исполнителей")
        self.assertContains(response, 'id="epr-csv-download-btn"', html=False)
        self.assertContains(response, 'id="epr-csv-upload-btn"', html=False)

    def test_epr_csv_download_exports_table_columns(self):
        response = self.client.get(reverse("epr_csv_download"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("expert_profiles.csv", response["Content-Disposition"])
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(
            rows[0],
            [
                "ФИО",
                "Эл. почта (логин)",
                "Дополнительная эл. почта",
                "Телефон",
                "Дополнительный телефон",
                "Направление экспертизы",
                "Специальность",
                "Профессиональный статус",
                "Профессиональный статус (кратко)",
                "Грейд",
                "Страна",
                "Регион проживания",
                "Статус",
                "Дата",
            ],
        )
        self.assertEqual(rows[1][0], "Иванов Иван Иванович")
        self.assertEqual(rows[1][1], "expert@example.com")
        self.assertEqual(rows[1][5], "Отдел горной экспертизы")
        self.assertEqual(rows[1][6], "Геолог")
        self.assertEqual(rows[1][7], "Статус 1")
        self.assertEqual(rows[1][8], "С1")
        self.assertEqual(rows[1][9], "Старший")
        self.assertEqual(rows[1][12], "Активен")

    def test_epr_csv_upload_updates_profile_by_email(self):
        other_specialty = ExpertSpecialty.objects.create(
            specialty="Геофизик",
            specialty_en="Geophysicist",
            position=2,
        )
        csv_file = SimpleUploadedFile(
            "profiles.csv",
            (
                "ФИО;Эл. почта (логин);Дополнительная эл. почта;Телефон;Дополнительный телефон;"
                "Направление экспертизы;Специальность;Профессиональный статус;"
                "Профессиональный статус (кратко);Грейд;Страна;Регион проживания;Статус;Дата\n"
                "Иванов Иван Иванович;expert@example.com;;;;Отдел горной экспертизы;"
                "Геофизик;Новый статус;НС;Старший;;;Обновлён;01.01.2026\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(reverse("epr_csv_upload"), {"csv_file": csv_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["updated"], 1)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.professional_status, "Новый статус")
        self.assertEqual(self.profile.professional_status_short, "НС")
        self.assertEqual(self.profile.status, "Обновлён")
        self.assertEqual(self.profile.expertise_direction_id, self.org_unit.pk)
        self.assertEqual(self.profile.grade_id, self.grade.pk)
        specialty_names = list(
            self.profile.ranked_specialties.order_by("rank").values_list("specialty__specialty", flat=True)
        )
        self.assertEqual(specialty_names, ["Геофизик"])
        self.assertEqual(other_specialty.pk, ExpertSpecialty.objects.get(specialty="Геофизик").pk)
        contact_record = SpecialtyRecord.objects.get(person=self.person, specialty=other_specialty)
        link = self.profile.ranked_specialties.get()
        self.assertEqual(link.contact_specialty_record, contact_record)

    def test_epr_csv_upload_skips_unknown_email(self):
        csv_file = SimpleUploadedFile(
            "profiles.csv",
            (
                "ФИО;Эл. почта (логин);Дополнительная эл. почта;Телефон;Дополнительный телефон;"
                "Направление экспертизы;Специальность;Профессиональный статус;"
                "Профессиональный статус (кратко);Грейд;Страна;Регион проживания;Статус;Дата\n"
                "Неизвестный;missing@example.com;;;;;;;;;;;;\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(reverse("epr_csv_upload"), {"csv_file": csv_file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["updated"], 0)
        self.assertTrue(any("не найден" in item for item in response.json()["warnings"]))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.professional_status, "Статус 1")


class ExpertSpecialtyAdminTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="specialty-admin",
            email="specialty-admin@example.com",
            password="secret123",
        )
        self.client.force_login(self.user)
        self.specialty = ExpertSpecialty.objects.create(
            specialty="Геолог",
            specialty_en="Geologist",
            specialization_area="Специалист по подземным водам",
            created_by=self.user,
            position=1,
        )

    def test_changelist_shows_table_columns_and_author(self):
        response = self.client.get(reverse("admin:policy_app_policyexpertspecialty_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Специальности исполнителей")
        self.assertNotContains(response, "Специальность раздела")
        self.assertNotContains(response, "Специальности экспертов")
        index = self.client.get(reverse("admin:index"))
        self.assertContains(index, "ПРОДУКТЫ")
        self.assertContains(index, "/admin/policy_app/policyexpertspecialty/")
        self.assertNotContains(index, "/admin/experts_app/expertspecialty/")
        for label in (
            "Специальность на англ. языке",
            "Владелец",
            "Направление экспертизы",
            "Подразделение",
            "Организация",
            "Область специализации",
            "Автор",
        ):
            self.assertContains(response, label)
        self.assertContains(response, "Геолог")
        self.assertContains(response, "specialty-admin")

    def test_change_form_shows_derived_fields_and_author(self):
        response = self.client.get(
            reverse("admin:policy_app_policyexpertspecialty_change", args=[self.specialty.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Специальность исполнителя")
        self.assertContains(response, "Подразделение")
        self.assertContains(response, "Организация")
        self.assertNotContains(response, "Руководитель направления")
        self.assertContains(response, "Автор")
        self.assertContains(response, "specialty-admin")

    def test_admin_create_stores_author(self):
        response = self.client.post(
            reverse("admin:policy_app_policyexpertspecialty_add"),
            {
                "specialty": "Маркшейдер",
                "specialty_en": "Surveyor",
                "specialization_area": "",
                "is_group_owner": "on",
                "expertise_dir": "",
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, 302)
        specialty = ExpertSpecialty.objects.get(specialty="Маркшейдер")
        self.assertEqual(specialty.created_by_id, self.user.pk)


class ExpertSpecialtyRoleAccessTests(TestCase):
    def setUp(self):
        self.company = GroupMember.objects.create(
            short_name="IMC Montan",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
            position=1,
            is_management_company=True,
        )
        self.direction = ExpertiseDirection.objects.create(
            name="Горная экспертиза",
            short_name="ГЭ",
            position=1,
        )
        self.unit = OrgUnit.objects.create(
            company=self.company,
            department_name="Отдел горной экспертизы",
            short_name="OGE",
            expertise=self.direction,
            unit_type="expertise",
            level=2,
            position=2,
        )
        self.direction.department = self.unit
        self.direction.save(update_fields=["department"])
        self.other_direction = ExpertiseDirection.objects.create(
            name="Не установлено",
            short_name="—",
            position=2,
        )
        self.director_unit = OrgUnit.objects.create(
            company=self.company,
            department_name="Директор",
            short_name="DIR",
            expertise=self.other_direction,
            unit_type="administrative",
            level=1,
            position=1,
        )
        self.other_direction.department = self.director_unit
        self.other_direction.save(update_fields=["department"])

        self.head_user = self._user("esp-head", DEPARTMENT_HEAD_GROUP, self.unit, "Руководитель горной экспертизы")
        self.director_user = self._user("esp-director", DIRECTOR_GROUP, self.director_unit, "Директор")
        self.admin_user = self._user("esp-admin", ADMIN_GROUP, None, "Администратор")
        self.expert_user = self._user("esp-expert", "Эксперт", self.unit, "Эксперт")
        self.direction_director_user = self._user(
            "esp-direction-director",
            DIRECTION_DIRECTOR_GROUP,
            self.unit,
            "Директор направления",
        )
        Employee.objects.create(
            user=get_user_model().objects.create_user(username="esp-other", password="secret123", is_staff=True),
            job_title="Другой руководитель",
            role=DEPARTMENT_HEAD_GROUP,
            department=self.unit,
            position=5,
        )
        self.other_user = get_user_model().objects.get(username="esp-other")
        self.own = ExpertSpecialty.objects.create(
            specialty="Своя",
            expertise_dir=self.direction,
            created_by=self.head_user,
            position=1,
        )
        self.foreign = ExpertSpecialty.objects.create(
            specialty="Чужая",
            expertise_dir=self.other_direction,
            created_by=self.other_user,
            position=2,
        )
        self.unowned = ExpertSpecialty.objects.create(
            specialty="Без автора",
            expertise_dir=self.direction,
            position=3,
        )

    def _user(self, username, role, department, job_title):
        user = get_user_model().objects.create_user(
            username=username,
            password="secret123",
            is_staff=True,
        )
        Employee.objects.create(
            user=user,
            job_title=job_title,
            role=role,
            department=department,
            position=1,
        )
        return user

    def _checkbox(self, html, pk):
        import re

        match = re.search(rf'id="esp-sel-{pk}".*?>', html, re.S)
        self.assertIsNotNone(match)
        return match.group(0)

    def test_other_roles_see_readonly_table_without_actions(self):
        self.direction_director_user.is_superuser = True
        self.direction_director_user.save(update_fields=["is_superuser"])
        for user in (self.expert_user, self.direction_director_user):
            self.client.force_login(user)
            response = self.client.get(reverse("policy_expert_specialties_table"))
            html = response.content.decode()
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, "Добавить строку")
            self.assertNotContains(response, 'id="esp-csv-upload-btn"', html=False)
            self.assertNotContains(response, 'id="esp-csv-download-btn"', html=False)
            self.assertContains(response, 'class="policy-table-footer-actions"></div>', html=False)
            self.assertIn("disabled", html[html.index('id="esp-master"'):html.index('id="esp-master"') + 250])
            self.assertIn("disabled", self._checkbox(html, self.own.pk))
            self.assertIn("disabled", self._checkbox(html, self.foreign.pk))
            self.assertEqual(self.client.get(reverse("esp_form_create")).status_code, 403)
            self.assertEqual(
                self.client.post(reverse("esp_delete", args=[self.own.pk])).status_code,
                403,
            )

    def test_department_head_edits_only_own_rows_and_locked_direction(self):
        self.client.force_login(self.head_user)
        response = self.client.get(reverse("policy_expert_specialties_table"))
        html = response.content.decode()
        self.assertContains(response, "Добавить строку")
        self.assertNotIn("disabled", self._checkbox(html, self.own.pk))
        self.assertNotIn("disabled", self._checkbox(html, self.unowned.pk))
        self.assertIn("disabled", self._checkbox(html, self.foreign.pk))
        self.assertIn('data-row-order-locked="1"', html)

        form = self.client.get(reverse("esp_form_create"))
        self.assertContains(form, "disabled")
        self.assertContains(form, "readonly-field")
        self.assertContains(form, "ГЭ Горная экспертиза")
        self.assertContains(form, 'data-department="Отдел горной экспертизы"', html=False)
        self.assertContains(form, 'data-organization="IMC Montan"', html=False)
        self.assertNotContains(form, "Не установлено")

        created = self.client.post(
            reverse("esp_form_create"),
            {
                "specialty": "Геолог",
                "specialty_en": "Geologist",
                "owner_ids": "__group__",
                "expertise_dir": str(self.other_direction.pk),
                "specialization_area_suffix": "",
            },
        )
        self.assertEqual(created.status_code, 200)
        specialty = ExpertSpecialty.objects.get(specialty="Геолог")
        self.assertEqual(specialty.expertise_dir_id, self.direction.pk)
        self.assertEqual(specialty.created_by_id, self.head_user.pk)
        self.assertEqual(specialty.head_of_direction.role, DEPARTMENT_HEAD_GROUP)

        authored_elsewhere = ExpertSpecialty.objects.create(
            specialty="Создана руководителем в чужом направлении",
            expertise_dir=self.other_direction,
            created_by=self.head_user,
            position=4,
        )
        table_after = self.client.get(reverse("policy_expert_specialties_table"))
        self.assertIn("disabled", self._checkbox(table_after.content.decode(), authored_elsewhere.pk))
        self.assertEqual(self.client.get(reverse("esp_form_edit", args=[self.foreign.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("esp_form_edit", args=[self.unowned.pk])).status_code, 200)
        self.assertEqual(self.client.post(reverse("esp_delete", args=[self.foreign.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("esp_move_up", args=[self.foreign.pk])).status_code, 403)
        own_edit = self.client.get(reverse("esp_form_edit", args=[self.own.pk]))
        self.assertEqual(own_edit.status_code, 200)
        self.assertContains(own_edit, "disabled")
        self.assertContains(own_edit, "ГЭ Горная экспертиза")

    def test_director_create_locks_management_direction(self):
        self.director_user.is_superuser = True
        self.director_user.save(update_fields=["is_superuser"])
        self.client.force_login(self.director_user)
        table = self.client.get(reverse("policy_expert_specialties_table"))
        html = table.content.decode()
        self.assertNotIn("disabled", self._checkbox(html, self.foreign.pk))
        self.assertIn("disabled", self._checkbox(html, self.own.pk))
        self.assertIn("disabled", self._checkbox(html, self.unowned.pk))
        self.assertEqual(self.client.get(reverse("esp_form_edit", args=[self.own.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("esp_form_edit", args=[self.foreign.pk])).status_code, 200)

        form = self.client.get(reverse("esp_form_create"))
        self.assertContains(form, "disabled")
        self.assertContains(form, "— Не установлено")
        self.assertContains(form, 'value="Директор"', html=False)
        self.assertContains(form, 'data-department="Директор"', html=False)
        self.assertNotContains(form, "ГЭ Горная экспертиза")

        created = self.client.post(
            reverse("esp_form_create"),
            {
                "specialty": "Координатор",
                "specialty_en": "Coordinator",
                "owner_ids": "__group__",
                "expertise_dir": str(self.direction.pk),
                "specialization_area_suffix": "",
            },
        )
        self.assertEqual(created.status_code, 200)
        specialty = ExpertSpecialty.objects.get(specialty="Координатор")
        self.assertEqual(specialty.expertise_dir_id, self.other_direction.pk)
        self.assertEqual(specialty.head_of_direction.role, DIRECTOR_GROUP)
        self.assertEqual(specialty.created_by_id, self.director_user.pk)

    def test_director_of_unlisted_department_cannot_edit_rows(self):
        other_company = GroupMember.objects.create(
            short_name="Другая компания",
            country_name="Казахстан",
            country_code="398",
            country_alpha2="KZ",
            position=2,
        )
        other_unit = OrgUnit.objects.create(
            company=other_company,
            department_name="Директор",
            short_name="DIR2",
            unit_type="administrative",
            level=1,
            position=3,
        )
        user = self._user("esp-other-director", DIRECTOR_GROUP, other_unit, "Директор")
        user.is_superuser = True
        user.save(update_fields=["is_superuser"])
        self.client.force_login(user)
        response = self.client.get(reverse("policy_expert_specialties_table"))
        html = response.content.decode()
        self.assertContains(response, "Добавить строку")
        self.assertIn("disabled", self._checkbox(html, self.foreign.pk))
        self.assertIn("disabled", self._checkbox(html, self.own.pk))
        self.assertEqual(self.client.get(reverse("esp_form_edit", args=[self.foreign.pk])).status_code, 403)
        form = self.client.get(reverse("esp_form_create"))
        self.assertContains(form, "Для вашего подразделения не задано направление экспертизы.")

    def test_same_department_name_in_another_organization_stays_locked(self):
        other_company = GroupMember.objects.create(
            short_name="ТОО «IMC Montan»",
            country_name="Казахстан",
            country_code="398",
            country_alpha2="KZ",
            position=3,
        )
        other_unit = OrgUnit.objects.create(
            company=other_company,
            department_name="Директор",
            short_name="DIR-KZ",
            unit_type="administrative",
            level=1,
            position=4,
        )
        other_direction = ExpertiseDirection.objects.create(
            name="Дирекция Казахстана",
            short_name="KZ",
            position=3,
            department=other_unit,
        )
        other_unit.expertise = other_direction
        other_unit.save(update_fields=["expertise"])
        from group_app.models import ExpertiseManagementMode
        ExpertiseManagementMode.objects.filter(expertise_direction=other_direction).update(
            mode=ExpertiseManagementMode.MODE_SEPARATE,
        )
        other_specialty = ExpertSpecialty.objects.create(
            specialty="Координатор Казахстана",
            expertise_dir=other_direction,
            position=5,
        )
        other_director = self._user("esp-kz-director", DIRECTOR_GROUP, other_unit, "Директор")
        other_director.is_superuser = True
        other_director.save(update_fields=["is_superuser"])

        self.client.force_login(self.director_user)
        own_html = self.client.get(reverse("policy_expert_specialties_table")).content.decode()
        self.assertNotIn("disabled", self._checkbox(own_html, self.foreign.pk))
        self.assertIn("disabled", self._checkbox(own_html, other_specialty.pk))

        self.client.force_login(other_director)
        other_html = self.client.get(reverse("policy_expert_specialties_table")).content.decode()
        self.assertNotIn("disabled", self._checkbox(other_html, other_specialty.pk))
        self.assertIn("disabled", self._checkbox(other_html, self.foreign.pk))
        self.assertIn("disabled", self._checkbox(other_html, self.own.pk))

    def test_admin_edits_every_row_and_chooses_any_direction(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse("policy_expert_specialties_table"))
        html = response.content.decode()
        self.assertContains(response, "Добавить строку")
        self.assertNotIn("disabled", self._checkbox(html, self.own.pk))
        self.assertNotIn("disabled", self._checkbox(html, self.foreign.pk))
        self.assertNotIn("disabled", self._checkbox(html, self.unowned.pk))

        form = self.client.get(reverse("esp_form_create"))
        self.assertContains(form, "ГЭ Горная экспертиза")
        self.assertContains(form, "— Не установлено")
        html = form.content.decode()
        tag_start = html.rfind("<select", 0, html.index('id="esp-dir-select"'))
        tag_end = html.index(">", html.index('id="esp-dir-select"'))
        self.assertNotIn("disabled", html[tag_start:tag_end])

        self.assertEqual(self.client.get(reverse("esp_form_edit", args=[self.foreign.pk])).status_code, 200)
        created = self.client.post(
            reverse("esp_form_create"),
            {
                "specialty": "Маркшейдер",
                "specialty_en": "Surveyor",
                "owner_ids": "__group__",
                "expertise_dir": str(self.other_direction.pk),
                "specialization_area_suffix": "",
            },
        )
        self.assertEqual(created.status_code, 200)
        specialty = ExpertSpecialty.objects.get(specialty="Маркшейдер")
        self.assertEqual(specialty.expertise_dir_id, self.other_direction.pk)

    def test_department_head_csv_upload_uses_own_direction(self):
        self.client.force_login(self.head_user)
        csv_file = SimpleUploadedFile(
            "specialties.csv",
            (
                "Специальность;Специальность на англ. языке;Область специализации;"
                "Направление экспертизы;Руководитель направления;Подразделение;Организация;Владелец\n"
                "Геолог;Geologist;;—;;;Группа\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )
        response = self.client.post(reverse("esp_csv_upload"), {"csv_file": csv_file})
        self.assertEqual(response.status_code, 200)
        specialty = ExpertSpecialty.objects.get(specialty="Геолог")
        self.assertEqual(specialty.expertise_dir_id, self.direction.pk)
        self.assertEqual(specialty.created_by_id, self.head_user.pk)

        self.client.force_login(self.expert_user)
        denied = self.client.post(reverse("esp_csv_upload"), {"csv_file": csv_file})
        self.assertEqual(denied.status_code, 403)

    def test_group_membership_grants_department_head_when_role_is_empty(self):
        user = get_user_model().objects.create_user(
            username="esp-group-head",
            password="secret123",
            is_staff=True,
        )
        Employee.objects.create(user=user, job_title="Руководитель", role="", department=self.unit)
        group, _created = Group.objects.get_or_create(name=DEPARTMENT_HEAD_GROUP)
        user.groups.add(group)
        self.client.force_login(user)
        form = self.client.get(reverse("esp_form_create"))
        self.assertEqual(form.status_code, 200)
        self.assertContains(form, "disabled")
        self.assertContains(form, "ГЭ Горная экспертиза")
        self.assertNotContains(form, "Не установлено")
