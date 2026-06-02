from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
import uuid

from group_app.models import GroupMember
from projects_app.models import Performer


def _refresh_linked_project_registration_uids(contract_registration_ids):
    contract_registration_ids = [pk for pk in contract_registration_ids if pk]
    if not contract_registration_ids:
        return
    from projects_app.models import ProjectRegistration

    registrations = list(
        ProjectRegistration.objects
        .select_related("group_member", "contract_project_registration")
        .filter(contract_project_registration_id__in=contract_registration_ids)
    )
    if registrations:
        ProjectRegistration._bulk_refresh_short_uids(registrations)


CONTRACT_TYPE_CHOICES = [
    ("gph", "ГПХ Договор гражданско-правового характера"),
    ("smz", "СМЗ Договор с самозанятым"),
]

PARTY_CHOICES = [
    ("individual", "ФЗЛ Физлицо"),
    ("legal_entity", "ЮРЛ Юрлицо"),
    ("ip", "ИП Индивидуальный предприниматель"),
]


class ContractProjectRegistration(models.Model):
    class AgreementType(models.TextChoices):
        MAIN = "MAIN", "Основной договор"
        ADDENDUM = "ADDENDUM", "Допсоглашение"

    class PreliminaryReportTermUnit(models.TextChoices):
        MONTHS = "months", "мес."
        DAYS = "days", "дн."
        WEEKS = "weeks", "нед."

    class SourceDataTermUnit(models.TextChoices):
        DAYS = "days", "дн."
        WEEKS = "weeks", "нед."
        MONTHS = "months", "мес."

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
    contract_number = models.CharField("Номер договора", max_length=100, blank=True, default="")
    contract_date = models.DateField("Дата договора", null=True, blank=True)
    stage_payloads_json = models.JSONField("Данные этапов договора", default=list, blank=True)
    proposal_registration = models.ForeignKey(
        "proposals_app.ProposalRegistration",
        verbose_name="ТКП ID",
        on_delete=models.SET_NULL,
        related_name="linked_contract_project_registrations",
        null=True,
        blank=True,
    )
    group = models.CharField("Группа", max_length=2, default="RU", db_index=True)
    group_member = models.ForeignKey(
        "group_app.GroupMember",
        verbose_name="Группа",
        on_delete=models.PROTECT,
        related_name="contract_project_registrations",
        null=True,
        blank=True,
    )
    agreement_sequence = models.PositiveIntegerField(
        "№ этапа-продукта",
        default=0,
        editable=False,
        db_index=True,
    )
    agreement_type = models.CharField(
        "Вид соглашения",
        max_length=20,
        choices=AgreementType.choices,
        default=AgreementType.MAIN,
        db_index=True,
    )
    agreement_number = models.CharField("№ соглашения", max_length=100, blank=True)
    type = models.ForeignKey(
        "policy_app.Product",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="contract_project_registrations",
        verbose_name="Тип",
    )
    products = models.ManyToManyField(
        "policy_app.Product",
        through="ContractProjectRegistrationProduct",
        related_name="ranked_contract_project_registrations",
        verbose_name="Тип",
        blank=True,
    )
    name = models.CharField("Название", max_length=255)
    short_uid = models.CharField(
        "Договор ID",
        max_length=32,
        unique=True,
        db_index=True,
        blank=True,
        editable=False,
    )

    STATUS_CHOICES = [
        ("Разрабатывается проект договора", "Разрабатывается проект договора"),
        ("Отправлен проект договора", "Отправлен проект договора"),
        ("Договор подписан факсимиле", "Договор подписан факсимиле"),
        ("Договор подписан ЭЦП", "Договор подписан ЭЦП"),
        ("Договор в 2 экз. отправлен почтой", "Договор в 2 экз. отправлен почтой"),
        ("Договор в 2 экз. получен клиентом", "Договор в 2 экз. получен клиентом"),
        ("Договор с экз. IMCM отправлен почтой", "Договор с экз. IMCM отправлен почтой"),
        ("Договор с экз. IMCM получен", "Договор с экз. IMCM получен"),
    ]
    status = models.CharField(
        "Статус",
        max_length=50,
        choices=STATUS_CHOICES,
        default="Разрабатывается проект договора",
    )
    year = models.PositiveIntegerField("Год", null=True, blank=True)
    evaluation_date = models.DateField("Дата оценки", null=True, blank=True)
    source_data_term = models.DecimalField(
        "Исходные данные",
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    source_data_term_unit = models.CharField(
        "Единица срока предоставления исходных данных",
        max_length=10,
        choices=SourceDataTermUnit.choices,
        default=SourceDataTermUnit.WEEKS,
    )
    source_data_date = models.DateField("Дата предоставления данных", null=True, blank=True)
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

    country = models.ForeignKey(
        "classifiers_app.OKSMCountry",
        verbose_name="Страна",
        on_delete=models.SET_NULL,
        related_name="contract_project_registrations",
        null=True,
        blank=True,
    )
    customer = models.CharField("Заказчик", max_length=255, blank=True)
    identifier = models.CharField("Идентификатор", max_length=64, blank=True, default="")
    registration_number = models.CharField("Регистрационный номер", max_length=100, blank=True)
    registration_region = models.CharField("Регион", max_length=255, blank=True, default="")
    registration_date = models.DateField("Дата регистрации", null=True, blank=True)
    asset_owner = models.CharField("Владелец активов", max_length=255, blank=True, default="")
    asset_owner_matches_customer = models.BooleanField("Совпадает с Заказчиком", default=True)
    asset_owner_country = models.ForeignKey(
        "classifiers_app.OKSMCountry",
        verbose_name="Страна владельца активов",
        on_delete=models.SET_NULL,
        related_name="contract_project_asset_owner_registrations",
        null=True,
        blank=True,
    )
    asset_owner_identifier = models.CharField("Идентификатор владельца активов", max_length=64, blank=True, default="")
    asset_owner_registration_number = models.CharField(
        "Регистрационный номер владельца активов",
        max_length=100,
        blank=True,
        default="",
    )
    asset_owner_region = models.CharField("Регион владельца активов", max_length=255, blank=True, default="")
    asset_owner_registration_date = models.DateField("Дата регистрации владельца активов", null=True, blank=True)
    project_manager = models.CharField("Руководитель проекта", max_length=255, blank=True)
    project_manager_prs_id = models.CharField("ID-PRS руководителя проекта", max_length=32, blank=True, default="")

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Проект договора с клиентом"
        verbose_name_plural = "Проекты договоров с клиентами"

    def __str__(self):
        base = f"{self.formatted_number}{self.group_alpha2}"
        agreement = self.get_agreement_type_display()
        suffix = f" №{self.agreement_number}" if self.agreement_number else ""
        return f"{base} — {agreement}{suffix} — {self.name}"

    @property
    def formatted_number(self):
        return f"{int(self.number or 0):04d}"

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
        registrations = list(
            cls.objects
            .select_related("group_member", "proposal_registration")
            .filter(group_member_id__in=group_member_ids)
        )
        if registrations:
            cls._bulk_refresh_short_uids(registrations)

    @classmethod
    def _bulk_refresh_short_uids(cls, registrations):
        to_refresh = []
        for registration in registrations:
            new_uid = registration._build_short_uid()
            if registration.short_uid == new_uid:
                continue
            registration.short_uid = f"tmp{registration.pk}{uuid.uuid4().hex[:8]}"
            to_refresh.append((registration, new_uid))

        if not to_refresh:
            return

        with transaction.atomic():
            cls.objects.bulk_update([item[0] for item in to_refresh], ["short_uid"])
            for registration, new_uid in to_refresh:
                registration.short_uid = new_uid
            cls.objects.bulk_update([item[0] for item in to_refresh], ["short_uid"])
        _refresh_linked_project_registration_uids([item[0].pk for item in to_refresh])

    @classmethod
    def refresh_number_sequences(cls, numbers):
        normalized_numbers = []
        for number in numbers:
            if number is None:
                continue
            try:
                normalized_numbers.append(int(number))
            except (TypeError, ValueError):
                continue
        if not normalized_numbers:
            return

        registrations = list(
            cls.objects
            .select_related("group_member", "proposal_registration")
            .filter(number__in=set(normalized_numbers))
            .order_by("number", "position", "id")
        )
        if not registrations:
            return

        by_number = {}
        for registration in registrations:
            by_number.setdefault(registration.number, []).append(registration)

        to_refresh = []
        for group in by_number.values():
            total = len(group)
            for index, registration in enumerate(group, start=1):
                sequence = 0 if total == 1 else index
                current_sequence = int(registration.agreement_sequence or 0)
                registration.agreement_sequence = sequence
                new_uid = registration._build_short_uid()
                if current_sequence == sequence and registration.short_uid == new_uid:
                    continue
                registration.short_uid = f"tmp{registration.pk}{uuid.uuid4().hex[:8]}"
                to_refresh.append((registration, sequence, new_uid))

        if not to_refresh:
            return

        with transaction.atomic():
            cls.objects.bulk_update([item[0] for item in to_refresh], ["short_uid"])
            for registration, sequence, new_uid in to_refresh:
                registration.agreement_sequence = sequence
                registration.short_uid = new_uid
            cls.objects.bulk_update(
                [item[0] for item in to_refresh],
                ["agreement_sequence", "short_uid"],
            )
        _refresh_linked_project_registration_uids([item[0].pk for item in to_refresh])

    def save(self, *args, **kwargs):
        old_number = None
        old_position = None
        if self.pk:
            original = (
                ContractProjectRegistration.objects
                .filter(pk=self.pk)
                .values("number", "position")
                .first()
            )
            if original:
                old_number = original["number"]
                old_position = original["position"]
        member = self._resolved_group_member()
        if member:
            self.group = member.country_alpha2 or self.group
        if self.agreement_sequence is None or not self.pk:
            self.agreement_sequence = self._build_agreement_sequence()
        elif self._needs_agreement_sequence_refresh():
            self.agreement_sequence = self._build_agreement_sequence()
        if (
            not self.agreement_number
            and self.group_alpha2 == "RU"
            and self.agreement_type == self.AgreementType.MAIN
        ):
            self.agreement_number = f"IMCM/{self.number}"
        if not self.short_uid or self._needs_uid_refresh():
            self.short_uid = self._build_short_uid()
            update_fields = kwargs.get("update_fields")
            if update_fields is not None and "short_uid" not in update_fields:
                kwargs["update_fields"] = set(update_fields) | {"short_uid"}
        super().save(*args, **kwargs)
        update_fields = kwargs.get("update_fields")
        should_refresh_sequences = update_fields is None or bool(
            {"number", "position", "group", "group_member", "agreement_sequence", "short_uid"}
            & set(update_fields)
        )
        if should_refresh_sequences and (old_number != self.number or old_position != self.position or old_number is None):
            self.refresh_number_sequences([old_number, self.number])

    def _needs_uid_refresh(self):
        if not self.pk:
            return True
        orig = (
            ContractProjectRegistration.objects
            .filter(pk=self.pk)
            .values("number", "group", "group_member_id", "proposal_registration_id", "sub_number")
            .first()
        )
        return (
            not orig
            or orig["number"] != self.number
            or orig["group"] != self.group
            or orig["group_member_id"] != self.group_member_id
            or orig["proposal_registration_id"] != self.proposal_registration_id
            or orig["sub_number"] != self.sub_number
        )

    def _needs_agreement_sequence_refresh(self):
        if not self.pk:
            return True
        orig = ContractProjectRegistration.objects.filter(pk=self.pk).values("number", "position").first()
        return not orig or orig["number"] != self.number or orig["position"] != self.position

    def _build_agreement_sequence(self):
        siblings = list(
            ContractProjectRegistration.objects
            .filter(number=self.number)
            .exclude(pk=self.pk)
            .order_by("position", "id")
            .values_list("position", "id")
        )
        if not siblings:
            return 0
        if not self.pk:
            return len(siblings) + 1
        current_key = (self.position or 0, self.pk)
        earlier = sum(1 for position, pk in siblings if (position or 0, pk) < current_key)
        return earlier + 1

    def _build_short_uid(self):
        proposal_sequence = 0
        if self.proposal_registration_id:
            proposal = getattr(self, "proposal_registration", None)
            proposal_sequence = int(getattr(proposal, "sub_number", 0) or 0)
        return f"{self.formatted_number}{proposal_sequence}{int(self.sub_number or 0)}{self.group_order_number}{self.group_alpha2}"

    def _ordered_product_links(self):
        prefetched = getattr(self, "_prefetched_objects_cache", {})
        if "product_links" in prefetched:
            return list(prefetched["product_links"])
        if not self.pk:
            return []
        return list(
            self.product_links.select_related("product").order_by("rank", "id")
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
    def type_short_names(self):
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
        return "-".join(self.type_short_names)

    @property
    def primary_product(self):
        products = self.ordered_products()
        return products[0] if products else None


class ContractProjectRegistrationProduct(models.Model):
    registration = models.ForeignKey(
        ContractProjectRegistration,
        on_delete=models.CASCADE,
        related_name="product_links",
        verbose_name="Проект договора с клиентом",
    )
    product = models.ForeignKey(
        "policy_app.Product",
        on_delete=models.PROTECT,
        related_name="contract_project_registration_links",
        verbose_name="Продукт",
    )
    rank = models.PositiveIntegerField("Ранг", default=1)

    class Meta:
        ordering = ["rank", "id"]
        verbose_name = "Продукт проекта договора"
        verbose_name_plural = "Продукты проектов договоров"

    def __str__(self):
        return f"{self.registration.short_uid} — {self.product.short_name} (#{self.rank})"


def _sync_contract_project_registration_primary_product(registration_id):
    registration = (
        ContractProjectRegistration.objects
        .select_related("type")
        .prefetch_related("product_links__product")
        .filter(pk=registration_id)
        .first()
    )
    if not registration:
        return
    primary = registration.primary_product
    primary_id = getattr(primary, "pk", None)
    if registration.type_id != primary_id:
        ContractProjectRegistration.objects.filter(pk=registration.pk).update(type_id=primary_id)


@receiver(post_save, sender=ContractProjectRegistrationProduct)
def sync_contract_project_registration_products_after_save(sender, instance, **kwargs):
    _sync_contract_project_registration_primary_product(instance.registration_id)


@receiver(post_delete, sender=ContractProjectRegistrationProduct)
def sync_contract_project_registration_products_after_delete(sender, instance, **kwargs):
    if instance.registration_id:
        _sync_contract_project_registration_primary_product(instance.registration_id)


@receiver(post_delete, sender=ContractProjectRegistration)
def refresh_contract_project_registration_sequences_after_delete(sender, instance, **kwargs):
    ContractProjectRegistration.refresh_number_sequences([instance.number])


@receiver(post_save, sender=ContractProjectRegistration)
def refresh_linked_project_registration_uids_after_contract_save(sender, instance, **kwargs):
    _refresh_linked_project_registration_uids([instance.pk])


class ContractTemplate(models.Model):
    group_member = models.ForeignKey(
        "group_app.GroupMember",
        verbose_name="Группа",
        on_delete=models.SET_NULL,
        related_name="contract_templates",
        null=True,
    )
    group_members = models.ManyToManyField(
        "group_app.GroupMember",
        verbose_name="Группы",
        related_name="contract_template_sets",
        blank=True,
    )
    product = models.ForeignKey(
        "policy_app.Product",
        verbose_name="Продукт",
        on_delete=models.SET_NULL,
        related_name="contract_templates",
        null=True,
        blank=True,
    )
    products = models.ManyToManyField(
        "policy_app.Product",
        verbose_name="Продукты",
        related_name="contract_template_sets",
        blank=True,
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


class ContractReturnComment(models.Model):
    class AuthorRole(models.TextChoices):
        LAWYER = "lawyer", "Юрист"
        EXPERT = "expert", "Эксперт"
        OTHER = "other", "Другое"

    performer = models.ForeignKey(
        Performer,
        verbose_name="Исполнитель договора",
        on_delete=models.CASCADE,
        related_name="contract_return_comments",
    )
    contract_batch_id = models.UUIDField("ID батча договора", null=True, blank=True, db_index=True)
    text = models.TextField("Комментарий")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Автор",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="contract_return_comments",
    )
    author_role = models.CharField(
        "Роль автора",
        max_length=16,
        choices=AuthorRole.choices,
        default=AuthorRole.OTHER,
        db_index=True,
    )
    created_at = models.DateTimeField("Дата создания", auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = "Комментарий возврата договора"
        verbose_name_plural = "Комментарии возврата договоров"

    def __str__(self):
        return f"{self.performer_id}:{self.get_author_role_display()}"


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
