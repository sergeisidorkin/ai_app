import os
from datetime import date as date_type

from django.db import models

from classifiers_app.models import TerritorialDivision
from group_app.models import GroupMember, OrgUnit
from policy_app.models import (
    ADMIN_GROUP,
    DIRECTION_DIRECTOR_GROUP,
    DIRECTOR_GROUP,
    PROJECTS_HEAD_GROUP,
)
from users_app.models import Employee


def expert_facsimile_upload_to(instance, filename):
    return f"experts/facsimiles/{instance.pk or 'new'}/{os.path.basename(filename)}"


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


EXCLUDED_ROLES = (DIRECTOR_GROUP, DIRECTION_DIRECTOR_GROUP, ADMIN_GROUP, PROJECTS_HEAD_GROUP)


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

    def ordered_contract_details(self):
        records = list(
            self.contract_details_records.select_related(
                "citizenship_record",
                "citizenship_record__person",
            ).all()
        )
        records.sort(
            key=lambda item: (
                not getattr(item.citizenship_record, "is_active", False),
                getattr(item.citizenship_record, "position", 0),
                getattr(item.citizenship_record, "pk", 0),
                item.pk,
            )
        )
        return records

    def default_contract_details(self, *, require_facsimile=False):
        records = self.ordered_contract_details()
        if not records:
            return None
        if require_facsimile:
            with_facsimile = [
                item for item in records
                if getattr(getattr(item, "facsimile_file", None), "name", "")
            ]
            if with_facsimile:
                return with_facsimile[0]
        return records[0]

    def _ordered_email_records(self):
        employee = getattr(self, "employee", None)
        person = getattr(employee, "person_record", None) if employee else None
        if not person:
            return []
        return list(person.emails.filter(is_active=True).order_by("position", "id"))

    def _primary_residence_address(self):
        employee = getattr(self, "employee", None)
        person = getattr(employee, "person_record", None) if employee else None
        if not person:
            return None
        prefetched = getattr(person, "_prefetched_objects_cache", {}).get("residence_addresses")
        if prefetched is not None:
            active_items = [item for item in prefetched if item.is_active]
            active_items.sort(key=lambda item: (item.position, item.pk))
            return active_items[0] if active_items else None
        return person.residence_addresses.filter(is_active=True).order_by("position", "id").first()

    def resolved_extra_email(self):
        employee = getattr(self, "employee", None)
        if not employee:
            return ""
        person = getattr(employee, "person_record", None)
        if not person:
            return ""
        login_email = (getattr(employee.user, "email", "") or "").strip().lower()
        active_emails_qs = person.emails.filter(is_active=True).order_by("position", "id")
        anchor = None
        managed_email_id = getattr(employee, "managed_email_record_id", None)
        if managed_email_id:
            anchor = active_emails_qs.filter(pk=managed_email_id).first()
        if anchor is None and login_email:
            anchor = next(
                (
                    item
                    for item in active_emails_qs
                    if (item.email or "").strip().lower() == login_email
                ),
                None,
            )
        if anchor is not None:
            next_email = (
                active_emails_qs.filter(
                    models.Q(position__gt=anchor.position) |
                    (models.Q(position=anchor.position) & models.Q(pk__gt=anchor.pk))
                )
                .first()
            )
            if next_email:
                return next_email.email or ""
        fallback_email = next(
            (
                item
                for item in active_emails_qs
                if (item.email or "").strip().lower() != login_email
            ),
            None,
        )
        return (fallback_email.email or "") if fallback_email else ""

    def resolved_extra_phone(self):
        employee = getattr(self, "employee", None)
        if not employee:
            return ""
        return employee.secondary_phone_display or ""

    def resolved_country(self):
        address = self._primary_residence_address()
        return getattr(address, "country", None) if address else None

    def resolved_region(self):
        address = self._primary_residence_address()
        if not address or not address.country_id or not (address.region or "").strip():
            return None
        today = date_type.today()
        return (
            TerritorialDivision.objects.filter(
                country_id=address.country_id,
                region_name__iexact=(address.region or "").strip(),
                effective_date__lte=today,
            )
            .filter(
                models.Q(abolished_date__isnull=True) | models.Q(abolished_date__gte=today)
            )
            .order_by("position", "id")
            .first()
        )

    def save(self, *args, **kwargs):
        self.extra_email = self.resolved_extra_email()
        self.extra_phone = self.resolved_extra_phone()
        self.country = self.resolved_country()
        self.region = self.resolved_region()
        super().save(*args, **kwargs)


