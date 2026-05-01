import os
import shutil
import tempfile
import uuid
from datetime import date
from urllib.parse import quote
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from classifiers_app.models import OKSMCountry
from contacts_app.models import CitizenshipRecord, PersonRecord
from core.models import CloudStorageSettings
from contracts_app.forms import ContractTemplateForm
from contracts_app.models import ContractTemplate, ContractVariable
from contracts_app.variable_resolver import resolve_variables
from experts_app.models import ExpertContractDetails, ExpertProfile
from group_app.models import GroupMember, OrgUnit
from nextcloud_app.api import NextcloudApiError, NextcloudShare
from nextcloud_app.models import NextcloudUserLink
from policy_app.models import DEPARTMENT_HEAD_GROUP, EXPERT_GROUP, LAWYER_GROUP, Product
from projects_app.models import Performer, ProjectRegistration
from users_app.forms import FREELANCER_LABEL
from users_app.models import Employee


@override_settings(
    NEXTCLOUD_PROVISIONING_BASE_URL="https://cloud.example.com",
    NEXTCLOUD_PROVISIONING_USERNAME="cloud-admin",
    NEXTCLOUD_PROVISIONING_TOKEN="token",
    NEXTCLOUD_OIDC_PROVIDER_ID=1,
)
class ContractsCloudLabelTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix="contracts-tests-")
        self.addCleanup(lambda: shutil.rmtree(self.media_root, ignore_errors=True))

        self.user = get_user_model().objects.create_user(
            username="contracts-admin",
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
        self.group_member = GroupMember.objects.create(
            short_name="Россия",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
            position=1,
        )
        self.project = ProjectRegistration.objects.create(
            number=7001,
            group_member=self.group_member,
            type=self.product,
            name="Договорный проект",
            year=2026,
        )
        self.employee_user = get_user_model().objects.create_user(
            username="expert@example.com",
            email="expert@example.com",
            password="secret",
            is_staff=True,
        )
        self.employee = Employee.objects.create(
            user=self.employee_user,
            patronymic="Иванович",
            employment=FREELANCER_LABEL,
        )
        expert_group, _ = Group.objects.get_or_create(name=EXPERT_GROUP)
        self.employee_user.groups.add(expert_group)
        self.employee_link = NextcloudUserLink.objects.create(
            user=self.employee_user,
            nextcloud_user_id="nc-expert",
            nextcloud_username="nc-expert",
            nextcloud_email=self.employee_user.email,
        )
        self.performer = Performer.objects.create(
            registration=self.project,
            employee=self.employee,
            executor="Иванов Иван Иванович",
            participation_response=Performer.ParticipationResponse.CONFIRMED,
            contract_batch_id=uuid.uuid4(),
            contract_file="Договор 7001_Иванов ИИ.docx",
            contract_project_link="https://cloud.example.com/s/contract-docx",
            contract_project_disk_folder="/Corporate Root/2026/Project/09 Договоры/000 Иванов ИИ",
        )

    def test_contracts_partial_renders_contract_projects_before_contract_conclusion(self):
        response = self.client.get(reverse("contracts_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Составление проекта договора")
        self.assertContains(response, "Отправка проекта договора")
        self.assertContains(response, 'id="contract-dispatch-table"', html=False)
        self.assertContains(response, "Облако")
        self.assertContains(response, "Наименование файла DOCX")
        self.assertContains(response, "Наименование файла PDF")
        self.assertContains(response, "Договор 7001_Иванов ИИ.docx")
        self.assertContains(response, "https://cloud.example.com/s/contract-docx")
        self.assertContains(response, "Создать проект договора")
        self.assertContains(response, "Подписать проект договора")
        self.assertContains(response, "Отправить проект договора")
        self.assertContains(
            response,
            "На Nextcloud будут созданы папки договоров в структуре",
            html=False,
        )
        self.assertContains(response, 'id="contract-project-filter-toggle"', html=False)
        self.assertContains(response, 'id="signing-project-filter-toggle"', html=False)
        self.assertContains(response, 'class="form-check-input js-signing-filter"', html=False)
        self.assertContains(response, 'data-request-url="%s"' % reverse("contract_request"), html=False)
        self.assertContains(
            response,
            'data-create-contract-url="%s"' % reverse("create_contract_project"),
            html=False,
        )
        self.assertContains(
            response,
            'data-sign-contract-url="%s"' % reverse("sign_contract_documents"),
            html=False,
        )
        self.assertContains(response, "Договорный проект")

        content = response.content.decode("utf-8")
        contract_drafting_table = content[
            content.index('id="contract-drafting-table"'):
            content.index('id="contract-dispatch-table"')
        ]
        self.assertNotIn("<th>Грейд</th>", contract_drafting_table)
        self.assertNotIn("col-grade", contract_drafting_table)
        self.assertLess(
            content.index('id="contracts-project-filter-toggle"'),
            content.index('id="contract-conclusion-section"'),
        )
        contracts_table = content[
            content.index('class="table table-sm align-middle contracts-table mb-0"'):
            content.index('id="contracts-edit-btn"')
        ]
        self.assertNotIn('<th class="text-nowrap">Ссылка</th>', contracts_table)
        self.assertLess(
            contracts_table.index('<th class="text-nowrap">Номер договора</th>'),
            contracts_table.index('>Цена</th>'),
        )
        self.assertLess(
            contracts_table.index('>Цена</th>'),
            contracts_table.index('<th class="text-nowrap">Дата договора</th>'),
        )
        self.assertLess(
            content.index("Составление проекта договора"),
            content.index("Отправка проекта договора"),
        )
        self.assertLess(
            content.index("Отправка проекта договора"),
            content.index("Подписание договора"),
        )

    def test_contract_conclusion_column_registry_excludes_grade(self):
        from core.column_registry import get_column_choices

        choices = get_column_choices("projects", "contract_conclusion")

        self.assertNotIn(("grade", "Грейд"), choices)

    def test_contracts_partial_renders_contract_pdf_file_like_proposal_pdf(self):
        self.performer.contract_pdf_file = "Договор 7001_Иванов ИИ.pdf"
        self.performer.contract_pdf_link = "https://cloud.example.com/s/contract-pdf"
        self.performer.save(update_fields=["contract_pdf_file", "contract_pdf_link"])

        response = self.client.get(reverse("contracts_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<th class="text-nowrap">Наименование файла PDF</th>', html=False)
        self.assertContains(response, "https://cloud.example.com/s/contract-pdf")
        self.assertContains(response, "Договор 7001_Иванов ИИ.pdf")
        self.assertContains(response, "bi-file-pdf-fill")
        content = response.content.decode("utf-8")
        signing_section = content[content.index("Подписание договора"):]
        self.assertIn("https://cloud.example.com/s/contract-pdf", signing_section)
        self.assertIn("Договор 7001_Иванов ИИ.pdf", signing_section)

    @override_settings(ONLYOFFICE_DOCUMENT_SERVER_URL="https://docs.example.com")
    def test_sign_contract_documents_generates_pdf_and_public_link(self):
        with (
            patch("projects_app.views.convert_docx_source_to_pdf", return_value=b"%PDF-1.4") as mocked_convert,
            patch("projects_app.views.cloud_upload_file", return_value=True) as mocked_upload,
            patch("projects_app.views.cloud_publish_resource", return_value="https://cloud.example.com/s/contract-pdf") as mocked_publish,
            patch("projects_app.views._resolve_contract_project_nextcloud_file_id", return_value="pdf-file-id"),
        ):
            response = self.client.post(
                reverse("sign_contract_documents"),
                {"performer_ids[]": [self.performer.pk]},
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["generated"], 1)
        self.assertEqual(data["updates"][0]["contract_pdf_file"], "Договор 7001_Иванов ИИ.pdf")

        source_url = mocked_convert.call_args.kwargs["source_url"]
        self.assertIn(
            reverse("contract_onlyoffice_docx_source", args=[self.performer.pk]),
            source_url,
        )
        expected_pdf_path = (
            f"{self.performer.contract_project_disk_folder}/"
            "Договор 7001_Иванов ИИ.pdf"
        )
        mocked_upload.assert_called_once_with(self.user, expected_pdf_path, b"%PDF-1.4")
        mocked_publish.assert_called_once_with(self.user, expected_pdf_path)

        self.performer.refresh_from_db()
        self.assertEqual(self.performer.contract_pdf_file, "Договор 7001_Иванов ИИ.pdf")
        self.assertEqual(self.performer.contract_pdf_link, "https://cloud.example.com/s/contract-pdf")
        self.assertEqual(self.performer.contract_pdf_file_id, "pdf-file-id")

    def test_contract_edit_updates_contract_date_for_batch_rows(self):
        self.project.deadline = date(2026, 5, 27)
        self.project.save(update_fields=["deadline"])
        self.performer.contract_date = date(2026, 5, 7)
        self.performer.save(update_fields=["contract_date"])
        sibling = Performer.objects.create(
            registration=self.project,
            employee=self.employee,
            executor="Иванов Иван Иванович",
            contract_batch_id=self.performer.contract_batch_id,
        )

        form_response = self.client.get(reverse("contracts_edit", args=[self.performer.pk]))
        form_content = form_response.content.decode("utf-8")

        self.assertEqual(form_response.status_code, 200)
        self.assertLess(
            form_content.index("Цена договора"),
            form_content.index("Дата договора"),
        )
        self.assertContains(form_response, 'name="prepayment"', html=False)
        self.assertContains(form_response, 'name="final_payment"', html=False)
        self.assertContains(form_response, 'id="contracts-term-days-field"', html=False)
        self.assertContains(form_response, 'data-deadline="2026-05-27"', html=False)
        self.assertContains(form_response, 'value="20 дн."', html=False)
        self.assertContains(form_response, 'data-contract-form-cancel-btn="1"', html=False)
        self.assertContains(form_response, 'data-contract-form-save-btn="1"', html=False)
        self.assertContains(form_response, "Сохранение...", html=False)
        self.assertContains(form_response, "spinner-border spinner-border-sm me-2", html=False)

        response = self.client.post(
            reverse("contracts_edit", args=[self.performer.pk]),
            {
                "contract_number": "CUSTOM-42",
                "contract_date": "2026-05-07",
                "prepayment": "30",
                "contract_file": "custom.docx",
            },
        )

        self.assertEqual(response.status_code, 200)
        sibling.refresh_from_db()
        self.assertEqual(sibling.contract_number, "CUSTOM-42")
        self.assertEqual(sibling.contract_date, date(2026, 5, 7))
        self.assertEqual(sibling.prepayment, 30)
        self.assertEqual(sibling.final_payment, 70)
        self.assertEqual(sibling.contract_file, "custom.docx")

    def test_contracts_partial_uses_direction_head_as_responsible(self):
        direction = OrgUnit.objects.create(
            company=self.group_member,
            level=2,
            department_name="Геология",
            unit_type="expertise",
        )
        head_user = get_user_model().objects.create_user(
            username="direction-head@example.com",
            password="secret",
            first_name="Петр",
            last_name="Петров",
            is_staff=True,
        )
        Employee.objects.create(
            user=head_user,
            patronymic="Петрович",
            department=direction,
            role=DEPARTMENT_HEAD_GROUP,
        )
        ExpertProfile.objects.create(
            employee=self.employee,
            expertise_direction=direction,
        )

        response = self.client.get(reverse("contracts_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ответственный")
        self.assertContains(response, "Петров П.П.")

        form_response = self.client.get(reverse("contracts_edit", args=[self.performer.pk]))

        self.assertEqual(form_response.status_code, 200)
        self.assertContains(form_response, "Ответственный")
        self.assertContains(form_response, 'value="Петров Петр Петрович"', html=False)

    def test_contracts_partial_uses_project_manager_as_responsible_without_direction(self):
        self.project.project_manager = "Сидоров Сидор Сидорович"
        self.project.save(update_fields=["project_manager"])

        response = self.client.get(reverse("contracts_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ответственный")
        self.assertContains(response, "Сидоров С.С.")

        form_response = self.client.get(reverse("contracts_edit", args=[self.performer.pk]))

        self.assertEqual(form_response.status_code, 200)
        self.assertContains(form_response, 'value="Сидоров Сидор Сидорович"', html=False)

    def test_contracts_partial_uses_active_citizenship_country_as_default_group(self):
        kazakhstan = OKSMCountry.objects.create(
            number=398,
            code="398",
            short_name="Казахстан",
            alpha2="KZ",
            alpha3="KAZ",
        )
        GroupMember.objects.create(
            short_name="Казахстан",
            country_name="Казахстан",
            country_code="398",
            country_alpha2="KZ",
            position=2,
        )
        person = PersonRecord.objects.create(
            last_name="Иванов",
            first_name="Иван",
            middle_name="Иванович",
        )
        self.employee.person_record = person
        self.employee.save(update_fields=["person_record"])
        CitizenshipRecord.objects.create(
            person=person,
            country=kazakhstan,
            valid_to=None,
        )

        response = self.client.get(reverse("contracts_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Группа")
        content = response.content.decode("utf-8")
        contracts_table = content[
            content.index('class="table table-sm align-middle contracts-table mb-0"'):
            content.index('id="contracts-edit-btn"')
        ]
        self.assertLess(
            contracts_table.index(
                f'<span class="clf-id-droid-mono">{self.project.short_uid}</span>'
            ),
            contracts_table.index('<td class="text-nowrap">KZ</td>'),
        )

        form_response = self.client.get(reverse("contracts_edit", args=[self.performer.pk]))

        self.assertEqual(form_response.status_code, 200)
        self.assertContains(form_response, "contracts-group-select")
        self.assertContains(form_response, ">KZ Казахстан</option>", html=False)
        self.assertContains(form_response, "contracts-group-display")

    def test_contract_edit_saves_group_for_batch_rows(self):
        sibling = Performer.objects.create(
            registration=self.project,
            employee=self.employee,
            executor="Иванов Иван Иванович",
            contract_batch_id=self.performer.contract_batch_id,
        )

        response = self.client.post(
            reverse("contracts_edit", args=[self.performer.pk]),
            {
                "contract_group_member": str(self.group_member.pk),
                "contract_number": "CUSTOM-42",
                "contract_date": "2026-05-07",
                "contract_file": "custom.docx",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.performer.refresh_from_db()
        sibling.refresh_from_db()
        self.assertEqual(self.performer.contract_group_member_id, self.group_member.pk)
        self.assertEqual(sibling.contract_group_member_id, self.group_member.pk)

    def test_contracts_partial_uses_current_primary_cloud_label_in_disk_tooltip(self):
        response = self.client.get(reverse("contracts_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'title="Открыть папку на Nextcloud"', html=False)

    def test_contracts_partial_uses_public_folder_link_for_cloud_icon(self):
        self.performer.contract_project_folder_link = "https://cloud.example.com/s/contract-folder"
        self.performer.save(update_fields=["contract_project_folder_link"])

        response = self.client.get(reverse("contracts_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="https://cloud.example.com/s/contract-folder"', html=False)
        content = response.content.decode("utf-8")
        section = content[
            content.index('id="contract-conclusion-section"'):
            content.index("Подписание договора")
        ]
        self.assertIn('href="https://cloud.example.com/s/contract-folder"', section)

    @patch("nextcloud_app.api.NextcloudApiClient.list_resources")
    @patch("nextcloud_app.api.NextcloudApiClient.list_user_shares")
    def test_contracts_partial_uses_editor_docx_link_for_lawyer(
        self,
        mocked_list_user_shares,
        mocked_list_resources,
    ):
        lawyer_user = get_user_model().objects.create_user(
            username="lawyer-docx@example.com",
            email="lawyer-docx@example.com",
            password="secret",
            is_staff=True,
        )
        lawyer_group, _ = Group.objects.get_or_create(name=LAWYER_GROUP)
        lawyer_user.groups.add(lawyer_group)
        NextcloudUserLink.objects.create(
            user=lawyer_user,
            nextcloud_user_id="nc-lawyer",
            nextcloud_username="nc-lawyer",
            nextcloud_email=lawyer_user.email,
        )
        mocked_list_user_shares.return_value = {
            self.performer.contract_project_disk_folder: NextcloudShare(
                share_id="56",
                path=self.performer.contract_project_disk_folder,
                share_with="nc-lawyer",
                permissions=15,
                target_path="/Shared/000 Иванов ИИ",
            )
        }
        mocked_list_resources.return_value = [
            {
                "name": self.performer.contract_file,
                "path": f"{self.performer.contract_project_disk_folder}/{self.performer.contract_file}",
                "type": "file",
                "file_id": "4474",
            }
        ]
        self.client.force_login(lawyer_user)

        response = self.client.get(reverse("contracts_partial"))

        expected_url = (
            "https://cloud.example.com/apps/files/files/4474?dir="
            + quote("/Shared/000 Иванов ИИ", safe="/")
            + "&amp;openfile=true"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, expected_url, html=False)
        content = response.content.decode("utf-8")
        section = content[
            content.index('id="contract-conclusion-section"'):
            content.index("Подписание договора")
        ]
        self.assertIn(expected_url, section)
        self.assertNotIn('href="https://cloud.example.com/s/contract-docx"', section)

    @patch("nextcloud_app.api.NextcloudApiClient.list_resources")
    @patch("nextcloud_app.api.NextcloudApiClient.list_user_shares")
    def test_contracts_partial_resolves_lawyer_docx_link_from_parent_share(
        self,
        mocked_list_user_shares,
        mocked_list_resources,
    ):
        lawyer_user = get_user_model().objects.create_user(
            username="lawyer-parent-share@example.com",
            email="lawyer-parent-share@example.com",
            password="secret",
            is_staff=True,
        )
        lawyer_group, _ = Group.objects.get_or_create(name=LAWYER_GROUP)
        lawyer_user.groups.add(lawyer_group)
        NextcloudUserLink.objects.create(
            user=lawyer_user,
            nextcloud_user_id="nc-lawyer-parent",
            nextcloud_username="nc-lawyer-parent",
            nextcloud_email=lawyer_user.email,
        )
        parent_path = "/Corporate Root/2026/Project"
        mocked_list_user_shares.return_value = {
            parent_path: NextcloudShare(
                share_id="57",
                path=parent_path,
                share_with="nc-lawyer-parent",
                permissions=15,
                target_path="/Shared/Project",
            )
        }
        mocked_list_resources.return_value = [
            {
                "name": self.performer.contract_file,
                "path": f"{self.performer.contract_project_disk_folder}/{self.performer.contract_file}",
                "type": "file",
                "file_id": "4475",
            }
        ]
        self.client.force_login(lawyer_user)

        response = self.client.get(reverse("contracts_partial"))

        expected_target_dir = "/Shared/Project/09 Договоры/000 Иванов ИИ"
        expected_url = (
            "https://cloud.example.com/apps/files/files/4475?dir="
            + quote(expected_target_dir, safe="/")
            + "&amp;openfile=true"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, expected_url, html=False)

    @patch("nextcloud_app.api.NextcloudApiClient.list_resources")
    @patch("nextcloud_app.api.NextcloudApiClient.ensure_user_share")
    @patch("nextcloud_app.api.NextcloudApiClient.get_user_share")
    @patch("nextcloud_app.api.NextcloudApiClient.list_user_shares")
    def test_contracts_partial_repairs_missing_lawyer_share_for_docx_link(
        self,
        mocked_list_user_shares,
        mocked_get_user_share,
        mocked_ensure_user_share,
        mocked_list_resources,
    ):
        lawyer_user = get_user_model().objects.create_user(
            username="lawyer-repair-share@example.com",
            email="lawyer-repair-share@example.com",
            password="secret",
            is_staff=True,
        )
        lawyer_group, _ = Group.objects.get_or_create(name=LAWYER_GROUP)
        lawyer_user.groups.add(lawyer_group)
        NextcloudUserLink.objects.create(
            user=lawyer_user,
            nextcloud_user_id="nc-lawyer-repair",
            nextcloud_username="nc-lawyer-repair",
            nextcloud_email=lawyer_user.email,
        )
        mocked_list_user_shares.return_value = {}
        mocked_get_user_share.return_value = None
        mocked_ensure_user_share.return_value = NextcloudShare(
            share_id="58",
            path=self.performer.contract_project_disk_folder,
            share_with="nc-lawyer-repair",
            permissions=15,
            target_path="/Shared/000 Иванов ИИ",
        )
        mocked_list_resources.return_value = [
            {
                "name": self.performer.contract_file,
                "path": f"{self.performer.contract_project_disk_folder}/{self.performer.contract_file}",
                "type": "file",
                "file_id": "4476",
            }
        ]
        self.client.force_login(lawyer_user)

        response = self.client.get(reverse("contracts_partial"))

        expected_url = (
            "https://cloud.example.com/apps/files/files/4476?dir="
            + quote("/Shared/000 Иванов ИИ", safe="/")
            + "&amp;openfile=true"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, expected_url, html=False)
        mocked_ensure_user_share.assert_called_once_with(
            "cloud-admin",
            self.performer.contract_project_disk_folder,
            "nc-lawyer-repair",
            permissions=15,
        )

    @patch("nextcloud_app.api.NextcloudApiClient.ensure_user_share", side_effect=NextcloudApiError("silent"))
    @patch("nextcloud_app.api.NextcloudApiClient.get_user_share", return_value=None)
    @patch("nextcloud_app.api.NextcloudApiClient.list_resources")
    @patch("nextcloud_app.api.NextcloudApiClient.list_user_shares", return_value={})
    def test_contracts_partial_falls_back_to_file_redirect_when_target_unknown(
        self,
        _mocked_list_user_shares,
        mocked_list_resources,
        _mocked_get_user_share,
        _mocked_ensure_user_share,
    ):
        lawyer_user = get_user_model().objects.create_user(
            username="lawyer-file-id@example.com",
            email="lawyer-file-id@example.com",
            password="secret",
            is_staff=True,
        )
        lawyer_group, _ = Group.objects.get_or_create(name=LAWYER_GROUP)
        lawyer_user.groups.add(lawyer_group)
        NextcloudUserLink.objects.create(
            user=lawyer_user,
            nextcloud_user_id="nc-lawyer-file-id",
            nextcloud_username="nc-lawyer-file-id",
            nextcloud_email=lawyer_user.email,
        )
        self.performer.contract_project_file_id = "4477"
        self.performer.contract_project_folder_file_id = "4478"
        self.performer.save(update_fields=["contract_project_file_id", "contract_project_folder_file_id"])
        self.client.force_login(lawyer_user)

        response = self.client.get(reverse("contracts_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="https://cloud.example.com/f/4477"', html=False)
        self.assertContains(response, 'href="https://cloud.example.com/f/4478"', html=False)
        mocked_list_resources.assert_not_called()

    def test_contract_template_form_saves_multiple_groups_and_products(self):
        second_group = GroupMember.objects.create(
            short_name="Казахстан",
            country_name="Казахстан",
            country_code="398",
            country_alpha2="KZ",
            position=2,
        )
        country = OKSMCountry.objects.create(
            number=398,
            code="398",
            short_name="Казахстан",
            alpha2="KZ",
            alpha3="KAZ",
        )
        product = Product.objects.create(
            short_name="CT-TDD",
            name_en="TDD",
            name_ru="TDD",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
        )
        second_product = Product.objects.create(
            short_name="CT-OVR",
            name_en="OVR",
            name_ru="OVR",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Обзор",
        )
        form = ContractTemplateForm(
            data={
                "group_member_ids": [str(self.group_member.pk), str(second_group.pk)],
                "product_ids": [str(product.pk), str(second_product.pk)],
                "contract_type": "smz",
                "party": "individual",
                "country": str(country.pk),
                "sample_name": "",
                "version": "",
                "section_ids": ["__all__"],
            },
            files={
                "file": SimpleUploadedFile(
                    "template.docx",
                    b"docx",
                    content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ),
            },
        )

        self.assertTrue(form.is_valid(), form.errors)
        template = form.save()

        self.assertEqual(
            set(template.group_members.values_list("pk", flat=True)),
            {self.group_member.pk, second_group.pk},
        )
        self.assertEqual(template.group_member_id, self.group_member.pk)
        self.assertEqual(
            set(template.products.values_list("pk", flat=True)),
            {product.pk, second_product.pk},
        )
        self.assertEqual(template.product_id, product.pk)
        self.assertTrue(template.sample_name.startswith("RU-KZ Шаблон договора ФЗЛ СМЗ KAZ_CT-TDD-CT-OVR-Общий_v"))

    def test_contract_template_table_renders_all_group_for_unscoped_template(self):
        ContractTemplate.objects.create(
            group_member=None,
            product=self.product,
            contract_type="gph",
            party="individual",
            country_name="Россия",
            country_code="643",
            sample_name="Все Шаблон договора ФЗЛ ГПХ RUS_DD-Общий_v1",
            version="1",
            file=SimpleUploadedFile(
                "template.docx",
                b"docx",
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            is_all_sections=True,
        )

        response = self.client.get(reverse("ct_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<td class=\"text-nowrap\">Все</td>", html=False)

    def test_contract_template_table_renders_all_product_for_unscoped_template(self):
        ContractTemplate.objects.create(
            group_member=self.group_member,
            product=None,
            contract_type="gph",
            party="individual",
            country_name="Россия",
            country_code="643",
            sample_name="RU Шаблон договора ФЗЛ ГПХ RUS_Все-Общий_v1",
            version="1",
            file=SimpleUploadedFile(
                "template.docx",
                b"docx",
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            is_all_sections=True,
        )

        response = self.client.get(reverse("ct_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<td class=\"text-nowrap\">Все</td>", html=False)

    def test_contracts_development_partial_renders_client_contract_projects_table(self):
        response = self.client.get(reverse("contracts_development_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Проекты договоров с клиентами")
        self.assertContains(response, "Вид соглашения")
        self.assertContains(response, "Проект ID")
        self.assertContains(response, "Заказчик")
        self.assertContains(response, reverse("contracts_project_registration_create"))
        self.assertContains(response, reverse("contracts_project_registration_edit", args=[self.project.pk]))

    def test_contracts_project_registration_create_form_targets_contracts_drafts_pane(self):
        response = self.client.get(reverse("contracts_project_registration_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'hx-post="%s"' % reverse("contracts_project_registration_create"), html=False)
        self.assertContains(response, 'hx-target="#contracts-drafts-pane"', html=False)
        self.assertNotContains(response, "Дедлайн")

    @patch("contracts_app.views._upload_scan_to_cloud_bytes", return_value="https://cloud.example.com/s/scan")
    def test_contract_scan_upload_returns_storage_label(self, _mock_upload):
        upload = SimpleUploadedFile("scan.pdf", b"pdf-data", content_type="application/pdf")
        with self.settings(MEDIA_ROOT=self.media_root):
            response = self.client.post(
                reverse("contract_scan_upload", args=[self.performer.pk]),
                {"contract_employee_scan": upload},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["storage_label"], "Nextcloud")
        self.performer.refresh_from_db()
        self.assertEqual(self.performer.contract_employee_scan.name, "")
        self.assertEqual(self.performer.contract_employee_scan_link, "https://cloud.example.com/s/scan")

    def test_contract_signing_modal_uses_cloud_link_for_current_file(self):
        self.performer.contract_scan_document = "Договор 7001_Иванов ИИ_1п.pdf"
        self.performer.contract_employee_scan_link = "https://cloud.example.com/s/current-scan"
        self.performer.save(update_fields=["contract_scan_document", "contract_employee_scan_link"])

        response = self.client.get(reverse("contracts_signing_edit", args=[self.performer.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "https://cloud.example.com/s/current-scan", html=False)
        self.assertContains(response, "Договор 7001_Иванов ИИ_1п.pdf", html=False)

    def test_contracts_partial_marks_signing_row_as_having_scan_from_cloud_fields(self):
        self.performer.contract_scan_document = "Договор 7001_Иванов ИИ_1п.pdf"
        self.performer.contract_employee_scan_link = "https://cloud.example.com/s/current-scan"
        self.performer.contract_employee_scan = ""
        self.performer.save(update_fields=["contract_scan_document", "contract_employee_scan_link", "contract_employee_scan"])

        response = self.client.get(reverse("contracts_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-has-scan="1"', html=False)

    @patch("nextcloud_app.api.NextcloudApiClient.list_user_shares")
    def test_contracts_partial_builds_nextcloud_disk_link_from_user_share_target(self, mocked_list_user_shares):
        mocked_list_user_shares.return_value = {
            self.performer.contract_project_disk_folder: NextcloudShare(
                share_id="55",
                path=self.performer.contract_project_disk_folder,
                share_with=self.employee_link.nextcloud_user_id,
                permissions=1,
                target_path="/Shared/000 Иванов ИИ",
            )
        }
        self.client.force_login(self.employee_user)

        response = self.client.get(reverse("contracts_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "/apps/files/files?dir=/Shared/000%20%D0%98%D0%B2%D0%B0%D0%BD%D0%BE%D0%B2%20%D0%98%D0%98",
            html=False,
        )

    @patch("nextcloud_app.api.NextcloudApiClient.list_user_shares", side_effect=NextcloudApiError("temporary outage"))
    def test_contracts_partial_falls_back_to_generic_folder_url_when_share_resolution_fails(self, _mocked_list_user_shares):
        self.client.force_login(self.employee_user)

        response = self.client.get(reverse("contracts_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "/apps/files/files?dir=/Corporate%20Root/2026/Project/09%20%D0%94%D0%BE%D0%B3%D0%BE%D0%B2%D0%BE%D1%80%D1%8B/000%20%D0%98%D0%B2%D0%B0%D0%BD%D0%BE%D0%B2%20%D0%98%D0%98",
            html=False,
        )

    @patch("contracts_app.views._upload_scan_to_cloud_bytes", return_value="")
    def test_contract_signing_edit_keeps_existing_local_scan_when_cloud_upload_fails(self, _mock_upload):
        with self.settings(MEDIA_ROOT=self.media_root):
            self.performer.contract_employee_scan.save("existing-scan.pdf", ContentFile(b"existing"), save=True)
            old_name = self.performer.contract_employee_scan.name
            old_path = self.performer.contract_employee_scan.path

            response = self.client.post(
                reverse("contracts_signing_edit", args=[self.performer.pk]),
                {
                    "contract_employee_scan": SimpleUploadedFile(
                        "new-scan.pdf",
                        b"new-data",
                        content_type="application/pdf",
                    ),
                },
            )

        self.assertEqual(response.status_code, 200)
        self.performer.refresh_from_db()
        self.assertEqual(self.performer.contract_employee_scan.name, old_name)
        self.assertTrue(os.path.exists(old_path))
        self.assertIn("contract_employee_scan", response.context["form"].errors)

    def test_contract_signing_edit_noop_does_not_clear_sibling_local_scan_fields(self):
        sibling = Performer.objects.create(
            registration=self.project,
            employee=self.employee,
            executor="Иванов Иван Иванович",
            contract_batch_id=self.performer.contract_batch_id,
            contract_project_disk_folder=self.performer.contract_project_disk_folder,
        )
        with self.settings(MEDIA_ROOT=self.media_root):
            sibling.contract_employee_scan.save("sibling-employee.pdf", ContentFile(b"employee"), save=True)
            sibling.contract_signed_scan_file.save("sibling-signed.pdf", ContentFile(b"signed"), save=True)
            employee_name = sibling.contract_employee_scan.name
            signed_name = sibling.contract_signed_scan_file.name

            response = self.client.post(
                reverse("contracts_signing_edit", args=[self.performer.pk]),
                {},
            )

        self.assertEqual(response.status_code, 200)
        sibling.refresh_from_db()
        self.assertEqual(sibling.contract_employee_scan.name, employee_name)
        self.assertEqual(sibling.contract_signed_scan_file.name, signed_name)


class ContractVariableBindingDisplayTests(TestCase):
    def test_binding_display_uses_current_app_section_label(self):
        variable = ContractVariable(
            source_section="experts",
            source_table="contract_details",
            source_column="full_name",
        )

        self.assertEqual(
            variable.binding_display,
            "Значения столбца «ФИО» "
            "из таблицы «Реквизиты физлиц-исполнителей» "
            "раздела «Исполнители»",
        )


class ContractVariableResolverTests(TestCase):
    def test_contract_details_variables_resolve_from_expert_contract_details(self):
        user = get_user_model().objects.create_user(
            username="resolver-expert",
            password="secret",
            first_name="Иван",
            last_name="Иванов",
        )
        employee = Employee.objects.create(user=user, patronymic="Иванович")
        person = PersonRecord.objects.create(
            last_name="Иванов",
            first_name="Иван",
            middle_name="Иванович",
            full_name_genitive="Иванова Ивана Ивановича",
            gender="male",
            birth_date=date(1990, 5, 17),
            position=1,
        )
        employee.person_record = person
        employee.save(update_fields=["person_record"])
        country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            short_name_genitive="России",
            full_name="Российская Федерация",
            alpha2="RU",
            alpha3="RUS",
            position=1,
        )
        citizenship = CitizenshipRecord.objects.create(
            person=person,
            country=country,
            status="Гражданство",
            identifier="Паспорт",
            number="123456",
            position=1,
        )
        profile = ExpertProfile.objects.create(employee=employee, position=1)
        ExpertContractDetails.objects.create(
            expert_profile=profile,
            citizenship_record=citizenship,
            inn="770123456789",
            passport_expiry_date=date(2030, 4, 27),
            bank_swift="SABRRUMM",
            bank_bik="044525225",
            settlement_account="40817810099910004312",
            corr_account="30101810400000000225",
            corr_bank_settlement_account="30101810945250000225",
            corr_bank_corr_account="30101810000000000000",
        )
        product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
        )
        project = ProjectRegistration.objects.create(
            number=7002,
            type=product,
            name="Договорный проект",
            customer='АО "Заказчик"',
            country=country,
            year=2026,
        )
        performer = Performer.objects.create(
            registration=project,
            employee=employee,
            executor="Иванов Иван Иванович",
        )

        variables = [
            ContractVariable(key="{{short_name}}", source_section="contacts", source_table="persons", source_column="short_name"),
            ContractVariable(key="{{name}}", source_section="projects", source_table="registration", source_column="customer"),
            ContractVariable(key="{{country}}", source_section="classifiers", source_table="oksm_countries", source_column="full_name"),
            ContractVariable(key="{{full_name_genitive}}", source_section="experts", source_table="contract_details", source_column="full_name_genitive"),
            ContractVariable(key="{{citizenship_country}}", source_section="experts", source_table="contract_details", source_column="citizenship_country"),
            ContractVariable(key="{{citizenship_identifier}}", source_section="experts", source_table="contract_details", source_column="citizenship_identifier"),
            ContractVariable(key="{{passport_expiry_date}}", source_section="experts", source_table="contract_details", source_column="passport_expiry"),
            ContractVariable(key="{{bank_swift}}", source_section="experts", source_table="contract_details", source_column="swift"),
            ContractVariable(key="{{corr_account}}", source_section="experts", source_table="contract_details", source_column="correspondent_account"),
            ContractVariable(key="{{corr_bank_settlement_account}}", source_section="experts", source_table="contract_details", source_column="corr_bank_settlement"),
            ContractVariable(key="{{legacy_bank_swift}}", source_section="experts", source_table="contract_details", source_column="bank_swift"),
        ]

        replacements, lists = resolve_variables(performer, variables)

        self.assertEqual(lists, {})
        self.assertEqual(replacements["{{short_name}}"], "Иванов И.И.")
        self.assertEqual(replacements["{{name}}"], 'АО "Заказчик"')
        self.assertEqual(replacements["{{country}}"], "Российская Федерация")
        self.assertEqual(replacements["{{full_name_genitive}}"], "Иванова Ивана Ивановича")
        self.assertEqual(replacements["{{citizenship_country}}"], "Россия")
        self.assertEqual(replacements["{{citizenship_identifier}}"], "Паспорт")
        self.assertEqual(replacements["{{passport_expiry_date}}"], "27.04.2030")
        self.assertEqual(replacements["{{bank_swift}}"], "SABRRUMM")
        self.assertEqual(replacements["{{corr_account}}"], "30101810400000000225")
        self.assertEqual(replacements["{{corr_bank_settlement_account}}"], "30101810945250000225")
        self.assertEqual(replacements["{{legacy_bank_swift}}"], "SABRRUMM")

    def test_date_variables_use_saved_performer_contract_date(self):
        product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
        )
        project = ProjectRegistration.objects.create(
            number=7004,
            type=product,
            name="Проект с датой договора",
            year=2026,
        )
        performer = Performer.objects.create(
            registration=project,
            executor="Иванов Иван Иванович",
            contract_date=date(2026, 5, 7),
        )
        variables = [
            ContractVariable(key="{{year}}", is_computed=True),
            ContractVariable(key="{{day}}", is_computed=True),
            ContractVariable(key="{{month}}", is_computed=True),
        ]

        replacements, lists = resolve_variables(performer, variables)

        self.assertEqual(lists, {})
        self.assertEqual(replacements["{{year}}"], "2026")
        self.assertEqual(replacements["{{day}}"], "07")
        self.assertEqual(replacements["{{month}}"], "мая")

    def test_contacts_short_name_falls_back_to_performer_employee_person_record(self):
        user = get_user_model().objects.create_user(
            username="resolver-performer-person",
            password="secret",
        )
        person = PersonRecord.objects.create(
            last_name="Петров",
            first_name="Петр",
            middle_name="Петрович",
            position=1,
        )
        employee = Employee.objects.create(user=user, person_record=person)
        product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
        )
        project = ProjectRegistration.objects.create(
            number=7003,
            type=product,
            name="Проект без профиля эксперта",
            year=2026,
        )
        performer = Performer.objects.create(
            registration=project,
            employee=employee,
            executor="Петров Петр Петрович",
        )
        variables = [
            ContractVariable(
                key="{{short_name}}",
                source_section="contacts",
                source_table="persons",
                source_column="short_name",
            ),
        ]

        replacements, lists = resolve_variables(performer, variables)

        self.assertEqual(lists, {})
        self.assertEqual(replacements["{{short_name}}"], "Петров П.П.")
