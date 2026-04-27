import csv
import io
import json
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

from classifiers_app.models import OKSMCountry, ProductionCalendarDay
from group_app.models import GroupMember
from notifications_app.models import Notification, NotificationPerformerLink
from notifications_app.services import process_participation_notification
from policy_app.models import ADMIN_GROUP, DEPARTMENT_HEAD_GROUP, Product
from projects_app.models import Performer, ProjectRegistration, ProjectRegistrationProduct
from proposals_app.models import ProposalRegistration
from users_app.models import Employee
from worktime_app.models import PersonalWorktimeWeekAssignment, WorktimeAssignment, WorktimeEntry
from worktime_app.views import (
    REGULAR_WORKDAY_HOURS,
    SHORTENED_WORKDAY_HOURS,
    ZERO_DECIMAL,
    _attach_group_histograms,
    _attach_row_histograms,
    _build_worktime_csv_project_index,
    _personal_week_order_ids,
    _personal_week_order_signature,
    _worktime_context,
)


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

    def test_attach_group_histograms_uses_zero_width_for_zero_totals(self):
        groups = [
            {
                "grand_total": 0,
                "rows": [
                    {"total_hours": 0},
                ],
            },
            {
                "grand_total": 10,
                "rows": [
                    {"total_hours": 0},
                    {"total_hours": 10},
                ],
            },
        ]

        result = _attach_group_histograms(groups)

        self.assertEqual(result[0]["histogram_width_percent"], Decimal("0"))
        self.assertEqual(result[0]["rows"][0]["histogram_width_percent"], Decimal("0"))
        self.assertEqual(result[1]["rows"][0]["histogram_width_percent"], Decimal("0"))
        self.assertEqual(result[1]["rows"][1]["histogram_width_percent"], Decimal("100"))

    def test_attach_row_histograms_uses_zero_width_for_zero_totals(self):
        rows = [
            {"total_hours": 0},
            {"total_hours": 5},
            {"total_hours": 10},
        ]

        result = _attach_row_histograms(rows)

        self.assertEqual(result[0]["histogram_width_percent"], Decimal("0"))
        self.assertEqual(result[1]["histogram_width_percent"], Decimal("59"))
        self.assertEqual(result[2]["histogram_width_percent"], Decimal("100"))

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
        self.assertContains(response, "3,3")

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
        self.assertContains(response, "{ key: 'vacation', label: 'Отпуск', color: '#e39bc9' }", html=False)
        self.assertContains(
            response,
            "{ key: 'other_absence', label: 'Прочее отсутствие', categoryKey: 'absence', categoryLabel: 'Отсутствие', color: '#b8c2cc' }",
            html=False,
        )
        self.assertContains(
            response,
            "{ key: 'time_off', label: 'Отгул', categoryKey: 'absence', categoryLabel: 'Отсутствие', color: '#d9e0e6' }",
            html=False,
        )
        self.assertContains(response, 'class="table-light fw-semibold worktime-summary-row worktime-group-row"', html=False)
        self.assertContains(response, 'class="fw-semibold worktime-summary-row worktime-grand-summary-row"', html=False)

    def test_general_partial_marks_non_working_day_columns(self):
        country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            alpha2="RU",
            alpha3="RUS",
        )
        company = GroupMember.objects.create(
            short_name="IMC Russia",
            country_name="Россия",
            country_code="643",
        )
        self.employee.employment = company.short_name
        self.employee.save(update_fields=["employment"])
        ProductionCalendarDay.objects.create(country=country, date=date(2026, 4, 8), is_working_day=False, is_holiday=True, working_hours=Decimal("0.0"))
        assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        WorktimeEntry.objects.create(assignment=assignment, work_date=date(2026, 4, 8), hours=Decimal("5"))

        response = self.client.get(reverse("worktime_partial"), {"month": "2026-04"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["days"][7]["is_non_working_day"])
        self.assertTrue(response.context["groups"][0]["rows"][0]["cells"][7]["is_non_working_day"])
        self.assertTrue(response.context["groups"][0]["column_cells"][7]["is_non_working_day"])
        self.assertTrue(response.context["total_column_cells"][7]["is_non_working_day"])
        self.assertTrue(response.context["daily_histogram"]["columns"][7]["is_non_working_day"])
        self.assertContains(response, "worktime-non-working-day-cell", html=False)
        self.assertContains(response, "worktime-non-working-day-total-cell", html=False)
        self.assertNotContains(response, 'class="worktime-daily-histogram-cell worktime-non-working-day-chart-cell"', html=False)

    def test_general_non_working_days_follow_selected_company_filter(self):
        selected_country = OKSMCountry.objects.create(
            number=398,
            code="398",
            short_name="Казахстан",
            alpha2="KZ",
            alpha3="KAZ",
        )
        selected_company = GroupMember.objects.create(
            short_name="IMC Kazakhstan",
            country_name="Казахстан",
            country_code="398",
        )
        self.other_employee.employment = selected_company.short_name
        self.other_employee.save(update_fields=["employment"])
        ProductionCalendarDay.objects.create(
            country=selected_country,
            date=date(2026, 4, 8),
            is_working_day=False,
            is_holiday=True,
            working_hours=Decimal("0.0"),
        )
        assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.other_employee,
            executor_name=self._full_name(self.other_employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        WorktimeEntry.objects.create(assignment=assignment, work_date=date(2026, 4, 8), hours=Decimal("5"))

        response = self.client.get(reverse("worktime_partial"), {"month": "2026-04", "company": str(selected_company.pk)})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["days"][7]["is_non_working_day"])
        self.assertContains(response, "worktime-non-working-day-head", html=False)

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

    def test_general_partial_filters_assignments_by_employee_company(self):
        first_company = GroupMember.objects.create(
            short_name="IMC Alpha",
            country_name="Россия",
            position=1,
        )
        second_company = GroupMember.objects.create(
            short_name="IMC Beta",
            country_name="Россия",
            position=2,
        )
        self.employee.employment = first_company.short_name
        self.employee.save(update_fields=["employment"])
        self.other_employee.employment = second_company.short_name
        self.other_employee.save(update_fields=["employment"])
        first_assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        second_assignment = WorktimeAssignment.objects.create(
            registration=self.second_registration,
            employee=self.other_employee,
            executor_name=self._full_name(self.other_employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        WorktimeEntry.objects.create(assignment=first_assignment, work_date=date(2026, 4, 1), hours=7)
        WorktimeEntry.objects.create(assignment=second_assignment, work_date=date(2026, 4, 2), hours=5)

        response = self.client.get(reverse("worktime_partial"), {"month": "2026-04", "company": str(first_company.pk)})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self._full_name(self.employee))
        self.assertContains(response, "Проект Альфа")
        self.assertContains(response, f'name="company" value="{first_company.pk}"', html=False)
        self.assertNotContains(response, self._full_name(self.other_employee))
        self.assertNotContains(response, "Проект Бета")

    def test_personal_context_includes_production_calendar_marks_for_employee_country(self):
        country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            alpha2="RU",
            alpha3="RUS",
        )
        company = GroupMember.objects.create(
            short_name="IMC Russia",
            country_name="Россия",
            country_code="643",
        )
        self.employee.employment = company.short_name
        self.employee.save(update_fields=["employment"])
        ProductionCalendarDay.objects.create(
            country=country,
            date=date(2026, 5, 4),
            is_working_day=False,
            is_weekend=True,
            is_holiday=True,
        )
        ProductionCalendarDay.objects.create(
            country=country,
            date=date(2026, 5, 9),
            is_working_day=False,
            is_weekend=True,
        )
        ProductionCalendarDay.objects.create(
            country=country,
            date=date(2026, 5, 10),
            is_working_day=False,
            is_weekend=True,
        )
        ProductionCalendarDay.objects.create(
            country=country,
            date=date(2026, 5, 11),
            is_working_day=False,
            is_holiday=True,
        )
        ProductionCalendarDay.objects.create(
            country=country,
            date=date(2026, 5, 8),
            is_working_day=True,
            is_shortened_day=True,
        )

        context = _worktime_context(self.user, personal_only=True, month_start=date(2026, 5, 4))
        marks = json.loads(context["personal_calendar_marks_json"])

        self.assertEqual(marks["2026-05-04"], "holiday")
        self.assertEqual(marks["2026-05-08"], "shortened")
        self.assertEqual(marks["2026-05-09"], "holiday")
        self.assertEqual(marks["2026-05-10"], "holiday")
        self.assertEqual(context["personal_calendar_mark_years"], "2026")
        self.assertEqual(context["personal_calendar_marks_url"], reverse("personal_worktime_calendar_marks"))

    def test_personal_calendar_marks_endpoint_uses_employee_employment_country(self):
        country = OKSMCountry.objects.create(
            number=398,
            code="398",
            short_name="Казахстан",
            alpha2="KZ",
            alpha3="KAZ",
        )
        company = GroupMember.objects.create(
            short_name="IMC Kazakhstan",
            country_name="Казахстан",
            country_code="398",
        )
        self.employee.employment = company.short_name
        self.employee.save(update_fields=["employment"])
        ProductionCalendarDay.objects.create(
            country=country,
            date=date(2026, 3, 21),
            is_working_day=False,
            is_holiday=True,
            holiday_name="Праздник",
        )
        ProductionCalendarDay.objects.create(
            country=country,
            date=date(2026, 3, 22),
            is_working_day=False,
            is_weekend=True,
        )
        ProductionCalendarDay.objects.create(
            country=country,
            date=date(2026, 12, 31),
            is_working_day=True,
            is_shortened_day=True,
        )

        response = self.client.get(reverse("personal_worktime_calendar_marks"), {"year": "2026"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["days"],
            {
                "2026-03-21": "holiday",
                "2026-03-22": "holiday",
                "2026-12-31": "shortened",
            },
        )

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
        PersonalWorktimeWeekAssignment.objects.create(assignment=tkp_assignment, week_start=date(2026, 3, 30))
        WorktimeEntry.objects.create(assignment=project_assignment, work_date=date(2026, 4, 1), hours=6)
        WorktimeEntry.objects.create(assignment=project_assignment, work_date=date(2026, 4, 2), hours=2)
        WorktimeEntry.objects.create(assignment=tkp_assignment, work_date=date(2026, 4, 3), hours=4)

        employee_context = _worktime_context(self.user, month_start=date(2026, 4, 1), breakdown="employees")
        activity_context = _worktime_context(self.user, month_start=date(2026, 4, 1), breakdown="activities")

        self.assertEqual(employee_context["grand_total"], activity_context["grand_total"])
        self.assertEqual(employee_context["column_totals"], activity_context["column_totals"])
        self.assertEqual(activity_context["breakdown_value"], "activities")

    def test_worktime_context_builds_daily_histogram_by_record_type(self):
        project_assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        business_assignment = WorktimeAssignment.objects.create(
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK,
            record_type=WorktimeAssignment.RecordType.BUSINESS_DEVELOPMENT,
        )
        sick_leave_assignment = WorktimeAssignment.objects.create(
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK,
            record_type=WorktimeAssignment.RecordType.SICK_LEAVE,
        )
        PersonalWorktimeWeekAssignment.objects.create(assignment=business_assignment, week_start=date(2026, 3, 30))
        PersonalWorktimeWeekAssignment.objects.create(assignment=sick_leave_assignment, week_start=date(2026, 3, 30))
        WorktimeEntry.objects.create(assignment=project_assignment, work_date=date(2026, 4, 1), hours=6)
        WorktimeEntry.objects.create(assignment=sick_leave_assignment, work_date=date(2026, 4, 1), hours=2)
        WorktimeEntry.objects.create(assignment=business_assignment, work_date=date(2026, 4, 2), hours=3)

        context = _worktime_context(self.user, month_start=date(2026, 4, 1), breakdown="employees")

        daily_histogram = context["daily_histogram"]
        self.assertTrue(daily_histogram["has_data"])
        self.assertTrue(daily_histogram["composition"]["has_data"])
        first_day = daily_histogram["columns"][0]
        second_day = daily_histogram["columns"][1]
        first_day_segments = {segment["key"]: segment for segment in first_day["segments"]}
        second_day_segments = {segment["key"]: segment for segment in second_day["segments"]}
        composition_categories = {category["key"]: category for category in daily_histogram["composition"]["categories"]}
        composition_segments = {segment["key"]: segment for segment in daily_histogram["composition"]["segments"]}

        self.assertEqual(first_day["total"], Decimal("8"))
        self.assertEqual(first_day_segments["project"]["value"], Decimal("6"))
        self.assertEqual(first_day_segments["project"]["height_percent"], Decimal("75"))
        self.assertEqual(first_day_segments["sick_leave"]["value"], Decimal("2"))
        self.assertEqual(first_day_segments["sick_leave"]["height_percent"], Decimal("25"))
        self.assertEqual(second_day["total"], Decimal("3"))
        self.assertEqual(second_day_segments["business_development"]["value"], Decimal("3"))
        self.assertEqual(second_day_segments["business_development"]["height_percent"], Decimal("37.5"))
        self.assertEqual(daily_histogram["composition"]["total"], Decimal("11"))
        self.assertEqual(composition_categories["work"]["value"], Decimal("6"))
        self.assertEqual(composition_categories["development"]["value"], Decimal("3"))
        self.assertEqual(composition_categories["absence"]["value"], Decimal("2"))
        self.assertEqual(composition_segments["project"]["value"], Decimal("6"))
        self.assertEqual(composition_segments["business_development"]["value"], Decimal("3"))
        self.assertEqual(composition_segments["sick_leave"]["value"], Decimal("2"))
        self.assertEqual(composition_segments["other_absence"]["color"], "#b8c2cc")
        self.assertEqual(composition_segments["time_off"]["color"], "#d9e0e6")
        self.assertIn("conic-gradient(", daily_histogram["composition"]["outer_gradient"])
        self.assertIn("conic-gradient(", daily_histogram["composition"]["inner_gradient"])

    def test_worktime_context_builds_daily_histogram_for_vacation_record_type(self):
        vacation_assignment = WorktimeAssignment.objects.create(
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK,
            record_type=WorktimeAssignment.RecordType.VACATION,
        )
        PersonalWorktimeWeekAssignment.objects.create(assignment=vacation_assignment, week_start=date(2026, 3, 30))
        WorktimeEntry.objects.create(assignment=vacation_assignment, work_date=date(2026, 4, 3), hours=8)

        context = _worktime_context(self.user, month_start=date(2026, 4, 1), breakdown="employees")

        third_day = context["daily_histogram"]["columns"][2]
        third_day_segments = {segment["key"]: segment for segment in third_day["segments"]}
        composition_categories = {
            category["key"]: category for category in context["daily_histogram"]["composition"]["categories"]
        }
        composition_segments = {
            segment["key"]: segment for segment in context["daily_histogram"]["composition"]["segments"]
        }

        self.assertEqual(third_day["total"], Decimal("8"))
        self.assertEqual(third_day_segments["vacation"]["value"], Decimal("8"))
        self.assertEqual(third_day_segments["vacation"]["height_percent"], Decimal("100"))
        self.assertEqual(composition_categories["vacation"]["value"], Decimal("8"))
        self.assertEqual(composition_segments["vacation"]["value"], Decimal("8"))

    def test_general_context_ignores_manual_hours_without_visible_personal_week_link(self):
        assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK,
        )
        PersonalWorktimeWeekAssignment.objects.create(assignment=assignment, week_start=date(2026, 3, 23))
        WorktimeEntry.objects.create(assignment=assignment, work_date=date(2026, 4, 4), hours=5)
        WorktimeEntry.objects.create(assignment=assignment, work_date=date(2026, 4, 5), hours=5)

        context = _worktime_context(self.user, month_start=date(2026, 4, 1), breakdown="employees")

        self.assertEqual(context["grand_total"], 0)
        self.assertEqual(context["groups"], [])
        self.assertEqual(context["daily_histogram"]["columns"][3]["total"], ZERO_DECIMAL)
        self.assertEqual(context["daily_histogram"]["columns"][4]["total"], ZERO_DECIMAL)

    def test_general_context_counts_manual_hours_only_inside_visible_personal_weeks(self):
        assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK,
        )
        PersonalWorktimeWeekAssignment.objects.create(assignment=assignment, week_start=date(2026, 3, 30))
        WorktimeEntry.objects.create(assignment=assignment, work_date=date(2026, 4, 4), hours=5)
        WorktimeEntry.objects.create(assignment=assignment, work_date=date(2026, 4, 6), hours=7)

        context = _worktime_context(self.user, month_start=date(2026, 4, 1), breakdown="employees")

        self.assertEqual(context["grand_total"], Decimal("5"))
        self.assertEqual(context["column_totals"][3], Decimal("5"))
        self.assertEqual(context["column_totals"][5], 0)

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
        self.assertContains(response, 'class="worktime-hist-head"', html=False)
        self.assertContains(response, 'class="worktime-hist-cell worktime-hist-cell-bar"', html=False)
        self.assertContains(response, 'class="worktime-hist-bar worktime-hist-bar-secondary"', html=False)
        self.assertContains(response, 'data-worktime-hist-sort-btn="desc"', html=False)
        self.assertContains(response, 'data-worktime-hist-sort-btn="asc"', html=False)
        self.assertContains(response, ">5<", html=False)
        self.assertContains(response, 'hx-get="/worktime/partial/personal/"', html=False)

    def test_personal_context_adds_calculated_downtime_row_from_production_calendar(self):
        country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            alpha2="RU",
            alpha3="RUS",
        )
        company = GroupMember.objects.create(
            short_name="IMC Russia",
            country_name="Россия",
            country_code="643",
        )
        self.employee.employment = company.short_name
        self.employee.save(update_fields=["employment"])
        ProductionCalendarDay.objects.create(country=country, date=date(2026, 4, 6), is_working_day=True, working_hours=Decimal("8.0"))
        ProductionCalendarDay.objects.create(
            country=country,
            date=date(2026, 4, 7),
            is_working_day=True,
            is_shortened_day=True,
            working_hours=Decimal("7.0"),
        )
        ProductionCalendarDay.objects.create(country=country, date=date(2026, 4, 8), is_working_day=False, is_holiday=True, working_hours=Decimal("0.0"))
        ProductionCalendarDay.objects.create(country=country, date=date(2026, 4, 9), is_working_day=False, is_weekend=True, working_hours=Decimal("0.0"))
        ProductionCalendarDay.objects.create(country=country, date=date(2026, 4, 10), is_working_day=True, is_shortened_day=True)
        project_assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        PersonalWorktimeWeekAssignment.objects.create(assignment=project_assignment, week_start=date(2026, 4, 6))
        WorktimeEntry.objects.create(assignment=project_assignment, work_date=date(2026, 4, 6), hours=Decimal("2"))
        WorktimeEntry.objects.create(assignment=project_assignment, work_date=date(2026, 4, 7), hours=Decimal("3"))
        WorktimeEntry.objects.create(assignment=project_assignment, work_date=date(2026, 4, 9), hours=Decimal("5"))

        context = _worktime_context(self.user, personal_only=True, month_start=date(2026, 4, 6))
        downtime_row = context["rows"][-1]
        downtime_values = [cell["value"] for cell in downtime_row["cells"]]
        histogram_columns = context["daily_histogram"]["columns"]

        self.assertEqual(downtime_row["assignment"].record_type, WorktimeAssignment.RecordType.DOWNTIME)
        self.assertTrue(downtime_row["is_calculated_downtime"])
        self.assertTrue(downtime_row["is_locked"])
        self.assertEqual(downtime_values[:5], [Decimal("6.0"), Decimal("4.0"), ZERO_DECIMAL, ZERO_DECIMAL, SHORTENED_WORKDAY_HOURS])
        self.assertFalse(context["days"][0]["is_non_working_day"])
        self.assertTrue(context["days"][2]["is_non_working_day"])
        self.assertTrue(context["days"][3]["is_non_working_day"])
        self.assertFalse(downtime_row["cells"][0]["is_non_working_day"])
        self.assertTrue(downtime_row["cells"][2]["is_non_working_day"])
        self.assertTrue(downtime_row["cells"][2]["hide_downtime_zero"])
        self.assertTrue(downtime_row["cells"][3]["hide_downtime_zero"])
        self.assertTrue(context["summary_column_cells"][2]["is_empty_non_working_day"])
        self.assertFalse(context["summary_column_cells"][3]["is_empty_non_working_day"])
        self.assertEqual(histogram_columns[0]["segments"][0]["value"], Decimal("6.0"))
        self.assertEqual(histogram_columns[1]["segments"][0]["value"], Decimal("4.0"))
        self.assertTrue(histogram_columns[2]["is_non_working_day"])
        self.assertTrue(histogram_columns[3]["is_non_working_day"])
        self.assertEqual(histogram_columns[3]["segments"][0]["value"], ZERO_DECIMAL)
        self.assertEqual(histogram_columns[4]["segments"][0]["value"], ZERO_DECIMAL)

    def test_personal_vacation_hours_are_blocked_on_non_working_days(self):
        country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            alpha2="RU",
            alpha3="RUS",
        )
        company = GroupMember.objects.create(
            short_name="IMC Russia",
            country_name="Россия",
            country_code="643",
        )
        self.employee.employment = company.short_name
        self.employee.save(update_fields=["employment"])
        ProductionCalendarDay.objects.create(country=country, date=date(2026, 4, 7), is_working_day=True, working_hours=Decimal("8.0"))
        ProductionCalendarDay.objects.create(country=country, date=date(2026, 4, 8), is_working_day=False, is_holiday=True, working_hours=Decimal("0.0"))
        vacation_assignment = WorktimeAssignment.objects.create(
            record_type=WorktimeAssignment.RecordType.VACATION,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK,
        )
        PersonalWorktimeWeekAssignment.objects.create(assignment=vacation_assignment, week_start=date(2026, 4, 6))
        WorktimeEntry.objects.create(assignment=vacation_assignment, work_date=date(2026, 4, 7), hours=Decimal("4"))
        WorktimeEntry.objects.create(assignment=vacation_assignment, work_date=date(2026, 4, 8), hours=Decimal("8"))

        response = self.client.get(reverse("personal_worktime_partial"), {"week": "2026-04-10"})

        self.assertEqual(response.status_code, 200)
        vacation_row = next(
            row for row in response.context["rows"]
            if row["assignment"].pk == vacation_assignment.pk
        )
        self.assertEqual(vacation_row["cells"][1]["value"], Decimal("4"))
        self.assertFalse(vacation_row["cells"][1]["is_vacation_non_working_day"])
        self.assertIsNone(vacation_row["cells"][2]["value"])
        self.assertTrue(vacation_row["cells"][2]["is_vacation_non_working_day"])
        self.assertContains(response, "data-worktime-vacation-non-working-input", html=False)

    def test_personal_partial_disables_absence_hours_on_non_working_days(self):
        country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            alpha2="RU",
            alpha3="RUS",
        )
        company = GroupMember.objects.create(
            short_name="IMC Russia",
            country_name="Россия",
            country_code="643",
        )
        self.employee.employment = company.short_name
        self.employee.save(update_fields=["employment"])
        ProductionCalendarDay.objects.create(country=country, date=date(2026, 4, 8), is_working_day=False, is_holiday=True, working_hours=Decimal("0.0"))
        time_off_assignment = WorktimeAssignment.objects.create(
            record_type=WorktimeAssignment.RecordType.TIME_OFF,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK,
        )
        PersonalWorktimeWeekAssignment.objects.create(assignment=time_off_assignment, week_start=date(2026, 4, 6))
        WorktimeEntry.objects.create(assignment=time_off_assignment, work_date=date(2026, 4, 8), hours=Decimal("8"))

        response = self.client.get(reverse("personal_worktime_partial"), {"week": "2026-04-10"})

        self.assertEqual(response.status_code, 200)
        time_off_row = next(
            row for row in response.context["rows"]
            if row["assignment"].pk == time_off_assignment.pk
        )
        self.assertIsNone(time_off_row["cells"][2]["value"])
        self.assertTrue(time_off_row["cells"][2]["is_blocked_non_working_day"])
        self.assertContains(response, "data-worktime-blocked-non-working-input", html=False)

    def test_personal_save_removes_vacation_hours_on_non_working_days(self):
        country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            alpha2="RU",
            alpha3="RUS",
        )
        company = GroupMember.objects.create(
            short_name="IMC Russia",
            country_name="Россия",
            country_code="643",
        )
        self.employee.employment = company.short_name
        self.employee.save(update_fields=["employment"])
        ProductionCalendarDay.objects.create(country=country, date=date(2026, 4, 8), is_working_day=False, is_holiday=True, working_hours=Decimal("0.0"))
        vacation_assignment = WorktimeAssignment.objects.create(
            record_type=WorktimeAssignment.RecordType.VACATION,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK,
        )
        PersonalWorktimeWeekAssignment.objects.create(assignment=vacation_assignment, week_start=date(2026, 4, 6))
        WorktimeEntry.objects.create(assignment=vacation_assignment, work_date=date(2026, 4, 8), hours=Decimal("8"))

        response = self.client.post(
            reverse("worktime_save"),
            {
                "scope": "personal",
                "week": "2026-04-10",
                "assignment_ids": [str(vacation_assignment.pk)],
                f"hours_{vacation_assignment.pk}_20260408": "6",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            WorktimeEntry.objects.filter(
                assignment=vacation_assignment,
                work_date=date(2026, 4, 8),
            ).exists()
        )

    def test_personal_save_removes_absence_hours_on_non_working_days(self):
        country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            alpha2="RU",
            alpha3="RUS",
        )
        company = GroupMember.objects.create(
            short_name="IMC Russia",
            country_name="Россия",
            country_code="643",
        )
        self.employee.employment = company.short_name
        self.employee.save(update_fields=["employment"])
        ProductionCalendarDay.objects.create(country=country, date=date(2026, 4, 8), is_working_day=False, is_holiday=True, working_hours=Decimal("0.0"))
        sick_leave_assignment = WorktimeAssignment.objects.create(
            record_type=WorktimeAssignment.RecordType.SICK_LEAVE,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK,
        )
        PersonalWorktimeWeekAssignment.objects.create(assignment=sick_leave_assignment, week_start=date(2026, 4, 6))
        WorktimeEntry.objects.create(assignment=sick_leave_assignment, work_date=date(2026, 4, 8), hours=Decimal("8"))

        response = self.client.post(
            reverse("worktime_save"),
            {
                "scope": "personal",
                "week": "2026-04-10",
                "assignment_ids": [str(sick_leave_assignment.pk)],
                f"hours_{sick_leave_assignment.pk}_20260408": "6",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            WorktimeEntry.objects.filter(
                assignment=sick_leave_assignment,
                work_date=date(2026, 4, 8),
            ).exists()
        )

    def test_personal_partial_renders_downtime_row_locked_and_last(self):
        assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        PersonalWorktimeWeekAssignment.objects.create(assignment=assignment, week_start=date(2026, 4, 6))

        response = self.client.get(reverse("personal_worktime_partial"), {"week": "2026-04-10"})

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertLess(content.index("Проект Альфа"), content.index("Простой"))
        self.assertContains(response, 'data-worktime-calculated-downtime-row="1"', html=False)
        self.assertContains(response, "data-worktime-calculated-downtime-input", html=False)
        self.assertContains(response, 'class="bi bi-lock worktime-calculated-downtime-lock-icon"', html=False)
        self.assertContains(response, 'class="p-1 worktime-flex-cell worktime-non-working-day-cell"', html=False)
        self.assertContains(response, 'class="text-center worktime-flex-total-cell worktime-non-working-day-total-cell"', html=False)
        self.assertContains(response, 'class="worktime-daily-histogram-cell worktime-non-working-day-chart-cell"', html=False)
        self.assertContains(
            response,
            'class="worktime-daily-histogram-column worktime-daily-histogram-column-empty worktime-non-working-day-histogram-column worktime-non-working-day-histogram-column-hidden"',
            html=False,
        )
        self.assertContains(response, "disabled", html=False)

    def test_personal_partial_hist_sort_desc_orders_rows(self):
        low_assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        high_assignment = WorktimeAssignment.objects.create(
            proposal_registration=self.proposal,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        PersonalWorktimeWeekAssignment.objects.create(assignment=low_assignment, week_start=date(2026, 4, 6))
        PersonalWorktimeWeekAssignment.objects.create(assignment=high_assignment, week_start=date(2026, 4, 6))
        WorktimeEntry.objects.create(assignment=low_assignment, work_date=date(2026, 4, 7), hours=Decimal("2"))
        WorktimeEntry.objects.create(assignment=high_assignment, work_date=date(2026, 4, 7), hours=Decimal("6"))

        response = self.client.get(reverse("personal_worktime_partial"), {"week": "2026-04-10", "hist_sort": "desc"})

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertLess(content.index("ТКП Альфа"), content.index("Проект Альфа"))

    def test_personal_partial_formats_input_hours_compactly(self):
        assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        PersonalWorktimeWeekAssignment.objects.create(assignment=assignment, week_start=date(2026, 4, 6))
        WorktimeEntry.objects.create(assignment=assignment, work_date=date(2026, 4, 7), hours=Decimal("7.50"))
        WorktimeEntry.objects.create(assignment=assignment, work_date=date(2026, 4, 8), hours=Decimal("5.00"))

        response = self.client.get(reverse("personal_worktime_partial"), {"week": "2026-04-10"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="7.5"', html=False)
        self.assertContains(response, 'value="5"', html=False)

    def test_personal_partial_summary_hides_vacation_hours_when_other_activity_exists(self):
        project_assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        vacation_assignment = WorktimeAssignment.objects.create(
            record_type=WorktimeAssignment.RecordType.VACATION,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK,
        )
        PersonalWorktimeWeekAssignment.objects.create(assignment=project_assignment, week_start=date(2026, 4, 6))
        PersonalWorktimeWeekAssignment.objects.create(assignment=vacation_assignment, week_start=date(2026, 4, 6))
        WorktimeEntry.objects.create(assignment=vacation_assignment, work_date=date(2026, 4, 7), hours=Decimal("8"))
        WorktimeEntry.objects.create(assignment=vacation_assignment, work_date=date(2026, 4, 8), hours=Decimal("8"))
        WorktimeEntry.objects.create(assignment=project_assignment, work_date=date(2026, 4, 8), hours=Decimal("3"))

        response = self.client.get(reverse("personal_worktime_partial"), {"week": "2026-04-10"})

        self.assertEqual(response.status_code, 200)
        summary_column_cells = response.context["summary_column_cells"]
        downtime_row = response.context["rows"][-1]
        self.assertEqual(summary_column_cells[1]["display_total"], Decimal("8"))
        self.assertTrue(summary_column_cells[1]["vacation_only"])
        self.assertEqual(summary_column_cells[2]["display_total"], Decimal("3"))
        self.assertFalse(summary_column_cells[2]["vacation_only"])
        self.assertTrue(summary_column_cells[2]["has_vacation"])
        self.assertTrue(downtime_row["cells"][1]["hide_downtime_zero"])

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

    def test_autosave_large_numeric_value_returns_validation_error(self):
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
                f"hours_{assignment.pk}_20260401": "9" * 80,
                "autosave": "1",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {"ok": False, "error": "Значение за 01.04.2026 должно быть числом."},
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
        self.assertContains(response, "Отпуск")
        self.assertNotContains(response, '<option value="downtime">Простой</option>', html=False)

    def test_personal_row_delete_rejects_calculated_downtime_row(self):
        context = _worktime_context(self.user, personal_only=True, month_start=date(2026, 4, 6))
        downtime_assignment = context["rows"][-1]["assignment"]

        response = self.client.post(
            reverse("personal_worktime_row_delete", args=[downtime_assignment.pk]),
            {"week": "2026-04-06"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertTrue(
            PersonalWorktimeWeekAssignment.objects.filter(
                assignment=downtime_assignment,
                week_start=date(2026, 4, 6),
                is_hidden=False,
            ).exists()
        )

    def test_personal_worktime_row_form_lists_vacation_after_time_off(self):
        response = self.client.get(
            reverse("personal_worktime_row_form"),
            {"week": "2026-04-07"},
        )

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertLess(content.index("Отгул"), content.index("Отпуск"))

    def test_personal_worktime_row_form_lists_latest_tkp_first(self):
        response = self.client.get(
            reverse("personal_worktime_row_form"),
            {"week": "2026-04-07"},
        )

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertLess(content.index("ТКП Бета"), content.index("ТКП Альфа"))

    def test_personal_worktime_row_form_allows_restoring_hidden_project_assignment(self):
        assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        PersonalWorktimeWeekAssignment.objects.create(
            assignment=assignment,
            week_start=date(2026, 4, 6),
            is_hidden=True,
        )

        response = self.client.get(
            reverse("personal_worktime_row_form"),
            {"week": "2026-04-07"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.registration.short_uid)
        restore_response = self.client.post(
            reverse("personal_worktime_row_form"),
            {
                "week": "2026-04-07",
                "record_type": WorktimeAssignment.RecordType.PROJECT,
                "registration": str(self.registration.pk),
            },
        )
        self.assertEqual(restore_response.status_code, 204)
        hidden_link = PersonalWorktimeWeekAssignment.objects.get(
            assignment=assignment,
            week_start=date(2026, 4, 6),
        )
        self.assertFalse(hidden_link.is_hidden)

    def test_personal_worktime_row_form_restores_hidden_manual_assignment_without_old_hours(self):
        assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK,
        )
        PersonalWorktimeWeekAssignment.objects.create(
            assignment=assignment,
            week_start=date(2026, 4, 6),
            is_hidden=True,
        )
        WorktimeEntry.objects.create(assignment=assignment, work_date=date(2026, 4, 7), hours=Decimal("8"))

        response = self.client.post(
            reverse("personal_worktime_row_form"),
            {
                "week": "2026-04-07",
                "record_type": WorktimeAssignment.RecordType.PROJECT,
                "registration": str(self.registration.pk),
            },
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(
            WorktimeEntry.objects.filter(
                assignment=assignment,
                work_date=date(2026, 4, 7),
            ).exists()
        )
        personal_response = self.client.get(reverse("personal_worktime_partial"), {"week": "2026-04-07"})
        restored_row = next(
            row for row in personal_response.context["rows"]
            if row["assignment"].pk == assignment.pk
        )
        self.assertTrue(all(cell["value"] is None for cell in restored_row["cells"]))

    def test_personal_worktime_row_form_adds_orphaned_manual_assignment_without_old_hours(self):
        assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.MANUAL_PERSONAL_WEEK,
        )
        WorktimeEntry.objects.create(assignment=assignment, work_date=date(2026, 4, 7), hours=Decimal("8"))

        response = self.client.post(
            reverse("personal_worktime_row_form"),
            {
                "week": "2026-04-07",
                "record_type": WorktimeAssignment.RecordType.PROJECT,
                "registration": str(self.registration.pk),
            },
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(
            WorktimeEntry.objects.filter(
                assignment=assignment,
                work_date=date(2026, 4, 7),
            ).exists()
        )
        self.assertTrue(
            PersonalWorktimeWeekAssignment.objects.filter(
                assignment=assignment,
                week_start=date(2026, 4, 6),
                is_hidden=False,
            ).exists()
        )

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

    def test_personal_partial_renders_selection_controls(self):
        assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )

        response = self.client.get(reverse("personal_worktime_partial"), {"week": "2026-04-07"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="worktime-personal-master"', html=False)
        self.assertContains(response, 'data-worktime-target-name="worktime-personal-select"', html=False)
        self.assertContains(response, 'id="worktime-personal-actions"', html=False)
        self.assertContains(response, 'data-worktime-panel-action="up"', html=False)
        self.assertContains(response, 'data-worktime-panel-action="down"', html=False)
        self.assertContains(response, 'data-worktime-panel-action="delete"', html=False)
        self.assertContains(response, f'name="worktime-personal-select"', html=False)
        self.assertContains(
            response,
            f'data-row-order-save-url="{reverse("personal_worktime_row_order")}?week=2026-04-06"',
            html=False,
        )
        self.assertContains(response, f'data-row-order-id="{assignment.pk}"', html=False)
        self.assertContains(
            response,
            f'data-worktime-delete-url="{reverse("personal_worktime_row_delete", args=[assignment.pk])}?week=2026-04-06"',
            html=False,
        )

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
        self.assertContains(
            response,
            '<span class="worktime-merged-cell-content">Администрирование</span>',
            html=False,
        )
        self.assertContains(response, 'colspan="3" class="text-nowrap worktime-sticky-col-span3 worktime-col-merged"', html=False)

    def test_personal_row_delete_hides_row_for_selected_week_and_clears_week_entries(self):
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

        response = self.client.post(
            reverse("personal_worktime_row_delete", args=[assignment.pk]),
            {"week": "2026-04-07"},
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(
            WorktimeEntry.objects.filter(
                assignment=assignment,
                work_date=date(2026, 4, 7),
            ).exists()
        )
        week_link = PersonalWorktimeWeekAssignment.objects.get(
            assignment=assignment,
            week_start=date(2026, 4, 6),
        )
        self.assertTrue(week_link.is_hidden)
        hidden_response = self.client.get(reverse("personal_worktime_partial"), {"week": "2026-04-07"})
        other_week_response = self.client.get(reverse("personal_worktime_partial"), {"week": "2026-04-14"})
        self.assertNotContains(hidden_response, self.registration.name)
        self.assertContains(other_week_response, self.registration.name)

    def test_personal_row_delete_clears_manual_week_assignment_entries(self):
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

        response = self.client.post(
            reverse("personal_worktime_row_delete", args=[assignment.pk]),
            {"week": "2026-04-07"},
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(
            WorktimeEntry.objects.filter(
                assignment=assignment,
                work_date=date(2026, 4, 7),
            ).exists()
        )

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

    def test_personal_row_move_down_persists_custom_order(self):
        first_assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        second_assignment = WorktimeAssignment.objects.create(
            registration=self.second_registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )

        response = self.client.post(
            reverse("personal_worktime_row_move_down", args=[first_assignment.pk]),
            {"week": "2026-04-07"},
        )

        self.assertEqual(response.status_code, 204)
        visible_response = self.client.get(reverse("personal_worktime_partial"), {"week": "2026-04-07"})
        content = visible_response.content.decode("utf-8")
        self.assertLess(content.index("Проект Бета"), content.index("Проект Альфа"))
        self.assertEqual(
            list(
                PersonalWorktimeWeekAssignment.objects.filter(
                    assignment_id__in=[first_assignment.pk, second_assignment.pk],
                    week_start=date(2026, 4, 6),
                    is_hidden=False,
                ).order_by("position", "id").values_list("assignment_id", flat=True)
            ),
            [second_assignment.pk, first_assignment.pk],
        )

    def test_personal_row_order_endpoint_persists_full_order(self):
        first_assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        second_assignment = WorktimeAssignment.objects.create(
            registration=self.second_registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        week_start = date(2026, 4, 6)
        current_order = _personal_week_order_ids(self.user, week_start)

        response = self.client.post(
            reverse("personal_worktime_row_order"),
            data=json.dumps({
                "week": "2026-04-07",
                "ordered_assignment_ids": [second_assignment.pk, first_assignment.pk],
                "base_order_signature": _personal_week_order_signature(current_order),
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["order_signature"],
            _personal_week_order_signature([second_assignment.pk, first_assignment.pk]),
        )
        self.assertEqual(
            list(
                PersonalWorktimeWeekAssignment.objects.filter(
                    assignment_id__in=[first_assignment.pk, second_assignment.pk],
                    week_start=week_start,
                    is_hidden=False,
                ).order_by("position", "id").values_list("assignment_id", flat=True)
            ),
            [second_assignment.pk, first_assignment.pk],
        )

    def test_personal_row_order_endpoint_returns_conflict_for_stale_signature(self):
        first_assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        second_assignment = WorktimeAssignment.objects.create(
            registration=self.second_registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        week_start = date(2026, 4, 6)
        original_order = _personal_week_order_ids(self.user, week_start)
        original_signature = _personal_week_order_signature(original_order)
        self.client.post(
            reverse("personal_worktime_row_move_down", args=[first_assignment.pk]),
            {"week": "2026-04-07"},
        )

        response = self.client.post(
            reverse("personal_worktime_row_order"),
            data=json.dumps({
                "week": "2026-04-07",
                "ordered_assignment_ids": [first_assignment.pk, second_assignment.pk],
                "base_order_signature": original_signature,
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["current_assignment_ids"], [second_assignment.pk, first_assignment.pk])

    def test_personal_row_order_endpoint_rejects_changed_visible_set(self):
        first_assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        second_assignment = WorktimeAssignment.objects.create(
            registration=self.second_registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        week_start = date(2026, 4, 6)
        current_order = _personal_week_order_ids(self.user, week_start)

        response = self.client.post(
            reverse("personal_worktime_row_order"),
            data=json.dumps({
                "week": "2026-04-07",
                "ordered_assignment_ids": [first_assignment.pk],
                "base_order_signature": _personal_week_order_signature(current_order),
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(set(response.json()["current_assignment_ids"]), {first_assignment.pk, second_assignment.pk})

    def test_personal_row_order_endpoint_rejects_other_user_assignment(self):
        own_assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        other_assignment = WorktimeAssignment.objects.create(
            registration=self.second_registration,
            employee=self.other_employee,
            executor_name=self._full_name(self.other_employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        week_start = date(2026, 4, 6)
        current_order = _personal_week_order_ids(self.user, week_start)

        response = self.client.post(
            reverse("personal_worktime_row_order"),
            data=json.dumps({
                "week": "2026-04-07",
                "ordered_assignment_ids": [other_assignment.pk, own_assignment.pk],
                "base_order_signature": _personal_week_order_signature(current_order),
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertFalse(
            PersonalWorktimeWeekAssignment.objects.filter(
                assignment=other_assignment,
                week_start=week_start,
            ).exists()
        )

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
        self.assertContains(response, '<span class="worktime-merged-cell-content">Отгул</span>', html=False)
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
        self.assertContains(
            response,
            "worktime-calendar-table mb-0 worktime-calendar-table-general worktime-calendar-table-year",
            html=False,
        )
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

    def test_worktime_csv_upload_creates_missing_assignment_for_existing_tkp_and_employee(self):
        april_days = [""] * 30
        april_days[0] = "6"
        upload = self._make_worktime_csv_upload(
            self._worktime_csv_header("2026-04"),
            [[
                self._full_name(self.employee),
                self.proposal.short_uid,
                "",
                "",
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
            proposal_registration=self.proposal,
            executor_name=self._full_name(self.employee),
        )
        self.assertEqual(assignment.employee, self.employee)
        self.assertEqual(assignment.record_type, WorktimeAssignment.RecordType.TKP)
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
            [(date(2026, 4, 1), 6)],
        )

    def test_worktime_csv_upload_creates_missing_manual_assignment_for_named_record_type(self):
        april_days = [""] * 30
        april_days[0] = "4"
        upload = self._make_worktime_csv_upload(
            self._worktime_csv_header("2026-04"),
            [[
                self._full_name(self.employee),
                WorktimeAssignment.RecordType.ADMINISTRATION.label,
                "",
                "",
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
            registration__isnull=True,
            proposal_registration__isnull=True,
            executor_name=self._full_name(self.employee),
            record_type=WorktimeAssignment.RecordType.ADMINISTRATION,
        )
        self.assertEqual(assignment.employee, self.employee)
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
            [(date(2026, 4, 1), 4)],
        )

    def test_worktime_csv_upload_creates_missing_manual_assignment_for_vacation(self):
        april_days = [""] * 30
        april_days[1] = "8"
        upload = self._make_worktime_csv_upload(
            self._worktime_csv_header("2026-04"),
            [[
                self._full_name(self.employee),
                WorktimeAssignment.RecordType.VACATION.label,
                "",
                "",
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
            registration__isnull=True,
            proposal_registration__isnull=True,
            executor_name=self._full_name(self.employee),
            record_type=WorktimeAssignment.RecordType.VACATION,
        )
        self.assertEqual(assignment.employee, self.employee)
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
            [(date(2026, 4, 2), 8)],
        )

    def test_worktime_csv_upload_removes_vacation_hours_on_non_working_days(self):
        country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            alpha2="RU",
            alpha3="RUS",
        )
        company = GroupMember.objects.create(
            short_name="IMC Russia",
            country_name="Россия",
            country_code="643",
        )
        self.employee.employment = company.short_name
        self.employee.save(update_fields=["employment"])
        ProductionCalendarDay.objects.create(
            country=country,
            date=date(2026, 4, 2),
            is_working_day=False,
            is_holiday=True,
            working_hours=Decimal("0.0"),
        )

        april_days = [""] * 30
        april_days[1] = "8"
        april_days[2] = "8"
        upload = self._make_worktime_csv_upload(
            self._worktime_csv_header("2026-04"),
            [[
                self._full_name(self.employee),
                WorktimeAssignment.RecordType.VACATION.label,
                "",
                "",
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

        expected_downtime_entries = [
            (work_day, REGULAR_WORKDAY_HOURS)
            for day_number in range(1, 31)
            for work_day in [date(2026, 4, day_number)]
            if work_day.weekday() < 5 and work_day not in {date(2026, 4, 2), date(2026, 4, 3)}
        ]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "ok": True,
                "created": len(expected_downtime_entries) + 1,
                "updated": 0,
                "deleted": 0,
                "created_assignments": 2,
            },
        )
        vacation_assignment = WorktimeAssignment.objects.get(
            registration__isnull=True,
            proposal_registration__isnull=True,
            executor_name=self._full_name(self.employee),
            record_type=WorktimeAssignment.RecordType.VACATION,
        )
        self.assertEqual(
            list(
                WorktimeEntry.objects.filter(assignment=vacation_assignment)
                .order_by("work_date")
                .values_list("work_date", "hours")
            ),
            [(date(2026, 4, 3), Decimal("8.00"))],
        )
        downtime_assignment = WorktimeAssignment.objects.get(
            registration__isnull=True,
            proposal_registration__isnull=True,
            executor_name=self._full_name(self.employee),
            record_type=WorktimeAssignment.RecordType.DOWNTIME,
        )
        self.assertEqual(
            list(
                WorktimeEntry.objects.filter(assignment=downtime_assignment)
                .order_by("work_date")
                .values_list("work_date", "hours")
            ),
            expected_downtime_entries,
        )

    def test_worktime_csv_upload_removes_absence_hours_on_non_working_days(self):
        country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            alpha2="RU",
            alpha3="RUS",
        )
        company = GroupMember.objects.create(
            short_name="IMC Russia",
            country_name="Россия",
            country_code="643",
        )
        self.employee.employment = company.short_name
        self.employee.save(update_fields=["employment"])
        ProductionCalendarDay.objects.create(
            country=country,
            date=date(2026, 4, 2),
            is_working_day=False,
            is_holiday=True,
            working_hours=Decimal("0.0"),
        )

        april_days = [""] * 30
        april_days[1] = "8"
        april_days[2] = "8"
        upload = self._make_worktime_csv_upload(
            self._worktime_csv_header("2026-04"),
            [[
                self._full_name(self.employee),
                WorktimeAssignment.RecordType.OTHER_ABSENCE.label,
                "",
                "",
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

        expected_downtime_entries = [
            (work_day, REGULAR_WORKDAY_HOURS)
            for day_number in range(1, 31)
            for work_day in [date(2026, 4, day_number)]
            if work_day.weekday() < 5 and work_day not in {date(2026, 4, 2), date(2026, 4, 3)}
        ]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "ok": True,
                "created": len(expected_downtime_entries) + 1,
                "updated": 0,
                "deleted": 0,
                "created_assignments": 2,
            },
        )
        absence_assignment = WorktimeAssignment.objects.get(
            registration__isnull=True,
            proposal_registration__isnull=True,
            executor_name=self._full_name(self.employee),
            record_type=WorktimeAssignment.RecordType.OTHER_ABSENCE,
        )
        self.assertEqual(
            list(
                WorktimeEntry.objects.filter(assignment=absence_assignment)
                .order_by("work_date")
                .values_list("work_date", "hours")
            ),
            [(date(2026, 4, 3), Decimal("8.00"))],
        )
        downtime_assignment = WorktimeAssignment.objects.get(
            registration__isnull=True,
            proposal_registration__isnull=True,
            executor_name=self._full_name(self.employee),
            record_type=WorktimeAssignment.RecordType.DOWNTIME,
        )
        self.assertEqual(
            list(
                WorktimeEntry.objects.filter(assignment=downtime_assignment)
                .order_by("work_date")
                .values_list("work_date", "hours")
            ),
            expected_downtime_entries,
        )

    def test_worktime_csv_upload_adds_calculated_downtime_for_missing_hours(self):
        country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            alpha2="RU",
            alpha3="RUS",
        )
        company = GroupMember.objects.create(
            short_name="IMC Russia",
            country_name="Россия",
            country_code="643",
        )
        self.employee.employment = company.short_name
        self.employee.save(update_fields=["employment"])
        ProductionCalendarDay.objects.create(country=country, date=date(2026, 4, 6), is_working_day=True, working_hours=Decimal("8.0"))
        ProductionCalendarDay.objects.create(country=country, date=date(2026, 4, 7), is_working_day=True, is_shortened_day=True)
        assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )

        april_days = [""] * 30
        april_days[5] = "5"
        april_days[6] = "2"
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

        expected_downtime_entries = []
        for day_number in range(1, 31):
            work_day = date(2026, 4, day_number)
            if work_day.weekday() >= 5:
                continue
            if work_day == date(2026, 4, 6):
                expected_hours = Decimal("3.00")
            elif work_day == date(2026, 4, 7):
                expected_hours = SHORTENED_WORKDAY_HOURS - Decimal("2.00")
            else:
                expected_hours = REGULAR_WORKDAY_HOURS
            expected_downtime_entries.append((work_day, expected_hours))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "ok": True,
                "created": len(expected_downtime_entries) + 2,
                "updated": 0,
                "deleted": 0,
                "created_assignments": 1,
            },
        )
        downtime_assignment = WorktimeAssignment.objects.get(
            registration__isnull=True,
            proposal_registration__isnull=True,
            executor_name=self._full_name(self.employee),
            record_type=WorktimeAssignment.RecordType.DOWNTIME,
        )
        self.assertTrue(
            PersonalWorktimeWeekAssignment.objects.filter(
                assignment=downtime_assignment,
                week_start=date(2026, 4, 6),
            ).exists()
        )
        self.assertEqual(
            list(
                WorktimeEntry.objects.filter(assignment=downtime_assignment)
                .order_by("work_date")
                .values_list("work_date", "hours")
            ),
            expected_downtime_entries,
        )

    def test_worktime_csv_upload_adds_calculated_downtime_for_blank_working_days(self):
        country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            alpha2="RU",
            alpha3="RUS",
        )
        company = GroupMember.objects.create(
            short_name="IMC Russia",
            country_name="Россия",
            country_code="643",
        )
        self.employee.employment = company.short_name
        self.employee.save(update_fields=["employment"])
        assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )

        april_days = [""] * 30
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

        expected_downtime_entries = [
            (date(2026, 4, day_number), REGULAR_WORKDAY_HOURS)
            for day_number in range(1, 31)
            if date(2026, 4, day_number).weekday() < 5
        ]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "ok": True,
                "created": len(expected_downtime_entries),
                "updated": 0,
                "deleted": 0,
                "created_assignments": 1,
            },
        )
        downtime_assignment = WorktimeAssignment.objects.get(
            registration__isnull=True,
            proposal_registration__isnull=True,
            executor_name=self._full_name(self.employee),
            record_type=WorktimeAssignment.RecordType.DOWNTIME,
        )
        self.assertEqual(
            list(
                WorktimeEntry.objects.filter(assignment=downtime_assignment)
                .order_by("work_date")
                .values_list("work_date", "hours")
            ),
            expected_downtime_entries,
        )

    def test_worktime_csv_upload_reuses_calculated_downtime_assignment(self):
        _worktime_context(self.user, personal_only=True, month_start=date(2026, 4, 6))
        downtime_assignment = WorktimeAssignment.objects.get(
            registration__isnull=True,
            proposal_registration__isnull=True,
            executor_name=self._full_name(self.employee),
            record_type=WorktimeAssignment.RecordType.DOWNTIME,
        )

        april_days = [""] * 30
        april_days[0] = "2"
        april_days[6] = "3"
        upload = self._make_worktime_csv_upload(
            self._worktime_csv_header("2026-04"),
            [[
                self._full_name(self.employee),
                WorktimeAssignment.RecordType.DOWNTIME.label,
                "",
                "",
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
                "created": 2,
                "updated": 0,
                "deleted": 0,
                "created_assignments": 1,
            },
        )
        self.assertEqual(
            WorktimeAssignment.objects.filter(
                registration__isnull=True,
                proposal_registration__isnull=True,
                executor_name=self._full_name(self.employee),
                record_type=WorktimeAssignment.RecordType.DOWNTIME,
            ).count(),
            1,
        )
        self.assertTrue(
            PersonalWorktimeWeekAssignment.objects.filter(
                assignment=downtime_assignment,
                week_start=date(2026, 3, 30),
            ).exists()
        )
        self.assertEqual(
            list(
                WorktimeEntry.objects.filter(assignment=downtime_assignment)
                .order_by("work_date")
                .values_list("work_date", "hours")
            ),
            [
                (date(2026, 4, 1), Decimal("2.00")),
                (date(2026, 4, 7), Decimal("3.00")),
            ],
        )
        download_response = self.client.get(
            reverse("worktime_csv_download"),
            {"scale": "month", "period": "2026-04", "breakdown": "employees"},
        )
        rows = self._parse_worktime_csv_response(download_response)
        downtime_rows = [
            row for row in rows[1:]
            if row[:4] == [
                self._full_name(self.employee),
                "",
                "",
                WorktimeAssignment.RecordType.DOWNTIME.label,
            ]
        ]
        self.assertEqual(len(downtime_rows), 1)
        self.assertEqual(downtime_rows[0][4], "2")
        self.assertEqual(downtime_rows[0][10], "3")

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

    def test_worktime_csv_upload_rejects_large_numeric_hours_as_validation_error(self):
        assignment = WorktimeAssignment.objects.create(
            registration=self.registration,
            employee=self.employee,
            executor_name=self._full_name(self.employee),
            source_type=WorktimeAssignment.SourceType.PERFORMER_CONFIRMATION,
        )
        april_days = [""] * 30
        april_days[0] = "9" * 80
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
        self.assertIn("значение за 01.04.2026 должно быть числом", payload["warnings"][0])

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
