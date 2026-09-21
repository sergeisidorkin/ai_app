from __future__ import annotations

from django.db.models import Max

DEFAULT_MACRO_CODE = """def check(ctx):
    # ctx.text — плоский текст документа
    # верните [{"start": int, "end": int, "message": str, "links": [{"text": str, "url": str}]}, ...]
    findings = []
    return findings
"""

TPGR_COURSE_URL = "https://learn.imcmontanai.ru/course/section.php?id=12"
TPGR_COURSE_DASH_URL = "https://learn.imcmontanai.ru/course/section.php?id=5"
TPGR_COURSE_ABBR_URL = "https://learn.imcmontanai.ru/course/section.php?id=16"
TPGR_COURSE_NUM_URL = "https://learn.imcmontanai.ru/course/section.php?id=17"
TPGR_COURSE_QUOTE_URL = "https://learn.imcmontanai.ru/course/section.php?id=14"
TPGR_COURSE_LIST_URL = "https://learn.imcmontanai.ru/course/section.php?id=18"
TPGR_COURSE_SN_URL = "https://learn.imcmontanai.ru/course/section.php?id=13"
TPGR_COURSE_LINK_TEXT = "Ссылка на страницу курса TPGR"

_HELPERS = """
def in_angles(text, i):
    # VBA IsInAngleBrackets: баланс «<»/«>» в тексте до позиции.
    balance = 0
    for ch in text[:i]:
        if ch == "<":
            balance += 1
        elif ch == ">":
            balance -= 1
    return balance > 0

def is_num_ch(ch):
    # VBA IsNumeric для одного символа: цифра или десятичный разделитель.
    return bool(ch) and (ch.isdigit() or ch in ".,")

def course_links(url):
    return [{
        "text": "Ссылка на страницу курса TPGR",
        "url": url,
    }]
"""


def _code(body: str) -> str:
    rendered = _HELPERS.strip() + "\n\n" + body.strip() + "\n"
    for token, value in (
        ("{nbsp}", "\u00a0"),
        ("{endash}", "\u2013"),
        ("{emdash}", "\u2014"),
        ("{minus}", "\u2212"),
        ("{rdquo}", "\u201d"),
        ("{ldquo}", "\u201c"),
        ("{dprime}", "\u2033"),
    ):
        rendered = rendered.replace(token, value)
    return rendered


