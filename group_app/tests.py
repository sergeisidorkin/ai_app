import os
import shutil
import tempfile
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from classifiers_app.models import OKSMCountry
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
