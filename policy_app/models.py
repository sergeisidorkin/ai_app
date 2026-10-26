from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models, transaction

DEPARTMENT_HEAD_GROUP = "Руководитель направления"
PROJECTS_HEAD_GROUP = "Руководитель проектов"
PROJECTS_COORDINATOR_GROUP = "Координатор проектов"
ADMIN_GROUP = "Администратор"
DIRECTOR_GROUP = "Директор"
DIRECTION_DIRECTOR_GROUP = "Директор направления"
EXPERT_GROUP = "Эксперт"
LAWYER_GROUP = "Юрист"
MANAGER_GROUPS = (
    DEPARTMENT_HEAD_GROUP,
    PROJECTS_HEAD_GROUP,
    PROJECTS_COORDINATOR_GROUP,
)
DIRECTOR_GROUPS = (
    DIRECTOR_GROUP,
    DIRECTION_DIRECTOR_GROUP,
)
ROLE_GROUPS_ORDER = (
    DEPARTMENT_HEAD_GROUP,
    PROJECTS_HEAD_GROUP,
    PROJECTS_COORDINATOR_GROUP,
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
)

SYSTEM_DSC_SECTION_CODE = "DSC"
SYSTEM_DSC_SECTION_DEFAULTS = {
    "code": SYSTEM_DSC_SECTION_CODE,
    "short_name": "Description",
    "short_name_ru": "Описание",
    "name_en": "Product description",
    "name_ru": "Описание продукта",
    "accounting_type": "Разделы",
    "expertise_dir": None,
    "expertise_direction": None,
    "exclude_from_tkp_autofill": False,
    "is_system": True,
}

# Старые значения типа учета раздела. В классификаторе их заменяют «Разделы» и «Управление».
LEGACY_SECTION_ACCOUNTING_TYPES = {
    "Раздел": "Разделы",
    "Услуги": "Управление",
}
_MISSING = object()


def classifier_accounting_type(value) -> str:
    text = str(value or "").strip()
    if not text:
        return "Разделы"
    return LEGACY_SECTION_ACCOUNTING_TYPES.get(text, text)


_SECTION_CLASSIFIER_FIELDS = {
    "short_name",
    "short_name_ru",
    "accounting_type",
    "expertise_dir",
    "expertise_dir_id",
    "expertise_direction",
    "expertise_direction_id",
}


def resolve_copied_section_name(posted, previous_name, new_name, *, block_changed) -> str:
    """Копирует наименование из классификатора, пока пользователь его не изменил."""
    posted = "" if posted is None else str(posted)
    if not block_changed:
        return posted
    if previous_name is None:
        return posted if posted.strip() else (new_name or "")
    if posted == (previous_name or ""):
        return new_name or ""
    return posted


def normalize_section_code(value) -> str:
    return str(value or "").strip().upper()


def is_system_dsc_code(value) -> bool:
    return normalize_section_code(value) == SYSTEM_DSC_SECTION_CODE

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

    def _ordered_consulting_types(self):
        prefetched = getattr(self, "_policy_consulting_types", None)
        if prefetched is not None:
            return prefetched
        return self.consulting_types.order_by("position", "id")

    def _ordered_service_types(self):
        prefetched = getattr(self, "_policy_service_types", None)
        if prefetched is not None:
            return prefetched
        return self.service_types.select_related("consulting_type").order_by(
            "consulting_type__position",
            "position",
            "id",
        )

    def _ordered_service_subtypes(self):
        prefetched = getattr(self, "_policy_service_subtypes", None)
        if prefetched is not None:
            return prefetched
        return self.service_subtypes.select_related(
            "service_type",
            "service_type__consulting_type",
        ).order_by(
            "service_type__consulting_type__position",
            "service_type__position",
            "position",
            "id",
        )

    @property
    def consulting_types_display(self):
        return _join_catalog_values(item.name for item in self._ordered_consulting_types())

    @property
    def service_types_display(self):
        return _join_catalog_values(item.name for item in self._ordered_service_types())

    @property
    def service_codes_display(self):
        return _join_catalog_values(item.code for item in self._ordered_service_types())

    @property
    def service_subtypes_display(self):
        return _join_catalog_values(item.name for item in self._ordered_service_subtypes())

    @property
    def table_rows(self):
        consulting_types = self._ordered_consulting_types()
        service_types = self._ordered_service_types()
        service_subtypes = self._ordered_service_subtypes()

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


