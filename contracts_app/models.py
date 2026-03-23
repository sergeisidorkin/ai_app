from django.db import models

from projects_app.models import Performer


CONTRACT_TYPE_CHOICES = [
    ("gph", "ГПХ Договор гражданско-правового характера"),
    ("smz", "СМЗ Договор с самозанятым"),
]

PARTY_CHOICES = [
    ("individual", "ФЗЛ Физлицо"),
    ("legal_entity", "ЮРЛ Юрлицо"),
    ("ip", "ИП Индивидуальный предприниматель"),
]


class ContractTemplate(models.Model):
    group_member = models.ForeignKey(
        "group_app.GroupMember",
        verbose_name="Группа",
        on_delete=models.SET_NULL,
        related_name="contract_templates",
        null=True,
    )
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
    is_all_sections = models.BooleanField("Все разделы", default=True)
    typical_sections_json = models.JSONField("Типовые разделы (услуги)", default=list, blank=True)
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Образец шаблона договора"
        verbose_name_plural = "Образцы шаблонов договоров"

    @property
    def typical_sections_display(self):
        if self.is_all_sections:
            return "Все"
        codes = [entry.get("code", "") for entry in self.typical_sections_json or [] if entry.get("code")]
        return ", ".join(codes) if codes else ""

    def __str__(self):
        return self.sample_name


class ContractVariable(models.Model):
    key = models.CharField("Переменная", max_length=255)
    description = models.CharField("Описание", max_length=512, blank=True, default="")
    is_computed = models.BooleanField("Расчётное поле", default=False)
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    source_section = models.CharField("Раздел", max_length=50, blank=True, default="")
    source_table = models.CharField("Таблица", max_length=50, blank=True, default="")
    source_column = models.CharField("Столбец", max_length=100, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Переменная шаблона"
        verbose_name_plural = "Переменные шаблонов"

    @property
    def binding_display(self):
        if self.is_computed:
            return "Расчётное поле"
        if not (self.source_section and self.source_table and self.source_column):
            return ""
        from core.column_registry import COLUMN_REGISTRY
        sec = COLUMN_REGISTRY.get(self.source_section)
        if not sec:
            return ""
        tbl = sec["tables"].get(self.source_table)
        if not tbl:
            return ""
        col_label = tbl["columns"].get(self.source_column, "")
        if not col_label:
            return ""
        return (
            f'Значения столбца «{col_label}» '
            f'из таблицы «{tbl["label"]}» '
            f'раздела «{sec["label"]}»'
        )

    def __str__(self):
        return self.key


class ContractSubject(models.Model):
    product = models.ForeignKey(
        "policy_app.Product",
        verbose_name="Продукт",
        on_delete=models.CASCADE,
        related_name="contract_subjects",
    )
    subject_text = models.CharField(
        "Предмет договора", max_length=1024, blank=True, default=""
    )
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Предмет договора"
        verbose_name_plural = "Предметы договора"

    def __str__(self):
        return self.subject_text or f"Предмет #{self.pk}"


class ContractProjectWork(Performer):
    """Proxy: работа с проектами договоров (раздел «Договоры → В работе»)."""

    class Meta:
        proxy = True
        verbose_name = "В работе: Проект договора"
        verbose_name_plural = "В работе: Проекты договоров"


class ContractSigningWork(Performer):
    """Proxy: работа с подписанием договоров (раздел «Договоры → В работе»)."""

    class Meta:
        proxy = True
        verbose_name = "В работе: Подписание договора"
        verbose_name_plural = "В работе: Подписание договоров"
