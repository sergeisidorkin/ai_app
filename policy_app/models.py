from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

DEPARTMENT_HEAD_GROUP = "Руководитель направления"
PROJECTS_HEAD_GROUP = "Руководитель проектов"
ADMIN_GROUP = "Администратор"
DIRECTOR_GROUP = "Директор"
DIRECTION_DIRECTOR_GROUP = "Директор направления"
EXPERT_GROUP = "Эксперт"
LAWYER_GROUP = "Юрист"
MANAGER_GROUPS = (
    DEPARTMENT_HEAD_GROUP,
    PROJECTS_HEAD_GROUP,
)
DIRECTOR_GROUPS = (
    DIRECTOR_GROUP,
    DIRECTION_DIRECTOR_GROUP,
)
ROLE_GROUPS_ORDER = (
    DEPARTMENT_HEAD_GROUP,
    PROJECTS_HEAD_GROUP,
    ADMIN_GROUP,
    EXPERT_GROUP,
    DIRECTOR_GROUP,
    DIRECTION_DIRECTOR_GROUP,
    LAWYER_GROUP,
)
SUPERUSER_GROUPS = (
    ADMIN_GROUP,
    DIRECTOR_GROUP,
    DIRECTION_DIRECTOR_GROUP,
    LAWYER_GROUP,
)

def _join_catalog_values(items) -> str:
    values = []
    seen = set()
    for item in items:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        values.append(value)
    return ", ".join(values)


class ConsultingDirection(models.Model):
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Направление консалтинга"
        verbose_name_plural = "Направления консалтинга"

    def __str__(self):
        return self.consulting_types_display or f"Направление консалтинга #{self.pk}"

    @property
    def consulting_types_display(self):
        return _join_catalog_values(self.consulting_types.order_by("position", "id").values_list("name", flat=True))

    @property
    def service_types_display(self):
        return _join_catalog_values(self.service_types.order_by("position", "id").values_list("name", flat=True))

    @property
    def service_codes_display(self):
        return _join_catalog_values(self.service_types.order_by("position", "id").values_list("code", flat=True))

    @property
    def service_subtypes_display(self):
        return _join_catalog_values(self.service_subtypes.order_by("position", "id").values_list("name", flat=True))

    @property
    def table_rows(self):
        consulting_types = sorted(
            list(self.consulting_types.all()),
            key=lambda item: (item.position, item.id),
        )
        service_types = sorted(
            list(self.service_types.select_related("consulting_type").all()),
            key=lambda item: (
                item.consulting_type.position if item.consulting_type_id else 0,
                item.position,
                item.id,
            ),
        )
        service_subtypes = sorted(
            list(self.service_subtypes.select_related("service_type", "service_type__consulting_type").all()),
            key=lambda item: (
                item.service_type.consulting_type.position if item.service_type_id and item.service_type.consulting_type_id else 0,
                item.service_type.position if item.service_type_id else 0,
                item.position,
                item.id,
            ),
        )

        rows = [
            {
                "consulting_type": item.service_type.consulting_type.name,
                "service_type": item.service_type.name,
                "code": item.service_type.code,
                "service_subtype": item.name,
            }
            for item in service_subtypes
        ]
        if rows:
            return rows

        rows = [
            {
                "consulting_type": item.consulting_type.name,
                "service_type": item.name,
                "code": item.code,
                "service_subtype": "",
            }
            for item in service_types
        ]
        if rows:
            return rows

        return [
            {
                "consulting_type": item.name,
                "service_type": "",
                "code": "",
                "service_subtype": "",
            }
            for item in consulting_types
        ]


class ConsultingDirectionType(models.Model):
    direction = models.ForeignKey(
        ConsultingDirection,
        on_delete=models.CASCADE,
        related_name="consulting_types",
        verbose_name="Направление консалтинга",
    )
    name = models.CharField("Вид консалтинга", max_length=128, unique=True)
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["direction__position", "position", "id"]
        verbose_name = "Вид консалтинга"
        verbose_name_plural = "Виды консалтинга"

    def __str__(self):
        return self.name


