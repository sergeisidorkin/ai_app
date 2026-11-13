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


class ProposalVersionError(Exception):
    """Новую версию ТКП нельзя создать, пока у этого ТКП ID есть черновик."""


class ProposalRegistration(models.Model):
    class ProposalKind(models.TextChoices):
        REGULAR = "regular", "Обычные"
        OWED_TO_US = "owed_to_us", "Должны нам"

    class ProposalDocumentKind(models.TextChoices):
        FINAL = "final", "Итоговое"
        PRELIMINARY = "preliminary", "Предварительное"

    class ProposalStatus(models.TextChoices):
        DRAFT = "draft", "Черновик"
        SENT = "sent", "Отправленное"
        COMPLETED = "completed", "Завершённое"
        POSTPONED = "postponed", "Отложенное"
        NOT_HELD = "not_held", "Несостоявшееся"

    DRAFT_STATUSES = frozenset({ProposalStatus.DRAFT})
    LOCKED_STATUSES = frozenset({
        ProposalStatus.SENT,
        ProposalStatus.COMPLETED,
        ProposalStatus.POSTPONED,
        ProposalStatus.NOT_HELD,
    })
    VERSION_DRAFT_ERROR = (
        "У этого ТКП ID уже есть черновик. Новую версию можно создать после отправки."
    )
    VERSION_CLONE_SKIP = frozenset({
        "docx_file_name",
        "docx_file_link",
        "docx_file_id",
        "pdf_file_name",
        "pdf_file_link",
        "pdf_file_id",
        "sent_date",
        "transfer_to_contract_date",
        "recipient",
        "recipient_country",
        "recipient_identifier",
        "recipient_registration_number",
        "recipient_registration_date",
        "recipient_identifier_record",
        "recipient_job_title",
        "contact_full_name",
        "contact_email",
    })

    class PreliminaryReportTermUnit(models.TextChoices):
        MONTHS = "months", "мес."
        DAYS = "days", "дн."
        WEEKS = "weeks", "нед."

    class FinalReportTermUnit(models.TextChoices):
        DAYS = "days", "дн."
        WEEKS = "weeks", "нед."
        MONTHS = "months", "мес."

    position = models.PositiveIntegerField(default=0, db_index=True, verbose_name="Позиция")
    number = models.PositiveIntegerField(
        verbose_name="Номер",
        validators=[MinValueValidator(0), MaxValueValidator(9999)],
    )
    sub_number = models.PositiveSmallIntegerField(
        "№",
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(9)],
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
        db_index=True,
        blank=True,
        editable=False,
    )
    version = models.PositiveIntegerField("Версия", default=1)
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
        "Категория",
        max_length=20,
        choices=ProposalKind.choices,
        default=ProposalKind.REGULAR,
        db_index=True,
    )
    document_kind = models.CharField(
        "Вид",
        max_length=20,
        choices=ProposalDocumentKind.choices,
        default=ProposalDocumentKind.FINAL,
        db_index=True,
    )
    status = models.CharField(
        "Статус",
        max_length=20,
        choices=ProposalStatus.choices,
        default=ProposalStatus.DRAFT,
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
    registration_region = models.CharField("Регион", max_length=255, blank=True, default="")
    identifier = models.CharField("Идентификатор", max_length=64, blank=True, default="")
    registration_number = models.CharField("Регистрационный номер", max_length=100, blank=True)
    registration_date = models.DateField("Дата регистрации", null=True, blank=True)
    customer_identifier_record = models.ForeignKey(
        "classifiers_app.BusinessEntityIdentifierRecord",
        verbose_name="Идентификатор заказчика",
        on_delete=models.SET_NULL,
        related_name="proposal_customer_registrations",
        null=True,
        blank=True,
    )
    asset_owner = models.CharField("Владелец активов", max_length=255, blank=True, default="")
    asset_owner_matches_customer = models.BooleanField("Совпадает с Заказчиком", default=True)
    asset_owner_country = models.ForeignKey(
        OKSMCountry,
        verbose_name="Страна владельца активов",
        on_delete=models.SET_NULL,
        related_name="proposal_asset_owner_registrations",
        null=True,
        blank=True,
    )
    asset_owner_region = models.CharField("Регион владельца активов", max_length=255, blank=True, default="")
    asset_owner_identifier = models.CharField("Идентификатор владельца активов", max_length=64, blank=True, default="")
    asset_owner_registration_number = models.CharField(
        "Регистрационный номер владельца активов", max_length=100, blank=True, default=""
    )
    asset_owner_registration_date = models.DateField("Дата регистрации владельца активов", null=True, blank=True)
    asset_owner_identifier_record = models.ForeignKey(
        "classifiers_app.BusinessEntityIdentifierRecord",
        verbose_name="Идентификатор владельца активов",
        on_delete=models.SET_NULL,
        related_name="proposal_asset_owner_registrations",
        null=True,
        blank=True,
    )
    proposal_project_name = models.TextField("Наименование ТКП (проекта)", blank=True, default="")
    service_sections_json = models.JSONField("Состав услуг: разделы", default=list, blank=True)
    service_sections_editor_state = models.JSONField("Состав услуг: состояние редактора", default=list, blank=True)
    purpose = models.TextField("Цель оказания услуг", blank=True, default="")
    service_composition = models.TextField("Состав услуг", blank=True, default="")
    service_composition_customer_tz = models.TextField("Состав услуг: ТЗ Заказчика", blank=True, default="")
    service_customer_tz_editor_state = models.JSONField(
        "Состав услуг: состояние редактора ТЗ Заказчика",
        default=dict,
        blank=True,
    )
    service_composition_mode = models.CharField("Режим состава услуг", max_length=20, blank=True, default="sections")
    commercial_totals_json = models.JSONField("Итоги коммерческого предложения", default=dict, blank=True)
    stage_payloads_json = models.JSONField("Данные этапов ТКП", default=list, blank=True)
    evaluation_date = models.DateField("Дата оценки", null=True, blank=True)
    service_term_months = models.DecimalField(
        "Предварительный отчёт",
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    preliminary_report_term_unit = models.CharField(
        "Единица срока подготовки Предварительного отчёта",
        max_length=10,
        choices=PreliminaryReportTermUnit.choices,
        default=PreliminaryReportTermUnit.MONTHS,
    )
    preliminary_report_date = models.DateField("Дата Предварительного отчёта", null=True, blank=True)
    final_report_term_weeks = models.DecimalField(
        "Итоговый отчёт",
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    final_report_term_unit = models.CharField(
        "Единица срока подготовки Итогового отчёта",
        max_length=10,
        choices=FinalReportTermUnit.choices,
        default=FinalReportTermUnit.WEEKS,
    )
    final_report_date = models.DateField("Дата Итогового отчёта", null=True, blank=True)
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
    docx_file_id = models.CharField(
        "Идентификатор DOCX в Nextcloud",
        max_length=64,
        blank=True,
        default="",
    )
    pdf_file_name = models.CharField("Наименование файла PDF", max_length=255, blank=True, default="")
    pdf_file_link = models.CharField("Ссылка на PDF", max_length=500, blank=True, default="")
    pdf_file_id = models.CharField(
        "Идентификатор PDF в Nextcloud",
        max_length=64,
        blank=True,
        default="",
    )
    proposal_workspace_disk_path = models.CharField(
        "Путь к рабочей папке ТКП в облаке",
        max_length=1024,
        blank=True,
        default="",
    )
    proposal_workspace_target_path = models.CharField(
        "Путь к рабочей папке ТКП у пользователя в Nextcloud",
        max_length=1024,
        blank=True,
        default="",
    )
    proposal_workspace_public_url = models.URLField(
        "Публичная ссылка на рабочую папку ТКП",
        max_length=500,
        blank=True,
        default="",
    )
    proposal_workspace_file_id = models.CharField(
        "Идентификатор рабочей папки ТКП в Nextcloud",
        max_length=64,
        blank=True,
        default="",
    )
    sent_date = models.CharField("Дата отправки", max_length=255, blank=True, default="")
    transfer_to_contract_date = models.CharField("Дата передачи для составления договора", max_length=255, blank=True, default="")
    recipient = models.CharField("Наименование организации (краткое)", max_length=255, blank=True, default="")
    recipient_country = models.ForeignKey(
        OKSMCountry,
        verbose_name="Страна",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="proposal_dispatch_recipients",
    )
    recipient_identifier = models.CharField("Идентификатор", max_length=64, blank=True, default="")
    recipient_registration_number = models.CharField("Регистрационный номер", max_length=100, blank=True, default="")
    recipient_registration_date = models.DateField("Дата регистрации", null=True, blank=True)
    recipient_identifier_record = models.ForeignKey(
        "classifiers_app.BusinessEntityIdentifierRecord",
        verbose_name="Идентификатор получателя",
        on_delete=models.SET_NULL,
        related_name="proposal_recipient_registrations",
        null=True,
        blank=True,
    )
    recipient_job_title = models.CharField("Должность", max_length=255, blank=True, default="")
    contact_full_name = models.CharField("ФИО", max_length=255, blank=True, default="")
    contact_email = models.CharField("Эл. почта", max_length=255, blank=True, default="")

    class Meta:
        app_label = "proposals_app"
        ordering = ["position", "id"]
        verbose_name = "ТКП"
        verbose_name_plural = "Реестр ТКП"
        constraints = [
            models.UniqueConstraint(
                fields=("number", "sub_number", "group_member", "version"),
                name="proposal_registration_identity_unique",
            ),
        ]

    def __str__(self):
        return f"{self.short_uid} — {self.get_kind_display()}"

    @property
    def formatted_number(self):
        return f"{int(self.number or 0):04d}"

    @property
    def version_display(self):
        return f"{int(self.version or 1):02d}"

    @property
    def is_content_locked(self):
        return self.status in self.LOCKED_STATUSES

    @classmethod
    def identity_siblings(cls, number, sub_number, group_member, *, exclude_pk=None):
        member_id = getattr(group_member, "pk", group_member)
        queryset = cls.objects.filter(number=number, sub_number=int(sub_number or 0))
        if member_id:
            queryset = queryset.filter(group_member_id=member_id)
        else:
            queryset = queryset.filter(group_member__isnull=True)
        if exclude_pk:
            queryset = queryset.exclude(pk=exclude_pk)
        return queryset

    def has_identity_siblings(self):
        if not self.pk:
            return False
        return self.identity_siblings(
            self.number,
            self.sub_number,
            self.group_member_id,
            exclude_pk=self.pk,
        ).exists()

    def create_next_version(self):
        with transaction.atomic():
            siblings = list(
                type(self)
                .identity_siblings(self.number, self.sub_number, self.group_member_id)
                .select_for_update()
            )
            if any(item.status in self.DRAFT_STATUSES for item in siblings):
                raise ProposalVersionError(self.VERSION_DRAFT_ERROR)
            next_version = max((int(item.version or 1) for item in siblings), default=0) + 1
            values = {}
            for field in self._meta.concrete_fields:
                if field.primary_key or field.name in self.VERSION_CLONE_SKIP or field.name in {"version", "status"}:
                    continue
                values[field.attname] = getattr(self, field.attname)
            clone = type(self)(**values)
            clone.version = next_version
            clone.status = self.ProposalStatus.DRAFT
            clone.save()
            self._clone_version_children(clone)
            return clone

    def _clone_version_children(self, clone):
        related_models = (
            ("product_links", ProposalRegistrationProduct),
            ("assets", ProposalAsset),
            ("legal_entities", ProposalLegalEntity),
            ("proposal_objects", ProposalObject),
            ("commercial_offers", ProposalCommercialOffer),
        )
        for related_name, model in related_models:
            copies = []
            for child in getattr(self, related_name).all():
                child_values = {"proposal_id": clone.pk}
                for field in child._meta.concrete_fields:
                    if field.primary_key or field.name == "proposal":
                        continue
                    child_values[field.attname] = getattr(child, field.attname)
                copies.append(model(**child_values))
            if copies:
                model.objects.bulk_create(copies)

    @property
    def contact_short_name(self):
        parts = [part for part in str(self.contact_full_name or "").strip().split() if part]
        if not parts:
            return ""
        last_name = parts[0]
        initials = "".join(f"{part[0]}." for part in parts[1:] if part)
        return f"{last_name} {initials}".strip()

    def _stored_dispatch_recipients(self):
        if not self.pk:
            return []
        prefetched = getattr(self, "_prefetched_objects_cache", {})
        if "dispatch_recipients" in prefetched:
            return list(prefetched["dispatch_recipients"])
        return list(self.dispatch_recipients.order_by("position", "id"))

    def legacy_dispatch_recipient(self):
        full_name = (self.contact_full_name or "").strip()
        email = (self.contact_email or "").strip()
        organization = (self.recipient or "").strip()
        job_title = (self.recipient_job_title or "").strip()
        has_contact = any(
            [
                full_name,
                email,
                organization,
                job_title,
                self.recipient_country_id,
                (self.recipient_identifier or "").strip(),
                (self.recipient_registration_number or "").strip(),
                self.recipient_registration_date,
            ]
        )
        if not has_contact:
            return None
        parts = [part for part in full_name.split() if part]
        return ProposalDispatchRecipient(
            role=ProposalDispatchRecipient.Role.TO,
            last_name=parts[0] if parts else "",
            first_name=parts[1] if len(parts) > 1 else "",
            middle_name=" ".join(parts[2:]) if len(parts) > 2 else "",
            email=email,
            organization_short_name=organization,
            country_id=self.recipient_country_id,
            identifier=self.recipient_identifier or "",
            registration_number=self.recipient_registration_number or "",
            registration_date=self.recipient_registration_date,
            identifier_record_id=self.recipient_identifier_record_id,
            job_title=job_title,
        )

    def dispatch_contact_rows(self):
        rows = self._stored_dispatch_recipients()
        if rows:
            return rows
        legacy = self.legacy_dispatch_recipient()
        if legacy is not None:
            return [legacy]
        return [ProposalDispatchRecipient(role=ProposalDispatchRecipient.Role.TO)]

    @property
    def dispatch_to_emails(self):
        emails = []
        seen = set()
        for row in self.dispatch_contact_rows():
            if getattr(row, "role", "") != ProposalDispatchRecipient.Role.TO:
                continue
            email = (getattr(row, "email", "") or "").strip()
            key = email.casefold()
            if not email or key in seen:
                continue
            seen.add(key)
            emails.append(email)
        return " ".join(emails)

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
            .values("number", "sub_number", "group", "group_member_id")
            .first()
        )
        return (
            not original
            or original["number"] != self.number
            or original["sub_number"] != self.sub_number
            or original["group"] != self.group
            or original["group_member_id"] != self.group_member_id
        )

    def _build_short_uid(self):
        return f"{self.formatted_number}{int(self.sub_number or 0)}{self.group_order_number}{self.group_alpha2}"

    def save(self, *args, **kwargs):
        member = self._resolved_group_member()
        if member:
            self.group = member.country_alpha2 or self.group
        if not self.short_uid or self._needs_uid_refresh():
            self.short_uid = self._build_short_uid()
        super().save(*args, **kwargs)

    def _ordered_product_links(self):
        prefetched = getattr(self, "_prefetched_objects_cache", {})
        if "product_links" in prefetched:
            return list(prefetched["product_links"])
        if not self.pk:
            return []
        return list(
            self.product_links.select_related("product", "product__group", "product_group").order_by("rank", "id")
        )

    def ordered_products(self):
        links = self._ordered_product_links()
        if links:
            return [link.product for link in links if getattr(link, "product_id", None)]
        return [self.type] if self.type else []

    @property
    def ordered_product_ids(self):
        return [product.pk for product in self.ordered_products() if getattr(product, "pk", None)]

    @property
    def product_rank_map(self):
        return {product_id: index for index, product_id in enumerate(self.ordered_product_ids, start=1)}

    @property
    def primary_product(self):
        products = self.ordered_products()
        return products[0] if products else None

    @property
    def last_product(self):
        products = self.ordered_products()
        return products[-1] if products else None

    @property
    def type_short_names(self):
        from policy_app.product_groups import grouped_type_short_names

        links = self._ordered_product_links()
        if links:
            return grouped_type_short_names(links)
        labels = []
        for product in self.ordered_products():
            label = (
                getattr(product, "short_name", "")
                or str(product or "")
            ).strip()
            if label:
                labels.append(label)
        return labels

    @property
    def type_short_display(self):
        """Цепочка коротких имён до трёх продуктов, дальше — «N этап/этапа/этапов»."""
        from projects_app.registration_summary import SUMMARY_TYPE_CHAIN_LIMIT, stage_count_label

        links = self._ordered_product_links()
        if links:
            count = sum(1 for link in links if getattr(link, "product_id", None))
        else:
            count = len(self.ordered_products())
        if count > SUMMARY_TYPE_CHAIN_LIMIT:
            return stage_count_label(count)
        return "-".join(self.type_short_names)


class ProposalDispatchRecipient(models.Model):
    class Role(models.TextChoices):
        TO = "to", "Кому"
        BCC = "bcc", "Скрытая копия"

    proposal = models.ForeignKey(
        ProposalRegistration,
        verbose_name="ТКП",
        on_delete=models.CASCADE,
        related_name="dispatch_recipients",
    )
    role = models.CharField("Роль", max_length=8, choices=Role.choices, default=Role.TO, db_index=True)
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)
    person = models.ForeignKey(
        "contacts_app.PersonRecord",
        verbose_name="Лицо",
        on_delete=models.SET_NULL,
        related_name="proposal_dispatch_recipients",
        null=True,
        blank=True,
    )
    email_record = models.ForeignKey(
        "contacts_app.EmailRecord",
        verbose_name="Эл. почта контакта",
        on_delete=models.SET_NULL,
        related_name="proposal_dispatch_recipients",
        null=True,
        blank=True,
    )
    position_record = models.ForeignKey(
        "contacts_app.PositionRecord",
        verbose_name="Должность контакта",
        on_delete=models.SET_NULL,
        related_name="proposal_dispatch_recipients",
        null=True,
        blank=True,
    )
    last_name = models.CharField("Фамилия", max_length=255, blank=True, default="")
    first_name = models.CharField("Имя", max_length=255, blank=True, default="")
    middle_name = models.CharField("Отчество", max_length=255, blank=True, default="")
    email = models.CharField("Эл. почта", max_length=254, blank=True, default="")
    organization_short_name = models.CharField(
        "Наименование организации (краткое)",
        max_length=512,
        blank=True,
        default="",
    )
    country = models.ForeignKey(
        OKSMCountry,
        verbose_name="Страна",
        on_delete=models.SET_NULL,
        related_name="dispatch_recipient_countries",
        null=True,
        blank=True,
    )
    identifier = models.CharField("Идентификатор", max_length=64, blank=True, default="")
    registration_number = models.CharField("Регистрационный номер", max_length=100, blank=True, default="")
    registration_date = models.DateField("Дата регистрации", null=True, blank=True)
    identifier_record = models.ForeignKey(
        "classifiers_app.BusinessEntityIdentifierRecord",
        verbose_name="Идентификатор организации",
        on_delete=models.SET_NULL,
        related_name="proposal_dispatch_recipient_rows",
        null=True,
        blank=True,
    )
    job_title = models.CharField("Должность", max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "proposals_app"
        ordering = ["position", "id"]
        verbose_name = "Адресат отправки ТКП"
        verbose_name_plural = "Адресаты отправки ТКП"

    def __str__(self):
        return f"{self.get_role_display()} {self.email}".strip()

    @property
    def contact_full_name(self):
        return " ".join(
            part
            for part in [self.last_name, self.first_name, self.middle_name]
            if (part or "").strip()
        ).strip()

    @property
    def contact_short_name(self):
        parts = [part for part in self.contact_full_name.split() if part]
        if not parts:
            return ""
        initials = "".join(f"{part[0]}." for part in parts[1:] if part)
        return f"{parts[0]} {initials}".strip()

    @property
    def registration_date_display(self):
        if not self.registration_date:
            return ""
        return self.registration_date.strftime("%d.%m.%Y")

    @property
    def autocomplete_selected_value(self):
        return "1" if self.identifier_record_id else "0"


def mirror_primary_dispatch_recipient(proposal):
    primary = (
        proposal.dispatch_recipients.filter(role=ProposalDispatchRecipient.Role.TO)
        .select_related("country", "identifier_record")
        .order_by("position", "id")
        .first()
    )
    if primary is None:
        proposal.contact_full_name = ""
        proposal.contact_email = ""
        proposal.recipient = ""
        proposal.recipient_country = None
        proposal.recipient_identifier = ""
        proposal.recipient_registration_number = ""
        proposal.recipient_registration_date = None
        proposal.recipient_identifier_record = None
        proposal.recipient_job_title = ""
    else:
        proposal.contact_full_name = primary.contact_full_name[:255]
        proposal.contact_email = (primary.email or "")[:255]
        proposal.recipient = (primary.organization_short_name or "")[:255]
        proposal.recipient_country = primary.country
        proposal.recipient_identifier = primary.identifier or ""
        proposal.recipient_registration_number = primary.registration_number or ""
        proposal.recipient_registration_date = primary.registration_date
        proposal.recipient_identifier_record = primary.identifier_record
        proposal.recipient_job_title = primary.job_title or ""
    proposal.save(
        update_fields=[
            "contact_full_name",
            "contact_email",
            "recipient",
            "recipient_country",
            "recipient_identifier",
            "recipient_registration_number",
            "recipient_registration_date",
            "recipient_identifier_record",
            "recipient_job_title",
        ]
    )


class ProposalRegistrationProduct(models.Model):
    proposal = models.ForeignKey(
        ProposalRegistration,
        on_delete=models.CASCADE,
        related_name="product_links",
        verbose_name="ТКП",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="proposal_registration_links",
        verbose_name="Продукт",
    )
    product_group = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="proposal_registration_member_links",
        verbose_name="Групповой продукт",
    )
    rank = models.PositiveIntegerField("Ранг", default=1)

    class Meta:
        app_label = "proposals_app"
        ordering = ["rank", "id"]
        verbose_name = "Продукт ТКП"
        verbose_name_plural = "Продукты ТКП"

    def __str__(self):
        return f"{self.proposal.short_uid} — {self.product.short_name} (#{self.rank})"


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
    identifier_record = models.ForeignKey(
        "classifiers_app.BusinessEntityIdentifierRecord",
        verbose_name="Идентификатор бизнес-сущности",
        on_delete=models.SET_NULL,
        related_name="proposal_asset_identifier_links",
        null=True,
        blank=True,
    )

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
    identifier_record = models.ForeignKey(
        "classifiers_app.BusinessEntityIdentifierRecord",
        verbose_name="Идентификатор бизнес-сущности",
        on_delete=models.SET_NULL,
        related_name="proposal_legal_entity_identifier_links",
        null=True,
        blank=True,
    )

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
    code = models.CharField("Код", max_length=100, blank=True, default="")
    merge_without_code = models.BooleanField("Объединять без учета кода", default=False)
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
        blank=True,
    )
    product = models.ForeignKey(
        "policy_app.Product",
        verbose_name="Продукт",
        on_delete=models.SET_NULL,
        related_name="proposal_templates",
        null=True,
        blank=True,
    )
    group_members = models.ManyToManyField(
        "group_app.GroupMember",
        verbose_name="Группы",
        related_name="proposal_template_sets",
        blank=True,
    )
    products = models.ManyToManyField(
        "policy_app.Product",
        verbose_name="Продукты",
        related_name="proposal_template_sets",
        blank=True,
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
    is_computed = models.BooleanField("Расчётное поле", default=False)
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
        if self.is_computed:
            return "Расчётное поле"
        if not (self.source_section and self.source_table and self.source_column):
            return ""
        from core.column_registry import COLUMN_REGISTRY

        sec = COLUMN_REGISTRY.get(self.source_section)
        if not sec:
            return ""
        tbl = sec["tables"].get(self.source_table)
        if not tbl and self.source_section == "proposals" and self.source_table == "service_goals_and_report_titles":
            tbl = COLUMN_REGISTRY.get("products", {}).get("tables", {}).get("service_goals_and_report_titles")
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
