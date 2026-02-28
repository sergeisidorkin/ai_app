from django.conf import settings
from django.db import models


class Employee(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="employee_profile",
    )
    patronymic = models.CharField("Отчество", max_length=150, blank=True, default="")
    phone = models.CharField("Телефон", max_length=50, blank=True, default="")
    employment = models.CharField("Трудоустройство", max_length=255, blank=True, default="")
    job_title = models.CharField("Должность", max_length=255, blank=True, default="")
    role = models.CharField("Роль", max_length=255, blank=True, default="")
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Сотрудник"
        verbose_name_plural = "Сотрудники"

    def __str__(self):
        return f"{self.user.last_name} {self.user.first_name}".strip() or self.user.username
