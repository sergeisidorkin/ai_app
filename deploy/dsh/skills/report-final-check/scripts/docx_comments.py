#!/usr/bin/env python3
"""Extract DOCX text and add Word comments without third-party packages."""

from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
XML_NS = "http://www.w3.org/XML/1998/namespace"
COMMENTS_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
COMMENTS_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"

DOCUMENT_XML = "word/document.xml"
COMMENTS_XML = "word/comments.xml"
DOCUMENT_RELS = "word/_rels/document.xml.rels"
CONTENT_TYPES = "[Content_Types].xml"

ET.register_namespace("w", W_NS)


def w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def read_package(path: Path) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(path) as archive:
            return {
                item.filename: archive.read(item.filename)
                for item in archive.infolist()
                if not item.is_dir()
            }
    except (OSError, zipfile.BadZipFile) as exc:
        raise SystemExit(f"Некорректный DOCX: {exc}") from exc


def write_package(path: Path, parts: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)


def document_root(parts: dict[str, bytes]) -> ET.Element:
    xml = parts.get(DOCUMENT_XML)
    if not xml:
        raise SystemExit("В DOCX отсутствует word/document.xml.")
    register_document_namespaces(xml)
    try:
        return ET.fromstring(xml)
    except ET.ParseError as exc:
        raise SystemExit(f"Некорректный word/document.xml: {exc}") from exc


def walk_text(root: ET.Element):
    body = root.find(w("body"))
    if body is None:
        return "", []
    chunks = []
    spans = []
    offset = 0
    for paragraph in body.iter(w("p")):
        for node in paragraph.iter(w("t")):
            if any(parent.tag == w("del") for parent in _ancestors(root, node)):
                continue
            value = node.text or ""
            if not value:
                continue
            spans.append((node, offset, offset + len(value)))
            chunks.append(value)
            offset += len(value)
        chunks.append("\n")
        spans.append((None, offset, offset + 1))
        offset += 1
    return "".join(chunks), spans


def _ancestors(root: ET.Element, target: ET.Element):
    parent_map = {child: parent for parent in root.iter() for child in parent}
    current = parent_map.get(target)
    while current is not None:
        yield current
        current = parent_map.get(current)


def extract(source: Path, destination: Path) -> None:
    text, _spans = walk_text(document_root(read_package(source)))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")


def load_findings(path: Path, text: str) -> list[dict]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Некорректный findings.json: {exc}") from exc
    if not isinstance(raw, list):
        raise SystemExit("findings.json должен содержать JSON-массив.")

    findings = []
    used = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        quote = str(item.get("quote") or "").strip()
        message = str(item.get("message") or "").strip()
        if not quote or not message:
            continue
        occurrence = max(int(item.get("occurrence") or 1), 1)
        starts = []
        cursor = 0
        while True:
            index = text.find(quote, cursor)
            if index < 0:
                break
            starts.append(index)
            cursor = index + max(len(quote), 1)
        if not starts:
            raise SystemExit(f"Фрагмент из findings.json не найден в документе: {quote!r}")
        if occurrence > len(starts):
            raise SystemExit(
                f"В документе нет вхождения №{occurrence}: {quote!r}"
            )
        start = starts[occurrence - 1]
        end = start + len(quote)
        if any(start < old_end and end > old_start for old_start, old_end in used):
            raise SystemExit(f"Пересекающиеся замечания для фрагмента: {quote!r}")
        used.append((start, end))
        findings.append({
            "start": start,
            "end": end,
            "message": message,
            "author": str(item.get("author") or "report-final-check").strip()
            or "report-final-check",
        })
    return findings


def annotate(source: Path, destination: Path, findings_path: Path) -> None:
    parts = read_package(source)
    root = document_root(parts)
    text, _spans = walk_text(root)
    findings = load_findings(findings_path, text)
    if not findings:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        return

    comments_root, next_id = load_comments(parts.get(COMMENTS_XML))
    for item in sorted(
        findings,
        key=lambda row: (row["start"], -row["end"]),
        reverse=True,
    ):
        insert_comment_range(root, item["start"], item["end"], next_id)
        comments_root.append(comment_element(
            next_id,
            item["author"],
            item["message"],
        ))
        next_id += 1

    preserve_edge_spaces(root)
    ET.register_namespace("w", W_NS)
    parts[DOCUMENT_XML] = serialize_document(parts[DOCUMENT_XML], root)
    parts[COMMENTS_XML] = ET.tostring(
        comments_root,
        encoding="utf-8",
        xml_declaration=True,
    )
    parts[DOCUMENT_RELS] = ensure_comments_relationship(parts.get(DOCUMENT_RELS))
    parts[CONTENT_TYPES] = ensure_comments_content_type(parts.get(CONTENT_TYPES))
    write_package(destination, parts)


