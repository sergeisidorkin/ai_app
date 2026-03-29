from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from checklists_app.models import ProjectWorkspace
from policy_app.models import Product
from projects_app.models import ProjectRegistration
from yandexdisk_app.models import YandexDiskSelection
from yandexdisk_app.workspace import (
    _build_folder_tree,
    _contains_workspace_project_variable,
    _resolve_workspace_folder_name,
    _sanitize_relative_path,
    WorkspaceResult,
    create_basic_project_workspace_stream,
)


class WorkspaceFolderVariablesTests(SimpleTestCase):
    def make_project(self, *, short_uid="444410RU", product_short="DD", name="Проект Альфа"):
        product = Product(short_name=product_short, name_en="Due Diligence", name_ru="ДД", service_type="service")
        return ProjectRegistration(short_uid=short_uid, type=product, name=name)

    def test_resolve_workspace_folder_name_replaces_project_label(self):
        project = self.make_project()

        resolved = _resolve_workspace_folder_name("01 {project_label}", project)

        self.assertEqual(resolved, "01 444410RU DD Проект Альфа")

    def test_build_folder_tree_resolves_project_label_for_selected_project(self):
        project = self.make_project(name="Проект/Альфа")
        rows = [
            (1, "{project_label}"),
            (2, "02 Письма"),
            (3, "Черновики"),
        ]

        paths = _build_folder_tree(rows, project=project)

        self.assertEqual(
            paths,
            [
                "444410RU DD Проект_Альфа",
                "444410RU DD Проект_Альфа/02 Письма",
                "444410RU DD Проект_Альфа/02 Письма/Черновики",
            ],
        )

    def test_sanitize_relative_path_keeps_nested_folders(self):
        self.assertEqual(
            _sanitize_relative_path("05 Исходные данные/01 Запросы"),
            "05 Исходные данные/01 Запросы",
        )

    def test_contains_workspace_project_variable_detects_template_folder(self):
        self.assertTrue(_contains_workspace_project_variable("05 Исходные данные/{project_label}"))
        self.assertFalse(_contains_workspace_project_variable("05 Исходные данные/01 Запросы"))


class WorkspacePublishingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="workspace-owner",
            password="secret",
        )
        YandexDiskSelection.objects.create(
            user=self.user,
            resource_path="/Root",
            resource_name="Root",
            resource_type="dir",
        )
        self.product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            service_type="service",
        )
        self.project = ProjectRegistration.objects.create(
            number=4444,
            type=self.product,
            name="Проект Альфа",
            year=2026,
        )

    @patch("yandexdisk_app.workspace.publish_resource")
    @patch("yandexdisk_app.workspace.create_folder", return_value=True)
    def test_basic_workspace_creation_does_not_publish_project_folder(self, _create_folder, publish_resource):
        items = list(create_basic_project_workspace_stream(self.user, self.project))

        self.assertIsInstance(items[-1], WorkspaceResult)
        self.assertTrue(items[-1].ok)
        publish_resource.assert_not_called()

        workspace = ProjectWorkspace.objects.get(project=self.project)
        self.assertEqual(workspace.public_url, "")
