import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import CloudStorageSettings
from policy_app.models import Product
from projects_app.models import RegistrationWorkspaceFolder, SourceDataTargetFolder
from projects_app.forms import ProjectRegistrationForm
from group_app.models import GroupMember
from projects_app.models import ProjectRegistration


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
            service_type="service",
        )

    def test_type_and_deadline_are_required(self):
        form = ProjectRegistrationForm(
            data={
                "number": 4444,
                "group_member": self.group_member.pk,
                "agreement_type": "MAIN",
                "type": "",
                "name": "Проект Альфа",
                "status": "Не начат",
                "deadline": "",
                "year": 2026,
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("type", form.errors)
        self.assertIn("deadline", form.errors)


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
            service_type="service",
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
