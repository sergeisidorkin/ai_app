from __future__ import annotations

import re
import zipfile
from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO

from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
XMLNS_NS = "http://www.w3.org/2000/xmlns/"
XML_NS = "http://www.w3.org/XML/1998/namespace"
XML_SPACE_ATTR = f"{{{XML_NS}}}space"
XML_WHITESPACE = frozenset(" \t\r\n")
COMMENTS_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
HYPERLINK_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
COMMENTS_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"
DOCUMENT_XML = "word/document.xml"
STYLES_XML = "word/styles.xml"
SETTINGS_XML = "word/settings.xml"
FOOTNOTES_XML = "word/footnotes.xml"
ENDNOTES_XML = "word/endnotes.xml"
COMMENTS_XML = "word/comments.xml"
_DEFAULT_PAGE_WIDTH_TWIPS = 11906
_DEFAULT_MARGIN_TWIPS = 1440
_HF_KINDS = ("default", "first", "even")
NOTE_SKIP_TYPES = {"separator", "continuationSeparator", "continuationNotice"}
COMMENTS_RELS = "word/_rels/comments.xml.rels"
DOCUMENT_RELS = "word/_rels/document.xml.rels"
CONTENT_TYPES = "[Content_Types].xml"
COMMENT_REL_TYPES = {
    COMMENTS_REL_TYPE,
    "http://schemas.microsoft.com/office/2011/relationships/commentsExtended",
    "http://schemas.microsoft.com/office/2016/09/relationships/commentsIds",
    "http://schemas.microsoft.com/office/2018/08/relationships/commentsExtensible",
}
COMMENT_PART_NAMES = {
    "/word/comments.xml",
    "/word/commentsExtended.xml",
    "/word/commentsIds.xml",
    "/word/commentsExtensible.xml",
}
COMMENT_ZIP_NAMES = {
    "word/comments.xml",
    "word/commentsExtended.xml",
    "word/commentsIds.xml",
    "word/commentsExtensible.xml",
    "word/_rels/comments.xml.rels",
    "word/_rels/commentsExtended.xml.rels",
    "word/_rels/commentsIds.xml.rels",
    "word/_rels/commentsExtensible.xml.rels",
}


def w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


class DocxCommentError(ValueError):
    """DOCX cannot be read or comments cannot be written."""


def extract_document_text(docx_bytes: bytes) -> tuple[str, list[tuple[etree._Element | None, int, int]]]:
    root = _document_root(docx_bytes)
    return _walk_text(root)


def extract_notes(docx_bytes: bytes) -> list[dict]:
    """Footnote/endnote bodies keyed by Word id, for macros that comment on the reference mark."""
    if not docx_bytes or not docx_bytes.startswith(b"PK"):
        return []
    parts = _read_zip(docx_bytes)
    notes = []
    notes.extend(_notes_from_part(parts.get(FOOTNOTES_XML), "footnote"))
    notes.extend(_notes_from_part(parts.get(ENDNOTES_XML), "endnote"))
    try:
        root = etree.fromstring(parts[DOCUMENT_XML]) if DOCUMENT_XML in parts else None
    except etree.XMLSyntaxError:
        root = None
    if root is not None:
        super_ids = _superscript_style_ids(parts.get(STYLES_XML))
        around = _note_ref_around(root, super_ids)
        for note in notes:
            prev_ch, next_ch, prev2_ch, prev_super, next_super = around.get(
                (note.get("kind"), note.get("id")),
                ("", "", "", False, False),
            )
            note["prev_char"] = prev_ch
            note["next_char"] = next_ch
            note["prev2_char"] = prev2_ch
            note["prev_superscript"] = bool(prev_super)
            note["next_superscript"] = bool(next_super)
            note["wrapped_in_angles"] = prev_ch == "<" and next_ch == ">"
    else:
        for note in notes:
            note["prev_char"] = ""
            note["next_char"] = ""
            note["prev2_char"] = ""
            note["prev_superscript"] = False
            note["next_superscript"] = False
            note["wrapped_in_angles"] = False
    return notes


def extract_paragraphs(docx_bytes: bytes) -> list[dict]:
    """Body paragraphs with the same offsets as extract_document_text()."""
    if not docx_bytes or not docx_bytes.startswith(b"PK"):
        return []
    parts = _read_zip(docx_bytes)
    xml = parts.get(DOCUMENT_XML)
    if not xml:
        return []
    try:
        root = etree.fromstring(xml)
    except etree.XMLSyntaxError:
        return []
    names = _paragraph_style_names(parts.get(STYLES_XML))
    catalog = _style_catalog(parts.get(STYLES_XML))
    body = root.find(w("body"))
    if body is None:
        return []
    offset = 0
    paragraphs = []
    for paragraph in body.iter(w("p")):
        start = offset
        chunks: list[str] = []
        for _node, value in _iter_paragraph_plain(paragraph):
            chunks.append(value)
            offset += len(value)
        end = offset
        offset += 1
        p_pr = paragraph.find(w("pPr"))
        style_id = ""
        has_numpr = False
        if p_pr is not None:
            p_style = p_pr.find(w("pStyle"))
            if p_style is not None:
                style_id = p_style.get(w("val")) or ""
            has_numpr = p_pr.find(w("numPr")) is not None
        info = catalog.get(style_id) or {}
        paragraphs.append({
            "start": start,
            "end": end,
            "text": _visible_xml_text(paragraph),
            "style_id": style_id,
            "style_name": info.get("name") or names.get(style_id, ""),
            "aliases": info.get("aliases") or "",
            "has_numpr": has_numpr,
        })
    return paragraphs


