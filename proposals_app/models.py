import sys
import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction

from classifiers_app.models import OKSMCountry, OKVCurrency
from group_app.models import GroupMember
from policy_app.models import Product


# Prevent duplicate imports via `proposals_app.models` and `ai_app.proposals_app.models`.
sys.modules.setdefault("proposals_app.models", sys.modules[__name__])
sys.modules.setdefault("ai_app.proposals_app.models", sys.modules[__name__])


class ProposalRegistration(models.Model):
    class ProposalKind(models.TextChoices):
        REGULAR = "regular", "Обычные"
        OWED_TO_US = "owed_to_us", "Должны нам"

    position = models.PositiveIntegerField(default=0, db_index=True, verbose_name="Позиция")
    number = models.PositiveIntegerField(
        verbose_name="Номер",
        validators=[MinValueValidator(3333), MaxValueValidator(9999)],
    )
    group = models.CharField("Группа", max_length=2, default="RU", db_index=True)
    group_member = models.ForeignKey(
        GroupMember,
        verbose_name="Группа",
        on_delete=models.PROTECT,
        related_name="proposal_registrations",
        null=True,
        blank=True,
    )
    short_uid = models.CharField(
        "ТКП ID",
        max_length=32,
        unique=True,
        db_index=True,
        blank=True,
        editable=False,
    )
    type = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="proposal_registrations",
        verbose_name="Тип",
    )
    name = models.CharField("Название", max_length=255, blank=True, default="")
    kind = models.CharField(
        "Вид",
        max_length=20,
        choices=ProposalKind.choices,
        default=ProposalKind.REGULAR,
        db_index=True,
    )
    year = models.PositiveIntegerField("Год", null=True, blank=True)
    customer = models.CharField("Заказчик", max_length=255, blank=True)
    country = models.ForeignKey(
        OKSMCountry,
        verbose_name="Страна",
        on_delete=models.SET_NULL,
        related_name="proposal_registrations",
        null=True,
        blank=True,
    )
    identifier = models.CharField("Идентификатор", max_length=64, blank=True, default="")
    registration_number = models.CharField("Регистрационный номер", max_length=100, blank=True)
    registration_date = models.DateField("Дата регистрации", null=True, blank=True)
    purpose = models.TextField("Цель оказания услуг", blank=True, default="")
    service_composition = models.TextField("Состав услуг", blank=True, default="")
    evaluation_date = models.DateField("Дата оценки", null=True, blank=True)
    service_term_months = models.DecimalField(
        "Срок оказания услуг, мес.",
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    preliminary_report_date = models.DateField("Дата предварительного отчёта", null=True, blank=True)
    final_report_date = models.DateField("Дата итогового отчёта", null=True, blank=True)
    report_languages = models.CharField("Языки отчёта", max_length=255, blank=True, default="")
    service_cost = models.DecimalField(
        "Стоимость услуг",
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    currency = models.ForeignKey(
        OKVCurrency,
        verbose_name="Валюта",
        on_delete=models.SET_NULL,
        related_name="proposal_registrations",
        null=True,
        blank=True,
    )
    advance_percent = models.DecimalField(
        "Размер предоплаты в процентах",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    advance_term_days = models.PositiveIntegerField("Срок предоплаты в календарных днях", null=True, blank=True)
    preliminary_report_percent = models.DecimalField(
        "Размер оплаты Предварительного отчёта в процентах",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    preliminary_report_term_days = models.PositiveIntegerField(
        "Срок оплаты Предварительного отчёта в календарных днях",
        null=True,
        blank=True,
    )
    final_report_percent = models.DecimalField(
        "Размер оплаты Итогового отчёта в процентах",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    final_report_term_days = models.PositiveIntegerField(
        "Срок оплаты Итогового отчёта в календарных днях",
        null=True,
        blank=True,
    )
    docx_file_name = models.CharField("Наименование файла DOCX", max_length=255, blank=True, default="")
    docx_file_link = models.CharField("Ссылка на DOCX", max_length=500, blank=True, default="")
    pdf_file_name = models.CharField("Наименование файла PDF", max_length=255, blank=True, default="")
    pdf_file_link = models.CharField("Ссылка на PDF", max_length=500, blank=True, default="")
    sent_date = models.CharField("Дата отправки", max_length=255, blank=True, default="")
    recipient = models.CharField("Получатель", max_length=255, blank=True, default="")
    contact_full_name = models.CharField("ФИО", max_length=255, blank=True, default="")
    contact_email = models.CharField("Эл. почта", max_length=255, blank=True, default="")

    class Meta:
        app_label = "proposals_app"
        ordering = ["position", "id"]
        verbose_name = "ТКП"
        verbose_name_plural = "Реестр ТКП"
        constraints = [
            models.UniqueConstraint(
                fields=("number", "group_member"),
                name="proposal_registration_identity_unique",
            ),
        ]

    def __str__(self):
        return f"{self.short_uid} — {self.get_kind_display()}"

    @property
    def group_alpha2(self):
        member = self._resolved_group_member()
        if member:
            return (member.country_alpha2 or "").strip().upper()
        return (self.group or "").strip().upper()

    @property
    def group_order_number(self):
        member = self._resolved_group_member()
        if member:
            return int(member.country_order_number or 0)
        return 0

    @property
    def group_display(self):
        member = self._resolved_group_member()
        if member:
            return member.group_code_label
        return self.group_alpha2

    def _resolved_group_member(self):
        if not self.group_member_id:
            return None
        cached = getattr(self, "_group_member_cache", None)
        if cached and cached.pk == self.group_member_id:
            return cached
        member = GroupMember.objects.filter(pk=self.group_member_id).first()
        self._group_member_cache = member
        return member

    @classmethod
    def refresh_short_uids_for_group_members(cls, group_member_ids):
        proposals = list(
            cls.objects.select_related("group_member").filter(group_member_id__in=group_member_ids)
        )
        if not proposals:
            return
        cls._bulk_refresh_short_uids(proposals)

    @classmethod
    def _bulk_refresh_short_uids(cls, proposals):
        to_refresh = []
        for proposal in proposals:
            new_uid = proposal._build_short_uid()
            if proposal.short_uid == new_uid:
                continue
            proposal.short_uid = f"tmp{proposal.pk}{uuid.uuid4().hex[:8]}"
            to_refresh.append((proposal, new_uid))

        if not to_refresh:
            return

        with transaction.atomic():
            cls.objects.bulk_update([item[0] for item in to_refresh], ["short_uid"])
            for proposal, new_uid in to_refresh:
                proposal.short_uid = new_uid
            cls.objects.bulk_update([item[0] for item in to_refresh], ["short_uid"])

    def _needs_uid_refresh(self):
        if not self.pk:
            return True
        original = (
            ProposalRegistration.objects.filter(pk=self.pk)
            .values("number", "group", "group_member_id")
            .first()
        )
        return (
            not original
            or original["number"] != self.number
            or original["group"] != self.group
            or original["group_member_id"] != self.group_member_id
        )

    def _build_short_uid(self):
        return f"{self.number}{self.group_order_number}{self.group_alpha2}"

    def save(self, *args, **kwargs):
        member = self._resolved_group_member()
        if member:
            self.group = member.country_alpha2 or self.group
        if not self.short_uid or self._needs_uid_refresh():
            self.short_uid = self._build_short_uid()
        super().save(*args, **kwargs)


class ProposalAsset(models.Model):
    proposal = models.ForeignKey(
        ProposalRegistration,
        on_delete=models.CASCADE,
        related_name="assets",
        verbose_name="ТКП",
    )
    position = models.PositiveIntegerField(default=0, db_index=True, verbose_name="Позиция")
    short_name = models.CharField("Наименование (краткое)", max_length=512, blank=True, default="")
    country = models.ForeignKey(
        OKSMCountry,
        verbose_name="Страна",
        on_delete=models.SET_NULL,
        related_name="proposal_assets",
        null=True,
        blank=True,
    )
    identifier = models.CharField("Идентификатор", max_length=255, blank=True, default="")
    registration_number = models.CharField("Регистрационный номер", max_length=255, blank=True, default="")
    registration_date = models.DateField("Дата регистрации", null=True, blank=True)

    class Meta:
        app_label = "proposals_app"
        ordering = ["position", "id"]
        verbose_name = "Актив ТКП"
        verbose_name_plural = "Активы ТКП"

    def __str__(self):
        return self.short_name or f"Актив ТКП #{self.pk}"


class ProposalLegalEntity(models.Model):
    proposal = models.ForeignKey(
        ProposalRegistration,
        on_delete=models.CASCADE,
        related_name="legal_entities",
        verbose_name="ТКП",
    )
    position = models.PositiveIntegerField(default=0, db_index=True, verbose_name="Позиция")
    asset_short_name = models.CharField("Наименование актива (краткое)", max_length=512, blank=True, default="")
    short_name = models.CharField("Наименование (краткое)", max_length=512, blank=True, default="")
    country = models.ForeignKey(
        OKSMCountry,
        verbose_name="Страна",
        on_delete=models.SET_NULL,
        related_name="proposal_legal_entities",
        null=True,
        blank=True,
    )
    identifier = models.CharField("Идентификатор", max_length=255, blank=True, default="")
    registration_number = models.CharField("Регистрационный номер", max_length=255, blank=True, default="")
    registration_date = models.DateField("Дата регистрации", null=True, blank=True)

    class Meta:
        app_label = "proposals_app"
        ordering = ["position", "id"]
        verbose_name = "Юрлицо ТКП"
        verbose_name_plural = "Юрлица ТКП"

    def __str__(self):
        return self.short_name or f"Юрлицо ТКП #{self.pk}"


class ProposalObject(models.Model):
    proposal = models.ForeignKey(
        ProposalRegistration,
        on_delete=models.CASCADE,
        related_name="proposal_objects",
        verbose_name="ТКП",
    )
    position = models.PositiveIntegerField(default=0, db_index=True, verbose_name="Позиция")
    legal_entity_short_name = models.CharField("Наименование юрлица (краткое)", max_length=512, blank=True, default="")
    short_name = models.CharField("Наименование объекта (краткое)", max_length=512, blank=True, default="")
    region = models.CharField("Регион", max_length=255, blank=True, default="")
    object_type = models.CharField("Тип", max_length=255, blank=True, default="")
    license = models.CharField("Лицензия", max_length=255, blank=True, default="")
    registration_date = models.DateField("Дата регистрации", null=True, blank=True)

    class Meta:
        app_label = "proposals_app"
        ordering = ["position", "id"]
        verbose_name = "Объект ТКП"
        verbose_name_plural = "Объекты ТКП"

    def __str__(self):
        return self.short_name or f"Объект ТКП #{self.pk}"


class ProposalCommercialOffer(models.Model):
    proposal = models.ForeignKey(
        ProposalRegistration,
        on_delete=models.CASCADE,
        related_name="commercial_offers",
        verbose_name="ТКП",
    )
    position = models.PositiveIntegerField(default=0, db_index=True, verbose_name="Позиция")
    specialist = models.CharField("Специалист", max_length=255, blank=True, default="")
    job_title = models.CharField("Должность", max_length=255, blank=True, default="")
    professional_status = models.CharField("Профессиональный статус", max_length=255, blank=True, default="")
    service_name = models.CharField("Услуги", max_length=255, blank=True, default="")
    rate_eur_per_day = models.DecimalField(
        "Ставка, евро / день",
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    asset_day_counts = models.JSONField("Количество дней", default=list, blank=True)
    total_eur_without_vat = models.DecimalField(
        "Итого, евро без НДС",
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )

    class Meta:
        app_label = "proposals_app"
        ordering = ["position", "id"]
        verbose_name = "Коммерческое предложение ТКП"
        verbose_name_plural = "Коммерческие предложения ТКП"

    def __str__(self):
        return self.specialist or f"Коммерческое предложение #{self.pk}"


class ProposalTemplate(models.Model):
    group_member = models.ForeignKey(
        "group_app.GroupMember",
        verbose_name="Группа",
        on_delete=models.SET_NULL,
        related_name="proposal_templates",
        null=True,
    )
    product = models.ForeignKey(
        "policy_app.Product",
        verbose_name="Продукт",
        on_delete=models.CASCADE,
        related_name="proposal_templates",
    )
    sample_name = models.CharField("Наименование образца", max_length=512)
    version = models.CharField("Версия", max_length=128, blank=True, default="")
    file = models.FileField("Файл", upload_to="proposal_templates/", blank=True, default="")
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "proposals_app"
        ordering = ["position", "id"]
        verbose_name = "Образец шаблона ТКП"
        verbose_name_plural = "Образцы шаблонов ТКП"

    def __str__(self):
        return self.sample_name


class ProposalVariable(models.Model):
    key = models.CharField("Переменная", max_length=255)
    description = models.CharField("Описание", max_length=512, blank=True, default="")
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)
    source_section = models.CharField("Раздел", max_length=50, blank=True, default="")
    source_table = models.CharField("Таблица", max_length=50, blank=True, default="")
    source_column = models.CharField("Столбец", max_length=100, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "proposals_app"
        ordering = ["position", "id"]
        verbose_name = "Переменная шаблона ТКП"
        verbose_name_plural = "Переменные шаблонов ТКП"

    @property
    def binding_display(self):
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
