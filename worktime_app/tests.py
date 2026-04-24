import csv
import io
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from notifications_app.models import Notification, NotificationPerformerLink
from notifications_app.services import process_participation_notification
from policy_app.models import ADMIN_GROUP, DEPARTMENT_HEAD_GROUP, Product
from projects_app.models import Performer, ProjectRegistration, ProjectRegistrationProduct
from proposals_app.models import ProposalRegistration
from users_app.models import Employee
from worktime_app.models import PersonalWorktimeWeekAssignment, WorktimeAssignment, WorktimeEntry
from worktime_app.views import _attach_group_histograms, _build_worktime_csv_project_index, _worktime_context


class WorktimeAppTests(TestCase):
    FREELANCER_LABEL = "Внештатный сотрудник"

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
        self.employee = Employee.objects.create(user=self.user, patronymic="Иванович", role=ADMIN_GROUP)

        self.other_user = get_user_model().objects.create_user(
            username="other-worktime-user",
            password="secret",
            is_staff=True,
            first_name="Петр",
            last_name="Петров",
        )
        self.other_employee = Employee.objects.create(user=self.other_user, patronymic="Петрович")

        self.pm_user = get_user_model().objects.create_user(
            username="pm-worktime-user",
            password="secret",
            is_staff=True,
            first_name="Мария",
            last_name="Сидорова",
        )
        self.pm_employee = Employee.objects.create(
            user=self.pm_user,
            patronymic="Олеговна",
            role="Руководитель проектов",
        )

        self.direction_user = get_user_model().objects.create_user(
            username="direction-worktime-user",
            password="secret",
            is_staff=True,
            first_name="Анна",
            last_name="Кузнецова",
        )
        self.direction_employee = Employee.objects.create(
            user=self.direction_user,
            patronymic="Игоревна",
            role=DEPARTMENT_HEAD_GROUP,
        )

        self.product = Product.objects.create(
            short_name="WT",
            name_en="Work Time",
            name_ru="Рабочее время",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
        )
        self.registration = ProjectRegistration.objects.create(
            number=4444,
            type=self.product,
            name="Проект Альфа",
            deadline=date(2026, 4, 30),
        )
        self.second_registration = ProjectRegistration.objects.create(
            number=4445,
            type=self.product,
            name="Проект Бета",
            deadline=date(2026, 4, 30),
        )
        self.proposal = ProposalRegistration.objects.create(
            number=5555,
            type=self.product,
            name="ТКП Альфа",
        )
        self.second_proposal = ProposalRegistration.objects.create(
            number=5556,
            type=self.product,
            name="ТКП Бета",
        )
        self.freelancer_user = get_user_model().objects.create_user(
            username="freelancer-worktime-user",
            password="secret",
            is_staff=True,
            first_name="Федор",
            last_name="Вольный",
        )
        self.freelancer_employee = Employee.objects.create(
            user=self.freelancer_user,
            patronymic="Алексеевич",
            employment=self.FREELANCER_LABEL,
        )
        self.nonstaff_user = get_user_model().objects.create_user(
            username="nonstaff-worktime-user",
            password="secret",
            is_staff=False,
            first_name="Николай",
            last_name="Обычный",
        )
        self.nonstaff_employee = Employee.objects.create(
            user=self.nonstaff_user,
            patronymic="Ильич",
        )

    def _full_name(self, employee):
        return Performer.employee_full_name(employee)

    def _worktime_csv_header(self, month_value):
        year, month = [int(part) for part in str(month_value).split("-", 1)]
        total_days = monthrange(year, month)[1]
        return ["Сотрудник", "Проект", "Тип", "Название", *[str(day) for day in range(1, total_days + 1)]]

    def _make_worktime_csv_upload(self, header, rows, *, name="worktime.csv"):
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=";")
        writer.writerow(header)
        writer.writerows(rows)
        return SimpleUploadedFile(
            name,
            buffer.getvalue().encode("utf-8-sig"),
            content_type="text/csv",
        )

    def _parse_worktime_csv_response(self, response):
        return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))

    def test_attach_group_histograms_scales_detail_rows_to_group_bar(self):
        groups = [
            {
                "label": "Исполнитель 1",
                "grand_total": 20,
                "rows": [
                    {"total_hours": 5},
                    {"total_hours": 20},
                ],
            },
            {
                "label": "Исполнитель 2",
                "grand_total": 10,
                "rows": [
                    {"total_hours": 10},
                ],
            },
        ]

        result = _attach_group_histograms(groups)

        self.assertEqual(result[0]["histogram_width_percent"], Decimal("100"))
        self.assertEqual(result[0]["rows"][0]["histogram_width_percent"], Decimal("2"))
        self.assertEqual(result[0]["rows"][1]["histogram_width_percent"], Decimal("100"))
        self.assertEqual(result[1]["histogram_width_percent"], Decimal("18"))
        self.assertEqual(result[1]["rows"][0]["histogram_width_percent"], Decimal("18"))

    def test_general_partial_renders_histograms_with_decimal_hours(self):
        assignment_a = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        assignment_b = WorktimeAssignment.objects.create(
            registration=self.second_registration,
            employee=self.other_employee,
            executor_name=self._full_name(self.other_employee),
            source_type=WorktimeAssignment.SourceType.PROJECT_MANAGER,
        )
        WorktimeEntry.objects.create(assignment=assignment_a, work_date=date(2026, 4, 1), hours=Decimal("7.50"))
        WorktimeEntry.objects.create(assignment=assignment_b, work_date=date(2026, 4, 2), hours=Decimal("3.25"))

        response = self.client.get(reverse("worktime_partial"), {"month": "2026-04", "hist_sort": "desc"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self._full_name(self.employee))
        self.assertContains(response, self._full_name(self.other_employee))
        self.assertContains(response, "7,5")
        self.assertContains(response, "3,25")

    def test_project_manager_save_creates_assignment(self):
        registration = ProjectRegistration.objects.create(
            number=4446,
            type=self.product,
            name="Проект PM",
            deadline=date(2026, 4, 30),
            project_manager=self._full_name(self.pm_employee),
        )

        assignment = WorktimeAssignment.objects.get(registration=registration)

        self.assertEqual(assignment.employee, self.pm_employee)
        self.assertEqual(assignment.executor_name, self._full_name(self.pm_employee))
        self.assertEqual(assignment.source_type, WorktimeAssignment.SourceType.PROJECT_MANAGER)

    def test_project_manager_change_replaces_project_manager_assignment(self):
        registration = ProjectRegistration.objects.create(
            number=4447,
            type=self.product,
            name="Проект PM swap",
            deadline=date(2026, 4, 30),
            project_manager=self._full_name(self.pm_employee),
        )
        new_pm_user = get_user_model().objects.create_user(
            username="pm-worktime-user-2",
            password="secret",
            is_staff=True,
            first_name="Ольга",
            last_name="Смирнова",
        )
        new_pm_employee = Employee.objects.create(
            user=new_pm_user,
            patronymic="Сергеевна",
            role="Руководитель проектов",
        )

        registration.project_manager = self._full_name(new_pm_employee)
        registration.save()

        self.assertFalse(
            WorktimeAssignment.objects.filter(
                registration=registration,
                executor_name=self._full_name(self.pm_employee),
            ).exists()
        )
        self.assertTrue(
            WorktimeAssignment.objects.filter(
                registration=registration,
                executor_name=self._full_name(new_pm_employee),
                source_type=WorktimeAssignment.SourceType.PROJECT_MANAGER,
            ).exists()
        )

    def test_project_manager_save_does_not_create_assignment_for_nonstaff_user(self):
        ProjectRegistration.objects.create(
            number=4448,
            type=self.product,
            name="Проект nonstaff PM",
            deadline=date(2026, 4, 30),
            project_manager=self._full_name(self.nonstaff_employee),
        )

        self.assertFalse(
            WorktimeAssignment.objects.filter(
                executor_name=self._full_name(self.nonstaff_employee),
                source_type=WorktimeAssignment.SourceType.PROJECT_MANAGER,
            ).exists()
        )

    def test_process_participation_notification_creates_assignment_on_confirm(self):
        performer = Performer.objects.create(
            registration=self.registration,
            executor=self._full_name(self.employee),
            employee=self.employee,
        )
        notification = Notification.objects.create(
            notification_type=Notification.NotificationType.PROJECT_PARTICIPATION_CONFIRMATION,
            related_section=Notification.RelatedSection.PROJECTS,
            recipient=self.user,
            sender=self.other_user,
            project=self.registration,
            title_text="Подтвердите участие",
            payload={"letter_template_type": "participation_confirmation"},
        )
        NotificationPerformerLink.objects.create(notification=notification, performer=performer)

        process_participation_notification(
            notification,
            self.user,
            Notification.ActionChoice.CONFIRMED,
        )

        assignment = WorktimeAssignment.objects.get(
            registration=self.registration,
            executor_name=self._full_name(self.employee),
        )
        self.assertEqual(assignment.performer, performer)
        self.assertEqual(assignment.source_type, WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION)

    def test_process_participation_notification_does_not_create_assignment_for_freelancer(self):
        performer = Performer.objects.create(
            registration=self.registration,
            executor=self._full_name(self.freelancer_employee),
            employee=self.freelancer_employee,
        )
        notification = Notification.objects.create(
            notification_type=Notification.NotificationType.PROJECT_PARTICIPATION_CONFIRMATION,
            related_section=Notification.RelatedSection.PROJECTS,
            recipient=self.freelancer_user,
            sender=self.user,
            project=self.registration,
            title_text="Подтвердите участие",
            payload={"letter_template_type": "participation_confirmation"},
        )
        NotificationPerformerLink.objects.create(notification=notification, performer=performer)

        process_participation_notification(
            notification,
            self.freelancer_user,
            Notification.ActionChoice.CONFIRMED,
        )

        self.assertFalse(
            WorktimeAssignment.objects.filter(
                registration=self.registration,
                executor_name=self._full_name(self.freelancer_employee),
                source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
            ).exists()
        )

    def test_participation_request_creates_direction_head_assignment_on_send(self):
        performer = Performer.objects.create(
            registration=self.registration,
            executor=self._full_name(self.direction_employee),
            employee=self.direction_employee,
        )
        request_sent_at = timezone.localtime().replace(second=0, microsecond=0).isoformat(timespec="minutes")

        with patch("projects_app.views.create_participation_notifications") as mocked_notifications:
            mocked_notifications.return_value = {
                "delivery_channels": ["system"],
                "email_delivery": {"requested": 0, "sent": 0, "failed": 0},
            }
            response = self.client.post(
                reverse("participation_request"),
                {
                    "performer_ids": [str(performer.pk)],
                    "duration_hours": "4",
                    "request_sent_at": request_sent_at,
                    "delivery_channels": ["system"],
                },
            )

        self.assertEqual(response.status_code, 200)
        assignment = WorktimeAssignment.objects.get(
            registration=self.registration,
            executor_name=self._full_name(self.direction_employee),
        )
        self.assertEqual(assignment.performer, performer)
        self.assertEqual(assignment.source_type, WorktimeAssignment.SourceType.DIRECTION_HEAD_REQUEST)

    def test_partial_renders_calendar_grouped_by_executor(self):
        assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        WorktimeAssignment.objects.create(
            registration=self.second_registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PROJECT_MANAGER,
        )
        WorktimeEntry.objects.create(
            assignment=assignment,
            work_date=date(2026, 4, 1),
            hours=7,
        )

        response = self.client.get(reverse("worktime_partial"), {"month": "2026-04"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Фонд рабочего времени")
        self.assertContains(response, self._full_name(self.employee))
        self.assertContains(response, "Проект Альфа")
        self.assertContains(response, "Проект Бета")
        self.assertContains(response, ">7<", html=False)
        self.assertContains(response, "Итого")
        self.assertNotContains(response, f'hours_{assignment.pk}_20260401', html=False)
        self.assertContains(response, 'data-worktime-general-collapse-toggle', html=False)
        self.assertContains(response, 'data-worktime-group-collapse-toggle', html=False)
        self.assertContains(response, 'data-worktime-group-key', html=False)
        self.assertContains(response, 'class="worktime-hist-head"', html=False)
        self.assertContains(response, 'data-worktime-hist-sort-btn="desc"', html=False)
        self.assertContains(response, 'data-worktime-hist-sort-btn="asc"', html=False)
        self.assertContains(response, "Разбивка:")
        self.assertContains(response, "по сотрудникам")
        self.assertContains(response, "по активностям")
        self.assertContains(response, 'data-worktime-breakdown-value', html=False)
        self.assertContains(response, 'class="worktime-hist-cell worktime-hist-cell-bar"', html=False)
        self.assertContains(response, 'class="worktime-hist-bar"', html=False)
        self.assertContains(response, 'class="worktime-hist-bar worktime-hist-bar-secondary"', html=False)
        self.assertContains(response, 'class="table-light fw-semibold worktime-summary-row worktime-group-row"', html=False)
        self.assertContains(response, 'class="fw-semibold worktime-summary-row worktime-grand-summary-row"', html=False)

    def test_general_partial_hides_freelancer_assignments(self):
        eligible_assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        hidden_assignment = WorktimeAssignment.objects.create(
            registration=self.second_registration,
            employee=self.freelancer_employee,
            executor_name=self._full_name(self.freelancer_employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        WorktimeEntry.objects.create(assignment=eligible_assignment, work_date=date(2026, 4, 1), hours=7)
        WorktimeEntry.objects.create(assignment=hidden_assignment, work_date=date(2026, 4, 2), hours=5)

        response = self.client.get(reverse("worktime_partial"), {"month": "2026-04"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self._full_name(self.employee))
        self.assertNotContains(response, self._full_name(self.freelancer_employee))

    def test_general_partial_hist_sort_desc_orders_groups_and_rows(self):
        third_registration = ProjectRegistration.objects.create(
            number=4446,
            type=self.product,
            name="Проект Гамма",
            deadline=date(2026, 4, 30),
        )
        assignment_a1 = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        assignment_a2 = WorktimeAssignment.objects.create(
            registration=third_registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PROJECT_MANAGER,
        )
        assignment_b1 = WorktimeAssignment.objects.create(
            registration=self.second_registration,
            employee=self.other_employee,
            executor_name=self._full_name(self.other_employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        WorktimeEntry.objects.create(assignment=assignment_a1, work_date=date(2026, 4, 1), hours=4)
        WorktimeEntry.objects.create(assignment=assignment_a2, work_date=date(2026, 4, 2), hours=8)
        WorktimeEntry.objects.create(assignment=assignment_b1, work_date=date(2026, 4, 3), hours=6)

        response = self.client.get(reverse("worktime_partial"), {"month": "2026-04", "hist_sort": "desc"})

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertLess(content.index(self._full_name(self.employee)), content.index(self._full_name(self.other_employee)))
        self.assertLess(content.index("Проект Гамма"), content.index("Проект Альфа"))

    def test_general_partial_breakdown_activities_groups_rows_by_activity(self):
        assignment_a1 = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        assignment_a2 = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.other_employee,
            executor_name=self._full_name(self.other_employee),
            source_type=WorktimeAssignment.SourceType.PROJECT_MANAGER,
        )
        WorktimeEntry.objects.create(assignment=assignment_a1, work_date=date(2026, 4, 1), hours=5)
        WorktimeEntry.objects.create(assignment=assignment_a2, work_date=date(2026, 4, 2), hours=7)

        response = self.client.get(reverse("worktime_partial"), {"month": "2026-04", "breakdown": "activities"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.registration.short_uid, count=1)
        self.assertContains(response, "Проект Альфа", count=1)
        self.assertContains(response, self._full_name(self.employee))
        self.assertContains(response, self._full_name(self.other_employee))
        self.assertContains(response, 'data-worktime-group-key="activities:project:', html=False)

    def test_worktime_context_breakdown_activities_preserves_totals(self):
        project_assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        tkp_assignment = WorktimeAssignment.objects.create(
            proposal_registration=self.proposal,
            employee=self.other_employee,
            executor_name=self._full_name(self.other_employee),
            source_type=WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK,
            record_type=WorktimeAssignment.RecordType.TKP,
        )
        WorktimeEntry.objects.create(assignment=project_assignment, work_date=date(2026, 4, 1), hours=6)
        WorktimeEntry.objects.create(assignment=project_assignment, work_date=date(2026, 4, 2), hours=2)
        WorktimeEntry.objects.create(assignment=tkp_assignment, work_date=date(2026, 4, 3), hours=4)

        employee_context = _worktime_context(self.user, month_start=date(2026, 4, 1), breakdown="employees")
        activity_context = _worktime_context(self.user, month_start=date(2026, 4, 1), breakdown="activities")

        self.assertEqual(employee_context["grand_total"], activity_context["grand_total"])
        self.assertEqual(employee_context["column_totals"], activity_context["column_totals"])
        self.assertEqual(activity_context["breakdown_value"], "activities")

    def test_general_partial_hist_sort_desc_orders_activity_groups_and_rows(self):
        third_registration = ProjectRegistration.objects.create(
            number=4446,
            type=self.product,
            name="Проект Гамма",
            deadline=date(2026, 4, 30),
        )
        assignment_alpha_low = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        assignment_alpha_high = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.other_employee,
            executor_name=self._full_name(self.other_employee),
            source_type=WorktimeAssignment.SourceType.PROJECT_MANAGER,
        )
        assignment_gamma = WorktimeAssignment.objects.create(
            registration=third_registration,
            employee=self.pm_employee,
            executor_name=self._full_name(self.pm_employee),
            source_type=WorktimeAssignment.SourceType.PROJECT_MANAGER,
        )
        WorktimeEntry.objects.create(assignment=assignment_alpha_low, work_date=date(2026, 4, 1), hours=3)
        WorktimeEntry.objects.create(assignment=assignment_alpha_high, work_date=date(2026, 4, 2), hours=8)
        WorktimeEntry.objects.create(assignment=assignment_gamma, work_date=date(2026, 4, 3), hours=6)

        response = self.client.get(
            reverse("worktime_partial"),
            {"month": "2026-04", "breakdown": "activities", "hist_sort": "desc"},
        )

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertLess(content.index("Проект Альфа"), content.index("Проект Гамма"))
        self.assertLess(content.index(self._full_name(self.other_employee)), content.index(self._full_name(self.employee)))

    def test_general_partial_preserves_breakdown_value_in_forms(self):
        response = self.client.get(reverse("worktime_partial"), {"month": "2026-04", "breakdown": "activities"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="breakdown" value="activities"', html=False, count=2)

    def test_personal_partial_filters_assignments_by_current_user(self):
        assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        WorktimeAssignment.objects.create(
            registration=self.second_registration,
            employee=self.other_employee,
            executor_name=self._full_name(self.other_employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        WorktimeEntry.objects.create(
            assignment=assignment,
            work_date=date(2026, 4, 7),
            hours=5,
        )

        response = self.client.get(reverse("personal_worktime_partial"), {"week": "2026-04-10"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "с 06.04.26 по 12.04.26")
        self.assertContains(response, "Проект Альфа")
        self.assertNotContains(response, "Проект Бета")
        self.assertNotContains(response, self._full_name(self.employee))
        self.assertContains(response, "Итого")
        self.assertNotContains(response, 'class="worktime-hist-head"', html=False)
        self.assertContains(response, ">5<", html=False)
        self.assertContains(response, 'hx-get="/worktime/partial/personal/"', html=False)

    def test_personal_partial_rejects_too_far_future_week(self):
        future_anchor = timezone.localdate() + timedelta(weeks=3)

        response = self.client.get(reverse("personal_worktime_partial"), {"week": future_anchor.isoformat()})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Нельзя выбрать слишком далекую будущую неделю. Доступны текущая неделя и только две следующие.")

    def test_save_updates_worktime_entries_for_month(self):
        assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )

        response = self.client.post(
            reverse("worktime_save"),
            {
                "scope": "all",
                "month": "2026-04",
                "assignment_ids": [str(assignment.pk)],
                f"hours_{assignment.pk}_20260401": "8",
                f"hours_{assignment.pk}_20260402": "6",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Табель сохранен.")
        self.assertEqual(
            list(
                WorktimeEntry.objects.filter(assignment=assignment)
                .order_by("work_date")
                .values_list("work_date", "hours")
            ),
            [
                (date(2026, 4, 1), 8),
                (date(2026, 4, 2), 6),
            ],
        )

    def test_save_accepts_decimal_hours_for_month(self):
        assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )

        response = self.client.post(
            reverse("worktime_save"),
            {
                "scope": "all",
                "month": "2026-04",
                "assignment_ids": [str(assignment.pk)],
                f"hours_{assignment.pk}_20260401": "7.5",
                f"hours_{assignment.pk}_20260402": "0,25",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Табель сохранен.")
        self.assertEqual(
            list(
                WorktimeEntry.objects.filter(assignment=assignment)
                .order_by("work_date")
                .values_list("work_date", "hours")
            ),
            [
                (date(2026, 4, 1), Decimal("7.50")),
                (date(2026, 4, 2), Decimal("0.25")),
            ],
        )

    def test_personal_save_updates_only_selected_week(self):
        assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )

        response = self.client.post(
            reverse("worktime_save"),
            {
                "scope": "personal",
                "week": "2026-04-07",
                "assignment_ids": [str(assignment.pk)],
                f"hours_{assignment.pk}_20260406": "4",
                f"hours_{assignment.pk}_20260412": "7",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Табель сохранен.")
        self.assertContains(response, "с 06.04.26 по 12.04.26")
        self.assertContains(response, 'hx-get="/worktime/partial/personal/"', html=False)
        self.assertEqual(
            list(
                WorktimeEntry.objects.filter(assignment=assignment)
                .order_by("work_date")
                .values_list("work_date", "hours")
            ),
            [
                (date(2026, 4, 6), 4),
                (date(2026, 4, 12), 7),
            ],
        )

    def test_autosave_returns_json_without_panel_rerender(self):
        assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )

        response = self.client.post(
            reverse("worktime_save"),
            {
                "scope": "personal",
                "week": "2026-04-07",
                "assignment_ids": [str(assignment.pk)],
                f"hours_{assignment.pk}_20260406": "5",
                "autosave": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})
        self.assertEqual(
            list(
                WorktimeEntry.objects.filter(assignment=assignment)
                .order_by("work_date")
                .values_list("work_date", "hours")
            ),
            [(date(2026, 4, 6), 5)],
        )

    def test_autosave_validation_error_returns_json(self):
        assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )

        response = self.client.post(
            reverse("worktime_save"),
            {
                "scope": "all",
                "month": "2026-04",
                "assignment_ids": [str(assignment.pk)],
                f"hours_{assignment.pk}_20260401": "25",
                "autosave": "1",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {"ok": False, "error": "Количество часов за 01.04.2026 должно быть в диапазоне от 0 до 24."},
        )

    def test_personal_worktime_row_form_lists_available_projects(self):
        response = self.client.get(
            reverse("personal_worktime_row_form"),
            {"week": "2026-04-07"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Вид записи")
        self.assertContains(response, "Проект")
        self.assertContains(response, "Больничный")
        self.assertContains(response, "Учет часов работы")
        self.assertContains(response, "4444")
        self.assertContains(response, "WT")
        self.assertContains(response, "Проект Альфа")
        self.assertContains(response, "5555")
        self.assertContains(response, "ТКП Альфа")
        self.assertContains(response, "5556")
        self.assertContains(response, "ТКП Бета")

    def test_personal_worktime_row_form_lists_latest_tkp_first(self):
        response = self.client.get(
            reverse("personal_worktime_row_form"),
            {"week": "2026-04-07"},
        )

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertLess(content.index("ТКП Бета"), content.index("ТКП Альфа"))

    def test_personal_worktime_row_form_creates_project_week_assignment(self):
        response = self.client.post(
            reverse("personal_worktime_row_form"),
            {
                "week": "2026-04-07",
                "record_type": WorktimeAssignment.RecordType.PROJECT,
                "registration": str(self.registration.pk),
            },
        )

        self.assertEqual(response.status_code, 204)
        assignment = WorktimeAssignment.objects.get(
            registration=self.registration,
            executor_name=self._full_name(self.employee),
        )
        self.assertEqual(assignment.source_type, WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK)
        self.assertEqual(assignment.record_type, WorktimeAssignment.RecordType.PROJECT)
        self.assertTrue(
            PersonalWorktimeWeekAssignment.objects.filter(
                assignment=assignment,
                week_start=date(2026, 4, 6),
            ).exists()
        )

    def test_personal_worktime_row_form_creates_non_project_week_assignment_without_registration(self):
        response = self.client.post(
            reverse("personal_worktime_row_form"),
            {
                "week": "2026-04-07",
                "record_type": WorktimeAssignment.RecordType.SICK_LEAVE,
            },
        )

        self.assertEqual(response.status_code, 204)
        assignment = WorktimeAssignment.objects.get(
            registration__isnull=True,
            executor_name=self._full_name(self.employee),
            record_type=WorktimeAssignment.RecordType.SICK_LEAVE,
        )
        self.assertEqual(assignment.source_type, WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK)
        self.assertTrue(
            PersonalWorktimeWeekAssignment.objects.filter(
                assignment=assignment,
                week_start=date(2026, 4, 6),
            ).exists()
        )

    def test_personal_worktime_row_form_requires_project_when_project_type_selected(self):
        response = self.client.post(
            reverse("personal_worktime_row_form"),
            {
                "week": "2026-04-07",
                "record_type": WorktimeAssignment.RecordType.PROJECT,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Выберите проект для учета часов работы.")

    def test_personal_worktime_row_form_requires_tkp_when_tkp_type_selected(self):
        response = self.client.post(
            reverse("personal_worktime_row_form"),
            {
                "week": "2026-04-07",
                "record_type": WorktimeAssignment.RecordType.TKP,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Выберите ТКП для учета часов работы.")

    def test_personal_worktime_row_form_creates_tkp_week_assignment(self):
        response = self.client.post(
            reverse("personal_worktime_row_form"),
            {
                "week": "2026-04-07",
                "record_type": WorktimeAssignment.RecordType.TKP,
                "proposal_registration": str(self.proposal.pk),
            },
        )

        self.assertEqual(response.status_code, 204)
        assignment = WorktimeAssignment.objects.get(
            proposal_registration=self.proposal,
            executor_name=self._full_name(self.employee),
        )
        self.assertEqual(assignment.source_type, WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK)
        self.assertEqual(assignment.record_type, WorktimeAssignment.RecordType.TKP)
        self.assertTrue(
            PersonalWorktimeWeekAssignment.objects.filter(
                assignment=assignment,
                week_start=date(2026, 4, 6),
            ).exists()
        )

    def test_personal_partial_shows_tkp_assignment_as_registry_row(self):
        assignment = WorktimeAssignment.objects.create(
            proposal_registration=self.proposal,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK,
            record_type=WorktimeAssignment.RecordType.TKP,
        )
        PersonalWorktimeWeekAssignment.objects.create(
            assignment=assignment,
            week_start=date(2026, 4, 6),
        )

        response = self.client.get(reverse("personal_worktime_partial"), {"week": "2026-04-07"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.proposal.short_uid)
        self.assertContains(response, "WT")
        self.assertContains(response, "ТКП Альфа")
        self.assertNotContains(response, 'colspan="3" class="text-nowrap worktime-sticky-col-span3 worktime-col-merged"', html=False)

    def test_personal_partial_shows_manual_week_assignment_only_for_selected_week(self):
        assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK,
        )
        PersonalWorktimeWeekAssignment.objects.create(
            assignment=assignment,
            week_start=date(2026, 4, 6),
        )

        visible_response = self.client.get(reverse("personal_worktime_partial"), {"week": "2026-04-07"})
        hidden_response = self.client.get(reverse("personal_worktime_partial"), {"week": "2026-04-14"})

        self.assertContains(visible_response, "Проект Альфа")
        self.assertContains(visible_response, "WT")
        self.assertNotContains(hidden_response, "Проект Альфа")

    def test_personal_partial_shows_selected_record_type_for_manual_assignment(self):
        assignment = WorktimeAssignment.objects.create(
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK,
            record_type=WorktimeAssignment.RecordType.ADMINISTRATION,
        )
        PersonalWorktimeWeekAssignment.objects.create(
            assignment=assignment,
            week_start=date(2026, 4, 6),
        )

        response = self.client.get(reverse("personal_worktime_partial"), {"week": "2026-04-07"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Администрирование", count=1)
        self.assertContains(response, 'colspan="3" class="text-nowrap worktime-sticky-col-span3 worktime-col-merged"', html=False)

    def test_personal_partial_places_non_project_rows_below_project_rows(self):
        project_assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK,
        )
        non_project_assignment = WorktimeAssignment.objects.create(
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK,
            record_type=WorktimeAssignment.RecordType.TIME_OFF,
        )
        PersonalWorktimeWeekAssignment.objects.create(
            assignment=project_assignment,
            week_start=date(2026, 4, 6),
        )
        PersonalWorktimeWeekAssignment.objects.create(
            assignment=non_project_assignment,
            week_start=date(2026, 4, 6),
        )

        response = self.client.get(reverse("personal_worktime_partial"), {"week": "2026-04-07"})

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertLess(content.index("Проект Альфа"), content.index("Отгул"))

    def test_general_partial_shows_manual_week_assignment_only_when_period_has_hours(self):
        assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK,
        )
        PersonalWorktimeWeekAssignment.objects.create(
            assignment=assignment,
            week_start=date(2026, 4, 6),
        )
        WorktimeEntry.objects.create(
            assignment=assignment,
            work_date=date(2026, 4, 7),
            hours=8,
        )

        april_response = self.client.get(reverse("worktime_partial"), {"month": "2026-04"})
        may_response = self.client.get(reverse("worktime_partial"), {"month": "2026-05"})

        self.assertContains(april_response, "Проект Альфа")
        self.assertContains(april_response, self._full_name(self.employee))
        self.assertNotContains(may_response, "Проект Альфа")

    def test_general_partial_shows_non_project_manual_assignment_when_period_has_hours(self):
        assignment = WorktimeAssignment.objects.create(
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK,
            record_type=WorktimeAssignment.RecordType.TIME_OFF,
        )
        PersonalWorktimeWeekAssignment.objects.create(
            assignment=assignment,
            week_start=date(2026, 4, 6),
        )
        WorktimeEntry.objects.create(
            assignment=assignment,
            work_date=date(2026, 4, 7),
            hours=8,
        )

        response = self.client.get(reverse("worktime_partial"), {"month": "2026-04"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Отгул", count=1)
        self.assertContains(response, 'colspan="3" class="text-nowrap worktime-sticky-col-span3 worktime-col-merged"', html=False)

    def test_general_partial_shows_tkp_assignment_as_registry_row_when_period_has_hours(self):
        assignment = WorktimeAssignment.objects.create(
            proposal_registration=self.proposal,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK,
            record_type=WorktimeAssignment.RecordType.TKP,
        )
        PersonalWorktimeWeekAssignment.objects.create(
            assignment=assignment,
            week_start=date(2026, 4, 6),
        )
        WorktimeEntry.objects.create(
            assignment=assignment,
            work_date=date(2026, 4, 7),
            hours=8,
        )

        response = self.client.get(reverse("worktime_partial"), {"month": "2026-04"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.proposal.short_uid)
        self.assertContains(response, "WT")
        self.assertContains(response, "ТКП Альфа")
        self.assertNotContains(response, 'colspan="3" class="text-nowrap worktime-sticky-col-span3 worktime-col-merged"', html=False)

    def test_general_partial_places_non_project_rows_below_project_rows(self):
        project_assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        non_project_assignment = WorktimeAssignment.objects.create(
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK,
            record_type=WorktimeAssignment.RecordType.TIME_OFF,
        )
        PersonalWorktimeWeekAssignment.objects.create(
            assignment=non_project_assignment,
            week_start=date(2026, 4, 6),
        )
        WorktimeEntry.objects.create(
            assignment=project_assignment,
            work_date=date(2026, 4, 7),
            hours=4,
        )
        WorktimeEntry.objects.create(
            assignment=non_project_assignment,
            work_date=date(2026, 4, 7),
            hours=8,
        )

        response = self.client.get(reverse("worktime_partial"), {"month": "2026-04"})

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertLess(content.index("Проект Альфа"), content.index("Отгул"))

    def test_general_partial_renders_scale_filter_and_custom_period_picker(self):
        response = self.client.get(reverse("worktime_partial"), {"scale": "month", "period": "2026-04"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Масштаб:")
        self.assertContains(response, 'data-worktime-general-collapse-toggle', html=False)
        self.assertContains(response, 'data-worktime-period-form', html=False)
        self.assertContains(response, 'data-worktime-scale-value', html=False)
        self.assertContains(response, 'value="month"', html=False)
        self.assertContains(response, "Апрель, 2026 г.")

    def test_general_partial_renders_csv_controls_for_employee_month_breakdown(self):
        response = self.client.get(
            reverse("worktime_partial"),
            {"scale": "month", "period": "2026-04", "breakdown": "employees"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Скачать CSV")
        self.assertContains(response, "Загрузить CSV")
        self.assertContains(response, 'data-worktime-csv-download-url="/worktime/csv-download/"', html=False)
        self.assertContains(response, 'data-worktime-csv-upload-url="/worktime/csv-upload/"', html=False)
        self.assertContains(response, 'class="btn btn-primary btn-sm d-flex align-items-center"', html=False, count=2)
        self.assertContains(response, 'class="bi bi-cloud-arrow-down me-2"', html=False)
        self.assertNotContains(
            response,
            'disabled title="Загрузка и скачивание CSV доступны только для месячного табеля с разбивкой по сотрудникам."',
            html=False,
        )

    def test_general_partial_disables_csv_controls_for_activity_breakdown(self):
        response = self.client.get(
            reverse("worktime_partial"),
            {"scale": "month", "period": "2026-04", "breakdown": "activities"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Скачать CSV")
        self.assertContains(response, "Загрузить CSV")
        self.assertContains(
            response,
            'disabled title="Загрузка и скачивание CSV доступны только для месячного табеля с разбивкой по сотрудникам."',
            html=False,
            count=2,
        )
        self.assertContains(response, "Загрузка и скачивание CSV доступны только для месячного табеля с разбивкой по сотрудникам.")

    def test_general_partial_hides_csv_controls_for_non_admin_user(self):
        self.employee.role = ""
        self.employee.save(update_fields=["role"])

        response = self.client.get(
            reverse("worktime_partial"),
            {"scale": "month", "period": "2026-04", "breakdown": "employees"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Скачать CSV")
        self.assertNotContains(response, "Загрузить CSV")
        self.assertNotContains(response, 'data-worktime-csv-download-url="/worktime/csv-download/"', html=False)
        self.assertNotContains(response, 'data-worktime-csv-upload-url="/worktime/csv-upload/"', html=False)

    def test_general_partial_year_scale_aggregates_hours_by_month(self):
        assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        WorktimeEntry.objects.create(
            assignment=assignment,
            work_date=date(2026, 4, 7),
            hours=8,
        )
        WorktimeEntry.objects.create(
            assignment=assignment,
            work_date=date(2026, 4, 14),
            hours=5,
        )
        WorktimeEntry.objects.create(
            assignment=assignment,
            work_date=date(2026, 5, 2),
            hours=3,
        )

        response = self.client.get(reverse("worktime_partial"), {"scale": "year", "period": "2026"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Янв")
        self.assertContains(response, "Апр")
        self.assertContains(response, "Дек")
        self.assertContains(response, 'data-worktime-detail-row', html=False)
        self.assertContains(response, ">13<", html=False)
        self.assertContains(response, ">3<", html=False)
        self.assertNotContains(response, f'hours_{assignment.pk}_20260407', html=False)

    def test_worktime_csv_download_returns_selected_month_data(self):
        assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        WorktimeEntry.objects.create(
            assignment=assignment,
            work_date=date(2026, 4, 1),
            hours=7,
        )
        WorktimeEntry.objects.create(
            assignment=assignment,
            work_date=date(2026, 4, 3),
            hours=5,
        )

        response = self.client.get(
            reverse("worktime_csv_download"),
            {"scale": "month", "period": "2026-04", "breakdown": "employees"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertEqual(response["Content-Disposition"], 'attachment; filename="worktime-2026-04.csv"')
        rows = self._parse_worktime_csv_response(response)
        self.assertEqual(rows[0], self._worktime_csv_header("2026-04"))
        self.assertEqual(rows[1][0], self._full_name(self.employee))
        self.assertEqual(rows[1][1], assignment.display_project_code)
        self.assertEqual(rows[1][2], assignment.display_type_label)
        self.assertEqual(rows[1][3], assignment.display_project_name)
        self.assertEqual(rows[1][4], "7")
        self.assertEqual(rows[1][5], "")
        self.assertEqual(rows[1][6], "5")

    def test_worktime_csv_upload_replaces_only_selected_month_for_touched_rows(self):
        assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        untouched_assignment = WorktimeAssignment.objects.create(
            registration=self.second_registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PROJECT_MANAGER,
        )
        WorktimeEntry.objects.create(assignment=assignment, work_date=date(2026, 4, 1), hours=3)
        WorktimeEntry.objects.create(assignment=assignment, work_date=date(2026, 4, 2), hours=4)
        WorktimeEntry.objects.create(assignment=assignment, work_date=date(2026, 5, 1), hours=7)
        WorktimeEntry.objects.create(assignment=untouched_assignment, work_date=date(2026, 4, 1), hours=5)

        april_days = [""] * 30
        april_days[0] = "8"
        april_days[2] = "6"
        upload = self._make_worktime_csv_upload(
            self._worktime_csv_header("2026-04"),
            [[
                self._full_name(self.employee),
                assignment.display_project_code,
                assignment.display_type_label,
                assignment.display_project_name,
                *april_days,
            ]],
        )

        response = self.client.post(
            reverse("worktime_csv_upload"),
            {
                "csv_file": upload,
                "scale": "month",
                "period": "2026-04",
                "breakdown": "employees",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"ok": True, "created": 1, "updated": 1, "deleted": 1},
        )
        self.assertEqual(
            list(
                WorktimeEntry.objects.filter(assignment=assignment)
                .order_by("work_date")
                .values_list("work_date", "hours")
            ),
            [
                (date(2026, 4, 1), 8),
                (date(2026, 4, 3), 6),
                (date(2026, 5, 1), 7),
            ],
        )
        self.assertEqual(
            list(
                WorktimeEntry.objects.filter(assignment=untouched_assignment)
                .order_by("work_date")
                .values_list("work_date", "hours")
            ),
            [(date(2026, 4, 1), 5)],
        )

    def test_worktime_csv_upload_creates_missing_assignment_for_existing_project_and_employee(self):
        april_days = [""] * 30
        april_days[0] = "8"
        upload = self._make_worktime_csv_upload(
            self._worktime_csv_header("2026-04"),
            [[
                self._full_name(self.employee),
                self.second_registration.short_uid,
                self.second_registration.type_short_display or "—",
                self.second_registration.name,
                *april_days,
            ]],
        )

        response = self.client.post(
            reverse("worktime_csv_upload"),
            {
                "csv_file": upload,
                "scale": "month",
                "period": "2026-04",
                "breakdown": "employees",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "ok": True,
                "created": 1,
                "updated": 0,
                "deleted": 0,
                "created_assignments": 1,
            },
        )
        assignment = WorktimeAssignment.objects.get(
            registration=self.second_registration,
            executor_name=self._full_name(self.employee),
        )
        self.assertEqual(assignment.employee, self.employee)
        self.assertEqual(assignment.record_type, WorktimeAssignment.RecordType.PROJECT)
        self.assertEqual(assignment.source_type, WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK)
        self.assertTrue(
            PersonalWorktimeWeekAssignment.objects.filter(
                assignment=assignment,
                week_start=date(2026, 3, 30),
            ).exists()
        )
        self.assertEqual(
            list(
                WorktimeEntry.objects.filter(assignment=assignment)
                .order_by("work_date")
                .values_list("work_date", "hours")
            ),
            [(date(2026, 4, 1), 8)],
        )
        visible_response = self.client.get(reverse("personal_worktime_partial"), {"week": "2026-04-01"})
        hidden_response = self.client.get(reverse("personal_worktime_partial"), {"week": "2026-04-14"})
        self.assertContains(visible_response, self.second_registration.name)
        self.assertNotContains(hidden_response, self.second_registration.name)

    def test_worktime_csv_upload_accepts_decimal_hours(self):
        assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        april_days = [""] * 30
        april_days[0] = "7,5"
        april_days[1] = "0.25"
        upload = self._make_worktime_csv_upload(
            self._worktime_csv_header("2026-04"),
            [[
                self._full_name(self.employee),
                assignment.display_project_code,
                assignment.display_type_label,
                assignment.display_project_name,
                *april_days,
            ]],
        )

        response = self.client.post(
            reverse("worktime_csv_upload"),
            {
                "csv_file": upload,
                "scale": "month",
                "period": "2026-04",
                "breakdown": "employees",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"ok": True, "created": 2, "updated": 0, "deleted": 0},
        )
        self.assertEqual(
            list(
                WorktimeEntry.objects.filter(assignment=assignment)
                .order_by("work_date")
                .values_list("work_date", "hours")
            ),
            [
                (date(2026, 4, 1), Decimal("7.50")),
                (date(2026, 4, 2), Decimal("0.25")),
            ],
        )

    def test_worktime_csv_upload_reuses_existing_manual_assignment_and_adds_missing_week_links(self):
        assignment = WorktimeAssignment.objects.create(
            registration=self.second_registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK,
        )
        PersonalWorktimeWeekAssignment.objects.create(
            assignment=assignment,
            week_start=date(2026, 3, 30),
        )
        WorktimeEntry.objects.create(assignment=assignment, work_date=date(2026, 4, 1), hours=8)

        april_days = [""] * 30
        april_days[0] = "8"
        april_days[13] = "6"
        upload = self._make_worktime_csv_upload(
            self._worktime_csv_header("2026-04"),
            [[
                self._full_name(self.employee),
                self.second_registration.short_uid,
                self.second_registration.type_short_display or "—",
                self.second_registration.name,
                *april_days,
            ]],
        )

        response = self.client.post(
            reverse("worktime_csv_upload"),
            {
                "csv_file": upload,
                "scale": "month",
                "period": "2026-04",
                "breakdown": "employees",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"ok": True, "created": 1, "updated": 0, "deleted": 0},
        )
        self.assertTrue(
            PersonalWorktimeWeekAssignment.objects.filter(
                assignment=assignment,
                week_start=date(2026, 4, 13),
            ).exists()
        )
        self.assertEqual(
            list(
                WorktimeEntry.objects.filter(assignment=assignment)
                .order_by("work_date")
                .values_list("work_date", "hours")
            ),
            [(date(2026, 4, 1), 8), (date(2026, 4, 14), 6)],
        )
        visible_response = self.client.get(reverse("personal_worktime_partial"), {"week": "2026-04-14"})
        self.assertContains(visible_response, self.second_registration.name)

    def test_build_worktime_csv_project_index_prefetches_product_links(self):
        third_registration = ProjectRegistration.objects.create(
            number=4446,
            type=self.product,
            name="Проект Гамма",
            deadline=date(2026, 4, 30),
        )
        for registration, rank in (
            (self.registration, 1),
            (self.second_registration, 2),
            (third_registration, 3),
        ):
            ProjectRegistrationProduct.objects.create(
                registration=registration,
                product=self.product,
                rank=rank,
            )

        with CaptureQueriesContext(connection) as queries:
            projects_by_code, projects_by_key, duplicate_keys = _build_worktime_csv_project_index()

        self.assertLessEqual(len(queries), 3)
        self.assertIn(self.registration.short_uid.casefold(), projects_by_code)
        self.assertIn(third_registration.short_uid.casefold(), projects_by_code)
        self.assertFalse(duplicate_keys)
        self.assertIn(
            (
                self.registration.short_uid.casefold(),
                (self.registration.type_short_display or "—").casefold(),
                self.registration.name.casefold(),
            ),
            projects_by_key,
        )

    def test_worktime_csv_upload_rejects_missing_file(self):
        response = self.client.post(
            reverse("worktime_csv_upload"),
            {"scale": "month", "period": "2026-04", "breakdown": "employees"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"ok": False, "error": "Файл не выбран."})

    def test_worktime_csv_upload_rejects_non_csv_file(self):
        response = self.client.post(
            reverse("worktime_csv_upload"),
            {
                "csv_file": SimpleUploadedFile("worktime.txt", b"test", content_type="text/plain"),
                "scale": "month",
                "period": "2026-04",
                "breakdown": "employees",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"ok": False, "error": "Допустимы только файлы CSV."})

    def test_worktime_csv_upload_rejects_invalid_header(self):
        upload = self._make_worktime_csv_upload(
            ["Сотрудник", "Проект", "Тип", "Название", "1", "2"],
            [["Иван Иванов", "4444", "WT", "Проект Альфа", "8", "4"]],
        )

        response = self.client.post(
            reverse("worktime_csv_upload"),
            {
                "csv_file": upload,
                "scale": "month",
                "period": "2026-04",
                "breakdown": "employees",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        self.assertIn("CSV должен содержать колонки:", response.json()["error"])

    def test_worktime_csv_upload_reports_unknown_row(self):
        assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        april_days = [""] * 30
        april_days[0] = "8"
        upload = self._make_worktime_csv_upload(
            self._worktime_csv_header("2026-04"),
            [[
                "Несуществующий Сотрудник",
                assignment.display_project_code,
                assignment.display_type_label,
                assignment.display_project_name,
                *april_days,
            ]],
        )

        response = self.client.post(
            reverse("worktime_csv_upload"),
            {
                "csv_file": upload,
                "scale": "month",
                "period": "2026-04",
                "breakdown": "employees",
            },
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error"], "Не удалось обработать ни одной строки табеля.")
        self.assertIn("не найден среди штатных сотрудников", payload["warnings"][0])

    def test_worktime_csv_upload_rejects_hours_out_of_range(self):
        assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        april_days = [""] * 30
        april_days[0] = "25"
        upload = self._make_worktime_csv_upload(
            self._worktime_csv_header("2026-04"),
            [[
                self._full_name(self.employee),
                assignment.display_project_code,
                assignment.display_type_label,
                assignment.display_project_name,
                *april_days,
            ]],
        )

        response = self.client.post(
            reverse("worktime_csv_upload"),
            {
                "csv_file": upload,
                "scale": "month",
                "period": "2026-04",
                "breakdown": "employees",
            },
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error"], "Не удалось обработать ни одной строки табеля.")
        self.assertIn("должно быть в диапазоне от 0 до 24", payload["warnings"][0])

    def test_worktime_csv_upload_rejects_activity_breakdown(self):
        upload = self._make_worktime_csv_upload(
            self._worktime_csv_header("2026-04"),
            [],
        )

        response = self.client.post(
            reverse("worktime_csv_upload"),
            {
                "csv_file": upload,
                "scale": "month",
                "period": "2026-04",
                "breakdown": "activities",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {
                "ok": False,
                "error": "Загрузка и скачивание CSV доступны только для месячного табеля с разбивкой по сотрудникам.",
            },
        )

    def test_worktime_csv_download_rejects_year_scale(self):
        response = self.client.get(
            reverse("worktime_csv_download"),
            {"scale": "year", "period": "2026", "breakdown": "employees"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.content.decode("utf-8"),
            "Загрузка и скачивание CSV доступны только для месячного табеля с разбивкой по сотрудникам.",
        )

    def test_worktime_csv_upload_forbidden_for_non_admin_role(self):
        self.employee.role = ""
        self.employee.save(update_fields=["role"])
        upload = self._make_worktime_csv_upload(self._worktime_csv_header("2026-04"), [])

        response = self.client.post(
            reverse("worktime_csv_upload"),
            {
                "csv_file": upload,
                "scale": "month",
                "period": "2026-04",
                "breakdown": "employees",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json(),
            {
                "ok": False,
                "error": "Загрузка и скачивание CSV доступны только пользователям с ролью Администратор.",
            },
        )

    def test_worktime_csv_download_forbidden_for_non_admin_role(self):
        self.employee.role = ""
        self.employee.save(update_fields=["role"])

        response = self.client.get(
            reverse("worktime_csv_download"),
            {"scale": "month", "period": "2026-04", "breakdown": "employees"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.content.decode("utf-8"),
            "Загрузка и скачивание CSV доступны только пользователям с ролью Администратор.",
        )

    def test_panel_defers_initial_timesheet_load_until_explicit_event(self):
        request = self.factory.get("/")
        request.user = self.user

        html = render_to_string("worktime_app/panel.html", request=request)

        self.assertIn('hx-trigger="worktime-timesheet-load-ready once from:body, worktime-updated-worktime-timesheet-load-ready from:body"', html)
        self.assertNotIn('hx-trigger="load, worktime-updated from:body"', html)
