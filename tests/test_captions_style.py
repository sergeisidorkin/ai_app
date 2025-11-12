import io, zipfile, re, base64
from macroops_app.docx_builder import build_docx_from_ops

def test_caption_style_id_is_caption():
    ops = [
        {"op":"table.start","cols":2},
        {"op":"table.row","header":True},
        {"op":"table.cell","text":"A"},
        {"op":"table.cell","text":"B"},
        {"op":"table.end"},
        {"op":"caption.add","target":"table","text":"Пример"},
    ]
    b64 = build_docx_from_ops(ops)
    raw = io.BytesIO(base64.b64decode(b64))
    with zipfile.ZipFile(raw) as z:
        styles = z.read("word/styles.xml").decode("utf-8", "ignore")
        docxml = z.read("word/document.xml").decode("utf-8", "ignore")
    assert 'w:styleId="Caption"' in styles
    assert re.search(r'<w:pStyle[^>]+w:val="Caption"', docxml)