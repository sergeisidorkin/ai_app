from __future__ import annotations

from lxml import etree

from .docx_comments import DOCUMENT_XML, DocxCommentError, _is_deleted, _read_zip, w

A4_WIDTH_TWIPS = 11906
DEFAULT_MARGIN_TWIPS = 1440
DEFAULT_SZ_HP = 22
TAB_TWIPS = 720
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
# Доли em × 1000, близко к Times New Roman / Cambria / Calibri для оценки переноса.
# Кириллическая «т» не узкая (в отличие от латинской t).
_NARROW = set("ijlI.,;:'!|")
_WIDE = set("mwMWШшЩщЖжЮюЫыФф")
_LETTER_EM = 510
_UPPER_EM = 700
# Consolas / Menlo / Cascadia ≈ 0.55em; Courier ≈ 0.60em. В отчётах typewriter — Consolas.
_MONO_EM = 550
_MONO_EM_BY_FONT = {
    "courier": 600,
    "courier new": 600,
}
_BOLD_NUM = 108
_ITALIC_NUM = 104
_MONO_FONTS = {
    "consolas",
    "courier",
    "courier new",
    "menlo",
    "monaco",
    "lucida console",
    "andale mono",
    "cascadia mono",
    "cascadia code",
}
_CHAR_EM = {
    " ": 250,
    "\u00a0": 250,
    ".": 250,
    ",": 250,
    "-": 333,
    "(": 333,
    ")": 333,
    "«": 500,
    "»": 500,
    "№": 780,
    "\u2013": 500,
    "\u2014": 1000,
}


def extract_line_end_spaces(docx_bytes: bytes) -> frozenset[int]:
    """Смещения обычных пробелов, после которых Word переносит визуальную строку."""
    parts = _read_zip(docx_bytes)
    xml = parts.get(DOCUMENT_XML)
    if not xml:
        raise DocxCommentError("В файле нет word/document.xml.")
    try:
        root = etree.fromstring(xml)
    except etree.XMLSyntaxError as exc:
        raise DocxCommentError("Некорректный word/document.xml.") from exc
    styles = _style_sheet(parts.get("word/styles.xml"))
    numbering = _numbering_map(parts.get("word/numbering.xml"))
    body = root.find(w("body"))
    if body is None:
        return frozenset()
    page_w, margin_l, margin_r = _page_box(body)
    usable = max(page_w - margin_l - margin_r, 200)
    ends: set[int] = set()
    offset = 0
    for paragraph in body.iter(w("p")):
        para_w = _paragraph_widths(paragraph, usable, styles, numbering)
        items, offset = _paragraph_items(paragraph, offset, styles)
        ends.update(_wrap_space_offsets(items, para_w[0], para_w[1]))
        offset += 1
    return frozenset(ends)


def _style_sheet(styles_xml: bytes | None) -> dict:
    default_sz = DEFAULT_SZ_HP
    sz_by_style: dict[str, int] = {}
    based_on: dict[str, str] = {}
    ind_by_style: dict[str, dict[str, int]] = {}
    rpr_by_style: dict[str, dict] = {}
    numpr_by_style: dict[str, tuple[str, int]] = {}
    empty = {
        "default_sz": default_sz,
        "sz": sz_by_style,
        "based": based_on,
        "ind": ind_by_style,
        "rpr": rpr_by_style,
        "numpr": numpr_by_style,
    }
    if not styles_xml:
        return empty
    try:
        root = etree.fromstring(styles_xml)
    except etree.XMLSyntaxError:
        return empty
    rpr = root.find(f"{w('docDefaults')}/{w('rPrDefault')}/{w('rPr')}")
    parsed = _sz_of(rpr)
    if parsed:
        default_sz = parsed
    for style in root.iter(w("style")):
        style_id = style.get(w("styleId")) or ""
        if not style_id:
            continue
        based = style.find(w("basedOn"))
        if based is not None and based.get(w("val")):
            based_on[style_id] = based.get(w("val"))
        rpr_attrs = _rpr_attrs(style.find(w("rPr"))) or _rpr_attrs(style.find(f"{w('pPr')}/{w('rPr')}"))
        if rpr_attrs:
            rpr_by_style[style_id] = rpr_attrs
        sz = rpr_attrs.get("sz")
        if sz:
            sz_by_style[style_id] = sz
        ind = _ind_of(style.find(w("pPr")))
        if ind:
            ind_by_style[style_id] = ind
        num_id, ilvl = _num_pr_of(style.find(w("pPr")))
        if num_id:
            numpr_by_style[style_id] = (num_id, ilvl)
    return {
        "default_sz": default_sz,
        "sz": sz_by_style,
        "based": based_on,
        "ind": ind_by_style,
        "rpr": rpr_by_style,
        "numpr": numpr_by_style,
    }