TPGR_MACROS = [
    {
        "name": "TPGR-ZN-01.03 Знак %",
        "description": "Знак % набирается слитно с числом, без пробела.",
        "code": _code(
            r"""
def check(ctx):
    # Блок 1 VBA TPGR(): найти «%», если перед ним пробел/nbsp и число — комментарий на число.
    text = ctx.text or ""
    findings = []
    msg = "TPGR-ZN-01.03: Знак % необходимо набирать слитно с числом в цифровой форме"
    start = 0
    while True:
        i = text.find("%", start)
        if i < 0:
            break
        prev = text[i - 1:i]
        if prev in (" ", "{nbsp}") and i >= 2 and text[i - 2].isdigit():
            left = i - 2
            while left > 0 and is_num_ch(text[left - 1]):
                left -= 1
            if not in_angles(text, i):
                findings.append({
                    "start": left,
                    "end": i - 1,
                    "message": msg,
                    "links": course_links("https://learn.imcmontanai.ru/course/section.php?id=12"),
                })
        start = i + 1
    return findings
"""
        ),
    },
    {
        "name": "TPGR-ZN-01.01 Знаки №, §, °C",
        "description": "№, § и °C отделяются от числа неразрывным пробелом.",
        "code": _code(
            r"""
def check(ctx):
    text = ctx.text or ""
    findings = []
    msg = "TPGR-ZN-01.01: Знаки №, §, °C отделяются от числа неразрывным пробелом"

    def near_number_or_upper(ch):
        return bool(ch) and (ch.isdigit() or (ch.isalpha() and ch == ch.upper()))

    for m in re.finditer(r"[№§]", text):
        i = m.start()
        if in_angles(text, i):
            continue
        nxt = text[i + 1:i + 2]
        if m.group() == "№" and nxt in ("", "\n"):
            continue
        if m.group() == "№" and nxt in (" ", "{nbsp}") and text[i + 2:i + 3] in ("", "\n"):
            continue
        hit = False
        if nxt == " ":
            if near_number_or_upper(text[i + 2:i + 3]):
                hit = True
        elif nxt.isdigit() or nxt.isalpha():
            hit = True
        if hit:
            findings.append({
                "start": i,
                "end": i + 1,
                "message": msg,
                "links": course_links("https://learn.imcmontanai.ru/course/section.php?id=12"),
            })
    for m in re.finditer("°C", text):
        if in_angles(text, m.start()):
            continue
        j = m.start()
        prev = text[j - 1:j]
        if prev == "{nbsp}":
            continue
        pos = j - 1
        if pos >= 0 and text[pos] == " ":
            pos -= 1
        if pos >= 0 and text[pos].isdigit():
            findings.append({
                "start": j,
                "end": m.end(),
                "message": msg,
                "links": course_links("https://learn.imcmontanai.ru/course/section.php?id=12"),
            })
    return findings
"""
        ),
    },
    {
        "name": "TPGR-TR-01.15 Длинное тире",
        "description": "Для разделения слов и предложений — длинное тире с пробелами, не дефис и не короткое тире.",
        "code": _code(
            r"""
def check(ctx):
    # Между словами нужно длинное тире с пробелами/nbsp с обеих сторон.
    # Дефис, короткое тире и минус между словами — ошибка, если есть отбивка.
    # «буква-буква» без пробелов — дефис в сложном слове, не ошибка.
    text = ctx.text or ""
    findings = []
    msg = "TPGR-TR-01.15: Для разделения слов и предложений используется длинное тире с отбивкой пробелами"
    marks = set("-{endash}{minus}{emdash}")
    emdash = "{emdash}"
    spaces = set(" {nbsp}")
    roman = set("IVXLCDMivxlcdm")

    def num_or_roman(ch):
        return bool(ch) and (ch.isdigit() or ch in roman)

    def neighbor(i, step):
        j = i + step
        while 0 <= j < len(text) and text[j] in spaces:
            j += step
        if 0 <= j < len(text):
            return text[j]
        return ""

    def add(i):
        if in_angles(text, i):
            return
        findings.append({
            "start": i,
            "end": i + 1,
            "message": msg,
            "links": course_links("https://learn.imcmontanai.ru/course/section.php?id=5"),
        })

    i = 0
    while i < len(text):
        ch = text[i]
        if ch not in marks:
            i += 1
            continue
        before = text[i - 1:i]
        after = text[i + 1:i + 2]
        left = neighbor(i, -1)
        right = neighbor(i, 1)
        if num_or_roman(left) and num_or_roman(right):
            i += 1
            continue
        if not (left.isalpha() and right.isalpha()):
            i += 1
            continue
        left_sp = before in spaces
        right_sp = after in spaces
        if ch == emdash and left_sp and right_sp:
            i += 1
            continue
        if ch == "-" and not left_sp and not right_sp:
            i += 1
            continue
        add(i)
        i += 1
    return findings
"""
        ),
    },
    {
        "name": "TPGR-TR-01.13 Короткое тире в диапазонах",
        "description": "В цифровых и римских диапазонах — короткое тире без пробелов.",
        "code": _code(
            r"""
def check(ctx):
    # В диапазоне 10–20 / I–V нужно короткое тире без пробелов.
    text = ctx.text or ""
    findings = []
    msg = "TPGR-TR-01.13: В цифровых диапазонах и римских числах должно быть короткое тире без отбивки пробелами"
    dashes = set("-{minus}{emdash}{endash}")
    endash = "{endash}"
    spaces = set(" {nbsp}")
    token_chars = set("0123456789IVXLCDMivxlcdm")
    roman = re.compile(
        r"^(?=[MDCLXVI])M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$",
        re.I,
    )

    def add(i):
        if in_angles(text, i):
            return
        findings.append({
            "start": i,
            "end": i + 1,
            "message": msg,
            "links": course_links("https://learn.imcmontanai.ru/course/section.php?id=5"),
        })

    i = 0
    while i < len(text):
        ch = text[i]
        if ch not in dashes:
            i += 1
            continue
        left = i - 1
        while left >= 0 and text[left] in spaces:
            left -= 1
        right = i + 1
        while right < len(text) and text[right] in spaces:
            right += 1
        tok_l = []
        j = left
        while j >= 0 and text[j] in token_chars:
            tok_l.append(text[j])
            j -= 1
        tok_l = "".join(reversed(tok_l))
        before_tok = j
        tok_r = []
        j = right
        while j < len(text) and text[j] in token_chars:
            tok_r.append(text[j])
            j += 1
        tok_r = "".join(tok_r)
        arab = tok_l.isdigit() and tok_r.isdigit()
        rom = bool(tok_l and tok_r and roman.match(tok_l) and roman.match(tok_r))
        if not (arab or rom):
            i += 1
            continue
        has_spaces = (i > 0 and text[i - 1] in spaces) or (
            i + 1 < len(text) and text[i + 1] in spaces
        )
        if not has_spaces and ch == endash:
            i += 1
            continue
        left_ctx = text[max(0, i - 15):i]
        if "№" in left_ctx or re.search(r"табл\.", left_ctx, re.I) or re.search(r"рис\.", left_ctx, re.I):
            i += 1
            continue
        p = before_tok
        while p >= 0 and text[p] in spaces:
            p -= 1
        letters = 0
        while p >= 0 and text[p].isalpha() and text[p] == text[p].upper():
            letters += 1
            p -= 1
        if letters >= 2:
            i += 1
            continue
        num_start = left - len(tok_l) + 1 if tok_l else i
        if len(tok_l) == 4 and num_start >= 6 and re.search(r"\d{2}\.\d{2}\.$", text[num_start - 6:num_start]):
            i += 1
            continue
        if num_start > 0 and text[num_start - 1] in "/:":
            i += 1
            continue
        if i > 0 and text[i - 1].isdigit() and i + 1 < len(text) and text[i + 1].isdigit():
            a = i
            while a > 0 and (text[a - 1].isdigit() or text[a - 1] in dashes):
                a -= 1
            b = i + 1
            while b < len(text) and (text[b].isdigit() or text[b] in dashes):
                b += 1
            if sum(1 for c in text[a:b] if c in dashes) > 1:
                i += 1
                continue
        add(i)
        i += 1
    return findings
"""
        ),
    },
    {
        "name": "TPGR-PR-01.01 Неразрывный пробел в сокращениях",
        "description": "Между частями графических сокращений с точкой и между инициалами ставится неразрывный пробел (т. д., А. С.). Шаблон ДД.ММ.ГГ и сайты *.рф пропускаются.",
        "code": _code(
            r"""
def check(ctx):
    # т. д. / т. п. и инициалы А. С.: между ними nbsp, не обычный пробел и не вплотную.
    # Шаблон ДД.ММ.ГГ(ГГ) и домены *.рф — не сокращения.
    text = ctx.text or ""
    findings = []
    msg = "TPGR-PR-01.01: Между графическими сокращениями с точкой, состоящими из нескольких слов, всегда используется неразрывный пробел"

    def is_letter(ch):
        return bool(ch) and ch.isalpha()

    def word_len_before(pos, max_len=4):
        n = 0
        j = pos - 1
        while n < max_len and j >= 0 and is_letter(text[j]):
            n += 1
            j -= 1
        if n == max_len and j >= 0 and is_letter(text[j]):
            return 0
        return n

    def word_len_after(pos, max_len=4):
        n = 0
        j = pos
        while n < max_len and j < len(text) and is_letter(text[j]):
            n += 1
            j += 1
        if n == max_len and j < len(text) and is_letter(text[j]):
            return 0
        return n

    def all_upper(s):
        return bool(s) and all(ch.isalpha() and ch == ch.upper() for ch in s)

    start = 0
    while True:
        i = text.find(".", start)
        if i < 0:
            break
        start = i + 1
        if text[max(0, i - 3):i].lower() == "www":
            continue
        n1 = word_len_before(i)
        if n1 == 0:
            continue
        sep = text[i + 1:i + 2]
        if sep == " ":
            offset = 1
        elif is_letter(sep):
            offset = 0
        else:
            continue
        w2 = i + 1 + offset
        n2 = word_len_after(w2)
        if n2 == 0:
            continue
        if text[w2 + n2:w2 + n2 + 1] != ".":
            continue
        first = text[i - n1:i]
        second = text[w2:w2 + n2]
        if first.lower() == "дд" and second.lower() == "мм":
            continue
        if second.lower() == "рф":
            continue
        # Заглавное длинное слово (г. Москва / см. Рис.) — не сокращение; А. С. — инициалы.
        if all_upper(second[:1]) and not (n2 <= 2 and all_upper(second)):
            continue
        if in_angles(text, i):
            continue
        findings.append({
            "start": i,
            "end": i + 1,
            "message": msg,
            "links": course_links("https://learn.imcmontanai.ru/course/section.php?id=16"),
        })
    return findings
"""
        ),
    },
    {
        "name": "TPGR-PR-01.08 Висячие предлоги",
        "description": "После частиц, предлогов и аббревиатур в конце визуальной строки — неразрывный пробел.",
        "code": _code(
            r"""
def check(ctx):
    # Один проход: частица + пробел, после которого начинается следующая визуальная
    # строка (ctx.line_end_spaces из раскладки DOCX, либо перевод абзаца).
    text = ctx.text or ""
    layout = getattr(ctx, "line_end_spaces", None)
    use_layout = layout is not None
    line_ends = layout or ()
    findings = []
    msg = "TPGR-PR-01.08: В конце строки после частиц, предлогов и аббревиатур (до 3 знаков) должен ставиться неразрывный пробел"
    particles = {
        "в", "без", "во", "до", "за", "из", "к", "ко",
        "на", "над", "о", "об", "от", "по", "под",
        "при", "про", "с", "со", "у", "а", "и", "но",
        "да", "ли", "то", "бы", "ль", "не", "ни", "ну", "уж", "ведь",
        "вот", "вон", "раз", "ооо", "зао", "оао", "ао", "пао", "зато", "тоо",
    }
    spaces = set(" {nbsp}")
    prev_ok = set(" {nbsp}(«")
    n = len(text)
    i = 0
    balance = 0
    while i < n:
        ch = text[i]
        if ch == "<":
            balance += 1
            i += 1
            continue
        if ch == ">":
            balance -= 1
            i += 1
            continue
        if not ch.isalpha():
            i += 1
            continue
        j = i + 1
        while j < n and text[j].isalpha():
            j += 1
        if j - i <= 4 and text[i:j].lower() in particles:
            prev = text[i - 1] if i else ""
            nxt = text[j] if j < n else ""
            after = text[j + 1] if j + 1 < n else ""
            if use_layout:
                visual_end = j in line_ends
            else:
                visual_end = after in ("\n", "\r")
            if prev in prev_ok and nxt in spaces and visual_end:
                if balance <= 0:
                    findings.append({
                        "start": i,
                        "end": j,
                        "message": msg,
                        "links": course_links("https://learn.imcmontanai.ru/course/section.php?id=16"),
                    })
        i = j
    return findings
"""
        ),
    },
    {
        "name": "TMPL-SS-00.00 Незакрытые угловые скобки",
        "description": "Баланс «<»/«>» по всему документу: технический текст внутри скобок может занимать несколько абзацев. Лишняя «>» тоже ошибка. Сравнения (< 0,1, <=) не скобки. Сноски — комментарий на знаке сноски.",
        "code": _code(
            r"""
def check(ctx):
    # Стек «<»/«>» по всему тексту: очистка удаляет всё между скобками, в том числе несколько абзацев.
    # Незакрытая «<» и лишняя «>» (пропуск парной скобки) — ошибка.
    # Сравнения (< 0,1, <=, <-, > 0,1, >=) и стрелка «–>» (короткое тире) не скобки шаблона.
    # Дефис и «>» (->) — закрывающая скобка шаблона.
    # Ёлочки «» только цитируют символ скобки («<», «>»), это не << / >>.
    # Сноски: одно примечание на знак сноски в основном тексте.
    text = ctx.text or ""
    findings = []
    msg_close = "TMPL-SS-00.00: Отсутствует закрывающая угловая скобка (>)"
    msg_open = "TMPL-SS-00.00: Отсутствует открывающая угловая скобка (<)"
    msg_close_fn = "TMPL-SS-00.00: Отсутствует закрывающая угловая скобка (>) в тексте сноски внизу страницы"
    msg_open_fn = "TMPL-SS-00.00: Отсутствует открывающая угловая скобка (<) в тексте сноски внизу страницы"
    spaces = set(" \t\r\n\xa0")
    lt_ops = set("=-~–—")
    en_dash = "–"

    def is_lt_op(s, i):
        n = len(s)
        nxt = s[i + 1] if i + 1 < n else ""
        if nxt in lt_ops:
            return True
        j = i + 1
        while j < n and s[j] in spaces:
            j += 1
        return j > i + 1 and j < n and (s[j].isdigit() or s[j] in "+.")

    def is_gt_op(s, i):
        n = len(s)
        prev = s[i - 1] if i else ""
        nxt = s[i + 1] if i + 1 < n else ""
        if nxt == ">" or prev == ">":
            return False
        if prev == "-":
            return False
        if prev == en_dash:
            return True
        if nxt == "=":
            return True
        j = i + 1
        while j < n and s[j] in spaces:
            j += 1
        return j > i + 1 and j < n and (s[j].isdigit() or s[j] in "+.")

    def scan(s):
        stack = []
        extra = []
        for i, ch in enumerate(s):
            if ch == "<":
                if is_lt_op(s, i):
                    continue
                stack.append(i)
            elif ch == ">":
                if is_gt_op(s, i):
                    continue
                if stack:
                    stack.pop()
                else:
                    extra.append(i)
        return stack, extra

    def merged(positions, s, widen_close=False):
        runs = []
        for pos in positions:
            start = pos
            end = pos + 1
            if widen_close:
                while start > 0 and s[start - 1] == ">":
                    start -= 1
            if runs and start <= runs[-1][1]:
                runs[-1] = (runs[-1][0], max(runs[-1][1], end))
            else:
                runs.append((start, end))
        return runs

    opened, extra = scan(text)
    for start, end in merged(opened, text):
        findings.append({"start": start, "end": end, "message": msg_close})
    for start, end in merged(extra, text, widen_close=True):
        findings.append({"start": start, "end": end, "message": msg_open})

    for note in getattr(ctx, "notes", None) or ():
        nid = str(note.get("id") or "")
        if not nid:
            continue
        body = note.get("text") or ""
        opened, extra = scan(body)
        if not opened and not extra:
            continue
        msg = msg_close_fn if opened else msg_open_fn
        findings.append({
            "start": 0,
            "end": 1,
            "message": msg,
            "note_id": nid,
            "note_kind": str(note.get("kind") or "footnote"),
        })
    return findings
"""
        ),
    },
    {
        "name": "TMPL-SS-00.00 Сноски без угловых скобок",
        "description": "Для сносок на публичные источники знак сноски ставится без угловых скобок.",
        "code": _code(
            r'''
def check(ctx):
    # VBA блок 9 (публичные источники): если сноска не на NextCloud, знак не в <>.
    findings = []
    msg = "TMPL-SS-00.00: Для сносок на публичные источники знак сноски ставится без угловых скобок"
    nc = (getattr(ctx, "nextcloud_base_url", "") or "").strip().lower()
    needles = []
    if nc:
        needles.append(nc)
    needles.append("cloud.imcmontanai.ru")
    for note in getattr(ctx, "notes", None) or ():
        nid = str(note.get("id") or "")
        if not nid:
            continue
        body = (note.get("text") or "").lower()
        if any(item and item in body for item in needles):
            continue
        if not note.get("wrapped_in_angles"):
            continue
        findings.append({
            "start": 0,
            "end": 1,
            "message": msg,
            "note_id": nid,
            "note_kind": str(note.get("kind") or "footnote"),
        })
    return findings
'''
        ),
    },
    {
        "name": "DOCX-SS-00.00 Битая перекрёстная ссылка",
        "description": "Текст «Ошибка! Источник ссылки не найден.» вместо рабочей перекрёстной ссылки.",
        "code": _code(
            r"""
def check(ctx):
    # VBA блок 15: сначала Fields.Update, затем поиск этой фразы.
    # Регистр не важен; точку в конце Word иногда опускает; английский Word — тот же смысл.
    text = ctx.text or ""
    findings = []
    msg = "DOCX-SS-00.00: Перекрестная ссылка не работает"
    pattern = re.compile(
        "|".join((
            r"ошибка!\s+источник\s+ссылки\s+не\s+найден\.?",
            r"error!\s+reference\s+source\s+not\s+found\.?",
        )),
        re.I,
    )
    for m in pattern.finditer(text):
        if in_angles(text, m.start()):
            continue
        findings.append({"start": m.start(), "end": m.end(), "message": msg})
    return findings
"""
        ),
    },
    {
        "name": "TPGR-DT-00.00 Лишнее «г.» после даты",
        "description": "После даты ДД.ММ.ГГ / ДД.ММ.ГГГГ не нужны «г.», «год» и склонения, в том числе в конце предложения. Слитное «2010г.» тоже ошибка.",
        "code": _code(
            r"""
def check(ctx):
    # Дата ДД.ММ.ГГ или ДД.ММ.ГГГГ + «г.» / «год» и склонения — лишнее.
    # Точка конца предложения после «год» не часть суффикса. «2010г.» без пробела — тоже.
    text = ctx.text or ""
    findings = []
    msg = "TPGR-DT-00.00: После даты, указанной в формате ДД.ММ.ГГГГ, слово «года» или сокращение «г.» не требуется"
    word_suffixes = {"год", "года", "году", "годе"}
    spaces = set(" {nbsp}")
    cyr = set("АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя")
    n = len(text)
    date_re = re.compile(
        r"(?<![0-9А-Яа-яЁё])(?:\d{2}\.\d{2}\.\d{4}(?!\d)|\d{2}\.\d{2}\.\d{2}(?!\d)|[Дд]{2}\.[Мм]{2}\.[Гг]{4}(?![ГгА-Яа-яЁё])|[Дд]{2}\.[Мм]{2}\.[Гг]{2}(?![ГгА-Яа-яЁё]))"
    )
    year_re = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")

    def suffix_at(j):
        k = j
        while k < n and text[k] in spaces:
            k += 1
        if k >= n:
            return None
        t = k
        while t < n and text[t] in cyr:
            t += 1
        word = text[k:t].lower()
        if word == "г" and t < n and text[t] == ".":
            return j, k, t + 1, "г."
        if word in word_suffixes:
            return j, k, t, word
        return None

    def add(j, k, t):
        if in_angles(text, j if j <= k else k):
            return
        if k == j:
            start, end = k, t
        else:
            start, end = j, j + 1
        findings.append({"start": start, "end": end, "message": msg})

    for m in date_re.finditer(text):
        found = suffix_at(m.end())
        if not found:
            continue
        j, k, t, _suffix = found
        if in_angles(text, m.start()):
            continue
        add(j, k, t)
    for m in year_re.finditer(text):
        if m.start() >= 6 and re.search(r"\d{2}\.\d{2}\.$", text[m.start() - 6:m.start()]):
            continue
        found = suffix_at(m.end())
        if not found:
            continue
        j, k, t, suffix = found
        if k != j or suffix != "г.":
            continue
        if in_angles(text, m.start()):
            continue
        add(j, k, t)
    return findings
"""
        ),
    },
    {
        "name": "TPGR-CH-02.01 Разряды в числах",
        "description": "С 4-значных чисел группы разрядов отделяются неразрывным пробелом (годы, коды и почтовые индексы пропускаются).",
        "code": _code(
            r"""
def check(ctx):
    # Слитных 4+ цифр в целой части быть не должно — нужен nbsp между разрядами.
    text = ctx.text or ""
    findings = []
    msg = "TPGR-CH-02.01: Начиная с 4-значных чисел, рекомендуется разбивать число на группы разрядов, отделяя их неразрывным пробелом"
    years = set(str(y) for y in range(2018, 2036))
    prefixes = {"n", "№", "код", "инн", "огрн", "кпп", "окпо", "окато", "октмо", "окогу"}
    year_after = {"год", "года", "году", "годы", "г.", "гг."}
    spaces = set(" {nbsp}")
    letters = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя")
    upper3 = set("ABCDEFGHIJKLMNOPQRSTUVWXYZАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ")

    def is_break(ch):
        if not ch:
            return True
        if ch.isalnum() or ch in "-{endash}{minus}":
            return False
        return True

    n = len(text)
    for m in re.finditer(r"[0-9][0-9,.]*", text):
        raw = m.group()
        if raw[0] == "0":
            continue
        int_digits = 0
        has_dec = False
        consumed = 0
        for idx, ch in enumerate(raw):
            if ch.isdigit():
                int_digits += 1
                consumed = idx + 1
            elif ch in ",." and idx + 1 < len(raw) and raw[idx + 1].isdigit():
                has_dec = True
                consumed = idx + 1
                while consumed < len(raw) and raw[consumed].isdigit():
                    consumed += 1
                break
            else:
                break
        start = m.start()
        end = start + consumed
        if start >= 2 and text[start - 2].isdigit():
            prev = text[start - 1]
            if prev == "{nbsp}":
                continue
            if prev == " ":
                grp_end = start
                while grp_end < n and text[grp_end].isdigit():
                    grp_end += 1
                if grp_end - start == 3:
                    continue
        first_int = int_digits
        grouped_space = False
        extra = 0
        if not has_dec:
            scan = end
            while scan < n:
                if text[scan] not in spaces:
                    break
                sep_space = False
                probe = scan
                while probe < n and text[probe] in spaces:
                    if text[probe] == " ":
                        sep_space = True
                    probe += 1
                if probe >= n or not text[probe].isdigit():
                    break
                k = probe
                while k < n and text[k].isdigit():
                    k += 1
                if (k - probe) != 3:
                    break
                extra += 3
                if sep_space:
                    grouped_space = True
                scan = k
            if extra:
                int_digits += extra
                end = scan
                if end < n and text[end] in ",." and end + 1 < n and text[end + 1].isdigit():
                    has_dec = True
                    end += 1
                    while end < n and text[end].isdigit():
                        end += 1
        if extra and not grouped_space and first_int < 4:
            continue
        if extra and not grouped_space:
            int_digits = first_int
            end = start + consumed
        if int_digits < 4:
            continue
        if in_angles(text, start):
            continue
        if end < n and text[end] == "," and (end + 1 >= n or text[end + 1] in spaces):
            continue
        if 4 <= int_digits <= 6:
            pos = start - 1
            if pos >= 0 and text[pos] in spaces:
                tok = ""
                j = pos - 1
                while j >= 0 and len(tok) < 3 and text[j] in upper3:
                    tok = text[j] + tok
                    j -= 1
                if len(tok) == 3 and (j < 0 or text[j] not in letters):
                    continue
        pos = start - 1
        while pos >= 0 and text[pos] in " {nbsp}:/":
            pos -= 1
        tok = ""
        while pos >= 0 and (text[pos] in letters or text[pos] == "№"):
            tok = text[pos] + tok
            pos -= 1
        if tok.lower() in prefixes:
            continue
        if int_digits == 4 and not has_dec:
            token = text[start:end]
            if token in years:
                continue
            j = start - 1
            steps = 0
            date_year = False
            while j >= 0 and steps < 3:
                if text[j] == ".":
                    if j > 0 and text[j - 1].isdigit():
                        date_year = True
                    break
                j -= 1
                steps += 1
            if date_year:
                continue
            k = end
            while k < n and text[k] in spaces:
                k += 1
            w = ""
            while k < n and len(w) < 4 and (text[k] in letters or text[k] == "."):
                w += text[k]
                k += 1
            if w.lower() in year_after:
                continue
            if start >= 3 and text[start - 3:start - 1] == "»," and text[start - 1] in spaces:
                continue
            if start >= 2 and text[start - 2] == "{emdash}" and text[start - 1] in spaces:
                if end < n and text[end] == ".":
                    continue
            if start >= 2 and text[start - 2] == "." and text[start - 1] in spaces:
                if end < n and text[end] == ".":
                    continue
            if start >= 2 and text[start - 2] == "," and text[start - 1] in spaces:
                nxt = text[end] if end < n else ""
                if nxt in ".)];":
                    continue
                k = end
                while k < n and text[k] in spaces:
                    k += 1
                if k >= n or text[k] == "\n":
                    continue
            if token.isdigit():
                year_num = int(token)
                if 2000 <= year_num <= 2060:
                    skip_year_cell = False
                    for cell in getattr(ctx, "table_cells", None) or ():
                        c_start = int(cell.get("start") or 0)
                        c_end = int(cell.get("end") or 0)
                        if start < c_start or end > c_end:
                            continue
                        cell_text = (cell.get("text") or text[c_start:c_end]).replace("{nbsp}", " ").strip(" \t\r\n")
                        if cell_text == token:
                            skip_year_cell = True
                            break
                    if skip_year_cell:
                        continue
        if int_digits in (5, 6) and not has_dec:
            k = end
            if k < n and text[k] in spaces:
                while k < n and text[k] in spaces:
                    k += 1
                chunk = text[k:]
                low = chunk.lower()
                addr = False
                if low.startswith("г.") or low.startswith("пгт") or low.startswith("пос.") or low.startswith("с."):
                    addr = True
                elif low.startswith("р."):
                    p = 2
                    while p < len(chunk) and chunk[p] in spaces:
                        p += 1
                    if p < len(chunk) and low[p:p + 1] == "п":
                        addr = True
                elif chunk[:1].isalpha() and chunk[:1].isupper():
                    addr = True
                if addr:
                    continue
        before = text[start - 1] if start else ""
        after = text[end] if end < n else ""
        if not (is_break(before) and is_break(after)):
            continue
        findings.append({
            "start": start,
            "end": start + 1,
            "message": msg,
            "links": course_links("https://learn.imcmontanai.ru/course/section.php?id=17"),
        })
    return findings
"""
        ),
    },
    {
        "name": "TPGR-KV-01.03 Повтор кавычек",
        "description": "Кавычки одного рисунка рядом не повторяются (««, »»).",
        "code": _code(
            r"""
def check(ctx):
    # «« и »» — кавычки одного рисунка подряд, комментарий на первую из пары.
    text = ctx.text or ""
    findings = []
    msg = "TPGR-KV-01.03: Кавычки одного рисунка рядом не повторяются"
    start = 0
    n = len(text)
    while start < n:
        i = text.find("««", start)
        j = text.find("»»", start)
        if i < 0 and j < 0:
            break
        if i < 0 or (j >= 0 and j < i):
            i = j
        if in_angles(text, i):
            start = i + 1
            continue
        findings.append({
            "start": i,
            "end": i + 1,
            "message": msg,
            "links": course_links("https://learn.imcmontanai.ru/course/section.php?id=14"),
        })
        start = i + 1
    return findings
"""
        ),
    },
    {
        "name": "TPGR-KV-01.02 Кавычки-ёлочки",
        "description": "В технических текстах только кавычки «ёлочки», не прямые и не английские. Двойной штрих ″ для координат допустим.",
        "code": _code(
            r'''
def check(ctx):
    # Запрещены прямые ", английские “ ” „ ‟ и полноширинные ＂ — только «ёлочки».
    # Двойной штрих ″ / ‶ для географических координат не считаем кавычками.
    text = ctx.text or ""
    findings = []
    msg = "TPGR-KV-01.02: В технических текстах должны использоваться только кавычки «ёлочки»"
    bad = set((
        chr(34),
        chr(0x201C),
        chr(0x201D),
        chr(0x201E),
        chr(0x201F),
        chr(0xFF02),
    ))
    for i, ch in enumerate(text):
        if ch not in bad:
            continue
        if in_angles(text, i):
            continue
        findings.append({
            "start": i,
            "end": i + 1,
            "message": msg,
            "links": course_links("https://learn.imcmontanai.ru/course/section.php?id=14"),
        })
    return findings
'''
        ),
    },
    {
        "name": "TPGR-KV-01.05 Незакрытые ёлочки",
        "description": "У открывающей « должна быть закрывающая »; новая « после конца предложения — незакрытая предыдущая пара.",
        "code": _code(
            r'''
def check(ctx):
    # VBA: стек из одной «; вторая « сбрасывает пару. Комментарий на первую,
    # если между ними есть точка-конец предложения, и на оставшуюся « в конце.
    # Точки в кодах (47.13330), аббревиатурах (см.) и инициалах (А.) — не граница.
    text = ctx.text or ""
    findings = []
    msg = "TPGR-KV-01.05: В кавычки «ёлочки» заключаются названия проектной документации, научных отчетов, законов и т. д.; отсутствует закрывающая кавычка"
    links = course_links("https://learn.imcmontanai.ru/course/section.php?id=14")
    abbr = set((
        "см", "г", "гг", "рис", "табл", "п", "пп", "т", "д", "е", "н", "э",
        "им", "стр", "вып", "изд", "ул", "пр", "обл", "пос", "др",
    ))
    stack = []

    def sent_dot(inner):
        n = len(inner)
        i = 0
        while i < n:
            if inner[i] != ".":
                i += 1
                continue
            prev = inner[i - 1] if i else ""
            j = i + 1
            while j < n and inner[j] in " \t\r\n\xa0":
                j += 1
            nxt = inner[j] if j < n else ""
            if prev.isdigit() and nxt.isdigit():
                i += 1
                continue
            if prev == ".":
                i += 1
                continue
            if prev.isupper() and (i < 2 or not inner[i - 2].isalpha()):
                i += 1
                continue
            k = i - 1
            while k >= 0 and inner[k].isalpha():
                k -= 1
            word = inner[k + 1:i]
            if word.lower() in abbr:
                i += 1
                continue
            if (j > i + 1 or nxt == "") and (nxt == "" or nxt.isupper()):
                return True
            i += 1
        return False

    for i, ch in enumerate(text):
        if ch == "«":
            if in_angles(text, i):
                continue
            if stack:
                if sent_dot(text[stack[0] + 1:i]):
                    findings.append({
                        "start": stack[0],
                        "end": stack[0] + 1,
                        "message": msg,
                        "links": links,
                    })
                stack = [i]
            else:
                stack = [i]
        elif ch == "»" and stack:
            stack.pop(0)
    for pos in stack:
        findings.append({
            "start": pos,
            "end": pos + 1,
            "message": msg,
            "links": links,
        })
    return findings
'''
        ),
    },
    {
        "name": "TPGR-SP-02.04 Точка в конце списков",
        "description": "В конце списка ставится точка, как и в конце любого предложения.",
        "code": _code(
            r'''
def check(ctx):
    # VBA блок 23: NameLocal «Маркированный список» / «Абзац списка».
    # В OOXML у стандартного Word это List Bullet / List Paragraph.
    text = ctx.text or ""
    findings = []
    msg = "TPGR-SP-02.04: В конце списка ставится точка, как и в конце любого предложения"
    links = course_links("https://learn.imcmontanai.ru/course/section.php?id=18")
    kinds = {
        "маркированный список": "mark",
        "маркированный список 2": "mark",
        "list bullet": "mark",
        "list bullet 2": "mark",
        "listbullet": "mark",
        "listbullet2": "mark",
        "абзац списка": "cont",
        "list paragraph": "cont",
        "listparagraph": "cont",
    }
    trim_ch = " \t{nbsp}"

    def base_name(para):
        name = (para.get("style_name") or para.get("style_id") or "").strip()
        pos = name.find(";")
        if pos >= 0:
            name = name[:pos].strip()
        return name

    def list_kind(para):
        name = base_name(para).lower()
        kind = kinds.get(name)
        if kind:
            return kind
        if name.startswith("маркированный список") or name.startswith("list bullet"):
            return "mark"
        return ""

    def is_mark_name(name):
        return name.startswith("маркированный список") or name.startswith("list bullet") or name in ("listbullet", "listbullet2")

    def flush(last, prev, count, tail):
        if count <= 1 or last is None:
            return
        prev_name = base_name(prev).lower() if prev else ""
        if tail == 1 and is_mark_name(prev_name):
            return
        raw = last.get("text") or ""
        i = len(raw) - 1
        while i >= 0 and raw[i] in trim_ch:
            i -= 1
        if i < 0 or raw[i] == ".":
            return
        pos = int(last.get("start") or 0) + i
        if in_angles(text, pos):
            return
        findings.append({
            "start": pos,
            "end": pos + 1,
            "message": msg,
            "links": links,
        })

    in_list = False
    count = 0
    tail = 0
    last = None
    prev = None
    for para in getattr(ctx, "paragraphs", None) or ():
        kind = list_kind(para)
        if kind:
            if not in_list:
                in_list = True
                count = 0
                tail = 0
                last = None
                prev = None
            count += 1
            tail = (tail + 1) if kind == "cont" else 0
            prev = last
            last = para
            continue
        if in_list:
            flush(last, prev, count, tail)
            in_list = False
    if in_list:
        flush(last, prev, count, tail)
    return findings
'''
        ),
    },
    {
        "name": "TPGR-SN-02.06 Пробел перед знаком сноски",
        "description": "Знак указателя сноски не отбивается пробелом от комментируемого текста.",
        "code": _code(
            r'''
def check(ctx):
    # VBA блок 12: пробел/nbsp сразу перед знаком сноски (не перед «<»).
    findings = []
    msg = "TPGR-SN-02.06: Знак указателя сноски не отбивается пробелом от комментируемого текста"
    links = course_links("https://learn.imcmontanai.ru/course/section.php?id=13")
    spaces = set(" {nbsp}")
    for note in getattr(ctx, "notes", None) or ():
        if str(note.get("kind") or "footnote") != "footnote":
            continue
        nid = str(note.get("id") or "")
        if not nid:
            continue
        prev = note.get("prev_char") or ""
        if prev not in spaces:
            continue
        findings.append({
            "start": 0,
            "end": 1,
            "message": msg,
            "links": links,
            "note_id": nid,
            "note_kind": "footnote",
        })
    return findings
'''
        ),
    },
    {
        "name": "TPGR-TB-00.00 Точка в конце ячейки таблицы",
        "description": "В конце ячейки таблицы точка не ставится: роль точки играет граница между ячейками.",
        "code": _code(
            r'''
def check(ctx):
    # VBA блок 16: последняя точка в ячейке, если после неё только пробелы/абзацы.
    text = ctx.text or ""
    findings = []
    msg = "TPGR-TB-00.00: В конце ячейки таблицы точка не ставится: роль точки в конце последнего абзаца играет граница между ячейками"
    exceptions = (
        "руб.", "чел.", "шт.", "ед.", "тыс.", "и др.", "т. п.", "т. д.", "и пр.", "дн.", "г.", " н.",
    )
    trim_ch = " \t\r\n"
    for cell in getattr(ctx, "table_cells", None) or ():
        start = int(cell.get("start") or 0)
        end = int(cell.get("end") or 0)
        if start < 0 or end > len(text) or start >= end:
            continue
        raw = text[start:end]
        pos = raw.rfind(".")
        if pos <= 0:
            continue
        if raw[pos + 1:].strip(trim_ch) != "":
            continue
        cell_text = (cell.get("text") or raw).replace("{nbsp}", " ").strip(trim_ch)
        skip = False
        low = cell_text.lower()
        for item in exceptions:
            if low.endswith(item):
                skip = True
                break
        if skip:
            continue
        abs_pos = start + pos
        if in_angles(text, abs_pos):
            continue
        # Как VBA: комментарий на символ перед точкой — так он виден в ячейке.
        mark_start = abs_pos - 1
        findings.append({
            "start": mark_start,
            "end": abs_pos + 1,
            "message": msg,
        })
    return findings
'''
        ),
    },
    {
        "name": "DOCX-SS-00.00 Ссылка на ближайший объект",
        "description": "Перекрёстная ссылка на рисунок или таблицу должна указывать на ближайший по тексту объект.",
        "code": _code(
            r'''
def check(ctx):
    # VBA блок 17: REF с «Рис»/«Табл» сверяется с ближайшим следующим заголовком без REF.
    text = ctx.text or ""
    findings = []
    dashes = set("-.{endash}{emdash}{minus}" + chr(0xAD) + chr(0x2010) + chr(0x2011) + chr(0x2012))

    def has_fig_table(value):
        low = (value or "").lower()
        return "рис" in low or "табл" in low

    def visible_number(value):
        seps = "".join(sorted(dashes))
        m = re.search(r"\d+(?:\s*[" + re.escape(seps) + r"]\s*\d+)+", value or "")
        if m:
            bits = re.split(r"\s*[" + re.escape(seps) + r"]\s*", m.group(0))
            return "-".join([bit for bit in bits if bit])
        m = re.search(r"\d+", value or "")
        return m.group(0) if m else ""

    def digits_only(value):
        return re.sub(r"\D", "", value or "")

    ref_paras = set()
    fig_refs = []
    for field in getattr(ctx, "ref_fields", None) or ():
        if str(field.get("kind") or "") != "REF":
            continue
        para_start = field.get("para_start")
        if para_start is None:
            para_start = int(field.get("start") or 0)
        else:
            para_start = int(para_start)
        ref_paras.add(para_start)
        result = field.get("result") or ""
        if not has_fig_table(result):
            continue
        num = visible_number(result)
        if not num:
            continue
        fig_refs.append({
            "start": int(field.get("start") or 0),
            "end": int(field.get("end") or 0),
            "para_start": para_start,
            "number": num,
        })

    captions = []
    for para in getattr(ctx, "paragraphs", None) or ():
        start = int(para.get("start") or 0)
        if start in ref_paras:
            continue
        body = para.get("text") or ""
        if not has_fig_table(body):
            continue
        num = visible_number(body)
        if num:
            captions.append((start, num))

    para_ref_count = {}
    for item in fig_refs:
        key = item["para_start"]
        para_ref_count[key] = para_ref_count.get(key, 0) + 1

    for item in fig_refs:
        if para_ref_count.get(item["para_start"], 0) > 1:
            continue
        pos = item["end"]
        near = ""
        best = None
        for cap_start, cap_num in captions:
            dist = cap_start - pos
            if dist > 0 and (best is None or dist < best):
                best = dist
                near = cap_num
        if not near:
            continue
        if digits_only(item["number"]) == digits_only(near):
            continue
        start = item["end"] - 1
        end = item["end"]
        if start < 0 or end > len(text) or start >= end:
            continue
        if in_angles(text, start):
            continue
        msg = (
            "DOCX-SS-00.00: Перекрёстная ссылка должна указывать на ближайший объект. После данной ссылки с номером «"
            + item["number"]
            + "» далее идёт ближайший объект (рисунок или таблица) с номером «"
            + near
            + "»"
        )
        findings.append({"start": start, "end": end, "message": msg})
    return findings
'''
        ),
    },
    {
        "name": "DOCX-KL-00.00 Ширина колонтитулов",
        "description": "Колонтитул, связанный с предыдущим разделом, не должен наследовать чужую ширину страницы.",
        "code": _code(
            r'''
def check(ctx):
    # VBA блок 24: связанный колонтитул при другой ширине полосы набора.
    text = ctx.text or ""
    findings = []
    msg = "DOCX-KL-00.00: Колонтитулы страницы должны быть выровнены по ширине страницы"
    kinds = ("default", "first", "even")
    groups = ("headers", "footers")
    tol = 20
    sections = list(getattr(ctx, "sections", None) or ())
    for i in range(1, len(sections)):
        curr = sections[i] or {}
        curr_w = curr.get("content_width")
        if curr_w is None:
            continue
        curr_w = int(curr_w)
        issue = False
        for kind in kinds:
            for group in groups:
                hf = ((curr.get(group) or {}).get(kind)) or {}
                if not hf.get("exists") or not hf.get("linked"):
                    continue
                src_w = curr_w
                j = i - 1
                while j >= 0:
                    prev_hf = (((sections[j] or {}).get(group) or {}).get(kind)) or {}
                    if not prev_hf.get("exists") or not prev_hf.get("linked"):
                        prev_w = (sections[j] or {}).get("content_width")
                        if prev_w is not None:
                            src_w = int(prev_w)
                        break
                    j -= 1
                if abs(src_w - curr_w) > tol:
                    issue = True
                    break
            if issue:
                break
        if not issue:
            continue
        start = curr.get("start")
        end = curr.get("end")
        if start is None:
            continue
        start = int(start)
        if end is None:
            end = len(text)
        else:
            end = int(end)
        mark = start
        while mark < end and mark < len(text) and text[mark] in "\r\n":
            mark += 1
        if mark >= len(text) or mark >= end:
            mark = start
        if mark < 0 or mark + 1 > len(text):
            continue
        findings.append({"start": mark, "end": mark + 1, "message": msg})
    return findings
'''
        ),
    },
    {
        "name": "TMPL-SS-00.00 Табуляция после «Источник:»",
        "description": "После «Источник:» должны идти пробел и знак табуляции.",
        "code": _code(
            r'''
def check(ctx):
    # VBA блок 10: «Источник: » / «Источник:»+nbsp, следующий знак — табуляция.
    text = ctx.text or ""
    findings = []
    msg = "TMPL-SS-00.00: После «Источник:» должны идти пробел и знак табуляции"
    tabs = getattr(ctx, "tab_offsets", None) or ()
    needles = ("Источник: ", "Источник:{nbsp}")
    for needle in needles:
        start = 0
        while True:
            i = text.find(needle, start)
            if i < 0:
                break
            end = i + len(needle)
            after = text[end:end + 1]
            if after == "\t" or end in tabs:
                start = end
                continue
            if after == "":
                start = end
                continue
            mark = end - 2
            if mark < 0 or mark + 1 > len(text):
                start = end
                continue
            if in_angles(text, mark):
                start = end
                continue
            findings.append({"start": mark, "end": mark + 1, "message": msg})
            start = end
    return findings
'''
        ),
    },
    {
        "name": "TMPL-ST-00.00 Проверка стилей",
        "description": "В отчёте допускаются только стили абзаца и знака из шаблона.",
        "code": _code(
            r'''
def check(ctx):
    # VBA блок 6: NameLocal абзаца/знака сверяется со списком стилей шаблона.
    text = ctx.text or ""
    findings = []
    para_msg = "TMPL-ST-00.00: К абзацу применен стиль, отсутствующий в шаблоне"
    char_msg = "TMPL-ST-00.00: Обнаружен недопустимый стиль знака: '"
    para_ok = {
        "абзац списка", "list paragraph", "listparagraph",
        "верхний колонтитул", "header",
        "гиперссылка", "hyperlink",
        "заголовок", "title",
        "заголовок 1", "heading 1", "heading1",
        "заголовок 2", "heading 2", "heading2",
        "заголовок 3", "heading 3", "heading3",
        "заголовок 4", "heading 4", "heading4",
        "заголовок 5", "heading 5", "heading5",
        "заголовок оглавления", "toc heading", "tocheading",
        "знак сноски", "footnote reference", "footnotereference",
        "маркированный список", "list bullet", "listbullet",
        "маркированный список 2", "list bullet 2", "listbullet2",
        "название", "caption",
        "название объекта",
        "нижний колонтитул", "footer",
        "нумерованный список", "list number", "listnumber",
        "нумерованный список 2", "list number 2", "listnumber2",
        "нумерованный список 3", "list number 3", "listnumber3",
        "нумерованный список 4", "list number 4", "listnumber4",
        "обычный", "normal",
        "оглавление 1", "toc 1", "toc1",
        "оглавление 2", "toc 2", "toc2",
        "оглавление 3", "toc 3", "toc3",
        "перечень рисунков", "table of figures", "tableoffigures",
        "подзаголовок", "subtitle",
        "подпись", "signature",
        "список литературы", "bibliography",
        "таблица ссылок",
        "текст",
        "текст выноски", "balloon text", "balloontext",
        "текст задания",
        "текст пояснений",
        "текст примечания", "comment text", "commenttext", "annotation text", "annotationtext",
        "текст сноски", "footnote text", "footnotetext",
        "текст таблицы",
    }
    char_ok = {
        "основной шрифт абзаца", "default paragraph font", "defaultparagraphfont",
        "гиперссылка", "hyperlink",
        "знак сноски", "footnote reference", "footnotereference",
        "знак концевой сноски", "endnote reference", "endnotereference",
        "знак примечания", "comment reference", "commentreference",
        "сильное выделение", "strong",
    }

    def parts_of(item):
        bits = []
        for key in ("style_name", "style_id", "aliases"):
            raw = item.get(key) or ""
            for piece in raw.replace(";", ",").split(","):
                piece = piece.strip()
                if piece:
                    bits.append(piece)
        return bits

    def normalized(name):
        name = (name or "").strip()
        pos = name.find(";")
        if pos >= 0:
            name = name[:pos].strip()
        low = name.lower()
        if low.endswith(" знак") or low.endswith(" char"):
            name = name[:len(name) - 5].strip()
        return name

    def is_allowed(item, allowed):
        tokens = parts_of(item)
        if not tokens:
            return True
        for tok in tokens:
            name = normalized(tok)
            low = name.lower()
            compact = low.replace(" ", "")
            if low in allowed or compact in allowed:
                return True
        return False

    def display_name(item):
        name = (item.get("style_name") or item.get("style_id") or "").strip()
        pos = name.find(";")
        if pos >= 0:
            name = name[:pos].strip()
        return name

    for para in getattr(ctx, "paragraphs", None) or ():
        start = para.get("start")
        end = para.get("end")
        if start is None or end is None:
            continue
        start = int(start)
        end = int(end)
        if start >= end:
            continue
        if is_allowed(para, para_ok):
            continue
        mark = end - 1
        if mark < 0 or mark + 1 > len(text):
            continue
        findings.append({
            "start": mark,
            "end": mark + 1,
            "message": para_msg + ": '" + display_name(para) + "'",
        })

    prev_para = None
    prev_bad = ""
    for run in getattr(ctx, "char_runs", None) or ():
        para_key = run.get("para_start")
        if para_key != prev_para:
            prev_para = para_key
            prev_bad = ""
        if not (run.get("style_id") or "").strip():
            prev_bad = ""
            continue
        raw = run.get("text") or ""
        if not raw.strip():
            continue
        full = display_name(run)
        if is_allowed(run, char_ok) or is_allowed(run, para_ok):
            prev_bad = ""
            continue
        if full == prev_bad:
            continue
        r_start = run.get("start")
        r_end = run.get("end")
        if r_start is None or r_end is None:
            continue
        r_start = int(r_start)
        r_end = int(r_end)
        if r_start < 0 or r_end > len(text) or r_start >= r_end:
            continue
        findings.append({
            "start": r_start,
            "end": r_end,
            "message": char_msg + full + "'.",
        })
        prev_bad = full
    return findings
'''
        ),
    },
    {
        "name": "TMPL-SN-00.00 Табуляция после знака сноски",
        "description": "После знака сноски внизу страницы нужны пробел и знак табуляции.",
        "code": _code(
            r'''
def check(ctx):
    # VBA блок 8: после знака сноски в теле — табуляция или пробел/nbsp и табуляция.
    findings = []
    msg = "TMPL-SN-00.00: После знака сноски внизу страницы нужно добавить пробел и знак табуляции"
    for note in getattr(ctx, "notes", None) or ():
        if str(note.get("kind") or "footnote") != "footnote":
            continue
        nid = str(note.get("id") or "")
        if not nid:
            continue
        if note.get("has_space_tab"):
            continue
        findings.append({
            "start": 0,
            "end": 1,
            "message": msg,
            "note_id": nid,
            "note_kind": "footnote",
        })
    return findings
'''
        ),
    },
    {
        "name": "TMPL-SN-00.00 Скобки NextCloud-сноски",
        "description": "Сноска на NextCloud заключается в угловые скобки, скобки в надстрочном регистре.",
        "code": _code(
            r'''
def check(ctx):
    # VBA блок 9 (NextCloud): знак сноски в <> , скобки надстрочные.
    findings = []
    msg_wrap = "TMPL-SN-00.00: В угловые скобки (<>) должен заключаться знак сноски, содержащий ссылку на облачное хранилище проекта NextCloud"
    msg_super = "TMPL-SN-00.00: Угловые скобки (<>), в которые заключается знак сноски, содержащий ссылку на облачное хранилище проекта NextCloud, должны быть в надстрочном регистре"
    nc = (getattr(ctx, "nextcloud_base_url", "") or "").strip().lower()
    needles = []
    if nc:
        needles.append(nc)
    needles.append("cloud.imcmontanai.ru")
    for note in getattr(ctx, "notes", None) or ():
        if str(note.get("kind") or "footnote") != "footnote":
            continue
        nid = str(note.get("id") or "")
        if not nid:
            continue
        body = (note.get("text") or "").lower()
        if not any(item and item in body for item in needles):
            continue
        if not note.get("wrapped_in_angles"):
            findings.append({
                "start": 0,
                "end": 1,
                "message": msg_wrap,
                "note_id": nid,
                "note_kind": "footnote",
            })
            continue
        if note.get("prev_superscript") and note.get("next_superscript"):
            continue
        findings.append({
            "start": 0,
            "end": 1,
            "message": msg_super,
            "note_id": nid,
            "note_kind": "footnote",
        })
    return findings
'''
        ),
    },
    {
        "name": "TMPL-SN-00.00 Пробел перед сноской в скобках",
        "description": "Знак сноски в угловых скобках не отбивается пробелом от комментируемого текста.",
        "code": _code(
            r'''
def check(ctx):
    # VBA блок 11: пробел/nbsp сразу перед «<» у знака сноски.
    findings = []
    msg = "TMPL-SN-00.00: Знак указателя сноски, заключенный в угловые скобки (<>), не отбивается пробелом от комментируемого текста"
    spaces = set(" {nbsp}")
    for note in getattr(ctx, "notes", None) or ():
        if str(note.get("kind") or "footnote") != "footnote":
            continue
        nid = str(note.get("id") or "")
        if not nid:
            continue
        if (note.get("prev_char") or "") != "<":
            continue
        if (note.get("prev2_char") or "") not in spaces:
            continue
        findings.append({
            "start": 0,
            "end": 1,
            "message": msg,
            "note_id": nid,
            "note_kind": "footnote",
        })
    return findings
'''
        ),
    },
    {
        "name": "GRMM-PN-00.00 Точка в конце сноски",
        "description": "В конце предложения (текста сноски) ставится точка.",
        "code": _code(
            r'''
def check(ctx):
    # VBA блок 14: непустая сноска без точки в конце; NextCloud пропускается.
    findings = []
    msg = "GRMM-PN-00.00: В конце предложения (текста сноски) ставится точка"
    nc = (getattr(ctx, "nextcloud_base_url", "") or "").strip().lower()
    needles = []
    if nc:
        needles.append(nc)
    needles.append("cloud.imcmontanai.ru")
    for note in getattr(ctx, "notes", None) or ():
        if str(note.get("kind") or "footnote") != "footnote":
            continue
        nid = str(note.get("id") or "")
        if not nid:
            continue
        body = note.get("text") or ""
        if any(item and item in body.lower() for item in needles):
            continue
        trimmed = body.rstrip(" \t\r\n")
        if not trimmed or trimmed[-1:] == ".":
            continue
        findings.append({
            "start": 0,
            "end": 1,
            "message": msg,
            "note_id": nid,
            "note_kind": "footnote",
        })
    return findings
'''
        ),
    },
]


def sync_tpgr_macros(model) -> tuple[int, int]:
    """Create or refresh TPGR macros by name. Other macros are left untouched."""
    created = 0
    updated = 0
    next_pos = int(model.objects.aggregate(m=Max("position")).get("m") or 0)
    for spec in TPGR_MACROS:
        obj = model.objects.filter(name=spec["name"]).first()
        if obj is None:
            next_pos += 1
            model.objects.create(
                name=spec["name"],
                description=spec["description"],
                code=spec["code"],
                position=next_pos,
            )
            created += 1
            continue
        fields = []
        if obj.description != spec["description"]:
            obj.description = spec["description"]
            fields.append("description")
        if obj.code != spec["code"]:
            obj.code = spec["code"]
            fields.append("code")
        if fields:
            obj.save(update_fields=fields)
            updated += 1
    return created, updated


def tpgr_macro_code(name_prefix: str) -> str:
    for item in TPGR_MACROS:
        if item["name"].startswith(name_prefix):
            return item["code"]
    raise KeyError(name_prefix)
