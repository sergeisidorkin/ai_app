from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from lxml import etree

from .docx_comments import (
    DOCUMENT_XML,
    DocxCommentError,
    _iter_paragraph_plain,
    _read_zip,
    w,
)

W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
_SENTENCE_END_RE = re.compile(r"(?<=[.!?…])(?:\s+|$)")


@dataclass(frozen=True)
class DocumentAnchor:
    anchor_id: str
    start: int
    end: int
    text: str
    text_sha256: str
    style_id: str = ""
    heading_path: tuple[str, ...] = ()
    structural_path: str = ""

    def as_payload(self, *, local_start: int = 0, local_end: int | None = None) -> dict:
        local_end = len(self.text) if local_end is None else local_end
        return {
            "anchor_id": self.anchor_id,
            "text_sha256": self.text_sha256,
            "structural_path": self.structural_path,
            "heading_path": list(self.heading_path),
            "slice_start": local_start,
            "slice_end": local_end,
            "text": self.text[local_start:local_end],
        }


@dataclass(frozen=True)
class DocumentSnapshot:
    source_sha256: str
    text: str
    anchors: tuple[DocumentAnchor, ...]

    @property
    def by_id(self) -> dict[str, DocumentAnchor]:
        return {item.anchor_id: item for item in self.anchors}


@dataclass(frozen=True)
class ChunkBlock:
    anchor: DocumentAnchor
    slice_start: int
    slice_end: int
    core_start: int
    core_end: int

    @property
    def text(self) -> str:
        return self.anchor.text[self.slice_start:self.slice_end]

    def as_payload(self) -> dict:
        payload = self.anchor.as_payload(
            local_start=self.slice_start,
            local_end=self.slice_end,
        )
        payload["core_start"] = self.core_start
        payload["core_end"] = self.core_end
        return payload


