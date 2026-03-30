import os
import shutil
import tempfile
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import CloudStorageSettings
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
            service_type="service",
        )
        self.project = ProjectRegistration.objects.create(
            number=7001,
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
            contract_batch_id=uuid.uuid4(),
            contract_project_disk_folder="/Corporate Root/2026/Project/09 Договоры/000 Иванов ИИ",
        )

    def test_contracts_partial_uses_current_primary_cloud_label_in_disk_tooltip(self):
        response = self.client.get(reverse("contracts_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'title="Открыть папку на Nextcloud"', html=False)

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
