from django.db import models


CONTRACT_TYPE_CHOICES = [
    ("gph", "ГПХ Договор гражданско-правового характера"),
    ("smz", "СМЗ Договор с самозанятым"),
]

PARTY_CHOICES = [
    ("individual", "Физлицо"),
    ("legal_entity", "Юрлицо"),
]


class ContractTemplate(models.Model):
    product = models.ForeignKey(
        "policy_app.Product",
        verbose_name="Продукт",
        on_delete=models.CASCADE,
        related_name="contract_templates",
    )
    contract_type = models.CharField(
        "Вид", max_length=16, choices=CONTRACT_TYPE_CHOICES,
    )
    party = models.CharField(
        "Сторона", max_length=16, choices=PARTY_CHOICES,
    )
    country_name = models.CharField("Страна", max_length=255)
    country_code = models.CharField("Код страны (ОКСМ)", max_length=3, blank=True, default="")
    sample_name = models.CharField("Наименование образца", max_length=512)
    version = models.CharField("Версия", max_length=128, blank=True, default="")
    file = models.FileField("Файл", upload_to="contract_templates/", blank=True, default="")
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Образец шаблона договора"
        verbose_name_plural = "Образцы шаблонов договоров"

    def __str__(self):
        return self.sample_name
