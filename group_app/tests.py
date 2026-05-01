import os
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from classifiers_app.models import OKSMCountry
from .models import GroupMember


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
