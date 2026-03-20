"""
Process a .docx template: replace ``{{variable}}`` placeholders with values
and ``[[variable]]`` placeholders with bulleted lists.

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
_LIST_PLACEHOLDER_RE = re.compile(r"\[\[[a-zA-Z][a-zA-Z0-9_]*\]\]")


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


def _replace_list_in_paragraph(paragraph, list_replacements: dict[str, list[str]]) -> bool:
    """If the paragraph contains a ``[[list_var]]`` placeholder, replace the
    entire paragraph with a bulleted list of items.  Returns True if replaced.

    Formatting (font, size, bold, italic) is copied from the run containing
    the opening ``[[`` of the placeholder.
    """
    if not list_replacements:
        return False
    runs = paragraph.runs
    if not runs:
        return False
    full_text = "".join(r.text for r in runs)
    m = _LIST_PLACEHOLDER_RE.search(full_text)
    if not m:
        return False
    key = m.group()
    items = list_replacements.get(key)
    if items is None:
        return False

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

    source_run = runs[_run_at(m.start())]
    source_rPr = source_run._element.find(qn("w:rPr"))

    parent = paragraph._element.getparent()
    anchor = paragraph._element

    from docx.oxml import OxmlElement

    for item_text in items:
        new_p = OxmlElement("w:p")
        pPr = OxmlElement("w:pPr")
        numPr = OxmlElement("w:numPr")
        ilvl = OxmlElement("w:ilvl")
        ilvl.set(qn("w:val"), "0")
        numId = OxmlElement("w:numId")
        numId.set(qn("w:val"), "1")
        numPr.append(ilvl)
        numPr.append(numId)
        pPr.append(numPr)
        new_p.append(pPr)

        new_r = OxmlElement("w:r")
        if source_rPr is not None:
            new_r.append(deepcopy(source_rPr))
        new_t = OxmlElement("w:t")
        new_t.set(qn("xml:space"), "preserve")
        new_t.text = item_text
        new_r.append(new_t)
        new_p.append(new_r)

        anchor.addnext(new_p)
        anchor = new_p

    parent.remove(paragraph._element)
    return True


def _ensure_bullet_numbering(doc):
    """Ensure the document has an abstract numbering definition for bullet
    lists (numId=1) so that ``w:numPr`` references work correctly.
    """
    from docx.oxml import OxmlElement

    numbering_part = doc.part.numbering_part
    numbering_elm = numbering_part._element

    for abstract in numbering_elm.findall(qn("w:abstractNum")):
        abs_id = abstract.get(qn("w:abstractNumId"))
        if abs_id == "0":
            return

    abstract_num = OxmlElement("w:abstractNum")
    abstract_num.set(qn("w:abstractNumId"), "0")
    lvl = OxmlElement("w:lvl")
    lvl.set(qn("w:ilvl"), "0")
    num_fmt = OxmlElement("w:numFmt")
    num_fmt.set(qn("w:val"), "bullet")
    lvl.append(num_fmt)
    lvl_text = OxmlElement("w:lvlText")
    lvl_text.set(qn("w:val"), "\u2022")
    lvl.append(lvl_text)
    lvl_jc = OxmlElement("w:lvlJc")
    lvl_jc.set(qn("w:val"), "left")
    lvl.append(lvl_jc)
    pPr = OxmlElement("w:pPr")
    ind = OxmlElement("w:ind")
    ind.set(qn("w:left"), "720")
    ind.set(qn("w:hanging"), "360")
    pPr.append(ind)
    lvl.append(pPr)
    rPr = OxmlElement("w:rPr")
    rFonts = OxmlElement("w:rFonts")
    rFonts.set(qn("w:ascii"), "Symbol")
    rFonts.set(qn("w:hAnsi"), "Symbol")
    rFonts.set(qn("w:hint"), "default")
    rPr.append(rFonts)
    lvl.append(rPr)
    abstract_num.append(lvl)
    numbering_elm.insert(0, abstract_num)

    for num_el in numbering_elm.findall(qn("w:num")):
        if num_el.get(qn("w:numId")) == "1":
            return

    num_el = OxmlElement("w:num")
    num_el.set(qn("w:numId"), "1")
    abstract_ref = OxmlElement("w:abstractNumId")
    abstract_ref.set(qn("w:val"), "0")
    num_el.append(abstract_ref)
    numbering_elm.append(num_el)


def _process_paragraphs(paragraphs, replacements: dict[str, str]) -> None:
    for para in paragraphs:
        _replace_in_paragraph(para, replacements)


def _process_list_paragraphs(
    paragraphs, list_replacements: dict[str, list[str]],
) -> None:
    for para in list(paragraphs):
        _replace_list_in_paragraph(para, list_replacements)


def _process_tables(
    tables,
    replacements: dict[str, str],
    list_replacements: dict[str, list[str]] | None = None,
) -> None:
    for table in tables:
        for row in table.rows:
            for cell in row.cells:
                if list_replacements:
                    _process_list_paragraphs(cell.paragraphs, list_replacements)
                _process_paragraphs(cell.paragraphs, replacements)
                _process_tables(cell.tables, replacements, list_replacements)


def process_template(
    file_bytes: bytes,
    replacements: dict[str, str],
    list_replacements: dict[str, list[str]] | None = None,
) -> bytes:
    """Return modified .docx bytes with all placeholders substituted.

    *file_bytes*: raw bytes of the source .docx template.
    *replacements*: mapping ``{"{{key}}": "value", ...}``.
    *list_replacements*: mapping ``{"[[key]]": ["item1", ...], ...}``.
    """
    if not replacements and not list_replacements:
        return file_bytes

    doc = Document(BytesIO(file_bytes))

    if list_replacements:
        try:
            _ensure_bullet_numbering(doc)
        except Exception:
            pass
        _process_list_paragraphs(doc.paragraphs, list_replacements)

    _process_paragraphs(doc.paragraphs, replacements)
    _process_tables(doc.tables, replacements, list_replacements)

    for section in doc.sections:
        for header_footer in (section.header, section.footer,
                              section.first_page_header, section.first_page_footer,
                              section.even_page_header, section.even_page_footer):
            if header_footer and header_footer.is_linked_to_previous:
                continue
            if header_footer:
                if list_replacements:
                    _process_list_paragraphs(
                        header_footer.paragraphs, list_replacements,
                    )
                _process_paragraphs(header_footer.paragraphs, replacements)
                _process_tables(
                    header_footer.tables, replacements, list_replacements,
                )

    out = BytesIO()
    doc.save(out)
    return out.getvalue()
