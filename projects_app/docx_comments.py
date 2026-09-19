from __future__ import annotations

import zipfile
from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO

from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
COMMENTS_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
COMMENTS_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"
DOCUMENT_XML = "word/document.xml"
COMMENTS_XML = "word/comments.xml"
DOCUMENT_RELS = "word/_rels/document.xml.rels"
CONTENT_TYPES = "[Content_Types].xml"


def w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


class DocxCommentError(ValueError):
    """DOCX cannot be read or comments cannot be written."""


def extract_document_text(docx_bytes: bytes) -> tuple[str, list[tuple[etree._Element | None, int, int]]]:
    root = _document_root(docx_bytes)
    return _walk_text(root)


def insert_comments(docx_bytes: bytes, findings: list[dict]) -> bytes:
    if not findings:
        return docx_bytes
    parts = _read_zip(docx_bytes)
    if DOCUMENT_XML not in parts:
        raise DocxCommentError("В файле нет word/document.xml.")

    doc_root = etree.fromstring(parts[DOCUMENT_XML])
    comments_root, next_id = _load_comments_root(parts.get(COMMENTS_XML))
    ordered = sorted(
        (item for item in findings if _valid_finding(item)),
        key=lambda item: (int(item["start"]), -int(item["end"])),
        reverse=True,
    )
    for item in ordered:
        start = int(item["start"])
        end = int(item["end"])
        message = str(item.get("message") or "").strip()
        author = str(item.get("author") or "Проверка").strip() or "Проверка"
        _insert_one_comment(doc_root, start, end, next_id)
        comments_root.append(_comment_element(next_id, author, message))
        next_id += 1

    parts[DOCUMENT_XML] = etree.tostring(doc_root, xml_declaration=True, encoding="UTF-8", standalone=True)
    parts[COMMENTS_XML] = etree.tostring(comments_root, xml_declaration=True, encoding="UTF-8", standalone=True)
    parts[DOCUMENT_RELS] = _ensure_comments_rel(parts.get(DOCUMENT_RELS))
    parts[CONTENT_TYPES] = _ensure_comments_content_type(parts.get(CONTENT_TYPES))
    return _write_zip(parts)


def _valid_finding(item: dict) -> bool:
    try:
        start = int(item.get("start"))
        end = int(item.get("end"))
    except (TypeError, ValueError):
        return False
    message = str(item.get("message") or "").strip()
    return bool(message) and 0 <= start < end


def _document_root(docx_bytes: bytes) -> etree._Element:
    parts = _read_zip(docx_bytes)
    xml = parts.get(DOCUMENT_XML)
    if not xml:
        raise DocxCommentError("В файле нет word/document.xml.")
    try:
        return etree.fromstring(xml)
    except etree.XMLSyntaxError as exc:
        raise DocxCommentError("Некорректный word/document.xml.") from exc


def _walk_text(root: etree._Element) -> tuple[str, list[tuple[etree._Element | None, int, int]]]:
    body = root.find(w("body"))
    if body is None:
        return "", []
    spans: list[tuple[etree._Element | None, int, int]] = []
    parts: list[str] = []
    offset = 0
    for paragraph in body.iter(w("p")):
        for node in paragraph.iter(w("t")):
            if _is_deleted(node):
                continue
            value = node.text or ""
            if not value:
                continue
            spans.append((node, offset, offset + len(value)))
            parts.append(value)
            offset += len(value)
        parts.append("\n")
        spans.append((None, offset, offset + 1))
        offset += 1
    return "".join(parts), spans


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
    right_t = None
    for node in right.iter(w("t")):
        if right_t is None:
            node.text = text[local_index:]
            right_t = node
        else:
            node_parent = node.getparent()
            if node_parent is not None:
                node_parent.remove(node)
    if right_t is None:
        right_t = etree.SubElement(right, w("t"))
        right_t.text = text[local_index:]
        right_t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
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


def _comment_element(comment_id: int, author: str, message: str) -> etree._Element:
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
    return comment


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
            root = etree.Element(w("comments"), nsmap={"w": W_NS})
    else:
        root = etree.Element(w("comments"), nsmap={"w": W_NS})
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