def extract_char_runs(docx_bytes: bytes) -> list[dict]:
    """Character-styled runs with the same offsets as extract_document_text()."""
    if not docx_bytes or not docx_bytes.startswith(b"PK"):
        return []
    parts = _read_zip(docx_bytes)
    xml = parts.get(DOCUMENT_XML)
    if not xml:
        return []
    try:
        root = etree.fromstring(xml)
    except etree.XMLSyntaxError:
        return []
    catalog = _style_catalog(parts.get(STYLES_XML))
    body = root.find(w("body"))
    if body is None:
        return []
    offset = 0
    runs: list[dict] = []
    for paragraph in body.iter(w("p")):
        para_start = offset
        by_run: dict[etree._Element, dict] = {}
        order: list[etree._Element] = []
        for node, value in _iter_paragraph_plain(paragraph):
            if node is None:
                offset += len(value)
                continue
            run = node.getparent()
            while run is not None and run.tag != w("r"):
                run = run.getparent()
            start_here = offset
            offset += len(value)
            if run is None or _is_deleted(run):
                continue
            if _closest_paragraph(run) is not paragraph:
                continue
            if run not in by_run:
                style_id = ""
                r_pr = run.find(w("rPr"))
                if r_pr is not None:
                    r_style = r_pr.find(w("rStyle"))
                    if r_style is not None:
                        style_id = r_style.get(w("val")) or ""
                by_run[run] = {
                    "start": start_here,
                    "end": offset,
                    "parts": [value],
                    "style_id": style_id,
                }
                order.append(run)
            else:
                rec = by_run[run]
                rec["end"] = offset
                rec["parts"].append(value)
        for run in order:
            rec = by_run[run]
            style_id = rec["style_id"]
            info = catalog.get(style_id) or {}
            runs.append({
                "start": rec["start"],
                "end": rec["end"],
                "text": "".join(rec["parts"]),
                "style_id": style_id,
                "style_name": info.get("name") or style_id,
                "aliases": info.get("aliases") or "",
                "para_start": para_start,
            })
        offset += 1
    return runs


def _closest_paragraph(node: etree._Element) -> etree._Element | None:
    for ancestor in node.iterancestors():
        if ancestor.tag == w("p"):
            return ancestor
    return None


def extract_tab_offsets(docx_bytes: bytes) -> frozenset[int]:
    """Offsets of w:tab in the same coordinate system as extract_document_text()."""
    if not docx_bytes or not docx_bytes.startswith(b"PK"):
        return frozenset()
    parts = _read_zip(docx_bytes)
    xml = parts.get(DOCUMENT_XML)
    if not xml:
        return frozenset()
    try:
        root = etree.fromstring(xml)
    except etree.XMLSyntaxError:
        return frozenset()
    body = root.find(w("body"))
    if body is None:
        return frozenset()
    offset = 0
    tabs: set[int] = set()
    for paragraph in body.iter(w("p")):
        for node in paragraph.iter():
            if node is paragraph or _is_deleted(node):
                continue
            if node.tag == w("t"):
                value = node.text or ""
                if value:
                    offset += len(value)
            elif node.tag in (w("br"), w("cr")):
                offset += 1
            elif node.tag == w("tab") and _tab_belongs_to_paragraph(node, paragraph):
                tabs.add(offset)
        offset += 1
    return frozenset(tabs)


def _tab_belongs_to_paragraph(node: etree._Element, paragraph: etree._Element) -> bool:
    parent = node.getparent()
    while parent is not None and parent is not paragraph:
        if parent.tag == w("p"):
            return False
        parent = parent.getparent()
    return parent is paragraph


def extract_table_cells(docx_bytes: bytes) -> list[dict]:
    """Table cells with the same paragraph offsets as extract_document_text()."""
    if not docx_bytes or not docx_bytes.startswith(b"PK"):
        return []
    parts = _read_zip(docx_bytes)
    xml = parts.get(DOCUMENT_XML)
    if not xml:
        return []
    try:
        root = etree.fromstring(xml)
    except etree.XMLSyntaxError:
        return []
    body = root.find(w("body"))
    if body is None:
        return []
    offset = 0
    # Key by the lxml node itself: id() of proxies is reused after GC and
    # merges later tables into the previous cell.
    by_cell: dict[etree._Element, dict] = {}
    order: list[etree._Element] = []
    for paragraph in body.iter(w("p")):
        start = offset
        chunks: list[str] = []
        for _node, value in _iter_paragraph_plain(paragraph):
            chunks.append(value)
            offset += len(value)
        end = offset
        offset += 1
        cell = _closest_table_cell(paragraph)
        if cell is None:
            continue
        if cell not in by_cell:
            by_cell[cell] = {"start": start, "end": end, "parts": []}
            order.append(cell)
        rec = by_cell[cell]
        rec["end"] = end
        rec["parts"].append("".join(chunks))
    return [
        {
            "start": by_cell[cell]["start"],
            "end": by_cell[cell]["end"],
            "text": "".join(by_cell[cell]["parts"]),
        }
        for cell in order
    ]


def extract_sections(docx_bytes: bytes) -> list[dict]:
    """Body sections with the same paragraph offsets as extract_document_text()."""
    if not docx_bytes or not docx_bytes.startswith(b"PK"):
        return []
    parts = _read_zip(docx_bytes)
    xml = parts.get(DOCUMENT_XML)
    if not xml:
        return []
    try:
        root = etree.fromstring(xml)
    except etree.XMLSyntaxError:
        return []
    body = root.find(w("body"))
    if body is None:
        return []
    even_odd = _w_on(_settings_even_odd(parts.get(SETTINGS_XML)))
    offset = 0
    section_start = 0
    raw: list[dict] = []
    for paragraph in body.iter(w("p")):
        for _node, value in _iter_paragraph_plain(paragraph):
            offset += len(value)
        offset += 1
        sect = _body_paragraph_sectpr(paragraph)
        if sect is None:
            continue
        raw.append(_section_raw(sect, section_start, offset))
        section_start = offset
    body_sect = body.find(w("sectPr"))
    if body_sect is not None:
        raw.append(_section_raw(body_sect, section_start, offset))
    header_maps = [item["header_refs"] for item in raw]
    footer_maps = [item["footer_refs"] for item in raw]
    sections = []
    for index, item in enumerate(raw):
        headers = {}
        footers = {}
        for kind in _HF_KINDS:
            exists = True if kind == "default" else item["title_pg"] if kind == "first" else even_odd
            headers[kind] = {
                "exists": exists,
                "linked": _hf_linked(index, kind, header_maps),
            }
            footers[kind] = {
                "exists": exists,
                "linked": _hf_linked(index, kind, footer_maps),
            }
        sections.append({
            "start": item["start"],
            "end": item["end"],
            "content_width": item["content_width"],
            "headers": headers,
            "footers": footers,
        })
    return sections


