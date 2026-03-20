MONTHS_RU_GENITIVE = [
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]

MONTHS_RU_NOMINATIVE = [
    "", "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]


def format_date_ru(value, fmt="j E Y"):
    """
    Форматирует дату с русскими названиями месяцев.
    Спецификаторы: j d E(род.) F(им.) m n Y y.
    """
    if value is None:
        return ""
    tokens = {
        "j": str(value.day),
        "d": f"{value.day:02d}",
        "E": MONTHS_RU_GENITIVE[value.month],
        "F": MONTHS_RU_NOMINATIVE[value.month],
        "m": f"{value.month:02d}",
        "n": str(value.month),
        "Y": str(value.year),
        "y": f"{value.year % 100:02d}",
    }
    return "".join(tokens.get(ch, ch) for ch in fmt)
