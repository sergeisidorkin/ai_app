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

# CI can import this module through either `proposals_app.document_generation`
# or `ai_app.proposals_app.document_generation`. Keep both names bound to the
# same module object so patch() targets stay stable.
sys.modules.setdefault("proposals_app.document_generation", sys.modules[__name__])
sys.modules.setdefault("ai_app.proposals_app.document_generation", sys.modules[__name__])


def ensure_proposal_documents_root() -> Path:
    root = Path(settings.MEDIA_ROOT) / PROPOSAL_DOCUMENTS_SUBDIR
    root.mkdir(parents=True, exist_ok=True)
    return root


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
    if docx_name:
        pdf_name = f"{Path(docx_name).stem}.pdf"
    else:
        pdf_name = f"{build_proposal_document_base_name(proposal)}.pdf"

    workspace_root = workspace_path.rstrip("/")
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


def build_proposal_docx_source_token(proposal) -> str:
    payload = {
        "proposal_id": int(proposal.pk),
        "docx_file_name": str(getattr(proposal, "docx_file_name", "") or "").strip(),
        "docx_file_link": str(getattr(proposal, "docx_file_link", "") or "").strip(),
    }
    return signing.dumps(payload, salt=PROPOSAL_DOCX_SOURCE_TOKEN_SALT, compress=True)


def is_valid_proposal_docx_source_token(proposal, token: str) -> bool:
    try:
        payload = signing.loads(
            str(token or "").strip(),
            salt=PROPOSAL_DOCX_SOURCE_TOKEN_SALT,
            max_age=_proposal_docx_source_token_ttl(),
        )
    except signing.BadSignature:
        return False

    return (
        payload.get("proposal_id") == proposal.pk
        and payload.get("docx_file_name") == str(getattr(proposal, "docx_file_name", "") or "").strip()
        and payload.get("docx_file_link") == str(getattr(proposal, "docx_file_link", "") or "").strip()
    )


def build_proposal_docx_source_url(request, proposal) -> str:
    token = build_proposal_docx_source_token(proposal)
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
        request_payload = {"token": jwt.encode(payload, jwt_secret, algorithm="HS256")}
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


def load_existing_proposal_docx_bytes(user, proposal) -> bytes:
    docx_name = str(getattr(proposal, "docx_file_name", "") or "").strip()
    if not docx_name:
        raise RuntimeError("Для ТКП не указан DOCX-файл.")

    local_docx_path = get_generated_docx_path(proposal)
    if local_docx_path and local_docx_path.exists():
        return local_docx_path.read_bytes()

    raw_link = str(getattr(proposal, "docx_file_link", "") or "").strip()
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


def generate_and_store_proposal_pdf(user, proposal, *, source_url: str) -> dict[str, str]:
    source_name = str(getattr(proposal, "docx_file_name", "") or "").strip() or "proposal.docx"
    pdf_bytes = convert_docx_source_to_pdf(source_url=source_url, source_name=source_name)
    return store_generated_pdf_document(user, proposal, pdf_bytes)


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
