from html import escape as _html_escape

from .models import LetterTemplate


def get_effective_template(template_type, user):
    """Return user-specific template if exists, otherwise the default (admin) template."""
    if user and user.is_authenticated:
        user_tpl = LetterTemplate.objects.filter(
            template_type=template_type, user=user
        ).first()
        if user_tpl:
            return user_tpl
    return LetterTemplate.objects.filter(
        template_type=template_type, is_default=True
    ).first()


def render_template(body_html, variables: dict, safe_keys=frozenset()) -> str:
    """Replace {key} placeholders in *body_html* with HTML-escaped values from *variables*.

    Keys listed in *safe_keys* are inserted as-is (already trusted HTML).
    """
    result = body_html
    for key, value in variables.items():
        replacement = str(value) if key in safe_keys else _html_escape(str(value))
        result = result.replace("{{" + key + "}}", replacement)
        result = result.replace("{" + key + "}", replacement)
    return result


def render_subject(subject_template, variables: dict) -> str:
    """Replace {key} placeholders in *subject_template* with values from *variables*."""
    result = subject_template
    for key, value in variables.items():
        result = result.replace("{{" + key + "}}", str(value))
        result = result.replace("{" + key + "}", str(value))
    return result