class ConsultingServiceType(models.Model):
    direction = models.ForeignKey(
        ConsultingDirection,
        on_delete=models.CASCADE,
        related_name="service_types",
        verbose_name="Направление консалтинга",
    )
    consulting_type = models.ForeignKey(
        ConsultingDirectionType,
        on_delete=models.CASCADE,
        related_name="service_types",
        verbose_name="Вид консалтинга",
    )
    name = models.CharField("Тип услуг", max_length=128)
    code = models.CharField("Код", max_length=32)
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["direction__position", "consulting_type__position", "position", "id"]
        verbose_name = "Тип услуги консалтинга"
        verbose_name_plural = "Типы услуг консалтинга"
        constraints = [
            models.UniqueConstraint(
                fields=["consulting_type", "name"],
                name="ux_consulting_service_type_by_kind",
            ),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.consulting_type_id and self.direction_id and self.consulting_type.direction_id != self.direction_id:
            raise ValidationError({"consulting_type": "Вид консалтинга должен относиться к той же строке."})


class ConsultingServiceSubtype(models.Model):
    direction = models.ForeignKey(
        ConsultingDirection,
        on_delete=models.CASCADE,
        related_name="service_subtypes",
        verbose_name="Направление консалтинга",
    )
    service_type = models.ForeignKey(
        ConsultingServiceType,
        on_delete=models.CASCADE,
        related_name="service_subtypes",
        verbose_name="Тип услуг",
    )
    name = models.CharField("Подтип услуги", max_length=255)
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["direction__position", "service_type__position", "position", "id"]
        verbose_name = "Подтип услуги консалтинга"
        verbose_name_plural = "Подтипы услуг консалтинга"
        constraints = [
            models.UniqueConstraint(
                fields=["service_type", "name"],
                name="ux_consulting_service_subtype_by_type",
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def consulting_type(self):
        return self.service_type.consulting_type

    @property
    def code(self):
        return self.service_type.code

    def clean(self):
        super().clean()
        if self.service_type_id and self.direction_id and self.service_type.direction_id != self.direction_id:
            raise ValidationError({"service_type": "Тип услуг должен относиться к той же строке."})


def build_consulting_catalog_meta():
    consulting_types = list(
        ConsultingDirectionType.objects.select_related("direction").order_by(
            "direction__position", "position", "id"
        )
    )
    service_types = list(
        ConsultingServiceType.objects.select_related("direction", "consulting_type").order_by(
            "direction__position", "consulting_type__position", "position", "id"
        )
    )
    service_subtypes = list(
        ConsultingServiceSubtype.objects.select_related(
            "direction", "service_type", "service_type__consulting_type"
        ).order_by(
            "direction__position", "service_type__consulting_type__position", "service_type__position", "position", "id"
        )
    )
    return {
        "consulting_types": [
            {"id": item.pk, "label": item.name, "direction_id": item.direction_id}
            for item in consulting_types
        ],
        "service_categories": [
            {
                "id": item.pk,
                "label": item.name,
                "code": item.code,
                "consulting_type_id": item.consulting_type_id,
                "consulting_type_label": item.consulting_type.name,
                "direction_id": item.direction_id,
            }
            for item in service_types
        ],
        "service_subtypes": [
            {
                "id": item.pk,
                "label": item.name,
                "service_category_id": item.service_type_id,
                "consulting_type_id": item.service_type.consulting_type_id,
                "direction_id": item.direction_id,
                "code": item.service_type.code,
            }
            for item in service_subtypes
        ],
    }


class Product(models.Model):
    short_name = models.CharField("Краткое имя", max_length=64, unique=True)
    name_en = models.CharField("Наименование на английском языке", max_length=255)
    display_name = models.CharField("Отображаемое в системе имя", max_length=255, blank=True, default="")
    name_ru = models.CharField("Наименование на русском языке", max_length=255)
    consulting_type = models.CharField("Вид консалтинга", max_length=128, blank=True, default="")
    service_category = models.CharField("Тип услуг", max_length=128, blank=True, default="")
    service_code = models.CharField("Код", max_length=32, blank=True, default="")
    service_subtype = models.CharField("Подтип услуги", max_length=255, blank=True, default="")
    consulting_type_ref = models.ForeignKey(
        "policy_app.ConsultingDirectionType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
        verbose_name="Вид консалтинга",
    )
    service_category_ref = models.ForeignKey(
        "policy_app.ConsultingServiceType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
        verbose_name="Тип услуг",
    )
    service_subtype_ref = models.ForeignKey(
        "policy_app.ConsultingServiceSubtype",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
        verbose_name="Подтип услуги",
    )
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
    def consulting_type_display(self):
        return (self.consulting_type_ref.name if self.consulting_type_ref_id else self.consulting_type) or ""

    @property
    def service_category_display(self):
        return (self.service_category_ref.name if self.service_category_ref_id else self.service_category) or ""

    @property
    def service_subtype_display(self):
        return (self.service_subtype_ref.name if self.service_subtype_ref_id else self.service_subtype) or ""

    def clean(self):
        super().clean()
        if self.service_subtype_ref_id:
            self.service_category_ref = self.service_subtype_ref.service_type
        if self.service_category_ref_id:
            self.consulting_type_ref = self.service_category_ref.consulting_type
        if (
            self.consulting_type_ref_id
            and self.service_category_ref_id
            and self.service_category_ref.consulting_type_id != self.consulting_type_ref_id
        ):
            raise ValidationError({"service_category_ref": "Тип услуг не соответствует виду консалтинга."})
        if (
            self.service_category_ref_id
            and self.service_subtype_ref_id
            and self.service_subtype_ref.service_type_id != self.service_category_ref_id
        ):
            raise ValidationError({"service_subtype_ref": "Подтип услуги не соответствует типу услуг."})

    def _sync_catalog_refs_from_legacy_values(self):
        if not self.consulting_type_ref_id and self.consulting_type:
            self.consulting_type_ref = (
                ConsultingDirectionType.objects.filter(name=self.consulting_type).order_by("position", "id").first()
            )
        if not self.service_category_ref_id and self.service_category:
            qs = ConsultingServiceType.objects.filter(name=self.service_category)
            if self.consulting_type_ref_id:
                qs = qs.filter(consulting_type=self.consulting_type_ref)
            self.service_category_ref = qs.order_by("position", "id").first()
        if not self.service_subtype_ref_id and self.service_subtype:
            qs = ConsultingServiceSubtype.objects.filter(name=self.service_subtype)
            if self.service_category_ref_id:
                qs = qs.filter(service_type=self.service_category_ref)
            self.service_subtype_ref = qs.order_by("position", "id").first()

    def _sync_legacy_values_from_catalog_refs(self):
        if self.service_subtype_ref_id:
            self.service_category_ref = self.service_subtype_ref.service_type
        if self.service_category_ref_id:
            self.consulting_type_ref = self.service_category_ref.consulting_type
        if self.consulting_type_ref_id:
            self.consulting_type = self.consulting_type_ref.name
        if self.service_category_ref_id:
            self.service_category = self.service_category_ref.name
            self.service_code = self.service_category_ref.code or ""
        if self.service_subtype_ref_id:
            self.service_subtype = self.service_subtype_ref.name

    def save(self, *args, **kwargs):
        self._sync_catalog_refs_from_legacy_values()
        self._sync_legacy_values_from_catalog_refs()
        self.full_clean()
        super().save(*args, **kwargs)

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
    exclude_from_tkp_autofill = models.BooleanField(
        "Исключить из автозаполнения в ТКП",
        default=False,
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
    service_goal_genitive = models.TextField(
        "Цели оказания услуг в родительном падеже",
        blank=True,
        default="",
    )
    report_title = models.TextField("Титул отчета/ТКП", blank=True, default="")
    product_name = models.TextField("Название продукта", blank=True, default="")
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
    service_composition_editor_state = models.JSONField(
        "Состав услуг: состояние редактора",
        default=dict,
        blank=True,
    )
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Типовой состав услуг"
        verbose_name_plural = "Типовой состав услуг"
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.product.short_name} / {self.section.name_ru}"


class TypicalServiceTerm(models.Model):
    product = models.ForeignKey(
        Product,
        verbose_name="Продукт",
        on_delete=models.CASCADE,
        related_name="typical_service_terms",
    )
    preliminary_report_months = models.DecimalField(
        "Срок подготовки Предварительного отчёта, мес.",
        max_digits=6,
        decimal_places=1,
        default=0,
        validators=[MinValueValidator(0)],
    )
    final_report_weeks = models.PositiveIntegerField(
        "Срок подготовки Итогового отчёта, нед.",
        default=0,
    )
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Типовой срок оказания услуг"
        verbose_name_plural = "Типовые сроки оказания услуг"
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.product.short_name} / {self.preliminary_report_months} мес. / {self.final_report_weeks} нед."

    @property
    def preliminary_report_months_display(self):
        return format(self.preliminary_report_months, ".1f").replace(".", ",")


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
        verbose_name_plural = "Тарифы разделов (услуг)"

    def __str__(self):
        return f"{self.product.short_name} / {self.section.short_name}"