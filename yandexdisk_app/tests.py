from django.test import SimpleTestCase

from policy_app.models import Product
from projects_app.models import ProjectRegistration
from yandexdisk_app.workspace import _build_folder_tree, _resolve_workspace_folder_name


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