def _style_ind(styles: dict, style_id: str) -> dict[str, int]:
    seen: set[str] = set()
    current = style_id
    while current and current not in seen:
        seen.add(current)
        if current in styles["ind"]:
            return styles["ind"][current]
        current = styles["based"].get(current, "")
    return {}


def _numbering_map(numbering_xml: bytes | None) -> dict[str, dict[int, dict[str, int]]]:
    """numId → {ilvl: {left, right}}. hanging маркера в ширину текста не входит."""
    if not numbering_xml:
        return {}
    try:
        root = etree.fromstring(numbering_xml)
    except etree.XMLSyntaxError:
        return {}
    abstracts: dict[str, dict[int, dict[str, int]]] = {}
    for absn in root.iter(w("abstractNum")):
        aid = absn.get(w("abstractNumId")) or ""
        levels: dict[int, dict[str, int]] = {}
        for lvl in absn.findall(w("lvl")):
            try:
                ilvl = int(lvl.get(w("ilvl")) or 0)
            except ValueError:
                ilvl = 0
            ind = _ind_of(lvl.find(w("pPr")))
            left_right = {key: ind[key] for key in ("left", "right") if key in ind}
            if left_right:
                levels[ilvl] = left_right
        if aid:
            abstracts[aid] = levels
    out: dict[str, dict[int, dict[str, int]]] = {}
    for num in root.findall(w("num")):
        nid = num.get(w("numId")) or ""
        if not nid or nid == "0":
            continue
        abs_el = num.find(w("abstractNumId"))
        aid = abs_el.get(w("val")) if abs_el is not None else ""
        out[nid] = dict(abstracts.get(aid) or {})
    return out


def _num_pr_of(p_pr: etree._Element | None) -> tuple[str, int]:
    if p_pr is None:
        return "", 0
    num_pr = p_pr.find(w("numPr"))
    if num_pr is None:
        return "", 0
    num_id_el = num_pr.find(w("numId"))
    ilvl_el = num_pr.find(w("ilvl"))
    num_id = (num_id_el.get(w("val")) or "") if num_id_el is not None else ""
    if num_id == "0":
        num_id = ""
    ilvl = 0
    if ilvl_el is not None:
        try:
            ilvl = int(ilvl_el.get(w("val")) or 0)
        except ValueError:
            ilvl = 0
    return num_id, ilvl


def _style_num_pr(styles: dict, style_id: str) -> tuple[str, int]:
    seen: set[str] = set()
    current = style_id
    while current and current not in seen:
        seen.add(current)
        if current in styles.get("numpr", {}):
            return styles["numpr"][current]
        current = styles.get("based", {}).get(current, "")
    return "", 0


def _numbering_left(paragraph: etree._Element, styles: dict, numbering: dict) -> dict[str, int]:
    p_pr = paragraph.find(w("pPr"))
    num_id, ilvl = _num_pr_of(p_pr)
    if not num_id:
        style_id = ""
        if p_pr is not None:
            p_style = p_pr.find(w("pStyle"))
            if p_style is not None:
                style_id = p_style.get(w("val")) or ""
        num_id, ilvl = _style_num_pr(styles, style_id)
    if not num_id:
        return {}
    levels = numbering.get(num_id) or {}
    return dict(levels.get(ilvl) or levels.get(0) or {})


def _page_box(body: etree._Element) -> tuple[int, int, int]:
    sect = None
    for node in body.iter(w("sectPr")):
        sect = node
    if sect is None:
        return A4_WIDTH_TWIPS, DEFAULT_MARGIN_TWIPS, DEFAULT_MARGIN_TWIPS
    pg_sz = sect.find(w("pgSz"))
    pg_mar = sect.find(w("pgMar"))
    width = _int_attr(pg_sz, "w", A4_WIDTH_TWIPS)
    left = _int_attr(pg_mar, "left", DEFAULT_MARGIN_TWIPS)
    right = _int_attr(pg_mar, "right", DEFAULT_MARGIN_TWIPS)
    return width, left, right


def _paragraph_widths(
    paragraph: etree._Element,
    usable: int,
    styles: dict,
    numbering: dict | None = None,
) -> tuple[int, int]:
    cell_w = _cell_width(paragraph)
    content = cell_w if cell_w else usable
    p_pr = paragraph.find(w("pPr"))
    style_id = ""
    if p_pr is not None:
        p_style = p_pr.find(w("pStyle"))
        if p_style is not None:
            style_id = p_style.get(w("val")) or ""
    ind = dict(_numbering_left(paragraph, styles, numbering or {}))
    ind.update(_style_ind(styles, style_id))
    ind.update(_ind_of(p_pr))
    left = ind.get("left", 0)
    right = ind.get("right", 0)
    first = ind.get("firstLine", 0)
    hanging = ind.get("hanging", 0)
    rest = max(content - left - right, 200)
    first_line = max(rest - first + hanging, 200)
    return first_line, rest


