from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from policy_app.models import Product
from projects_app.models import Performer, ProjectRegistration


class WorktimeViewsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="worktime-user",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)

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
            work_hours=8,
        )

    def test_partial_renders_timesheet_table(self):
        response = self.client.get(reverse("worktime_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Количество часов работы")
        self.assertContains(response, "Проект Альфа")
        self.assertContains(response, ">8<", html=False)

    def test_edit_updates_work_hours_and_triggers_refresh(self):
        response = self.client.post(
            reverse("worktime_edit", args=[self.performer.pk]),
            {"work_hours": "12"},
        )

        self.performer.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Trigger"], "worktime-updated")
        self.assertEqual(self.performer.work_hours, 12)
        self.assertContains(response, ">12<", html=False)