def _settings_even_odd(xml: bytes | None) -> etree._Element | None:
    if not xml:
        return None
    try:
        root = etree.fromstring(xml)
    except etree.XMLSyntaxError:
        return None
    return root.find(w("evenAndOddHeaders"))


def _body_paragraph_sectpr(paragraph: etree._Element) -> etree._Element | None:
    parent = paragraph.getparent()
    if parent is None or parent.tag != w("body"):
        return None
    p_pr = paragraph.find(w("pPr"))
    if p_pr is None:
        return None
    return p_pr.find(w("sectPr"))


def _section_raw(sect: etree._Element, start: int, end: int) -> dict:
    pg_sz = sect.find(w("pgSz"))
    pg_mar = sect.find(w("pgMar"))
    width = _xml_int(pg_sz, "w", _DEFAULT_PAGE_WIDTH_TWIPS)
    left = _xml_int(pg_mar, "left", _DEFAULT_MARGIN_TWIPS)
    right = _xml_int(pg_mar, "right", _DEFAULT_MARGIN_TWIPS)
    return {
        "start": start,
        "end": end,
        "content_width": width - left - right,
        "title_pg": _w_on(sect.find(w("titlePg"))),
        "header_refs": _hf_refs(sect, "headerReference"),
        "footer_refs": _hf_refs(sect, "footerReference"),
    }


def _hf_refs(sect: etree._Element, tag: str) -> dict[str, str]:
    refs: dict[str, str] = {}
    for node in sect.findall(w(tag)):
        kind = node.get(w("type")) or "default"
        rid = node.get(f"{{{R_NS}}}id") or ""
        refs[kind] = rid
    return refs


def _hf_linked(index: int, kind: str, ref_maps: list[dict[str, str]]) -> bool:
    if index <= 0:
        return False
    own = ref_maps[index].get(kind)
    if own is None:
        return True
    prev = None
    for item in reversed(ref_maps[:index]):
        if kind in item:
            prev = item[kind]
            break
    return prev is not None and own == prev


def _w_on(node: etree._Element | None) -> bool:
    if node is None:
        return False
    val = (node.get(w("val")) or "").strip().lower()
    return val not in {"0", "false", "off"}


def _xml_int(node: etree._Element | None, name: str, default: int) -> int:
    if node is None:
        return default
    raw = node.get(w(name))
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _closest_table_cell(paragraph: etree._Element) -> etree._Element | None:
    for ancestor in paragraph.iterancestors():
        if ancestor.tag == w("tc"):
            return ancestor
    return None


def _paragraph_style_names(xml: bytes | None) -> dict[str, str]:
    names: dict[str, str] = {}
    for style_id, info in _style_catalog(xml).items():
        if info.get("type") == "paragraph":
            names[style_id] = info.get("name") or style_id
    return names


def _style_catalog(xml: bytes | None) -> dict[str, dict]:
    if not xml:
        return {}
    try:
        root = etree.fromstring(xml)
    except etree.XMLSyntaxError:
        return {}
    catalog: dict[str, dict] = {}
    for style in root.iter(w("style")):
        style_id = style.get(w("styleId")) or ""
        if not style_id:
            continue
        name_el = style.find(w("name"))
        alias_el = style.find(w("aliases"))
        catalog[style_id] = {
            "type": style.get(w("type")) or "paragraph",
            "name": (name_el.get(w("val")) if name_el is not None else "") or style_id,
            "aliases": (alias_el.get(w("val")) if alias_el is not None else "") or "",
        }
    return catalog


def materialize_symbols(docx_bytes: bytes) -> bytes:
    """Turn Word w:sym glyphs into real w:t characters so macros can see quotes."""
    if not docx_bytes or not docx_bytes.startswith(b"PK"):
        return docx_bytes
    parts = _read_zip(docx_bytes)
    xml = parts.get(DOCUMENT_XML)
    if not xml:
        return docx_bytes
    try:
        root = etree.fromstring(xml)
    except etree.XMLSyntaxError:
        return docx_bytes
    changed = False
    for sym in list(root.iter(w("sym"))):
        char = _sym_char(sym)
        if not char:
            continue
        parent = sym.getparent()
        if parent is None:
            continue
        t_elem = etree.Element(w("t"))
        t_elem.text = char
        _ensure_xml_space_preserve(t_elem)
        parent.replace(sym, t_elem)
        changed = True
    if not changed:
        return docx_bytes
    parts[DOCUMENT_XML] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    return _write_zip(parts)


BROKEN_REF_RESULT = "Ошибка! Источник ссылки не найден."
_REF_BOOKMARK_RE = re.compile(
    r"(?is)^\s*(REF|PAGEREF|NOTEREF)\s+(?:\"([^\"]+)\"|([^\s\\]+))"
)


def update_broken_ref_fields(docx_bytes: bytes) -> bytes:
    """VBA Fields.Update for REF: missing bookmark → «Ошибка! Источник ссылки не найден.»"""
    if not docx_bytes or not docx_bytes.startswith(b"PK"):
        return docx_bytes
    parts = _read_zip(docx_bytes)
    xml = parts.get(DOCUMENT_XML)
    if not xml:
        return docx_bytes
    try:
        bookmarks = _collect_bookmark_names(parts)
        root = etree.fromstring(xml)
    except (etree.XMLSyntaxError, DocxCommentError):
        return docx_bytes
    if not _rewrite_broken_ref_fields(root, bookmarks):
        return docx_bytes
    parts[DOCUMENT_XML] = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    return _write_zip(parts)


def _collect_bookmark_names(parts: dict[str, bytes]) -> set[str]:
    names: set[str] = set()
    for name, data in parts.items():
        if not name.startswith("word/") or not name.endswith(".xml"):
            continue
        if name.startswith("word/_rels/") or name.startswith("word/comments"):
            continue
        try:
            root = etree.fromstring(data)
        except etree.XMLSyntaxError:
            continue
        for mark in root.iter(w("bookmarkStart")):
            value = (mark.get(w("name")) or "").strip()
            if value:
                names.add(value)
    return names


