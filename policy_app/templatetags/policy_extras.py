import json
import re
from html import escape
from html.parser import HTMLParser

from django import template
from django.utils.safestring import mark_safe


register = template.Library()


ALLOWED_TAGS = {"p", "br", "strong", "b", "em", "i", "u", "span", "ol", "ul", "li"}
BLOCKED_TAGS = {"script", "style", "iframe", "object", "embed", "svg", "math"}
VOID_TAGS = {"br"}
ALLOWED_DATA_LIST_VALUES = {"ordered", "bullet", "circle", "square", "dash", "ndash", "check"}
ALLOWED_CLASS_RE = re.compile(
    r"^(?:"
    r"ql-ui|"
    r"ql-align-(?:center|right|justify)|"
    r"ql-font-(?:calibri|cambria|sans|serif|monospace|georgia|times-new-roman)|"
    r"ql-indent-[1-9][0-9]*|"
    r"ql-size-(?:small|large|huge)|"
    r"ql-direction-rtl"
    r")$"
)
ALLOWED_STYLE_PROPERTIES = {"color", "background-color", "background"}
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?(?:[0-9a-fA-F]{2})?$")
RGB_COLOR_RE = re.compile(
    r"^rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})(?:\s*,\s*(0|1|0?\.\d+))?\s*\)$"
)


def _parse_editor_state(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if raw:
            try:
                parsed = json.loads(raw)
            except (TypeError, ValueError, json.JSONDecodeError):
                return {}
            if isinstance(parsed, dict):
                return parsed
    return {}


def _text_to_html(value):
    text = str(value or "").strip()
    if not text:
        return ""
    paragraphs = []
    for chunk in re.split(r"\n{2,}", text):
        escaped = escape(chunk).replace("\n", "<br>")
        paragraphs.append(f"<p>{escaped}</p>")
    return "".join(paragraphs)


def _sanitize_classes(value):
    classes = [
        item
        for item in str(value or "").split()
        if ALLOWED_CLASS_RE.fullmatch(item)
    ]
    return " ".join(classes)


def _is_safe_color(value):
    value = str(value or "").strip()
    if HEX_COLOR_RE.fullmatch(value):
        return True
    match = RGB_COLOR_RE.fullmatch(value)
    if not match:
        return False
    red, green, blue = (int(match.group(index)) for index in (1, 2, 3))
    return all(0 <= channel <= 255 for channel in (red, green, blue))


def _sanitize_style(value):
    declarations = []
    for declaration in str(value or "").split(";"):
        if ":" not in declaration:
            continue
        prop, raw_style_value = declaration.split(":", 1)
        prop = prop.strip().lower()
        style_value = raw_style_value.strip()
        if prop not in ALLOWED_STYLE_PROPERTIES:
            continue
        if not _is_safe_color(style_value):
            continue
        declarations.append(f"{prop}: {style_value}")
    return "; ".join(declarations)


class QuillHtmlSanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._ignored_depth = 0
        self._suppressed_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if self._suppressed_depth:
            self._suppressed_depth += 1
            return
        if self._ignored_depth:
            if tag in BLOCKED_TAGS:
                self._ignored_depth += 1
            return
        if tag in BLOCKED_TAGS:
            self._ignored_depth += 1
            return
        if tag not in ALLOWED_TAGS:
            return
        cleaned_attrs = []
        for attr_name, attr_value in attrs:
            attr_name = str(attr_name or "").lower()
            attr_value = "" if attr_value is None else str(attr_value)
            if attr_name == "class":
                classes = _sanitize_classes(attr_value)
                if classes:
                    cleaned_attrs.append(("class", classes))
            elif tag == "li" and attr_name == "data-list":
                data_list = attr_value.strip().lower()
                if data_list in ALLOWED_DATA_LIST_VALUES:
                    cleaned_attrs.append(("data-list", data_list))
            elif attr_name == "style":
                style = _sanitize_style(attr_value)
                if style:
                    cleaned_attrs.append(("style", style))

        if tag == "span" and any(
            name == "class" and "ql-ui" in value.split()
            for name, value in cleaned_attrs
        ):
            self._suppressed_depth = 1
            return

        attr_html = "".join(
            f' {name}="{escape(value, quote=True)}"'
            for name, value in cleaned_attrs
        )
        self.parts.append(f"<{tag}{attr_html}>")
        if tag == "li" and any(name == "data-list" for name, _ in cleaned_attrs):
            self.parts.append('<span class="ql-ui"></span>')

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self._suppressed_depth:
            self._suppressed_depth -= 1
            return
        if tag in BLOCKED_TAGS:
            if self._ignored_depth:
                self._ignored_depth -= 1
            return
        if self._ignored_depth:
            return
        if tag not in ALLOWED_TAGS:
            return
        if tag not in VOID_TAGS:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        if not self._ignored_depth and not self._suppressed_depth:
            self.parts.append(escape(data))

    def handle_entityref(self, name):
        if not self._ignored_depth and not self._suppressed_depth:
            self.parts.append(f"&{name};")

    def handle_charref(self, name):
        if not self._ignored_depth and not self._suppressed_depth:
            self.parts.append(f"&#{name};")

    def get_html(self):
        return "".join(self.parts)


def _sanitize_quill_html(value):
    sanitizer = QuillHtmlSanitizer()
    sanitizer.feed(str(value or ""))
    sanitizer.close()
    return sanitizer.get_html()


@register.filter(name="policy_quill_html")
def policy_quill_html(editor_state, plain_text=""):
    state = _parse_editor_state(editor_state)
    html = str(state.get("html") or "").strip()
    if not html:
        html = _text_to_html(plain_text or state.get("plain_text") or "")
    return mark_safe(_sanitize_quill_html(html))
