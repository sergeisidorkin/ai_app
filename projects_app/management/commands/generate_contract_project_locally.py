import json
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.test import RequestFactory

from projects_app.models import Performer


class LocalContractCloud:
    def __init__(self, output_dir, root_path):
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.root_path = self._normalize_cloud_path(root_path)
        self.uploaded_files = []
        self._published_counter = 0

    @staticmethod
    def _normalize_cloud_path(path):
        raw = str(path or "").strip().replace("\\", "/")
        parts = [part.strip() for part in raw.split("/") if part.strip()]
        if any(part in {".", ".."} for part in parts):
            raise CommandError("Локальный cloud path не должен содержать '.' или '..'.")
        return "/" + "/".join(parts) if parts else "/"

    def local_path(self, cloud_path):
        normalized = self._normalize_cloud_path(cloud_path)
        parts = [part for part in normalized.strip("/").split("/") if part]
        return self.output_dir.joinpath(*parts)

    def create_folder(self, _user, cloud_path):
        self.local_path(cloud_path).mkdir(parents=True, exist_ok=True)
        return True

    def list_resources(self, _user, cloud_path, *, limit=100):
        local_path = self.local_path(cloud_path)
        if not local_path.exists():
            return []
        items = []
        for child in sorted(local_path.iterdir(), key=lambda item: item.name)[:limit]:
            items.append({
                "name": child.name,
                "path": f"{self._normalize_cloud_path(cloud_path).rstrip('/')}/{child.name}",
            })
        return items

    def upload_file(self, _user, cloud_path, data, *, overwrite=True):
        local_path = self.local_path(cloud_path)
        if local_path.exists() and not overwrite:
            return False
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(data)
        self.uploaded_files.append((cloud_path, local_path))
        return True

    def publish_resource(self, _user, cloud_path):
        self._published_counter += 1
        return f"https://local.contract.test/{self._published_counter}"


class Command(BaseCommand):
    help = (
        "Локально генерирует проект договора для выбранных Performer ID, "
        "используя тот же view, что и кнопка «Создать проект договора»."
    )

    def add_arguments(self, parser):
        parser.add_argument("performer_ids", nargs="*", type=int, help="ID строк из таблицы составления договора")
        parser.add_argument("--user-id", type=int, help="ID staff-пользователя, от имени которого выполнить генерацию")
        parser.add_argument("--username", help="Username staff-пользователя, от имени которого выполнить генерацию")
        parser.add_argument(
            "--output-dir",
            default="tmp/contract-project-local",
            help="Куда сохранить локально созданные DOCX (по умолчанию: tmp/contract-project-local)",
        )
        parser.add_argument(
            "--root-path",
            default="/Local Contract Test",
            help="Виртуальная корневая папка облака (по умолчанию: /Local Contract Test)",
        )
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Не откатывать изменения Performer в БД после локального прогона",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="Показать доступные строки для генерации и выйти",
        )
        parser.add_argument("--limit", type=int, default=30, help="Сколько строк показать для --list")

    def handle(self, *args, **options):
        if options["list"]:
            self._print_available_performers(options["limit"])
            return

        performer_ids = options["performer_ids"]
        if not performer_ids:
            raise CommandError("Передайте хотя бы один Performer ID или используйте --list.")

        user = self._get_user(options)
        if not user.is_staff:
            raise CommandError(f"Пользователь {user!s} не staff; view не разрешит генерацию.")

        local_cloud = LocalContractCloud(options["output_dir"], options["root_path"])
        request = RequestFactory().post(
            "/projects/performers/create-contract-project/",
            data={"performer_ids[]": [str(pk) for pk in performer_ids]},
        )
        request.user = user

        from projects_app import views as project_views

        patches = (
            patch.object(project_views, "get_selected_root_path", return_value=local_cloud.root_path),
            patch.object(project_views, "cloud_create_folder", side_effect=local_cloud.create_folder),
            patch.object(project_views, "list_folder_resources", side_effect=local_cloud.list_resources),
            patch.object(project_views, "cloud_upload_file", side_effect=local_cloud.upload_file),
            patch.object(project_views, "cloud_publish_resource", side_effect=local_cloud.publish_resource),
            patch.object(project_views, "_share_contract_folder_for_nextcloud", return_value=[]),
            patch.object(project_views, "_resolve_contract_project_nextcloud_file_id", return_value=""),
        )

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            with transaction.atomic():
                response = project_views.create_contract_project(request)
                messages = self._consume_response(response)
                final_message = next((msg for msg in reversed(messages) if "ok" in msg), None)
                if not options["commit"] or not final_message or not final_message.get("ok"):
                    transaction.set_rollback(True)

        if not final_message or not final_message.get("ok"):
            error = final_message.get("error") if final_message else "View не вернул финальный статус."
            raise CommandError(error)

        self.stdout.write(self.style.SUCCESS(final_message.get("message") or "Проект договора создан."))
        if final_message.get("warnings"):
            for warning in final_message["warnings"]:
                self.stdout.write(self.style.WARNING(f"Предупреждение: {warning}"))

        if local_cloud.uploaded_files:
            self.stdout.write("Созданные файлы:")
            for _cloud_path, local_path in local_cloud.uploaded_files:
                self.stdout.write(f"  {local_path}")
        else:
            self.stdout.write(self.style.WARNING("DOCX-файлы не были записаны. Проверьте предупреждения и шаблоны."))

        if not options["commit"]:
            self.stdout.write("Изменения в БД откатаны. Для сохранения полей Performer добавьте --commit.")

    def _get_user(self, options):
        User = get_user_model()
        if options.get("user_id"):
            try:
                return User.objects.get(pk=options["user_id"])
            except User.DoesNotExist as exc:
                raise CommandError(f"Пользователь с ID {options['user_id']} не найден.") from exc
        if options.get("username"):
            try:
                return User.objects.get(username=options["username"])
            except User.DoesNotExist as exc:
                raise CommandError(f"Пользователь {options['username']} не найден.") from exc

        user = User.objects.filter(is_staff=True).order_by("-is_superuser", "id").first()
        if not user:
            raise CommandError("Не найден staff-пользователь. Передайте --username или --user-id.")
        return user

    def _consume_response(self, response):
        messages = []
        if getattr(response, "streaming", False):
            for chunk in response.streaming_content:
                payload = chunk.decode("utf-8").strip()
                if not payload:
                    continue
                for line in payload.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    msg = json.loads(line)
                    messages.append(msg)
                    if "current" in msg and "total" in msg:
                        self.stdout.write(f"Прогресс: {msg['current']}/{msg['total']}")
            return messages

        payload = response.content.decode("utf-8").strip()
        if payload:
            messages.append(json.loads(payload))
        return messages

    def _print_available_performers(self, limit):
        rows = (
            Performer.objects
            .select_related("registration", "typical_section", "employee")
            .filter(contract_sent_at__isnull=True)
            .exclude(executor="")
            .order_by("registration_id", "executor", "position", "id")[:limit]
        )
        if not rows:
            self.stdout.write("Нет доступных строк Performer для создания проекта договора.")
            return

        self.stdout.write("Доступные Performer ID:")
        for performer in rows:
            project = performer.registration
            project_label = getattr(project, "short_uid", "") or getattr(project, "formatted_number", "") or "-"
            section = getattr(performer.typical_section, "code", "") or "-"
            created = "created" if performer.contract_project_created else "pending"
            self.stdout.write(
                f"  {performer.pk}: {project_label} | {performer.executor or '-'} | {section} | {created}"
            )