def _rewrite_broken_ref_fields(root: etree._Element, bookmarks: set[str]) -> bool:
    changed = False
    for simple in root.iter(w("fldSimple")):
        if _break_ref_if_missing(simple.get(w("instr")) or "", bookmarks):
            if _set_text_nodes_result(list(simple.iter(w("t"))), simple, BROKEN_REF_RESULT):
                changed = True
    stack: list[dict] = []
    for el in root.iter():
        if el.tag == w("fldChar"):
            kind = (el.get(w("fldCharType")) or "").lower()
            if kind == "begin":
                stack.append({"instr": [], "separated": False, "texts": [], "end": el})
            elif kind == "separate" and stack:
                stack[-1]["separated"] = True
            elif kind == "end" and stack:
                field = stack.pop()
                field["end"] = el
                if any(_field_kind("".join(item["instr"])).startswith("TOC") for item in stack):
                    continue
                instr = "".join(field["instr"])
                if _break_ref_if_missing(instr, bookmarks):
                    if _set_text_nodes_result(field["texts"], el, BROKEN_REF_RESULT):
                        changed = True
        elif el.tag == w("instrText") and stack and not stack[-1]["separated"]:
            stack[-1]["instr"].append(el.text or "")
        elif el.tag == w("t") and stack and stack[-1]["separated"] and not _is_deleted(el):
            stack[-1]["texts"].append(el)
    return changed


def _field_kind(instr: str) -> str:
    parts = (instr or "").split()
    return parts[0].upper() if parts else ""


def extract_ref_fields(docx_bytes: bytes) -> list[dict]:
    """REF field results with the same offsets as extract_document_text()."""
    if not docx_bytes or not docx_bytes.startswith(b"PK"):
        return []
    try:
        root = _document_root(docx_bytes)
    except DocxCommentError:
        return []
    _text, spans = _walk_text(root)
    offsets = {id(node): (start, end) for node, start, end in spans if node is not None}
    collected: list[dict] = []
    for simple in root.iter(w("fldSimple")):
        item = _ref_field_from_nodes(
            simple.get(w("instr")) or "",
            list(simple.iter(w("t"))),
            offsets,
            _visible_xml_text(simple),
        )
        if item:
            collected.append(item)
    stack: list[dict] = []
    for el in root.iter():
        if el.tag == w("fldChar"):
            kind = (el.get(w("fldCharType")) or "").lower()
            if kind == "begin":
                stack.append({"instr": [], "separated": False, "texts": [], "result_parts": []})
            elif kind == "separate" and stack:
                stack[-1]["separated"] = True
            elif kind == "end" and stack:
                field = stack.pop()
                if any(_field_kind("".join(item["instr"])).startswith("TOC") for item in stack):
                    continue
                item = _ref_field_from_nodes(
                    "".join(field["instr"]),
                    field["texts"],
                    offsets,
                    "".join(field["result_parts"]),
                )
                if item:
                    collected.append(item)
        elif el.tag == w("instrText") and stack and not stack[-1]["separated"]:
            stack[-1]["instr"].append(el.text or "")
        elif stack and stack[-1]["separated"] and not _is_deleted(el):
            if el.tag == w("t"):
                stack[-1]["texts"].append(el)
                if el.text:
                    stack[-1]["result_parts"].append(el.text)
            elif el.tag in (w("noBreakHyphen"), w("softHyphen")):
                stack[-1]["result_parts"].append("-")
    body = root.find(w("body"))
    paragraphs: list[tuple[int, int]] = []
    if body is not None:
        offset = 0
        for paragraph in body.iter(w("p")):
            start = offset
            for _node, value in _iter_paragraph_plain(paragraph):
                offset += len(value)
            end = offset
            offset += 1
            paragraphs.append((start, end))
    for item in collected:
        item["para_start"] = item["start"]
        for start, end in paragraphs:
            if start <= item["start"] <= end:
                item["para_start"] = start
                break
    return collected


def _ref_field_from_nodes(instr: str, nodes: list, offsets: dict[int, tuple[int, int]], result: str | None = None) -> dict | None:
    if _field_kind(instr) != "REF":
        return None
    live = [node for node in nodes if node is not None and not _is_deleted(node) and id(node) in offsets]
    if not live:
        return None
    if result is None:
        result = "".join(node.text or "" for node in live)
    return {
        "kind": "REF",
        "result": result,
        "start": min(offsets[id(node)][0] for node in live),
        "end": max(offsets[id(node)][1] for node in live),
    }


def _visible_xml_text(root: etree._Element) -> str:
    """Plain text including Word hyphen glyphs that are not stored in w:t."""
    parts: list[str] = []
    for el in root.iter():
        if _is_deleted(el):
            continue
        if el.tag == w("t"):
            if el.text:
                parts.append(el.text)
        elif el.tag in (w("br"), w("cr")):
            parts.append("\n")
        elif el.tag in (w("noBreakHyphen"), w("softHyphen")):
            parts.append("-")
    return "".join(parts)


def _break_ref_if_missing(instr: str, bookmarks: set[str]) -> bool:
    match = _REF_BOOKMARK_RE.match(instr or "")
    if not match:
        return False
    name = (match.group(2) or match.group(3) or "").strip()
    return bool(name) and name not in bookmarks


def _set_text_nodes_result(nodes: list[etree._Element], anchor: etree._Element, text: str) -> bool:
    live = [node for node in nodes if node.getparent() is not None]
    if live:
        live[0].text = text
        _ensure_xml_space_preserve(live[0])
        for node in live[1:]:
            node.text = ""
        return True
    if anchor is None:
        return False
    new_run = etree.Element(w("r"))
    t_elem = etree.SubElement(new_run, w("t"))
    t_elem.text = text
    _ensure_xml_space_preserve(t_elem)
    if anchor.tag == w("fldSimple"):
        anchor.append(new_run)
        return True
    run = anchor.getparent()
    if run is None:
        return False
    run.addprevious(new_run)
    return True


