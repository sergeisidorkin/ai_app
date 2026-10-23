"""Visual line wraps taken from a rendered PDF instead of font-metric estimates.

The DOCX is rendered by a real layout engine (ONLYOFFICE Document Server or
LibreOffice), the PDF text is read back together with its coordinates, grouped
into visual lines and aligned to the text produced by extract_document_text().
A regular space between two consecutive words of one paragraph that end up on
different PDF lines is a line-end space.
"""
from __future__ import annotations

import difflib
import io
import logging
import math
import unicodedata

log = logging.getLogger(__name__)

# Invisible characters that never reach the PDF text.
_DROP_CHARS = frozenset("\xad\u200b\u200c\u200d\u2060\ufeff")
# Word separators on both sides. The non-breaking space is a separator for
# matching only: it is never reported as a line-end space.
_SPACE_CHARS = frozenset(" \t\r\n\xa0\u2002\u2003\u2007\u2009\u200a\u202f\u3000")
# A chunk whose baseline is within this share of the font size belongs to the
# current line (superscripts and subscripts are shifted by about a third).
_LINE_TOLERANCE = 0.5
# Below this share of matched words the PDF text is not this document
# (no ToUnicode map, wrong file) and the estimate is used instead.
_MIN_COVERAGE = 0.5
# Character-level recovery only for small unmatched gaps (hyphenated or merged
# words); long gaps are tables of contents, page numbers and the like.
_MAX_GAP_CHARS = 2000


class RenderedLayoutError(ValueError):
    """The PDF text cannot be aligned to the document text."""


def line_end_spaces_from_pdf(text: str, pdf_bytes: bytes) -> frozenset[int]:
    """Offsets of regular spaces after which the rendered document starts a new line."""
    lines = extract_pdf_lines(pdf_bytes)
    return line_end_spaces_from_lines(text, lines)


def line_end_spaces_from_lines(text: str, lines: list[list[str]]) -> frozenset[int]:
    """Same as line_end_spaces_from_pdf() for already extracted lines of PDF tokens."""
    tokens = _doc_tokens(text or "")
    if not tokens:
        return frozenset()
    first, last = _align(tokens, lines)
    coverage = _coverage(tokens, first)
    if coverage < _MIN_COVERAGE:
        raise RenderedLayoutError(
            f"Текст PDF совпал с документом только на {int(coverage * 100)}%."
        )
    return frozenset(_line_ends(text, tokens, first, last))


