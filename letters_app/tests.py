from django.test import TestCase

from .services import render_subject, render_template


class LetterTemplateRenderTests(TestCase):
    def test_render_template_supports_double_brace_variables(self):
        rendered = render_template(
            "<p>Направляем {{tkp_id}}</p>",
            {"tkp_id": "333300RU DD Приморское"},
        )

        self.assertEqual(rendered, "<p>Направляем 333300RU DD Приморское</p>")

    def test_render_subject_supports_double_brace_variables(self):
        rendered = render_subject(
            "ТКП {{tkp_id}}",
            {"tkp_id": "333300RU DD Приморское"},
        )

        self.assertEqual(rendered, "ТКП 333300RU DD Приморское")