def _sym_char(sym: etree._Element) -> str:
    raw = (sym.get(w("char")) or "").strip()
    if not raw:
        return ""
    try:
        code = int(raw, 16)
    except ValueError:
        return ""
    if 0xF000 <= code <= 0xF0FF:
        code = code & 0xFF
    if code in (0x22, 0x201C, 0x201D, 0x201E, 0x201F, 0x2033, 0x2036, 0xFF02):
        return chr(code)
    return ""


def insert_comments(docx_bytes: bytes, findings: list[dict]) -> bytes:
    if not findings:
        return docx_bytes
    parts = _read_zip(docx_bytes)
    if DOCUMENT_XML not in parts:
        raise DocxCommentError("В файле нет word/document.xml.")

    doc_root = etree.fromstring(parts[DOCUMENT_XML])
    comments_root, next_id = _load_comments_root(parts.get(COMMENTS_XML))
    rels_root, used_rids, url_to_rid = _load_comments_rels(parts.get(COMMENTS_RELS))
    ordered = sorted(
        (item for item in findings if _valid_finding(item)),
        key=lambda item: (int(item.get("start") or 0), -int(item.get("end") or 0)),
        reverse=True,
    )
    added_hyperlinks = False
    for item in ordered:
        start = int(item.get("start") or 0)
        end = int(item.get("end") or 0)
        message = str(item.get("message") or "").strip()
        author = str(item.get("author") or "Проверка").strip() or "Проверка"
        links = _finding_links(item)
        for link in links:
            if link["url"] not in url_to_rid:
                rid = _next_rid(used_rids)
                used_rids.add(rid)
                url_to_rid[link["url"]] = rid
                _add_hyperlink_rel(rels_root, rid, link["url"])
                added_hyperlinks = True
        if str(item.get("note_id") or "").strip():
            _insert_comment_on_note_ref(
                doc_root,
                str(item.get("note_id")).strip(),
                str(item.get("note_kind") or "footnote").strip() or "footnote",
                next_id,
            )
        else:
            _insert_one_comment(doc_root, start, end, next_id)
        comments_root.append(_comment_element(next_id, author, message, links, url_to_rid))
        next_id += 1

    _preserve_edge_spaces(doc_root)
    parts[DOCUMENT_XML] = etree.tostring(doc_root, xml_declaration=True, encoding="UTF-8", standalone=True)
    parts[COMMENTS_XML] = etree.tostring(comments_root, xml_declaration=True, encoding="UTF-8", standalone=True)
    if added_hyperlinks or COMMENTS_RELS in parts:
        parts[COMMENTS_RELS] = etree.tostring(rels_root, xml_declaration=True, encoding="UTF-8", standalone=True)
    parts[DOCUMENT_RELS] = _ensure_comments_rel(parts.get(DOCUMENT_RELS))
    parts[CONTENT_TYPES] = _ensure_comments_content_type(parts.get(CONTENT_TYPES))
    return _write_zip(parts)


def count_comments(docx_bytes: bytes) -> int:
    """Return the number of Word comments stored in a DOCX package."""
    parts = _read_zip(docx_bytes)
    xml = parts.get(COMMENTS_XML)
    if not xml:
        return 0
    try:
        root = etree.fromstring(xml)
    except etree.XMLSyntaxError as exc:
        raise DocxCommentError("Некорректный word/comments.xml.") from exc
    return len(root.findall(w("comment")))


def strip_comments(docx_bytes: bytes) -> bytes:
    """Remove Word comments and comment markers from a DOCX package."""
    if not docx_bytes or not docx_bytes.startswith(b"PK"):
        return docx_bytes
    parts = _read_zip(docx_bytes)
    if DOCUMENT_XML not in parts:
        return docx_bytes

    changed = False
    for name in list(parts):
        if name in COMMENT_ZIP_NAMES:
            del parts[name]
            changed = True
            continue
        if name.endswith(".rels"):
            cleaned = _strip_comment_rels(parts[name])
            if cleaned != parts[name]:
                parts[name] = cleaned
                changed = True
            continue
        if _is_comment_markup_part(name):
            cleaned = _strip_comment_markup(parts[name])
            if cleaned != parts[name]:
                parts[name] = cleaned
                changed = True

    if CONTENT_TYPES in parts:
        cleaned = _strip_comment_content_types(parts[CONTENT_TYPES])
        if cleaned != parts[CONTENT_TYPES]:
            parts[CONTENT_TYPES] = cleaned
            changed = True

    if not changed:
        return docx_bytes
    return _write_zip(parts)


def _valid_finding(item: dict) -> bool:
    message = str(item.get("message") or "").strip()
    if not message:
        return False
    if str(item.get("note_id") or "").strip():
        return True
    try:
        start = int(item.get("start"))
        end = int(item.get("end"))
    except (TypeError, ValueError):
        return False
    return 0 <= start < end


def _document_root(docx_bytes: bytes) -> etree._Element:
    parts = _read_zip(docx_bytes)
    xml = parts.get(DOCUMENT_XML)
    if not xml:
        raise DocxCommentError("В файле нет word/document.xml.")
    try:
        return etree.fromstring(xml)
    except etree.XMLSyntaxError as exc:
        raise DocxCommentError("Некорректный word/document.xml.") from exc


def _iter_paragraph_plain(paragraph: etree._Element):
    """w:t chunks and Shift+Enter line breaks, in document order."""
    for node in paragraph.iter():
        if node is paragraph or _is_deleted(node):
            continue
        if node.tag == w("t"):
            value = node.text or ""
            if value:
                yield node, value
        elif node.tag in (w("br"), w("cr")):
            yield None, "\n"


def _walk_text(root: etree._Element) -> tuple[str, list[tuple[etree._Element | None, int, int]]]:
    body = root.find(w("body"))
    if body is None:
        return "", []
    spans: list[tuple[etree._Element | None, int, int]] = []
    parts: list[str] = []
    offset = 0
    for paragraph in body.iter(w("p")):
        for node, value in _iter_paragraph_plain(paragraph):
            spans.append((node, offset, offset + len(value)))
            parts.append(value)
            offset += len(value)
        parts.append("\n")
        spans.append((None, offset, offset + 1))
        offset += 1
    return "".join(parts), spans


