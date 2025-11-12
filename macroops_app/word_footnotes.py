# macroops_app/word_footnotes.py
from __future__ import annotations
from typing import Optional
from lxml import etree
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

FOOTNOTES_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes"
STYLES_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles"

def _find_footnotes_part(doc_part) -> Optional[object]:
    for rel in doc_part.rels.values():
        try:
            if rel.reltype == FOOTNOTES_REL:
                return rel.target_part
        except Exception:
            continue
    return None

def _find_styles_part(doc_part):
    for rel in doc_part.rels.values():
        try:
            if rel.reltype == STYLES_REL:
                return rel.target_part
        except Exception:
            continue
    return None

def _ensure_footnote_styles(doc_part) -> None:
    try:
        st = _find_styles_part(doc_part)
        if not st:
            return
        root = parse_xml(st.blob)
        W = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}

        def has_style(typ: str, style_id: str, names: tuple[str, ...]) -> bool:
            if root.xpath(f"//w:style[@w:type='{typ}' and @w:styleId='{style_id}']", namespaces=W):
                return True
            for nm in names:
                if root.xpath("//w:style[@w:type=$t][w:name[@w:val=$n]]", namespaces=W, t=typ, n=nm):
                    return True
            return False

        def append_xml(xml_str: str):
            el = parse_xml(xml_str.encode("utf-8"))
            root.append(el)

        # paragraph: FootnoteText
        if not has_style("paragraph", "FootnoteText", ("Footnote Text", "Текст сноски")):
            append_xml("""
<w:style xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" w:type="paragraph" w:styleId="FootnoteText">
  <w:name w:val="Footnote Text"/>
  <w:basedOn w:val="Normal"/>
  <w:qFormat/>
  <w:pPr><w:spacing w:after="0"/></w:pPr>
</w:style>""")

        # character: FootnoteReference
        if not has_style("character", "FootnoteReference", ("Footnote Reference", "Знак сноски")):
            append_xml("""
<w:style xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" w:type="character" w:styleId="FootnoteReference">
  <w:name w:val="Footnote Reference"/>
  <w:basedOn w:val="DefaultParagraphFont"/>
  <w:uiPriority w:val="99"/><w:semiHidden/><w:unhideWhenUsed/>
  <w:rPr><w:vertAlign w:val="superscript"/></w:rPr>
</w:style>""")

        xml_bytes = etree.tostring(root, encoding="UTF-8", standalone=True)
        try:    st.blob = xml_bytes
        except: st._blob = xml_bytes
    except Exception:
        pass

def _next_footnote_id(footnotes_elm) -> int:
    # берём максимум по обычным (без w:type) сноскам
    max_id = 0
    tag_footnote = qn("w:footnote")
    attr_id = qn("w:id")
    attr_type = qn("w:type")
    for fn in footnotes_elm.iterchildren(tag_footnote):
        if fn.get(attr_type):  # separator / continuationSeparator
            continue
        try:
            fid = int(fn.get(attr_id, "0"))
            if fid > max_id:
                max_id = fid
        except Exception:
            pass
    return max_id + 1 if max_id >= 0 else 1

def _resolve_footnote_ref_style_id(doc_part) -> str:
    """
    Возвращает styleId для КОМПОНЕНТА 'Знак сноски' (character style).
    Ищем:
      1) styleId='FootnoteReference'
      2) по имени: 'Footnote Reference' / 'Знак сноски'
      3) фолбэк: 'FootnoteReference'
    """
    try:
        st = _find_styles_part(doc_part)
        if not st:
            return "FootnoteReference"
        root = parse_xml(st.blob)
        W = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}

        hit = root.xpath("//w:style[@w:type='character' and @w:styleId='FootnoteReference']", namespaces=W)
        if hit:
            return "FootnoteReference"

        for human in ("Footnote Reference", "Знак сноски"):
            hit = root.xpath("//w:style[@w:type='character'][w:name[@w:val=$n]]",
                             namespaces=W, n=human)
            if hit:
                sid = hit[0].get(qn("w:styleId"))
                if sid:
                    return sid
    except Exception:
        pass
    return "FootnoteReference"

