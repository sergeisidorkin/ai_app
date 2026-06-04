import json
import re
import shutil
import struct
import subprocess
import tempfile
import zlib
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.test import RequestFactory, override_settings

from projects_app.models import Performer


MINIMAL_PDF_BYTES = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Count 0>>endobj\n%%EOF\n"


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type)
    crc = zlib.crc32(data, crc)
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc & 0xFFFFFFFF)


def _visible_test_facsimile_png() -> bytes:
    width = 420
    height = 120
    pixels = bytearray([255, 255, 255, 0] * width * height)

    def set_pixel(x, y, rgba=(8, 62, 145, 255)):
        if 0 <= x < width and 0 <= y < height:
            offset = (y * width + x) * 4
            pixels[offset:offset + 4] = bytes(rgba)

    def draw_line(x0, y0, x1, y1, thickness=4):
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            for tx in range(-thickness // 2, thickness // 2 + 1):
                for ty in range(-thickness // 2, thickness // 2 + 1):
                    set_pixel(x0 + tx, y0 + ty)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    strokes = [
        (40, 78, 110, 42),
        (110, 42, 150, 80),
        (150, 80, 210, 35),
        (210, 35, 265, 76),
        (265, 76, 330, 48),
        (330, 48, 385, 70),
        (58, 90, 355, 90),
    ]
    for stroke in strokes:
        draw_line(*stroke)

    raw = b"".join(
        b"\x00" + bytes(pixels[row * width * 4:(row + 1) * width * 4])
        for row in range(height)
    )
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(raw, 9))
        + _png_chunk(b"IEND", b"")
    )


TEST_FACSIMILE_PNG_BYTES = _visible_test_facsimile_png()


class LocalContractCloud:
    def __init__(self, output_dir, read_roots):
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.read_roots = [Path(path).expanduser().resolve() for path in read_roots]
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
        return self._path_under_root(self.output_dir, cloud_path)

    def _path_under_root(self, root, cloud_path):
        normalized = self._normalize_cloud_path(cloud_path)
        parts = [part for part in normalized.strip("/").split("/") if part]
        return root.joinpath(*parts)

    def download_file(self, _user, cloud_path):
        for root in [self.output_dir, *self.read_roots]:
            local_path = self._path_under_root(root, cloud_path)
            if local_path.exists() and local_path.is_file():
                return (
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    local_path.read_bytes(),
                )
        roots = ", ".join(str(root) for root in [self.output_dir, *self.read_roots])
        raise RuntimeError(f"Не найден локальный DOCX для {cloud_path}. Проверенные корни: {roots}")

    def upload_file(self, _user, cloud_path, data, *, overwrite=True):
        local_path = self.local_path(cloud_path)
        if local_path.exists() and not overwrite:
            return False
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(data)
        self.uploaded_files.append((cloud_path, local_path))
        return True

    def publish_resource(self, _user, _cloud_path):
        self._published_counter += 1
        return f"https://local.contract.test/signed/{self._published_counter}"