PRODUCT_ACCURACY_CHOICES = (
    (">50%", ">50%"),
    ("±30\u201350%", "±30\u201350%"),
    ("±20\u201330%", "±20\u201330%"),
    ("±10\u201320%", "±10\u201320%"),
    ("<10%", "<10%"),
)
PRODUCT_ACCURACY_VALUES = frozenset(value for value, _label in PRODUCT_ACCURACY_CHOICES)
_PRODUCT_ACCURACY_DASHES = str.maketrans({
    "-": "\u2013",
    "\u2014": "\u2013",
    "\u2212": "\u2013",
})


def normalize_product_accuracy(value):
    if value is None:
        return ""
    return str(value).strip().translate(_PRODUCT_ACCURACY_DASHES)


PRODUCT_GROUP_MARK = "⧉"


def strip_product_group_mark(short_name):
    base = str(short_name or "").strip()
    if base.endswith(PRODUCT_GROUP_MARK):
        return base[: -len(PRODUCT_GROUP_MARK)].strip()
    return base


def with_product_group_mark(short_name):
    base = strip_product_group_mark(short_name)
    if not base:
        return ""
    return f"{base}{PRODUCT_GROUP_MARK}"


class Product(models.Model):
    ACCURACY_CHOICES = PRODUCT_ACCURACY_CHOICES
    ACCURACY_VALUES = PRODUCT_ACCURACY_VALUES

    short_name = models.CharField("Краткое имя", max_length=64, unique=True)
    name_en = models.CharField("Наименование на английском языке", max_length=255)
    display_name = models.CharField("Отображаемое в системе имя", max_length=255, blank=True, default="")
    name_ru = models.CharField("Наименование на русском языке", max_length=255)
    consulting_type = models.CharField("Вид консалтинга", max_length=128, blank=True, default="")
    service_category = models.CharField("Тип услуг", max_length=128, blank=True, default="")
    service_code = models.CharField("Код", max_length=32, blank=True, default="")
    service_subtype = models.CharField("Подтип услуги", max_length=255, blank=True, default="")
    accuracy = models.CharField(
        "Точность",
        max_length=16,
        blank=True,
        default="",
        choices=PRODUCT_ACCURACY_CHOICES,
    )
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
    is_product_group = models.BooleanField("Групповой продукт", default=False)
    group = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="grouped_products",
        verbose_name="Групповой продукт",
    )
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
        if self.is_product_group and self.group_id:
            raise ValidationError({"group": "Групповой продукт не может входить в другую группу."})
        if self.is_product_group:
            marked = with_product_group_mark(self.short_name)
            if not marked:
                raise ValidationError({"short_name": "Обязательное поле."})
            if len(marked) > 64:
                raise ValidationError({"short_name": "Краткое имя слишком длинное."})
            self.short_name = marked
        elif PRODUCT_GROUP_MARK in (self.short_name or ""):
            raise ValidationError({"short_name": "Знак ⧉ зарезервирован для группового продукта."})

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
        owners = getattr(self, "_policy_owner_display_items", None)
        if owners is None:
            owners = self.owners.only("id", "short_name", "position").order_by("position", "id")
        names = [owner.short_name for owner in owners]
        return ", ".join(names) if names else ""

    @property
    def classification_locked(self):
        return bool(self.pk and (self.is_product_group or self.group_id))

    def grouping_owner_key(self):
        if self.is_group_owner:
            return "group"
        owners = getattr(self, "_policy_owner_display_items", None)
        if owners is None:
            owner_ids = self.owners.values_list("pk", flat=True)
        else:
            owner_ids = [owner.pk for owner in owners]
        normalized = sorted(int(owner_id) for owner_id in owner_ids)
        if not normalized:
            return "none"
        return ",".join(str(owner_id) for owner_id in normalized)


