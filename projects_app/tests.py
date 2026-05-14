import base64
import json
import uuid
from io import BytesIO
from datetime import date

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from docx import Document
from docx.enum.text import WD_COLOR_INDEX

from checklists_app.models import ChecklistItem, SourceDataItemFolder, SourceDataSectionFolder, SourceDataWorkspace
from classifiers_app.models import BusinessEntityIdentifierRecord, BusinessEntityRecord, LegalEntityRecord, OKSMCountry
from contacts_app.models import CitizenshipRecord, PersonRecord
from core.models import CloudStorageSettings
from contracts_app.models import ContractTemplate
from nextcloud_app.models import NextcloudUserLink
from notifications_app.models import Notification
from policy_app.models import (
    DIRECTOR_GROUP,
    DIRECTION_DIRECTOR_GROUP,
    EXPERT_GROUP,
    LAWYER_GROUP,
    PROJECTS_HEAD_GROUP,
    Product,
    TypicalSectionSpecialty,
)
from experts_app.models import ExpertContractDetails, ExpertProfile, ExpertProfileSpecialty, ExpertSpecialty
from projects_app.models import (
    LegalEntity,
    Performer,
    ProjectRegistration,
    ProjectRegistrationProduct,
    RegistrationWorkspaceFolder,
    SourceDataTargetFolder,
    WorkVolume,
)
from projects_app.forms import ContractConditionsForm, LegalEntityForm, PerformerForm, ProjectRegistrationForm, WorkVolumeForm
from group_app.models import GroupMember, OrgUnit
from users_app.models import Employee
from unittest.mock import call, patch


TEST_CONTRACT_IMAGE_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMBAAZ/qh8AAAAASUVORK5CYII="
)


class SourceDataTargetFolderViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="staff-user",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)

    def test_load_excludes_unresolved_template_paths(self):
        RegistrationWorkspaceFolder.objects.bulk_create(
            [
                RegistrationWorkspaceFolder(user=self.user, level=1, name="05 Исходные данные", position=0),
                RegistrationWorkspaceFolder(user=self.user, level=2, name="{project_label}", position=1),
                RegistrationWorkspaceFolder(user=self.user, level=2, name="01 Запросы", position=2),
            ]
        )

        response = self.client.get(reverse("source_data_target_folder_load"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["options"], ["05 Исходные данные", "05 Исходные данные/01 Запросы"])

    def test_save_rejects_unresolved_template_paths(self):
        response = self.client.post(
            reverse("source_data_target_folder_save"),
            data=json.dumps({"folder_name": "05 Исходные данные/{project_label}"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        self.assertFalse(SourceDataTargetFolder.objects.filter(user=self.user).exists())

    def test_load_keeps_second_level_options_when_nextcloud_selected(self):
        settings_obj = CloudStorageSettings.get_solo()
        settings_obj.primary_storage = CloudStorageSettings.PrimaryStorage.NEXTCLOUD
        settings_obj.save()
        RegistrationWorkspaceFolder.objects.bulk_create(
            [
                RegistrationWorkspaceFolder(user=self.user, level=1, name="05 Исходные данные", position=0),
                RegistrationWorkspaceFolder(user=self.user, level=2, name="01 Запросы", position=1),
            ]
        )

        response = self.client.get(reverse("source_data_target_folder_load"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["options"], ["05 Исходные данные", "05 Исходные данные/01 Запросы"])


class ProjectRegistrationFormTests(TestCase):
    def setUp(self):
        self.group_member = GroupMember.objects.create(
            short_name="IMC",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
            position=0,
        )
        self.product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
        )
        self.second_product = Product.objects.create(
            short_name="QAQC_FORM",
            name_en="QAQC Form",
            name_ru="QAQC Form",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Контроль качества",
            position=2,
        )

    def test_type_ids_and_deadline_are_required(self):
        form = ProjectRegistrationForm(
            data={
                "number": 4444,
                "group_member": self.group_member.pk,
                "agreement_type": "MAIN",
                "name": "Проект Альфа",
                "status": "Не начат",
                "deadline": "",
                "year": 2026,
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("type_ids", form.errors)
        self.assertIn("deadline", form.errors)

    def test_number_accepts_zero_and_rejects_negative_values(self):
        valid_form = ProjectRegistrationForm(
            data={
                "number": 0,
                "group_member": self.group_member.pk,
                "agreement_type": "MAIN",
                "type_id": [self.product.pk],
                "name": "Проект Ноль",
                "status": "Не начат",
                "deadline": "2026-01-10",
                "year": 2026,
            }
        )
        invalid_form = ProjectRegistrationForm(
            data={
                "number": -1,
                "group_member": self.group_member.pk,
                "agreement_type": "MAIN",
                "type_id": [self.product.pk],
                "name": "Проект Минус",
                "status": "Не начат",
                "deadline": "2026-01-10",
                "year": 2026,
            }
        )

        self.assertTrue(valid_form.is_valid())
        self.assertFalse(invalid_form.is_valid())
        self.assertIn("number", invalid_form.errors)

    def test_number_uses_numeric_widget_and_cleans_to_int(self):
        form = ProjectRegistrationForm(
            data={
                "number": 10,
                "group_member": self.group_member.pk,
                "agreement_type": "MAIN",
                "type_id": [self.product.pk],
                "name": "Проект Десять",
                "status": "Не начат",
                "deadline": "2026-01-10",
                "year": 2026,
            }
        )

        self.assertEqual(form.fields["number"].widget.input_type, "number")
        self.assertEqual(form.fields["number"].widget.attrs["id"], "registration-number-input")
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["number"], 10)

    def test_existing_instance_keeps_numeric_number_value(self):
        registration = ProjectRegistration.objects.create(
            number=1,
            group_member=self.group_member,
            type=self.product,
            agreement_type=ProjectRegistration.AgreementType.MAIN,
            name="Проект Один",
            status="Не начат",
        )

        form = ProjectRegistrationForm(instance=registration)

        self.assertEqual(form["number"].value(), 1)

    def test_project_short_uid_uses_zero_padded_number(self):
        registration = ProjectRegistration.objects.create(
            number=1,
            group_member=self.group_member,
            type=self.product,
            agreement_type=ProjectRegistration.AgreementType.MAIN,
            name="Проект ID",
            status="Не начат",
        )

        self.assertEqual(registration.short_uid, "000100RU")
        self.assertTrue(registration.display_identifier.startswith("0001 "))

    def test_project_short_uid_stage_digit_uses_product_row_sequence(self):
        first = ProjectRegistration.objects.create(
            number=55,
            group_member=self.group_member,
            type=self.product,
            agreement_type=ProjectRegistration.AgreementType.MAIN,
            name="Первый продукт",
            status="Не начат",
            position=1,
        )
        second = ProjectRegistration.objects.create(
            number=55,
            group_member=self.group_member,
            type=self.second_product,
            agreement_type=ProjectRegistration.AgreementType.MAIN,
            name="Второй продукт",
            status="Не начат",
            position=2,
        )

        first.refresh_from_db()
        second.refresh_from_db()

        self.assertEqual(first.short_uid, "005510RU")
        self.assertEqual(second.short_uid, "005520RU")
        self.assertEqual(first.agreement_sequence, 1)
        self.assertEqual(second.agreement_sequence, 2)

    def test_form_allows_duplicate_project_identity_values_and_keeps_project_id_unique(self):
        first = ProjectRegistration.objects.create(
            number=4444,
            group_member=self.group_member,
            type=self.product,
            agreement_type=ProjectRegistration.AgreementType.MAIN,
            name="Проект Дубль 1",
            status="Не начат",
        )

        form = ProjectRegistrationForm(
            data={
                "number": 4444,
                "group_member": self.group_member.pk,
                "agreement_type": "MAIN",
                "type_id": [self.product.pk],
                "name": "Проект Дубль 2",
                "status": "Не начат",
                "deadline": "2026-01-10",
                "year": 2026,
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        duplicate = form.save()
        duplicate.refresh_from_db()

        self.assertEqual(first.number, duplicate.number)
        self.assertEqual(first.group_member_id, duplicate.group_member_id)
        self.assertEqual(first.agreement_type, duplicate.agreement_type)
        self.assertEqual(first.agreement_number, duplicate.agreement_number)
        self.assertNotEqual(first.pk, duplicate.pk)
        self.assertNotEqual(first.short_uid, duplicate.short_uid)

    def test_cleaned_type_ids_keep_ranked_order_without_duplicates(self):
        form = ProjectRegistrationForm()
        bound_form = ProjectRegistrationForm(
            data={
                "number": 11,
                "group_member": self.group_member.pk,
                "agreement_type": "MAIN",
                "type_id": [self.second_product.pk, self.product.pk, self.second_product.pk],
                "name": "Проект Ранги",
                "status": "Не начат",
                "deadline": "2026-01-10",
                "year": 2026,
            }
        )

        self.assertNotIn("type", form.fields)
        self.assertTrue(bound_form.is_valid())
        self.assertEqual(bound_form.cleaned_type_ids, [self.second_product.pk, self.product.pk])

    def test_edit_form_rejects_multiple_products(self):
        bound_form = ProjectRegistrationForm(
            data={
                "number": 11,
                "group_member": self.group_member.pk,
                "agreement_type": "MAIN",
                "type_id": [self.product.pk, self.second_product.pk],
                "name": "Проект Редактирование",
                "status": "Не начат",
                "deadline": "2026-01-10",
                "year": 2026,
            },
            allow_multiple_products=False,
        )

        self.assertFalse(bound_form.is_valid())
        self.assertIn("type_ids", bound_form.errors)

    def test_projects_date_fields_use_native_date_inputs(self):
        forms_and_fields = [
            (ProjectRegistrationForm(), ["deadline", "registration_date"]),
            (ContractConditionsForm(), ["contract_start", "contract_end"]),
            (WorkVolumeForm(), ["registration_date"]),
            (LegalEntityForm(), ["registration_date"]),
        ]

        for form, field_names in forms_and_fields:
            for field_name in field_names:
                widget = form.fields[field_name].widget
                with self.subTest(form=form.__class__.__name__, field=field_name):
                    self.assertEqual(widget.input_type, "date")
                    self.assertEqual(widget.format, "%Y-%m-%d")
                    self.assertNotIn("js-date", widget.attrs.get("class", ""))

    def test_project_manager_choices_include_direction_directors(self):
        project_manager_user = get_user_model().objects.create_user(
            username="project-manager-choice",
            first_name="Иван",
            last_name="Проектов",
            is_staff=True,
        )
        direction_director_user = get_user_model().objects.create_user(
            username="direction-director-choice",
            first_name="Дарья",
            last_name="Директорова",
            is_staff=True,
        )
        expert_user = get_user_model().objects.create_user(
            username="expert-choice",
            first_name="Егор",
            last_name="Экспертов",
            is_staff=True,
        )
        Employee.objects.create(
            user=project_manager_user,
            patronymic="Иванович",
            role=PROJECTS_HEAD_GROUP,
        )
        Employee.objects.create(
            user=direction_director_user,
            patronymic="Дмитриевна",
            role=DIRECTION_DIRECTOR_GROUP,
        )
        Employee.objects.create(
            user=expert_user,
            patronymic="Егорович",
            role=EXPERT_GROUP,
        )

        registration_choices = [label for _value, label in ProjectRegistrationForm().fields["project_manager"].choices]
        work_choices = [label for _value, label in WorkVolumeForm().fields["manager"].choices]

        for choices in (registration_choices, work_choices):
            self.assertTrue(any(label.startswith("Проектов Иван Иванович") for label in choices))
            self.assertTrue(any(label.startswith("Директорова Дарья Дмитриевна") for label in choices))
            self.assertFalse(any(label.startswith("Экспертов Егор Егорович") for label in choices))

    def test_project_manager_form_saves_selected_prs_id(self):
        person = PersonRecord.objects.create(
            last_name="Иванов",
            first_name="Иван",
            middle_name="Иванович",
            position=1,
        )
        user = get_user_model().objects.create_user(
            username="project-manager-prs",
            first_name="Иван",
            last_name="Иванов",
            is_staff=True,
        )
        Employee.objects.create(
            user=user,
            person_record=person,
            patronymic="Иванович",
            role=PROJECTS_HEAD_GROUP,
        )
        group_member = GroupMember.objects.create(
            short_name="IMCM",
            country_name="Россия",
            country_alpha2="RU",
        )
        product = Product.objects.create(short_name="PRS-DD", name_en="Due Diligence PRS", name_ru="ДД PRS")

        choices = dict(ProjectRegistrationForm().fields["project_manager"].choices)
        self.assertEqual(choices[person.formatted_id], "Иванов Иван Иванович")
        legacy_value = f"Иванов Иван Иванович ({person.formatted_id})"
        legacy_form = ProjectRegistrationForm(
            instance=ProjectRegistration(project_manager=legacy_value)
        )
        self.assertEqual(
            dict(legacy_form.fields["project_manager"].choices)[legacy_value],
            "Иванов Иван Иванович",
        )

        form = ProjectRegistrationForm(
            data={
                "number": "6201",
                "group_member": str(group_member.pk),
                "agreement_type": ProjectRegistration.AgreementType.MAIN,
                "name": "Проект с руководителем",
                "status": "Не начат",
                "deadline": "2026-05-01",
                "year": "2026",
                "country": "",
                "customer": "",
                "identifier": "",
                "registration_number": "",
                "registration_date": "",
                "project_manager": person.formatted_id,
                "type_id": str(product.pk),
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        obj = form.save(commit=False)
        self.assertEqual(obj.project_manager, "Иванов Иван Иванович")
        self.assertEqual(obj.project_manager_prs_id, person.formatted_id)

    def test_project_manager_form_selects_saved_prs_id_on_edit(self):
        person = PersonRecord.objects.create(
            last_name="Петров",
            first_name="Петр",
            middle_name="Петрович",
            position=2,
        )
        user = get_user_model().objects.create_user(
            username="project-manager-edit-prs",
            first_name="Петр",
            last_name="Петров",
            is_staff=True,
        )
        Employee.objects.create(
            user=user,
            person_record=person,
            patronymic="Петрович",
            role=PROJECTS_HEAD_GROUP,
        )
        registration = ProjectRegistration(
            project_manager="Петров Петр Петрович",
            project_manager_prs_id=person.formatted_id,
        )

        form = ProjectRegistrationForm(instance=registration)

        self.assertEqual(form["project_manager"].value(), person.formatted_id)


class PerformerFormExecutorFilteringTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
        )
        self.project = ProjectRegistration.objects.create(
            number=6101,
            type=self.product,
            name="Проект исполнителей",
            year=2026,
        )
        self.section = self.product.sections.create(
            code="TAX",
            short_name="Tax",
            short_name_ru="Налоги",
            name_en="Tax",
            name_ru="Налоги",
            accounting_type="Раздел",
        )
        self.matching_specialty = ExpertSpecialty.objects.create(specialty="Налоги")
        self.other_specialty = ExpertSpecialty.objects.create(specialty="Геология")
        TypicalSectionSpecialty.objects.create(
            section=self.section,
            specialty=self.matching_specialty,
            rank=1,
        )
        self.matching_name = "Иванов Иван Иванович"
        self.other_name = "Петров Петр Петрович"
        self.matching_employee = self._create_employee(
            username="tax.executor",
            first_name="Иван",
            last_name="Иванов",
            patronymic="Иванович",
            specialty=self.matching_specialty,
        )
        self.other_employee = self._create_employee(
            username="geo.executor",
            first_name="Петр",
            last_name="Петров",
            patronymic="Петрович",
            specialty=self.other_specialty,
        )

    def _create_employee(self, *, username, first_name, last_name, patronymic, specialty):
        user = get_user_model().objects.create_user(
            username=username,
            password="secret",
            first_name=first_name,
            last_name=last_name,
            is_staff=True,
        )
        employee = Employee.objects.create(user=user, patronymic=patronymic)
        profile = ExpertProfile.objects.create(employee=employee)
        ExpertProfileSpecialty.objects.create(profile=profile, specialty=specialty, rank=1)
        return employee

    def test_executor_choices_are_filtered_by_typical_section_specialties(self):
        form = PerformerForm(data={
            "registration": self.project.pk,
            "typical_section": self.section.pk,
        })

        choices = [value for value, _label in form.fields["executor"].choices]

        self.assertIn(self.matching_name, choices)
        self.assertNotIn(self.other_name, choices)

    def test_executor_choices_are_unfiltered_until_typical_section_is_selected(self):
        form = PerformerForm()

        choices = [value for value, _label in form.fields["executor"].choices]

        self.assertIn(self.matching_name, choices)
        self.assertIn(self.other_name, choices)


class ProjectRegistrationFormViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="projects-form-user",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.group_member = GroupMember.objects.create(
            short_name="IMC",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
            position=1,
        )
        self.product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
            position=1,
        )
        self.extra_product = Product.objects.create(
            short_name="CTRL",
            name_en="Control",
            name_ru="Контроль",
            consulting_type="Горный",
            service_category="Контроль",
            service_subtype="Контроль качества",
            position=2,
        )

    def test_registration_form_renders_linked_type_block(self):
        response = self.client.get(reverse("registration_form_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Добавить проект")
        self.assertContains(response, 'id="registration-type-meta"', html=False)
        self.assertContains(response, 'name="type_consulting"', html=False)
        self.assertContains(response, 'name="type_service_category"', html=False)
        self.assertContains(response, 'name="type_service_subtype"', html=False)
        self.assertContains(response, 'name="type_id"', html=False)
        self.assertContains(response, "Вид консалтинга")
        self.assertContains(response, "Тип услуги")
        self.assertContains(response, "Подтип услуги")
        self.assertContains(response, "Продукт")
        self.assertContains(response, "Контроль")
        self.assertContains(response, "Контроль качества")

    def test_registration_edit_rejects_multiple_products(self):
        registration = ProjectRegistration.objects.create(
            number=6210,
            group_member=self.group_member,
            agreement_type=ProjectRegistration.AgreementType.MAIN,
            type=self.product,
            name="Проект для редактирования",
            status="Не начат",
            year=2026,
            deadline=date(2026, 1, 10),
        )
        ProjectRegistrationProduct.objects.create(
            registration=registration,
            product=self.product,
            rank=1,
        )

        response = self.client.post(
            reverse("registration_form_edit", args=[registration.pk]),
            {
                "number": 6210,
                "group_member": self.group_member.pk,
                "agreement_type": "MAIN",
                "type_id": [self.product.pk, self.extra_product.pk],
                "name": "Проект для редактирования",
                "status": "Не начат",
                "deadline": "2026-01-10",
                "year": 2026,
                "project_manager": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Для строки проекта можно выбрать только один продукт.")
        self.assertEqual(
            list(registration.product_links.order_by("rank").values_list("product_id", flat=True)),
            [self.product.pk],
        )

    def test_projects_registry_groups_repeated_numbers_visually(self):
        first = ProjectRegistration.objects.create(
            number=6211,
            group_member=self.group_member,
            agreement_type=ProjectRegistration.AgreementType.MAIN,
            type=self.product,
            name="Первый продукт",
            status="Не начат",
            year=2026,
            position=1,
        )
        second = ProjectRegistration.objects.create(
            number=6211,
            group_member=self.group_member,
            agreement_type=ProjectRegistration.AgreementType.MAIN,
            type=self.extra_product,
            name="Второй продукт",
            status="Не начат",
            year=2026,
            position=2,
        )

        response = self.client.get(reverse("projects_partial"))

        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertContains(response, 'class="registration-number-has-next"', html=False)
        self.assertContains(response, 'class="registration-number-continuation"', html=False)
        self.assertContains(response, first.short_uid)
        self.assertContains(response, second.short_uid)

    def test_registration_launch_moves_not_started_project_to_in_progress(self):
        registration = ProjectRegistration.objects.create(
            number=6201,
            group_member=self.group_member,
            agreement_type=ProjectRegistration.AgreementType.MAIN,
            type=self.product,
            name="Проект для запуска",
            status="Не начат",
            year=2026,
        )

        response = self.client.post(reverse("registration_launch", args=[registration.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "status": "В работе"})
        registration.refresh_from_db()
        self.assertEqual(registration.status, "В работе")

    def test_registration_launch_rejects_already_started_project(self):
        registration = ProjectRegistration.objects.create(
            number=6202,
            group_member=self.group_member,
            agreement_type=ProjectRegistration.AgreementType.MAIN,
            type=self.product,
            name="Уже запущенный проект",
            status="В работе",
            year=2026,
        )

        response = self.client.post(reverse("registration_launch", args=[registration.pk]))

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        registration.refresh_from_db()
        self.assertEqual(registration.status, "В работе")

    def test_registration_status_update_changes_project_status(self):
        registration = ProjectRegistration.objects.create(
            number=6203,
            group_member=self.group_member,
            agreement_type=ProjectRegistration.AgreementType.MAIN,
            type=self.product,
            name="Проект со сменой статуса",
            status="Не начат",
            year=2026,
        )

        response = self.client.post(
            reverse("registration_status_update", args=[registration.pk]),
            {"status": "На проверке"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "status": "На проверке"})
        registration.refresh_from_db()
        self.assertEqual(registration.status, "На проверке")

    def test_registration_status_update_rejects_unknown_status(self):
        registration = ProjectRegistration.objects.create(
            number=6204,
            group_member=self.group_member,
            agreement_type=ProjectRegistration.AgreementType.MAIN,
            type=self.product,
            name="Проект с ошибочным статусом",
            status="Не начат",
            year=2026,
        )

        response = self.client.post(
            reverse("registration_status_update", args=[registration.pk]),
            {"status": "Неизвестно"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        registration.refresh_from_db()
        self.assertEqual(registration.status, "Не начат")

    def test_registration_manager_update_changes_project_manager(self):
        manager_user = get_user_model().objects.create_user(
            username="project.manager",
            password="secret",
            first_name="Иван",
            last_name="Иванов",
        )
        manager_employee = Employee.objects.create(
            user=manager_user,
            patronymic="Иванович",
            role=PROJECTS_HEAD_GROUP,
        )
        registration = ProjectRegistration.objects.create(
            number=6205,
            group_member=self.group_member,
            agreement_type=ProjectRegistration.AgreementType.MAIN,
            type=self.product,
            name="Проект со сменой руководителя",
            status="Не начат",
            year=2026,
        )

        response = self.client.post(
            reverse("registration_manager_update", args=[registration.pk]),
            {"project_manager": "Иванов Иван Иванович"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "ok": True,
                "manager": "Иванов Иван Иванович",
                "managerValue": manager_employee.formatted_prs_id,
                "managerLabel": "Иванов И.И.",
            },
        )
        registration.refresh_from_db()
        self.assertEqual(registration.project_manager, "Иванов Иван Иванович")
        self.assertEqual(registration.project_manager_prs_id, manager_employee.formatted_prs_id)

    def test_registration_manager_update_allows_clearing_project_manager(self):
        registration = ProjectRegistration.objects.create(
            number=6206,
            group_member=self.group_member,
            agreement_type=ProjectRegistration.AgreementType.MAIN,
            type=self.product,
            name="Проект без руководителя",
            status="Не начат",
            year=2026,
            project_manager="Иванов Иван Иванович",
        )

        response = self.client.post(
            reverse("registration_manager_update", args=[registration.pk]),
            {"project_manager": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["managerLabel"], "")
        registration.refresh_from_db()
        self.assertEqual(registration.project_manager, "")
        self.assertEqual(registration.project_manager_prs_id, "")

    def test_registration_deadline_update_changes_project_deadline(self):
        registration = ProjectRegistration.objects.create(
            number=6207,
            group_member=self.group_member,
            agreement_type=ProjectRegistration.AgreementType.MAIN,
            type=self.product,
            name="Проект со сменой дедлайна",
            status="Не начат",
            year=2026,
        )

        response = self.client.post(
            reverse("registration_deadline_update", args=[registration.pk]),
            {"deadline": "2026-06-15"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"ok": True, "deadline": "2026-06-15", "deadlineLabel": "15.06.2026"},
        )
        registration.refresh_from_db()
        self.assertEqual(registration.deadline, date(2026, 6, 15))

    def test_registration_deadline_update_allows_clearing_project_deadline(self):
        registration = ProjectRegistration.objects.create(
            number=6208,
            group_member=self.group_member,
            agreement_type=ProjectRegistration.AgreementType.MAIN,
            type=self.product,
            name="Проект без дедлайна",
            status="Не начат",
            year=2026,
            deadline=date(2026, 6, 15),
        )

        response = self.client.post(
            reverse("registration_deadline_update", args=[registration.pk]),
            {"deadline": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "deadline": "", "deadlineLabel": ""})
        registration.refresh_from_db()
        self.assertIsNone(registration.deadline)

    def test_registration_deadline_update_rejects_invalid_date(self):
        registration = ProjectRegistration.objects.create(
            number=6209,
            group_member=self.group_member,
            agreement_type=ProjectRegistration.AgreementType.MAIN,
            type=self.product,
            name="Проект с ошибочным дедлайном",
            status="Не начат",
            year=2026,
        )

        response = self.client.post(
            reverse("registration_deadline_update", args=[registration.pk]),
            {"deadline": "15.06.2026"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        registration.refresh_from_db()
        self.assertIsNone(registration.deadline)


class ProjectRegistrationRegistrySyncTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="projects-registry-user",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.group_member = GroupMember.objects.create(
            short_name="IMC",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
            position=1,
        )
        self.product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
            position=1,
        )
        self.second_product = Product.objects.create(
            short_name="QAQC_SYNC",
            name_en="QAQC Sync",
            name_ru="QAQC Sync",
            consulting_type="Горный",
            service_category="Контроль",
            service_subtype="Контроль качества",
            position=2,
        )
        self.country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            full_name="Российская Федерация",
            alpha2="RU",
            alpha3="RUS",
            position=1,
        )

    def _post_registration(self, **extra):
        payload = {
            "number": 4444,
            "group_member": self.group_member.pk,
            "agreement_type": "MAIN",
            "type_id": [self.product.pk],
            "name": "Проект Альфа",
            "status": "Не начат",
            "deadline": "2026-01-10",
            "year": 2026,
            "customer": 'ООО "Синхронизация"',
            "country": self.country.pk,
            "identifier": "ОГРН",
            "registration_number": "1234567890",
            "registration_date": "2025-02-10",
            "project_manager": "",
            "customer_autocomplete_identifier_record_id": "",
            "customer_autocomplete_selected_from_autocomplete": "0",
        }
        payload.update(extra)
        return self.client.post(reverse("registration_form_create"), payload)

    def test_manual_registration_save_creates_new_registry_chain(self):
        existing_entity = BusinessEntityRecord.objects.create(name='ООО "Синхронизация"', position=1)
        existing_identifier = BusinessEntityIdentifierRecord.objects.create(
            business_entity=existing_entity,
            identifier_type="ОГРН",
            registration_country=self.country,
            registration_region="Москва",
            registration_date=timezone.datetime(2025, 2, 10).date(),
            number="1234567890",
            valid_from=timezone.datetime(2025, 2, 10).date(),
            position=1,
        )
        LegalEntityRecord.objects.create(
            attribute=LegalEntityRecord.ATTRIBUTE_NAME,
            identifier_record=existing_identifier,
            short_name='ООО "Синхронизация"',
            registration_country=self.country,
            identifier="ОГРН",
            registration_number="1234567890",
            registration_date=timezone.datetime(2025, 2, 10).date(),
            position=1,
        )

        response = self._post_registration()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(BusinessEntityRecord.objects.count(), 2)
        self.assertEqual(
            LegalEntityRecord.objects.filter(
                attribute=LegalEntityRecord.ATTRIBUTE_NAME,
                short_name='ООО "Синхронизация"',
            ).count(),
            2,
        )
        newest_entity = BusinessEntityRecord.objects.order_by("-id").first()
        project = ProjectRegistration.objects.get(number=4444)
        self.assertEqual(newest_entity.source, "[Проекты / Заказчик]")
        self.assertEqual(newest_entity.record_author, "projects-registry-user")
        self.assertEqual(project.type_short_display, "DD")
        self.assertEqual(
            list(project.product_links.order_by("rank").values_list("product_id", flat=True)),
            [self.product.pk],
        )

    def test_manual_registration_save_allows_duplicate_identity_values(self):
        first = ProjectRegistration.objects.create(
            number=4444,
            group_member=self.group_member,
            agreement_type=ProjectRegistration.AgreementType.MAIN,
            agreement_number="IMCM/4444",
            type=self.product,
            name="Проект Альфа",
            status="Не начат",
            year=2026,
            position=1,
        )

        response = self._post_registration()

        self.assertEqual(response.status_code, 200)
        duplicates = list(
            ProjectRegistration.objects
            .filter(
                number=4444,
                group_member=self.group_member,
                agreement_type=ProjectRegistration.AgreementType.MAIN,
                agreement_number="IMCM/4444",
                type=self.product,
            )
            .order_by("id")
        )
        self.assertEqual(len(duplicates), 2)
        self.assertNotEqual(duplicates[0].pk, duplicates[1].pk)
        self.assertNotEqual(duplicates[0].short_uid, duplicates[1].short_uid)
        first.refresh_from_db()
        self.assertEqual(first.short_uid, duplicates[0].short_uid)
        self.assertEqual(duplicates[0].short_uid, "444410RU")
        self.assertEqual(duplicates[1].short_uid, "444420RU")
        self.assertEqual(
            list(duplicates[1].product_links.order_by("rank").values_list("product_id", flat=True)),
            [self.product.pk],
        )

    def test_selected_autocomplete_registration_save_does_not_create_new_chain(self):
        existing_entity = BusinessEntityRecord.objects.create(name='ООО "Связать"', position=1)
        existing_identifier = BusinessEntityIdentifierRecord.objects.create(
            business_entity=existing_entity,
            identifier_type="ОГРН",
            registration_country=self.country,
            registration_region="Москва",
            registration_date=timezone.datetime(2025, 2, 10).date(),
            number="1234567890",
            valid_from=timezone.datetime(2025, 2, 10).date(),
            position=1,
        )
        LegalEntityRecord.objects.create(
            attribute=LegalEntityRecord.ATTRIBUTE_NAME,
            identifier_record=existing_identifier,
            short_name='ООО "Связать"',
            registration_country=self.country,
            identifier="ОГРН",
            registration_number="1234567890",
            registration_date=timezone.datetime(2025, 2, 10).date(),
            position=1,
        )

        response = self._post_registration(
            customer='ООО "Связать"',
            customer_autocomplete_identifier_record_id=str(existing_identifier.pk),
            customer_autocomplete_selected_from_autocomplete="1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(BusinessEntityRecord.objects.count(), 1)

    def test_registration_create_and_work_deps_use_ranked_joined_products(self):
        response = self._post_registration(type_id=[self.product.pk, self.second_product.pk])

        self.assertEqual(response.status_code, 200)
        projects = list(ProjectRegistration.objects.filter(number=4444).order_by("position", "id"))
        self.assertEqual(len(projects), 2)
        self.assertEqual([project.type_short_display for project in projects], ["DD", self.second_product.short_name])
        self.assertEqual([project.short_uid for project in projects], ["444410RU", "444420RU"])
        self.assertEqual(
            list(projects[0].product_links.order_by("rank").values_list("product_id", flat=True)),
            [self.product.pk],
        )
        self.assertEqual(
            list(projects[1].product_links.order_by("rank").values_list("product_id", flat=True)),
            [self.second_product.pk],
        )
        self.assertEqual(BusinessEntityRecord.objects.count(), 1)

        deps_response = self.client.get(reverse("work_deps"), {"project": projects[1].pk})

        self.assertEqual(deps_response.status_code, 200)
        self.assertEqual(deps_response.json()["type_short"], self.second_product.short_name)


class WorkVolumePerformerCreationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="performers-view-user",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
        )
        self.second_product = Product.objects.create(
            short_name="QAQC_WORK",
            name_en="QAQC Work",
            name_ru="QAQC Work",
            consulting_type="Горный",
            service_category="Контроль",
            service_subtype="Контроль качества",
            position=2,
        )
        self.project_manager_employee = self._create_employee(
            username="project.manager",
            first_name="Иван",
            last_name="Иванов",
            patronymic="Иванович",
        )
        self.first_manager_employee = self._create_employee(
            username="asset.manager.one",
            first_name="Петр",
            last_name="Петров",
            patronymic="Петрович",
        )
        self.second_manager_employee = self._create_employee(
            username="asset.manager.two",
            first_name="Сидор",
            last_name="Сидоров",
            patronymic="Сидорович",
        )
        self.project_manager_name = "Иванов Иван Иванович"
        self.first_manager_name = "Петров Петр Петрович"
        self.second_manager_name = "Сидоров Сидор Сидорович"
        self.project = ProjectRegistration.objects.create(
            number=6001,
            type=self.product,
            name="Проект активов",
            year=2026,
            project_manager=self.project_manager_name,
        )
        ProjectRegistrationProduct.objects.create(
            registration=self.project,
            product=self.product,
            rank=1,
        )
        ProjectRegistrationProduct.objects.create(
            registration=self.project,
            product=self.second_product,
            rank=2,
        )
        self.product.sections.create(
            code="PRD",
            short_name="Project Director",
            short_name_ru="Руководитель проекта",
            name_en="Project Director",
            name_ru="Руководитель проекта",
            accounting_type="Раздел",
            position=1,
        )
        self.product.sections.create(
            code="PRJ",
            short_name="Project Manager",
            short_name_ru="Менеджер проекта",
            name_en="Project Manager",
            name_ru="Менеджер проекта",
            accounting_type="Раздел",
            position=2,
        )
        self.product.sections.create(
            code="CRD",
            short_name="Coordinator",
            short_name_ru="Координатор",
            name_en="Coordinator",
            name_ru="Координатор",
            accounting_type="Раздел",
            position=3,
        )
        self.second_product.sections.create(
            code="QA",
            short_name="QA Section",
            short_name_ru="QA раздел",
            name_en="QA Section",
            name_ru="QA раздел",
            accounting_type="Раздел",
            position=1,
        )

    def _create_employee(self, *, username, first_name, last_name, patronymic):
        user = get_user_model().objects.create_user(
            username=username,
            password="secret",
            first_name=first_name,
            last_name=last_name,
            is_staff=True,
        )
        return Employee.objects.create(user=user, patronymic=patronymic)

    def test_work_volume_form_uses_project_manager_label(self):
        form = WorkVolumeForm()

        self.assertEqual(form.fields["manager"].label, "Менеджер проекта")

    def test_equal_project_manager_and_manager_skips_prj_and_assigns_prd_to_project_manager(self):
        work_item = WorkVolume.objects.create(
            project=self.project,
            name="Актив 1",
            asset_name="Актив 1",
            manager=self.project_manager_name,
        )

        self.assertFalse(
            Performer.objects.filter(work_item=work_item, typical_section__code="PRJ").exists()
        )
        prd = Performer.objects.get(work_item=work_item, typical_section__code="PRD")
        self.assertEqual(prd.executor, self.project_manager_name)
        self.assertEqual(prd.employee, self.project_manager_employee)

    def test_different_manager_creates_prj_and_does_not_duplicate_prd_or_crd(self):
        first_work_item = WorkVolume.objects.create(
            project=self.project,
            name="Актив 1",
            asset_name="Актив 1",
            manager=self.first_manager_name,
        )

        self.assertTrue(
            Performer.objects.filter(work_item=first_work_item, typical_section__code="PRD").exists()
        )
        self.assertTrue(
            Performer.objects.filter(work_item=first_work_item, typical_section__code="PRJ").exists()
        )

        second_work_item = WorkVolume.objects.create(
            project=self.project,
            name="Актив 2",
            asset_name="Актив 2",
            manager=self.second_manager_name,
        )

        self.assertEqual(
            Performer.objects.filter(registration=self.project, typical_section__code="PRD").count(),
            1,
        )
        self.assertEqual(
            Performer.objects.filter(registration=self.project, typical_section__code="CRD").count(),
            1,
        )
        self.assertEqual(
            Performer.objects.filter(registration=self.project, typical_section__code="PRJ").count(),
            2,
        )

        first_prj = Performer.objects.get(work_item=first_work_item, typical_section__code="PRJ")
        second_prj = Performer.objects.get(work_item=second_work_item, typical_section__code="PRJ")
        prd = Performer.objects.get(registration=self.project, typical_section__code="PRD")

        self.assertEqual(first_prj.executor, self.first_manager_name)
        self.assertEqual(first_prj.employee, self.first_manager_employee)
        self.assertEqual(second_prj.executor, self.second_manager_name)
        self.assertEqual(second_prj.employee, self.second_manager_employee)
        self.assertEqual(prd.executor, self.project_manager_name)
        self.assertEqual(prd.employee, self.project_manager_employee)

    def test_multi_product_work_item_creates_sections_grouped_by_ranked_products(self):
        work_item = WorkVolume.objects.create(
            project=self.project,
            name="Актив 3",
            asset_name="Актив 3",
            manager=self.first_manager_name,
        )

        codes = list(
            Performer.objects
            .filter(work_item=work_item)
            .order_by("position", "id")
            .values_list("typical_section__code", flat=True)
        )

        self.assertEqual(codes, ["PRD", "PRJ", "CRD", "QA"])

    def test_performers_partial_shows_section_product_in_main_table(self):
        WorkVolume.objects.create(
            project=self.project,
            name="Актив 3",
            asset_name="Актив 3",
            manager=self.first_manager_name,
        )

        response = self.client.get(reverse("performers_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<th class=\"text-nowrap\">Продукт</th>", html=False)
        self.assertContains(response, self.second_product.short_name)
        content = response.content.decode("utf-8")
        main_table = content[
            content.index('id="performers-main-section"'):
            content.index('id="participation-confirmation-section"')
        ]
        self.assertNotIn("<th>Аванс</th>", main_table)
        self.assertNotIn("<th>Окон. платёж</th>", main_table)
        self.assertNotIn("<th>№ договора</th>", main_table)

        performer = Performer.objects.filter(registration=self.project).first()
        form_response = self.client.get(reverse("performer_form_edit", args=[performer.pk]))

        self.assertEqual(form_response.status_code, 200)
        form_content = form_response.content.decode("utf-8")
        self.assertNotIn('name="prepayment"', form_content)
        self.assertNotIn('name="final_payment"', form_content)
        self.assertNotIn('name="contract_number"', form_content)

    def test_performers_partial_splits_project_subsections(self):
        response = self.client.get(reverse("performers_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="projects-content-team" class="projects-section-content d-none"', html=False)
        self.assertContains(response, 'id="projects-content-info-request" class="projects-section-content d-none"', html=False)
        self.assertContains(response, 'id="performers-main-section"', html=False)
        self.assertContains(response, 'id="participation-confirmation-section"', html=False)
        self.assertContains(response, 'id="info-request-approval-section"', html=False)

        content = response.content.decode("utf-8")
        self.assertLess(
            content.index('id="projects-content-team"'),
            content.index('id="performers-main-section"'),
        )
        self.assertLess(
            content.index('id="participation-confirmation-section"'),
            content.index('id="projects-content-info-request"'),
        )
        self.assertLess(
            content.index('id="projects-content-info-request"'),
            content.index('id="info-request-approval-section"'),
        )

    def test_direction_director_uses_project_manager_executor_locking(self):
        Employee.objects.create(user=self.user, role=DIRECTION_DIRECTOR_GROUP)
        company = GroupMember.objects.create(
            short_name="IMC",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
            position=10,
        )
        direction = OrgUnit.objects.create(
            company=company,
            level=2,
            department_name="Налоговое направление",
            short_name="TAX",
            unit_type="expertise",
        )
        section = self.product.sections.create(
            code="TAX",
            short_name="Tax",
            short_name_ru="Налоги",
            name_en="Tax",
            name_ru="Налоги",
            accounting_type="Раздел",
            expertise_direction=direction,
            position=4,
        )
        Performer.objects.create(
            registration=self.project,
            asset_name="Актив с направлением",
            executor="Эксперт",
            typical_section=section,
        )

        response = self.client.get(reverse("performers_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "performer-locked-icon")


class ProjectProductLinkSyncTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="project-link-staff",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
        )
        self.second_product = Product.objects.create(
            short_name="QAQC_LINK",
            name_en="QAQC Link",
            name_ru="QAQC Link",
            consulting_type="Горный",
            service_category="Контроль",
            service_subtype="Контроль качества",
            position=2,
        )
        self.project = ProjectRegistration.objects.create(
            number=6101,
            type=self.product,
            name="Связанный проект",
            year=2026,
        )
        ProjectRegistrationProduct.objects.create(
            registration=self.project,
            product=self.product,
            rank=1,
        )
        ProjectRegistrationProduct.objects.create(
            registration=self.project,
            product=self.second_product,
            rank=2,
        )
        self.work_item = WorkVolume.objects.create(
            project=self.project,
            asset_name="Актив 1",
            manager="Менеджер",
            position=1,
        )
        self.legal_entity = LegalEntity.objects.get(work_item=self.work_item)

    def test_product_short_name_change_updates_joined_work_and_legal_rows(self):
        self.product.short_name = "CONS"
        self.product.save()

        self.work_item.refresh_from_db()
        self.legal_entity.refresh_from_db()

        self.project.refresh_from_db()

        expected_type = f"CONS-{self.second_product.short_name}"
        self.assertEqual(self.project.type_short_display, expected_type)
        self.assertEqual(self.work_item.type, expected_type)
        self.assertEqual(self.legal_entity.work_type, expected_type)

        response = self.client.get(reverse("projects_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, expected_type)
        self.assertNotContains(response, '<td class="text-nowrap">DD</td>', html=False)

    def test_projects_partial_splits_scope_tables_to_separate_subsection(self):
        ProjectRegistration.objects.create(
            number=6102,
            type=self.product,
            name="Проект в работе",
            status="В работе",
            year=2026,
        )

        response = self.client.get(reverse("projects_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="projects-content-launch" class="projects-section-content"', html=False)
        self.assertContains(response, 'id="projects-content-scope" class="projects-section-content d-none"', html=False)
        self.assertContains(response, "Реестр проектов")
        self.assertContains(response, "Запуск")
        self.assertContains(response, 'data-registration-launch', html=False)
        self.assertContains(response, 'data-registration-status', html=False)
        self.assertContains(response, 'data-registration-manager', html=False)
        self.assertContains(response, 'data-registration-deadline', html=False)
        self.assertContains(response, 'id="registration-status-editor"', html=False)
        self.assertContains(response, 'id="registration-manager-editor"', html=False)
        self.assertContains(response, 'id="registration-deadline-editor"', html=False)
        self.assertContains(response, 'bi bi-play-circle', html=False)
        self.assertContains(response, 'bi bi-circle', html=False)
        self.assertContains(response, 'reg-launch-status--work', html=False)
        self.assertContains(response, "Сроки проекта по договору")
        self.assertContains(response, "Объем услуг: активы")
        self.assertContains(response, "Объем услуг: юрлица")

        content = response.content.decode("utf-8")
        self.assertLess(
            content.index('id="projects-content-launch"'),
            content.index("Реестр проектов"),
        )
        self.assertLess(
            content.index("Сроки проекта по договору"),
            content.index('id="projects-content-scope"'),
        )
        self.assertLess(
            content.index('id="projects-content-scope"'),
            content.index("Объем услуг: активы"),
        )
        self.assertLess(
            content.index("Объем услуг: активы"),
            content.index("Объем услуг: юрлица"),
        )


class ExpertProjectVisibilityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="projects-expert",
            password="secret",
            is_staff=True,
            first_name="Иван",
            last_name="Эксперт",
        )
        self.employee = Employee.objects.create(
            user=self.user,
            patronymic="Иванович",
            role=EXPERT_GROUP,
        )
        self.client.force_login(self.user)
        self.product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
        )
        self.confirmed_project = ProjectRegistration.objects.create(
            number=7001,
            type=self.product,
            name="Подтвержденный проект",
            year=2026,
        )
        self.declined_project = ProjectRegistration.objects.create(
            number=7002,
            type=self.product,
            name="Отклоненный проект",
            year=2026,
        )
        self.requested_project = ProjectRegistration.objects.create(
            number=7003,
            type=self.product,
            name="Проект с запросом участия",
            year=2026,
        )
        WorkVolume.objects.create(
            project=self.confirmed_project,
            name="Подтвержденный актив",
            asset_name="Подтвержденный актив",
            manager="Менеджер",
        )
        WorkVolume.objects.create(
            project=self.declined_project,
            name="Отклоненный актив",
            asset_name="Отклоненный актив",
            manager="Менеджер",
        )
        WorkVolume.objects.create(
            project=self.requested_project,
            name="Актив с запросом участия",
            asset_name="Актив с запросом участия",
            manager="Менеджер",
        )
        Performer.objects.create(
            registration=self.confirmed_project,
            asset_name="Подтвержденный актив",
            executor=Performer.employee_full_name(self.employee),
            employee=self.employee,
            participation_response=Performer.ParticipationResponse.CONFIRMED,
        )
        Performer.objects.create(
            registration=self.declined_project,
            asset_name="Отклоненный актив",
            executor=Performer.employee_full_name(self.employee),
            employee=self.employee,
            participation_response=Performer.ParticipationResponse.DECLINED,
        )
        Performer.objects.create(
            registration=self.requested_project,
            asset_name="Актив с запросом участия",
            executor=Performer.employee_full_name(self.employee),
            employee=self.employee,
            participation_request_sent_at=timezone.now(),
        )

    def test_projects_partial_for_expert_shows_confirmed_and_requested_participation_projects(self):
        response = self.client.get(reverse("projects_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.confirmed_project.name)
        self.assertContains(response, self.confirmed_project.short_uid)
        self.assertContains(response, self.requested_project.name)
        self.assertContains(response, self.requested_project.short_uid)
        self.assertNotContains(response, self.declined_project.name)
        self.assertNotContains(response, self.declined_project.short_uid)
        self.assertNotContains(response, "Отклоненный актив")

    def test_performers_partial_for_expert_shows_confirmed_and_requested_participation_projects(self):
        response = self.client.get(reverse("performers_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.confirmed_project.name)
        self.assertContains(response, self.confirmed_project.short_uid)
        self.assertContains(response, self.requested_project.name)
        self.assertContains(response, self.requested_project.short_uid)
        self.assertNotContains(response, self.declined_project.name)
        self.assertNotContains(response, self.declined_project.short_uid)
        self.assertNotContains(response, "Отклоненный актив")

    def test_projects_partial_for_expert_is_readonly(self):
        response = self.client.get(reverse("projects_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "products-actions-row")
        content = response.content.decode("utf-8")
        for checkbox_id in (
            "registrations-master",
            f"reg-sel-{self.confirmed_project.pk}",
            "contract-conditions-master",
            f"contract-sel-{self.confirmed_project.pk}",
            "work-master",
            "legal-entities-master",
        ):
            checkbox_start = content.index(f'id="{checkbox_id}"')
            checkbox_html = content[checkbox_start:content.index("aria-label", checkbox_start)]
            self.assertIn("disabled", checkbox_html)
        work_item = WorkVolume.objects.get(project=self.confirmed_project)
        checkbox_start = content.index(f'id="work-sel-{work_item.pk}"')
        checkbox_html = content[checkbox_start:content.index("aria-label", checkbox_start)]
        self.assertIn("disabled", checkbox_html)

    def test_performers_partial_for_expert_is_readonly(self):
        response = self.client.get(reverse("performers_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "products-actions-row")
        self.assertContains(response, "performer-locked-icon")
        self.assertNotContains(response, "performer-quick-edit")
        self.assertContains(response, 'id="participation-confirmation-section" class="mt-5" data-expert-readonly="1"', html=False)
        self.assertNotContains(response, "Скоррект. затраты")
        self.assertNotContains(response, "Расч. затраты")
        self.assertNotContains(response, "Согласовано")
        self.assertNotContains(response, 'id="perf-total-actual"', html=False)
        content = response.content.decode("utf-8")
        performer = Performer.objects.get(registration=self.confirmed_project)
        for checkbox_id in (
            "performers-master",
            f"perf-sel-{performer.pk}",
            "participation-master",
            f"participation-sel-{performer.pk}",
            "info-request-master",
            f"info-request-sel-{performer.pk}",
        ):
            checkbox_start = content.index(f'id="{checkbox_id}"')
            checkbox_html = content[checkbox_start:content.index("aria-label", checkbox_start)]
            self.assertIn("disabled", checkbox_html)

    def test_group_expert_with_empty_employee_role_is_still_filtered(self):
        self.employee.role = ""
        self.employee.save(update_fields=["role"])
        expert_group, _ = Group.objects.get_or_create(name=EXPERT_GROUP)
        self.user.groups.add(expert_group)

        projects_response = self.client.get(reverse("projects_partial"))
        performers_response = self.client.get(reverse("performers_partial"))

        self.assertEqual(projects_response.status_code, 200)
        self.assertContains(projects_response, self.confirmed_project.name)
        self.assertNotContains(projects_response, self.declined_project.name)
        self.assertNotContains(projects_response, "Отклоненный актив")
        self.assertEqual(performers_response.status_code, 200)
        self.assertContains(performers_response, self.confirmed_project.name)
        self.assertNotContains(performers_response, self.declined_project.name)
        self.assertNotContains(performers_response, "Отклоненный актив")


class CloudStorageProjectRoutingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="project-staff",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
        )
        self.project = ProjectRegistration.objects.create(
            number=5001,
            type=self.product,
            name="Проект маршрутизации",
            year=2026,
        )

    def test_create_workspace_returns_controlled_error_when_nextcloud_selected(self):
        settings_obj = CloudStorageSettings.get_solo()
        settings_obj.primary_storage = CloudStorageSettings.PrimaryStorage.NEXTCLOUD
        settings_obj.save()

        response = self.client.post(
            reverse("create_workspace"),
            {"project_id": self.project.pk},
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertIn("Nextcloud", payload["error"])

    def test_projects_partial_uses_current_primary_cloud_label_in_workspace_modal(self):
        settings_obj = CloudStorageSettings.get_solo()
        settings_obj.primary_storage = CloudStorageSettings.PrimaryStorage.NEXTCLOUD
        settings_obj.save()

        response = self.client.get(reverse("projects_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="reg-create-workspace-storage-label">Nextcloud', html=False)

    def test_workspace_folders_list_returns_current_primary_cloud_label(self):
        settings_obj = CloudStorageSettings.get_solo()
        settings_obj.primary_storage = CloudStorageSettings.PrimaryStorage.NEXTCLOUD
        settings_obj.save()

        response = self.client.get(reverse("workspace_folders_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["storage_label"], "Nextcloud")

    def test_performers_partial_no_longer_renders_contract_conclusion_table(self):
        settings_obj = CloudStorageSettings.get_solo()
        settings_obj.primary_storage = CloudStorageSettings.PrimaryStorage.NEXTCLOUD
        settings_obj.save()

        response = self.client.get(reverse("performers_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Заключение договора")
        self.assertNotContains(response, "create-contract-progress-modal")

    def test_performers_partial_uses_current_primary_cloud_label_in_source_data_modal(self):
        settings_obj = CloudStorageSettings.get_solo()
        settings_obj.primary_storage = CloudStorageSettings.PrimaryStorage.NEXTCLOUD
        settings_obj.save()

        response = self.client.get(reverse("performers_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "На Nextcloud в целевой директории будет создана структура папок для выбранного проекта в соответствии с согласованным информационным запросом.",
            html=False,
        )


@override_settings(
    NEXTCLOUD_PROVISIONING_BASE_URL="https://cloud.example.com",
    NEXTCLOUD_PROVISIONING_USERNAME="cloud-admin",
    NEXTCLOUD_PROVISIONING_TOKEN="token",
    NEXTCLOUD_OIDC_PROVIDER_ID=1,
)
class NextcloudSourceDataWorkspaceFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="source-data-staff",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)
        settings_obj = CloudStorageSettings.get_solo()
        settings_obj.primary_storage = CloudStorageSettings.PrimaryStorage.NEXTCLOUD
        settings_obj.nextcloud_root_path = "/Corporate Root"
        settings_obj.save()
        self.product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
        )
        self.project = ProjectRegistration.objects.create(
            number=5003,
            type=self.product,
            name="Исходные данные",
            year=2026,
        )
        self.section = self.product.sections.create(
            code="FIN",
            short_name="Finance",
            short_name_ru="Финансы",
            name_en="Finance",
            name_ru="Финансы",
            accounting_type="Раздел",
            position=1,
        )
        self.item = ChecklistItem.objects.create(
            project=self.project,
            section=self.section,
            code="REQ",
            number=1,
            short_name="ОСВ",
            name="Оборотно-сальдовая ведомость",
            position=1,
        )
        Performer.objects.create(
            registration=self.project,
            asset_name="ООО Ромашка",
            typical_section=self.section,
            info_approval_status=Performer.InfoApprovalStatus.APPROVED,
        )
        SourceDataTargetFolder.objects.create(user=self.user, folder_name="05 Исходные данные/01 Запросы")

    @patch("nextcloud_app.api.NextcloudApiClient.ensure_public_link_share")
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_folder")
    def test_create_source_data_workspace_uses_nextcloud_and_stores_public_links(
        self,
        mocked_ensure_folder,
        mocked_public_share,
    ):
        expected_project_folder = f"{self.project.short_uid} DD Исходные данные"
        base_path = f"/Corporate Root/03 Проекты/2026/{expected_project_folder}/05 Исходные данные/01 Запросы"
        section_path = f"{base_path}/01 FIN Финансы"
        item_path = f"{section_path}/REQ-01 ОСВ"
        mocked_ensure_folder.side_effect = [section_path, item_path]
        mocked_public_share.return_value = "https://cloud.example.com/s/item-folder"

        response = self.client.post(
            reverse("create_source_data_workspace"),
            {"project_id": self.project.pk},
        )

        self.assertEqual(response.status_code, 200)
        chunks = [json.loads(chunk.decode("utf-8").strip()) for chunk in response.streaming_content]
        self.assertTrue(chunks[-1]["ok"])
        self.assertIn("Nextcloud", chunks[-1]["message"])

        mocked_ensure_folder.assert_has_calls(
            [
                call("cloud-admin", section_path),
                call("cloud-admin", item_path),
            ]
        )
        mocked_public_share.assert_has_calls(
            [
                call("cloud-admin", item_path, _quick=True),
            ]
        )

        section_folder = SourceDataSectionFolder.objects.get(project=self.project, section=self.section, asset_name="ООО Ромашка")
        item_folder = SourceDataItemFolder.objects.get(
            project=self.project,
            checklist_item=self.item,
            asset_name="ООО Ромашка",
        )
        workspace = SourceDataWorkspace.objects.get(project=self.project)
        self.assertEqual(section_folder.disk_path, section_path)
        self.assertEqual(section_folder.public_url, "")
        self.assertEqual(item_folder.disk_path, item_path)
        self.assertEqual(item_folder.public_url, "https://cloud.example.com/s/item-folder")
        self.assertEqual(workspace.disk_path, base_path)
        self.assertEqual(workspace.created_by, self.user)


@override_settings(
    NEXTCLOUD_PROVISIONING_BASE_URL="https://cloud.example.com",
    NEXTCLOUD_PROVISIONING_USERNAME="cloud-admin",
    NEXTCLOUD_PROVISIONING_TOKEN="token",
    NEXTCLOUD_OIDC_PROVIDER_ID=1,
)
class NextcloudContractProjectFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="contracts-staff",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)
        settings_obj = CloudStorageSettings.get_solo()
        settings_obj.primary_storage = CloudStorageSettings.PrimaryStorage.NEXTCLOUD
        settings_obj.nextcloud_root_path = "/Corporate Root"
        settings_obj.save()
        self.product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
        )
        self.project = ProjectRegistration.objects.create(
            number=5002,
            type=self.product,
            name="Контрактный проект",
            year=2026,
        )
        self.recipient_user = get_user_model().objects.create_user(
            username="performer@example.com",
            email="performer@example.com",
            password="secret",
            first_name="Иван",
            last_name="Иванов",
            is_staff=True,
        )
        self.employee = Employee.objects.create(
            user=self.recipient_user,
            patronymic="Иванович",
            employment="Фрилансер",
        )
        self.lawyer_user = get_user_model().objects.create_user(
            username="lawyer@example.com",
            email="lawyer@example.com",
            password="secret",
            is_staff=True,
        )
        lawyer_group, _ = Group.objects.get_or_create(name=LAWYER_GROUP)
        self.lawyer_user.groups.add(lawyer_group)
        self.performer = Performer.objects.create(
            registration=self.project,
            employee=self.employee,
            executor="Иванов Иван Иванович",
        )
        self.template = ContractTemplate.objects.create(
            product=self.product,
            contract_type="gph",
            party="individual",
            country_name="",
            sample_name="Базовый шаблон",
            version="1",
            file=SimpleUploadedFile(
                "contract.docx",
                b"fake-docx-content",
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            is_all_sections=True,
        )
        self.executor_link = NextcloudUserLink.objects.create(
            user=self.recipient_user,
            nextcloud_user_id=f"ncstaff-{self.recipient_user.pk}",
            nextcloud_username=f"ncstaff-{self.recipient_user.pk}",
            nextcloud_email=self.recipient_user.email,
        )
        self.lawyer_link = NextcloudUserLink.objects.create(
            user=self.lawyer_user,
            nextcloud_user_id=f"ncstaff-{self.lawyer_user.pk}",
            nextcloud_username=f"ncstaff-{self.lawyer_user.pk}",
            nextcloud_email=self.lawyer_user.email,
        )

    @patch("nextcloud_app.provisioning.ensure_nextcloud_account")
    @patch("contracts_app.variable_resolver.resolve_variables", return_value=({}, {}))
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_user_share")
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_public_link_share", return_value="https://cloud.example.com/s/public-doc")
    @patch("nextcloud_app.api.NextcloudApiClient.upload_file", return_value=True)
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_folder", return_value="/Corporate Root/02 Договоры/2026/5002 DD Контрактный проект/02 Исполнители/000 Иванов ИИ")
    @patch("nextcloud_app.api.NextcloudApiClient.list_resources", return_value=[])
    def test_create_contract_project_uses_nextcloud_and_stores_public_link(
        self,
        mocked_list_resources,
        mocked_ensure_folder,
        mocked_upload_file,
        mocked_public_share,
        mocked_ensure_user_share,
        mocked_resolve_variables,
        mocked_ensure_nextcloud_account,
    ):
        mocked_ensure_nextcloud_account.side_effect = lambda user, client=None: (
            self.executor_link if user.pk == self.recipient_user.pk else self.lawyer_link
        )
        response = self.client.post(
            reverse("create_contract_project"),
            {"performer_ids[]": [self.performer.pk]},
        )

        self.assertEqual(response.status_code, 200)
        chunks = [json.loads(chunk.decode("utf-8").strip()) for chunk in response.streaming_content]
        self.assertEqual(chunks[-1]["ok"], True, chunks)

        self.performer.refresh_from_db()
        expected_project_folder = f"{self.project.short_uid} DD Контрактный проект"
        expected_base_path = f"/Corporate Root/02 Договоры/2026/{expected_project_folder}/02 Исполнители"
        expected_folder_path = f"{expected_base_path}/000 Иванов ИИ"
        expected_docx_name = f"Договор {self.project.short_uid}_Иванов ИИ.docx"
        expected_upload_path = f"{expected_folder_path}/{expected_docx_name}"

        mocked_list_resources.assert_any_call("cloud-admin", expected_base_path, limit=1000)
        mocked_ensure_folder.assert_has_calls(
            [
                call("cloud-admin", "/Corporate Root"),
                call("cloud-admin", "/Corporate Root/02 Договоры"),
                call("cloud-admin", "/Corporate Root/02 Договоры/2026"),
                call("cloud-admin", f"/Corporate Root/02 Договоры/2026/{expected_project_folder}"),
                call("cloud-admin", expected_base_path),
                call("cloud-admin", expected_folder_path),
            ]
        )
        mocked_upload_file.assert_called_once()
        self.assertEqual(mocked_upload_file.call_args.args[0], "cloud-admin")
        self.assertEqual(mocked_upload_file.call_args.args[1], expected_upload_path)
        mocked_public_share.assert_has_calls(
            [
                call("cloud-admin", expected_folder_path),
                call("cloud-admin", expected_upload_path),
            ]
        )
        mocked_ensure_user_share.assert_has_calls(
            [
                call("cloud-admin", expected_folder_path, self.executor_link.nextcloud_user_id, permissions=1),
                call("cloud-admin", expected_folder_path, self.lawyer_link.nextcloud_user_id, permissions=15),
            ],
            any_order=True,
        )
        self.assertTrue(self.performer.contract_project_created)
        self.assertEqual(self.performer.contract_project_link, "https://cloud.example.com/s/public-doc")
        self.assertEqual(self.performer.contract_project_folder_link, "https://cloud.example.com/s/public-doc")
        self.assertEqual(self.performer.contract_project_disk_folder, expected_folder_path)
        self.assertEqual(self.performer.contract_file, expected_docx_name)
        self.assertIsNotNone(self.performer.contract_project_created_at)
        self.assertIsNotNone(self.performer.contract_date)

    @patch("nextcloud_app.provisioning.ensure_nextcloud_account")
    @patch("contracts_app.variable_resolver.resolve_variables", return_value=({}, {}))
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_user_share")
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_public_link_share", return_value="https://cloud.example.com/s/public-doc")
    @patch("nextcloud_app.api.NextcloudApiClient.upload_file", return_value=True)
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_folder", return_value="/Corporate Root/02 Договоры/2026/5002 DD Контрактный проект/02 Исполнители/000 Иванов ИИ")
    @patch("nextcloud_app.api.NextcloudApiClient.list_resources", return_value=[])
    def test_create_contract_project_uses_saved_contract_number_and_date(
        self,
        mocked_list_resources,
        mocked_ensure_folder,
        mocked_upload_file,
        mocked_public_share,
        mocked_ensure_user_share,
        mocked_resolve_variables,
        mocked_ensure_nextcloud_account,
    ):
        pending_batch_id = uuid.uuid4()
        self.performer.contract_batch_id = pending_batch_id
        self.performer.contract_number = "CUSTOM-42"
        self.performer.contract_date = date(2026, 4, 15)
        self.performer.save(update_fields=["contract_batch_id", "contract_number", "contract_date"])
        mocked_ensure_nextcloud_account.side_effect = lambda user, client=None: (
            self.executor_link if user.pk == self.recipient_user.pk else self.lawyer_link
        )

        response = self.client.post(
            reverse("create_contract_project"),
            {"performer_ids[]": [self.performer.pk]},
        )

        self.assertEqual(response.status_code, 200)
        chunks = [json.loads(chunk.decode("utf-8").strip()) for chunk in response.streaming_content]
        self.assertEqual(chunks[-1]["ok"], True, chunks)
        mocked_resolve_variables.assert_called()
        resolved_performer = mocked_resolve_variables.call_args.args[0]
        self.assertEqual(resolved_performer.contract_number, "CUSTOM-42")
        self.assertEqual(resolved_performer.contract_date, date(2026, 4, 15))
        self.performer.refresh_from_db()
        self.assertEqual(self.performer.contract_batch_id, pending_batch_id)
        self.assertFalse(self.performer.contract_is_addendum)
        self.assertEqual(self.performer.contract_number, "CUSTOM-42")
        self.assertEqual(self.performer.contract_date, date(2026, 4, 15))

    @patch("nextcloud_app.provisioning.ensure_nextcloud_account")
    @patch("contracts_app.variable_resolver.resolve_variables", return_value=({}, {}))
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_user_share")
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_public_link_share", return_value="https://cloud.example.com/s/reused-doc")
    @patch("nextcloud_app.api.NextcloudApiClient.upload_file", return_value=True)
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_folder", return_value="/Corporate Root/02 Договоры/2026/5002 DD Контрактный проект/02 Исполнители/000 Иванов ИИ")
    @patch("nextcloud_app.api.NextcloudApiClient.list_resources", return_value=[])
    def test_create_contract_project_reuses_existing_executor_folder_for_regeneration(
        self,
        mocked_list_resources,
        mocked_ensure_folder,
        mocked_upload_file,
        mocked_public_share,
        mocked_ensure_user_share,
        mocked_resolve_variables,
        mocked_ensure_nextcloud_account,
    ):
        existing_batch_id = uuid.uuid4()
        existing_folder_path = "/Corporate Root/02 Договоры/2026/5002 DD Контрактный проект/02 Исполнители/000 Иванов ИИ"
        self.performer.contract_batch_id = existing_batch_id
        self.performer.contract_project_created = True
        self.performer.contract_project_disk_folder = existing_folder_path
        self.performer.contract_project_folder_link = "https://cloud.example.com/s/existing-folder"
        self.performer.contract_project_folder_file_id = "folder-file-id"
        self.performer.contract_pdf_file = "old-contract.pdf"
        self.performer.contract_pdf_link = "https://cloud.example.com/s/old-pdf"
        self.performer.contract_pdf_file_id = "old-pdf-id"
        self.performer.contract_signed_pdf_file = "old-signed-contract.pdf"
        self.performer.contract_signed_pdf_link = "https://cloud.example.com/s/old-signed-pdf"
        self.performer.contract_signed_pdf_file_id = "old-signed-pdf-id"
        self.performer.save(update_fields=[
            "contract_batch_id",
            "contract_project_created",
            "contract_project_disk_folder",
            "contract_project_folder_link",
            "contract_project_folder_file_id",
            "contract_pdf_file",
            "contract_pdf_link",
            "contract_pdf_file_id",
            "contract_signed_pdf_file",
            "contract_signed_pdf_link",
            "contract_signed_pdf_file_id",
        ])
        mocked_ensure_nextcloud_account.side_effect = lambda user, client=None: (
            self.executor_link if user.pk == self.recipient_user.pk else self.lawyer_link
        )

        response = self.client.post(
            reverse("create_contract_project"),
            {"performer_ids[]": [self.performer.pk]},
        )

        self.assertEqual(response.status_code, 200)
        chunks = [json.loads(chunk.decode("utf-8").strip()) for chunk in response.streaming_content]
        self.assertEqual(chunks[-1]["ok"], True, chunks)
        mocked_upload_file.assert_called_once()
        self.assertEqual(
            mocked_upload_file.call_args.args[1],
            f"{existing_folder_path}/Договор {self.project.short_uid}_Иванов ИИ.docx",
        )
        self.assertFalse(
            any("001 Иванов ИИ" in str(call_args) for call_args in mocked_ensure_folder.call_args_list),
            mocked_ensure_folder.call_args_list,
        )
        self.performer.refresh_from_db()
        self.assertEqual(self.performer.contract_batch_id, existing_batch_id)
        self.assertEqual(self.performer.contract_project_disk_folder, existing_folder_path)
        self.assertEqual(self.performer.contract_pdf_file, "")
        self.assertEqual(self.performer.contract_pdf_link, "")
        self.assertEqual(self.performer.contract_pdf_file_id, "")
        self.assertEqual(self.performer.contract_signed_pdf_file, "")
        self.assertEqual(self.performer.contract_signed_pdf_link, "")
        self.assertEqual(self.performer.contract_signed_pdf_file_id, "")

    @patch("nextcloud_app.provisioning.ensure_nextcloud_account")
    @patch("contracts_app.variable_resolver.resolve_variables", return_value=({}, {}))
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_user_share")
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_public_link_share", return_value="https://cloud.example.com/s/new-doc")
    @patch("nextcloud_app.api.NextcloudApiClient.upload_file", return_value=True)
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_folder", return_value="/Corporate Root/02 Договоры/2026/5002 DD Контрактный проект/02 Исполнители/000 Иванов ИИ")
    @patch("nextcloud_app.api.NextcloudApiClient.list_resources", return_value=[{"name": "000 Иванов ИИ"}])
    def test_create_contract_project_reuses_sent_batch_folder_when_creating_addendum(
        self,
        mocked_list_resources,
        mocked_ensure_folder,
        mocked_upload_file,
        mocked_public_share,
        mocked_ensure_user_share,
        mocked_resolve_variables,
        mocked_ensure_nextcloud_account,
    ):
        old_batch_id = uuid.uuid4()
        pending_batch_id = uuid.uuid4()
        expected_project_folder = f"{self.project.short_uid} DD Контрактный проект"
        old_folder_path = f"/Corporate Root/02 Договоры/2026/{expected_project_folder}/02 Исполнители/000 Иванов ИИ"
        self.performer.contract_batch_id = old_batch_id
        self.performer.contract_project_created = True
        self.performer.contract_project_disk_folder = old_folder_path
        self.performer.contract_project_folder_link = "https://cloud.example.com/s/existing-folder"
        self.performer.contract_file = "Договор 5002_Иванов ИИ.docx"
        self.performer.contract_sent_at = timezone.now()
        self.performer.save(update_fields=[
            "contract_batch_id",
            "contract_project_created",
            "contract_project_disk_folder",
            "contract_project_folder_link",
            "contract_file",
            "contract_sent_at",
        ])
        addendum_performer = Performer.objects.create(
            registration=self.project,
            employee=self.employee,
            executor="Иванов Иван Иванович",
            contract_batch_id=pending_batch_id,
        )
        mocked_ensure_nextcloud_account.side_effect = lambda user, client=None: (
            self.executor_link if user.pk == self.recipient_user.pk else self.lawyer_link
        )

        response = self.client.post(
            reverse("create_contract_project"),
            {"performer_ids[]": [self.performer.pk, addendum_performer.pk]},
        )

        self.assertEqual(response.status_code, 200)
        chunks = [json.loads(chunk.decode("utf-8").strip()) for chunk in response.streaming_content]
        self.assertEqual(chunks[-1]["ok"], True, chunks)
        mocked_upload_file.assert_called_once()
        self.assertEqual(
            mocked_upload_file.call_args.args[1],
            f"{old_folder_path}/Договор {self.project.short_uid}_Иванов ИИ_ДС1.docx",
        )
        self.performer.refresh_from_db()
        addendum_performer.refresh_from_db()
        self.assertEqual(self.performer.contract_batch_id, old_batch_id)
        self.assertEqual(self.performer.contract_project_disk_folder, old_folder_path)
        self.assertEqual(addendum_performer.contract_batch_id, pending_batch_id)
        self.assertTrue(addendum_performer.contract_is_addendum)
        self.assertEqual(addendum_performer.contract_addendum_number, 1)
        self.assertEqual(addendum_performer.contract_project_disk_folder, old_folder_path)
        self.assertEqual(addendum_performer.contract_project_folder_link, "https://cloud.example.com/s/existing-folder")
        self.assertEqual(addendum_performer.contract_file, f"Договор {self.project.short_uid}_Иванов ИИ_ДС1.docx")

    @patch("nextcloud_app.provisioning.ensure_nextcloud_account")
    @patch("contracts_app.variable_resolver.resolve_variables", return_value=({}, {}))
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_user_share")
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_public_link_share", return_value="https://cloud.example.com/s/image-doc")
    @patch("nextcloud_app.api.NextcloudApiClient.upload_file", return_value=True)
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_folder", return_value="/Corporate Root/02 Договоры/2026/5002 DD Контрактный проект/02 Исполнители/000 Иванов ИИ")
    @patch("nextcloud_app.api.NextcloudApiClient.list_resources", return_value=[])
    def test_create_contract_project_preserves_seal_and_director_facsimile_placeholders(
        self,
        mocked_list_resources,
        mocked_ensure_folder,
        mocked_upload_file,
        mocked_public_share,
        mocked_ensure_user_share,
        mocked_resolve_variables,
        mocked_ensure_nextcloud_account,
    ):
        group_member = GroupMember.objects.create(
            short_name="IMCM",
            full_name="IMCM LLC",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
        )
        group_member.seal_file.save("seal.png", ContentFile(TEST_CONTRACT_IMAGE_PNG_BYTES), save=True)
        self.project.group_member = group_member
        self.project.save(update_fields=["group_member"])

        director_user = get_user_model().objects.create_user(
            username="director@example.com",
            email="director@example.com",
            password="secret",
            first_name="Дина",
            last_name="Директорова",
            is_staff=True,
        )
        director_department = OrgUnit.objects.create(
            company=group_member,
            department_name="Руководство",
            level=1,
        )
        director_employee = Employee.objects.create(
            user=director_user,
            patronymic="Дмитриевна",
            role=DIRECTOR_GROUP,
            department=director_department,
        )
        director_person = PersonRecord.objects.create(
            last_name="Директорова",
            first_name="Дина",
            middle_name="Дмитриевна",
            position=1,
        )
        country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            alpha2="RU",
            alpha3="RUS",
        )
        citizenship = CitizenshipRecord.objects.create(
            person=director_person,
            country=country,
            position=1,
        )
        director_profile = ExpertProfile.objects.create(employee=director_employee, position=1)
        director_details = ExpertContractDetails.objects.create(
            expert_profile=director_profile,
            citizenship_record=citizenship,
        )
        director_details.facsimile_file.save(
            "facsimile.png",
            ContentFile(TEST_CONTRACT_IMAGE_PNG_BYTES),
            save=True,
        )

        template_doc = Document()
        template_doc.add_paragraph("Печать [[seal]]")
        template_doc.add_paragraph("Подпись [[facsimile_imcm]]")
        template_buffer = BytesIO()
        template_doc.save(template_buffer)
        self.template.file.save("contract-images.docx", ContentFile(template_buffer.getvalue()), save=True)

        mocked_ensure_nextcloud_account.side_effect = lambda user, client=None: (
            self.executor_link if user.pk == self.recipient_user.pk else self.lawyer_link
        )

        response = self.client.post(
            reverse("create_contract_project"),
            {"performer_ids[]": [self.performer.pk]},
        )

        self.assertEqual(response.status_code, 200)
        chunks = [json.loads(chunk.decode("utf-8").strip()) for chunk in response.streaming_content]
        self.assertEqual(chunks[-1]["ok"], True, chunks)
        mocked_upload_file.assert_called_once()
        generated_doc = Document(BytesIO(mocked_upload_file.call_args.args[2]))
        self.assertEqual(generated_doc.paragraphs[0].text, "Печать [[seal]]")
        self.assertEqual(generated_doc.paragraphs[1].text, "Подпись [[facsimile_imcm]]")
        combined_xml = "\n".join(paragraph._p.xml for paragraph in generated_doc.paragraphs)
        self.assertNotIn("<wp:anchor", combined_xml)
        self.assertIn("[[seal]]", combined_xml)
        self.assertIn("[[facsimile_imcm]]", combined_xml)

    def test_contract_docx_source_inserts_images_and_clears_highlighting_for_pdf(self):
        from projects_app.views import _build_contract_docx_source_token

        group_member = GroupMember.objects.create(
            short_name="IMCM",
            full_name="IMCM LLC",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
        )
        group_member.seal_file.save("seal.png", ContentFile(TEST_CONTRACT_IMAGE_PNG_BYTES), save=True)
        self.project.group_member = group_member
        self.project.save(update_fields=["group_member"])

        director_user = get_user_model().objects.create_user(
            username="pdf-director@example.com",
            email="pdf-director@example.com",
            password="secret",
            first_name="Дина",
            last_name="Директорова",
            is_staff=True,
        )
        director_department = OrgUnit.objects.create(
            company=group_member,
            department_name="Руководство",
            level=1,
        )
        director_employee = Employee.objects.create(
            user=director_user,
            patronymic="Дмитриевна",
            role=DIRECTOR_GROUP,
            department=director_department,
        )
        director_person = PersonRecord.objects.create(
            last_name="Директорова",
            first_name="Дина",
            middle_name="Дмитриевна",
            position=1,
        )
        country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            alpha2="RU",
            alpha3="RUS",
        )
        citizenship = CitizenshipRecord.objects.create(
            person=director_person,
            country=country,
            position=1,
        )
        director_profile = ExpertProfile.objects.create(employee=director_employee, position=1)
        director_details = ExpertContractDetails.objects.create(
            expert_profile=director_profile,
            citizenship_record=citizenship,
        )
        director_details.facsimile_file.save(
            "facsimile.png",
            ContentFile(TEST_CONTRACT_IMAGE_PNG_BYTES),
            save=True,
        )

        source_doc = Document()
        seal_run = source_doc.add_paragraph().add_run("Печать [[seal]]")
        seal_run.font.highlight_color = WD_COLOR_INDEX.YELLOW
        facsimile_run = source_doc.add_paragraph().add_run("Подпись [[facsimile_imcm]]")
        facsimile_run.font.highlight_color = WD_COLOR_INDEX.YELLOW
        performer_facsimile_run = source_doc.add_paragraph().add_run("Исполнитель [[facsimile_prfrm]]")
        performer_facsimile_run.font.highlight_color = WD_COLOR_INDEX.YELLOW
        source_buffer = BytesIO()
        source_doc.save(source_buffer)

        self.performer.contract_file = "Договор 5002_Иванов ИИ.docx"
        self.performer.contract_project_disk_folder = (
            "/Corporate Root/02 Договоры/2026/5002 DD Контрактный проект/"
            "02 Исполнители/000 Иванов ИИ"
        )
        self.performer.save(update_fields=["contract_file", "contract_project_disk_folder"])
        token = _build_contract_docx_source_token(self.performer)
        self.client.logout()

        with patch(
            "projects_app.views.cloud_download_file",
            return_value=(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                source_buffer.getvalue(),
            ),
        ):
            response = self.client.get(
                reverse("contract_onlyoffice_docx_source", args=[self.performer.pk]),
                {"token": token},
            )

        self.assertEqual(response.status_code, 200)
        signed_doc = Document(BytesIO(response.content))
        self.assertEqual(signed_doc.paragraphs[0].text, "Печать ")
        self.assertEqual(signed_doc.paragraphs[1].text, "Подпись ")
        self.assertEqual(signed_doc.paragraphs[2].text, "Исполнитель ")
        combined_xml = "\n".join(paragraph._p.xml for paragraph in signed_doc.paragraphs)
        self.assertEqual(combined_xml.count("<wp:anchor"), 2)
        self.assertEqual(combined_xml.count('behindDoc="1"'), 2)
        self.assertIn('relativeHeight="0"', signed_doc.paragraphs[0]._p.xml)
        self.assertIn('wp:positionH relativeFrom="column"', signed_doc.paragraphs[0]._p.xml)
        self.assertIn("<wp:align>center</wp:align>", signed_doc.paragraphs[0]._p.xml)
        self.assertIn('relativeHeight="1"', signed_doc.paragraphs[1]._p.xml)
        self.assertNotIn("[[seal]]", combined_xml)
        self.assertNotIn("[[facsimile_imcm]]", combined_xml)
        self.assertNotIn("[[facsimile_prfrm]]", combined_xml)
        self.assertNotIn("w:highlight", combined_xml)

    def test_contract_docx_source_inserts_performer_facsimile_for_signed_pdf(self):
        from projects_app.views import _build_contract_docx_source_token

        person = PersonRecord.objects.create(
            last_name="Иванов",
            first_name="Иван",
            middle_name="Иванович",
            position=1,
        )
        country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            alpha2="RU",
            alpha3="RUS",
        )
        citizenship = CitizenshipRecord.objects.create(
            person=person,
            country=country,
            position=1,
        )
        expert_profile = ExpertProfile.objects.create(employee=self.employee, position=1)
        contract_details = ExpertContractDetails.objects.create(
            expert_profile=expert_profile,
            citizenship_record=citizenship,
        )
        contract_details.facsimile_file.save(
            "performer-facsimile.png",
            ContentFile(TEST_CONTRACT_IMAGE_PNG_BYTES),
            save=True,
        )

        source_doc = Document()
        source_doc.add_paragraph("Исполнитель [[facsimile_prfrm]]")
        source_buffer = BytesIO()
        source_doc.save(source_buffer)

        self.performer.contract_file = "Договор 5002_Иванов ИИ.docx"
        self.performer.contract_project_disk_folder = (
            "/Corporate Root/02 Договоры/2026/5002 DD Контрактный проект/"
            "02 Исполнители/000 Иванов ИИ"
        )
        self.performer.save(update_fields=["contract_file", "contract_project_disk_folder"])
        token = _build_contract_docx_source_token(self.performer, include_performer_facsimile=True)
        self.client.logout()

        with patch(
            "projects_app.views.cloud_download_file",
            return_value=(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                source_buffer.getvalue(),
            ),
        ):
            response = self.client.get(
                reverse("contract_onlyoffice_docx_source", args=[self.performer.pk]),
                {"token": token},
            )

        self.assertEqual(response.status_code, 200)
        signed_doc = Document(BytesIO(response.content))
        self.assertEqual(signed_doc.paragraphs[0].text, "Исполнитель ")
        combined_xml = "\n".join(paragraph._p.xml for paragraph in signed_doc.paragraphs)
        self.assertEqual(combined_xml.count("<wp:anchor"), 1)
        self.assertIn('behindDoc="1"', signed_doc.paragraphs[0]._p.xml)
        self.assertIn('relativeHeight="1"', signed_doc.paragraphs[0]._p.xml)
        self.assertIn('wp:positionH relativeFrom="column"', signed_doc.paragraphs[0]._p.xml)
        self.assertIn("<wp:align>center</wp:align>", signed_doc.paragraphs[0]._p.xml)
        self.assertNotIn("[[facsimile_prfrm]]", combined_xml)

    @patch("nextcloud_app.provisioning.ensure_nextcloud_account")
    @patch("contracts_app.variable_resolver.resolve_variables", return_value=({}, {}))
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_user_share")
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_public_link_share", return_value="https://cloud.example.com/s/profile-country")
    @patch("nextcloud_app.api.NextcloudApiClient.upload_file", return_value=True)
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_folder", return_value="/Corporate Root/02 Договоры/2026/5002 DD Контрактный проект/02 Исполнители/000 Иванов ИИ")
    @patch("nextcloud_app.api.NextcloudApiClient.list_resources", return_value=[])
    def test_create_contract_project_falls_back_to_profile_country_without_contract_details(
        self,
        mocked_list_resources,
        mocked_ensure_folder,
        mocked_upload_file,
        mocked_public_share,
        mocked_ensure_user_share,
        mocked_resolve_variables,
        mocked_ensure_nextcloud_account,
    ):
        ru = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            full_name="Россия",
            alpha2="RU",
            alpha3="RUS",
        )
        profile = ExpertProfile.objects.create(employee=self.employee, position=1)
        ExpertProfile.objects.filter(pk=profile.pk).update(country=ru)
        self.template.country_name = "Россия"
        self.template.country_code = "643"
        self.template.save(update_fields=["country_name", "country_code"])
        mocked_ensure_nextcloud_account.side_effect = lambda user, client=None: (
            self.executor_link if user.pk == self.recipient_user.pk else self.lawyer_link
        )

        response = self.client.post(
            reverse("create_contract_project"),
            {"performer_ids[]": [self.performer.pk]},
        )

        self.assertEqual(response.status_code, 200)
        chunks = [json.loads(chunk.decode("utf-8").strip()) for chunk in response.streaming_content]
        self.assertEqual(chunks[-1]["ok"], True, chunks)
        self.assertTrue(mocked_upload_file.called, chunks)
        mocked_upload_file.assert_called_once()
        self.assertEqual(mocked_upload_file.call_args.args[2], b"fake-docx-content")

    @patch("nextcloud_app.provisioning.ensure_nextcloud_account")
    @patch("contracts_app.variable_resolver.resolve_variables", return_value=({}, {}))
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_user_share")
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_public_link_share", return_value="https://cloud.example.com/s/smz-doc")
    @patch("nextcloud_app.api.NextcloudApiClient.upload_file", return_value=True)
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_folder", return_value="/Corporate Root/02 Договоры/2026/5002 DD Контрактный проект/02 Исполнители/000 Иванов ИИ")
    @patch("nextcloud_app.api.NextcloudApiClient.list_resources", return_value=[])
    def test_create_contract_project_matches_smz_template_by_contract_details_country(
        self,
        mocked_list_resources,
        mocked_ensure_folder,
        mocked_upload_file,
        mocked_public_share,
        mocked_ensure_user_share,
        mocked_resolve_variables,
        mocked_ensure_nextcloud_account,
    ):
        kz_member = GroupMember.objects.create(
            short_name="KZ",
            country_name="Казахстан",
            country_code="398",
            country_alpha2="KZ",
        )
        self.project.group_member = kz_member
        self.project.save()
        person = PersonRecord.objects.create(
            last_name="Смирнова",
            first_name="Элина",
            middle_name="Юрьевна",
            position=1,
        )
        self.employee.person_record = person
        self.employee.save(update_fields=["person_record"])
        ru = OKSMCountry.objects.create(number=643, code="643", short_name="Россия", alpha2="RU", alpha3="RUS")
        kz = OKSMCountry.objects.create(number=398, code="398", short_name="Казахстан", alpha2="KZ", alpha3="KAZ")
        kz_citizenship = CitizenshipRecord.objects.create(person=person, country=kz, position=1)
        ru_citizenship = CitizenshipRecord.objects.create(person=person, country=ru, position=2)
        profile = ExpertProfile.objects.create(employee=self.employee, position=1)
        ExpertContractDetails.objects.create(
            expert_profile=profile,
            citizenship_record=kz_citizenship,
        )
        ru_details = ExpertContractDetails.objects.create(
            expert_profile=profile,
            citizenship_record=ru_citizenship,
            self_employed=date(2026, 1, 1),
        )
        smz_template = ContractTemplate.objects.create(
            group_member=kz_member,
            product=self.product,
            contract_type="smz",
            party="individual",
            country_name="Россия",
            country_code="643",
            sample_name="KZ Шаблон договора ФЗЛ СМЗ RUS_TDD-Общий_v1",
            version="1",
            file=SimpleUploadedFile(
                "smz-contract.docx",
                b"fake-smz-docx-content",
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            is_all_sections=True,
        )
        smz_template.group_members.set([kz_member])
        mocked_ensure_nextcloud_account.side_effect = lambda user, client=None: (
            self.executor_link if user.pk == self.recipient_user.pk else self.lawyer_link
        )

        response = self.client.post(
            reverse("create_contract_project"),
            {"performer_ids[]": [self.performer.pk]},
        )

        self.assertEqual(response.status_code, 200)
        chunks = [json.loads(chunk.decode("utf-8").strip()) for chunk in response.streaming_content]
        self.assertEqual(chunks[-1]["ok"], True, chunks)
        self.assertNotIn("warnings", chunks[-1])
        mocked_resolve_variables.assert_called()
        self.assertEqual(mocked_resolve_variables.call_args.kwargs["contract_details"], ru_details)
        self.assertEqual(mocked_upload_file.call_args.args[2], b"fake-smz-docx-content")
        self.performer.refresh_from_db()
        self.assertEqual(self.performer.contract_project_link, "https://cloud.example.com/s/smz-doc")

    @patch("nextcloud_app.provisioning.ensure_nextcloud_account")
    @patch("contracts_app.variable_resolver.resolve_variables", return_value=({}, {}))
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_user_share")
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_public_link_share", return_value="https://cloud.example.com/s/smz-all-doc")
    @patch("nextcloud_app.api.NextcloudApiClient.upload_file", return_value=True)
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_folder", return_value="/Corporate Root/02 Договоры/2026/5002 DD Контрактный проект/02 Исполнители/000 Иванов ИИ")
    @patch("nextcloud_app.api.NextcloudApiClient.list_resources", return_value=[])
    def test_create_contract_project_matches_smz_template_with_all_group_and_all_product(
        self,
        mocked_list_resources,
        mocked_ensure_folder,
        mocked_upload_file,
        mocked_public_share,
        mocked_ensure_user_share,
        mocked_resolve_variables,
        mocked_ensure_nextcloud_account,
    ):
        person = PersonRecord.objects.create(
            last_name="Смирнова",
            first_name="Элина",
            middle_name="Юрьевна",
            position=1,
        )
        self.employee.person_record = person
        self.employee.save(update_fields=["person_record"])
        ru = OKSMCountry.objects.create(number=643, code="643", short_name="Россия", alpha2="RU", alpha3="RUS")
        ru_citizenship = CitizenshipRecord.objects.create(person=person, country=ru, position=1)
        profile = ExpertProfile.objects.create(employee=self.employee, position=1)
        ru_details = ExpertContractDetails.objects.create(
            expert_profile=profile,
            citizenship_record=ru_citizenship,
            self_employed=date(2026, 1, 1),
        )
        ContractTemplate.objects.create(
            group_member=None,
            product=None,
            contract_type="smz",
            party="individual",
            country_name="Россия",
            country_code="643",
            sample_name="Все Шаблон договора ФЗЛ СМЗ RUS_Все-Общий_v1",
            version="1",
            file=SimpleUploadedFile(
                "smz-all-contract.docx",
                b"fake-smz-all-docx-content",
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            is_all_sections=True,
        )
        mocked_ensure_nextcloud_account.side_effect = lambda user, client=None: (
            self.executor_link if user.pk == self.recipient_user.pk else self.lawyer_link
        )

        response = self.client.post(
            reverse("create_contract_project"),
            {"performer_ids[]": [self.performer.pk]},
        )

        self.assertEqual(response.status_code, 200)
        chunks = [json.loads(chunk.decode("utf-8").strip()) for chunk in response.streaming_content]
        self.assertEqual(chunks[-1]["ok"], True)
        self.assertNotIn("warnings", chunks[-1])
        self.assertEqual(mocked_resolve_variables.call_args.kwargs["contract_details"], ru_details)
        self.assertEqual(mocked_upload_file.call_args.args[2], b"fake-smz-all-docx-content")

    @patch("nextcloud_app.provisioning.ensure_nextcloud_account")
    @patch("contracts_app.variable_resolver.resolve_variables", return_value=({}, {}))
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_user_share")
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_public_link_share", return_value="https://cloud.example.com/s/smz-edited-all-doc")
    @patch("nextcloud_app.api.NextcloudApiClient.upload_file", return_value=True)
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_folder", return_value="/Corporate Root/02 Договоры/2026/5002 DD Контрактный проект/02 Исполнители/000 Иванов ИИ")
    @patch("nextcloud_app.api.NextcloudApiClient.list_resources", return_value=[])
    def test_create_contract_project_matches_template_edited_to_all_group_and_all_product(
        self,
        mocked_list_resources,
        mocked_ensure_folder,
        mocked_upload_file,
        mocked_public_share,
        mocked_ensure_user_share,
        mocked_resolve_variables,
        mocked_ensure_nextcloud_account,
    ):
        from contracts_app.forms import ContractTemplateForm

        person = PersonRecord.objects.create(
            last_name="Смирнова",
            first_name="Элина",
            middle_name="Юрьевна",
            position=1,
        )
        self.employee.person_record = person
        self.employee.save(update_fields=["person_record"])
        ru = OKSMCountry.objects.create(number=643, code="643", short_name="Россия", alpha2="RU", alpha3="RUS")
        ru_citizenship = CitizenshipRecord.objects.create(person=person, country=ru, position=1)
        profile = ExpertProfile.objects.create(employee=self.employee, position=1)
        ru_details = ExpertContractDetails.objects.create(
            expert_profile=profile,
            citizenship_record=ru_citizenship,
            self_employed=date(2026, 1, 1),
        )
        smz_template = ContractTemplate.objects.create(
            group_member=self.project.group_member,
            product=self.product,
            contract_type="smz",
            party="individual",
            country_name="Россия",
            country_code="643",
            sample_name="RU Шаблон договора ФЗЛ СМЗ RUS_DD-Общий_v1",
            version="1",
            file=SimpleUploadedFile(
                "smz-specific-contract.docx",
                b"fake-edited-smz-docx-content",
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            is_all_sections=True,
        )
        smz_template.products.set([self.product])
        form = ContractTemplateForm(
            data={
                "group_member_ids": ["__all__"],
                "product_ids": ["__all__"],
                "contract_type": "smz",
                "party": "individual",
                "country": str(ru.pk),
                "sample_name": smz_template.sample_name,
                "version": smz_template.version,
                "section_ids": ["__all__"],
            },
            instance=smz_template,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        smz_template.refresh_from_db()
        self.assertIsNone(smz_template.group_member_id)
        self.assertFalse(smz_template.group_members.exists())
        self.assertIsNone(smz_template.product_id)
        self.assertFalse(smz_template.products.exists())
        mocked_ensure_nextcloud_account.side_effect = lambda user, client=None: (
            self.executor_link if user.pk == self.recipient_user.pk else self.lawyer_link
        )

        response = self.client.post(
            reverse("create_contract_project"),
            {"performer_ids[]": [self.performer.pk]},
        )

        self.assertEqual(response.status_code, 200)
        chunks = [json.loads(chunk.decode("utf-8").strip()) for chunk in response.streaming_content]
        self.assertEqual(chunks[-1]["ok"], True, chunks)
        self.assertNotIn("warnings", chunks[-1])
        self.assertEqual(mocked_resolve_variables.call_args.kwargs["contract_details"], ru_details)
        self.assertEqual(mocked_upload_file.call_args.args[2], b"fake-edited-smz-docx-content")

    @patch("nextcloud_app.provisioning.ensure_nextcloud_account")
    @patch("contracts_app.variable_resolver.resolve_variables", return_value=({}, {}))
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_user_share")
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_public_link_share", return_value="https://cloud.example.com/s/group-specific")
    @patch("nextcloud_app.api.NextcloudApiClient.upload_file", return_value=True)
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_folder", return_value="/Corporate Root/02 Договоры/2026/5002 DD Контрактный проект/02 Исполнители/000 Иванов ИИ")
    @patch("nextcloud_app.api.NextcloudApiClient.list_resources", return_value=[])
    def test_create_contract_project_prefers_specific_group_over_all_group_template(
        self,
        mocked_list_resources,
        mocked_ensure_folder,
        mocked_upload_file,
        mocked_public_share,
        mocked_ensure_user_share,
        mocked_resolve_variables,
        mocked_ensure_nextcloud_account,
    ):
        project_group = GroupMember.objects.create(
            short_name="RU",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
        )
        self.project.group_member = project_group
        self.project.save(update_fields=["group_member"])
        group_specific_template = ContractTemplate.objects.create(
            group_member=project_group,
            product=self.product,
            contract_type="gph",
            party="individual",
            country_name="",
            sample_name="RU Шаблон договора ФЗЛ ГПХ RUS_DD-Общий_v1",
            version="1",
            file=SimpleUploadedFile(
                "specific-contract.docx",
                b"group-specific-docx-content",
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            is_all_sections=True,
        )
        group_specific_template.group_members.set([project_group])
        ContractTemplate.objects.create(
            group_member=None,
            product=self.product,
            contract_type="gph",
            party="individual",
            country_name="",
            sample_name="Все Шаблон договора ФЗЛ ГПХ RUS_DD-Общий_v99",
            version="99",
            file=SimpleUploadedFile(
                "all-contract.docx",
                b"all-group-docx-content",
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            is_all_sections=True,
        )
        mocked_ensure_nextcloud_account.side_effect = lambda user, client=None: (
            self.executor_link if user.pk == self.recipient_user.pk else self.lawyer_link
        )

        response = self.client.post(
            reverse("create_contract_project"),
            {"performer_ids[]": [self.performer.pk]},
        )

        self.assertEqual(response.status_code, 200)
        chunks = [json.loads(chunk.decode("utf-8").strip()) for chunk in response.streaming_content]
        self.assertEqual(chunks[-1]["ok"], True)
        self.assertEqual(mocked_upload_file.call_args.args[2], b"group-specific-docx-content")

    @patch("nextcloud_app.provisioning.ensure_nextcloud_account")
    @patch("contracts_app.variable_resolver.resolve_variables", return_value=({}, {}))
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_user_share")
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_public_link_share", return_value="https://cloud.example.com/s/product-specific")
    @patch("nextcloud_app.api.NextcloudApiClient.upload_file", return_value=True)
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_folder", return_value="/Corporate Root/02 Договоры/2026/5002 DD Контрактный проект/02 Исполнители/000 Иванов ИИ")
    @patch("nextcloud_app.api.NextcloudApiClient.list_resources", return_value=[])
    def test_create_contract_project_prefers_specific_product_over_all_product_template(
        self,
        mocked_list_resources,
        mocked_ensure_folder,
        mocked_upload_file,
        mocked_public_share,
        mocked_ensure_user_share,
        mocked_resolve_variables,
        mocked_ensure_nextcloud_account,
    ):
        ContractTemplate.objects.create(
            group_member=None,
            product=None,
            contract_type="gph",
            party="individual",
            country_name="",
            sample_name="Все Шаблон договора ФЗЛ ГПХ RUS_Все-Общий_v99",
            version="99",
            file=SimpleUploadedFile(
                "all-product-contract.docx",
                b"all-product-docx-content",
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            is_all_sections=True,
        )
        self.template.products.set([self.product])
        mocked_ensure_nextcloud_account.side_effect = lambda user, client=None: (
            self.executor_link if user.pk == self.recipient_user.pk else self.lawyer_link
        )

        response = self.client.post(
            reverse("create_contract_project"),
            {"performer_ids[]": [self.performer.pk]},
        )

        self.assertEqual(response.status_code, 200)
        chunks = [json.loads(chunk.decode("utf-8").strip()) for chunk in response.streaming_content]
        self.assertEqual(chunks[-1]["ok"], True)
        self.assertEqual(mocked_upload_file.call_args.args[2], b"fake-docx-content")

    def test_contract_request_notification_uses_existing_nextcloud_link(self):
        self.performer.contract_project_link = "https://cloud.example.com/s/public-doc"
        self.performer.contract_pdf_link = "https://cloud.example.com/s/public-pdf"
        self.performer.save(update_fields=["contract_project_link", "contract_pdf_link"])
        request_sent_at = timezone.localtime().replace(second=0, microsecond=0)

        response = self.client.post(
            reverse("contract_request"),
            {
                "performer_ids[]": [self.performer.pk],
                "duration_hours": "24",
                "request_sent_at": request_sent_at.isoformat(),
                "delivery_channels[]": ["system"],
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["delivery_channels"], ["system"])
        self.assertFalse(payload["email_delivery"]["requested"])
        self.performer.refresh_from_db()
        self.assertEqual(self.performer.contract_sent_at, request_sent_at)
        notification = Notification.objects.get(notification_type=Notification.NotificationType.PROJECT_CONTRACT_CONCLUSION)
        self.assertEqual(notification.payload["document_docx_link"], "https://cloud.example.com/s/public-doc")
        self.assertEqual(notification.payload["document_pdf_link"], "https://cloud.example.com/s/public-pdf")
        self.assertEqual(notification.payload["document_link"], "https://cloud.example.com/s/public-doc")
        self.assertIn("https://cloud.example.com/s/public-doc", notification.content_text)
        self.assertIn("https://cloud.example.com/s/public-pdf", notification.content_text)

    def test_contract_request_can_send_only_system_email(self):
        self.performer.contract_project_link = "https://cloud.example.com/s/public-doc"
        self.performer.save(update_fields=["contract_project_link"])
        request_sent_at = timezone.localtime().replace(second=0, microsecond=0)

        with patch("notifications_app.services.send_notification_email") as mocked_send:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    reverse("contract_request"),
                    {
                        "performer_ids[]": [self.performer.pk],
                        "duration_hours": "24",
                        "request_sent_at": request_sent_at.isoformat(),
                        "delivery_channels[]": ["system_email"],
                    },
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["delivery_channels"], ["system_email"])
        self.assertTrue(payload["email_delivery"]["requested"])
        self.assertEqual(payload["email_delivery"]["attempted"], 1)
        self.assertFalse(
            Notification.objects.filter(
                notification_type=Notification.NotificationType.PROJECT_CONTRACT_CONCLUSION,
            ).exists()
        )
        mocked_send.assert_called_once()
        call_kwargs = mocked_send.call_args.kwargs
        self.assertEqual(call_kwargs["recipient"], self.recipient_user)
        self.assertIn("https://cloud.example.com/s/public-doc", call_kwargs["content"])
