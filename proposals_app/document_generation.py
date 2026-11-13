from __future__ import annotations

import hashlib
import posixpath
import sys
from types import SimpleNamespace
from pathlib import Path
from urllib.parse import quote, urlencode

import jwt
import requests
from django.conf import settings
from django.core import signing
from django.urls import reverse

from core.cloud_storage import (
    CloudStorageNotReadyError,
    download_file as cloud_download_file,
    get_any_connected_service_user,
    is_nextcloud_primary,
    sanitize_folder_name,
    upload_file as cloud_upload_file,
)


PROPOSAL_DOCUMENTS_SUBDIR = "proposal_documents"
PROPOSAL_DOCX_SOURCE_TOKEN_SALT = "proposals_app.proposal_docx_source"
DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
LOCAL_PROPOSAL_PATH_PREFIX = "local:"

# CI can import this module through either `proposals_app.document_generation`
# or `ai_app.proposals_app.document_generation`. Keep both names bound to the
# same module object so patch() targets stay stable.
sys.modules.setdefault("proposals_app.document_generation", sys.modules[__name__])
sys.modules.setdefault("ai_app.proposals_app.document_generation", sys.modules[__name__])


class LocalProposalFolderError(Exception):
    """Путь локальной папки нельзя использовать для генерации ТКП."""


def local_proposal_folder_enabled() -> bool:
    return bool(getattr(settings, "PROPOSAL_ALLOW_LOCAL_FOLDER", False))


def local_proposal_folder_placeholder() -> str:
    return str(Path.home() / "Desktop")


def encode_local_proposal_path(path: Path) -> str:
    return f"{LOCAL_PROPOSAL_PATH_PREFIX}{path}"


def parse_local_proposal_path(stored_path: str) -> str:
    raw = stored_path or ""
    if not raw.startswith(LOCAL_PROPOSAL_PATH_PREFIX):
        return ""
    return raw[len(LOCAL_PROPOSAL_PATH_PREFIX):]


def is_local_proposal_path(stored_path: str) -> bool:
    return stored_path.startswith(LOCAL_PROPOSAL_PATH_PREFIX) if stored_path else False


def _local_proposal_roots():
    roots = getattr(settings, "REPORT_CHECK_LOCAL_ROOTS", ()) or ()
    if not roots:
        roots = getattr(settings, "DSH_SORT_LOCAL_ROOTS", ()) or ()
    return roots