class TypicalSectionManager(models.Manager):
    def create(self, **kwargs):
        return super().create(**prepare_typical_section_create_kwargs(kwargs))


class TypicalSection(models.Model):
    """Строка продукта. Код и справочные поля берутся из классификатора блоков."""

    product = models.ForeignKey(Product, verbose_name="Продукт", on_delete=models.CASCADE, related_name="sections")
    code = models.CharField("Код", max_length=64)
    name_en = models.CharField(
        "Наименование раздела на английском языке",
        max_length=255,
        blank=True,
    )
    name_ru = models.CharField(
        "Наименование раздела на русском языке",
        max_length=255,
        blank=True,
    )
    exclude_from_tkp_autofill = models.BooleanField(
        "Исключить из автозаполнения в ТКП",
        default=False,
    )
    service_block = models.ForeignKey(
        "policy_app.ServiceBlockClassifier",
        on_delete=models.PROTECT,
        related_name="typical_sections",
        verbose_name="Блок услуг",
    )
    is_system = models.BooleanField("Системный раздел", default=False, db_index=True)
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TypicalSectionManager()

    class Meta:
        verbose_name = "Типовой раздел"
        verbose_name_plural = "Типовые разделы"
        ordering = ["product__short_name", "position", "id"]

        constraints = [
            models.UniqueConstraint(fields=["product", "code"], name="ux_section_product_code"),
            models.UniqueConstraint(fields=["product", "service_block"], name="ux_section_product_service_block"),
        ]

    def __str__(self):
        return f"{self.product.short_name}:{self.code}"

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = [
                name for name in update_fields if name not in _SECTION_CLASSIFIER_FIELDS
            ]
        dirty = getattr(self, "_classifier_dirty_fields", None)
        block = self._block()
        if dirty and block is not None and block.pk:
            block.save(update_fields=list(set(dirty) | {"updated_at"}))
            self._classifier_dirty_fields = set()
        if self.service_block_id:
            self.code = self.service_block.code
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = list(set(kwargs["update_fields"]) | {"service_block", "code"})
        super().save(*args, **kwargs)

    def _block(self):
        if not self.service_block_id:
            return None
        return self.service_block

    def _write_classifier_field(self, name, value):
        block = self._block()
        if block is None:
            return
        setattr(block, name, value)
        dirty = getattr(self, "_classifier_dirty_fields", None)
        if dirty is None:
            dirty = set()
            self._classifier_dirty_fields = dirty
        dirty.add(name)

    @property
    def short_name(self):
        block = self._block()
        return block.short_name if block is not None else ""

    @short_name.setter
    def short_name(self, value):
        self._write_classifier_field("short_name", value)

    @property
    def short_name_ru(self):
        block = self._block()
        return block.short_name_ru if block is not None else ""

    @short_name_ru.setter
    def short_name_ru(self, value):
        self._write_classifier_field("short_name_ru", value)

    @property
    def accounting_type(self):
        block = self._block()
        return block.accounting_type if block is not None else ""

    @accounting_type.setter
    def accounting_type(self, value):
        self._write_classifier_field("accounting_type", classifier_accounting_type(value))

    @property
    def expertise_dir(self):
        block = self._block()
        return block.expertise_dir if block is not None else None

    @expertise_dir.setter
    def expertise_dir(self, value):
        self._write_classifier_field("expertise_dir", value)

    @property
    def expertise_dir_id(self):
        block = self._block()
        return block.expertise_dir_id if block is not None else None

    @expertise_dir_id.setter
    def expertise_dir_id(self, value):
        self._write_classifier_field("expertise_dir_id", value)

    @property
    def expertise_direction(self):
        block = self._block()
        return block.expertise_direction if block is not None else None

    @expertise_direction.setter
    def expertise_direction(self, value):
        self._write_classifier_field("expertise_direction", value)

    @property
    def expertise_direction_id(self):
        block = self._block()
        return block.expertise_direction_id if block is not None else None

    @expertise_direction_id.setter
    def expertise_direction_id(self, value):
        self._write_classifier_field("expertise_direction_id", value)

    @property
    def ranked_specialties(self):
        block = self._block()
        if block is None:
            return ServiceBlockClassifierSpecialty.objects.none()
        return block.ranked_specialties

    @property
    def is_system_dsc(self):
        return self.is_system and is_system_dsc_code(self.code)

    @property
    def managed_department_display(self):
        direction = self.expertise_dir if self.expertise_dir_id else None
        if direction is None:
            return ""
        return direction.department_display


