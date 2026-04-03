from django.db import models

from group_app.models import GroupMember, OrgUnit
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
        "Специальность", max_length=512, blank=True, default="", unique=True
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
    expertise_dir = models.ForeignKey(
        "policy_app.ExpertiseDirection",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expert_specialties_linked",
        verbose_name="Направление экспертизы (политика)",
    )
    owners = models.ManyToManyField(
        GroupMember,
        blank=True,
        related_name="expert_specialties_owned",
        verbose_name="Владельцы",
    )
    is_group_owner = models.BooleanField("Группа (все компании)", default=False)
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Специальность эксперта"
        verbose_name_plural = "Специальности экспертов"

    def __str__(self):
        return self.specialty or f"Специальность #{self.pk}"

    @property
    def owner_display(self):
        if self.is_group_owner:
            return "Группа"
        names = list(self.owners.order_by("position").values_list("short_name", flat=True))
        return ", ".join(names) if names else ""


EXCLUDED_ROLES = ("Директор", "Администратор", "Руководитель проектов")


class ExpertProfile(models.Model):
    employee = models.OneToOneField(
        Employee,
        on_delete=models.CASCADE,
        related_name="expert_profile",
        verbose_name="Сотрудник",
    )
    yandex_mail = models.CharField(
        "Яндекс Почта", max_length=255, blank=True, default=""
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
    professional_status = models.CharField(
        "Профессиональный статус", max_length=255, blank=True, default=""
    )
    professional_status_short = models.CharField(
        "Профессиональный статус (кратко)", max_length=255, blank=True, default=""
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

    # --- Реквизиты для договора ---
    GENDER_CHOICES = [
        ("male", "Мужской"),
        ("female", "Женский"),
    ]
    full_name_genitive = models.CharField(
        "ФИО (полное) родительный падеж", max_length=512, blank=True, default=""
    )
    self_employed = models.DateField("Самозанятость (дата постановки на учет)", null=True, blank=True)
    tax_rate = models.PositiveIntegerField("Ставка налога, %", null=True, blank=True)
    citizenship = models.CharField("Гражданство", max_length=255, blank=True, default="")
    gender = models.CharField(
        "Пол", max_length=10, choices=GENDER_CHOICES, blank=True, default=""
    )
    inn = models.CharField("ИНН", max_length=50, blank=True, default="")
    snils = models.CharField("СНИЛС", max_length=14, blank=True, default="")
    birth_date = models.DateField("Дата рождения", null=True, blank=True)
    passport_series = models.CharField("Паспорт: серия", max_length=50, blank=True, default="")
    passport_number = models.CharField("Паспорт: номер", max_length=50, blank=True, default="")
    passport_issued_by = models.CharField("Паспорт: кем выдан", max_length=512, blank=True, default="")
    passport_issue_date = models.DateField("Паспорт: дата выдачи", null=True, blank=True)
    passport_expiry_date = models.DateField("Паспорт: срок действия", null=True, blank=True)
    passport_division_code = models.CharField("Паспорт: код подразделения", max_length=50, blank=True, default="")
    registration_address = models.CharField("Регистрация: адрес", max_length=512, blank=True, default="")
    bank_name = models.CharField("Наименование банка", max_length=255, blank=True, default="")
    bank_swift = models.CharField("SWIFT", max_length=50, blank=True, default="")
    bank_inn = models.CharField("ИНН банка", max_length=50, blank=True, default="")
    bank_bik = models.CharField("БИК", max_length=50, blank=True, default="")
    settlement_account = models.CharField("Рас. счет", max_length=50, blank=True, default="")
    corr_account = models.CharField("Кор. счет", max_length=50, blank=True, default="")
    bank_address = models.CharField("Адрес банка", max_length=512, blank=True, default="")
    corr_bank_name = models.CharField("Наименование банка-корреспондента", max_length=255, blank=True, default="")
    corr_bank_address = models.CharField("Адрес банка-корреспондента", max_length=512, blank=True, default="")
    corr_bank_bik = models.CharField("БИК банка-корреспондента", max_length=50, blank=True, default="")
    corr_bank_swift = models.CharField("SWIFT банка-корреспондента", max_length=50, blank=True, default="")
    corr_bank_settlement_account = models.CharField("Рас. счет банка-корреспондента", max_length=50, blank=True, default="")
    corr_bank_corr_account = models.CharField("Кор. счет банка-корреспондента", max_length=50, blank=True, default="")

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
