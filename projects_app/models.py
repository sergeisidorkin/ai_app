from django.db import models

class ProjectRegistration(models.Model):
    position = models.PositiveIntegerField(default=0, db_index=True, verbose_name="Позиция")
    number = models.CharField(max_length=50, verbose_name="Номер")
    type = models.CharField(max_length=100, blank=True, verbose_name="Тип")
    name = models.CharField(max_length=255, verbose_name="Название")
    status = models.CharField(max_length=100, blank=True, verbose_name="Статус")
    contract_start = models.DateField(null=True, blank=True, verbose_name="Начало контракта")
    contract_end = models.DateField(null=True, blank=True, verbose_name="Окончание контракта")
    completion_calc = models.DateField(null=True, blank=True, verbose_name="Окончание, расчет")
    input_data = models.CharField(max_length=255, blank=True, verbose_name="Исх. данные")
    stage1_weeks = models.PositiveIntegerField(default=0, verbose_name="Этап 1, недель")
    stage1_end = models.DateField(null=True, blank=True, verbose_name="Этап 1, дата окончания")
    stage2_weeks = models.PositiveIntegerField(default=0, verbose_name="Этап 2, недель")
    stage2_end = models.DateField(null=True, blank=True, verbose_name="Этап 2, дата окончания")
    stage3_weeks = models.PositiveIntegerField(default=0, verbose_name="Этап 3, недель")
    term_weeks = models.PositiveIntegerField(default=0, verbose_name="Срок, недель")
    deadline = models.DateField(null=True, blank=True, verbose_name="Дедлайн")
    year = models.IntegerField(null=True, blank=True, verbose_name="Год")
    customer = models.CharField(max_length=255, blank=True, verbose_name="Заказчик")
    registration_number = models.CharField(max_length=100, blank=True, verbose_name="Регистрационный номер")
    project_manager = models.CharField(max_length=255, blank=True, verbose_name="Руководитель проекта")
    deadline_format = models.CharField(max_length=100, blank=True, verbose_name="Дедлайн, формат")
    contract_subject = models.TextField(blank=True, verbose_name="Предмет договора")

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