from django.db import models

from group_app.models import OrgUnit
from users_app.models import Employee


class ExpertSpecialty(models.Model):
    expertise_direction = models.ForeignKey(
        OrgUnit,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expert_specialties",
        verbose_name="Направление экспертизы",
    )
    specialty = models.CharField(
        "Специальность", max_length=512, blank=True, default=""
    )
    specialty_en = models.CharField(
        "Специальность на англ. языке", max_length=512, blank=True, default=""
    )
    head_of_direction = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="headed_specialties",
        verbose_name="Руководитель направления",
    )
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Специальность эксперта"
        verbose_name_plural = "Специальности экспертов"

    def __str__(self):
        return self.specialty or f"Специальность #{self.pk}"


EXCLUDED_ROLES = ("Директор", "Администратор", "Руководитель проектов")


class ExpertProfile(models.Model):
    employee = models.OneToOneField(
        Employee,
        on_delete=models.CASCADE,
        related_name="expert_profile",
        verbose_name="Сотрудник",
    )
    extra_email = models.CharField(
        "Дополнительная эл. почта", max_length=255, blank=True, default=""
    )
    extra_phone = models.CharField(
        "Дополнительный телефон", max_length=50, blank=True, default=""
    )
    expertise_direction = models.ForeignKey(
        OrgUnit,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expert_profiles",
        verbose_name="Направление экспертизы",
    )
    specialties = models.ManyToManyField(
        ExpertSpecialty,
        through="ExpertProfileSpecialty",
        blank=True,
        related_name="expert_profiles",
        verbose_name="Специальности",
    )
    grade = models.ForeignKey(
        "policy_app.Grade",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expert_profiles",
        verbose_name="Грейд",
    )
    country = models.ForeignKey(
        "classifiers_app.OKSMCountry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expert_profiles",
        verbose_name="Страна",
    )
    region = models.ForeignKey(
        "classifiers_app.TerritorialDivision",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expert_profiles",
        verbose_name="Регион",
    )
    status = models.CharField(
        "Статус", max_length=255, blank=True, default=""
    )
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Профиль эксперта"
        verbose_name_plural = "База экспертов"

    def __str__(self):
        return str(self.employee)

    @property
    def full_name(self):
        u = self.employee.user
        parts = [u.last_name, u.first_name, self.employee.patronymic]
        return " ".join(p for p in parts if p)


class ExpertProfileSpecialty(models.Model):
    profile = models.ForeignKey(
        ExpertProfile,
        on_delete=models.CASCADE,
        related_name="ranked_specialties",
    )
    specialty = models.ForeignKey(
        ExpertSpecialty,
        on_delete=models.CASCADE,
        related_name="profile_links",
    )
    rank = models.PositiveIntegerField("Ранг", default=1)

    class Meta:
        ordering = ["rank"]
        unique_together = [("profile", "specialty")]
        verbose_name = "Специальность профиля"
        verbose_name_plural = "Специальности профиля"

    def __str__(self):
        return f"{self.profile} — {self.specialty} (#{self.rank})"