class ExpertContractDetails(models.Model):
    GENDER_CHOICES = [
        ("male", "мужской"),
        ("female", "женский"),
    ]
    CITIZENSHIP_PREFIXES = {
        "male": "гражданин",
        "female": "гражданка",
    }

    expert_profile = models.ForeignKey(
        ExpertProfile,
        on_delete=models.CASCADE,
        related_name="contract_details_records",
        verbose_name="Профиль эксперта",
    )
    citizenship_record = models.OneToOneField(
        "contacts_app.CitizenshipRecord",
        on_delete=models.CASCADE,
        related_name="expert_contract_details",
        verbose_name="ID-CTZ",
    )
    full_name_genitive = models.CharField(
        "ФИО (полное) родительный падеж", max_length=512, blank=True, default=""
    )
    self_employed = models.DateField(
        "Самозанятость (дата постановки на учет)",
        null=True,
        blank=True,
    )
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
    registration_postal_code = models.CharField("Регистрация: индекс", max_length=32, blank=True, default="")
    registration_region = models.CharField("Регистрация: регион", max_length=255, blank=True, default="")
    registration_locality = models.CharField("Регистрация: населенный пункт", max_length=255, blank=True, default="")
    registration_street = models.CharField("Регистрация: улица", max_length=255, blank=True, default="")
    registration_building = models.CharField("Регистрация: здание", max_length=255, blank=True, default="")
    registration_premise = models.CharField("Регистрация: помещение", max_length=255, blank=True, default="")
    registration_premise_part = models.CharField("Регистрация: часть помещения", max_length=255, blank=True, default="")
    registration_date = models.DateField("Регистрация: дата", null=True, blank=True)
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
    facsimile_file = models.FileField(
        "Факсимиле",
        upload_to=expert_facsimile_upload_to,
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [
            "expert_profile__position",
            "citizenship_record__position",
            "citizenship_record_id",
            "id",
        ]
        verbose_name = "Реквизиты физлица-исполнителя"
        verbose_name_plural = "Реквизиты физлиц-исполнителей"

    def __str__(self):
        return f"{self.full_name} / {self.formatted_ctz_id or 'без ID-CTZ'}".strip()

    @property
    def employee(self):
        return getattr(self.expert_profile, "employee", None)

    @property
    def full_name(self):
        return self.expert_profile.full_name if self.expert_profile_id else ""

    @property
    def citizenship_country(self):
        citizenship = getattr(self, "citizenship_record", None)
        country = getattr(citizenship, "country", None) if citizenship else None
        return (getattr(country, "short_name", "") or "").strip()

    @property
    def citizenship_country_genitive(self):
        citizenship = getattr(self, "citizenship_record", None)
        country = getattr(citizenship, "country", None) if citizenship else None
        if not country:
            return ""
        return (
            getattr(country, "short_name_genitive", "")
            or getattr(country, "short_name", "")
            or ""
        ).strip()

    @property
    def citizenship_status(self):
        citizenship = getattr(self, "citizenship_record", None)
        return (getattr(citizenship, "status", "") or "").strip()

    @property
    def citizenship_identifier(self):
        citizenship = getattr(self, "citizenship_record", None)
        return (getattr(citizenship, "identifier", "") or "").strip()

    @property
    def citizenship_number(self):
        citizenship = getattr(self, "citizenship_record", None)
        return (getattr(citizenship, "number", "") or "").strip()

    @property
    def person_birth_date(self):
        employee = getattr(self, "employee", None)
        person = getattr(employee, "person_record", None) if employee else None
        return getattr(person, "birth_date", None)

    @property
    def person_full_name_genitive(self):
        employee = getattr(self, "employee", None)
        person = getattr(employee, "person_record", None) if employee else None
        return getattr(person, "full_name_genitive", "") or ""

    @property
    def person_gender(self):
        employee = getattr(self, "employee", None)
        person = getattr(employee, "person_record", None) if employee else None
        return getattr(person, "gender", "") or ""

    @property
    def calculated_citizenship(self):
        if self.citizenship_status != "Гражданство":
            return ""
        prefix = self.CITIZENSHIP_PREFIXES.get(self.gender or "")
        country_name = self.citizenship_country_genitive
        if not prefix or not country_name:
            return ""
        return f"{prefix} {country_name}"

    @property
    def formatted_ctz_id(self):
        citizenship = getattr(self, "citizenship_record", None)
        return getattr(citizenship, "formatted_id", "")

    @property
    def calculated_registration_address(self):
        postal_code = (self.registration_postal_code or "").strip()
        address_parts = [
            (self.registration_locality or "").strip(),
            (self.registration_street or "").strip(),
            (self.registration_building or "").strip(),
            (self.registration_premise or "").strip(),
            (self.registration_premise_part or "").strip(),
        ]
        address_parts = [part for part in address_parts if part]
        if postal_code and address_parts:
            return f"{postal_code} {', '.join(address_parts)}"
        if postal_code:
            return postal_code
        return ", ".join(address_parts)

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        self.full_name_genitive = self.person_full_name_genitive
        self.gender = self.person_gender
        self.citizenship = self.calculated_citizenship
        self.birth_date = self.person_birth_date
        self.registration_address = self.calculated_registration_address
        if update_fields is not None:
            kwargs["update_fields"] = set(update_fields) | {
                "full_name_genitive",
                "gender",
                "citizenship",
                "birth_date",
                "registration_address",
            }
        super().save(*args, **kwargs)


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
