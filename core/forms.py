"""Общие помощники для Django-форм.

Заблокированные (нередактируемые) поля во всём приложении оформляются одинаково:

* внешний вид задаётся **только** CSS-классом ``readonly-field``
  (цвета — переменные ``--locked-field-bg`` / ``--locked-field-fg`` в ``site.css``);
  инлайн-стили не используются;
* для ``<input>`` / ``<textarea>`` ставятся атрибуты ``readonly`` и ``tabindex="-1"``;
* для ``<select>`` атрибут ``readonly`` браузерами не поддерживается, поэтому
  используется ``disabled`` (``use_disabled_attr=True``);
* ``field.disabled = True`` выставляется тогда, когда значение поля не должно
  приниматься из POST (Django берёт его из ``initial``).
"""

from __future__ import annotations

from django import forms

LOCKED_FIELD_CLASS = "readonly-field"
LOCKED_FIELD_ATTRS = {"readonly": True, "tabindex": "-1"}
LOCKED_SELECT_ATTRS = {"disabled": True, "tabindex": "-1"}


def _join_classes(*parts: str | None) -> str:
    seen: list[str] = []
    for part in parts:
        for cls in str(part or "").split():
            if cls not in seen:
                seen.append(cls)
    return " ".join(seen)


def locked_attrs(*extra_classes: str, base: str | None = "form-control", select: bool = False, **attrs):
    """Вернуть ``attrs`` для виджета заблокированного поля.

    ``locked_attrs()`` →
    ``{"class": "form-control readonly-field", "readonly": True, "tabindex": "-1"}``.

    :param extra_classes: дополнительные CSS-классы (``"js-stage1-end"``).
    :param base: базовый класс Bootstrap (``"form-control"``; ``"form-select"`` для select;
        ``None``/``""`` — без базового класса).
    :param select: использовать ``disabled`` вместо ``readonly`` (для ``<select>``).
    :param attrs: любые другие атрибуты (``id``, ``placeholder`` …); они имеют приоритет.
    """
    locked = LOCKED_SELECT_ATTRS if select else LOCKED_FIELD_ATTRS
    return {
        "class": _join_classes(base, LOCKED_FIELD_CLASS, *extra_classes),
        **locked,
        **attrs,
    }


def lock_field(field: forms.Field, *, disabled: bool = False, use_disabled_attr: bool = False, **attrs):
    """Заблокировать уже существующее поле формы (используется в ``__init__``).

    Добавляет класс ``readonly-field`` к ``widget.attrs["class"]``, ставит
    ``readonly`` + ``tabindex="-1"`` (или ``disabled`` + ``tabindex="-1"`` при
    ``use_disabled_attr=True`` — для ``<select>``), убирает инлайн ``style`` и при
    ``disabled=True`` выставляет ``field.disabled`` (значение не берётся из POST).
    """
    widget = field.widget
    widget.attrs["class"] = _join_classes(widget.attrs.get("class"), LOCKED_FIELD_CLASS)
    widget.attrs.pop("style", None)
    widget.attrs.update(LOCKED_SELECT_ATTRS if use_disabled_attr else LOCKED_FIELD_ATTRS)
    widget.attrs.update(attrs)
    if disabled:
        field.disabled = True
    return field
