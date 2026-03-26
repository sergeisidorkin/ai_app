from django.conf import settings
from django.db import models


class LearningUserLink(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="learning_link",
    )
    moodle_user_id = models.PositiveBigIntegerField(
        "ID пользователя в Moodle",
        unique=True,
        null=True,
        blank=True,
    )
    moodle_username = models.CharField("Логин в Moodle", max_length=255, blank=True, default="")
    moodle_email = models.EmailField("Email в Moodle", blank=True, default="")
    last_login_at = models.DateTimeField("Последний вход в Moodle", null=True, blank=True)
    last_synced_at = models.DateTimeField("Последняя синхронизация", null=True, blank=True)
    source_payload = models.JSONField("Сырые данные Moodle", default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Связка пользователя с Moodle"
        verbose_name_plural = "Связки пользователей с Moodle"

    def __str__(self):
        return self.user.get_username()


class LearningCourse(models.Model):
    moodle_course_id = models.PositiveBigIntegerField("ID курса в Moodle", unique=True)
    shortname = models.CharField("Короткое имя", max_length=255, blank=True, default="")
    fullname = models.CharField("Название курса", max_length=255)
    category_name = models.CharField("Категория", max_length=255, blank=True, default="")
    summary = models.TextField("Описание", blank=True, default="")
    moodle_url = models.URLField("Ссылка на курс", blank=True, default="")
    is_visible = models.BooleanField("Доступен пользователям", default=True)
    last_synced_at = models.DateTimeField("Последняя синхронизация", null=True, blank=True)
    source_payload = models.JSONField("Сырые данные Moodle", default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Курс обучения"
        verbose_name_plural = "Курсы обучения"
        ordering = ["fullname", "id"]

    def __str__(self):
        return self.fullname


class LearningEnrollment(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="learning_enrollments",
    )
    course = models.ForeignKey(
        LearningCourse,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    moodle_enrollment_id = models.PositiveBigIntegerField(
        "ID назначения в Moodle",
        null=True,
        blank=True,
    )
    role_name = models.CharField("Роль", max_length=100, blank=True, default="")
    enrolled_at = models.DateTimeField("Дата назначения", null=True, blank=True)
    last_synced_at = models.DateTimeField("Последняя синхронизация", null=True, blank=True)
    source_payload = models.JSONField("Сырые данные Moodle", default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Назначение курса"
        verbose_name_plural = "Назначения курсов"
        ordering = ["-enrolled_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "course"],
                name="learning_enrollment_user_course_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.user} -> {self.course}"


class LearningCourseResult(models.Model):
    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "Не начат"
        IN_PROGRESS = "in_progress", "В процессе"
        COMPLETED = "completed", "Завершен"
        FAILED = "failed", "Не пройден"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="learning_course_results",
    )
    course = models.ForeignKey(
        LearningCourse,
        on_delete=models.CASCADE,
        related_name="results",
    )
    status = models.CharField(
        "Статус прохождения",
        max_length=32,
        choices=Status.choices,
        default=Status.NOT_STARTED,
    )
    progress_percent = models.PositiveSmallIntegerField("Прогресс, %", default=0)
    grade_value = models.DecimalField(
        "Итоговый балл",
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
    )
    grade_display = models.CharField("Отображаемый балл", max_length=100, blank=True, default="")
    completed_at = models.DateTimeField("Дата завершения", null=True, blank=True)
    certificate_url = models.URLField("Ссылка на сертификат", blank=True, default="")
    last_synced_at = models.DateTimeField("Последняя синхронизация", null=True, blank=True)
    source_payload = models.JSONField("Сырые данные Moodle", default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Результат по курсу"
        verbose_name_plural = "Результаты по курсам"
        ordering = ["-completed_at", "-updated_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "course"],
                name="learning_result_user_course_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.user} / {self.course} / {self.status}"


class LearningSyncRun(models.Model):
    class Scope(models.TextChoices):
        CATALOG = "catalog", "Каталог"
        USERS = "users", "Пользователи"
        RESULTS = "results", "Результаты"
        FULL = "full", "Полная синхронизация"

    class Status(models.TextChoices):
        STARTED = "started", "Запущена"
        SUCCESS = "success", "Успешно"
        FAILED = "failed", "Ошибка"

    scope = models.CharField("Область синхронизации", max_length=20, choices=Scope.choices)
    status = models.CharField("Статус", max_length=20, choices=Status.choices, default=Status.STARTED)
    started_at = models.DateTimeField("Начало", auto_now_add=True)
    finished_at = models.DateTimeField("Окончание", null=True, blank=True)
    stats = models.JSONField("Статистика", default=dict, blank=True)
    error_message = models.TextField("Текст ошибки", blank=True, default="")
    source_payload = models.JSONField("Служебные данные", default=dict, blank=True)

    class Meta:
        verbose_name = "Запуск синхронизации обучения"
        verbose_name_plural = "Запуски синхронизации обучения"
        ordering = ["-started_at", "-id"]

    def __str__(self):
        return f"{self.scope} / {self.status}"