def register_document_namespaces(xml: bytes) -> None:
    """Reuse Word's original prefixes while serializing modified elements."""
    try:
        declarations = ET.iterparse(BytesIO(xml), events=("start-ns",))
        for _event, (prefix, uri) in declarations:
            if prefix and re.fullmatch(r"ns\d+", prefix):
                continue
            ET.register_namespace(prefix or "", uri)
    except (ET.ParseError, ValueError):
        # document_root() reports malformed XML; reserved prefixes can safely
        # fall back to ElementTree-generated names.
        return


def serialize_document(original_xml: bytes, root: ET.Element) -> bytes:
    """Preserve Word's root tag and all mc:Ignorable namespace declarations."""
    serialized = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    original_match = re.search(rb"<([A-Za-z_][\w.-]*:)?document\b", original_xml)
    serialized_match = re.search(rb"<([A-Za-z_][\w.-]*:)?document\b", serialized)
    if not original_match or not serialized_match:
        return serialized

    original_open_end = _xml_tag_end(original_xml, original_match.start())
    serialized_open_end = _xml_tag_end(serialized, serialized_match.start())
    if original_open_end < 0 or serialized_open_end < 0:
        return serialized

    original_qname = original_match.group(0)[1:].split(None, 1)[0]
    original_close = b"</" + original_qname + b">"
    serialized_qname = serialized_match.group(0)[1:].split(None, 1)[0]
    serialized_close = b"</" + serialized_qname + b">"
    original_close_start = original_xml.rfind(original_close)
    serialized_close_start = serialized.rfind(serialized_close)
    if original_close_start < 0 or serialized_close_start < 0:
        return serialized

    return (
        original_xml[:original_open_end + 1]
        + serialized[serialized_open_end + 1:serialized_close_start]
        + original_xml[original_close_start:]
    )


def _xml_tag_end(xml: bytes, start: int) -> int:
    quote = None
    for index in range(start, len(xml)):
        byte = xml[index]
        if quote is not None:
            if byte == quote:
                quote = None
            continue
        if byte in (ord('"'), ord("'")):
            quote = byte
        elif byte == ord(">"):
            return index
    return -1


def locate(spans, index: int, *, for_end: bool):
    for node, start, end in spans:
        if node is None:
            continue
        if for_end and start < index <= end:
            return node, index - start
        if not for_end and start <= index < end:
            return node, index - start
    if for_end:
        for node, _start, _end in reversed(spans):
            if node is not None:
                return node, len(node.text or "")
    return None, 0


def parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    return {child: parent for parent in root.iter() for child in parent}


XML_WHITESPACE = frozenset(" \t\r\n")


def _ensure_xml_space_preserve(text_node: ET.Element) -> None:
    value = text_node.text or ""
    if value and (value[0] in XML_WHITESPACE or value[-1] in XML_WHITESPACE):
        text_node.set(f"{{{XML_NS}}}space", "preserve")


def preserve_edge_spaces(root: ET.Element) -> None:
    for node in root.iter(w("t")):
        _ensure_xml_space_preserve(node)


def split_run_text(root: ET.Element, text_node: ET.Element, index: int) -> None:
    value = text_node.text or ""
    parents = parent_map(root)
    run = parents.get(text_node)
    parent = parents.get(run) if run is not None else None
    if parent is None or index <= 0 or index >= len(value):
        return
    right = copy.deepcopy(run)
    text_node.text = value[:index]
    right_nodes = list(right.iter(w("t")))
    if not right_nodes:
        return
    right_nodes[0].text = value[index:]
    _ensure_xml_space_preserve(text_node)
    _ensure_xml_space_preserve(right_nodes[0])
    for extra in right_nodes[1:]:
        extra.text = ""
    position = list(parent).index(run)
    parent.insert(position + 1, right)