def _notes_from_part(xml: bytes | None, kind: str) -> list[dict]:
    if not xml:
        return []
    try:
        root = etree.fromstring(xml)
    except etree.XMLSyntaxError:
        return []
    tag = w("footnote") if kind == "footnote" else w("endnote")
    notes = []
    for el in root.findall(tag):
        if (el.get(w("type")) or "") in NOTE_SKIP_TYPES:
            continue
        nid = el.get(w("id"))
        if nid is None:
            continue
        chunks: list[str] = []
        for paragraph in el.iter(w("p")):
            for node in paragraph.iter(w("t")):
                if _is_deleted(node):
                    continue
                value = node.text or ""
                if value:
                    chunks.append(value)
            chunks.append("\n")
        notes.append({
            "id": str(nid),
            "kind": kind,
            "text": "".join(chunks),
            "has_space_tab": _note_has_space_tab(el),
        })
    return notes


def _note_has_space_tab(el: etree._Element) -> bool:
    """True if the note body is «space/nbsp + tab» right after w:footnoteRef."""
    ref_tag = w("footnoteRef") if el.tag == w("footnote") else w("endnoteRef")
    saw_ref = False
    before: list[str] = []
    after: list[str] = []
    for node in el.iter():
        if _is_deleted(node):
            continue
        if node.tag == ref_tag:
            saw_ref = True
            after = []
            continue
        chars: list[str] = []
        if node.tag == w("tab"):
            chars = ["\t"]
        elif node.tag == w("t"):
            chars = list(node.text or "")
        elif node.tag in (w("br"), w("cr")):
            chars = ["\n"]
        elif node.tag in (w("noBreakHyphen"), w("softHyphen")):
            chars = ["-"]
        bucket = after if saw_ref else before
        for ch in chars:
            if len(bucket) >= 2:
                break
            bucket.append(ch)
        if saw_ref and len(after) >= 2:
            break
    prefix = "".join(after if saw_ref else before)
    return prefix[:1] == "\t" or prefix[:2] in (" \t", "\u00a0\t")


def _note_ref_around(
    root: etree._Element,
    super_style_ids: frozenset[str] | None = None,
) -> dict[tuple[str, str], tuple[str, str, str, bool, bool]]:
    body = root.find(w("body"))
    if body is None:
        return {}
    super_style_ids = super_style_ids or frozenset()
    around: dict[tuple[str, str], tuple[str, str, str, bool, bool]] = {}
    for kind, tag in (("footnote", w("footnoteReference")), ("endnote", w("endnoteReference"))):
        for node in body.iter(tag):
            if _is_deleted(node):
                continue
            nid = node.get(w("id"))
            if nid is None:
                continue
            around[(kind, str(nid))] = _chars_around_node(node, super_style_ids)
    return around


def _chars_around_node(
    node: etree._Element,
    super_style_ids: frozenset[str] | None = None,
) -> tuple[str, str, str, bool, bool]:
    paragraph = node
    while paragraph is not None and paragraph.tag != w("p"):
        paragraph = paragraph.getparent()
    if paragraph is None:
        return "", "", "", False, False
    before: list[tuple[etree._Element, str]] = []
    after_node = None
    after = ""
    seen = False
    for el in paragraph.iter():
        if el is node:
            seen = True
            continue
        if el.tag != w("t") or _is_deleted(el):
            continue
        value = el.text or ""
        if not value:
            continue
        if not seen:
            before.append((el, value))
        else:
            after_node = el
            after = value
            break
    joined = "".join(item[1] for item in before)
    prev = joined[-1:]
    prev2 = joined[-2:-1]
    nxt = after[:1] if after else ""
    prev_super = False
    if prev and before:
        prev_super = _run_is_superscript(before[-1][0], super_style_ids)
    next_super = False
    if nxt and after_node is not None:
        next_super = _run_is_superscript(after_node, super_style_ids)
    return prev, nxt, prev2, prev_super, next_super


def _run_is_superscript(t_elem: etree._Element, super_style_ids: frozenset[str] | None = None) -> bool:
    run = t_elem.getparent()
    while run is not None and run.tag != w("r"):
        run = run.getparent()
    if run is None:
        return False
    r_pr = run.find(w("rPr"))
    if r_pr is None:
        return False
    if _vert_align_is_super(r_pr.find(w("vertAlign"))):
        return True
    r_style = r_pr.find(w("rStyle"))
    style_id = (r_style.get(w("val")) if r_style is not None else "") or ""
    return bool(style_id and style_id in (super_style_ids or ()))


def _vert_align_is_super(node: etree._Element | None) -> bool:
    if node is None:
        return False
    val = (node.get(w("val")) or "").strip().lower()
    return val in {"superscript", "super"}


def _superscript_style_ids(xml: bytes | None) -> frozenset[str]:
    if not xml:
        return frozenset()
    try:
        root = etree.fromstring(xml)
    except etree.XMLSyntaxError:
        return frozenset()
    based_on: dict[str, str] = {}
    direct: set[str] = set()
    all_ids: list[str] = []
    for style in root.iter(w("style")):
        style_id = style.get(w("styleId")) or ""
        if not style_id:
            continue
        all_ids.append(style_id)
        based = style.find(w("basedOn"))
        parent = (based.get(w("val")) if based is not None else "") or ""
        if parent:
            based_on[style_id] = parent
        r_pr = style.find(w("rPr"))
        if r_pr is None:
            p_pr = style.find(w("pPr"))
            r_pr = p_pr.find(w("rPr")) if p_pr is not None else None
        if _vert_align_is_super(None if r_pr is None else r_pr.find(w("vertAlign"))):
            direct.add(style_id)
    ids: set[str] = set()
    for style_id in all_ids:
        seen: set[str] = set()
        current = style_id
        while current and current not in seen:
            seen.add(current)
            if current in direct:
                ids.add(style_id)
                break
            current = based_on.get(current, "")
    return frozenset(ids)


def _is_deleted(node: etree._Element) -> bool:
    for ancestor in node.iterancestors():
        if ancestor.tag == w("del"):
            return True
    return False


