import csv
import io
import os
import shutil
import tempfile
from datetime import date
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from classifiers_app.models import (
    OKSMCountry,
    BusinessEntityIdentifierRecord,
    BusinessEntityRecord,
    LegalEntityIdentifier,
    LegalEntityRecord,
)
from classifiers_app.name_history_csv import NAME_HISTORY_CSV_FIELDS
from classifiers_app.views import BUSINESS_REGISTRY_CSV_FIELDS
from group_app.registry_sync import GROUP_BUSINESS_ENTITY_SOURCE, backfill_group_member_registries
from policy_app.models import DEPARTMENT_HEAD_GROUP, ExpertiseDirection, Product, TypicalSection
from projects_app.models import Performer, ProjectRegistration
from users_app.models import Employee
from .expertise_management import operation_head, operation_unit
from .models import ExpertiseManagementMode, GroupMember, OrgUnit


class GroupMemberSealTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix="group-tests-")
        self.addCleanup(lambda: shutil.rmtree(self.media_root, ignore_errors=True))

        self.user = get_user_model().objects.create_user(
            username="group-admin",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)
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
        self.member = GroupMember.objects.create(
            short_name="IMC",
            full_name="IMC Montan",
            name_en="IMC Montan",
            country_name=self.country.short_name,
            country_code=self.country.code,
            country_alpha2=self.country.alpha2,
            position=1,
        )

    def _member_form_data(self):
        return {
            "short_name": self.member.short_name,
            "full_name": self.member.full_name,
            "name_en": self.member.name_en,
            "country": str(self.country.pk),
            "identifier": self.member.identifier,
            "registration_number": self.member.registration_number,
            "registration_date": "",
        }

    def test_member_edit_uploads_seal_and_renders_download_link(self):
        data = self._member_form_data()
        data["seal_file"] = SimpleUploadedFile(
            "seal.png",
            b"seal-data",
            content_type="image/png",
        )

        with self.settings(MEDIA_ROOT=self.media_root):
            response = self.client.post(
                reverse("gm_form_edit", args=[self.member.pk]),
                data,
            )

        self.assertEqual(response.status_code, 200)
        self.member.refresh_from_db()
        self.assertTrue(self.member.seal_file.name)
        self.assertContains(response, "Печать")
        self.assertContains(
            response,
            reverse("gm_seal_download", args=[self.member.pk]),
            html=False,
        )

    def test_member_create_uploads_seal_file(self):
        data = {
            "short_name": "IMC KZ",
            "full_name": "IMC Kazakhstan",
            "name_en": "IMC Kazakhstan",
            "country": str(self.country.pk),
            "identifier": "",
            "registration_number": "123",
            "registration_date": "",
            "seal_file": SimpleUploadedFile(
                "seal.png",
                b"seal-data",
                content_type="image/png",
            ),
        }

        with self.settings(MEDIA_ROOT=self.media_root):
            response = self.client.post(reverse("gm_form_create"), data)

        self.assertEqual(response.status_code, 200)
        member = GroupMember.objects.get(short_name="IMC KZ")
        self.assertTrue(member.seal_file.name)
        self.assertIn(str(member.pk), member.seal_file.name)

    def test_member_edit_can_clear_seal_file(self):
        with self.settings(MEDIA_ROOT=self.media_root):
            self.member.seal_file.save("seal.png", ContentFile(b"seal-data"), save=True)
            old_path = self.member.seal_file.path

            data = self._member_form_data()
            data["seal_file-clear"] = "on"
            response = self.client.post(
                reverse("gm_form_edit", args=[self.member.pk]),
                data,
            )

        self.assertEqual(response.status_code, 200)
        self.member.refresh_from_db()
        self.assertEqual(self.member.seal_file.name, "")
        self.assertFalse(os.path.exists(old_path))

    def test_member_seal_download_returns_attachment(self):
        with self.settings(MEDIA_ROOT=self.media_root):
            self.member.seal_file.save("seal.png", ContentFile(b"seal-data"), save=True)

            response = self.client.get(
                reverse("gm_seal_download", args=[self.member.pk])
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertIn("seal.png", response["Content-Disposition"])
        self.assertEqual(b"".join(response.streaming_content), b"seal-data")

    def test_member_seal_download_uses_storage_open_without_filesystem_path(self):
        self.member.seal_file = "group/seals/1/seal.png"
        self.member.save(update_fields=["seal_file"])
        file_obj = MagicMock()
        file_obj.read.side_effect = [b"seal-data", b""]
        file_obj.close = MagicMock()
        with patch.object(self.member.seal_file.storage, "open", return_value=file_obj) as mocked_open:
            response = self.client.get(reverse("gm_seal_download", args=[self.member.pk]))

        self.assertEqual(response.status_code, 200)
        mocked_open.assert_called_once_with(self.member.seal_file.name, "rb")
        self.assertIn("seal.png", response["Content-Disposition"])
        self.assertEqual(b"".join(response.streaming_content), b"seal-data")

    def test_management_company_checkbox_is_exclusive(self):
        other = GroupMember.objects.create(
            short_name="Other Co",
            full_name="Other Company",
            name_en="Other Company",
            country_name=self.country.short_name,
            country_code=self.country.code,
            country_alpha2=self.country.alpha2,
            position=2,
        )
        data = self._member_form_data()
        data["is_management_company"] = "on"
        response = self.client.post(reverse("gm_form_edit", args=[self.member.pk]), data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ">УК<", html=False)
        self.assertContains(response, "bi-check-square", html=False)
        form_response = self.client.get(reverse("gm_form_edit", args=[self.member.pk]))
        self.assertContains(form_response, "Управляющая компания")
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_management_company)

        other_data = {
            "short_name": other.short_name,
            "full_name": other.full_name,
            "name_en": other.name_en,
            "country": str(self.country.pk),
            "identifier": "",
            "registration_number": "",
            "registration_date": "",
            "is_management_company": "on",
        }
        self.client.post(reverse("gm_form_edit", args=[other.pk]), other_data)
        self.member.refresh_from_db()
        other.refresh_from_db()
        self.assertFalse(self.member.is_management_company)
        self.assertTrue(other.is_management_company)


class ExpertiseManagementModeTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(username="mode-admin", password="secret", is_staff=True)
        self.client.force_login(self.staff)
        self.uk = GroupMember.objects.create(
            short_name="ООО УК",
            country_name="Россия",
            position=1,
            is_management_company=True,
        )
        self.too = GroupMember.objects.create(
            short_name="ТОО",
            country_name="Казахстан",
            position=2,
        )
        self.direction = ExpertiseDirection.objects.create(
            name="Экология",
            short_name="ECO",
            position=1,
        )
        self.uk_unit = OrgUnit.objects.create(
            company=self.uk,
            department_name="Сектор экологии",
            level=2,
            expertise=self.direction,
            unit_type="expertise",
            position=1,
        )
        self.too_unit = OrgUnit.objects.create(
            company=self.too,
            department_name="Сектор экологии ТОО",
            level=2,
            expertise=self.direction,
            unit_type="expertise",
            position=2,
        )
        self.uk_head = self._employee("uk-head", "Иванов", "Иван", self.uk_unit)
        self.too_head = self._employee("too-head", "Сергеев", "Сергей", self.too_unit)
        self.product = Product.objects.create(
            short_name="DD",
            name_en="DD",
            name_ru="ДД",
            position=1,
        )
        self.section = TypicalSection.objects.create(
            product=self.product,
            code="ECO",
            short_name="ECO",
            name_en="Ecology",
            name_ru="Экология",
            expertise_dir=self.direction,
            position=1,
        )

    def _employee(self, username, last_name, first_name, department):
        user = get_user_model().objects.create_user(
            username=username,
            password="secret",
            is_staff=True,
            email=f"{username}@example.com",
            last_name=last_name,
            first_name=first_name,
        )
        return Employee.objects.create(
            user=user,
            role=DEPARTMENT_HEAD_GROUP,
            department=department,
            job_title="Руководитель направления",
            position=1,
        )

    def _project(self, number, company):
        return ProjectRegistration.objects.create(number=number, group_member=company)

    def _performer(self, project, employee=None, confirmed=False):
        return Performer.objects.create(
            registration=project,
            typical_section=self.section,
            employee=employee,
            participation_response=(
                Performer.ParticipationResponse.CONFIRMED if confirmed else ""
            ),
        )

    def test_new_direction_defaults_to_management_company_mode(self):
        mode = ExpertiseManagementMode.objects.get(expertise_direction=self.direction)
        self.assertEqual(mode.mode, ExpertiseManagementMode.MODE_MANAGEMENT_COMPANY)
        response = self.client.get(reverse("group_partial"))
        self.assertContains(response, "Режим управления")
        self.assertContains(response, "Управление через УК")
        html = response.content.decode()
        mode_block = html[html.index("Режим управления"):]
        add_button = mode_block[mode_block.index("<button"):mode_block.index("Добавить строку")]
        self.assertIn("disabled", add_button)
        self.assertIn("btn btn-primary btn-sm", add_button)
        self.assertContains(response, "ECO")

        edit = self.client.post(
            reverse("expertise_mode_form_edit", args=[mode.pk]),
            {"mode": ExpertiseManagementMode.MODE_SEPARATE},
        )
        self.assertEqual(edit.status_code, 200)
        self.assertContains(edit, "Раздельное управление")
        mode.refresh_from_db()
        self.assertEqual(mode.mode, ExpertiseManagementMode.MODE_SEPARATE)

    def test_uk_mode_uses_management_company_head_for_every_project(self):
        too_project = self._project(1, self.too)
        ooo_project = self._project(2, self.uk)
        self.assertEqual(operation_head(self.direction, too_project.group_member), self.uk_head)
        self.assertEqual(operation_head(self.direction, ooo_project.group_member), self.uk_head)

    def test_separate_mode_uses_the_project_company_head(self):
        ExpertiseManagementMode.objects.filter(expertise_direction=self.direction).update(
            mode=ExpertiseManagementMode.MODE_SEPARATE,
        )
        too_project = self._project(1, self.too)
        ooo_project = self._project(2, self.uk)
        self.assertEqual(operation_head(self.direction, too_project.group_member), self.too_head)
        self.assertEqual(operation_head(self.direction, ooo_project.group_member), self.uk_head)

    def test_two_units_in_one_company_leave_the_head_empty(self):
        OrgUnit.objects.create(
            company=self.uk,
            department_name="Второй сектор",
            level=2,
            expertise=self.direction,
            unit_type="expertise",
            position=3,
        )
        self.assertIsNone(operation_head(self.direction, self.too))
        self.assertIsNone(operation_unit(self.direction, self.uk))

    def test_contract_report_and_folder_use_the_same_head_as_request_approval(self):
        ExpertiseManagementMode.objects.filter(expertise_direction=self.direction).update(
            mode=ExpertiseManagementMode.MODE_SEPARATE,
        )
        project = self._project(1, self.too)
        expert = self._employee("expert", "Петров", "Петр", self.uk_unit)
        expert.role = "Эксперт"
        expert.save(update_fields=["role"])
        performer = self._performer(project, expert, confirmed=True)
        self._performer(project, self.too_head, confirmed=True)
        self._performer(project, self.uk_head, confirmed=True)

        from checklists_app.views import _get_dh_expertise_section_ids
        from contracts_app.views import _attach_contract_responsible_names
        from nextcloud_app.workspace import _direction_head_by_performer
        from projects_app.report_access import _is_direction_expert_assignment

        self.assertIn(self.section.pk, _get_dh_expertise_section_ids(self.too_head.user, project))
        self.assertNotIn(self.section.pk, _get_dh_expertise_section_ids(self.uk_head.user, project))
        self.assertTrue(_is_direction_expert_assignment(self.too_head, performer))
        self.assertFalse(_is_direction_expert_assignment(self.uk_head, performer))

        named = _attach_contract_responsible_names([performer])[0]
        self.assertEqual(named.responsible_name, Performer.employee_full_name(self.too_head))
        self.assertEqual(_direction_head_by_performer([performer])[performer.pk], self.too_head)


class GroupMemberRegistrySyncTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="registry-admin",
            password="secret",
            is_staff=True,
            first_name="Иван",
            last_name="Петров",
        )
        self.client.force_login(self.user)
        self.russia = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            full_name="Российская Федерация",
            alpha2="RU",
            alpha3="RUS",
            position=1,
        )
        self.kazakhstan = OKSMCountry.objects.create(
            number=398,
            code="398",
            short_name="Казахстан",
            full_name="Республика Казахстан",
            alpha2="KZ",
            alpha3="KAZ",
            position=2,
        )
        LegalEntityIdentifier.objects.create(
            identifier="ОГРН",
            full_name="Основной государственный регистрационный номер",
            code=self.russia.code,
            country=self.russia,
            position=1,
        )
        LegalEntityIdentifier.objects.create(
            identifier="БИН",
            full_name="Бизнес-идентификационный номер",
            code=self.kazakhstan.code,
            country=self.kazakhstan,
            position=2,
        )

    def _create_member(self, **overrides):
        data = {
            "short_name": 'ООО "Альфа"',
            "full_name": 'Общество с ограниченной ответственностью "Альфа"',
            "name_en": "Alpha LLC",
            "country": str(self.russia.pk),
            "identifier": "",
            "registration_number": "1027700132195",
            "registration_date": "2020-01-15",
        }
        data.update(overrides)
        response = self.client.post(reverse("gm_form_create"), data)
        self.assertEqual(response.status_code, 200)
        return GroupMember.objects.get(short_name=data["short_name"])

    def _chain(self, member):
        entity = member.business_entity
        identifier = entity.identifiers.get()
        name = identifier.legal_entity_records.get(attribute=LegalEntityRecord.ATTRIBUTE_NAME)
        address = identifier.legal_entity_records.get(attribute=LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS)
        return entity, identifier, name, address

    def test_create_makes_separate_chain_even_when_number_matches(self):
        first = self._create_member()
        second = self._create_member(
            short_name='ООО "Бета"',
            full_name='Общество с ограниченной ответственностью "Бета"',
            name_en="Beta LLC",
        )

        self.assertNotEqual(first.business_entity_id, second.business_entity_id)
        entity, identifier, name, address = self._chain(first)
        self.assertEqual(entity.name, 'ООО "Альфа"')
        self.assertEqual(entity.source, GROUP_BUSINESS_ENTITY_SOURCE)
        self.assertEqual(entity.record_author, "Иван Петров")
        self.assertEqual(identifier.identifier_type, "ОГРН")
        self.assertEqual(identifier.number, "1027700132195")
        self.assertEqual(identifier.registration_country, self.russia)
        self.assertEqual(identifier.registration_date, date(2020, 1, 15))
        self.assertEqual(identifier.valid_from, date(2020, 1, 15))
        self.assertEqual(name.short_name, 'ООО "Альфа"')
        self.assertEqual(name.full_name, 'Общество с ограниченной ответственностью "Альфа"')
        self.assertEqual(name.name_received_date, date(2020, 1, 15))
        self.assertEqual(address.registration_country, self.russia)
        self.assertEqual(address.street, "")
        self.assertEqual(address.valid_from, date(2020, 1, 15))
        self.assertEqual(BusinessEntityRecord.objects.count(), 2)

    def test_edit_overwrites_only_group_fields(self):
        member = self._create_member()
        entity, identifier, name, address = self._chain(member)
        entity.comment = "заметка"
        entity.save(update_fields=["comment"])
        identifier.registration_region = "Москва"
        identifier.save()
        name.registration_region = "Москва"
        name.save()
        address.street = "Ленина"
        address.registration_region = "Москва"
        address.save()

        response = self.client.post(
            reverse("gm_form_edit", args=[member.pk]),
            {
                "short_name": 'ООО "Гамма"',
                "full_name": 'Общество с ограниченной ответственностью "Гамма"',
                "name_en": "Gamma LLC",
                "country": str(self.kazakhstan.pk),
                "identifier": "ОГРН",
                "registration_number": "123456789012",
                "registration_date": "2024-03-01",
            },
        )
        self.assertEqual(response.status_code, 200)

        entity.refresh_from_db()
        identifier.refresh_from_db()
        name.refresh_from_db()
        address.refresh_from_db()
        self.assertEqual(entity.name, 'ООО "Гамма"')
        self.assertEqual(entity.comment, "заметка")
        self.assertEqual(entity.source, GROUP_BUSINESS_ENTITY_SOURCE)
        self.assertEqual(identifier.identifier_type, "БИН")
        self.assertEqual(identifier.number, "123456789012")
        self.assertEqual(identifier.registration_country, self.kazakhstan)
        self.assertEqual(identifier.registration_date, date(2024, 3, 1))
        self.assertEqual(identifier.registration_region, "Москва")
        self.assertEqual(identifier.valid_from, date(2020, 1, 15))
        self.assertEqual(name.short_name, 'ООО "Гамма"')
        self.assertEqual(name.full_name, 'Общество с ограниченной ответственностью "Гамма"')
        self.assertEqual(name.registration_region, "Москва")
        self.assertEqual(name.name_received_date, date(2020, 1, 15))
        self.assertEqual(name.registration_country, self.kazakhstan)
        self.assertEqual(address.street, "Ленина")
        self.assertEqual(address.registration_region, "Москва")
        self.assertEqual(address.registration_country, self.kazakhstan)
        self.assertEqual(address.valid_from, date(2020, 1, 15))

    def test_delete_member_deletes_registry_chain(self):
        member = self._create_member()
        entity_id = member.business_entity_id

        response = self.client.post(reverse("gm_delete", args=[member.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(GroupMember.objects.filter(pk=member.pk).exists())
        self.assertFalse(BusinessEntityRecord.objects.filter(pk=entity_id).exists())
        self.assertFalse(BusinessEntityIdentifierRecord.objects.filter(business_entity_id=entity_id).exists())
        self.assertFalse(LegalEntityRecord.objects.exists())

    def test_directory_keeps_group_fields_locked(self):
        member = self._create_member()
        entity, identifier, name, address = self._chain(member)

        name_response = self.client.get(reverse("ber_form_edit", args=[entity.pk]))
        self.assertContains(name_response, "readonly-field")
        edit_response = self.client.post(
            reverse("ber_form_edit", args=[entity.pk]),
            {"name": 'ООО "Чужое"', "comment": "новая заметка"},
        )
        self.assertEqual(edit_response.status_code, 200)
        entity.refresh_from_db()
        self.assertEqual(entity.name, 'ООО "Альфа"')
        self.assertEqual(entity.comment, "новая заметка")

        identifier_response = self.client.post(
            reverse("bei_form_edit", args=[identifier.pk]),
            {
                "business_entity": str(entity.pk),
                "registration_country": str(self.kazakhstan.pk),
                "registration_region": "",
                "identifier_type": "БИН",
                "number": "999",
                "registration_date": "01.02.2022",
                "valid_from": "2019-05-01",
                "valid_to": "",
            },
        )
        self.assertEqual(identifier_response.status_code, 200, identifier_response.content[:500])
        identifier.refresh_from_db()
        self.assertEqual(identifier.number, "1027700132195")
        self.assertEqual(identifier.identifier_type, "ОГРН")
        self.assertEqual(identifier.registration_country, self.russia)
        self.assertEqual(identifier.registration_date, date(2020, 1, 15))
        self.assertEqual(identifier.valid_from, date(2019, 5, 1))

        address.street = "Старая"
        address.save(update_fields=["street"])
        address_response = self.client.post(
            reverse("bea_form_edit", args=[address.pk]),
            {
                "identifier_record": str(identifier.pk),
                "registration_country": str(self.kazakhstan.pk),
                "registration_region": "",
                "postal_code": "101000",
                "municipality": "",
                "settlement": "",
                "locality": "",
                "district": "",
                "street": "Новая",
                "building": "",
                "premise": "",
                "premise_part": "",
                "valid_from": "2020-01-15",
                "valid_to": "",
            },
        )
        self.assertEqual(address_response.status_code, 200, address_response.content[:500])
        address.refresh_from_db()
        self.assertEqual(address.street, "Новая")
        self.assertEqual(address.postal_code, "101000")
        self.assertEqual(address.registration_country, self.russia)

        record_response = self.client.post(
            reverse("ler_form_edit", args=[name.pk]),
            {
                "identifier_record": str(identifier.pk),
                "short_name": 'ООО "Чужое"',
                "full_name": "Чужое полное",
                "registration_region": "",
                "name_received_date": "2020-01-15",
                "name_changed_date": "2021-01-01",
            },
        )
        self.assertEqual(record_response.status_code, 200, record_response.content[:500])
        name.refresh_from_db()
        self.assertEqual(name.short_name, 'ООО "Альфа"')
        self.assertEqual(name.full_name, 'Общество с ограниченной ответственностью "Альфа"')
        self.assertEqual(name.name_changed_date, date(2021, 1, 1))

        for url_name, pk in (
            ("ber_delete", entity.pk),
            ("bei_delete", identifier.pk),
            ("ler_delete", name.pk),
        ):
            response = self.client.post(reverse(url_name, args=[pk]))
            self.assertEqual(response.status_code, 409, url_name)
            self.assertIn("Состав группы", response.content.decode())
        self.assertTrue(BusinessEntityRecord.objects.filter(pk=entity.pk).exists())
        self.assertTrue(BusinessEntityIdentifierRecord.objects.filter(pk=identifier.pk).exists())
        self.assertTrue(LegalEntityRecord.objects.filter(pk=name.pk).exists())

    def test_backfill_creates_chain_for_existing_member(self):
        member = GroupMember.objects.create(
            short_name='ООО "Уже было"',
            full_name="Полное уже было",
            country_name=self.russia.short_name,
            country_code=self.russia.code,
            country_alpha2=self.russia.alpha2,
            identifier="ОГРН",
            registration_number="555",
            registration_date=date(2019, 6, 1),
            position=1,
        )

        backfill_group_member_registries()
        backfill_group_member_registries()

        member.refresh_from_db()
        entity, identifier, name, address = self._chain(member)
        self.assertEqual(entity.name, 'ООО "Уже было"')
        self.assertEqual(entity.source, GROUP_BUSINESS_ENTITY_SOURCE)
        self.assertEqual(entity.record_author, "")
        self.assertEqual(identifier.number, "555")
        self.assertEqual(identifier.valid_from, date(2019, 6, 1))
        self.assertEqual(name.full_name, "Полное уже было")
        self.assertEqual(name.name_received_date, date(2019, 6, 1))
        self.assertEqual(address.registration_country, self.russia)
        self.assertEqual(BusinessEntityRecord.objects.count(), 1)

    def _registry_csv(self, rows):
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=BUSINESS_REGISTRY_CSV_FIELDS, delimiter=";", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            payload = {field: "" for field in BUSINESS_REGISTRY_CSV_FIELDS}
            payload.update(row)
            writer.writerow(payload)
        return SimpleUploadedFile(
            "business-registry.csv",
            ("\ufeff" + buffer.getvalue()).encode("utf-8"),
            content_type="text/csv",
        )

    def test_business_registry_csv_keeps_group_chain(self):
        member = self._create_member()
        entity, identifier, name, address = self._chain(member)
        address.street = "Ленина"
        address.save(update_fields=["street"])
        BusinessEntityRecord.objects.create(name="Чужая", position=50)
        upload = self._registry_csv(
            [
                {
                    "section": "business_entity",
                    "business_entity_ref": f"{entity.pk:05d}-BSN",
                    "position": "1",
                    "business_entity_name": 'ООО "Подмена"',
                    "comment": "из csv",
                    "source": "csv",
                },
                {
                    "section": "identifier",
                    "business_entity_ref": f"{entity.pk:05d}-BSN",
                    "identifier_ref": f"{identifier.pk:05d}-IDN",
                    "position": "1",
                    "identifier_type": "ИНН",
                    "registration_country_code": "398",
                    "registration_number": "000",
                    "registration_region": "Казань",
                    "registration_date": "2024-01-01",
                    "valid_from": "2018-01-01",
                },
                {
                    "section": "name",
                    "business_entity_ref": f"{entity.pk:05d}-BSN",
                    "identifier_ref": f"{identifier.pk:05d}-IDN",
                    "position": "1",
                    "short_name": 'ООО "Подмена"',
                    "full_name": "Подмена",
                },
                {
                    "section": "address",
                    "business_entity_ref": f"{entity.pk:05d}-BSN",
                    "identifier_ref": f"{identifier.pk:05d}-IDN",
                    "position": "1",
                    "street": "CSV улица",
                    "registration_country_code": "398",
                },
                {
                    "section": "business_entity",
                    "business_entity_ref": "00999-BSN",
                    "position": "2",
                    "business_entity_name": "Новая компания",
                },
            ]
        )

        response = self.client.post(reverse("business_registry_csv_upload"), {"csv_file": upload})

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["ok"])
        entity.refresh_from_db()
        identifier.refresh_from_db()
        name.refresh_from_db()
        address.refresh_from_db()
        self.assertEqual(entity.name, 'ООО "Альфа"')
        self.assertEqual(entity.comment, "из csv")
        self.assertEqual(identifier.number, "1027700132195")
        self.assertEqual(identifier.identifier_type, "ОГРН")
        self.assertEqual(identifier.registration_country, self.russia)
        self.assertEqual(identifier.registration_region, "Казань")
        self.assertEqual(identifier.valid_from, date(2018, 1, 1))
        self.assertEqual(name.short_name, 'ООО "Альфа"')
        self.assertEqual(address.street, "Ленина")
        self.assertEqual(address.registration_country, self.russia)
        self.assertFalse(BusinessEntityRecord.objects.filter(name="Чужая").exists())
        self.assertTrue(BusinessEntityRecord.objects.filter(name="Новая компания").exists())

    def test_name_csv_does_not_change_group_name(self):
        member = self._create_member()
        _entity, _identifier, name, _address = self._chain(member)
        row = [
            name.short_name,
            "Новое полное",
            "Россия",
            "Татарстан",
            "ИНН",
            "000",
            "01.02.2022",
            "",
            "",
            "",
            "",
        ]
        header = "краткое;полное;страна;регион;идентификатор;номер;дата;запись;автор;получено;смена\n"
        upload = SimpleUploadedFile(
            "names.csv",
            ("\ufeff" + header + ";".join(row) + "\n").encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(reverse("ler_csv_upload"), {"csv_file": upload})

        self.assertEqual(response.status_code, 200, response.content)
        name.refresh_from_db()
        self.assertEqual(name.short_name, 'ООО "Альфа"')
        self.assertEqual(name.full_name, 'Общество с ограниченной ответственностью "Альфа"')
        self.assertEqual(name.registration_region, "Татарстан")
        self.assertEqual(name.identifier, "ОГРН")
        self.assertEqual(name.registration_number, "1027700132195")

    def test_name_history_csv_does_not_change_group_name(self):
        member = self._create_member()
        entity, identifier, name, _address = self._chain(member)
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=NAME_HISTORY_CSV_FIELDS, delimiter=";", lineterminator="\n")
        writer.writeheader()
        writer.writerow(
            {
                "ID-BSN": f"{entity.pk:05d}-BSN",
                "Наименование бизнес-сущности": 'ООО "Подмена"',
                "ID-IDN": f"{identifier.pk:05d}-IDN",
                "ID-ATR": f"{name.pk:05d}-ATR",
                "Идентификатор": "ИНН",
                "Регистрационный номер": "1027700132195",
                "Код страны": "398",
                "Страна": "Казахстан",
                "Регион": "Алматы",
                "Дата регистрации": "2020-01-15",
                "Идентификатор действителен от": "2020-01-15",
                "Идентификатор действителен до": "",
                "Наименование (краткое)": 'ООО "Подмена"',
                "Наименование (полное)": "Подмена",
                "Дата получения наименования": "2020-01-15",
                "Дата смены наименования": "",
            }
        )
        upload = SimpleUploadedFile(
            "name-history.csv",
            ("\ufeff" + buffer.getvalue()).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(reverse("ler_history_csv_upload"), {"csv_file": upload})

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["ok"], response.content)
        entity.refresh_from_db()
        identifier.refresh_from_db()
        name.refresh_from_db()
        self.assertEqual(entity.name, 'ООО "Альфа"')
        self.assertEqual(identifier.identifier_type, "ОГРН")
        self.assertEqual(identifier.number, "1027700132195")
        self.assertEqual(identifier.registration_country, self.russia)
        self.assertEqual(name.short_name, 'ООО "Альфа"')
        self.assertEqual(name.full_name, 'Общество с ограниченной ответственностью "Альфа"')
        self.assertEqual(name.registration_region, "Алматы")