def insert_comment_range(
    root: ET.Element,
    start: int,
    end: int,
    comment_id: int,
) -> None:
    text, spans = walk_text(root)
    if not (0 <= start < end <= len(text)):
        raise SystemExit("Некорректный диапазон комментария.")
    start_node, start_local = locate(spans, start, for_end=False)
    if start_node is None:
        raise SystemExit("Не удалось найти начало комментария.")
    split_run_text(root, start_node, start_local)

    _text, spans = walk_text(root)
    end_node, end_local = locate(spans, end, for_end=True)
    if end_node is not None:
        split_run_text(root, end_node, end_local)

    _text, spans = walk_text(root)
    start_node, _ = locate(spans, start, for_end=False)
    end_node, _ = locate(spans, end, for_end=True)
    if start_node is None or end_node is None:
        raise SystemExit("Не удалось привязать комментарий к тексту.")
    parents = parent_map(root)
    start_run = parents.get(start_node)
    end_run = parents.get(end_node)
    start_parent = parents.get(start_run) if start_run is not None else None
    end_parent = parents.get(end_run) if end_run is not None else None
    if start_parent is None or end_parent is None:
        raise SystemExit("Не удалось найти абзац для комментария.")

    start_marker = ET.Element(w("commentRangeStart"), {w("id"): str(comment_id)})
    start_parent.insert(list(start_parent).index(start_run), start_marker)

    end_position = list(end_parent).index(end_run)
    end_parent.insert(
        end_position + 1,
        ET.Element(w("commentRangeEnd"), {w("id"): str(comment_id)}),
    )
    reference_run = ET.Element(w("r"))
    properties = ET.SubElement(reference_run, w("rPr"))
    ET.SubElement(properties, w("rStyle"), {w("val"): "CommentReference"})
    ET.SubElement(reference_run, w("commentReference"), {w("id"): str(comment_id)})
    end_parent.insert(end_position + 2, reference_run)


def load_comments(xml: bytes | None):
    if xml:
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as exc:
            raise SystemExit(f"Некорректный word/comments.xml: {exc}") from exc
    else:
        root = ET.Element(w("comments"))
    ids = []
    for comment in root.findall(w("comment")):
        try:
            ids.append(int(comment.get(w("id")) or -1))
        except ValueError:
            pass
    return root, max(ids, default=-1) + 1


def comment_element(comment_id: int, author: str, message: str) -> ET.Element:
    comment = ET.Element(w("comment"), {
        w("id"): str(comment_id),
        w("author"): author,
        w("date"): datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        w("initials"): "RFC",
    })
    paragraph = ET.SubElement(comment, w("p"))
    run = ET.SubElement(paragraph, w("r"))
    node = ET.SubElement(run, w("t"), {f"{{{XML_NS}}}space": "preserve"})
    node.text = message
    return comment


def ensure_comments_relationship(xml: bytes | None) -> bytes:
    root = (
        ET.fromstring(xml)
        if xml
        else ET.Element(f"{{{REL_NS}}}Relationships")
    )
    for item in root:
        if item.get("Type") == COMMENTS_REL_TYPE:
            ET.register_namespace("", REL_NS)
            return ET.tostring(root, encoding="utf-8", xml_declaration=True)
    used = {item.get("Id") or "" for item in root}
    index = 1
    while f"rId{index}" in used:
        index += 1
    ET.SubElement(root, f"{{{REL_NS}}}Relationship", {
        "Id": f"rId{index}",
        "Type": COMMENTS_REL_TYPE,
        "Target": "comments.xml",
    })
    ET.register_namespace("", REL_NS)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def ensure_comments_content_type(xml: bytes | None) -> bytes:
    root = (
        ET.fromstring(xml)
        if xml
        else ET.Element(f"{{{CT_NS}}}Types")
    )
    for item in root:
        if item.get("PartName") == "/word/comments.xml":
            ET.register_namespace("", CT_NS)
            return ET.tostring(root, encoding="utf-8", xml_declaration=True)
    ET.SubElement(root, f"{{{CT_NS}}}Override", {
        "PartName": "/word/comments.xml",
        "ContentType": COMMENTS_CONTENT_TYPE,
    })
    ET.register_namespace("", CT_NS)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser("extract")
    extract_parser.add_argument("source", type=Path)
    extract_parser.add_argument("destination", type=Path)

    annotate_parser = subparsers.add_parser("annotate")
    annotate_parser.add_argument("source", type=Path)
    annotate_parser.add_argument("destination", type=Path)
    annotate_parser.add_argument("findings", type=Path)

    args = parser.parse_args()
    if args.command == "extract":
        extract(args.source, args.destination)
    else:
        annotate(args.source, args.destination, args.findings)


if __name__ == "__main__":
    main()