def _insert_one_comment(doc_root: etree._Element, start: int, end: int, comment_id: int) -> None:
    text, spans = _walk_text(doc_root)
    if start >= len(text):
        return
    end = min(end, len(text))
    if start >= end:
        return

    start_node, start_local = _locate(spans, start, for_end=False)
    if start_node is None:
        return
    if 0 < start_local < len(start_node.text or ""):
        _split_run_text(start_node, start_local)

    _text, spans = _walk_text(doc_root)
    end_node, end_local = _locate(spans, end, for_end=True)
    if end_node is not None and 0 < end_local < len(end_node.text or ""):
        _split_run_text(end_node, end_local)

    _text, spans = _walk_text(doc_root)
    start_node, _start_local = _locate(spans, start, for_end=False)
    end_node, _end_local = _locate(spans, end, for_end=True)
    if start_node is None:
        return
    if end_node is None:
        end_node = start_node

    start_run = start_node.getparent()
    end_run = end_node.getparent()
    if start_run is None or end_run is None:
        return

    start_parent = start_run.getparent()
    end_parent = end_run.getparent()
    start_idx = list(start_parent).index(start_run)
    start_parent.insert(start_idx, _comment_marker("commentRangeStart", comment_id))

    end_idx = list(end_parent).index(end_run)
    end_parent.insert(end_idx + 1, _comment_marker("commentRangeEnd", comment_id))
    end_parent.insert(end_idx + 2, _comment_reference_run(comment_id))


def _insert_comment_on_note_ref(doc_root: etree._Element, note_id: str, note_kind: str, comment_id: int) -> None:
    body = doc_root.find(w("body"))
    if body is None:
        return
    tag = w("endnoteReference") if note_kind == "endnote" else w("footnoteReference")
    for node in body.iter(tag):
        if (node.get(w("id")) or "") != note_id:
            continue
        run = node.getparent()
        parent = run.getparent() if run is not None else None
        if parent is None:
            return
        idx = list(parent).index(run)
        parent.insert(idx, _comment_marker("commentRangeStart", comment_id))
        idx = list(parent).index(run)
        parent.insert(idx + 1, _comment_marker("commentRangeEnd", comment_id))
        parent.insert(idx + 2, _comment_reference_run(comment_id))
        return


def _locate(spans, index: int, *, for_end: bool):
    for node, start, end in spans:
        if node is None:
            continue
        if for_end:
            if start < index <= end:
                return node, index - start
        elif start <= index < end:
            return node, index - start
    if for_end:
        for node, start, end in reversed(spans):
            if node is not None:
                return node, len(node.text or "")
    return None, 0


def _split_run_text(t_elem: etree._Element, local_index: int) -> etree._Element:
    text = t_elem.text or ""
    run = t_elem.getparent()
    parent = run.getparent() if run is not None else None
    if parent is None or local_index <= 0 or local_index >= len(text):
        return t_elem
    idx = list(parent).index(run)
    right = deepcopy(run)
    t_elem.text = text[:local_index]
    _ensure_xml_space_preserve(t_elem)
    right_t = None
    for node in right.iter(w("t")):
        if right_t is None:
            node.text = text[local_index:]
            _ensure_xml_space_preserve(node)
            right_t = node
        else:
            node_parent = node.getparent()
            if node_parent is not None:
                node_parent.remove(node)
    if right_t is None:
        right_t = etree.SubElement(right, w("t"))
        right_t.text = text[local_index:]
        _ensure_xml_space_preserve(right_t)
    parent.insert(idx + 1, right)
    return right_t


def _comment_marker(tag: str, comment_id: int) -> etree._Element:
    elem = etree.Element(w(tag))
    elem.set(w("id"), str(comment_id))
    return elem


def _comment_reference_run(comment_id: int) -> etree._Element:
    run = etree.Element(w("r"))
    r_pr = etree.SubElement(run, w("rPr"))
    r_style = etree.SubElement(r_pr, w("rStyle"))
    r_style.set(w("val"), "CommentReference")
    ref = etree.SubElement(run, w("commentReference"))
    ref.set(w("id"), str(comment_id))
    return run


def _ensure_xml_space_preserve(t_elem: etree._Element) -> None:
    """Keep leading/trailing spaces in a w:t, otherwise Word drops them."""
    text = t_elem.text or ""
    if text and (text[0] in XML_WHITESPACE or text[-1] in XML_WHITESPACE):
        t_elem.set(XML_SPACE_ATTR, "preserve")


def _preserve_edge_spaces(root: etree._Element) -> None:
    for node in root.iter(w("t")):
        _ensure_xml_space_preserve(node)


