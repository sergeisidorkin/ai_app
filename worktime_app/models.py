from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class WorktimeAssignment(models.Model):
    class SourceType(models.TextChoices):
        PERFORMER_CONFIRMATION = "performer_confirmation", "Подтверждение исполнителя"
        PROJECT_MANAGER = "project_manager", "Руководитель проекта"
        DIRECTION_HEAD_REQUEST = "direction_head_request", "Запрос руководителю направления"
        MANUAL_PERSONAL_WEEK = "manual_personal_week", "Личный табель по неделе"

    class RecordType(models.TextChoices):
        TKP = "tkp", "ТКП"
        PROJECT = "project", "Проект"
        SICK_LEAVE = "sick_leave", "Больничный"
        OTHER_ABSENCE = "other_absence", "Прочее отсутствие"
        ADMINISTRATION = "administration", "Администрирование"
        BUSINESS_DEVELOPMENT = "business_development", "Бизнес-девелопмент"
        STRATEGIC_DEVELOPMENT = "strategic_development", "Стратегическое развитие"
        DOWNTIME = "downtime", "Простой"
        TIME_OFF = "time_off", "Отгул"

    registration = models.ForeignKey(
        "projects_app.ProjectRegistration",
        on_delete=models.CASCADE,
        related_name="worktime_assignments",
        verbose_name="Проект",
        null=True,
        blank=True,
    )
    proposal_registration = models.ForeignKey(
        "proposals_app.ProposalRegistration",
        on_delete=models.CASCADE,
        related_name="worktime_assignments",
        verbose_name="ТКП",
        null=True,
        blank=True,
    )
    performer = models.ForeignKey(
        "projects_app.Performer",
        on_delete=models.SET_NULL,
        related_name="worktime_assignments",
        verbose_name="Строка исполнителя",
        null=True,
        blank=True,
    )
    employee = models.ForeignKey(
        "users_app.Employee",
        on_delete=models.SET_NULL,
        related_name="worktime_assignments",
        verbose_name="Сотрудник",
        null=True,
        blank=True,
    )
    executor_name = models.CharField("Исполнитель", max_length=255, db_index=True)
    source_type = models.CharField(
        "Источник создания",
        max_length=40,
        choices=SourceType.choices,
        default=SourceType.PERFORMER_CONFIRMATION,
    )
    record_type = models.CharField(
        "Вид записи",
        max_length=40,
        choices=RecordType.choices,
        default=RecordType.PROJECT,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["executor_name", "registration__position", "registration__id", "id"]
        verbose_name = "Строка табеля"
        verbose_name_plural = "Строки табеля"
        constraints = [
            models.UniqueConstraint(
                fields=("registration", "executor_name"),
                name="worktime_assignment_project_executor_unique",
            ),
            models.UniqueConstraint(
                fields=("executor_name", "record_type"),
                condition=models.Q(registration__isnull=True, proposal_registration__isnull=True),
                name="worktime_assignment_manual_record_type_unique",
            ),
            models.UniqueConstraint(
                fields=("proposal_registration", "executor_name"),
                name="worktime_assignment_tkp_executor_unique",
            ),
        ]

    def __str__(self):
        project_label = self.display_project_label
        return f"{self.executor_name} — {project_label}"

    @property
    def display_executor_name(self):
        if self.employee_id:
            from projects_app.models import Performer

            return Performer.employee_full_name(self.employee)
        return self.executor_name

    @property
    def display_type_label(self):
        if self.registration_id is not None:
            if getattr(self.registration, "type", None):
                return getattr(self.registration.type, "short_name", "") or str(self.registration.type)
            return "—"
        if self.proposal_registration_id is not None:
            if getattr(self.proposal_registration, "type", None):
                return getattr(self.proposal_registration.type, "short_name", "") or str(self.proposal_registration.type)
            return "—"
        if self.registration_id is None:
            return "—"
        return "—"

    @property
    def display_manual_label(self):
        return self.get_record_type_display()

    @property
    def display_project_code(self):
        if self.registration_id is None:
            if self.proposal_registration_id is not None:
                return getattr(self.proposal_registration, "short_uid", "") or "—"
            return self.display_manual_label
        return getattr(self.registration, "short_uid", "") or "—"

    @property
    def display_project_name(self):
        if self.registration_id is None:
            if self.proposal_registration_id is not None:
                return getattr(self.proposal_registration, "name", "") or "—"
            return self.display_manual_label
        return getattr(self.registration, "name", "") or "—"

    @property
    def display_project_label(self):
        if self.registration_id is None and self.proposal_registration_id is not None:
            return getattr(self.proposal_registration, "short_uid", "") or getattr(self.proposal_registration, "name", "") or "—"
        return self.display_project_code if self.registration_id is None else (
            getattr(self.registration, "short_uid", "") or getattr(self.registration, "name", "") or "—"
        )

    @property
    def has_linked_registry_row(self):
        return self.registration_id is not None or self.proposal_registration_id is not None


class WorktimeEntry(models.Model):
    assignment = models.ForeignKey(
        WorktimeAssignment,
        on_delete=models.CASCADE,
        related_name="entries",
        verbose_name="Строка табеля",
    )
    work_date = models.DateField("Дата")
    hours = models.PositiveIntegerField(
        "Количество часов",
        validators=[MinValueValidator(0), MaxValueValidator(24)],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["work_date", "id"]
        verbose_name = "Запись табеля"
        verbose_name_plural = "Записи табеля"
        constraints = [
            models.UniqueConstraint(
                fields=("assignment", "work_date"),
                name="worktime_entry_assignment_date_unique",
            ),
        ]

    def __str__(self):
        return f"{self.assignment} @ {self.work_date:%d.%m.%Y}"


class PersonalWorktimeWeekAssignment(models.Model):
    assignment = models.ForeignKey(
        WorktimeAssignment,
        on_delete=models.CASCADE,
        related_name="personal_week_links",
        verbose_name="Строка табеля",
    )
    week_start = models.DateField("Начало недели")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["week_start", "assignment__executor_name", "assignment__registration__id", "id"]
        verbose_name = "Недельная строка личного табеля"
        verbose_name_plural = "Недельные строки личного табеля"
        constraints = [
            models.UniqueConstraint(
                fields=("assignment", "week_start"),
                name="worktime_personal_week_assignment_unique",
            ),
        ]

    def __str__(self):
        return f"{self.assignment} [{self.week_start:%d.%m.%Y}]"

