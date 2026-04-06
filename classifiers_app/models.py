from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateRangeField, RangeOperators
from django.db import models
from django.db.backends.postgresql.psycopg_any import DateRange
from django.db.models import Q


def build_closed_date_range(valid_from, valid_to):
    return DateRange(valid_from, valid_to, "[]")


def build_half_open_date_range(valid_from, valid_to):
    return DateRange(valid_from, valid_to, "[)")


class OKSMCountry(models.Model):
    number = models.PositiveIntegerField("№")
    code = models.CharField("Код", max_length=3)
    short_name = models.CharField("Наименование страны (краткое)", max_length=255)
    full_name = models.CharField("Наименование страны (полное)", max_length=512, blank=True, default="")
    alpha2 = models.CharField("Буквенный код (Альфа-2)", max_length=2)
    alpha3 = models.CharField("Буквенный код (Альфа-3)", max_length=3)
    approval_date = models.DateField("Дата утверждения", blank=True, null=True)
    expiry_date = models.DateField("Дата прекращения действия", blank=True, null=True)
    source = models.CharField("Источник", max_length=512, blank=True, default="")
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Страна (ОКСМ)"
        verbose_name_plural = "Страны (ОКСМ)"

    def __str__(self):
        return f"{self.code} — {self.short_name}"


class OKVCurrency(models.Model):
    code_numeric = models.CharField("Код 000", max_length=3)
    code_alpha = models.CharField("Код AAA", max_length=3)
    name = models.CharField("Наименование валюты", max_length=255)
    abbreviation = models.CharField("Сокращенное обозначение", max_length=50, blank=True, default="")
    symbol = models.CharField("Символ", max_length=10, blank=True, default="")
    countries = models.ManyToManyField(OKSMCountry, verbose_name="Страны использования", blank=True, related_name="currencies")
    countries_codes = models.CharField("Коды стран использования", max_length=512, blank=True, default="")
    approval_date = models.DateField("Дата утверждения", null=True, blank=True)
    expiry_date = models.DateField("Дата прекращения действия", null=True, blank=True)
    source = models.CharField("Источник", max_length=512, blank=True, default="")
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Валюта (ОКВ)"
        verbose_name_plural = "Валюты (ОКВ)"

    def __str__(self):
        return f"{self.code_alpha} — {self.name}"

    def countries_display(self):
        return ", ".join(c.short_name for c in self.countries.all())

    def update_countries_codes(self):
        codes = ", ".join(c.code for c in self.countries.all())
        if codes != self.countries_codes:
            self.countries_codes = codes
            OKVCurrency.objects.filter(pk=self.pk).update(countries_codes=codes)


class LegalEntityIdentifier(models.Model):
    """Классификатор идентификаторов юрлиц."""
    identifier = models.CharField("Идентификатор", max_length=64)
    full_name = models.CharField("Наименование идентификатора (полное)", max_length=512)
    code = models.CharField("Код", max_length=3, blank=True, default="")
    country = models.ForeignKey(
        OKSMCountry,
        verbose_name="Страна",
        on_delete=models.CASCADE,
        related_name="legal_entity_identifiers",
        null=True,
        blank=True,
    )
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Идентификатор юрлица"
        verbose_name_plural = "Классификатор идентификаторов юрлиц"

    def __str__(self):
        return f"{self.identifier} — {self.full_name}"


class TerritorialDivision(models.Model):
    country = models.ForeignKey(
        OKSMCountry, verbose_name="Страна", on_delete=models.CASCADE, related_name="territorial_divisions"
    )
    region_name = models.CharField("Регион", max_length=255)
    region_code = models.CharField("Код региона", max_length=32)
    effective_date = models.DateField("Дата создания")
    abolished_date = models.DateField("Дата упразднения", blank=True, null=True)
    source = models.TextField("Источник", blank=True, default="")
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Административно-территориальная единица"
        verbose_name_plural = "Административно-территориальное деление"

    def __str__(self):
        return f"{self.country.short_name} / {self.region_name} ({self.effective_date})"


