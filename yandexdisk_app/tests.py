from unittest.mock import patch
from datetime import datetime, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from checklists_app.models import ChecklistItem, SourceDataItemFolder, SourceDataWorkspace, ProjectWorkspace
from core.models import CloudStorageSettings
from policy_app.models import Product
from projects_app.models import ProjectRegistration
from yandexdisk_app.models import YandexDiskSelection
from yandexdisk_app.sync import _sync_folders, run_sync
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


class FolderSyncTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="sync-owner",
            password="secret",
            is_staff=True,
        )
        self.product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            service_type="service",
        )
        self.project = ProjectRegistration.objects.create(
            number=6001,
            type=self.product,
            name="Синхронизация папок",
            year=2026,
        )
        self.section = self.product.sections.create(
            code="FIN",
            short_name="Finance",
            short_name_ru="Финансы",
            name_en="Finance",
            name_ru="Финансы",
            accounting_type="Раздел",
            position=1,
        )
        self.item = ChecklistItem.objects.create(
            project=self.project,
            section=self.section,
            code="REQ",
            number=1,
            short_name="ОСВ",
            name="Оборотно-сальдовая ведомость",
            position=1,
        )

    def test_sync_folders_counts_files_in_nested_subfolders(self):
        folder = SourceDataItemFolder.objects.create(
            project=self.project,
            checklist_item=self.item,
            asset_name="",
            disk_path="/Root/base/REQ-01 ОСВ",
        )
        calls = []

        def fake_list_resources(user, path, limit=1000):
            calls.append(path)
            if path == "/Root/base":
                return [{"path": "/Root/base/REQ-01 ОСВ", "type": "dir"}]
            if path == "/Root/base/REQ-01 ОСВ":
                return [
                    {"path": "/Root/base/REQ-01 ОСВ/file-a.pdf", "type": "file", "modified": "2026-03-29T10:00:00Z"},
                    {"path": "/Root/base/REQ-01 ОСВ/nested", "type": "dir"},
                ]
            if path == "/Root/base/REQ-01 ОСВ/nested":
                return [
                    {"path": "/Root/base/REQ-01 ОСВ/nested/file-b.pdf", "type": "file", "modified": "2026-03-30T12:00:00Z"},
                ]
            return []

        updated = _sync_folders(self.user, SourceDataItemFolder.objects.filter(pk=folder.pk), 0, fake_list_resources)

        self.assertEqual(updated, 1)
        folder.refresh_from_db()
        self.assertEqual(folder.file_count, 2)
        self.assertEqual(folder.last_upload_at, datetime(2026, 3, 30, 12, 0, tzinfo=dt_timezone.utc))
        self.assertIn("/Root/base/REQ-01 ОСВ/nested", calls)

    @patch("core.cloud_storage.list_folder_resources")
    def test_run_sync_updates_source_data_folders_for_nextcloud_without_yandex_account(self, mocked_list_folder_resources):
        settings_obj = CloudStorageSettings.get_solo()
        settings_obj.primary_storage = CloudStorageSettings.PrimaryStorage.NEXTCLOUD
        settings_obj.nextcloud_root_path = "/Corporate Root"
        settings_obj.save()
        SourceDataWorkspace.objects.create(
            project=self.project,
            disk_path="/Corporate Root/2026/6001 DD Синхронизация папок/05 Исходные данные",
            created_by=self.user,
        )
        folder = SourceDataItemFolder.objects.create(
            project=self.project,
            checklist_item=self.item,
            asset_name="",
            disk_path="/Corporate Root/2026/6001 DD Синхронизация папок/05 Исходные данные/REQ-01 ОСВ",
        )

        def nextcloud_listing(user, path, limit=1000):
            if path.endswith("/05 Исходные данные"):
                return [{"path": folder.disk_path, "type": "dir"}]
            if path == folder.disk_path:
                return [
                    {"path": f"{folder.disk_path}/scan-1.pdf", "type": "file", "modified": "2026-03-28T08:30:00Z"},
                    {"path": f"{folder.disk_path}/nested", "type": "dir"},
                ]
            if path == f"{folder.disk_path}/nested":
                return [{"path": f"{folder.disk_path}/nested/scan-2.pdf", "type": "file", "modified": "2026-03-31T09:00:00Z"}]
            return []

        mocked_list_folder_resources.side_effect = nextcloud_listing

        updated = run_sync(delay=0)

        self.assertEqual(updated, 1)
        folder.refresh_from_db()
        self.assertEqual(folder.file_count, 2)
        self.assertEqual(folder.last_upload_at, datetime(2026, 3, 31, 9, 0, tzinfo=dt_timezone.utc))
