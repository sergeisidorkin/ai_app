"""
Автономный переводчик чисел в текст прописью на русском языке.

Поддерживает целые числа от 0 до 999 999 999 999 (до триллиона − 1).
Отрицательные числа: «минус …».

    >>> number_to_words_ru(0)
    'ноль'
    >>> number_to_words_ru(12500)
    'двенадцать тысяч пятьсот'
    >>> number_to_words_ru(1)
    'один'
    >>> number_to_words_ru(2, feminine=True)
    'две'
    >>> number_to_words_ru(117647)
    'сто семнадцать тысяч шестьсот сорок семь'
"""

from __future__ import annotations

_ONES = [
    "", "один", "два", "три", "четыре",
    "пять", "шесть", "семь", "восемь", "девять",
]
_ONES_FEM = [
    "", "одна", "две", "три", "четыре",
    "пять", "шесть", "семь", "восемь", "девять",
]
_TEENS = [
    "десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать",
    "пятнадцать", "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать",
]
_TENS = [
    "", "", "двадцать", "тридцать", "сорок",
    "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят", "девяносто",
]
_HUNDREDS = [
    "", "сто", "двести", "триста", "четыреста",
    "пятьсот", "шестьсот", "семьсот", "восемьсот", "девятьсот",
]

# (singular, 2-4, 5-20), is_feminine
_SCALES: list[tuple[tuple[str, str, str], bool]] = [
    (("", "", ""), False),                                   # ones
    (("тысяча", "тысячи", "тысяч"), True),                   # 10^3
    (("миллион", "миллиона", "миллионов"), False),            # 10^6
    (("миллиард", "миллиарда", "миллиардов"), False),         # 10^9
]


def _plural_form(n: int, forms: tuple[str, str, str]) -> str:
    """Выбор падежной формы: (1, 21, 31…) / (2-4, 22-24…) / (5-20, 25-30…)."""
    mod100 = abs(n) % 100
    mod10 = abs(n) % 10
    if 11 <= mod100 <= 19:
        return forms[2]
    if mod10 == 1:
        return forms[0]
    if 2 <= mod10 <= 4:
        return forms[1]
    return forms[2]


def _triplet_to_words(n: int, feminine: bool) -> str:
    """Перевод числа 0..999 в слова."""
    if n == 0:
        return ""
    parts: list[str] = []
    h = n // 100
    if h:
        parts.append(_HUNDREDS[h])
    remainder = n % 100
    if 10 <= remainder <= 19:
        parts.append(_TEENS[remainder - 10])
    else:
        t = remainder // 10
        o = remainder % 10
        if t:
            parts.append(_TENS[t])
        if o:
            parts.append(_ONES_FEM[o] if feminine else _ONES[o])
    return " ".join(parts)


def number_to_words_ru(n: int | float, feminine: bool = False) -> str:
    """Переводит целое число в текст прописью на русском языке.

    *feminine* — использовать женский род для единиц
    (``одна``, ``две`` вместо ``один``, ``два``).
    По умолчанию мужской род.
    """
    n = int(n)
    if n == 0:
        return "ноль"

    prefix = ""
    if n < 0:
        prefix = "минус "
        n = -n

    chunks: list[str] = []
    scale_idx = 0
    while n > 0 and scale_idx < len(_SCALES):
        triplet = n % 1000
        n //= 1000
        if triplet:
            scale_forms, scale_fem = _SCALES[scale_idx]
            use_fem = scale_fem if scale_idx > 0 else feminine
            words = _triplet_to_words(triplet, use_fem)
            scale_word = _plural_form(triplet, scale_forms)
            chunk = f"{words} {scale_word}".strip() if scale_word else words
            chunks.append(chunk)
        scale_idx += 1

    chunks.reverse()
    return prefix + " ".join(chunks)