def resolve_territorial_division_region_code(*, country_id=None, region_name="", as_of=None):
    region_name = (region_name or "").strip()
    if not country_id or not region_name:
        return ""
    qs = TerritorialDivision.objects.filter(
        country_id=country_id,
        region_name__iexact=region_name,
    )
    if as_of:
        qs = qs.filter(
            effective_date__lte=as_of,
        ).filter(
            Q(abolished_date__isnull=True) | Q(abolished_date__gte=as_of),
        )
    division = qs.order_by("position", "id").first()
    return division.region_code if division else ""


class RussianFederationSubjectCode(models.Model):
    subject_name = models.CharField("Наименование субъекта Российской Федерации", max_length=255)
    oktmo_code = models.CharField("Код региона ОКТМО", max_length=32, blank=True, default="")
    fns_code = models.CharField("Код ФНС России", max_length=64, blank=True, default="")
    source = models.TextField("Источник", blank=True, default="")
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Код субъекта Российской Федерации"
        verbose_name_plural = "Коды ФНС России для субъектов Российской Федерации"

    def __str__(self):
        return self.subject_name


class BusinessEntityRecord(models.Model):
    name = models.CharField("Наименование", max_length=512)
    record_date = models.DateField("Дата записи", blank=True, null=True)
    record_author = models.CharField("Автор записи", max_length=255, blank=True, default="")
    source = models.TextField("Источник", blank=True, default="")
    comment = models.TextField("Комментарий", blank=True, default="")
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Бизнес-сущность"
        verbose_name_plural = "Реестр бизнес-сущностей"

    def __str__(self):
        return self.name


class BusinessEntityIdentifierRecord(models.Model):
    business_entity = models.ForeignKey(
        BusinessEntityRecord,
        verbose_name="ID",
        on_delete=models.CASCADE,
        related_name="identifiers",
    )
    identifier_type = models.CharField("Тип идентификатора", max_length=255)
    registration_code = models.CharField("Код", max_length=16, blank=True, default="")
    registration_region_code = models.CharField("Код региона", max_length=32, blank=True, default="")
    registration_country = models.ForeignKey(
        OKSMCountry,
        verbose_name="Страна регистрации",
        on_delete=models.SET_NULL,
        related_name="business_entity_identifier_records",
        null=True,
        blank=True,
    )
    number = models.CharField("Номер", max_length=255, blank=True, default="")
    registration_region = models.CharField("Регион", max_length=255, blank=True, default="")
    record_date = models.DateField("Дата записи", blank=True, null=True)
    record_author = models.CharField("Автор записи", max_length=255, blank=True, default="")
    registration_date = models.DateField("Дата регистрации", blank=True, null=True)
    valid_from = models.DateField("Действителен от", blank=True, null=True)
    valid_to = models.DateField("Действителен до", blank=True, null=True)
    valid_range = DateRangeField("Технический диапазон действия", blank=True, null=True, editable=False)
    is_active = models.BooleanField("Актуален", default=True)
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Идентификатор бизнес-сущности"
        verbose_name_plural = "Реестр идентификаторов"
        constraints = [
            ExclusionConstraint(
                name="bei_no_overlap_per_business_entity",
                expressions=[
                    ("business_entity", RangeOperators.EQUAL),
                    ("valid_range", RangeOperators.OVERLAPS),
                ],
            ),
        ]

    def __str__(self):
        return f"{self.business_entity_id:05d} / {self.identifier_type}"

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        self.registration_code = self.registration_country.code if self.registration_country_id else ""
        self.registration_region_code = resolve_territorial_division_region_code(
            country_id=self.registration_country_id,
            region_name=self.registration_region,
            as_of=self.registration_date,
        )
        self.is_active = self.valid_to is None
        self.valid_range = build_closed_date_range(self.valid_from, self.valid_to)
        if update_fields is not None:
            kwargs["update_fields"] = set(update_fields) | {
                "registration_code",
                "registration_region_code",
                "is_active",
                "valid_range",
            }
        super().save(*args, **kwargs)


