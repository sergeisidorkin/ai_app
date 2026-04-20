import sys

from django.db import models, transaction
from django.db.models import Q

from classifiers_app.models import LegalEntityRecord, OKSMCountry

sys.modules.setdefault("contacts_app.models", sys.modules[__name__])
sys.modules.setdefault("ai_app.contacts_app.models", sys.modules[__name__])


CONTACT_POSITION_SOURCE = "[ТКП / Отправка ТКП]"
USER_KIND_EMPLOYEE = "employee"
USER_KIND_EXTERNAL = "external"
USER_KIND_CHOICES = [
    (USER_KIND_EMPLOYEE, "Сотрудник"),
    (USER_KIND_EXTERNAL, "Внешний пользователь"),
]
PERSON_GENDER_MALE = "male"
PERSON_GENDER_FEMALE = "female"
PERSON_GENDER_CHOICES = [
    (PERSON_GENDER_MALE, "мужской"),
    (PERSON_GENDER_FEMALE, "женский"),
]


def _normalize_compare_value(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


class PersonRecord(models.Model):
    last_name = models.CharField("Фамилия", max_length=255, blank=True, default="")
    first_name = models.CharField("Имя", max_length=255, blank=True, default="")
    middle_name = models.CharField("Отчество", max_length=255, blank=True, default="")
    full_name_genitive = models.CharField("ФИО (полное) в родительном падеже", max_length=512, blank=True, default="")
    gender = models.CharField("Пол", max_length=10, blank=True, default="", choices=PERSON_GENDER_CHOICES)
    birth_date = models.DateField("Дата рождения", blank=True, null=True)
    citizenship = models.ForeignKey(
        OKSMCountry,
        verbose_name="Гражданство",
        on_delete=models.SET_NULL,
        related_name="contact_person_records",
        null=True,
        blank=True,
    )
    user_kind = models.CharField("Пользователь", max_length=16, blank=True, default="", choices=USER_KIND_CHOICES)
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "contacts_app"
        ordering = ["position", "id"]
        verbose_name = "Лицо"
        verbose_name_plural = "Реестр лиц"

    def __str__(self):
        return self.display_name or f"{self.pk:05d}-PRS"

    @property
    def formatted_id(self):
        if not self.pk:
            return ""
        return f"{self.pk:05d}-PRS"

    @property
    def display_name(self):
        parts = [self.last_name, self.first_name, self.middle_name]
        return " ".join(part for part in parts if part).strip()


class PositionRecord(models.Model):
    person = models.ForeignKey(
        PersonRecord,
        verbose_name="ID-PRS",
        on_delete=models.CASCADE,
        related_name="positions",
    )
    organization_short_name = models.CharField(
        "Наименование организации (краткое)",
        max_length=512,
        blank=True,
        default="",
    )
    job_title = models.CharField("Должность", max_length=255, blank=True, default="")
    valid_from = models.DateField("Действ. от", blank=True, null=True)
    valid_to = models.DateField("Действ. до", blank=True, null=True)
    is_active = models.BooleanField("Актуален", default=True)
    is_user_managed = models.BooleanField("Управляется пользователем", default=False)
    record_date = models.DateField("Дата записи", blank=True, null=True)
    record_author = models.CharField("Автор записи", max_length=255, blank=True, default="")
    source = models.TextField("Источник", blank=True, default="")
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "contacts_app"
        ordering = ["position", "id"]
        verbose_name = "Должность"
        verbose_name_plural = "Реестр должностей"

    def __str__(self):
        return f"{self.formatted_id} {self.job_title}".strip()

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        self.is_active = self.valid_to is None
        if update_fields is not None:
            kwargs["update_fields"] = set(update_fields) | {"is_active"}
        super().save(*args, **kwargs)

    @property
    def formatted_id(self):
        if not self.pk:
            return ""
        return f"{self.pk:05d}-PSN"

    @classmethod
    def organization_choices(cls):
        values = (
            LegalEntityRecord.objects.filter(
                attribute=LegalEntityRecord.ATTRIBUTE_NAME,
                is_active=True,
            )
            .exclude(short_name="")
            .order_by("position", "id")
            .values_list("short_name", flat=True)
        )
        result = []
        seen = set()
        for value in values:
            normalized = value.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result

    def resolve_source(self) -> str:
        from proposals_app.models import ProposalRegistration

        title = _normalize_compare_value(self.job_title)
        surname = _normalize_compare_value(self.person.last_name if self.person_id else "")
        if not title or not surname:
            return ""
        qs = ProposalRegistration.objects.exclude(contact_full_name="").order_by("position", "id")
        for proposal in qs.iterator():
            if _normalize_compare_value(proposal.recipient_job_title) != title:
                continue
            full_name = _normalize_compare_value(proposal.contact_full_name)
            proposal_surname = full_name.split(" ", 1)[0] if full_name else ""
            if proposal_surname == surname:
                return CONTACT_POSITION_SOURCE
        return ""


class PhoneRecord(models.Model):
    PHONE_TYPE_MOBILE = "mobile"
    PHONE_TYPE_LANDLINE = "landline"
    PHONE_TYPE_CHOICES = [
        (PHONE_TYPE_MOBILE, "Мобильный"),
        (PHONE_TYPE_LANDLINE, "Стационарный"),
    ]

    person = models.ForeignKey(
        PersonRecord,
        verbose_name="ID-PRS",
        on_delete=models.CASCADE,
        related_name="phones",
    )
    country = models.ForeignKey(
        OKSMCountry,
        verbose_name="Страна",
        on_delete=models.SET_NULL,
        related_name="contact_phone_records",
        null=True,
        blank=True,
    )
    code = models.CharField("Код", max_length=32, blank=True, default="")
    phone_type = models.CharField(
        "Тип связи",
        max_length=16,
        choices=PHONE_TYPE_CHOICES,
        default=PHONE_TYPE_MOBILE,
    )
    region = models.CharField("Регион", max_length=255, blank=True, default="")
    phone_number = models.CharField("Номер телефона", max_length=255, blank=True, default="")
    is_primary = models.BooleanField("Основной", default=False)
    extension = models.CharField("Добавочный номер", max_length=32, blank=True, default="")
    valid_from = models.DateField("Действ. от", blank=True, null=True)
    valid_to = models.DateField("Действ. до", blank=True, null=True)
    is_active = models.BooleanField("Актуален", default=True)
    record_date = models.DateField("Дата записи", blank=True, null=True)
    record_author = models.CharField("Автор записи", max_length=255, blank=True, default="")
    source = models.TextField("Источник", blank=True, default="")
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "contacts_app"
        ordering = ["position", "id"]
        verbose_name = "Телефонный номер"
        verbose_name_plural = "Реестр телефонных номеров"
        constraints = [
            models.UniqueConstraint(
                fields=["person"],
                condition=Q(is_primary=True),
                name="contacts_phone_primary_per_person",
            ),
        ]

    def __str__(self):
        phone_display = self.phone_number or ""
        if self.extension:
            phone_display = f"{phone_display} доб. {self.extension}".strip()
        return f"{self.formatted_id} {phone_display}".strip()

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        self.is_active = self.valid_to is None
        if update_fields is not None:
            kwargs["update_fields"] = set(update_fields) | {"is_active"}
        with transaction.atomic():
            if self.is_primary and self.person_id:
                type(self).objects.filter(person_id=self.person_id, is_primary=True).exclude(pk=self.pk).update(is_primary=False)
            super().save(*args, **kwargs)

    def validate_constraints(self, exclude=None):
        # Primary phone uniqueness is enforced in save() by atomically unsetting
        # the flag on sibling records before writing the current row.
        if self.is_primary and self.person_id:
            return
        super().validate_constraints(exclude=exclude)

    @property
    def formatted_id(self):
        if not self.pk:
            return ""
        return f"{self.pk:05d}-TEL"


class EmailRecord(models.Model):
    person = models.ForeignKey(
        PersonRecord,
        verbose_name="ID-PRS",
        on_delete=models.CASCADE,
        related_name="emails",
    )
    email = models.EmailField("Электронная почта", max_length=254, blank=True, default="")
    valid_from = models.DateField("Действ. от", blank=True, null=True)
    valid_to = models.DateField("Действ. до", blank=True, null=True)
    is_active = models.BooleanField("Актуален", default=True)
    is_user_managed = models.BooleanField("Управляется пользователем", default=False)
    user_kind = models.CharField("Пользователь", max_length=16, blank=True, default="", choices=USER_KIND_CHOICES)
    record_date = models.DateField("Дата записи", blank=True, null=True)
    record_author = models.CharField("Автор записи", max_length=255, blank=True, default="")
    source = models.TextField("Источник", blank=True, default="")
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "contacts_app"
        ordering = ["position", "id"]
        verbose_name = "Адрес электронной почты"
        verbose_name_plural = "Реестр адресов электронной почты"

    def __str__(self):
        return f"{self.formatted_id} {self.email}".strip()

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        self.is_active = self.valid_to is None
        if update_fields is not None:
            kwargs["update_fields"] = set(update_fields) | {"is_active"}
        super().save(*args, **kwargs)

    @property
    def formatted_id(self):
        if not self.pk:
            return ""
        return f"{self.pk:05d}-EML"


class ResidenceAddressRecord(models.Model):
    person = models.ForeignKey(
        PersonRecord,
        verbose_name="ID-PRS",
        on_delete=models.CASCADE,
        related_name="residence_addresses",
    )
    country = models.ForeignKey(
        OKSMCountry,
        verbose_name="Страна",
        on_delete=models.SET_NULL,
        related_name="contact_residence_address_records",
        null=True,
        blank=True,
    )
    region = models.CharField("Регион", max_length=255, blank=True, default="")
    postal_code = models.CharField("Индекс", max_length=32, blank=True, default="")
    locality = models.CharField("Населенный пункт", max_length=255, blank=True, default="")
    street = models.CharField("Улица", max_length=255, blank=True, default="")
    building = models.CharField("Здание", max_length=255, blank=True, default="")
    premise = models.CharField("Помещение", max_length=255, blank=True, default="")
    premise_part = models.CharField("Часть помещения", max_length=255, blank=True, default="")
    valid_from = models.DateField("Действ. от", blank=True, null=True)
    valid_to = models.DateField("Действ. до", blank=True, null=True)
    is_active = models.BooleanField("Актуален", default=True)
    record_date = models.DateField("Дата записи", blank=True, null=True)
    record_author = models.CharField("Автор записи", max_length=255, blank=True, default="")
    source = models.TextField("Источник", blank=True, default="")
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "contacts_app"
        ordering = ["position", "id"]
        verbose_name = "Адрес проживания"
        verbose_name_plural = "Реестр адресов проживания"

    def __str__(self):
        country_name = self.country.short_name if self.country_id and self.country else ""
        return f"{self.formatted_id} {country_name}".strip()

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        self.is_active = self.valid_to is None
        if update_fields is not None:
            kwargs["update_fields"] = set(update_fields) | {"is_active"}
        super().save(*args, **kwargs)

    @property
    def formatted_id(self):
        if not self.pk:
            return ""
        return f"{self.pk:05d}-ADR"


class CitizenshipRecord(models.Model):
    person = models.ForeignKey(
        PersonRecord,
        verbose_name="ID-PRS",
        on_delete=models.CASCADE,
        related_name="citizenships",
    )
    country = models.ForeignKey(
        OKSMCountry,
        verbose_name="Страна",
        on_delete=models.SET_NULL,
        related_name="contact_citizenship_records",
        null=True,
        blank=True,
    )
    status = models.CharField("Статус", max_length=255, blank=True, default="")
    identifier = models.CharField("Идентификатор", max_length=255, blank=True, default="")
    number = models.CharField("Номер", max_length=255, blank=True, default="")
    valid_from = models.DateField("Действ. от", blank=True, null=True)
    valid_to = models.DateField("Действ. до", blank=True, null=True)
    is_active = models.BooleanField("Актуален", default=True)
    record_date = models.DateField("Дата записи", blank=True, null=True)
    record_author = models.CharField("Автор записи", max_length=255, blank=True, default="")
    source = models.TextField("Источник", blank=True, default="")
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "contacts_app"
        ordering = ["position", "id"]
        verbose_name = "Гражданство"
        verbose_name_plural = "Реестр гражданств и идентификаторов"

    def __str__(self):
        country_name = self.country.short_name if self.country_id and self.country else ""
        return f"{self.formatted_id} {country_name}".strip()

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        self.is_active = self.valid_to is None
        if update_fields is not None:
            kwargs["update_fields"] = set(update_fields) | {"is_active"}
        super().save(*args, **kwargs)

    @property
    def formatted_id(self):
        if not self.pk:
            return ""
        return f"{self.pk:05d}-CTZ"
