import os
import shutil
import tempfile
import uuid
from datetime import date
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
from contracts_app.models import ContractVariable
from contracts_app.variable_resolver import resolve_variables
from experts_app.models import ExpertContractDetails, ExpertProfile
from group_app.models import GroupMember
from nextcloud_app.api import NextcloudApiError, NextcloudShare
from nextcloud_app.models import NextcloudUserLink
from policy_app.models import EXPERT_GROUP, Product
from projects_app.models import Performer, ProjectRegistration
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
            employment="Фрилансер",
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
            contract_project_disk_folder="/Corporate Root/2026/Project/09 Договоры/000 Иванов ИИ",
        )

    def test_contracts_partial_renders_contract_conclusion_before_contract_projects(self):
        response = self.client.get(reverse("contracts_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Заключение договора")
        self.assertContains(response, "Создать проект договора")
        self.assertContains(response, "Отправить проект договора")
        self.assertContains(
            response,
            "На Nextcloud в целевой папке будут созданы папки исполнителей с проектами договоров.",
            html=False,
        )
        self.assertContains(response, 'id="contract-project-filter-toggle"', html=False)
        self.assertContains(response, 'data-request-url="%s"' % reverse("contract_request"), html=False)
        self.assertContains(
            response,
            'data-create-contract-url="%s"' % reverse("create_contract_project"),
            html=False,
        )
        self.assertContains(response, "Договорный проект")

        content = response.content.decode("utf-8")
        self.assertLess(
            content.index('id="contract-conclusion-section"'),
            content.index('id="contracts-project-filter-toggle"'),
        )

    def test_contracts_partial_uses_current_primary_cloud_label_in_disk_tooltip(self):
        response = self.client.get(reverse("contracts_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'title="Открыть папку на Nextcloud"', html=False)

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
