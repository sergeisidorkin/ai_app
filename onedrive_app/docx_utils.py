from io import BytesIO
from docx import Document

def append_text(docx_bytes: bytes, text: str) -> bytes:
    buf = BytesIO(docx_bytes)
    doc = Document(buf)
    doc.add_paragraph(text or "")
    out = BytesIO()
    doc.save(out)
    return out.getvalue()