def prepare_typical_section_create_kwargs(kwargs):
    """Собирает блок классификатора для создания раздела.

    Старые вызовы передают краткое имя, тип учета и экспертизу прямо в раздел.
    Эти значения записываются в классификатор, а не в строку продукта.
    """
    short_name = kwargs.pop("short_name", _MISSING)
    short_name_ru = kwargs.pop("short_name_ru", _MISSING)
    accounting_type = kwargs.pop("accounting_type", _MISSING)
    expertise_dir = kwargs.pop("expertise_dir", _MISSING)
    expertise_dir_id = kwargs.pop("expertise_dir_id", _MISSING)
    expertise_direction = kwargs.pop("expertise_direction", _MISSING)
    expertise_direction_id = kwargs.pop("expertise_direction_id", _MISSING)

    block = kwargs.get("service_block")
    block_id = kwargs.get("service_block_id")
    if block is None and block_id:
        block = ServiceBlockClassifier.objects.filter(pk=block_id).first()

    code = normalize_service_block_code(kwargs.get("code") or (block.code if block is not None else ""))
    if block is None and is_system_dsc_code(code):
        block = ensure_dsc_service_block()
    created = False
    if block is None:
        if code:
            block = ServiceBlockClassifier.objects.filter(code=code).first()
        if block is None:
            if not code:
                raise ValidationError("Для типового блока нужен код классификатора.")
            position = (
                ServiceBlockClassifier.objects.order_by("-position", "-id")
                .values_list("position", flat=True)
                .first()
                or 0
            ) + 1
            block = ServiceBlockClassifier(
                code=code,
                short_name=(str(short_name).strip() if short_name is not _MISSING and short_name else code)[:64],
                short_name_ru=(
                    str(short_name_ru).strip() if short_name_ru is not _MISSING and short_name_ru else ""
                )[:128],
                name_en=str(kwargs.get("name_en") or "")[:255],
                name_ru=str(kwargs.get("name_ru") or "")[:255],
                accounting_type=classifier_accounting_type(
                    None if accounting_type is _MISSING else accounting_type
                ),
                position=position,
            )
            if expertise_dir is not _MISSING:
                block.expertise_dir = expertise_dir
            elif expertise_dir_id is not _MISSING:
                block.expertise_dir_id = expertise_dir_id
            if expertise_direction is not _MISSING:
                block.expertise_direction = expertise_direction
            elif expertise_direction_id is not _MISSING:
                block.expertise_direction_id = expertise_direction_id
            block.save()
            created = True
    if not created and block is not None and not is_system_dsc_code(block.code):
        changed = []
        if short_name is not _MISSING and short_name and block.short_name != short_name:
            block.short_name = str(short_name)[:64]
            changed.append("short_name")
        if short_name_ru is not _MISSING and block.short_name_ru != (short_name_ru or ""):
            block.short_name_ru = str(short_name_ru or "")[:128]
            changed.append("short_name_ru")
        if accounting_type is not _MISSING:
            mapped = classifier_accounting_type(accounting_type)
            if block.accounting_type != mapped:
                block.accounting_type = mapped
                changed.append("accounting_type")
        if expertise_dir is not _MISSING and block.expertise_dir != expertise_dir:
            block.expertise_dir = expertise_dir
            changed.append("expertise_dir")
        elif expertise_dir_id is not _MISSING and block.expertise_dir_id != expertise_dir_id:
            block.expertise_dir_id = expertise_dir_id
            changed.append("expertise_dir")
        if expertise_direction is not _MISSING and block.expertise_direction != expertise_direction:
            block.expertise_direction = expertise_direction
            changed.append("expertise_direction")
        elif (
            expertise_direction_id is not _MISSING
            and block.expertise_direction_id != expertise_direction_id
        ):
            block.expertise_direction_id = expertise_direction_id
            changed.append("expertise_direction")
        if changed:
            block.save(update_fields=changed)
    kwargs["service_block"] = block
    kwargs["code"] = block.code
    return kwargs