def _comment_element(
    comment_id: int,
    author: str,
    message: str,
    links: list[dict] | None = None,
    url_to_rid: dict[str, str] | None = None,
) -> etree._Element:
    comment = etree.Element(w("comment"))
    comment.set(w("id"), str(comment_id))
    comment.set(w("author"), author)
    comment.set(w("date"), datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    comment.set(w("initials"), _initials(author))
    paragraph = etree.SubElement(comment, w("p"))
    run = etree.SubElement(paragraph, w("r"))
    text_node = etree.SubElement(run, w("t"))
    text_node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    text_node.text = message
    for link in links or []:
        rid = (url_to_rid or {}).get(link["url"])
        if not rid:
            continue
        link_p = etree.SubElement(comment, w("p"))
        hyperlink = etree.SubElement(link_p, w("hyperlink"))
        hyperlink.set(f"{{{R_NS}}}id", rid)
        hyperlink.set(w("history"), "1")
        link_run = etree.SubElement(hyperlink, w("r"))
        r_pr = etree.SubElement(link_run, w("rPr"))
        r_style = etree.SubElement(r_pr, w("rStyle"))
        r_style.set(w("val"), "Hyperlink")
        color = etree.SubElement(r_pr, w("color"))
        color.set(w("val"), "0563C1")
        underline = etree.SubElement(r_pr, w("u"))
        underline.set(w("val"), "single")
        link_text = etree.SubElement(link_run, w("t"))
        link_text.text = link["text"]
    return comment


def _finding_links(item: dict) -> list[dict]:
    links = []
    raw = item.get("links")
    if isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            text = str(entry.get("text") or "").strip()
            url = str(entry.get("url") or "").strip()
            if text and url:
                links.append({"text": text, "url": url})
    text = str(item.get("link_text") or "").strip()
    url = str(item.get("link_url") or "").strip()
    if text and url:
        links.append({"text": text, "url": url})
    return links


def _load_comments_rels(xml_bytes: bytes | None) -> tuple[etree._Element, set[str], dict[str, str]]:
    if xml_bytes:
        try:
            root = etree.fromstring(xml_bytes)
        except etree.XMLSyntaxError:
            root = etree.Element(f"{{{REL_NS}}}Relationships", nsmap={None: REL_NS})
    else:
        root = etree.Element(f"{{{REL_NS}}}Relationships", nsmap={None: REL_NS})
    used: set[str] = set()
    url_to_rid: dict[str, str] = {}
    for rel in root:
        rid = rel.get("Id") or ""
        if rid:
            used.add(rid)
        if rel.get("Type") == HYPERLINK_REL_TYPE and (rel.get("Target") or ""):
            url_to_rid[rel.get("Target") or ""] = rid
    return root, used, url_to_rid


def _add_hyperlink_rel(root: etree._Element, rid: str, url: str) -> None:
    rel = etree.SubElement(root, f"{{{REL_NS}}}Relationship")
    rel.set("Id", rid)
    rel.set("Type", HYPERLINK_REL_TYPE)
    rel.set("Target", url)
    rel.set("TargetMode", "External")


def _next_rid(used: set[str]) -> str:
    idx = 1
    while f"rId{idx}" in used:
        idx += 1
    return f"rId{idx}"


def _initials(author: str) -> str:
    parts = [part for part in str(author or "").split() if part]
    if not parts:
        return "ПР"
    chars = "".join(part[0] for part in parts[:2])
    return chars.upper()[:4] or "ПР"


def _load_comments_root(xml_bytes: bytes | None) -> tuple[etree._Element, int]:
    if xml_bytes:
        try:
            root = etree.fromstring(xml_bytes)
        except etree.XMLSyntaxError:
            root = etree.Element(w("comments"), nsmap={"w": W_NS, "r": R_NS})
    else:
        root = etree.Element(w("comments"), nsmap={"w": W_NS, "r": R_NS})
    if "r" not in (root.nsmap or {}):
        root.set(f"{{{XMLNS_NS}}}r", R_NS)
    max_id = -1
    for comment in root.findall(w("comment")):
        try:
            max_id = max(max_id, int(comment.get(w("id")) or -1))
        except ValueError:
            continue
    return root, max_id + 1


def _ensure_comments_rel(xml_bytes: bytes | None) -> bytes:
    if xml_bytes:
        root = etree.fromstring(xml_bytes)
    else:
        root = etree.Element(f"{{{REL_NS}}}Relationships", nsmap={None: REL_NS})
    for rel in root:
        if rel.get("Type") == COMMENTS_REL_TYPE:
            return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    used = {rel.get("Id") or "" for rel in root}
    idx = 1
    while f"rId{idx}" in used:
        idx += 1
    rel = etree.SubElement(root, f"{{{REL_NS}}}Relationship")
    rel.set("Id", f"rId{idx}")
    rel.set("Type", COMMENTS_REL_TYPE)
    rel.set("Target", "comments.xml")
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _ensure_comments_content_type(xml_bytes: bytes | None) -> bytes:
    if xml_bytes:
        root = etree.fromstring(xml_bytes)
    else:
        root = etree.Element(f"{{{CT_NS}}}Types", nsmap={None: CT_NS})
    for item in root:
        if item.get("PartName") == "/word/comments.xml":
            return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    override = etree.SubElement(root, f"{{{CT_NS}}}Override")
    override.set("PartName", "/word/comments.xml")
    override.set("ContentType", COMMENTS_CONTENT_TYPE)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _is_comment_markup_part(name: str) -> bool:
    if not name.startswith("word/") or name.endswith(".rels"):
        return False
    basename = name.rsplit("/", 1)[-1]
    return (
        name == DOCUMENT_XML
        or basename.startswith("header")
        or basename.startswith("footer")
        or basename in {"footnotes.xml", "endnotes.xml"}
    )


def _strip_comment_markup(xml_bytes: bytes) -> bytes:
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError as exc:
        raise DocxCommentError("Некорректный XML документа Word.") from exc
    comment_tags = {
        w("commentRangeStart"),
        w("commentRangeEnd"),
        w("commentReference"),
    }
    removed = False
    for elem in list(root.iter()):
        if elem.tag in comment_tags:
            parent = elem.getparent()
            if parent is not None:
                parent.remove(elem)
                removed = True
    for run in list(root.iter(w("r"))):
        if any(child.tag != w("rPr") for child in run):
            continue
        r_pr = run.find(w("rPr"))
        if r_pr is None:
            continue
        style = r_pr.find(w("rStyle"))
        if style is not None and style.get(w("val")) == "CommentReference":
            parent = run.getparent()
            if parent is not None:
                parent.remove(run)
                removed = True
    if not removed:
        return xml_bytes
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _strip_comment_rels(xml_bytes: bytes) -> bytes:
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError:
        return xml_bytes
    removed = False
    for rel in list(root):
        target = (rel.get("Target") or "").replace("\\", "/").lstrip("./")
        if rel.get("Type") in COMMENT_REL_TYPES or target in {
            "comments.xml",
            "commentsExtended.xml",
            "commentsIds.xml",
            "commentsExtensible.xml",
        }:
            root.remove(rel)
            removed = True
    if not removed:
        return xml_bytes
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _strip_comment_content_types(xml_bytes: bytes) -> bytes:
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError:
        return xml_bytes
    removed = False
    for item in list(root):
        if item.get("PartName") in COMMENT_PART_NAMES:
            root.remove(item)
            removed = True
    if not removed:
        return xml_bytes
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _read_zip(data: bytes) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(BytesIO(data)) as zin:
            return {info.filename: zin.read(info.filename) for info in zin.infolist() if not info.is_dir()}
    except zipfile.BadZipFile as exc:
        raise DocxCommentError("Файл не является корректным DOCX.") from exc


def _write_zip(parts: dict[str, bytes]) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for name, data in parts.items():
            zout.writestr(name, data)
    return buffer.getvalue()