def _local_proposal_path_is_allowed(resolved: Path) -> bool:
    for raw in _local_proposal_roots():
        try:
            root = Path(raw).expanduser().resolve()
        except OSError:
            continue
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _normalize_local_folder_text(raw_path) -> str:
    text = str(raw_path or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    return text


def resolve_local_proposal_folder(raw_path) -> Path:
    if not local_proposal_folder_enabled():
        raise LocalProposalFolderError("Локальная папка на этом стенде выключена.")
    text = _normalize_local_folder_text(raw_path)
    if not text:
        raise LocalProposalFolderError("Укажите путь к локальной папке.")
    try:
        resolved = Path(text).expanduser().resolve()
    except OSError as exc:
        raise LocalProposalFolderError(f"Не удалось прочитать путь: {exc}") from exc
    if resolved.exists() and not resolved.is_dir():
        raise LocalProposalFolderError("Укажите путь к папке, а не к файлу.")
    if not _local_proposal_path_is_allowed(resolved):
        raise LocalProposalFolderError(
            "Путь вне разрешённых корней локального тестирования. "
            "Укажите каталог внутри домашней папки пользователя или папки проекта."
        )
    if not resolved.is_dir():
        raise LocalProposalFolderError(f"Папка не найдена: {resolved}")
    return resolved


def resolve_proposal_generation_source(request):
    source_kind = (request.POST.get("source_kind") or "cloud").strip() or "cloud"
    if source_kind not in {"cloud", "local"}:
        source_kind = "cloud"
    if source_kind != "local":
        return "cloud", None
    return "local", resolve_local_proposal_folder(request.POST.get("local_folder_path") or "")


def resolve_stored_local_proposal_file(stored_path: str) -> Path | None:
    if not local_proposal_folder_enabled():
        return None
    raw = parse_local_proposal_path(stored_path)
    if not raw:
        return None
    try:
        path = Path(raw).expanduser().resolve()
    except OSError:
        return None
    if not path.is_file() or not _local_proposal_path_is_allowed(path):
        return None
    return path


def _checked_local_proposal_file(stored_path: str) -> Path:
    if not local_proposal_folder_enabled():
        raise LocalProposalFolderError("Локальная папка на этом стенде выключена.")
    raw = parse_local_proposal_path(stored_path)
    if not raw:
        raise LocalProposalFolderError("Некорректный путь к локальному файлу ТКП.")
    try:
        path = Path(raw).expanduser().resolve()
    except OSError as exc:
        raise LocalProposalFolderError(f"Не удалось прочитать путь: {exc}") from exc
    if not _local_proposal_path_is_allowed(path):
        raise LocalProposalFolderError(
            "Путь вне разрешённых корней локального тестирования. "
            "Укажите каталог внутри домашней папки пользователя или папки проекта."
        )
    if path.exists() and not path.is_file():
        raise LocalProposalFolderError("Укажите путь к файлу, а не к папке.")
    if not path.parent.is_dir():
        raise LocalProposalFolderError(f"Папка не найдена: {path.parent}")
    return path


def _local_file_in_folder(folder: Path, file_name: str) -> Path:
    name = Path(str(file_name or "").replace("\\", "/")).name
    if not name or name in {".", ".."}:
        raise LocalProposalFolderError("Некорректное имя файла ТКП.")
    try:
        path = (Path(folder) / name).resolve()
        path.relative_to(Path(folder).resolve())
    except (OSError, ValueError) as exc:
        raise LocalProposalFolderError("Некорректный путь к локальному файлу ТКП.") from exc
    if not _local_proposal_path_is_allowed(path):
        raise LocalProposalFolderError(
            "Путь вне разрешённых корней локального тестирования. "
            "Укажите каталог внутри домашней папки пользователя или папки проекта."
        )
    return path


def store_generated_documents_locally(
    proposal,
    docx_bytes: bytes,
    folder: Path,
    pdf_bytes: bytes | None = None,
) -> dict[str, str]:
    output_dir = Path(folder).expanduser().resolve()
    base_name = build_proposal_document_base_name(proposal)
    docx_name = f"{base_name}.docx"
    docx_path = _local_file_in_folder(output_dir, docx_name)
    try:
        docx_path.write_bytes(docx_bytes)
    except OSError as exc:
        raise LocalProposalFolderError(f"Не удалось сохранить файл в локальную папку: {exc}") from exc
    result = {
        "docx_name": docx_name,
        "docx_path": encode_local_proposal_path(docx_path),
        "output_dir": str(output_dir),
        "pdf_name": "",
        "pdf_path": "",
    }
    if pdf_bytes is not None:
        pdf_name = f"{base_name}.pdf"
        pdf_path = _local_file_in_folder(output_dir, pdf_name)
        try:
            pdf_path.write_bytes(pdf_bytes)
        except OSError as exc:
            raise LocalProposalFolderError(f"Не удалось сохранить файл в локальную папку: {exc}") from exc
        result["pdf_name"] = pdf_name
        result["pdf_path"] = encode_local_proposal_path(pdf_path)
    return result


def ensure_proposal_documents_root() -> Path:
    root = Path(settings.MEDIA_ROOT) / PROPOSAL_DOCUMENTS_SUBDIR
    root.mkdir(parents=True, exist_ok=True)
    return root


def _proposal_document_version_token(proposal) -> str:
    """Версии одного ТКП ID делят short_uid и рабочую папку, поэтому файл без версии затирает предыдущий."""
    try:
        version = int(getattr(proposal, "version", None) or 1)
    except (TypeError, ValueError):
        version = 1
    return f"v{max(version, 1):02d}"


def build_proposal_document_base_name(proposal) -> str:
    proposal_id = sanitize_folder_name(proposal.short_uid or f"proposal-{proposal.pk}")
    product = ""
    if proposal.type_id:
        product = sanitize_folder_name(proposal.type.short_name or str(proposal.type))
    label = sanitize_folder_name(proposal.name or proposal.customer or "TKP")
    parts = ["ТКП", proposal_id]
    if product:
        parts.append(product)
    if label:
        parts.append(label)
    parts.append(_proposal_document_version_token(proposal))
    return "_".join(part for part in parts if part)


def build_proposal_documents_paths(proposal) -> dict[str, str | Path]:
    root = ensure_proposal_documents_root()
    year_dir = sanitize_folder_name(str(proposal.year) if proposal.year else "Без года")
    proposal_dir = sanitize_folder_name(proposal.short_uid or f"proposal-{proposal.pk}")
    output_dir = root / year_dir / proposal_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    base_name = build_proposal_document_base_name(proposal)
    docx_name = f"{base_name}.docx"
    pdf_name = f"{base_name}.pdf"
    docx_path = output_dir / docx_name
    pdf_path = output_dir / pdf_name

    relative_docx = Path(PROPOSAL_DOCUMENTS_SUBDIR) / year_dir / proposal_dir / docx_name
    relative_pdf = Path(PROPOSAL_DOCUMENTS_SUBDIR) / year_dir / proposal_dir / pdf_name
    media_base = settings.MEDIA_URL.rstrip("/")
    docx_url = media_base + "/" + "/".join(quote(part) for part in relative_docx.parts)
    pdf_url = media_base + "/" + "/".join(quote(part) for part in relative_pdf.parts)

    return {
        "docx_name": docx_name,
        "pdf_name": pdf_name,
        "docx_path": docx_path,
        "pdf_path": pdf_path,
        "docx_url": docx_url,
        "pdf_url": pdf_url,
        "output_dir": output_dir,
    }


def build_proposal_workspace_document_paths(proposal) -> dict[str, str]:
    workspace_path = str(getattr(proposal, "proposal_workspace_disk_path", "") or "").strip()
    if not workspace_path:
        raise RuntimeError("Для ТКП не задана рабочая папка в облачном хранилище.")

    base_name = build_proposal_document_base_name(proposal)
    docx_name = f"{base_name}.docx"
    pdf_name = f"{base_name}.pdf"
    workspace_root = workspace_path.rstrip("/")
    docx_path = posixpath.join(workspace_root, docx_name)
    pdf_path = posixpath.join(workspace_root, pdf_name)

    return {
        "workspace_root": workspace_root,
        "docx_name": docx_name,
        "docx_path": docx_path,
        "pdf_name": pdf_name,
        "pdf_path": pdf_path,
    }


def build_proposal_workspace_pdf_paths(proposal) -> dict[str, str]:
    workspace_path = str(getattr(proposal, "proposal_workspace_disk_path", "") or "").strip()
    if not workspace_path:
        raise RuntimeError("Для ТКП не задана рабочая папка в облачном хранилище.")

    docx_name = str(getattr(proposal, "docx_file_name", "") or "").strip()
    raw_docx_link = str(getattr(proposal, "docx_file_link", "") or "").strip()
    media_url = str(getattr(settings, "MEDIA_URL", "") or "").strip()
    if docx_name:
        pdf_name = f"{Path(docx_name).stem}.pdf"
    else:
        pdf_name = f"{build_proposal_document_base_name(proposal)}.pdf"

    workspace_root = workspace_path.rstrip("/")
    if raw_docx_link and not (media_url and raw_docx_link.startswith(media_url)):
        workspace_root = (posixpath.dirname(raw_docx_link) or workspace_root).rstrip("/")
    pdf_path = posixpath.join(workspace_root, pdf_name)
    return {
        "workspace_root": workspace_root,
        "pdf_name": pdf_name,
        "pdf_path": pdf_path,
    }


def _get_cloud_upload_user(user):
    if is_nextcloud_primary():
        # Nextcloud access uses the service account from settings, so an
        # authenticated Django user is not required for server-to-server reads.
        return user or SimpleNamespace(username="nextcloud-system")
    from yandexdisk_app.models import YandexDiskAccount

    if user is not None and YandexDiskAccount.objects.filter(user=user, access_token__gt="").exists():
        return user
    try:
        return get_any_connected_service_user()
    except CloudStorageNotReadyError as exc:
        raise RuntimeError(str(exc)) from exc


def get_generated_docx_path(proposal) -> Path | None:
    stored_link = str(getattr(proposal, "docx_file_link", "") or "")
    if is_local_proposal_path(stored_link):
        return resolve_stored_local_proposal_file(stored_link)
    if not proposal.docx_file_name:
        return None
    root = ensure_proposal_documents_root()
    year_dir = sanitize_folder_name(str(proposal.year) if proposal.year else "Без года")
    proposal_dir = sanitize_folder_name(proposal.short_uid or f"proposal-{proposal.pk}")
    path = root / year_dir / proposal_dir / proposal.docx_file_name
    if path.exists():
        return path

    # The proposal metadata can be edited after generation, while the document remains
    # in its original folder. Fall back to any matching generated file name.
    matches = sorted(root.rglob(proposal.docx_file_name), key=lambda item: item.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def is_onlyoffice_conversion_configured() -> bool:
    return bool(str(getattr(settings, "ONLYOFFICE_DOCUMENT_SERVER_URL", "") or "").strip())


def _onlyoffice_document_server_url() -> str:
    return str(getattr(settings, "ONLYOFFICE_DOCUMENT_SERVER_URL", "") or "").strip().rstrip("/")


def _onlyoffice_jwt_secret() -> str:
    return str(getattr(settings, "ONLYOFFICE_JWT_SECRET", "") or "").strip()


def _onlyoffice_verify_ssl() -> bool:
    return bool(getattr(settings, "ONLYOFFICE_VERIFY_SSL", True))


def _onlyoffice_timeout() -> int:
    return int(getattr(settings, "ONLYOFFICE_CONVERSION_TIMEOUT", 120) or 120)


def _proposal_docx_source_token_ttl() -> int:
    return int(getattr(settings, "ONLYOFFICE_DOCX_SOURCE_TOKEN_TTL", 300) or 300)


def build_proposal_docx_source_token(proposal, *, signer_user_id: int | None = None) -> str:
    payload = {
        "proposal_id": int(proposal.pk),
        "docx_file_name": str(getattr(proposal, "docx_file_name", "") or "").strip(),
        "docx_file_link": str(getattr(proposal, "docx_file_link", "") or "").strip(),
        "signer_user_id": int(signer_user_id) if signer_user_id else None,
    }
    return signing.dumps(payload, salt=PROPOSAL_DOCX_SOURCE_TOKEN_SALT, compress=True)


def get_proposal_docx_source_token_payload(proposal, token: str) -> dict[str, object] | None:
    try:
        payload = signing.loads(
            str(token or "").strip(),
            salt=PROPOSAL_DOCX_SOURCE_TOKEN_SALT,
            max_age=_proposal_docx_source_token_ttl(),
        )
    except signing.BadSignature:
        return None

    if not (
        payload.get("proposal_id") == proposal.pk
        and payload.get("docx_file_name") == str(getattr(proposal, "docx_file_name", "") or "").strip()
        and payload.get("docx_file_link") == str(getattr(proposal, "docx_file_link", "") or "").strip()
    ):
        return None
    return payload


def is_valid_proposal_docx_source_token(proposal, token: str) -> bool:
    return get_proposal_docx_source_token_payload(proposal, token) is not None


def build_proposal_docx_source_url(request, proposal, *, signer_user_id: int | None = None) -> str:
    token = build_proposal_docx_source_token(proposal, signer_user_id=signer_user_id)
    path = reverse("proposal_onlyoffice_docx_source", args=[proposal.pk])
    query = urlencode({"token": token})
    if request is not None:
        return request.build_absolute_uri(f"{path}?{query}")
    base_url = str(getattr(settings, "BASE_URL", "") or "").strip().rstrip("/")
    if not base_url:
        raise RuntimeError("Не задан BASE_URL для доступа ONLYOFFICE к исходному DOCX.")
    return f"{base_url}{path}?{query}"


def _build_onlyoffice_conversion_key(source_name: str, source_url: str) -> str:
    raw_value = f"{source_name}:{source_url}"
    return hashlib.sha256(raw_value.encode("utf-8")).hexdigest()


def _build_onlyoffice_converter_url(conversion_key: str) -> str:
    base_url = _onlyoffice_document_server_url()
    if not base_url:
        raise RuntimeError("Не настроен ONLYOFFICE Document Server для генерации PDF.")
    return f"{base_url}/converter?{urlencode({'shardkey': conversion_key})}"


def _build_onlyoffice_conversion_payload(*, source_name: str, source_url: str) -> tuple[str, dict[str, object]]:
    file_type = Path(source_name or "proposal.docx").suffix.lower().lstrip(".")
    if not file_type:
        file_type = "docx"
    conversion_key = _build_onlyoffice_conversion_key(source_name, source_url)
    payload = {
        "async": False,
        "filetype": file_type,
        "key": conversion_key,
        "outputtype": "pdf",
        "title": f"{Path(source_name or 'proposal.docx').stem}.pdf",
        "url": source_url,
    }
    return conversion_key, payload


def convert_docx_source_to_pdf(*, source_url: str, source_name: str = "proposal.docx") -> bytes:
    clean_source_url = str(source_url or "").strip()
    if not clean_source_url:
        raise RuntimeError("Не передана ссылка на исходный DOCX для ONLYOFFICE.")

    conversion_key, payload = _build_onlyoffice_conversion_payload(
        source_name=source_name,
        source_url=clean_source_url,
    )
    request_payload: dict[str, object]
    headers = {"Accept": "application/json"}
    jwt_secret = _onlyoffice_jwt_secret()
    if jwt_secret:
        request_payload = dict(payload)
        request_payload["token"] = jwt.encode(payload, jwt_secret, algorithm="HS256")
    else:
        request_payload = payload

    try:
        response = requests.post(
            _build_onlyoffice_converter_url(conversion_key),
            json=request_payload,
            headers=headers,
            timeout=_onlyoffice_timeout(),
            verify=_onlyoffice_verify_ssl(),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"ONLYOFFICE недоступен для генерации PDF: {exc}") from exc

    try:
        response_payload = response.json()
    except ValueError as exc:
        raise RuntimeError("ONLYOFFICE вернул некорректный ответ при генерации PDF.") from exc

    error_code = int(response_payload.get("error") or 0)
    if error_code:
        raise RuntimeError(f"ONLYOFFICE не смог сформировать PDF (код ошибки {error_code}).")

    if not response_payload.get("endConvert") or not response_payload.get("fileUrl"):
        raise RuntimeError("ONLYOFFICE не завершил генерацию PDF.")

    try:
        pdf_response = requests.get(
            str(response_payload["fileUrl"]).strip(),
            timeout=_onlyoffice_timeout(),
            verify=_onlyoffice_verify_ssl(),
        )
        pdf_response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Не удалось скачать PDF из ONLYOFFICE: {exc}") from exc

    pdf_bytes = pdf_response.content or b""
    if not pdf_bytes:
        raise RuntimeError("ONLYOFFICE вернул пустой PDF-файл.")
    return pdf_bytes


def get_generated_pdf_path(proposal) -> Path | None:
    return resolve_stored_local_proposal_file(str(getattr(proposal, "pdf_file_link", "") or ""))


def load_existing_proposal_docx_bytes(user, proposal) -> bytes:
    docx_name = str(getattr(proposal, "docx_file_name", "") or "").strip()
    if not docx_name:
        raise RuntimeError("Для ТКП не указан DOCX-файл.")

    raw_link = str(getattr(proposal, "docx_file_link", "") or "").strip()
    if is_local_proposal_path(raw_link):
        local_path = resolve_stored_local_proposal_file(raw_link)
        if local_path is None:
            raise RuntimeError("Локальная копия DOCX-файла не найдена.")
        return local_path.read_bytes()

    local_docx_path = get_generated_docx_path(proposal)
    if local_docx_path and local_docx_path.exists():
        return local_docx_path.read_bytes()

    if not raw_link:
        raise RuntimeError("Для ТКП не задан путь к DOCX-файлу.")

    media_url = str(getattr(settings, "MEDIA_URL", "") or "").strip()
    if media_url and raw_link.startswith(media_url):
        relative_path = raw_link[len(media_url):].lstrip("/")
        local_media_path = Path(settings.MEDIA_ROOT) / relative_path
        if local_media_path.exists():
            return local_media_path.read_bytes()
        raise RuntimeError("Локальная копия DOCX-файла не найдена.")

    cloud_user = _get_cloud_upload_user(user)
    if not cloud_user:
        raise RuntimeError("Не найден пользователь с подключенным облачным хранилищем для чтения DOCX.")

    _mime_type, docx_bytes = cloud_download_file(cloud_user, raw_link)
    if docx_bytes:
        return docx_bytes
    raise RuntimeError("Не удалось получить DOCX из рабочего пространства ТКП.")


def store_generated_pdf_document(user, proposal, pdf_bytes: bytes) -> dict[str, str]:
    raw_docx_link = str(getattr(proposal, "docx_file_link", "") or "").strip()
    if is_local_proposal_path(raw_docx_link):
        docx_path = _checked_local_proposal_file(raw_docx_link)
        docx_name = str(getattr(proposal, "docx_file_name", "") or "").strip() or docx_path.name
        pdf_name = f"{Path(docx_name).stem}.pdf"
        pdf_path = _local_file_in_folder(docx_path.parent, pdf_name)
        try:
            pdf_path.write_bytes(pdf_bytes)
        except OSError as exc:
            raise LocalProposalFolderError(f"Не удалось сохранить файл в локальную папку: {exc}") from exc
        return {
            "pdf_name": pdf_name,
            "pdf_path": encode_local_proposal_path(pdf_path),
            "output_dir": str(docx_path.parent),
        }

    paths = build_proposal_workspace_pdf_paths(proposal)
    cloud_user = _get_cloud_upload_user(user)
    if not cloud_user:
        raise RuntimeError("Не найден пользователь с подключенным облачным хранилищем для загрузки PDF.")
    if not cloud_upload_file(cloud_user, paths["pdf_path"], pdf_bytes):
        raise RuntimeError("Не удалось загрузить PDF в рабочую папку ТКП.")
    return {
        "pdf_name": str(paths["pdf_name"]),
        "pdf_path": str(paths["pdf_path"]),
        "output_dir": str(paths["workspace_root"]),
    }


def convert_docx_bytes_to_pdf_locally(docx_bytes: bytes, *, source_name: str = "proposal.docx") -> bytes:
    """DOCX → PDF через локальный LibreOffice, без ONLYOFFICE."""
    if not docx_bytes:
        raise RuntimeError("Пустой DOCX-файл нельзя конвертировать в PDF.")
    from projects_app.docx_render import DocxRenderError, _render_with_libreoffice, find_soffice

    if not find_soffice():
        raise RuntimeError(
            "LibreOffice (soffice) не найден. Установите LibreOffice для локальной генерации PDF."
        )
    try:
        pdf_bytes = _render_with_libreoffice(docx_bytes, source_name or "proposal.docx")
    except DocxRenderError as exc:
        raise RuntimeError(f"Локальная генерация PDF не удалась: {exc}") from exc
    if not pdf_bytes:
        raise RuntimeError("Локальная генерация PDF вернула пустой файл.")
    return pdf_bytes


def generate_and_store_proposal_pdf(user, proposal, *, source_url: str) -> dict[str, str]:
    source_name = str(getattr(proposal, "docx_file_name", "") or "").strip() or "proposal.docx"
    pdf_bytes = convert_docx_source_to_pdf(source_url=source_url, source_name=source_name)
    return store_generated_pdf_document(user, proposal, pdf_bytes)


def store_existing_proposal_docx_bytes(user, proposal, docx_bytes: bytes) -> dict[str, str]:
    docx_name = str(getattr(proposal, "docx_file_name", "") or "").strip()
    raw_link = str(getattr(proposal, "docx_file_link", "") or "").strip()
    media_url = str(getattr(settings, "MEDIA_URL", "") or "").strip()

    if is_local_proposal_path(raw_link):
        path = _checked_local_proposal_file(raw_link)
        try:
            path.write_bytes(docx_bytes)
        except OSError as exc:
            raise LocalProposalFolderError(f"Не удалось сохранить файл в локальную папку: {exc}") from exc
        return {
            "docx_name": docx_name or path.name,
            "docx_path": encode_local_proposal_path(path),
            "output_dir": str(path.parent),
        }

    if raw_link:
        if media_url and raw_link.startswith(media_url):
            relative_path = raw_link[len(media_url):].lstrip("/")
            local_media_path = Path(settings.MEDIA_ROOT) / relative_path
            local_media_path.parent.mkdir(parents=True, exist_ok=True)
            local_media_path.write_bytes(docx_bytes)
            return {
                "docx_name": docx_name or local_media_path.name,
                "docx_path": raw_link,
                "output_dir": str(local_media_path.parent),
            }

        cloud_user = _get_cloud_upload_user(user)
        if not cloud_user:
            raise RuntimeError("Не найден пользователь с подключенным облачным хранилищем для загрузки DOCX.")
        if not cloud_upload_file(cloud_user, raw_link, docx_bytes):
            raise RuntimeError("Не удалось обновить DOCX в рабочей папке ТКП.")
        return {
            "docx_name": docx_name or posixpath.basename(raw_link),
            "docx_path": raw_link,
            "output_dir": posixpath.dirname(raw_link) or "/",
        }

    return store_generated_documents(user, proposal, docx_bytes, None)


def store_generated_documents(user, proposal, docx_bytes: bytes, pdf_bytes: bytes | None = None) -> dict[str, str]:
    paths = build_proposal_workspace_document_paths(proposal)
    cloud_user = _get_cloud_upload_user(user)
    if not cloud_user:
        raise RuntimeError("Не найден пользователь с подключенным облачным хранилищем для загрузки DOCX.")
    if not cloud_upload_file(cloud_user, paths["docx_path"], docx_bytes):
        raise RuntimeError("Не удалось загрузить DOCX в рабочую папку ТКП.")
    result = {
        "docx_name": str(paths["docx_name"]),
        "docx_path": str(paths["docx_path"]),
        "output_dir": str(paths["workspace_root"]),
    }
    if pdf_bytes is not None:
        if not cloud_upload_file(cloud_user, paths["pdf_path"], pdf_bytes):
            raise RuntimeError("Не удалось загрузить PDF в рабочую папку ТКП.")
        result["pdf_name"] = str(paths["pdf_name"])
        result["pdf_path"] = str(paths["pdf_path"])
    else:
        result["pdf_name"] = ""
        result["pdf_path"] = ""
    return result
