"""
Process a .docx template: replace ``{{variable}}`` placeholders with values.

Handles the common Word issue where a single placeholder like ``{{inn}}``
is split across multiple XML runs (e.g. run1="{{", run2="inn", run3="}}").
"""

from __future__ import annotations

import re
from io import BytesIO

from docx import Document


_PLACEHOLDER_RE = re.compile(r"\{\{[a-zA-Z][a-zA-Z0-9_]*\}\}")


def _replace_in_paragraph(paragraph, replacements: dict[str, str]) -> None:
    """Replace placeholders in a single paragraph, handling split runs."""
    full_text = "".join(run.text for run in paragraph.runs)
    if not _PLACEHOLDER_RE.search(full_text):
        return

    new_text = full_text
    for key, value in replacements.items():
        if key in new_text:
            new_text = new_text.replace(key, value)

    if new_text == full_text:
        return

    runs = paragraph.runs
    if not runs:
        return

    # Preserve formatting of the first run; clear the rest.
    runs[0].text = new_text
    for run in runs[1:]:
        run.text = ""


def _process_paragraphs(paragraphs, replacements: dict[str, str]) -> None:
    for para in paragraphs:
        _replace_in_paragraph(para, replacements)


def _process_tables(tables, replacements: dict[str, str]) -> None:
    for table in tables:
        for row in table.rows:
            for cell in row.cells:
                _process_paragraphs(cell.paragraphs, replacements)
                _process_tables(cell.tables, replacements)


def process_template(file_bytes: bytes, replacements: dict[str, str]) -> bytes:
    """Return modified .docx bytes with all placeholders substituted.

    *file_bytes*: raw bytes of the source .docx template.
    *replacements*: mapping ``{"{{key}}": "value", ...}``.
    """
    if not replacements:
        return file_bytes

    doc = Document(BytesIO(file_bytes))

    _process_paragraphs(doc.paragraphs, replacements)
    _process_tables(doc.tables, replacements)

    for section in doc.sections:
        for header_footer in (section.header, section.footer,
                              section.first_page_header, section.first_page_footer,
                              section.even_page_header, section.even_page_footer):
            if header_footer and header_footer.is_linked_to_previous:
                continue
            if header_footer:
                _process_paragraphs(header_footer.paragraphs, replacements)
                _process_tables(header_footer.tables, replacements)

    out = BytesIO()
    doc.save(out)
    return out.getvalue()
