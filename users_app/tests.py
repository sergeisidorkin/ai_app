from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from contacts_app.models import CitizenshipRecord, EmailRecord, PersonRecord, PhoneRecord, PositionRecord
from group_app.models import GroupMember
from policy_app.models import DIRECTION_DIRECTOR_GROUP, DIRECTOR_GROUP, ROLE_GROUPS_ORDER

from .forms import EmployeeForm, ExternalRegistrationForm, FREELANCER_LABEL
from .models import Employee, PendingRegistration


class UsersContactsSyncTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(
            username="admin@example.com",
            email="admin@example.com",
            password="secret",
            is_staff=True,
            first_name="Админ",
            last_name="Системный",
        )
        self.client.force_login(self.admin)

    def _employee_payload(self, **overrides):
        payload = {
            "last_name": "Иванов",
            "first_name": "Иван",
            "patronymic": "Иванович",
            "person_record": "",
            "email": "ivanov@example.com",
            "password": "StrongPassword123!",
            "employment": FREELANCER_LABEL,
            "department": "",
            "job_title": "Инженер",
            "role": "",
        }
        payload.update(overrides)
        return payload

    def _external_payload(self, **overrides):
        payload = {
            "last_name": "Петров",
            "first_name": "Петр",
            "patronymic": "Петрович",
            "email": "petrov@example.com",
            "password": "StrongPassword123!",
            "organization": 'ООО "Бета"',
            "job_title": "Консультант",
        }
        payload.update(overrides)
        return payload

    def test_employee_model_no_longer_has_phone_field(self):
        field_names = {field.name for field in Employee._meta.get_fields()}

        self.assertNotIn("phone", field_names)

    def test_employee_role_choices_place_direction_director_after_director(self):
        for role_name in ROLE_GROUPS_ORDER:
            Group.objects.get_or_create(name=role_name)

        role_names = list(EmployeeForm().fields["role"].queryset.values_list("name", flat=True))

        director_index = role_names.index(DIRECTOR_GROUP)
        self.assertEqual(role_names[director_index + 1], DIRECTION_DIRECTOR_GROUP)

    def test_employee_form_grants_direction_director_superuser_rights(self):
        group, _ = Group.objects.get_or_create(name=DIRECTION_DIRECTOR_GROUP)
        form = EmployeeForm(
            self._employee_payload(
                email="direction-director@example.com",
                role=str(group.pk),
            )
        )

        self.assertTrue(form.is_valid(), form.errors)
        employee = form.save()

        self.assertEqual(employee.role, DIRECTION_DIRECTOR_GROUP)
        self.assertTrue(employee.user.is_superuser)

    def test_employee_create_creates_linked_contact_records(self):
        response = self.client.post(reverse("emp_form_create"), self._employee_payload())

        self.assertEqual(response.status_code, 200)
        employee = Employee.objects.select_related("user", "person_record", "managed_email_record", "managed_position_record").get()
        self.assertEqual(employee.person_record.display_name, "Иванов Иван Иванович")
        self.assertEqual(employee.person_record.user_kind, "employee")
        self.assertEqual(employee.managed_email_record.person, employee.person_record)
        self.assertEqual(employee.managed_email_record.email, "ivanov@example.com")
        self.assertEqual(employee.managed_email_record.user_kind, "employee")
        self.assertTrue(employee.managed_email_record.is_user_managed)
        self.assertEqual(employee.managed_email_record.source, "[Пользователи / Сотрудники]")
        self.assertEqual(employee.managed_position_record.person, employee.person_record)
        self.assertEqual(employee.managed_position_record.organization_short_name, FREELANCER_LABEL)
        self.assertEqual(employee.managed_position_record.job_title, "Инженер")
        self.assertTrue(employee.managed_position_record.is_user_managed)
        self.assertEqual(employee.managed_position_record.source, "[Пользователи / Сотрудники]")
        self.assertTrue(employee.person_record.phones.exists())
        self.assertTrue(PhoneRecord.objects.get(person=employee.person_record).is_primary)
        self.assertEqual(
            CitizenshipRecord.objects.get(person=employee.person_record).source,
            "[Пользователи / Сотрудники]",
        )
        self.assertEqual(
            PhoneRecord.objects.get(person=employee.person_record).source,
            "[Пользователи / Сотрудники]",
        )

    def test_external_create_creates_linked_contact_records(self):
        response = self.client.post(reverse("ext_form_create"), self._external_payload())

        self.assertEqual(response.status_code, 200)
        employee = Employee.objects.select_related("user", "person_record", "managed_email_record", "managed_position_record").get()
        self.assertFalse(employee.user.is_staff)
        self.assertEqual(employee.person_record.user_kind, "external")
        self.assertEqual(employee.managed_email_record.email, "petrov@example.com")
        self.assertEqual(employee.managed_email_record.user_kind, "external")
        self.assertEqual(employee.managed_email_record.source, "[Пользователи / Внешние пользователи]")
        self.assertEqual(employee.managed_position_record.organization_short_name, 'ООО "Бета"')
        self.assertEqual(employee.managed_position_record.job_title, "Консультант")
        self.assertEqual(employee.managed_position_record.source, "[Пользователи / Внешние пользователи]")
        self.assertEqual(
            CitizenshipRecord.objects.get(person=employee.person_record).source,
            "[Пользователи / Внешние пользователи]",
        )
        self.assertEqual(
            PhoneRecord.objects.get(person=employee.person_record).source,
            "[Пользователи / Внешние пользователи]",
        )
        self.assertTrue(PhoneRecord.objects.get(person=employee.person_record).is_primary)

    def test_external_edit_syncs_person_record_name_fields(self):
        self.client.post(reverse("ext_form_create"), self._external_payload())
        employee = Employee.objects.get()

        response = self.client.post(
            reverse("ext_form_edit", args=[employee.pk]),
            self._external_payload(
                last_name="Сидорова",
                first_name="Анна",
                patronymic="Игоревна",
                email="anna@example.com",
                password="",
            ),
        )

        self.assertEqual(response.status_code, 200)
        employee.refresh_from_db()
        employee.person_record.refresh_from_db()
        self.assertEqual(employee.person_record.display_name, "Сидорова Анна Игоревна")

    def test_employee_edit_syncs_linked_contact_records(self):
        self.client.post(reverse("emp_form_create"), self._employee_payload())
        employee = Employee.objects.get()
        company = GroupMember.objects.create(
            short_name='АО "Альфа"',
            full_name='АО "Альфа"',
            country_name="Россия",
            position=1,
        )

        response = self.client.post(
            reverse("emp_form_edit", args=[employee.pk]),
            self._employee_payload(
                last_name="Сидоров",
                first_name="Сидр",
                patronymic="Сидорович",
                email="sidorov@example.com",
                employment=company.short_name,
                job_title="Архитектор",
                password="",
            ),
        )

        self.assertEqual(response.status_code, 200)
        employee.refresh_from_db()
        employee.person_record.refresh_from_db()
        employee.managed_email_record.refresh_from_db()
        employee.managed_position_record.refresh_from_db()
        self.assertEqual(employee.person_record.display_name, "Сидоров Сидр Сидорович")
        self.assertEqual(employee.managed_email_record.email, "sidorov@example.com")
        self.assertEqual(employee.managed_position_record.organization_short_name, 'АО "Альфа"')
        self.assertEqual(employee.managed_position_record.job_title, "Архитектор")

    def test_employee_edit_restores_managed_contact_sources(self):
        self.client.post(reverse("emp_form_create"), self._employee_payload())
        employee = Employee.objects.get()
        EmailRecord.objects.filter(pk=employee.managed_email_record_id).update(source="")
        PositionRecord.objects.filter(pk=employee.managed_position_record_id).update(source="")

        response = self.client.post(
            reverse("emp_form_edit", args=[employee.pk]),
            self._employee_payload(password=""),
        )

        self.assertEqual(response.status_code, 200)
        employee.refresh_from_db()
        employee.managed_email_record.refresh_from_db()
        employee.managed_position_record.refresh_from_db()
        self.assertEqual(employee.managed_email_record.source, "[Пользователи / Сотрудники]")
        self.assertEqual(employee.managed_position_record.source, "[Пользователи / Сотрудники]")

    def test_employee_edit_restores_bootstrap_contact_sources(self):
        self.client.post(reverse("emp_form_create"), self._employee_payload())
        employee = Employee.objects.get()
        citizenship = CitizenshipRecord.objects.get(person=employee.person_record)
        phone = PhoneRecord.objects.get(person=employee.person_record)
        CitizenshipRecord.objects.filter(pk=citizenship.pk).update(source="")
        PhoneRecord.objects.filter(pk=phone.pk).update(source="", is_primary=False)

        response = self.client.post(
            reverse("emp_form_edit", args=[employee.pk]),
            self._employee_payload(password=""),
        )

        self.assertEqual(response.status_code, 200)
        citizenship.refresh_from_db()
        phone.refresh_from_db()
        self.assertEqual(citizenship.source, "[Пользователи / Сотрудники]")
        self.assertEqual(phone.source, "[Пользователи / Сотрудники]")
        self.assertTrue(phone.is_primary)

    def test_employee_delete_detaches_contacts_without_deleting_them(self):
        self.client.post(reverse("emp_form_create"), self._employee_payload())
        employee = Employee.objects.get()
        person_id = employee.person_record_id
        email_id = employee.managed_email_record_id
        position_id = employee.managed_position_record_id

        response = self.client.post(reverse("emp_delete", args=[employee.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Employee.objects.exists())
        self.assertTrue(PersonRecord.objects.filter(pk=person_id).exists())
        self.assertTrue(EmailRecord.objects.filter(pk=email_id).exists())
        self.assertTrue(PositionRecord.objects.filter(pk=position_id).exists())
        self.assertEqual(PersonRecord.objects.get(pk=person_id).user_kind, "")
        email = EmailRecord.objects.get(pk=email_id)
        position = PositionRecord.objects.get(pk=position_id)
        self.assertEqual(email.user_kind, "")
        self.assertFalse(email.is_user_managed)
        self.assertFalse(position.is_user_managed)

    def test_employee_create_can_link_to_existing_person_record(self):
        shared_person = PersonRecord.objects.create(
            last_name="Общий",
            first_name="Контакт",
            middle_name="",
            position=1,
        )

        response = self.client.post(
            reverse("emp_form_create"),
            self._employee_payload(
                person_record=str(shared_person.pk),
                email="shared@example.com",
            ),
        )

        self.assertEqual(response.status_code, 200)
        employee = Employee.objects.select_related("person_record", "managed_email_record", "managed_position_record").get()
        self.assertEqual(employee.person_record_id, shared_person.pk)
        self.assertEqual(employee.user.last_name, "Общий")
        self.assertEqual(employee.user.first_name, "Контакт")
        self.assertEqual(employee.patronymic, "")
        self.assertEqual(employee.managed_email_record.person_id, shared_person.pk)
        self.assertEqual(employee.managed_position_record.person_id, shared_person.pk)

    def test_employee_edit_form_keeps_name_fields_editable_for_current_person_record(self):
        shared_person = PersonRecord.objects.create(
            last_name="Общий",
            first_name="Контакт",
            middle_name="Связанный",
            position=1,
        )
        self.client.post(
            reverse("emp_form_create"),
            self._employee_payload(
                person_record=str(shared_person.pk),
                email="shared@example.com",
            ),
        )
        employee = Employee.objects.get()

        response = self.client.get(reverse("emp_form_edit", args=[employee.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="last_name"', html=False)
        self.assertContains(response, 'name="first_name"', html=False)
        self.assertContains(response, 'name="patronymic"', html=False)
        self.assertContains(response, 'value="Общий"', html=False)
        self.assertContains(response, 'value="Контакт"', html=False)
        self.assertContains(response, 'value="Связанный"', html=False)
        html = response.content.decode("utf-8")
        self.assertNotRegex(html, r'<input[^>]+name="last_name"[^>]+\breadonly\b')
        self.assertNotRegex(html, r'<input[^>]+name="first_name"[^>]+\breadonly\b')
        self.assertNotRegex(html, r'<input[^>]+name="patronymic"[^>]+\breadonly\b')

    def test_employee_edit_allows_updating_names_for_current_person_record(self):
        shared_person = PersonRecord.objects.create(
            last_name="Общий",
            first_name="Контакт",
            middle_name="Связанный",
            position=1,
        )
        self.client.post(
            reverse("emp_form_create"),
            self._employee_payload(
                person_record=str(shared_person.pk),
                email="shared@example.com",
            ),
        )
        employee = Employee.objects.get()

        response = self.client.post(
            reverse("emp_form_edit", args=[employee.pk]),
            self._employee_payload(
                last_name="Исправленная",
                first_name="Запись",
                patronymic="Сотрудника",
                person_record=str(shared_person.pk),
                email="shared@example.com",
                password="",
            ),
        )

        self.assertEqual(response.status_code, 200)
        employee.refresh_from_db()
        shared_person.refresh_from_db()
        self.assertEqual(employee.user.last_name, "Исправленная")
        self.assertEqual(employee.user.first_name, "Запись")
        self.assertEqual(employee.patronymic, "Сотрудника")
        self.assertEqual(shared_person.last_name, "Исправленная")
        self.assertEqual(shared_person.first_name, "Запись")
        self.assertEqual(shared_person.middle_name, "Сотрудника")

    def test_employee_relink_detaches_old_rows_and_adds_new_rows_for_selected_person(self):
        self.client.post(reverse("emp_form_create"), self._employee_payload())
        employee = Employee.objects.select_related("person_record", "managed_email_record", "managed_position_record").get()
        old_person_id = employee.person_record_id
        old_email_id = employee.managed_email_record_id
        old_position_id = employee.managed_position_record_id
        company = GroupMember.objects.create(
            short_name='АО "Альфа"',
            full_name='АО "Альфа"',
            country_name="Россия",
            position=1,
        )

        shared_person = PersonRecord.objects.create(
            last_name="Петров",
            first_name="Петр",
            middle_name="Петрович",
            position=2,
        )
        existing_email = EmailRecord.objects.create(
            person=shared_person,
            email="existing@example.com",
            position=2,
        )
        existing_position = PositionRecord.objects.create(
            person=shared_person,
            organization_short_name='ООО "Бета"',
            job_title="Руководитель",
            position=2,
        )

        response = self.client.post(
            reverse("emp_form_edit", args=[employee.pk]),
            self._employee_payload(
                last_name="Подмена",
                first_name="Имени",
                patronymic="Отчества",
                person_record=str(shared_person.pk),
                email="linked@example.com",
                employment=company.short_name,
                job_title="Архитектор",
                password="",
            ),
        )

        self.assertEqual(response.status_code, 200)
        employee.refresh_from_db()
        self.assertEqual(employee.person_record_id, shared_person.pk)
        self.assertEqual(employee.user.last_name, "Петров")
        self.assertEqual(employee.user.first_name, "Петр")
        self.assertEqual(employee.patronymic, "Петрович")
        self.assertNotEqual(employee.managed_email_record_id, old_email_id)
        self.assertNotEqual(employee.managed_position_record_id, old_position_id)

        old_person = PersonRecord.objects.get(pk=old_person_id)
        old_email = EmailRecord.objects.get(pk=old_email_id)
        old_position = PositionRecord.objects.get(pk=old_position_id)
        self.assertEqual(old_person.user_kind, "")
        self.assertFalse(old_email.is_user_managed)
        self.assertEqual(old_email.user_kind, "")
        self.assertFalse(old_position.is_user_managed)

        new_email = EmailRecord.objects.get(pk=employee.managed_email_record_id)
        new_position = PositionRecord.objects.get(pk=employee.managed_position_record_id)
        self.assertEqual(new_email.person_id, shared_person.pk)
        self.assertEqual(new_email.email, "linked@example.com")
        self.assertTrue(new_email.is_user_managed)
        self.assertEqual(new_position.person_id, shared_person.pk)
        self.assertEqual(new_position.organization_short_name, 'АО "Альфа"')
        self.assertEqual(new_position.job_title, "Архитектор")
        self.assertTrue(new_position.is_user_managed)

        existing_email.refresh_from_db()
        existing_position.refresh_from_db()
        self.assertEqual(existing_email.person_id, shared_person.pk)
        self.assertEqual(existing_email.email, "existing@example.com")
        self.assertEqual(existing_position.person_id, shared_person.pk)
        self.assertEqual(existing_position.organization_short_name, 'ООО "Бета"')
        self.assertEqual(existing_position.job_title, "Руководитель")

    def test_employee_delete_keeps_person_user_kind_when_other_accounts_still_linked(self):
        shared_person = PersonRecord.objects.create(
            last_name="Общий",
            first_name="Сотрудник",
            middle_name="",
            position=1,
            user_kind="employee",
        )
        self.client.post(
            reverse("emp_form_create"),
            self._employee_payload(
                person_record=str(shared_person.pk),
                email="first@example.com",
            ),
        )
        self.client.post(
            reverse("emp_form_create"),
            self._employee_payload(
                first_name="Второй",
                email="second@example.com",
                person_record=str(shared_person.pk),
            ),
        )
        first_employee = Employee.objects.order_by("id").first()

        response = self.client.post(reverse("emp_delete", args=[first_employee.pk]))

        self.assertEqual(response.status_code, 200)
        shared_person.refresh_from_db()
        self.assertEqual(shared_person.user_kind, "employee")
        self.assertEqual(Employee.objects.filter(person_record=shared_person).count(), 1)

    def test_external_registration_form_creates_employee_and_contacts(self):
        form = ExternalRegistrationForm(
            data={
                "email": "external@example.com",
                "password": "StrongPassword123!",
                "password_confirm": "StrongPassword123!",
                "last_name": "Внешний",
                "first_name": "Пользователь",
                "patronymic": "Тестовый",
                "organization": 'ООО "Гамма"',
                "job_title": "Представитель",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        pending = form.save()

        self.assertIsInstance(pending, PendingRegistration)
        employee = pending.user.employee_profile
        self.assertEqual(employee.person_record.user_kind, "external")
        self.assertEqual(employee.managed_email_record.email, "external@example.com")
        self.assertEqual(employee.managed_position_record.organization_short_name, 'ООО "Гамма"')
        self.assertEqual(employee.managed_position_record.job_title, "Представитель")

    def test_users_partial_renders_id_prs_columns_instead_of_phone(self):
        self.client.post(reverse("emp_form_create"), self._employee_payload())
        self.client.post(reverse("ext_form_create"), self._external_payload())

        response = self.client.get(reverse("users_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ">ID-PRS<", count=2, html=False)
        self.assertNotContains(response, ">Телефон<", html=False)
        self.assertContains(response, "-PRS")
