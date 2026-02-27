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