def _paragraph_items(paragraph: etree._Element, offset: int, styles: dict) -> tuple[list[tuple], int]:
    items: list[tuple] = []
    p_pr = paragraph.find(w("pPr"))
    style_id = ""
    if p_pr is not None:
        p_style = p_pr.find(w("pStyle"))
        if p_style is not None:
            style_id = p_style.get(w("val")) or ""
    para_format = _merged_style_format(styles, style_id)
    p_mark = _rpr_attrs(None if p_pr is None else p_pr.find(w("rPr")))
    p_rstyle = p_mark.pop("rStyle", "")
    if p_rstyle:
        para_format.update(_merged_style_format(styles, p_rstyle))
    para_format.update(p_mark)
    for node in paragraph.iter():
        if _is_deleted(node):
            continue
        nested = _in_descendant_p(node, paragraph)
        tag = node.tag
        if tag == w("t"):
            fmt = _run_format(node, para_format, styles)
            for ch in node.text or "":
                width = _char_width(
                    ch,
                    fmt["sz"],
                    bold=fmt["bold"],
                    italic=fmt["italic"],
                    font=fmt.get("font") or "",
                    mono=fmt["mono"],
                )
                items.append(("space" if ch == " " else "word", offset, width))
                offset += 1
        elif nested:
            continue
        elif tag in (w("br"), w("cr")):
            items.append(("br", None, 0))
            offset += 1
        elif tag == w("tab"):
            items.append(("tab", None, 0))
        elif tag in (w("drawing"), w("pict"), w("object")):
            items.append(("word", None, _drawing_width(node)))
    return items, offset


def _wrap_space_offsets(items: list[tuple], first_w: int, rest_w: int) -> set[int]:
    ends: set[int] = set()
    x = 0
    max_w = first_w
    word_w = 0
    gap_w = 0
    gap_off = None

    def flush_word():
        nonlocal x, word_w, gap_w, gap_off, max_w
        if word_w <= 0:
            x += gap_w
            gap_w = 0
            return
        extra = word_w if x <= 0 else gap_w + word_w
        if x > 0 and x + extra > max_w:
            if gap_off is not None:
                ends.add(gap_off)
            x = word_w
            max_w = rest_w
        else:
            x += extra
        word_w = 0
        gap_w = 0
        gap_off = None

    def force_br():
        nonlocal x, word_w, gap_w, gap_off, max_w
        flush_word()
        if gap_off is not None:
            ends.add(gap_off)
        x = 0
        max_w = rest_w
        gap_w = 0
        gap_off = None
        word_w = 0

    for kind, offset, width in items:
        if kind == "br":
            force_br()
        elif kind == "space":
            flush_word()
            gap_w += width
            gap_off = offset
        elif kind == "tab":
            flush_word()
            stop = TAB_TWIPS
            tab_w = stop - (x % stop)
            if tab_w <= 0:
                tab_w = stop
            gap_w += tab_w
        else:
            word_w += width
    flush_word()
    return ends


def _default_format(styles: dict) -> dict:
    return {
        "sz": styles.get("default_sz") or DEFAULT_SZ_HP,
        "bold": False,
        "italic": False,
        "font": "",
        "mono": False,
    }


def _merged_style_format(styles: dict, style_id: str) -> dict:
    state = _default_format(styles)
    state.update(_style_rpr_overlay(styles, style_id))
    state["mono"] = _is_mono(state.get("font") or "")
    return state


def _style_rpr_overlay(styles: dict, style_id: str) -> dict:
    overlay: dict = {}
    for sid in _style_chain(styles, style_id):
        overlay.update(styles.get("rpr", {}).get(sid) or {})
    overlay.pop("rStyle", None)
    return overlay


def _style_chain(styles: dict, style_id: str) -> list[str]:
    chain: list[str] = []
    seen: set[str] = set()
    current = style_id
    while current and current not in seen:
        seen.add(current)
        chain.append(current)
        current = styles.get("based", {}).get(current, "")
    chain.reverse()
    return chain


def _run_format(t_node: etree._Element, para_format: dict, styles: dict) -> dict:
    state = dict(para_format)
    node = t_node.getparent()
    while node is not None and node.tag != w("r"):
        node = node.getparent()
    if node is None:
        state["mono"] = _is_mono(state.get("font") or "")
        return state
    attrs = _rpr_attrs(node.find(w("rPr")))
    r_style = attrs.pop("rStyle", "")
    if r_style:
        state.update(_style_rpr_overlay(styles, r_style))
    state.update(attrs)
    state["mono"] = _is_mono(state.get("font") or "")
    return state


