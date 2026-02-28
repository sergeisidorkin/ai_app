from django.conf import settings
from django.db import models

DEPARTMENT_HEAD_GROUP = "Руководитель направления"

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


class SectionStructure(models.Model):
    product = models.ForeignKey(
        Product, verbose_name="Продукт", on_delete=models.CASCADE, related_name="structures"
    )
    section = models.ForeignKey(
        TypicalSection, verbose_name="Раздел", on_delete=models.CASCADE, related_name="structures"
    )
    subsections = models.TextField("Подразделы", blank=True, default="")
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Типовая структура раздела"
        verbose_name_plural = "Типовая структура раздела"
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.product.short_name} / {self.section.short_name}"


class Grade(models.Model):
    grade_en = models.CharField("Грейд на английском языке", max_length=255)
    grade_ru = models.CharField("Грейд на русском языке", max_length=255)
    qualification_levels = models.PositiveIntegerField("Число уровней квалификации", default=5)
    qualification = models.PositiveIntegerField("Квалификация", default=0)
    is_base_rate = models.BooleanField("Базовая ставка", default=False)
    base_rate_share = models.IntegerField("Доля базовой ставки, %", default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="grades",
        verbose_name="Автор",
    )
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_by", "position", "id"]
        verbose_name = "Грейд"
        verbose_name_plural = "Грейды"

    def __str__(self):
        return self.grade_en or self.grade_ru