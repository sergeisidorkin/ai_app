from django.conf import settings
from django.db import models

DEPARTMENT_HEAD_GROUP = "Руководитель направления"
PROJECTS_HEAD_GROUP = "Руководитель проектов"
ADMIN_GROUP = "Администратор"
DIRECTOR_GROUP = "Директор"
EXPERT_GROUP = "Эксперт"
LAWYER_GROUP = "Юрист"
MANAGER_GROUPS = (
    DEPARTMENT_HEAD_GROUP,
    PROJECTS_HEAD_GROUP,
)
SUPERUSER_GROUPS = (
    ADMIN_GROUP,
    DIRECTOR_GROUP,
    LAWYER_GROUP,
)

class Product(models.Model):
    short_name = models.CharField("Краткое имя", max_length=64, unique=True)
    name_en = models.CharField("Наименование на английском языке", max_length=255)
    display_name = models.CharField("Отображаемое в системе имя", max_length=255, blank=True, default="")
    name_ru = models.CharField("Наименование на русском языке", max_length=255)
    service_type = models.CharField("Тип услуги", max_length=128)
    owners = models.ManyToManyField(
        "group_app.GroupMember",
        blank=True,
        related_name="products",
        verbose_name="Владельцы",
    )
    is_group_owner = models.BooleanField("Группа (все компании)", default=False)
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Продукт"
        verbose_name_plural = "Продукты"

    def __str__(self):
        return self.short_name

    @property
    def owner_display(self):
        if self.is_group_owner:
            return "Группа"
        names = list(self.owners.order_by("position").values_list("short_name", flat=True))
        return ", ".join(names) if names else ""

class TypicalSection(models.Model):
    ACCOUNTING_TYPE_CHOICES = [
        ("Раздел", "Раздел"),
        ("Услуги", "Услуги"),
    ]

    product = models.ForeignKey(Product, verbose_name="Продукт", on_delete=models.CASCADE, related_name="sections")
    code = models.CharField("Код", max_length=64)
    short_name = models.CharField("Краткое имя EN", max_length=64)
    short_name_ru = models.CharField("Краткое имя RU", max_length=128, blank=True, default="")
    name_en = models.CharField("Наименование раздела на английском языке", max_length=255)
    name_ru = models.CharField("Наименование раздела на русском языке", max_length=255)
    accounting_type = models.CharField("Тип учета", max_length=128, choices=ACCOUNTING_TYPE_CHOICES, default="Раздел")
    executor = models.CharField("Исполнитель", max_length=128, blank=True, default="")
    specialties = models.ManyToManyField(
        "experts_app.ExpertSpecialty",
        through="TypicalSectionSpecialty",
        blank=True,
        related_name="typical_sections",
        verbose_name="Специальности",
    )
    expertise_dir = models.ForeignKey(
        "policy_app.ExpertiseDirection",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="typical_sections_dir",
        verbose_name="Экспертиза",
    )
    expertise_direction = models.ForeignKey(
        "group_app.OrgUnit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="typical_sections",
        verbose_name="Направление экспертизы",
    )
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Типовой раздел"
        verbose_name_plural = "Типовые разделы"
        ordering = ["product__short_name", "position", "id"]

        constraints = [
            models.UniqueConstraint(fields=["product", "code"], name="ux_section_product_code")
        ]

    def __str__(self):
        return f"{self.product.short_name}:{self.code}"


class TypicalSectionSpecialty(models.Model):
    section = models.ForeignKey(
        TypicalSection,
        on_delete=models.CASCADE,
        related_name="ranked_specialties",
    )
    specialty = models.ForeignKey(
        "experts_app.ExpertSpecialty",
        on_delete=models.CASCADE,
        related_name="section_links",
    )
    rank = models.PositiveIntegerField("Ранг", default=1)

    class Meta:
        ordering = ["rank"]
        unique_together = [("section", "specialty")]
        verbose_name = "Специальность раздела"
        verbose_name_plural = "Специальности раздела"

    def __str__(self):
        return f"{self.section} — {self.specialty} (#{self.rank})"


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


class ServiceGoalReport(models.Model):
    product = models.ForeignKey(
        Product,
        verbose_name="Продукт",
        on_delete=models.CASCADE,
        related_name="service_goal_reports",
    )
    service_goal = models.TextField("Цели оказания услуг", blank=True, default="")
    report_title = models.TextField("Название отчета", blank=True, default="")
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Цель услуги и название отчета"
        verbose_name_plural = "Цели услуг и названия отчетов"
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.product.short_name} / {self.report_title or self.service_goal}"