def _rpr_attrs(r_pr: etree._Element | None) -> dict:
    if r_pr is None:
        return {}
    out: dict = {}
    sz = _sz_of(r_pr)
    if sz:
        out["sz"] = sz
    bold = _on_off(r_pr.find(w("b")))
    if bold is None:
        bold = _on_off(r_pr.find(w("bCs")))
    if bold is not None:
        out["bold"] = bold
    italic = _on_off(r_pr.find(w("i")))
    if italic is None:
        italic = _on_off(r_pr.find(w("iCs")))
    if italic is not None:
        out["italic"] = italic
    fonts = r_pr.find(w("rFonts"))
    if fonts is not None:
        name = fonts.get(w("ascii")) or fonts.get(w("hAnsi")) or fonts.get(w("cs")) or ""
        if name:
            out["font"] = name
    r_style = r_pr.find(w("rStyle"))
    if r_style is not None:
        style_id = r_style.get(w("val")) or ""
        if style_id:
            out["rStyle"] = style_id
    return out


def _on_off(el: etree._Element | None) -> bool | None:
    if el is None:
        return None
    val = (el.get(w("val")) or "").strip().lower()
    if val in ("0", "false", "off"):
        return False
    return True


def _is_mono(font: str) -> bool:
    return font.strip().lower() in _MONO_FONTS


def _sz_of(r_pr: etree._Element | None) -> int | None:
    if r_pr is None:
        return None
    sz = r_pr.find(w("sz"))
    if sz is None:
        sz = r_pr.find(w("szCs"))
    if sz is None:
        return None
    try:
        value = int(sz.get(w("val")) or 0)
    except ValueError:
        return None
    return value if value > 0 else None


def _ind_of(p_pr: etree._Element | None) -> dict[str, int]:
    if p_pr is None:
        return {}
    ind = p_pr.find(w("ind"))
    if ind is None:
        return {}
    out = {}
    for name in ("left", "right", "firstLine", "hanging", "start", "end"):
        value = _int_attr(ind, name, None)
        if value is not None:
            out["left" if name == "start" else "right" if name == "end" else name] = value
    return out


def _cell_width(paragraph: etree._Element) -> int | None:
    node = paragraph.getparent()
    while node is not None:
        if node.tag == w("tc"):
            tc_pr = node.find(w("tcPr"))
            if tc_pr is None:
                return None
            tc_w = tc_pr.find(w("tcW"))
            width = _dxa(tc_w)
            if not width:
                return None
            mar = tc_pr.find(w("tcMar"))
            left = _dxa(None if mar is None else mar.find(w("left"))) or 0
            right = _dxa(None if mar is None else mar.find(w("right"))) or 0
            return max(width - left - right, 200)
        if node.tag == w("body"):
            return None
        node = node.getparent()
    return None


def _dxa(node: etree._Element | None) -> int | None:
    if node is None:
        return None
    w_type = (node.get(w("type")) or "dxa").lower()
    if w_type not in ("dxa", ""):
        return None
    return _int_attr(node, "w", None)


def _drawing_width(node: etree._Element) -> int:
    for extent in node.iter(f"{{{WP_NS}}}extent"):
        cx = extent.get("cx")
        if cx:
            try:
                return max(int(cx) // 635, 0)
            except ValueError:
                return 0
    return 0


def _char_width(
    ch: str,
    sz_hp: int,
    bold: bool = False,
    italic: bool = False,
    font: str = "",
    mono: bool = False,
) -> int:
    em = max(int(sz_hp or DEFAULT_SZ_HP), 1) * 10
    if mono:
        units = _MONO_EM_BY_FONT.get((font or "").strip().lower(), _MONO_EM)
    elif ch in _CHAR_EM:
        units = _CHAR_EM[ch]
    elif ch.isdigit():
        units = 500
    elif ch in _NARROW:
        units = 280
    elif ch in _WIDE:
        units = 780
    elif ch.isalpha() and ch == ch.upper() and ch.lower() != ch:
        units = _UPPER_EM
    elif ch.isalpha():
        units = _LETTER_EM
    else:
        units = 400
    width = em * units // 1000
    if bold:
        width = width * _BOLD_NUM // 100
    if italic:
        width = width * _ITALIC_NUM // 100
    return width


def _in_descendant_p(node: etree._Element, paragraph: etree._Element) -> bool:
    parent = node.getparent()
    while parent is not None and parent is not paragraph:
        if parent.tag == w("p"):
            return True
        parent = parent.getparent()
    return False


def _int_attr(node: etree._Element | None, name: str, default):
    if node is None:
        return default
    raw = node.get(w(name))
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default