class BusinessEntityReorganizationEvent(models.Model):
    reorganization_event_uid = models.CharField("ID-REO", max_length=32, unique=True, db_index=True)
    relation_type = models.CharField("Тип связи", max_length=255, blank=True, default="")
    event_date = models.DateField("Дата события", blank=True, null=True)
    comment = models.TextField("Комментарий", blank=True, default="")
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Событие реорганизации"
        verbose_name_plural = "События реорганизации"

    def __str__(self):
        return self.reorganization_event_uid or f"REO {self.pk}"


class BusinessEntityRelationRecord(models.Model):
    event = models.ForeignKey(
        BusinessEntityReorganizationEvent,
        verbose_name="Событие реорганизации",
        on_delete=models.CASCADE,
        related_name="relations",
    )
    from_business_entity = models.ForeignKey(
        BusinessEntityRecord,
        verbose_name="От ID-BSN",
        on_delete=models.CASCADE,
        related_name="outgoing_relations",
    )
    to_business_entity = models.ForeignKey(
        BusinessEntityRecord,
        verbose_name="К ID-BSN",
        on_delete=models.CASCADE,
        related_name="incoming_relations",
    )
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Связь бизнес-сущностей"
        verbose_name_plural = "Реестр реорганизаций"

    def __str__(self):
        event_uid = self.event.reorganization_event_uid if self.event_id else "—"
        return f"{event_uid} / {self.from_business_entity_id:05d} -> {self.to_business_entity_id:05d}"


def detect_legal_entity_region_by_identifier(identifier: str, registration_number: str) -> str:
    identifier_upper = (identifier or "").upper()
    if "ОГРН" not in identifier_upper and "OGRN" not in identifier_upper:
        return ""

    digits = "".join(ch for ch in (registration_number or "") if ch.isdigit())
    if len(digits) < 5:
        return ""

    fns_code = digits[3:5]
    item = RussianFederationSubjectCode.objects.filter(
        fns_code=fns_code
    ).order_by("position", "id").first()
    return item.subject_name if item else ""