class TypicalServiceComposition(models.Model):
    product = models.ForeignKey(
        Product,
        verbose_name="Продукт",
        on_delete=models.CASCADE,
        related_name="typical_service_compositions",
    )
    section = models.ForeignKey(
        TypicalSection,
        verbose_name="Раздел (услуга)",
        on_delete=models.CASCADE,
        related_name="typical_service_compositions",
    )
    service_composition = models.TextField("Состав услуг", blank=True, default="")
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Типовой состав услуг"
        verbose_name_plural = "Типовой состав услуг"
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.product.short_name} / {self.section.name_ru}"


class ExpertiseDirection(models.Model):
    PRICING_METHOD_CHOICES = [
        ("vpm", "Ставка в ВПМ"),
        ("hours", "Объем услуг в часах"),
    ]

    name = models.CharField("Наименование направления", max_length=255)
    short_name = models.CharField("Краткое обозначение", max_length=128)
    pricing_method = models.CharField(
        "Расчет стоимости услуг",
        max_length=16,
        choices=PRICING_METHOD_CHOICES,
        blank=True,
        default="",
    )
    owners = models.ManyToManyField(
        "group_app.GroupMember",
        blank=True,
        related_name="expertise_directions",
        verbose_name="Владельцы",
    )
    is_group_owner = models.BooleanField("Группа (все компании)", default=False)
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Направление экспертизы"
        verbose_name_plural = "Направления экспертизы"

    def __str__(self):
        return self.name

    @property
    def owner_display(self):
        if self.is_group_owner:
            return "Группа"
        names = list(self.owners.order_by("position").values_list("short_name", flat=True))
        return ", ".join(names) if names else ""


class Grade(models.Model):
    grade_en = models.CharField("Грейд на английском языке", max_length=255)
    grade_ru = models.CharField("Грейд на русском языке", max_length=255)
    qualification_levels = models.PositiveIntegerField("Число уровней квалификации", default=5)
    qualification = models.PositiveIntegerField("Квалификация", default=0)
    is_base_rate = models.BooleanField("Базовая ставка", default=False)
    base_rate_share = models.IntegerField("Доля базовой ставки, %", default=0)
    hourly_rate = models.DecimalField(
        "Часовая ставка", max_digits=12, decimal_places=2, null=True, blank=True
    )
    currency = models.ForeignKey(
        "classifiers_app.OKVCurrency",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="grades",
        verbose_name="Валюта",
    )
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


class SpecialtyTariff(models.Model):
    specialty_group = models.CharField("Группа специальностей", max_length=255, blank=True, default="")
    specialties = models.ManyToManyField(
        "experts_app.ExpertSpecialty",
        blank=True,
        related_name="specialty_tariffs",
        verbose_name="Специальности",
    )
    expertise_direction = models.ForeignKey(
        "group_app.OrgUnit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="specialty_tariffs",
        verbose_name="Направление экспертизы",
    )
    daily_rate_tkp_eur = models.DecimalField(
        "Дневная ставка оплаты в евро для ТКП",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    daily_rate_ss = models.DecimalField(
        "Дневная ставка оплаты для с/с",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    currency = models.ForeignKey(
        "classifiers_app.OKVCurrency",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="specialty_tariffs",
        verbose_name="Валюта",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="specialty_tariffs",
        verbose_name="Автор",
    )
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_by", "position", "id"]
        verbose_name = "Тариф специальностей"
        verbose_name_plural = "Тарифы специальностей"

    def __str__(self):
        return self.specialty_group or f"Тариф специальностей #{self.pk}"

    @property
    def expertise_direction_display(self):
        labels = []
        seen = set()
        for specialty in self.specialties.select_related("expertise_dir").order_by("position", "id"):
            label = (getattr(specialty.expertise_dir, "short_name", "") or "").strip()
            if label == "—":
                label = ""
            if label and label not in seen:
                seen.add(label)
                labels.append(label)
        return ", ".join(labels)


class Tariff(models.Model):
    product = models.ForeignKey(
        Product, verbose_name="Продукт", on_delete=models.CASCADE, related_name="tariffs"
    )
    section = models.ForeignKey(
        TypicalSection, verbose_name="Раздел", on_delete=models.CASCADE, related_name="tariffs"
    )
    base_rate_vpm = models.DecimalField(
        "Базовая ставка в ВПМ", max_digits=10, decimal_places=2, default=1
    )
    service_hours = models.PositiveIntegerField(
        "Объем услуг в часах", default=0
    )
    service_days_tkp = models.PositiveIntegerField(
        "Объем услуг в днях для ТКП", default=0
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tariffs",
        verbose_name="Автор",
    )
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_by", "position", "id"]
        verbose_name = "Тариф"
        verbose_name_plural = "Тарифы"

    def __str__(self):
        return f"{self.product.short_name} / {self.section.short_name}"