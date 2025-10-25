# docops_queue/urlkeys.py
import re
import urllib.parse as up

def make_doc_key(url: str) -> str:
    """
    Приводит любой OneDrive/SharePoint URL к ключу сопоставления одного и того же документа.
    Поддержаны:
      - share-ссылки вида: /:w:/(g|r)/personal/<user>/.../<file_token>
      - прямые пути:        /personal/<user>/Documents/.../<filename.docx>
    """
    if not url:
        return ""

    # 1) убрать схему + query/fragment, нормализовать путь
    try:
        u = up.urlsplit(url.strip())
    except Exception:
        return url.strip().lower()

    host = (u.netloc or "").lower()
    # пробуем распаковать %XX, привести к lower
    path = up.unquote(u.path or "").strip()
    path = re.sub(r"/+", "/", path).rstrip("/").lower()

    # 2) share-ссылка: "/:w:/(g|r)/personal/<user>/.../<token>"
    m = re.match(r"^/:w:/(?:g|r)/(personal/[^/]+)/(?:.*?/)?([^/]+)$", path)
    if m:
        user = m.group(1)            # "personal/<user>"
        token = m.group(2)           # "eqll6wkb..." (последний сегмент)
        return f"{host}/{user}/{token}"

    # 3) обычный личный путь: "/personal/<user>/.../<filename.docx>"
    n = re.match(r"^(?:/)?(personal/[^/]+/.*/)([^/]+)$", path)
    if n:
        prefix = n.group(1)          # "personal/<user>/.../"
        fname  = n.group(2)          # "document 3.docx"
        return f"{host}/{prefix}{fname}"

    # 4) fallback — хотя бы host + path
    return f"{host}{path}"