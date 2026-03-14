from django.db import models


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


class LegalEntityRecord(models.Model):
    """База юридических лиц."""
    short_name = models.CharField("Наименование (краткое)", max_length=512)
    full_name = models.CharField("Наименование (полное)", max_length=1024, blank=True, default="")
    identifier = models.CharField("Идентификатор", max_length=255, blank=True, default="")
    registration_number = models.CharField("Регистрационный номер", max_length=255, blank=True, default="")
    registration_date = models.DateField("Дата регистрации", blank=True, null=True)
    registration_country = models.ForeignKey(
        OKSMCountry,
        verbose_name="Страна регистрации",
        on_delete=models.SET_NULL,
        related_name="legal_entity_records",
        null=True,
        blank=True,
    )
    record_date = models.DateField("Дата записи", blank=True, null=True)
    record_author = models.CharField("Автор записи", max_length=255, blank=True, default="")
    name_received_date = models.DateField("Дата получения наименования", blank=True, null=True)
    name_changed_date = models.DateField("Дата смены наименования", blank=True, null=True)
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Юридическое лицо"
        verbose_name_plural = "Юридические лица"

    def __str__(self):
        return self.short_name


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