class LegalEntityRecord(models.Model):
    """База юридических лиц."""

    ATTRIBUTE_NAME = "Наименование"
    ATTRIBUTE_LEGAL_ADDRESS = "Юридический адрес"
    ATTRIBUTE_CHOICES = (
        (ATTRIBUTE_NAME, ATTRIBUTE_NAME),
        (ATTRIBUTE_LEGAL_ADDRESS, ATTRIBUTE_LEGAL_ADDRESS),
    )

    attribute = models.CharField("Атрибут", max_length=64, choices=ATTRIBUTE_CHOICES, default=ATTRIBUTE_NAME, db_index=True)
    short_name = models.CharField("Наименование (краткое)", max_length=512, blank=True, default="")
    full_name = models.CharField("Наименование (полное)", max_length=1024, blank=True, default="")
    identifier = models.CharField("Идентификатор", max_length=255, blank=True, default="")
    registration_number = models.CharField("Регистрационный номер", max_length=255, blank=True, default="")
    registration_date = models.DateField("Дата регистрации", blank=True, null=True)
    identifier_record = models.ForeignKey(
        BusinessEntityIdentifierRecord,
        verbose_name="ID-IDN",
        on_delete=models.CASCADE,
        related_name="legal_entity_records",
        null=True,
        blank=True,
    )
    registration_country = models.ForeignKey(
        OKSMCountry,
        verbose_name="Страна регистрации",
        on_delete=models.SET_NULL,
        related_name="legal_entity_records",
        null=True,
        blank=True,
    )
    registration_region = models.CharField("Регион", max_length=255, blank=True, default="")
    record_date = models.DateField("Дата записи", blank=True, null=True)
    record_author = models.CharField("Автор записи", max_length=255, blank=True, default="")
    name_received_date = models.DateField("Дата получения наименования", blank=True, null=True)
    name_changed_date = models.DateField("Дата смены наименования", blank=True, null=True)
    postal_code = models.CharField("Индекс", max_length=32, blank=True, default="")
    municipality = models.CharField("Муниципальное образование", max_length=255, blank=True, default="")
    settlement = models.CharField("Поселение", max_length=255, blank=True, default="")
    locality = models.CharField("Населенный пункт", max_length=255, blank=True, default="")
    district = models.CharField("Квартал / район", max_length=255, blank=True, default="")
    street = models.CharField("Улица", max_length=255, blank=True, default="")
    building = models.CharField("Здание", max_length=255, blank=True, default="")
    premise = models.CharField("Помещение", max_length=255, blank=True, default="")
    premise_part = models.CharField("Часть помещения", max_length=255, blank=True, default="")
    valid_from = models.DateField("Действителен от", blank=True, null=True)
    valid_to = models.DateField("Действителен до", blank=True, null=True)
    valid_range = DateRangeField("Технический диапазон действия", blank=True, null=True, editable=False)
    is_active = models.BooleanField("Актуален", default=True)
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Юридическое лицо"
        verbose_name_plural = "Юридические лица"
        constraints = [
            ExclusionConstraint(
                name="ler_name_no_overlap_per_identifier",
                expressions=[
                    ("identifier_record", RangeOperators.EQUAL),
                    ("valid_range", RangeOperators.OVERLAPS),
                ],
                condition=Q(attribute="Наименование", identifier_record__isnull=False),
            ),
            ExclusionConstraint(
                name="ler_address_no_overlap_per_identifier",
                expressions=[
                    ("identifier_record", RangeOperators.EQUAL),
                    ("valid_range", RangeOperators.OVERLAPS),
                ],
                condition=Q(attribute="Юридический адрес", identifier_record__isnull=False),
            ),
        ]

    def __str__(self):
        return self.short_name or self.full_name or f"{self.attribute} #{self.pk}"

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        if self.attribute == self.ATTRIBUTE_NAME:
            self.valid_from = self.name_received_date
            self.valid_to = self.name_changed_date
            self.valid_range = build_half_open_date_range(self.name_received_date, self.name_changed_date)
            self.is_active = self.name_changed_date is None
            derived_fields = {"valid_from", "valid_to", "valid_range", "is_active"}
        else:
            self.valid_range = build_closed_date_range(self.valid_from, self.valid_to)
            self.is_active = self.valid_to is None
            derived_fields = {"valid_range", "is_active"}
        if update_fields is not None:
            kwargs["update_fields"] = set(update_fields) | derived_fields
        super().save(*args, **kwargs)


class BusinessEntityAttributeRecord(models.Model):
    attribute_name = models.CharField("Наименование атрибута", max_length=255, blank=True, default="")
    subsection_name = models.CharField("Наименование подраздела", max_length=255, blank=True, default="")
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Атрибут"
        verbose_name_plural = "Реестр атрибутов"

    def __str__(self):
        return self.attribute_name or "Атрибут"


class LivingWage(models.Model):
    country = models.ForeignKey(
        OKSMCountry, verbose_name="Страна", on_delete=models.CASCADE, related_name="living_wages"
    )
    region = models.ForeignKey(
        TerritorialDivision, verbose_name="Регион", on_delete=models.CASCADE, related_name="living_wages"
    )
    amount = models.DecimalField("Величина прожиточного минимума", max_digits=12, decimal_places=2)
    currency = models.CharField("Валюта", max_length=50)
    approval_date = models.DateField("Дата утверждения")
    expiry_date = models.DateField("Дата прекращения действия", blank=True, null=True)
    source = models.TextField("Источник", blank=True, default="")
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Величина прожиточного минимума"
        verbose_name_plural = "Величины прожиточного минимума"

    def __str__(self):
        return f"{self.country.short_name} / {self.region.region_name} — {self.amount}"
