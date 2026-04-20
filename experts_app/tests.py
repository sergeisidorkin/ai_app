import os
import shutil
import tempfile
from datetime import date

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from classifiers_app.models import OKSMCountry, TerritorialDivision
from experts_app.forms import ExpertContractDetailsForm
from contacts_app.models import CitizenshipRecord, EmailRecord, PersonRecord, PhoneRecord
from experts_app.models import ExpertContractDetails, ExpertProfile
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

    def test_experts_partial_renders_one_contract_details_row_per_citizenship(self):
        CitizenshipRecord.objects.create(
            person=self.person,
            identifier="ВНЖ",
            number="654321",
            position=2,
        )

        response = self.client.get(reverse("experts_partial"))

        self.assertEqual(response.status_code, 200)
        row_count = ExpertContractDetails.objects.filter(expert_profile=self.profile).count()
        self.assertGreaterEqual(row_count, 2)
        self.assertContains(response, "Иванов Иван Иванович", count=1 + row_count)

    def test_experts_partial_syncs_full_name_genitive_from_person_record(self):
        ExpertContractDetails.objects.filter(pk=self.contract_detail.pk).update(full_name_genitive="Старое значение")
        PersonRecord.objects.filter(pk=self.person.pk).update(full_name_genitive="Нового Иванова Ивана Ивановича")

        response = self.client.get(reverse("experts_partial"))

        self.assertEqual(response.status_code, 200)
        self.contract_detail.refresh_from_db()
        self.assertEqual(self.contract_detail.full_name_genitive, "Нового Иванова Ивана Ивановича")
        self.assertContains(response, "Нового Иванова Ивана Ивановича")

    def test_experts_partial_syncs_gender_from_person_record(self):
        ExpertContractDetails.objects.filter(pk=self.contract_detail.pk).update(gender="")
        PersonRecord.objects.filter(pk=self.person.pk).update(gender="female")

        response = self.client.get(reverse("experts_partial"))

        self.assertEqual(response.status_code, 200)
        self.contract_detail.refresh_from_db()
        self.assertEqual(self.contract_detail.gender, "female")
        self.assertContains(response, "женский")

    def test_experts_partial_renders_only_active_citizenship_rows(self):
        CitizenshipRecord.objects.create(
            person=self.person,
            country=self.country,
            status="ВНЖ",
            identifier="ВНЖ",
            number="654321",
            valid_to=date(2026, 1, 1),
            position=2,
        )

        response = self.client.get(reverse("experts_partial"))

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
