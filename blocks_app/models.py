from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

class Block(models.Model):
    code = models.CharField("Код блока", max_length=100, unique=True, db_index=True)
    name = models.CharField("Наименование блока", max_length=255)
    prompt = models.TextField("Промпт")
    context = models.TextField("Контекст", blank=True, default="")
    model = models.CharField("Модель", max_length=100, blank=True, default="")
    temperature = models.FloatField(
        "Температура", null=True, blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(2.0)],
        help_text="Оставьте пустым — будет значение по умолчанию модели."
    )

    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "Блок"
        verbose_name_plural = "Блоки"

    def __str__(self):
        return f"{self.code} — {self.name}"