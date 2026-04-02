from __future__ import annotations

import os
import posixpath
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote

from django.conf import settings

from core.cloud_storage import sanitize_folder_name


PROPOSAL_DOCUMENTS_SUBDIR = "proposal_documents"


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


def convert_docx_bytes_to_pdf(docx_bytes: bytes, *, source_name: str = "proposal.docx") -> bytes:
    soffice = shutil.which("soffice")
    if not soffice:
        raise RuntimeError("На сервере не найден LibreOffice (soffice) для генерации PDF.")

    with tempfile.TemporaryDirectory(prefix="proposal-pdf-") as tmpdir:
        tmp_path = Path(tmpdir)
        source_path = tmp_path / (Path(source_name).stem + ".docx")
        source_path.write_bytes(docx_bytes)

        proc = subprocess.run(
            [
                soffice,
                "--headless",
                "--convert-to",
                "pdf:writer_pdf_Export",
                "--outdir",
                str(tmp_path),
                str(source_path),
            ],
            capture_output=True,
            text=True,
            timeout=90,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            if detail:
                raise RuntimeError(f"Не удалось сгенерировать PDF: {detail}")
            raise RuntimeError("Не удалось сгенерировать PDF.")

        pdf_path = source_path.with_suffix(".pdf")
        if not pdf_path.exists():
            generated = sorted(tmp_path.glob("*.pdf"))
            if generated:
                pdf_path = generated[0]
        if not pdf_path.exists():
            raise RuntimeError("LibreOffice не создал PDF-файл.")

        return pdf_path.read_bytes()


def store_generated_documents(proposal, docx_bytes: bytes, pdf_bytes: bytes | None = None) -> dict[str, str]:
    paths = build_proposal_documents_paths(proposal)
    Path(paths["docx_path"]).write_bytes(docx_bytes)
    result = {
        "docx_name": str(paths["docx_name"]),
        "docx_url": str(paths["docx_url"]),
        "output_dir": str(paths["output_dir"]),
    }
    if pdf_bytes is not None:
        Path(paths["pdf_path"]).write_bytes(pdf_bytes)
        result["pdf_name"] = str(paths["pdf_name"])
        result["pdf_url"] = str(paths["pdf_url"])
    else:
        pdf_path = Path(paths["pdf_path"])
        if pdf_path.exists():
            pdf_path.unlink()
        result["pdf_name"] = ""
        result["pdf_url"] = ""
    return result