def ensure_system_dsc_section(product):
    if not product or not getattr(product, "pk", None):
        return None
    if getattr(product, "is_product_group", False):
        return None

    with transaction.atomic():
        sections = list(
            TypicalSection.objects.select_for_update()
            .filter(product=product)
            .order_by("position", "id")
        )
        section = next((item for item in sections if is_system_dsc_code(item.code)), None)
        block = ensure_dsc_service_block()
        names = {
            "name_en": block.name_en or SYSTEM_DSC_SECTION_DEFAULTS["name_en"],
            "name_ru": block.name_ru or SYSTEM_DSC_SECTION_DEFAULTS["name_ru"],
        }
        if section is None:
            section = TypicalSection.objects.create(
                product=product,
                position=0,
                service_block=block,
                code=block.code,
                name_en=names["name_en"],
                name_ru=names["name_ru"],
                exclude_from_tkp_autofill=False,
                is_system=True,
            )
            sections.append(section)
        else:
            changed_fields = []
            if section.service_block_id != block.pk:
                section.service_block = block
                changed_fields.append("service_block")
            if section.code != block.code:
                section.code = block.code
                changed_fields.append("code")
            for field, value in names.items():
                if getattr(section, field) != value:
                    setattr(section, field, value)
                    changed_fields.append(field)
            if not section.is_system:
                section.is_system = True
                changed_fields.append("is_system")
            if section.exclude_from_tkp_autofill:
                section.exclude_from_tkp_autofill = False
                changed_fields.append("exclude_from_tkp_autofill")
            if changed_fields:
                section.save(update_fields=[*changed_fields, "updated_at"])

        ordered = [section] + [item for item in sections if item.pk != section.pk]
        changed_positions = []
        for index, item in enumerate(ordered, start=1):
            if item.position != index:
                item.position = index
                changed_positions.append(item)
        if changed_positions:
            TypicalSection.objects.bulk_update(changed_positions, ["position"])
            from .cache import schedule_policy_cache_invalidation

            schedule_policy_cache_invalidation(
                using=product._state.db or "default",
            )

    section.refresh_from_db()
    return section


def ensure_system_dsc_sections_for_all_products():
    for product in Product.objects.filter(is_product_group=False).order_by("position", "id"):
        ensure_system_dsc_section(product)


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