class Command(BaseCommand):
    help = (
        "Локально воспроизводит кнопку «Подписать договор» из таблицы "
        "«Подписание договора» для выбранных Performer ID."
    )

    def add_arguments(self, parser):
        parser.add_argument("performer_ids", nargs="*", type=int, help="ID строк из таблицы подписания договора")
        parser.add_argument("--user-id", type=int, help="ID пользователя, от имени которого выполнить подписание")
        parser.add_argument("--username", help="Username пользователя, от имени которого выполнить подписание")
        parser.add_argument(
            "--output-dir",
            default="tmp/contract-signing-local",
            help="Куда сохранить локально созданный signed PDF (по умолчанию: tmp/contract-signing-local)",
        )
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Не откатывать изменения Performer/уведомлений в БД после локального прогона",
        )
        parser.add_argument(
            "--use-onlyoffice",
            action="store_true",
            help="Использовать реальную ONLYOFFICE-конвертацию вместо локального LibreOffice",
        )
        parser.add_argument(
            "--fake-pdf",
            action="store_true",
            help="Создать минимальный тестовый PDF без конвертации DOCX (только smoke-test flow)",
        )
        parser.add_argument(
            "--docx-root-dir",
            action="append",
            default=[],
            help=(
                "Локальный корень, где искать ранее созданный DOCX по cloud path. "
                "Можно передать несколько раз. По умолчанию проверяются tmp/contract-project-local-test "
                "и tmp/contract-project-local."
            ),
        )
        parser.add_argument(
            "--skip-facsimile-check",
            action="store_true",
            help="Не требовать реальное факсимиле исполнителя; для локальной конвертации вставляется тестовая PNG-подпись",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="Показать строки, похожие на доступные для подписания, и выйти",
        )
        parser.add_argument("--limit", type=int, default=30, help="Сколько строк показать для --list")

    def handle(self, *args, **options):
        if options["list"]:
            self._print_available_performers(options["limit"])
            return

        performer_ids = options["performer_ids"]
        if not performer_ids:
            raise CommandError("Передайте хотя бы один Performer ID или используйте --list.")
        if options["use_onlyoffice"] and options["fake_pdf"]:
            raise CommandError("Флаги --use-onlyoffice и --fake-pdf нельзя использовать одновременно.")

        user = self._get_user(options)
        docx_roots = options["docx_root_dir"] or [
            "tmp/contract-project-local-test",
            "tmp/contract-project-local",
        ]
        local_cloud = LocalContractCloud(options["output_dir"], docx_roots)
        request = RequestFactory().post(
            "/projects/performers/sign-performer-contract/",
            data={"performer_ids[]": [str(pk) for pk in performer_ids]},
            HTTP_HOST="localhost",
        )
        request.user = user

        from projects_app import views as project_views

        patches = [
            patch.object(project_views, "cloud_upload_file", side_effect=local_cloud.upload_file),
            patch.object(project_views, "cloud_publish_resource", side_effect=local_cloud.publish_resource),
            patch.object(project_views, "cloud_download_file", side_effect=local_cloud.download_file),
            patch.object(project_views, "_resolve_contract_project_nextcloud_file_id", return_value=""),
            patch.object(project_views, "_get_contract_cloud_user", return_value=user),
        ]
        if options["fake_pdf"]:
            patches.extend(
                [
                    patch.object(project_views, "is_onlyoffice_conversion_configured", return_value=True),
                    patch.object(project_views, "convert_docx_source_to_pdf", return_value=MINIMAL_PDF_BYTES),
                ]
            )
        elif not options["use_onlyoffice"]:
            patches.extend(
                [
                    patch.object(project_views, "is_onlyoffice_conversion_configured", return_value=True),
                    patch.object(
                        project_views,
                        "convert_docx_source_to_pdf",
                        side_effect=self._local_libreoffice_converter(project_views, user),
                    ),
                ]
            )
        if options["skip_facsimile_check"]:
            patches.append(patch.object(project_views, "_load_performer_facsimile_bytes", return_value=TEST_FACSIMILE_PNG_BYTES))

        with self._combined_patches(patches), override_settings(ALLOWED_HOSTS=["localhost", "testserver", "*"]):
            with transaction.atomic():
                response = project_views.sign_performer_contract_documents(request)
                data = self._response_json(response)
                if not options["commit"] or not data.get("ok"):
                    transaction.set_rollback(True)

        if not data.get("ok"):
            raise CommandError(data.get("error") or "View не вернул успешный статус.")

        self.stdout.write(self.style.SUCCESS(data.get("message") or "Подписанный договор сформирован."))
        self.stdout.write(f"Сформировано групп: {data.get('generated', 0)}")
        for warning in data.get("warnings") or []:
            self.stdout.write(self.style.WARNING(f"Предупреждение: {warning}"))

        if local_cloud.uploaded_files:
            self.stdout.write("Созданные файлы:")
            for _cloud_path, local_path in local_cloud.uploaded_files:
                self.stdout.write(f"  {local_path}")
        else:
            self.stdout.write(self.style.WARNING("PDF-файлы не были записаны. Проверьте ошибки и исходные строки."))

        if not options["commit"]:
            self.stdout.write("Изменения в БД откатаны. Для сохранения полей Performer добавьте --commit.")

    def _local_libreoffice_converter(self, project_views, user):
        soffice = self._find_soffice()

        def _convert(*, source_url: str, source_name: str = "contract.docx"):
            match = re.search(r"/contract-docx-source/(\d+)/", str(source_url or ""))
            if not match:
                raise RuntimeError(f"Не удалось определить Performer ID из source_url: {source_url}")
            performer = Performer.objects.get(pk=int(match.group(1)))
            docx_bytes = project_views._load_existing_contract_docx_bytes(user, performer)
            docx_bytes = project_views._prepare_contract_docx_for_pdf(
                docx_bytes,
                performer,
                include_performer_facsimile=True,
            )
            return self._convert_docx_bytes_with_libreoffice(soffice, docx_bytes, source_name)

        return _convert

    def _find_soffice(self):
        candidates = [
            shutil.which("soffice"),
            shutil.which("libreoffice"),
            "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        ]
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return candidate
        raise CommandError(
            "LibreOffice/soffice не найден. Установите LibreOffice, передайте --use-onlyoffice "
            "для реальной ONLYOFFICE-конвертации или --fake-pdf только для smoke-test."
        )

    def _convert_docx_bytes_with_libreoffice(self, soffice, docx_bytes, source_name):
        source_stem = Path(str(source_name or "contract.docx")).stem or "contract"
        with tempfile.TemporaryDirectory(prefix="contract-signing-") as tmp_dir:
            tmp_path = Path(tmp_dir)
            docx_path = tmp_path / f"{source_stem}.docx"
            docx_path.write_bytes(docx_bytes)
            result = subprocess.run(
                [
                    soffice,
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(tmp_path),
                    str(docx_path),
                ],
                cwd=str(tmp_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=120,
                check=False,
            )
            pdf_path = tmp_path / f"{source_stem}.pdf"
            if result.returncode != 0 or not pdf_path.exists():
                stdout = result.stdout.decode("utf-8", errors="replace").strip()
                stderr = result.stderr.decode("utf-8", errors="replace").strip()
                raise RuntimeError(
                    "LibreOffice не смог сконвертировать DOCX в PDF. "
                    f"stdout={stdout} stderr={stderr}"
                )
            return pdf_path.read_bytes()

    def _get_user(self, options):
        User = get_user_model()
        from policy_app.models import ADMIN_GROUP, EXPERT_GROUP

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

        user = (
            User.objects
            .filter(is_staff=True)
            .filter(groups__name__in=[ADMIN_GROUP, EXPERT_GROUP])
            .order_by("-is_superuser", "id")
            .first()
        )
        if not user:
            user = User.objects.filter(is_staff=True).order_by("-is_superuser", "id").first()
        if not user:
            raise CommandError("Не найден staff-пользователь. Передайте --username или --user-id.")
        return user

    def _response_json(self, response):
        payload = response.content.decode("utf-8").strip()
        if not payload:
            return {"ok": False, "error": "Пустой ответ view."}
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise CommandError(f"View вернул не JSON: {payload[:200]}") from exc

    def _print_available_performers(self, limit):
        rows = (
            Performer.objects
            .select_related("registration", "employee")
            .exclude(contract_file="")
            .exclude(contract_project_disk_folder="")
            .order_by("registration_id", "executor", "position", "id")[:limit]
        )
        if not rows:
            self.stdout.write("Нет строк Performer с DOCX и папкой договора.")
            return

        self.stdout.write("Строки с DOCX и папкой договора:")
        for performer in rows:
            project = performer.registration
            project_label = getattr(project, "short_uid", "") or getattr(project, "formatted_number", "") or "-"
            sent = "sent" if performer.contract_sent_at else "not-sent"
            signed = "signed" if performer.contract_signed_pdf_file else "unsigned"
            self.stdout.write(
                f"  {performer.pk}: {project_label} | {performer.executor or '-'} | {sent} | {signed} | {performer.contract_file}"
            )

    class _combined_patches:
        def __init__(self, patches):
            self.patches = patches
            self.started = []

        def __enter__(self):
            for patcher in self.patches:
                self.started.append(patcher)
                patcher.__enter__()
            return self

        def __exit__(self, exc_type, exc, tb):
            for patcher in reversed(self.started):
                patcher.__exit__(exc_type, exc, tb)
            return False