def _resolve_footnote_style_id(doc_part) -> str:
    """
    Возвращает styleId для абзацев сносок. Приоритет:
    1) styleId="FootnoteText" если есть в styles.xml
    2) Любой стиль с именем w:name/@w:val ∈ {"Footnote Text","Текст сноски"}
       (вернём его фактический styleId)
    3) Фолбэк: "FootnoteText"
    """
    try:
        st = _find_styles_part(doc_part)
        if not st:
            return "FootnoteText"
        root = parse_xml(st.blob)
        W = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}

        # 1) Прямо по styleId
        hit = root.xpath("//w:style[@w:type='paragraph' and @w:styleId='FootnoteText']", namespaces=W)
        if hit:
            return "FootnoteText"

        # 2) По локализованному имени
        for human in ("Footnote Text", "Текст сноски"):
            hit = root.xpath("//w:style[@w:type='paragraph'][w:name[@w:val=$n]]",
                             namespaces=W, n=human)
            if hit:
                # возьмём фактический styleId (может быть кастомным)
                sid = hit[0].get(qn("w:styleId"))
                if sid:
                    return sid
    except Exception:
        pass
    return "FootnoteText"

def _append_footnote(footnotes_elm, footnote_id: int, text: str, *, doc_part=None) -> None:
    w = lambda x: qn(f"w:{x}")

    fn = OxmlElement("w:footnote")
    fn.set(w("id"), str(footnote_id))

    # абзац с правильным стилем «FootnoteText»
    p = OxmlElement("w:p")
    pPr = OxmlElement("w:pPr")
    pStyle = OxmlElement("w:pStyle")
    p_style_id = _resolve_footnote_style_id(doc_part) if doc_part is not None else "FootnoteText"
    pStyle.set(w("val"), p_style_id)
    pPr.append(pStyle)
    p.insert(0, pPr)

    # первый run внизу — «номер сноски» со знаковым стилем и надстрочным
    r1 = OxmlElement("w:r")
    r1Pr = OxmlElement("w:rPr")
    r1Style = OxmlElement("w:rStyle")
    r1Style.set(w("val"), _resolve_footnote_ref_style_id(doc_part) if doc_part else "FootnoteReference")
    r1Pr.append(r1Style)
    r1Sup = OxmlElement("w:vertAlign"); r1Sup.set(w("val"), "superscript")
    r1Pr.append(r1Sup)
    r1.append(r1Pr)
    ref = OxmlElement("w:footnoteRef")  # нижний маркер
    r1.append(ref)
    p.append(r1)

    # пробел
    rSpace = OxmlElement("w:r")
    tSpace = OxmlElement("w:t"); tSpace.text = " "
    rSpace.append(tSpace)
    p.append(rSpace)

    # текст сноски
    r2 = OxmlElement("w:r")
    t = OxmlElement("w:t")
    if text.startswith(" ") or text.endswith(" "):
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t.text = text
    r2.append(t)
    p.append(r2)

    fn.append(p)
    footnotes_elm.append(fn)

def _insert_reference_run(paragraph: Paragraph, footnote_id: int) -> None:
    w = lambda x: qn(f"w:{x}")

    r = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")

    rStyle = OxmlElement("w:rStyle")
    rStyle.set(w("val"), _resolve_footnote_ref_style_id(paragraph.part))
    rPr.append(rStyle)

    # страховка, если стиль «FootnoteReference» в целевом документе не надстрочный
    rSup = OxmlElement("w:vertAlign"); rSup.set(w("val"), "superscript")
    rPr.append(rSup)

    r.append(rPr)

    ref = OxmlElement("w:footnoteReference")  # верхний маркер (в тексте)
    ref.set(w("id"), str(footnote_id))
    r.append(ref)

    paragraph._p.append(r)

    # мин. отступ после маркера
    rSpace = OxmlElement("w:r")
    tSpace = OxmlElement("w:t"); tSpace.text = " "
    rSpace.append(tSpace)
    paragraph._p.append(rSpace)

def add_footnote_to_paragraph(paragraph: Paragraph, text: str) -> bool:
    try:
        doc_part = paragraph.part
        fn_part = _find_footnotes_part(doc_part)
        if fn_part is None:
            return False

        # 1) стили — до модификации footnotes.xml
        _ensure_footnote_styles(doc_part)

        # 2) подчищаем пустые сноски
        root = parse_xml(fn_part.blob)
        next_id = _next_footnote_id(root)

        # 3) добавляем тело сноски + ставим ссылку в абзац
        _append_footnote(root, next_id, text, doc_part=doc_part)
        _insert_reference_run(paragraph, next_id)

        # 4) сохраняем part
        xml_bytes = etree.tostring(root, encoding="UTF-8", standalone=True)
        try:    fn_part.blob = xml_bytes
        except: fn_part._blob = xml_bytes

        return True
    except Exception:
        return False