def extract_pdf_lines(pdf_bytes: bytes) -> list[list[str]]:
    """Tokens of every visual line of the PDF, in content-stream order."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    lines: list[list[str]] = []
    for page in reader.pages:
        chunks: list[tuple[str, float, float]] = []

        def visit(value, cm, tm, _font, font_size, _chunks=chunks):
            if not value or not value.strip():
                return
            matrix = _mult(tm, cm)
            a, b = matrix[0], matrix[1]
            scale = math.hypot(a, b) or 1.0
            size = abs(float(font_size or 0)) * scale or scale
            # Rotated text (vertical table headers) is grouped by x instead of y.
            key = matrix[4] if abs(b) > abs(a) else matrix[5]
            _chunks.append((value, float(key), float(size)))

        page.extract_text(visitor_text=visit)
        lines.extend(_group_lines(chunks))
    return lines


def _mult(m: list[float], n: list[float]) -> list[float]:
    return [
        m[0] * n[0] + m[1] * n[2],
        m[0] * n[1] + m[1] * n[3],
        m[2] * n[0] + m[3] * n[2],
        m[2] * n[1] + m[3] * n[3],
        m[4] * n[0] + m[5] * n[2] + n[4],
        m[4] * n[1] + m[5] * n[3] + n[5],
    ]


def _group_lines(chunks: list[tuple[str, float, float]]) -> list[list[str]]:
    """Consecutive chunks with the same baseline form one visual line.

    The baseline of the line is that of its largest text, so a superscript does
    not drag the following regular text onto a new line.
    """
    lines: list[list[str]] = []
    parts: list[str] = []
    line_key = 0.0
    line_size = 0.0
    for value, key, size in chunks:
        if parts and abs(key - line_key) > _LINE_TOLERANCE * max(size, line_size):
            lines.append(parts)
            parts = []
        if not parts or size > line_size:
            line_key, line_size = key, size
        parts.append(value)
    if parts:
        lines.append(parts)
    out: list[list[str]] = []
    for group in lines:
        tokens = " ".join(group).split()
        if tokens:
            out.append(tokens)
    return out


def _norm_char(ch: str) -> str:
    if ch in _DROP_CHARS:
        return ""
    if ch == "\u2011":
        return "-"
    return unicodedata.normalize("NFKC", ch)


def _norm_token(value: str) -> str:
    return "".join(_norm_char(ch) for ch in value)


def _doc_tokens(text: str) -> list[tuple[int, int, list[tuple[str, int]]]]:
    """(start, end, [(normalized char, offset), ...]) for every word of the document text."""
    tokens: list[tuple[int, int, list[tuple[str, int]]]] = []
    n = len(text)
    i = 0
    while i < n:
        if text[i] in _SPACE_CHARS:
            i += 1
            continue
        j = i
        while j < n and text[j] not in _SPACE_CHARS:
            j += 1
        chars: list[tuple[str, int]] = []
        for k in range(i, j):
            for ch in _norm_char(text[k]):
                chars.append((ch, k))
        if chars:
            tokens.append((i, j, chars))
        i = j
    return tokens


def _align(
    tokens: list[tuple[int, int, list[tuple[str, int]]]],
    lines: list[list[str]],
) -> tuple[list[int | None], list[int | None]]:
    """PDF line of the first and of the last character of every document word."""
    pdf_tokens: list[tuple[str, int]] = []
    for line_id, words in enumerate(lines):
        for word in words:
            normalized = _norm_token(word)
            if normalized:
                pdf_tokens.append((normalized, line_id))
    doc_words = ["".join(ch for ch, _ in chars) for _s, _e, chars in tokens]
    pdf_words = [word for word, _ in pdf_tokens]
    first: list[int | None] = [None] * len(tokens)
    last: list[int | None] = [None] * len(tokens)
    if not pdf_words:
        return first, last
    used = [False] * len(pdf_tokens)
    matcher = difflib.SequenceMatcher(None, doc_words, pdf_words)
    prev_i = prev_j = 0
    for i, j, size in matcher.get_matching_blocks():
        if i > prev_i and j > prev_j:
            _recover_gap(tokens, prev_i, i, pdf_tokens, prev_j, j, first, last)
        for k in range(size):
            line_id = pdf_tokens[j + k][1]
            first[i + k] = line_id
            last[i + k] = line_id
            used[j + k] = True
        prev_i, prev_j = i + size, j + size
    _align_leftovers(doc_words, pdf_tokens, used, first, last)
    return first, last


# Segments the PDF emits out of document order (frames, cells drawn row by row)
# are paired in a second pass; only runs of several words count, so a stray
# «в» is never paired with an unrelated «в».
_MIN_LEFTOVER_BLOCK = 3


def _align_leftovers(doc_words, pdf_tokens, used, first, last) -> None:
    doc_index = [i for i, line_id in enumerate(first) if line_id is None]
    pdf_index = [j for j, flag in enumerate(used) if not flag]
    if len(doc_index) < _MIN_LEFTOVER_BLOCK or len(pdf_index) < _MIN_LEFTOVER_BLOCK:
        return
    matcher = difflib.SequenceMatcher(
        None,
        [doc_words[i] for i in doc_index],
        [pdf_tokens[j][0] for j in pdf_index],
    )
    for i, j, size in matcher.get_matching_blocks():
        if size < _MIN_LEFTOVER_BLOCK:
            continue
        for k in range(size):
            index = doc_index[i + k]
            line_id = pdf_tokens[pdf_index[j + k]][1]
            first[index] = line_id
            last[index] = line_id


def _recover_gap(tokens, doc_lo, doc_hi, pdf_tokens, pdf_lo, pdf_hi, first, last) -> None:
    """Character alignment of words the word matcher could not pair.

    Handles words hyphenated across lines («рацио-» + «нального»), words glued
    by the PDF text extraction and words split by a superscript.
    """
    doc_chars: list[tuple[str, int]] = []
    for index in range(doc_lo, doc_hi):
        for ch, _offset in tokens[index][2]:
            doc_chars.append((ch, index))
    pdf_chars: list[tuple[str, int]] = []
    for index in range(pdf_lo, pdf_hi):
        word, line_id = pdf_tokens[index]
        for ch in word:
            pdf_chars.append((ch, line_id))
    if not doc_chars or not pdf_chars:
        return
    if len(doc_chars) > _MAX_GAP_CHARS or len(pdf_chars) > _MAX_GAP_CHARS:
        return
    matcher = difflib.SequenceMatcher(
        None,
        [ch for ch, _ in doc_chars],
        [ch for ch, _ in pdf_chars],
        autojunk=False,
    )
    for i, j, size in matcher.get_matching_blocks():
        if size < 2:
            continue
        for k in range(size):
            index = doc_chars[i + k][1]
            line_id = pdf_chars[j + k][1]
            if first[index] is None:
                first[index] = line_id
            last[index] = line_id


def _coverage(tokens, first) -> float:
    total = 0
    matched = 0
    for (start, end, chars), line_id in zip(tokens, first):
        if sum(1 for ch, _ in chars if ch.isalnum()) < 2:
            continue
        total += 1
        if line_id is not None:
            matched += 1
    if not total:
        return 1.0
    return matched / total


def _line_ends(text: str, tokens, first, last) -> set[int]:
    ends: set[int] = set()
    for index in range(len(tokens) - 1):
        _s1, end_a, _c1 = tokens[index]
        start_b, _e2, _c2 = tokens[index + 1]
        gap = text[end_a:start_b]
        if "\n" in gap or "\r" in gap:
            continue
        line_a = last[index]
        line_b = first[index + 1]
        if line_a is None or line_b is None or line_b <= line_a:
            continue
        for k in range(end_a, start_b):
            if text[k] == " ":
                ends.add(k)
    return ends
