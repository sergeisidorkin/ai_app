from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from letters_app.models import LetterTemplate
from policy_app.models import ADMIN_GROUP, DIRECTOR_GROUP
from users_app.models import Employee

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


class LetterTemplatePermissionTests(TestCase):
    template_type = "participation_confirmation"

    def setUp(self):
        user_model = get_user_model()
        self.director = user_model.objects.create_user(
            username="director",
            password="testpass123",
            first_name="Иван",
            last_name="Директор",
            is_superuser=True,
            is_staff=True,
        )
        Employee.objects.create(user=self.director, role=DIRECTOR_GROUP)

        self.admin = user_model.objects.create_user(
            username="admin",
            password="testpass123",
            first_name="Анна",
            last_name="Админ",
            is_superuser=True,
            is_staff=True,
        )
        Employee.objects.create(user=self.admin, role=ADMIN_GROUP)

        self.author = user_model.objects.create_user(
            username="author",
            password="testpass123",
            first_name="Петр",
            last_name="Автор",
        )
        Employee.objects.create(user=self.author, role="")

        self.default_template = LetterTemplate.objects.create(
            template_type=self.template_type,
            user=None,
            subject_template="Общая тема",
            body_html="<p>Общий шаблон</p>",
            is_default=True,
        )
        LetterTemplate.objects.create(
            template_type=self.template_type,
            user=self.author,
            subject_template="Личная тема автора",
            body_html="<p>Личный шаблон автора</p>",
            is_default=False,
        )

    def test_director_sees_letters_section_as_regular_user(self):
        self.client.force_login(self.director)

        response = self.client.get(reverse("letter_template_partial", args=[self.template_type]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Общий шаблон")
        self.assertNotContains(response, "Шаблоны пользователей")

    def test_director_save_creates_personal_template_instead_of_overwriting_shared(self):
        self.client.force_login(self.director)

        response = self.client.post(
            reverse("letter_template_save", args=[self.template_type]),
            {
                "subject_template": "Тема директора",
                "body_html": "<p>Личный шаблон директора</p>",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.default_template.refresh_from_db()
        self.assertEqual(self.default_template.subject_template, "Общая тема")
        self.assertEqual(self.default_template.body_html, "<p>Общий шаблон</p>")
        personal_template = LetterTemplate.objects.get(template_type=self.template_type, user=self.director)
        self.assertEqual(personal_template.subject_template, "Тема директора")
        self.assertEqual(personal_template.body_html, "<p>Личный шаблон директора</p>")
        self.assertContains(response, "Ваш шаблон")

    def test_admin_save_still_updates_shared_template(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("letter_template_save", args=[self.template_type]),
            {
                "subject_template": "Новая общая тема",
                "body_html": "<p>Новый общий шаблон</p>",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.default_template.refresh_from_db()
        self.assertEqual(self.default_template.subject_template, "Новая общая тема")
        self.assertEqual(self.default_template.body_html, "<p>Новый общий шаблон</p>")
        self.assertFalse(
            LetterTemplate.objects.filter(template_type=self.template_type, user=self.admin).exists()
        )