@dataclass(frozen=True)
class DocumentChunk:
    chunk_id: str
    ordinal: int
    blocks: tuple[ChunkBlock, ...]

    def as_payload(self, source_sha256: str) -> dict:
        return {
            "schema_version": 1,
            "source_sha256": source_sha256,
            "chunk_id": self.chunk_id,
            "ordinal": self.ordinal,
            "blocks": [item.as_payload() for item in self.blocks],
        }

    def canonical_json(self, source_sha256: str) -> str:
        return json.dumps(
            self.as_payload(source_sha256),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


def build_document_snapshot(docx_bytes: bytes) -> DocumentSnapshot:
    parts = _read_zip(docx_bytes)
    xml = parts.get(DOCUMENT_XML)
    if not xml:
        raise DocxCommentError("В файле нет word/document.xml.")
    try:
        root = etree.fromstring(xml)
    except etree.XMLSyntaxError as exc:
        raise DocxCommentError("Некорректный word/document.xml.") from exc
    body = root.find(w("body"))
    if body is None:
        raise DocxCommentError("В word/document.xml отсутствует тело документа.")

    anchors: list[DocumentAnchor] = []
    full_text: list[str] = []
    offset = 0
    headings: list[tuple[int, str]] = []
    for ordinal, paragraph in enumerate(body.iter(w("p")), start=1):
        text = "".join(value for _node, value in _iter_paragraph_plain(paragraph))
        start = offset
        end = start + len(text)
        style_id = _paragraph_style_id(paragraph)
        heading_level = _heading_level(style_id)
        if heading_level:
            headings = [item for item in headings if item[0] < heading_level]
            headings.append((heading_level, text.strip()))
        para_id = paragraph.get(f"{{{W14_NS}}}paraId") or ""
        structural_path = _paragraph_structural_path(paragraph, ordinal)
        stable = para_id or structural_path
        anchor_id = f"body:{stable}:{ordinal}"
        anchors.append(DocumentAnchor(
            anchor_id=anchor_id,
            start=start,
            end=end,
            text=text,
            text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            style_id=style_id,
            heading_path=tuple(value for _level, value in headings if value),
            structural_path=structural_path,
        ))
        full_text.append(text)
        full_text.append("\n")
        offset = end + 1

    return DocumentSnapshot(
        source_sha256=hashlib.sha256(docx_bytes).hexdigest(),
        text="".join(full_text),
        anchors=tuple(anchors),
    )


def chunk_document(
    snapshot: DocumentSnapshot,
    *,
    max_core_chars: int = 12_000,
    overlap_chars: int = 1_500,
) -> tuple[DocumentChunk, ...]:
    max_core_chars = max(int(max_core_chars or 0), 500)
    overlap_chars = max(min(int(overlap_chars or 0), max_core_chars // 2), 0)
    segments: list[tuple[DocumentAnchor, int, int]] = []
    for anchor in snapshot.anchors:
        segments.extend(_anchor_segments(anchor, max_core_chars))
    if not segments:
        return ()

    groups: list[list[tuple[DocumentAnchor, int, int]]] = []
    current: list[tuple[DocumentAnchor, int, int]] = []
    current_size = 0
    for segment in segments:
        size = segment[2] - segment[1]
        if current and current_size + size > max_core_chars:
            groups.append(current)
            current = []
            current_size = 0
        current.append(segment)
        current_size += size
    if current:
        groups.append(current)

    chunks = []
    for index, core in enumerate(groups):
        before = _overlap_segments(groups[index - 1] if index else [], overlap_chars, from_end=True)
        after = _overlap_segments(
            groups[index + 1] if index + 1 < len(groups) else [],
            overlap_chars,
            from_end=False,
        )
        blocks = [
            ChunkBlock(anchor, start, end, 0, 0)
            for anchor, start, end in before
        ]
        blocks.extend(
            ChunkBlock(anchor, start, end, start, end)
            for anchor, start, end in core
        )
        blocks.extend(
            ChunkBlock(anchor, start, end, 0, 0)
            for anchor, start, end in after
        )
        digest = hashlib.sha256(
            "|".join(
                f"{item.anchor.anchor_id}:{item.slice_start}:{item.slice_end}:"
                f"{item.core_start}:{item.core_end}"
                for item in blocks
            ).encode("utf-8")
        ).hexdigest()[:20]
        chunks.append(DocumentChunk(
            chunk_id=f"chunk-{index + 1:05d}-{digest}",
            ordinal=index + 1,
            blocks=tuple(blocks),
        ))
    return tuple(chunks)


def _quoted_fragment(source: str, text: str) -> str:
    for match in re.finditer(r"«([^»]{2,300})»", source or ""):
        fragment = match.group(1).strip()
        if fragment and fragment in text:
            return fragment
    return ""


def _fallback_quote(core_text: str, explanation: str, replacement: str, limit: int = 200) -> str:
    for source in (explanation, replacement):
        fragment = _quoted_fragment(source, core_text)
        if fragment:
            return fragment
    stripped = (core_text or "").strip()
    if not stripped:
        return ""
    offset = core_text.find(stripped)
    snippet = core_text[offset:offset + min(len(stripped), limit)]
    return snippet.strip() or snippet


def validate_chunk_finding(
    snapshot: DocumentSnapshot,
    chunk: DocumentChunk,
    finding: dict,
) -> dict:
    anchor_id = str(finding.get("anchor_id") or "")
    blocks = [
        item
        for item in chunk.blocks
        if item.anchor.anchor_id == anchor_id and item.core_end > item.core_start
    ]
    if not blocks:
        raise ValueError("Находка относится к контексту, а не к core-зоне фрагмента.")
    quote = str(finding.get("quote") or "")
    if not quote:
        explanation = str(finding.get("explanation") or "")
        replacement = str(finding.get("replacement") or "")
        for item in blocks:
            core_text = item.anchor.text[item.core_start:item.core_end]
            quote = _fallback_quote(core_text, explanation, replacement)
            if quote:
                break
    if not quote:
        raise ValueError("Находка не содержит точную цитату.")
    try:
        start = int(finding.get("start"))
        end = int(finding.get("end"))
    except (TypeError, ValueError):
        start = end = -1
    block = next(
        (
            item
            for item in blocks
            if item.core_start <= start < end <= item.core_end
            and item.anchor.text[start:end] == quote
        ),
        None,
    )
    if block is None:
        matches = []
        for candidate in blocks:
            cursor = candidate.core_start
            while True:
                found = candidate.anchor.text.find(quote, cursor, candidate.core_end)
                if found < 0:
                    break
                matches.append((candidate, found))
                cursor = found + max(len(quote), 1)
        try:
            occurrence = int(finding.get("occurrence") or 1)
        except (TypeError, ValueError) as exc:
            raise ValueError("Некорректный номер occurrence.") from exc
        if not matches or occurrence < 1 or occurrence > len(matches):
            raise ValueError("Цитата находки не совпадает с core-зоной документа.")
        if len(matches) > 1 and "occurrence" not in finding:
            raise ValueError(
                "Цитата неоднозначна; модель должна указать номер occurrence."
            )
        block, start = matches[occurrence - 1]
        end = start + len(quote)
    live_anchor = snapshot.by_id.get(anchor_id)
    if live_anchor is None or live_anchor.text_sha256 != block.anchor.text_sha256:
        raise ValueError("Якорь исходного документа изменился.")
    explanation = str(finding.get("explanation") or "").strip()
    replacement = str(finding.get("replacement") or "").strip()
    if replacement == quote:
        replacement = ""
    if not explanation:
        raise ValueError("Находка не содержит объяснение.")
    return {
        "start": live_anchor.start + start,
        "end": live_anchor.start + end,
        "quote": quote,
        "rule_id": str(finding.get("rule_id") or "").strip(),
        "explanation": explanation,
        "replacement": replacement,
    }


def _paragraph_style_id(paragraph: etree._Element) -> str:
    p_pr = paragraph.find(w("pPr"))
    style = p_pr.find(w("pStyle")) if p_pr is not None else None
    return (style.get(w("val")) if style is not None else "") or ""


def _heading_level(style_id: str) -> int:
    match = re.search(r"(?:heading|заголовок)\s*([1-9])", style_id, re.IGNORECASE)
    return int(match.group(1)) if match else 0


def _paragraph_structural_path(paragraph: etree._Element, ordinal: int) -> str:
    cell = next((node for node in paragraph.iterancestors() if node.tag == w("tc")), None)
    row = next((node for node in paragraph.iterancestors() if node.tag == w("tr")), None)
    table = next((node for node in paragraph.iterancestors() if node.tag == w("tbl")), None)
    if cell is None or row is None or table is None:
        return f"p-{ordinal}"
    body = next((node for node in table.iterancestors() if node.tag == w("body")), None)
    tables = list(body.iter(w("tbl"))) if body is not None else [table]
    rows = list(table.findall(w("tr")))
    cells = list(row.findall(w("tc")))
    paragraphs = list(cell.iter(w("p")))
    return (
        f"tbl-{tables.index(table) + 1}/row-{rows.index(row) + 1}/"
        f"cell-{cells.index(cell) + 1}/p-{paragraphs.index(paragraph) + 1}"
    )


def _anchor_segments(
    anchor: DocumentAnchor,
    max_chars: int,
) -> list[tuple[DocumentAnchor, int, int]]:
    if len(anchor.text) <= max_chars:
        return [(anchor, 0, len(anchor.text))]
    boundaries = [0]
    boundaries.extend(match.end() for match in _SENTENCE_END_RE.finditer(anchor.text))
    if boundaries[-1] != len(anchor.text):
        boundaries.append(len(anchor.text))
    segments = []
    start = 0
    cursor = 1
    while start < len(anchor.text):
        limit = min(start + max_chars, len(anchor.text))
        candidates = [value for value in boundaries[cursor:] if start < value <= limit]
        end = candidates[-1] if candidates else limit
        segments.append((anchor, start, end))
        start = end
        while cursor < len(boundaries) and boundaries[cursor] <= start:
            cursor += 1
    return segments


def _overlap_segments(
    segments: list[tuple[DocumentAnchor, int, int]],
    limit: int,
    *,
    from_end: bool,
) -> list[tuple[DocumentAnchor, int, int]]:
    if not segments or limit <= 0:
        return []
    source = list(reversed(segments)) if from_end else segments
    selected = []
    size = 0
    for item in source:
        selected.append(item)
        size += item[2] - item[1]
        if size >= limit:
            break
    if from_end:
        selected.reverse()
    return selected
