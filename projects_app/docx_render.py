"""DOCX → PDF rendering for the visual line layout of report checks.

Two renderers:

* ONLYOFFICE Document Server (production). The server downloads the DOCX
  from this application, so the bytes are parked in a private directory and
  served once through a signed, short-lived URL.
* LibreOffice headless (development, servers without ONLYOFFICE).

REPORT_LAYOUT_RENDERER selects the renderer: ``auto`` (ONLYOFFICE when
configured, else LibreOffice when installed, else the font-metric estimate),
``onlyoffice``, ``libreoffice`` or ``estimate``.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.core import signing
from django.urls import reverse

log = logging.getLogger(__name__)

RENDER_SOURCE_TOKEN_SALT = "projects_app.report_render_docx_source"
RENDER_SOURCE_TTL = 15 * 60
_RENDER_KEY_RE = re.compile(r"^[0-9a-f]{32}$")
_SOFFICE_CANDIDATES = (
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "/usr/bin/soffice",
    "/usr/bin/libreoffice",
    "/usr/lib/libreoffice/program/soffice",
    "/opt/libreoffice/program/soffice",
    "/snap/bin/libreoffice",
)


class DocxRenderError(RuntimeError):
    """A configured renderer failed to produce a PDF."""


def renderer_mode() -> str:
    value = str(getattr(settings, "REPORT_LAYOUT_RENDERER", "auto") or "auto").strip().lower()
    if value in ("", "none", "off", "metrics"):
        return "estimate"
    return value


def render_docx_to_pdf(docx_bytes: bytes, *, file_name: str = "", on_start=None) -> bytes | None:
    """PDF of the document, or None when no renderer is configured.

    ``on_start(name)`` is called right before a renderer runs.
    Raises DocxRenderError when a renderer is configured but failed.
    """
    mode = renderer_mode()
    if mode == "estimate":
        return None
    backends = []
    if mode in ("auto", "onlyoffice") and _onlyoffice_available():
        backends.append(("ONLYOFFICE", _render_with_onlyoffice))
    if mode in ("auto", "libreoffice") and find_soffice():
        backends.append(("LibreOffice", _render_with_libreoffice))
    if not backends:
        if mode == "auto":
            return None
        raise DocxRenderError(f"Рендерер «{mode}» не настроен (REPORT_LAYOUT_RENDERER).")
    errors: list[str] = []
    for name, backend in backends:
        if on_start is not None:
            on_start(name)
        try:
            return backend(docx_bytes, file_name or "report.docx")
        except Exception as exc:  # noqa: BLE001 - every backend failure is reported together
            log.warning("Report layout renderer %s failed: %s", name, exc)
            errors.append(f"{name}: {exc}")
    raise DocxRenderError("; ".join(errors))


# --- ONLYOFFICE ---------------------------------------------------------------


def _onlyoffice_available() -> bool:
    from proposals_app.document_generation import is_onlyoffice_conversion_configured

    return is_onlyoffice_conversion_configured()


def _render_with_onlyoffice(docx_bytes: bytes, file_name: str) -> bytes:
    from proposals_app.document_generation import convert_docx_source_to_pdf

    key = store_render_source(docx_bytes)
    try:
        return convert_docx_source_to_pdf(
            source_url=build_render_source_url(key),
            source_name=file_name,
        )
    finally:
        drop_render_source(key)


def render_source_dir() -> Path:
    configured = str(getattr(settings, "REPORT_RENDER_CACHE_DIR", "") or "").strip()
    if configured:
        return Path(configured)
    return Path(tempfile.gettempdir()) / "ai_app_report_render"


def store_render_source(docx_bytes: bytes) -> str:
    """Park the DOCX for the Document Server; returns the key of the file."""
    directory = render_source_dir()
    directory.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    _drop_stale_render_sources(directory)
    key = uuid.uuid4().hex
    target = directory / f"{key}.docx"
    tmp = directory / f"{key}.part"
    tmp.write_bytes(docx_bytes)
    os.replace(tmp, target)
    return key


def load_render_source(key: str) -> bytes | None:
    if not _RENDER_KEY_RE.match(key or ""):
        return None
    path = render_source_dir() / f"{key}.docx"
    try:
        if time.time() - path.stat().st_mtime > RENDER_SOURCE_TTL:
            return None
        return path.read_bytes()
    except OSError:
        return None


def drop_render_source(key: str) -> None:
    if not _RENDER_KEY_RE.match(key or ""):
        return
    try:
        (render_source_dir() / f"{key}.docx").unlink()
    except OSError:
        pass


def _drop_stale_render_sources(directory: Path) -> None:
    deadline = time.time() - RENDER_SOURCE_TTL
    try:
        entries = list(directory.iterdir())
    except OSError:
        return
    for path in entries:
        try:
            if path.suffix in (".docx", ".part") and path.stat().st_mtime < deadline:
                path.unlink()
        except OSError:
            continue


def build_render_source_token(key: str) -> str:
    return signing.dumps({"key": key}, salt=RENDER_SOURCE_TOKEN_SALT, compress=True)


def render_source_token_matches(key: str, token: str) -> bool:
    try:
        payload = signing.loads(
            str(token or "").strip(),
            salt=RENDER_SOURCE_TOKEN_SALT,
            max_age=RENDER_SOURCE_TTL,
        )
    except signing.BadSignature:
        return False
    return isinstance(payload, dict) and payload.get("key") == key


def build_render_source_url(key: str) -> str:
    base_url = str(getattr(settings, "BASE_URL", "") or "").strip().rstrip("/")
    if not base_url:
        raise DocxRenderError("Не задан BASE_URL для доступа ONLYOFFICE к исходному DOCX.")
    path = reverse("report_render_docx_source", args=[key])
    return f"{base_url}{path}?token={quote(build_render_source_token(key), safe='')}"


# --- LibreOffice --------------------------------------------------------------


def find_soffice() -> str:
    configured = str(getattr(settings, "LIBREOFFICE_BINARY", "") or "").strip()
    candidates = [configured, shutil.which("soffice"), shutil.which("libreoffice"), *_SOFFICE_CANDIDATES]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return ""


def _render_with_libreoffice(docx_bytes: bytes, file_name: str) -> bytes:
    soffice = find_soffice()
    if not soffice:
        raise DocxRenderError("LibreOffice (soffice) не найден.")
    timeout = int(getattr(settings, "REPORT_RENDER_TIMEOUT", 180) or 180)
    with tempfile.TemporaryDirectory(prefix="report-render-") as tmp:
        work = Path(tmp)
        source = work / "source.docx"
        source.write_bytes(docx_bytes)
        profile = work / "profile"
        command = [
            soffice,
            "--headless",
            "--norestore",
            "--nologo",
            "--nodefault",
            "--nolockcheck",
            f"-env:UserInstallation={profile.as_uri()}",
            "--convert-to",
            "pdf",
            "--outdir",
            str(work),
            str(source),
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise DocxRenderError(f"LibreOffice не ответил за {timeout} с.") from exc
        except OSError as exc:
            raise DocxRenderError(f"LibreOffice не запустился: {exc}") from exc
        pdf = work / "source.pdf"
        if not pdf.is_file():
            detail = (completed.stderr or completed.stdout or b"").decode("utf-8", "replace").strip()
            raise DocxRenderError(
                "LibreOffice не сконвертировал DOCX в PDF"
                + (f": {detail[-300:]}" if detail else ".")
            )
        return pdf.read_bytes()
