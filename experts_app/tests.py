import os
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from experts_app.models import ExpertProfile
from users_app.models import Employee


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
        self.profile = ExpertProfile.objects.create(employee=self.employee, position=1)

    def test_contract_details_edit_uploads_facsimile_and_renders_download_link(self):
        with self.settings(MEDIA_ROOT=self.media_root):
            response = self.client.post(
                reverse("epr_contract_details_edit", args=[self.profile.pk]),
                {
                    "facsimile_file": SimpleUploadedFile(
                        "facsimile.pdf",
                        b"facsimile-data",
                        content_type="application/pdf",
                    ),
                },
            )

        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.facsimile_file.name)
        self.assertContains(response, "Факсимиле")
        self.assertContains(
            response,
            reverse("epr_contract_facsimile_download", args=[self.profile.pk]),
            html=False,
        )

    def test_contract_details_edit_can_clear_facsimile_file(self):
        with self.settings(MEDIA_ROOT=self.media_root):
            self.profile.facsimile_file.save("facsimile.pdf", ContentFile(b"facsimile-data"), save=True)
            old_path = self.profile.facsimile_file.path

            response = self.client.post(
                reverse("epr_contract_details_edit", args=[self.profile.pk]),
                {"facsimile_file-clear": "on"},
            )

        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.facsimile_file.name, "")
        self.assertFalse(os.path.exists(old_path))

    def test_contract_facsimile_download_returns_attachment(self):
        with self.settings(MEDIA_ROOT=self.media_root):
            self.profile.facsimile_file.save("facsimile.pdf", ContentFile(b"facsimile-data"), save=True)

            response = self.client.get(
                reverse("epr_contract_facsimile_download", args=[self.profile.pk])
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertIn("facsimile.pdf", response["Content-Disposition"])
        self.assertEqual(b"".join(response.streaming_content), b"facsimile-data")
