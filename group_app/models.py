from django.db import models


class GroupMember(models.Model):
    short_name = models.CharField("Наименование компании (краткое)", max_length=255)
    full_name = models.CharField("Наименование компании (полное)", max_length=512, blank=True, default="")
    name_en = models.CharField("Наименование на английском языке", max_length=512, blank=True, default="")
    country_name = models.CharField("Страна регистрации", max_length=255)
    country_code = models.CharField("Код страны (ОКСМ)", max_length=3, blank=True, default="")
    identifier = models.CharField("Идентификатор", max_length=255, blank=True, default="")
    registration_number = models.CharField("Регистрационный номер", max_length=255, blank=True, default="")
    registration_date = models.DateField("Дата регистрации", blank=True, null=True)
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Участник группы"
        verbose_name_plural = "Состав группы"

    def __str__(self):
        return self.short_name
