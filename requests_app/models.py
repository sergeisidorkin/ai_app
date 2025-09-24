from django.db import models
from policy_app.models import Product, TypicalSection

class RequestTable(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="request_tables")
    section = models.ForeignKey(TypicalSection, on_delete=models.CASCADE, related_name="request_tables")

    class Meta:
        unique_together = (("product", "section"),)
        verbose_name = "Таблица запросов"
        verbose_name_plural = "Таблицы запросов"

    def __str__(self):
        ps = getattr(self.product, "short_name", "") or str(self.product_id)
        sn = getattr(self.section, "name_ru", "") or str(self.section_id)
        return f"{ps} / {sn}"


class RequestItem(models.Model):
    table = models.ForeignKey(RequestTable, on_delete=models.CASCADE, related_name="items")
    position = models.PositiveIntegerField(default=1)
    code = models.CharField(max_length=50)
    number = models.PositiveIntegerField()
    short_name = models.CharField("Краткое наименование", max_length=120, blank=True, default="")
    name = models.CharField(max_length=255)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Запрос"
        verbose_name_plural = "Запросы"

    def __str__(self):
        return f"{self.code} — {self.name}"