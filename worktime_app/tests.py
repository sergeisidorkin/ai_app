from datetime import date

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase
from django.urls import reverse

from policy_app.models import Product
from projects_app.models import Performer, ProjectRegistration
from users_app.models import Employee


class WorktimeViewsTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = get_user_model().objects.create_user(
            username="worktime-user",
            password="secret",
            is_staff=True,
            first_name="Иван",
            last_name="Иванов",
        )
        self.client.force_login(self.user)
        self.employee = Employee.objects.create(user=self.user, patronymic="Иванович")

        self.other_user = get_user_model().objects.create_user(
            username="other-worktime-user",
            password="secret",
            first_name="Петр",
            last_name="Петров",
        )
        self.other_employee = Employee.objects.create(user=self.other_user, patronymic="Петрович")

        self.product = Product.objects.create(
            short_name="WT",
            name_en="Work Time",
            name_ru="Рабочее время",
            service_type="service",
        )
        self.registration = ProjectRegistration.objects.create(
            number=4444,
            type=self.product,
            name="Проект Альфа",
            deadline=date(2026, 4, 30),
        )
        self.performer = Performer.objects.create(
            registration=self.registration,
            executor="Иванов Иван",
            employee=self.employee,
            work_hours=8,
        )
        self.other_performer = Performer.objects.create(
            registration=self.registration,
            executor="Петров Петр Петрович",
            employee=self.other_employee,
            work_hours=5,
        )

    def test_partial_renders_timesheet_table(self):
        response = self.client.get(reverse("worktime_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Количество часов работы")
        self.assertContains(response, "Сотрудник")
        self.assertContains(response, "Иванов Иван")
        self.assertContains(response, "Петров Петр Петрович")
        self.assertContains(response, "Проект Альфа")
        self.assertContains(response, ">8<", html=False)
        self.assertContains(response, ">5<", html=False)

    def test_personal_partial_filters_rows_by_current_user(self):
        response = self.client.get(reverse("personal_worktime_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Количество часов работы")
        self.assertNotContains(response, "Сотрудник")
        self.assertContains(response, ">8<", html=False)
        self.assertNotContains(response, ">5<", html=False)

    def test_personal_partial_name_fallback_ignores_rows_linked_to_homonym(self):
        Performer.objects.create(
            registration=self.registration,
            executor="Иванов Иван Иванович",
            work_hours=3,
        )
        homonym_user = get_user_model().objects.create_user(
            username="worktime-homonym-user",
            password="secret",
            first_name="Иван",
            last_name="Иванов",
        )
        homonym_employee = Employee.objects.create(user=homonym_user, patronymic="Иванович")
        homonym_performer = Performer.objects.create(
            registration=self.registration,
            executor="Иванов Иван Иванович",
            work_hours=13,
        )
        Performer.objects.filter(pk=homonym_performer.pk).update(employee=homonym_employee)

        response = self.client.get(reverse("personal_worktime_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ">8<", html=False)
        self.assertContains(response, ">3<", html=False)
        self.assertNotContains(response, ">13<", html=False)

    def test_edit_updates_work_hours_and_triggers_refresh(self):
        response = self.client.post(
            reverse("worktime_edit", args=[self.performer.pk]),
            {"work_hours": "12"},
        )

        self.performer.refresh_from_db()
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["HX-Trigger"], "worktime-updated")
        self.assertEqual(self.performer.work_hours, 12)

    def test_edit_invalid_keeps_modal_form_with_errors(self):
        response = self.client.post(
            reverse("worktime_edit", args=[self.performer.pk]),
            {"work_hours": "-1"},
        )

        self.performer.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("HX-Trigger", response)
        self.assertEqual(self.performer.work_hours, 8)
        self.assertContains(response, "Редактировать рабочее время")
        self.assertContains(response, "invalid-feedback d-block", html=False)

    def test_panel_defers_initial_timesheet_load_until_explicit_event(self):
        request = self.factory.get("/")
        request.user = self.user

        html = render_to_string("worktime_app/panel.html", request=request)

        self.assertIn('hx-trigger="worktime-timesheet-load once from:body, worktime-updated from:body"', html)
        self.assertNotIn('hx-trigger="load, worktime-updated from:body"', html)