class ReportStructure(models.Model):
    product = models.ForeignKey(
        Product,
        verbose_name="Продукт",
        on_delete=models.CASCADE,
        related_name="report_structures",
    )
    level = models.PositiveSmallIntegerField(
        "Уровень",
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(9)],
    )
    code = models.CharField("Код", max_length=255, blank=True, default="")
    name = models.TextField("Наименование отчета, раздела (подраздела)", blank=True, default="")
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Типовая структура отчета"
        verbose_name_plural = "Типовая структура отчета"
        ordering = ["product_id", "position", "id"]

    def __str__(self):
        label = self.code or self.name
        return f"{self.product.short_name} / {label}"


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
    class TermUnit(models.TextChoices):
        DAYS = "days", "дн."
        WEEKS = "weeks", "нед."
        MONTHS = "months", "мес."

    product = models.ForeignKey(
        Product,
        verbose_name="Продукт",
        on_delete=models.CASCADE,
        related_name="typical_service_terms",
    )
    source_data_weeks = models.DecimalField(
        "Сроки предоставления исходных данных",
        max_digits=6,
        decimal_places=1,
        default=0,
        validators=[MinValueValidator(0)],
    )
    source_data_term_unit = models.CharField(
        "Единица срока предоставления исходных данных",
        max_length=10,
        choices=TermUnit.choices,
        default=TermUnit.WEEKS,
    )
    preliminary_report_months = models.DecimalField(
        "Срок подготовки Предварительного отчёта",
        max_digits=6,
        decimal_places=1,
        default=0,
        validators=[MinValueValidator(0)],
    )
    preliminary_report_term_unit = models.CharField(
        "Единица срока подготовки Предварительного отчёта",
        max_length=10,
        choices=TermUnit.choices,
        default=TermUnit.MONTHS,
    )
    final_report_weeks = models.DecimalField(
        "Срок подготовки Итогового отчёта",
        max_digits=6,
        decimal_places=1,
        default=0,
        validators=[MinValueValidator(0)],
    )
    final_report_term_unit = models.CharField(
        "Единица срока подготовки Итогового отчёта",
        max_length=10,
        choices=TermUnit.choices,
        default=TermUnit.WEEKS,
    )
    gantt_data = models.JSONField(
        "Диаграмма Гантта",
        default=dict,
        blank=True,
    )
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Типовой срок оказания услуг"
        verbose_name_plural = "Типовые сроки оказания услуг"
        ordering = ["position", "id"]

    def __str__(self):
        return (
            f"{self.product.short_name} / "
            f"{self.source_data_display} / "
            f"{self.preliminary_report_display} / "
            f"{self.final_report_display}"
        )

    @property
    def source_data_display(self):
        return self._format_term_display(self.source_data_weeks, self.source_data_term_unit)

    @property
    def source_data_value_display(self):
        return self.format_term_value(self.source_data_weeks, self.source_data_term_unit)

    @property
    def preliminary_report_months_display(self):
        return format(self.preliminary_report_months, ".1f").replace(".", ",")

    @property
    def preliminary_report_display(self):
        return self._format_term_display(self.preliminary_report_months, self.preliminary_report_term_unit)

    @property
    def preliminary_report_value_display(self):
        return self.format_term_value(self.preliminary_report_months, self.preliminary_report_term_unit)

    @property
    def final_report_display(self):
        return self._format_term_display(self.final_report_weeks, self.final_report_term_unit)

    @property
    def final_report_value_display(self):
        return self.format_term_value(self.final_report_weeks, self.final_report_term_unit)

    @classmethod
    def format_term_value(cls, value, unit):
        unit = unit if unit in cls.TermUnit.values else cls.TermUnit.WEEKS
        if unit == cls.TermUnit.DAYS:
            return str(int(value or 0))
        return format(value or 0, ".1f").replace(".", ",")

    @classmethod
    def _format_term_display(cls, value, unit):
        unit = unit if unit in cls.TermUnit.values else cls.TermUnit.WEEKS
        display_value = cls.format_term_value(value, unit)
        return f"{display_value} {dict(cls.TermUnit.choices).get(unit, '')}".strip()


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
    specialization_area = models.CharField(
        "Область специализации", max_length=512, blank=True, default=""
    )
    department = models.ForeignKey(
        "group_app.OrgUnit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="department_expertise_directions",
        verbose_name="Подразделение",
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

    def _managed_units(self):
        cached = getattr(self, "_managed_display_units", None)
        if cached is not None:
            return cached
        from group_app.expertise_management import display_units

        units = display_units(self)
        self._managed_display_units = units
        return units

    @property
    def department_display(self):
        from group_app.expertise_management import format_departments

        return format_departments(self._managed_units())

    @property
    def organization_display(self):
        """Компании подразделений, связанных с направлением в оргструктуре, с учётом режима."""
        from group_app.expertise_management import format_organizations

        return format_organizations(self._managed_units())

    @property
    def owner_display(self):
        if self.is_group_owner:
            return "Группа"
        owners = getattr(self, "_policy_owner_display_items", None)
        if owners is None:
            owners = self.owners.only("id", "short_name", "position").order_by("position", "id")
        names = [owner.short_name for owner in owners]
        return ", ".join(names) if names else ""


SERVICE_BLOCK_CODE_FORMAT_MESSAGE = "Код должен состоять ровно из трёх латинских букв."
SERVICE_BLOCK_CODE_UNIQUE_MESSAGE = "Блок услуг с таким кодом уже существует (без учёта регистра)."


def normalize_service_block_code(value):
    """Код хранится в верхнем регистре, поэтому уникальность в БД не зависит от регистра."""
    return str(value or "").strip().upper()


class ServiceBlockClassifier(models.Model):
    """Единый классификатор типовых блоков услуг: источник кода и справочных полей раздела."""

    ACCOUNTING_TYPE_CHOICES = [
        ("Разделы", "Разделы"),
        ("Управление", "Управление"),
        ("Материалы", "Материалы"),
    ]

    # Ровно три латинские буквы (без цифр, пробелов и знаков).
    code_validator = RegexValidator(
        regex=r"^[A-Za-z]{3}$",
        message=SERVICE_BLOCK_CODE_FORMAT_MESSAGE,
    )

    code = models.CharField(
        "Код",
        max_length=64,
        unique=True,
        validators=[code_validator],
        help_text="Ровно три латинские буквы; сравнение без учёта регистра.",
        error_messages={
            "unique": SERVICE_BLOCK_CODE_UNIQUE_MESSAGE,
            "max_length": SERVICE_BLOCK_CODE_FORMAT_MESSAGE,
        },
    )
    short_name = models.CharField("Краткое имя EN", max_length=64)
    short_name_ru = models.CharField("Краткое имя RU", max_length=128, blank=True, default="")
    name_en = models.CharField(
        "Наименование раздела (услуги) на английском языке",
        max_length=255,
        blank=True,
        default="",
    )
    name_ru = models.CharField(
        "Наименование раздела (услуги) на русском языке",
        max_length=255,
        blank=True,
        default="",
    )
    accounting_type = models.CharField(
        "Тип учета", max_length=128, choices=ACCOUNTING_TYPE_CHOICES, default="Разделы"
    )
    expertise_dir = models.ForeignKey(
        "policy_app.ExpertiseDirection",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_block_classifiers",
        verbose_name="Экспертиза",
    )
    expertise_direction = models.ForeignKey(
        "group_app.OrgUnit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_block_classifiers",
        verbose_name="Подразделение",
    )
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Классификатор типовых блоков услуг"
        verbose_name_plural = "Классификатор типовых блоков услуг"

    def __str__(self):
        return f"{self.code} {self.short_name}".strip()

    @property
    def department_display(self):
        direction = self.expertise_dir if self.expertise_dir_id else None
        return direction.department_display if direction is not None else ""

    @property
    def organization_display(self):
        direction = self.expertise_dir if self.expertise_dir_id else None
        return direction.organization_display if direction is not None else ""

    def clean(self):
        self.code = normalize_service_block_code(self.code)
        super().clean()

    def save(self, *args, **kwargs):
        stored_code = None
        if self.pk:
            stored_code = (
                type(self).objects.filter(pk=self.pk).values_list("code", flat=True).first()
            )
        self.code = stored_code or normalize_service_block_code(self.code)
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = list(set(update_fields) | {"code"})
        super().save(*args, **kwargs)


class ServiceBlockClassifierSpecialty(models.Model):
    """Упорядоченный исполнитель блока. Не записывается в типовые разделы."""

    classifier = models.ForeignKey(
        ServiceBlockClassifier,
        on_delete=models.CASCADE,
        related_name="ranked_specialties",
    )
    specialty = models.ForeignKey(
        "experts_app.ExpertSpecialty",
        on_delete=models.CASCADE,
        related_name="service_block_classifier_links",
    )
    rank = models.PositiveIntegerField("Ранг", default=1)

    class Meta:
        ordering = ["rank", "id"]
        unique_together = [("classifier", "specialty")]
        verbose_name = "Специальность блока услуг"
        verbose_name_plural = "Специальности блока услуг"

    def __str__(self):
        return f"{self.classifier} — {self.specialty} (#{self.rank})"


class _TypicalSectionSpecialtyManager:
    """Пишет исполнителя в блок классификатора, к которому привязан раздел."""

    def create(self, section=None, specialty=None, rank=1, **kwargs):
        if section is None and kwargs.get("section_id"):
            section = TypicalSection.objects.get(pk=kwargs["section_id"])
        if section is None or not getattr(section, "service_block_id", None):
            raise ValidationError("Раздел без блока классификатора не хранит исполнителя.")
        specialty_id = kwargs.get("specialty_id")
        if specialty is not None:
            specialty_id = getattr(specialty, "pk", specialty)
        return ServiceBlockClassifierSpecialty.objects.create(
            classifier_id=section.service_block_id,
            specialty_id=specialty_id,
            rank=kwargs.get("rank", rank),
        )

    def filter(self, *args, **kwargs):
        if "section" in kwargs:
            section = kwargs.pop("section")
            kwargs["classifier_id"] = section.service_block_id
        if "section_id" in kwargs:
            section = TypicalSection.objects.get(pk=kwargs.pop("section_id"))
            kwargs["classifier_id"] = section.service_block_id
        if "section_id__in" in kwargs:
            kwargs["classifier_id__in"] = list(
                TypicalSection.objects.filter(pk__in=kwargs.pop("section_id__in")).values_list(
                    "service_block_id",
                    flat=True,
                )
            )
        return ServiceBlockClassifierSpecialty.objects.filter(*args, **kwargs)

    def all(self):
        return ServiceBlockClassifierSpecialty.objects.all()


class TypicalSectionSpecialty:
    """Совместимость для кода, который создаёт исполнителя через раздел.

    Строка хранится в ServiceBlockClassifierSpecialty выбранного блока.
    """

    objects = _TypicalSectionSpecialtyManager()


def ensure_dsc_service_block():
    """Одна строка классификатора для системного раздела DSC."""
    from django.db.models import Max

    code = normalize_service_block_code(SYSTEM_DSC_SECTION_CODE)
    block = ServiceBlockClassifier.objects.filter(code=code).first()
    if block is not None:
        changed = []
        if not block.name_en:
            block.name_en = SYSTEM_DSC_SECTION_DEFAULTS["name_en"]
            changed.append("name_en")
        if not block.name_ru:
            block.name_ru = SYSTEM_DSC_SECTION_DEFAULTS["name_ru"]
            changed.append("name_ru")
        if changed:
            block.save(update_fields=changed)
        return block
    position = (ServiceBlockClassifier.objects.aggregate(m=Max("position"))["m"] or 0) + 1
    block = ServiceBlockClassifier.objects.create(
        code=code,
        short_name=SYSTEM_DSC_SECTION_DEFAULTS["short_name"],
        short_name_ru=SYSTEM_DSC_SECTION_DEFAULTS["short_name_ru"],
        name_en=SYSTEM_DSC_SECTION_DEFAULTS["name_en"],
        name_ru=SYSTEM_DSC_SECTION_DEFAULTS["name_ru"],
        accounting_type="Разделы",
        position=position,
    )
    return block


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
    def display_specialties(self):
        prefetched = getattr(self, "_policy_display_specialties", None)
        if prefetched is not None:
            return prefetched
        return self.specialties.select_related("expertise_dir").order_by("position", "id")

    @property
    def expertise_direction_display(self):
        labels = []
        seen = set()
        for specialty in self.display_specialties:
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