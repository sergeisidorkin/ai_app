from django.db import models

class Product(models.Model):
    short_name = models.CharField("Краткое имя", max_length=64, unique=True)
    name_en = models.CharField("Наименование на английском языке", max_length=255)
    name_ru = models.CharField("Наименование на русском языке", max_length=255)
    service_type = models.CharField("Тип услуги", max_length=128)
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Продукт"
        verbose_name_plural = "Продукты"

    def __str__(self):
        return self.short_name

class TypicalSection(models.Model):
    product = models.ForeignKey(Product, verbose_name="Продукт", on_delete=models.CASCADE, related_name="sections")
    code = models.CharField("Код", max_length=64)
    short_name = models.CharField("Краткое имя", max_length=64)
    name_en = models.CharField("Наименование раздела на английском языке", max_length=255)
    name_ru = models.CharField("Наименование раздела на русском языке", max_length=255)
    accounting_type = models.CharField("Тип учета", max_length=128)
    executor = models.CharField("Исполнитель", max_length=128)
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Типовой раздел"
        verbose_name_plural = "Типовые разделы"
        # Сортируем по продукту, затем по позиции (для устойчивого порядка), затем по id
        ordering = ["product__short_name", "position", "id"]

        constraints = [
            models.UniqueConstraint(fields=["product", "code"], name="ux_section_product_code")
        ]

    def __str__(self):
        return f"{self.product.short_name}:{self.code}"