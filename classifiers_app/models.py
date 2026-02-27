from django.db import models


class OKSMCountry(models.Model):
    number = models.PositiveIntegerField("№")
    code = models.CharField("Код", max_length=3)
    short_name = models.CharField("Наименование страны (краткое)", max_length=255)
    full_name = models.CharField("Наименование страны (полное)", max_length=512, blank=True, default="")
    alpha2 = models.CharField("Буквенный код (Альфа-2)", max_length=2)
    alpha3 = models.CharField("Буквенный код (Альфа-3)", max_length=3)
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Страна (ОКСМ)"
        verbose_name_plural = "Страны (ОКСМ)"

    def __str__(self):
        return f"{self.code} — {self.short_name}"
