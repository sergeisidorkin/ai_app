from __future__ import annotations

from django.db.models import Max

DEFAULT_MACRO_CODE = """def check(ctx):
    # ctx.text — плоский текст документа
    # верните [{"start": int, "end": int, "message": str}, ...]
    findings = []
    return findings
"""

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
"""


def _code(body: str) -> str:
    rendered = _HELPERS.strip() + "\n\n" + body.strip() + "\n"
    for token, value in (
        ("{nbsp}", "\u00a0"),
        ("{endash}", "\u2013"),
        ("{emdash}", "\u2014"),
        ("{minus}", "\u2212"),
        ("{rdquo}", "\u201d"),
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
        if prev in (" ", "{nbsp}") and i >= 2 and is_num_ch(text[i - 2]):
            left = i - 2
            while left > 0 and is_num_ch(text[left - 1]):
                left -= 1
            if not in_angles(text, i):
                findings.append({"start": left, "end": i - 1, "message": msg})
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
    for m in re.finditer(r"[№§]", text):
        i = m.start()
        if in_angles(text, i):
            continue
        nxt = text[i + 1:i + 2]
        if m.group() == "№" and nxt in ("", "\n"):
            continue
        if m.group() == "№" and nxt in (" ", "{nbsp}") and text[i + 2:i + 3] in ("", "\n"):
            continue
        if nxt not in (" ", "{nbsp}"):
            findings.append({"start": i, "end": i + 1, "message": msg})
        elif nxt == " ":
            after = text[i + 2:i + 3]
            if after.isdigit() or (after.isalpha() and after == after.upper()):
                findings.append({"start": i, "end": i + 1, "message": msg})
    for m in re.finditer("°C", text):
        if in_angles(text, m.start()):
            continue
        prev = text[m.start() - 1:m.start()] if m.start() else ""
        if prev != "{nbsp}":
            findings.append({"start": m.start(), "end": m.end(), "message": msg})
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
    text = ctx.text or ""
    findings = []
    msg = "TPGR-TR-01.15: Для разделения слов и предложений используется длинное тире с отбивкой пробелами"
    dashes = set("-{endash}{minus}")
    roman = set("IVXLCDMivxlcdm")
    i = 0
    while i < len(text):
        ch = text[i]
        if ch not in dashes:
            i += 1
            continue
        before = text[i - 1:i]
        after = text[i + 1:i + 2]
        if before not in (" ", "{nbsp}") or after not in (" ", "{nbsp}"):
            i += 1
            continue
        first = text[i - 2:i - 1]
        last = text[i + 2:i + 3]
        def num_or_roman(c):
            return bool(c) and (c.isdigit() or c in roman)
        if num_or_roman(first) and num_or_roman(last):
            i += 1
            continue
        if not in_angles(text, i):
            findings.append({"start": i, "end": i + 1, "message": msg})
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
    text = ctx.text or ""
    findings = []
    msg = "TPGR-TR-01.13: В цифровых диапазонах и римских числах должно быть короткое тире без отбивки пробелами"
    roman = re.compile(
        r"^(?=[MDCLXVI])M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$",
        re.I,
    )
    dashes = set("-{minus}{emdash}{endash}")
    i = 0
    while i < len(text):
        ch = text[i]
        if ch not in dashes:
            i += 1
            continue
        left = i - 1
        while left >= 0 and text[left] in " {nbsp}":
            left -= 1
        right = i + 1
        while right < len(text) and text[right] in " {nbsp}":
            right += 1
        ls = left
        while ls >= 0 and text[ls].isalnum():
            ls -= 1
        tok_l = text[ls + 1:left + 1]
        re_ = right
        while re_ < len(text) and text[re_].isalnum():
            re_ += 1
        tok_r = text[right:re_]
        arab = tok_l.isdigit() and tok_r.isdigit()
        rom = bool(roman.match(tok_l) and roman.match(tok_r))
        if not (arab or rom):
            i += 1
            continue
        has_spaces = (i > 0 and text[i - 1] in " {nbsp}") or (
            i + 1 < len(text) and text[i + 1] in " {nbsp}"
        )
        if not (has_spaces or ch != "{endash}"):
            i += 1
            continue
        left_ctx = text[max(0, i - 20):i]
        if "№" in left_ctx or "Табл." in left_ctx or "Рис." in left_ctx:
            i += 1
            continue
        if re.search(r"[A-ZА-ЯЁ]{2}", text[max(0, i - 8):i]):
            i += 1
            continue
        before_num = text[max(0, i - len(tok_l) - 6): i - len(tok_l) if tok_l else i]
        if re.search(r"\d{2}\.\d{2}\.$", before_num):
            i += 1
            continue
        ch_before_num = text[i - len(tok_l) - 1: i - len(tok_l)] if tok_l else ""
        if ch_before_num in "/:":
            i += 1
            continue
        window = text[max(0, i - 12):i + 13]
        dash_re = r"[-{endash}{emdash}{minus}]"
        if len(re.findall(dash_re, window)) > 1 and re.search(r"\d" + dash_re + r"\d+" + dash_re + r"\d", window):
            i += 1
            continue
        if in_angles(text, i):
            i += 1
            continue
        findings.append({"start": max(0, i - 1), "end": max(i, 1), "message": msg})
        i += 1
    return findings
"""
        ),
    },
    {
        "name": "TPGR-PR-01.01 Неразрывный пробел в сокращениях",
        "description": "Между частями графических сокращений с точкой ставится неразрывный пробел (т. д., т. п.).",
        "code": _code(
            r"""
def check(ctx):
    text = ctx.text or ""
    findings = []
    msg = "TPGR-PR-01.01: Между графическими сокращениями с точкой, состоящими из нескольких слов, всегда используется неразрывный пробел"
    for m in re.finditer(
        r"(?<![A-Za-zА-Яа-яЁё])([A-Za-zА-Яа-яЁё]{1,3})\.([ {nbsp}]?)([a-zа-яё]{1,3})\.",
        text,
    ):
        if m.group(1).lower() == "www":
            continue
        if m.group(2) == "{nbsp}":
            continue
        if in_angles(text, m.start()):
            continue
        dot = m.start() + len(m.group(1))
        findings.append({"start": dot, "end": dot + 1, "message": msg})
    return findings
"""
        ),
    },
    {
        "name": "TPGR-PR-01.08 Висячие предлоги",
        "description": "После частиц, предлогов и аббревиатур в конце абзаца — неразрывный пробел. Приближение VBA-проверки по концам строк.",
        "code": _code(
            r"""
def check(ctx):
    text = ctx.text or ""
    findings = []
    msg = "TPGR-PR-01.08: В конце строки после частиц, предлогов и аббревиатур (до 3 знаков) должен ставиться неразрывный пробел"
    parts = [
        "ведь", "без", "над", "под", "при", "про", "вот", "вон", "раз",
        "ООО", "ЗАО", "ОАО", "ПАО", "ЗАТО", "ТОО",
        "во", "до", "за", "из", "ко", "на", "об", "от", "по", "со",
        "да", "же", "ли", "то", "бы", "ль", "не", "ни", "ну", "уж", "но",
        "АО", "в", "к", "о", "с", "у", "а", "и",
    ]
    parts = sorted(set(parts), key=len, reverse=True)
    pat = r"(?iu)(?:^|(?<=[\s{nbsp}(«]))(?:" + "|".join(re.escape(p) for p in parts) + r") (?=\n|$)"
    for m in re.finditer(pat, text):
        if in_angles(text, m.start()):
            continue
        findings.append({"start": m.start(), "end": m.end(), "message": msg})
    return findings
"""
        ),
    },
    {
        "name": "TMPL-SS-00.00 Незакрытые угловые скобки",
        "description": "У каждой открывающей «<» должна быть закрывающая «>».",
        "code": _code(
            r"""
def check(ctx):
    text = ctx.text or ""
    findings = []
    msg = "TMPL-SS-00.00: Отсутствует закрывающая угловая скобка (>)"
    stack = []
    for i, ch in enumerate(text):
        if ch == "<":
            stack.append(i)
        elif ch == ">" and stack:
            stack.pop()
    for i in stack:
        findings.append({"start": i, "end": i + 1, "message": msg})
    return findings
"""
        ),
    },
    {
        "name": "DOCX-SS-00.00 Битая перекрёстная ссылка",
        "description": "Текст «Ошибка! Источник ссылки не найден.» вместо рабочей ссылки.",
        "code": _code(
            r"""
def check(ctx):
    text = ctx.text or ""
    findings = []
    msg = "DOCX-SS-00.00: Перекрестная ссылка не работает"
    needle = "Ошибка! Источник ссылки не найден."
    start = 0
    while True:
        i = text.find(needle, start)
        if i < 0:
            break
        findings.append({"start": i, "end": i + len(needle), "message": msg})
        start = i + 1
    return findings
"""
        ),
    },
    {
        "name": "TPGR-DT-00.00 Лишнее «г.» после даты",
        "description": "После даты ДД.ММ.ГГГГ не нужны «г.», «год» или «года».",
        "code": _code(
            r"""
def check(ctx):
    text = ctx.text or ""
    findings = []
    msg = "TPGR-DT-00.00: После даты, указанной в формате ДД.ММ.ГГГГ, слово «года» или сокращение «г.» не требуется"
    for m in re.finditer(
        r"(\d{2}\.\d{2}\.\d{4})([ {nbsp}]+)(г\.|год|года)(?!\w)",
        text,
        re.I,
    ):
        if in_angles(text, m.start()):
            continue
        findings.append({"start": m.start(2), "end": m.end(2), "message": msg})
    return findings
"""
        ),
    },
    {
        "name": "TPGR-CH-02.01 Разряды в числах",
        "description": "С 4-значных чисел группы разрядов отделяются неразрывным пробелом (годы и коды пропускаются).",
        "code": _code(
            r"""
def check(ctx):
    text = ctx.text or ""
    findings = []
    msg = "TPGR-CH-02.01: Начиная с 4-значных чисел, рекомендуется разбивать число на группы разрядов, отделяя их неразрывным пробелом"
    years = set(str(y) for y in range(2018, 2036))
    prefixes = {"n", "№", "код", "инн", "огрн", "кпп", "окпо", "окато", "октмо", "окогу"}
    year_after = ("год", "года", "году", "годы", "г.", "гг.")
    breaks = set(" {nbsp}\n\t.,;:!?)]»\"")
    for m in re.finditer(r"[0-9][0-9,.]*", text):
        num = m.group()
        int_digits = 0
        has_dec = False
        for ch in num:
            if ch.isdigit():
                int_digits += 1
            elif ch in ",.":
                has_dec = True
                break
            else:
                break
        if int_digits < 4 or num[0] == "0":
            continue
        if in_angles(text, m.start()):
            continue
        if m.start() >= 2 and text[m.start() - 1] == "{nbsp}" and text[m.start() - 2].isdigit():
            continue
        if int_digits == 4 and not has_dec:
            if num in years:
                continue
            if re.search(r"\d{2}\.\d{2}\.$", text[max(0, m.start() - 6):m.start()]):
                continue
            rest = text[m.end():m.end() + 8].lstrip(" {nbsp}").lower()
            if any(rest.startswith(w) for w in year_after):
                continue
        if 4 <= int_digits <= 6:
            pos = m.start() - 1
            if pos >= 0 and text[pos] in " {nbsp}":
                tok = text[max(0, pos - 3):pos]
                if len(tok) == 3 and tok.isalpha() and tok == tok.upper():
                    continue
        left = re.sub(r"[\s{nbsp}:/]+$", "", text[max(0, m.start() - 12):m.start()])
        tok = re.split(r"[^A-Za-zА-Яа-яЁё№]+", left)[-1] if left else ""
        if tok.lower() in prefixes or tok == "№":
            continue
        after = text[m.end():m.end() + 2]
        if after.startswith(",") and (len(after) == 1 or after[1] in " {nbsp}"):
            continue
        before = text[m.start() - 1] if m.start() else "\n"
        nxt = text[m.end()] if m.end() < len(text) else "\n"
        if before not in breaks or nxt not in breaks:
            continue
        findings.append({"start": m.start(), "end": m.start() + 1, "message": msg})
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
    text = ctx.text or ""
    findings = []
    msg = "TPGR-KV-01.03: Кавычки одного рисунка рядом не повторяются"
    for pat in ("««", "»»"):
        start = 0
        while True:
            i = text.find(pat, start)
            if i < 0:
                break
            if not in_angles(text, i):
                findings.append({"start": i, "end": i + 1, "message": msg})
            start = i + 1
    return findings
"""
        ),
    },
    {
        "name": "TPGR-KV-01.02 Кавычки-ёлочки",
        "description": "В технических текстах только кавычки «ёлочки», не прямые и не английские.",
        "code": _code(
            r'''
def check(ctx):
    text = ctx.text or ""
    findings = []
    msg = "TPGR-KV-01.02: В технических текстах должны использоваться только кавычки «ёлочки»"
    bad = set(['"', "{dprime}", "{rdquo}"])
    for i, ch in enumerate(text):
        if ch in bad:
            if in_angles(text, i):
                continue
            findings.append({"start": i, "end": i + 1, "message": msg})
    return findings
'''
        ),
    },
    {
        "name": "TPGR-KV-01.05 Незакрытые ёлочки",
        "description": "У открывающей « должна быть закрывающая »; вложенная « после точки считается новой незакрытой парой.",
        "code": _code(
            r"""
def check(ctx):
    text = ctx.text or ""
    findings = []
    msg = "TPGR-KV-01.05: В кавычки «ёлочки» заключаются названия проектной документации, научных отчетов, законов и т. д.; отсутствует закрывающая кавычка"
    stack = []
    for i, ch in enumerate(text):
        if ch == "«":
            if in_angles(text, i):
                continue
            if stack:
                inner = text[stack[0] + 1:i]
                if "." in inner:
                    findings.append({"start": stack[0], "end": stack[0] + 1, "message": msg})
                stack = [i]
            else:
                stack = [i]
        elif ch == "»" and stack:
            stack.pop(0)
    for i in stack:
        findings.append({"start": i, "end": i + 1, "message": msg})
    return findings
"""
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
