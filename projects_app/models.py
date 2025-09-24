from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from policy_app.models import Product, TypicalSection


DATE_INPUT_ATTRS = {"class": "form-control js-date", "autocomplete": "off"}  # ← хук для JS-пикера
DATE_INPUT_FORMATS = ["%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"]  # принимаем ISO и ДД.ММ.ГГ

class ProjectRegistration(models.Model):
    class Group(models.TextChoices):
        RU = "RU", "RU"
        KZ = "KZ", "KZ"
        AM = "AM", "AM"

    position = models.PositiveIntegerField(default=0, db_index=True, verbose_name="Позиция")
    number = models.PositiveIntegerField(
        verbose_name="Номер",
        validators=[MinValueValidator(3333), MaxValueValidator(9999)],
    )
    group = models.CharField("Группа", max_length=2, choices=Group.choices, default=Group.RU, db_index=True)
    type = models.ForeignKey(
        Product, on_delete=models.PROTECT, null=True, blank=True,
        related_name="project_registrations", verbose_name="Тип"
    )
    name = models.CharField("Название", max_length=255)

    STATUS_CHOICES = [
        ("Не начат", "Не начат"),
        ("В работе", "В работе"),
        ("На проверке", "На проверке"),
        ("Завершён", "Завершён"),
        ("Отложен", "Отложен"),
    ]
    status = models.CharField("Статус", max_length=20, choices=STATUS_CHOICES, default="Не начат")

    contract_start = models.DateField("Начало контракта", null=True, blank=True)
    contract_end = models.DateField("Окончание контракта", null=True, blank=True)
    completion_calc = models.DateField("Окончание, расчет", null=True, blank=True)

    input_data = models.CharField("Исх. данные", max_length=255, blank=True)

    stage1_weeks = models.PositiveIntegerField("Этап 1, недель", default=0)
    stage1_end = models.DateField("Этап 1, дата окончания", null=True, blank=True)
    stage2_weeks = models.PositiveIntegerField("Этап 2, недель", default=0)
    stage2_end = models.DateField("Этап 2, дата окончания", null=True, blank=True)
    stage3_weeks = models.PositiveIntegerField("Этап 3, недель", default=0)
    term_weeks = models.PositiveIntegerField("Срок, недель", default=0)

    deadline = models.DateField("Дедлайн", null=True, blank=True)
    year = models.PositiveIntegerField("Год", null=True, blank=True)

    customer = models.CharField("Заказчик", max_length=255, blank=True)
    registration_number = models.CharField("Регистрационный номер", max_length=100, blank=True)
    project_manager = models.CharField("Руководитель проекта", max_length=255, blank=True)
    contract_subject = models.TextField("Предмет договора", blank=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Регистрация проекта"
        verbose_name_plural = "Регистрация проекта"

    def __str__(self):
        return f"{self.number} — {self.name}"

class WorkVolume(models.Model):
    position = models.PositiveIntegerField(default=0, db_index=True, verbose_name="Позиция")
    project = models.ForeignKey(
        ProjectRegistration,
        on_delete=models.CASCADE,
        related_name="work_items",
        verbose_name="Номер проекта"
    )
    type = models.CharField(max_length=100, blank=True, verbose_name="Тип")
    name = models.CharField(max_length=255, verbose_name="Название")
    asset_name = models.CharField(max_length=255, blank=True, verbose_name="Наименование актива")
    registration_number = models.CharField(max_length=100, blank=True, verbose_name="Регистрационный номер")
    manager = models.CharField(max_length=255, blank=True, verbose_name="Менеджер")

    class Meta:
        ordering = ["project__position", "position", "id"]
        verbose_name = "Объем работ"
        verbose_name_plural = "Объем работ"

    def __str__(self):
        return f"{self.project.number if self.project_id else '-'} — {self.name}"

WorkVolumeItem = WorkVolume

class Performer(models.Model):
    position = models.PositiveIntegerField(default=1, db_index=True)

    registration = models.ForeignKey(
        ProjectRegistration,
        on_delete=models.CASCADE,
        related_name="performers",
        verbose_name="Регистрация проекта",
    )

    asset_name = models.CharField("Актив", max_length=255, blank=True, default="")
    executor = models.CharField("Исполнитель", max_length=255, blank=True, default="")
    grade = models.CharField("Грейд", max_length=50, blank=True, default="")

    typical_section = models.ForeignKey(
        TypicalSection,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        verbose_name="Типовой раздел",
        related_name="performer_items",
    )

    actual_costs = models.DecimalField("Фактические затраты", max_digits=12, decimal_places=2, null=True, blank=True)
    estimated_costs = models.DecimalField("Расчетные затраты", max_digits=12, decimal_places=2, null=True, blank=True)
    agreed_amount = models.DecimalField("Согласованная сумма", max_digits=12, decimal_places=2, null=True, blank=True)
    prepayment = models.DecimalField("Аванс", max_digits=12, decimal_places=2, null=True, blank=True)
    final_payment = models.DecimalField("Окон. платеж", max_digits=12, decimal_places=2, null=True, blank=True)

    contract_number = models.CharField("Номер договора", max_length=100, blank=True, default="")

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Исполнитель"
        verbose_name_plural = "Исполнители"

    def __str__(self):
        num = getattr(self.registration, "number", "") or ""
        grp = getattr(self.registration, "group", "") or ""
        return f"{num} {grp} — {self.executor or 'исполнитель'}"