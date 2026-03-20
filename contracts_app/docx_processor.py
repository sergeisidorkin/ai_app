"""
Process a .docx template: replace ``{{variable}}`` placeholders with values.

Handles the common Word issue where a single placeholder like ``{{inn}}``
is split across multiple XML runs (e.g. run1="{{", run2="inn", run3="}}").

Replacement text inherits the formatting of the run that contains the
opening ``{{`` of the placeholder, so bold/italic/font/size are preserved.
"""

from __future__ import annotations

import re
from copy import deepcopy
from io import BytesIO

from docx import Document
from docx.oxml.ns import qn


_PLACEHOLDER_RE = re.compile(r"\{\{[a-zA-Z][a-zA-Z0-9_]*\}\}")


def _replace_in_paragraph(paragraph, replacements: dict[str, str]) -> None:
    """Replace placeholders in a single paragraph, preserving run formatting.

    The algorithm:
    1. Build a mapping from character offset → run index.
    2. Find each placeholder span in the joined text.
    3. For each match, identify which runs it spans.
    4. Put the replacement value into the run where ``{{`` starts
       (preserving that run's formatting), then trim/clear the other
       runs that were consumed by the placeholder.
    """
    runs = paragraph.runs
    if not runs:
        return

    full_text = "".join(r.text for r in runs)
    if not _PLACEHOLDER_RE.search(full_text):
        return

    run_texts = [r.text for r in runs]
    run_starts: list[int] = []
    offset = 0
    for t in run_texts:
        run_starts.append(offset)
        offset += len(t)

    def _run_at(char_pos: int) -> int:
        for i in range(len(run_starts) - 1, -1, -1):
            if char_pos >= run_starts[i]:
                return i
        return 0

    matches = list(_PLACEHOLDER_RE.finditer(full_text))
    if not matches:
        return

    for m in reversed(matches):
        key = m.group()
        value = replacements.get(key)
        if value is None:
            continue

        start, end = m.start(), m.end()
        first_run_idx = _run_at(start)
        last_run_idx = _run_at(end - 1)

        if first_run_idx == last_run_idx:
            local_start = start - run_starts[first_run_idx]
            local_end = end - run_starts[first_run_idx]
            t = run_texts[first_run_idx]
            run_texts[first_run_idx] = t[:local_start] + value + t[local_end:]
        else:
            ft = run_texts[first_run_idx]
            local_start = start - run_starts[first_run_idx]
            run_texts[first_run_idx] = ft[:local_start] + value

            lt = run_texts[last_run_idx]
            local_end = end - run_starts[last_run_idx]
            run_texts[last_run_idx] = lt[local_end:]

            for mid in range(first_run_idx + 1, last_run_idx):
                run_texts[mid] = ""

    for i, run in enumerate(runs):
        run.text = run_texts[i]


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
