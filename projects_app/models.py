from django.conf import settings
from django.db import models, transaction
from django.core.validators import MinValueValidator, MaxValueValidator
from policy_app.models import Product, TypicalSection
from classifiers_app.models import OKSMCountry, OKVCurrency
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Max
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

DATE_INPUT_ATTRS = {"class": "form-control js-date", "autocomplete": "off"}  # ← хук для JS-пикера
DATE_INPUT_FORMATS = ["%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"]  # принимаем ISO и ДД.ММ.ГГ

class ProjectRegistration(models.Model):
    class AgreementType(models.TextChoices):
        MAIN = "MAIN", "Основной договор"
        ADDENDUM = "ADDENDUM", "Допсоглашение"

    position = models.PositiveIntegerField(default=0, db_index=True, verbose_name="Позиция")
    number = models.PositiveIntegerField(
        verbose_name="Номер",
        validators=[MinValueValidator(3333), MaxValueValidator(9999)],
    )
    group = models.CharField("Группа", max_length=2, default="RU", db_index=True)
    agreement_type = models.CharField(
        "Вид соглашения",
        max_length=20,
        choices=AgreementType.choices,
        default=AgreementType.MAIN,
        db_index=True,
    )
    agreement_number = models.CharField("№ соглашения", max_length=100, blank=True)
    type = models.ForeignKey(
        Product, on_delete=models.PROTECT, null=True, blank=True,
        related_name="project_registrations", verbose_name="Тип"
    )
    name = models.CharField("Название", max_length=255)

    short_uid = models.CharField(
        "Проект ID",
        max_length=32,
        unique=True,
        db_index=True,
        blank=True,
        editable=False,
    )

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

    input_data = models.PositiveIntegerField("Исх. данные, дней", null=True, blank=True, default=0)

    stage1_weeks = models.DecimalField(
        "Этап 1, недель",
        max_digits=4,
        decimal_places=1,
        default=0,
        validators=[MinValueValidator(0)],
    )
    stage1_end = models.DateField("Этап 1, дата окончания", null=True, blank=True)
    stage2_weeks = models.DecimalField(
        "Этап 2, недель",
        max_digits=4,
        decimal_places=1,
        default=0,
        validators=[MinValueValidator(0)],
    )
    stage2_end = models.DateField("Этап 2, дата окончания", null=True, blank=True)
    stage3_weeks = models.DecimalField (max_digits=4, decimal_places=1, default=0, validators=[MinValueValidator(0)],)
    term_weeks = models.DecimalField(
        "Срок, недель",
        max_digits=5,
        decimal_places=1,
        default=0,
        validators=[MinValueValidator(0)],
        editable=False,
    )

    deadline = models.DateField("Дедлайн", null=True, blank=True)
    year = models.PositiveIntegerField("Год", null=True, blank=True)

    country = models.ForeignKey(
        OKSMCountry,
        verbose_name="Страна",
        on_delete=models.SET_NULL,
        related_name="project_registrations",
        null=True,
        blank=True,
    )
    customer = models.CharField("Заказчик", max_length=255, blank=True)
    identifier = models.CharField("Идентификатор", max_length=64, blank=True, default="")
    registration_number = models.CharField("Регистрационный номер", max_length=100, blank=True)
    registration_date = models.DateField("Дата регистрации", null=True, blank=True)
    project_manager = models.CharField("Руководитель проекта", max_length=255, blank=True)
    contract_subject = models.TextField("Предмет договора", blank=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Регистрация проекта"
        verbose_name_plural = "Регистрация проекта"
        constraints = [
            models.UniqueConstraint(
                fields=("number", "group", "agreement_type", "agreement_number"),
                name="project_registration_identity_unique",
            ),
        ]

    def __str__(self):
        base = f"{self.number}{self.group}"
        agreement = self.get_agreement_type_display()
        suffix = f" №{self.agreement_number}" if self.agreement_number else ""
        return f"{base} — {agreement}{suffix} — {self.name}"

    @property
    def display_identifier(self):
        parts = [f"{self.number} {self.group} · {self.get_agreement_type_display()}"]
        if self.agreement_number:
            parts.append(f"№ {self.agreement_number}")
        return " ".join(parts)

    def save(self, *args, **kwargs):
        if (
            not self.agreement_number
            and self.group == "RU"
            and self.agreement_type == self.AgreementType.MAIN
        ):
            self.agreement_number = f"IMCM/{self.number}"
        self.stage1_end = self._calculate_stage1_end()
        self.stage2_end = self._calculate_stage2_end()
        self.term_weeks = self._calculate_term_weeks()
        self.completion_calc = self._calculate_completion_calc()
        if not self.short_uid or self._needs_uid_refresh():
            self.short_uid = self._build_short_uid()
        super().save(*args, **kwargs)

    def _calculate_stage1_end(self):
        if not self.contract_start:
            return None
        days = Decimal(self.input_data or 0)
        weeks = Decimal(self.stage1_weeks or 0) * Decimal("7")
        total = days + weeks
        if total < 0:
            total = Decimal("0")
        rounded_days = int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        return self.contract_start + timedelta(days=rounded_days)

    def _calculate_stage2_end(self):
        if not self.stage1_end:
            return None
        weeks = Decimal(self.stage2_weeks or 0) * Decimal("7")
        total = weeks
        if total < 0:
            total = Decimal("0")
        rounded_days = int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        return self.stage1_end + timedelta(days=rounded_days)

    def _calculate_term_weeks(self):
        days = Decimal(self.input_data or 0) / Decimal("7")
        stage1 = Decimal(self.stage1_weeks or 0)
        stage2 = Decimal(self.stage2_weeks or 0)
        stage3 = Decimal(self.stage3_weeks or 0)
        total = days + stage1 + stage2 + stage3
        if total < 0:
            total = Decimal("0")
        return total.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    def _calculate_completion_calc(self):
        if not self.stage2_end:
            return None
        weeks = Decimal(self.stage3_weeks or 0) * Decimal("7")
        total = max(weeks, Decimal("0"))
        rounded = int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        return self.stage2_end + timedelta(days=rounded)

    def _needs_uid_refresh(self):
        if not self.pk:
            return True
        orig = ProjectRegistration.objects.filter(pk=self.pk).values("number", "group").first()
        return not orig or orig["number"] != self.number or orig["group"] != self.group

    def _build_short_uid(self):
        base = f"{self.number}"
        idx = (
            ProjectRegistration.objects
            .filter(number=self.number, group=self.group)
            .exclude(pk=self.pk)
            .count()
        )
        return f"{base}{idx}{self.group}"

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
    country = models.ForeignKey(
        OKSMCountry,
        verbose_name="Страна",
        on_delete=models.SET_NULL,
        related_name="work_volumes",
        null=True,
        blank=True,
    )
    identifier = models.CharField("Идентификатор", max_length=64, blank=True, default="")
    registration_number = models.CharField(max_length=100, blank=True, verbose_name="Регистрационный номер")
    registration_date = models.DateField("Дата регистрации", null=True, blank=True)
    manager = models.CharField(max_length=255, blank=True, verbose_name="Менеджер")

    class Meta:
        ordering = ["project__position", "position", "id"]
        verbose_name = "Объем работ"
        verbose_name_plural = "Объем работ"

    def __str__(self):
        return f"{self.project.number if self.project_id else '-'} — {self.name}"


def _effective_work_asset_name(work_item):
    return (getattr(work_item, "asset_name", "") or getattr(work_item, "name", "") or "").strip()


def _sync_checklist_note_asset_names(project, section_ids, old_asset_name, new_asset_name):
    if not old_asset_name or old_asset_name == new_asset_name or not section_ids:
        return

    from checklists_app.models import ChecklistRequestNote, ChecklistCommentHistory

    source_notes = list(
        ChecklistRequestNote.objects
        .filter(project=project, asset_name=old_asset_name, section_id__in=section_ids)
        .select_related("checklist_item", "section")
    )
    if not source_notes:
        return

    with transaction.atomic():
        for source in source_notes:
            target = ChecklistRequestNote.objects.filter(
                checklist_item=source.checklist_item,
                project=source.project,
                section=source.section,
                asset_name=new_asset_name,
            ).exclude(pk=source.pk).first()

            if target:
                changed = False
                if source.imc_comment and not target.imc_comment:
                    target.imc_comment = source.imc_comment
                    changed = True
                if source.customer_comment and not target.customer_comment:
                    target.customer_comment = source.customer_comment
                    changed = True
                if changed:
                    target.save(update_fields=["imc_comment", "customer_comment", "updated_at"])
                ChecklistCommentHistory.objects.filter(note=source).update(note=target)
                source.delete()
                continue

            source.asset_name = new_asset_name
            source.save(update_fields=["asset_name"])


def _sync_related_asset_name_updates(instance, old_asset_name):
    new_asset_name = _effective_work_asset_name(instance)
    if old_asset_name == new_asset_name:
        return

    performers_qs = Performer.objects.filter(work_item=instance)
    section_ids = list(
        performers_qs.exclude(typical_section_id__isnull=True)
        .values_list("typical_section_id", flat=True)
        .distinct()
    )
    performers_qs.update(asset_name=new_asset_name)

    LegalEntity.objects.filter(
        work_item=instance,
        legal_name=old_asset_name,
    ).update(legal_name=new_asset_name)

    _sync_checklist_note_asset_names(instance.project, section_ids, old_asset_name, new_asset_name)

WorkVolumeItem = WorkVolume

class LegalEntity(models.Model):
    position = models.PositiveIntegerField(default=0, db_index=True, verbose_name="Позиция")
    project = models.ForeignKey(
        ProjectRegistration,
        on_delete=models.CASCADE,
        related_name="legal_entities",
        verbose_name="Проект",
    )
    work_item = models.ForeignKey(
        WorkVolume,
        on_delete=models.CASCADE,
        related_name="legal_entities",
        verbose_name="Наименование актива",
    )

    work_type = models.CharField("Тип", max_length=100, blank=True)
    work_name = models.CharField("Название", max_length=255, blank=True)    
    legal_name = models.CharField("Наименование юридического лица", max_length=255, blank=True)
    country = models.ForeignKey(
        OKSMCountry,
        verbose_name="Страна",
        on_delete=models.SET_NULL,
        related_name="legal_entities",
        null=True,
        blank=True,
    )
    identifier = models.CharField("Идентификатор", max_length=64, blank=True, default="")
    registration_number = models.CharField("Регистрационный номер", max_length=100, blank=True)
    registration_date = models.DateField("Дата регистрации", null=True, blank=True)

    class Meta:
        ordering = ["project__position", "position", "id"]
        verbose_name = "Юридическое лицо"
        verbose_name_plural = "Юридические лица"

    def __str__(self):
        project_uid = getattr(self.project, "short_uid", "")
        base = self.legal_name or self.registration_number or "юридическое лицо"
        return f"{project_uid} — {base}" if project_uid else base

    def save(self, *args, **kwargs):
        if self.work_item_id:
            self.project = self.work_item.project
            self.work_type = self.work_item.type or ""
            self.work_name = self.work_item.name or ""
        super().save(*args, **kwargs)

@receiver(post_save, sender=WorkVolume)
def ensure_primary_legal_entity(sender, instance, created, **kwargs):
    if not created or not instance.project_id:
        return
    if instance.legal_entities.exists():
        return
    max_pos = (
        LegalEntity.objects
        .filter(project_id=instance.project_id)
        .aggregate(max_pos=Max("position"))
        .get("max_pos") or 0
    )
    LegalEntity.objects.create(
        project=instance.project,
        work_item=instance,
        work_type=instance.type or "",
        work_name=instance.name or "",
        legal_name=instance.asset_name or instance.name or "",
        country=instance.country,
        identifier=instance.identifier,
        registration_number=instance.registration_number,
        registration_date=instance.registration_date,
        position=max_pos + 1,
    )


@receiver(pre_save, sender=WorkVolume)
def remember_previous_work_state(sender, instance, **kwargs):
    if not instance.pk:
        return
    previous = (
        WorkVolume.objects
        .filter(pk=instance.pk)
        .values("asset_name", "name")
        .first()
    )
    if previous:
        previous_asset = (previous.get("asset_name") or previous.get("name") or "").strip()
        instance._old_effective_asset_name = previous_asset


@receiver(post_save, sender=WorkVolume)
def ensure_performer_rows(sender, instance, created, **kwargs):
    if not created or not instance.project_id:
        return

    product_id = getattr(instance.project, "type_id", None)
    if not product_id:
        return

    sections = list(
        TypicalSection.objects
        .filter(product_id=product_id)
        .select_related("expertise_dir")
        .order_by("position", "id")
    )
    if not sections:
        return

    from users_app.models import Employee

    direction_ids = {s.expertise_direction_id for s in sections if s.expertise_direction_id}
    dept_head_map = {}
    if direction_ids:
        heads = (
            Employee.objects
            .select_related("user")
            .filter(
                department_id__in=direction_ids,
                role="Руководитель направления",
            )
        )
        for emp in heads:
            dept_head_map[emp.department_id] = emp

    # Pre-fetch expert profiles with grades for all department heads
    from experts_app.models import ExpertProfile
    head_employee_ids = [emp.pk for emp in dept_head_map.values()]
    expert_profile_map = {}
    if head_employee_ids:
        for p in ExpertProfile.objects.select_related("grade").filter(employee_id__in=head_employee_ids):
            expert_profile_map[p.employee_id] = p

    # Pre-fetch tariffs for all sections of this product
    from policy_app.models import Tariff, Grade
    tariff_map = {}
    tariff_hours_map = {}
    for t in Tariff.objects.filter(product_id=product_id, section_id__in=[s.id for s in sections]):
        tariff_map[t.section_id] = float(t.base_rate_vpm)
        tariff_hours_map[t.section_id] = t.service_hours or 0

    # Pre-fetch base-rate hourly rates per OrgUnit (direction)
    base_hourly_rate_map = {}
    for bg in (
        Grade.objects
        .filter(is_base_rate=True, hourly_rate__isnull=False)
        .select_related("created_by__employee_profile")
    ):
        emp = getattr(bg.created_by, "employee_profile", None)
        if emp and emp.department_id:
            base_hourly_rate_map[emp.department_id] = float(bg.hourly_rate)

    # Pre-fetch living wages
    import math
    from classifiers_app.models import LivingWage
    today = timezone.now().date()
    living_wage_map = {}
    for w in (
        LivingWage.objects
        .filter(
            models.Q(approval_date__lte=today),
            models.Q(expiry_date__isnull=True) | models.Q(expiry_date__gte=today),
        )
        .order_by("-approval_date")
    ):
        key = (w.country_id, w.region_id)
        if key not in living_wage_map:
            living_wage_map[key] = float(w.amount)

    next_position = (
        Performer.objects
        .aggregate(max_pos=Max("position"))
        .get("max_pos") or 0
    )
    asset_name = instance.asset_name or instance.name or ""

    rub = (
        OKVCurrency.objects
        .filter(
            models.Q(approval_date__isnull=True) | models.Q(approval_date__lte=today),
            models.Q(expiry_date__isnull=True) | models.Q(expiry_date__gte=today),
            code_alpha="RUB",
        )
        .first()
    )

    performers = []
    for section in sections:
        next_position += 1

        executor_name = ""
        employee_obj = None
        grade_value = ""
        grade_name_value = ""
        estimated_costs_value = None
        agreed_amount_value = None

        if section.expertise_direction_id:
            head = dept_head_map.get(section.expertise_direction_id)
            if head:
                parts = [
                    head.user.last_name.strip(),
                    head.user.first_name.strip(),
                    head.patronymic.strip(),
                ]
                executor_name = " ".join(p for p in parts if p)
                employee_obj = head

                profile = expert_profile_map.get(head.pk)
                if profile and profile.grade:
                    g = profile.grade
                    grade_name_value = g.grade_ru or g.grade_en or ""
                    q = g.qualification or 0
                    lvl = g.qualification_levels or 5
                    grade_value = f"{q}/{lvl}"

                    base_rate_share = 0 if g.is_base_rate else (g.base_rate_share or 0)
                    Y = base_rate_share / 100
                    pricing_method = ""
                    if section.expertise_dir_id:
                        pricing_method = section.expertise_dir.pricing_method or ""

                    if pricing_method == "vpm":
                        if profile.country_id and profile.region_id:
                            Z = living_wage_map.get((profile.country_id, profile.region_id))
                            X = tariff_map.get(section.id)
                            if Z is not None and X is not None:
                                result = math.ceil((Z * X * (1 + Y)) / 1000) * 1000
                                estimated_costs_value = Decimal(str(result))
                                agreed_amount_value = estimated_costs_value
                    else:
                        Z = base_hourly_rate_map.get(section.expertise_direction_id)
                        X = tariff_hours_map.get(section.id)
                        if Z is not None and X is not None and X > 0:
                            result = math.ceil((Z * X * (1 + Y)) / 1000) * 1000
                            estimated_costs_value = Decimal(str(result))
                            agreed_amount_value = estimated_costs_value

        performers.append(
            Performer(
                work_item=instance,
                registration=instance.project,
                asset_name=asset_name,
                typical_section=section,
                position=next_position,
                currency=rub,
                prepayment=50,
                final_payment=50,
                executor=executor_name,
                employee=employee_obj,
                grade=grade_value,
                grade_name=grade_name_value,
                estimated_costs=estimated_costs_value,
                agreed_amount=agreed_amount_value,
            )
        )

    Performer.objects.bulk_create(performers)


@receiver(post_save, sender=WorkVolume)
def sync_related_asset_name_updates(sender, instance, created, **kwargs):
    if created or not instance.project_id:
        return
    old_asset_name = getattr(instance, "_old_effective_asset_name", None)
    if old_asset_name is None:
        return
    _sync_related_asset_name_updates(instance, old_asset_name)

class Performer(models.Model):
    class ParticipationResponse(models.TextChoices):
        CONFIRMED = "confirmed", "Подтверждаю участие"
        DECLINED = "declined", "Не готов(а) участвовать"

    class InfoApprovalStatus(models.TextChoices):
        NOT_APPROVED = "not_approved", "Не согласован"
        APPROVED = "approved", "Согласован"

    position = models.PositiveIntegerField(default=1, db_index=True)

    work_item = models.ForeignKey(
        WorkVolume,
        on_delete=models.CASCADE,
        related_name="performers",
        null=True,
        blank=True,
        verbose_name="Строка объема услуг",
    )

    registration = models.ForeignKey(
        ProjectRegistration,
        on_delete=models.CASCADE,
        related_name="performers",
        verbose_name="Регистрация проекта",
    )

    asset_name = models.CharField("Актив", max_length=255, blank=True, default="")
    executor = models.CharField("Исполнитель", max_length=255, blank=True, default="")
    employee = models.ForeignKey(
        "users_app.Employee",
        on_delete=models.SET_NULL,
        related_name="performers",
        verbose_name="Сотрудник",
        null=True,
        blank=True,
    )
    grade = models.CharField("Грейд (уровень)", max_length=50, blank=True, default="")
    grade_name = models.CharField("Грейд (наименование)", max_length=255, blank=True, default="")
    currency = models.ForeignKey(
        "classifiers_app.OKVCurrency",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Валюта",
        related_name="performers",
    )

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
    participation_request_sent_at = models.DateTimeField("Дата отправки запроса", null=True, blank=True)
    participation_deadline_at = models.DateTimeField("Срок подтверждения", null=True, blank=True)
    participation_response = models.CharField(
        "Ответ на запрос",
        max_length=20,
        choices=ParticipationResponse.choices,
        blank=True,
        default="",
    )
    participation_response_at = models.DateTimeField("Дата ответа на запрос", null=True, blank=True)

    info_request_sent_at = models.DateTimeField("Дата отправки запроса согласования", null=True, blank=True)
    info_request_deadline_at = models.DateTimeField("Срок согласования", null=True, blank=True)
    info_approval_status = models.CharField(
        "Статус согласования",
        max_length=20,
        choices=InfoApprovalStatus.choices,
        blank=True,
        default="",
    )
    info_approval_at = models.DateTimeField("Дата ответа на запрос согласования", null=True, blank=True)

    contract_sent_at = models.DateTimeField("Дата отправки проекта договора", null=True, blank=True)
    contract_deadline_at = models.DateTimeField("Срок подписания договора", null=True, blank=True)
    contract_signing_date = models.DateField("Дата подписания", null=True, blank=True)
    contract_conclusion_status = models.CharField("Статус заключения договора", max_length=100, blank=True, default="")
    contract_signing_note = models.CharField("Подписание", max_length=255, blank=True, default="")
    contract_term = models.CharField("Срок договора", max_length=255, blank=True, default="")
    contract_file = models.CharField("Файл договора", max_length=500, blank=True, default="")
    contract_batch_id = models.UUIDField("ID батча договора", null=True, blank=True, db_index=True)
    contract_is_addendum = models.BooleanField("Доп. соглашение", default=False)
    contract_addendum_number = models.PositiveIntegerField("Номер доп. соглашения", null=True, blank=True)
    contract_project_created = models.BooleanField("Проект договора создан", default=False)
    contract_project_created_at = models.DateTimeField("Дата создания проекта договора", null=True, blank=True)
    contract_project_link = models.URLField("Ссылка на проект договора", blank=True, default="")
    contract_project_disk_folder = models.CharField("Папка проекта на Яндекс.Диске", max_length=500, blank=True, default="")
    contract_date = models.DateField("Дата договора", null=True, blank=True)

    contract_employee_scan = models.FileField("Скан с подписью сотрудника", upload_to="contract_employee_scans/", blank=True, default="")
    contract_send_date = models.DateField("Дата отправки", null=True, blank=True)
    contract_signed_scan = models.CharField("Скан подписанного договора", max_length=500, blank=True, default="")
    contract_upload_date = models.DateField("Дата загрузки", null=True, blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_employee_id = self.employee_id
        self._original_executor = self.executor

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Исполнитель"
        verbose_name_plural = "Исполнители"

    def __str__(self):
        num = getattr(self.registration, "number", "") or ""
        grp = getattr(self.registration, "group", "") or ""
        return f"{num} {grp} — {self.executor or 'исполнитель'}"

    @staticmethod
    def employee_full_name(employee):
        if not employee:
            return ""
        parts = [
            (getattr(getattr(employee, "user", None), "last_name", "") or "").strip(),
            (getattr(getattr(employee, "user", None), "first_name", "") or "").strip(),
            (getattr(employee, "patronymic", "") or "").strip(),
        ]
        return " ".join(part for part in parts if part).strip()

    @classmethod
    def resolve_employee_from_executor(cls, executor):
        normalized_executor = " ".join(str(executor or "").split()).strip()
        if not normalized_executor:
            return None
        from users_app.models import Employee

        for employee in Employee.objects.select_related("user").all():
            if cls.employee_full_name(employee) == normalized_executor:
                return employee
        return None

    def save(self, *args, **kwargs):
        normalized_executor = " ".join(str(self.executor or "").split()).strip()
        if normalized_executor:
            self.executor = normalized_executor
            resolved_employee = self.resolve_employee_from_executor(normalized_executor)
            if resolved_employee:
                self.employee = resolved_employee
        elif self.employee_id:
            self.executor = self.employee_full_name(self.employee)
        if (
            self.pk
            and self._original_employee_id is not None
            and self.employee_id != self._original_employee_id
        ):
            if self.participation_request_sent_at and self.participation_response:
                PerformerParticipationSnapshot.objects.create(
                    performer=self,
                    executor_name=self._original_executor or self.executor,
                    employee_id=self._original_employee_id,
                    request_sent_at=self.participation_request_sent_at,
                    deadline_at=self.participation_deadline_at,
                    response=self.participation_response,
                    response_at=self.participation_response_at,
                )
            self.participation_request_sent_at = None
            self.participation_deadline_at = None
            self.participation_response = ""
            self.participation_response_at = None
        if self.prepayment is not None:
            self.final_payment = Decimal("100") - Decimal(str(self.prepayment))
        super().save(*args, **kwargs)
        self._original_employee_id = self.employee_id
        self._original_executor = self.executor

    @property
    def participation_response_status(self):
        if not self.participation_deadline_at:
            return ""
        if self.participation_response_at:
            return "Просрочено" if self.participation_response_at > self.participation_deadline_at else "В срок"
        if timezone.now() > self.participation_deadline_at:
            return "Просрочено"
        return ""

    @property
    def info_response_status(self):
        if not self.info_request_deadline_at:
            return ""
        if self.info_approval_at:
            return "Просрочено" if self.info_approval_at > self.info_request_deadline_at else "В срок"
        if timezone.now() > self.info_request_deadline_at:
            return "Просрочено"
        return ""

    @property
    def contract_term_days(self):
        if not self.contract_date or not getattr(self.registration, "deadline", None):
            return None
        return (self.registration.deadline - self.contract_date).days

    @property
    def contract_response_status(self):
        if not self.contract_deadline_at:
            return ""
        return "Просрочено" if timezone.now() > self.contract_deadline_at else "В срок"


class PerformerParticipationSnapshot(models.Model):
    """Snapshot of participation data preserved when the executor changes on a Performer."""

    performer = models.ForeignKey(
        Performer,
        on_delete=models.CASCADE,
        related_name="participation_snapshots",
        verbose_name="Исполнитель",
    )
    executor_name = models.CharField("Исполнитель (ФИО)", max_length=255)
    employee = models.ForeignKey(
        "users_app.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="participation_snapshots",
        verbose_name="Сотрудник",
    )
    request_sent_at = models.DateTimeField("Дата отправки запроса", null=True, blank=True)
    deadline_at = models.DateTimeField("Срок подтверждения", null=True, blank=True)
    response = models.CharField(
        "Ответ на запрос",
        max_length=20,
        choices=Performer.ParticipationResponse.choices,
        blank=True,
        default="",
    )
    response_at = models.DateTimeField("Дата ответа", null=True, blank=True)

    class Meta:
        ordering = ["request_sent_at", "id"]
        verbose_name = "Снимок подтверждения участия"
        verbose_name_plural = "Снимки подтверждений участия"

    def __str__(self):
        return f"Snapshot {self.pk}: {self.executor_name} → {self.get_response_display() or '—'}"

    @property
    def response_status(self):
        if not self.deadline_at:
            return ""
        if self.response_at:
            return "Просрочено" if self.response_at > self.deadline_at else "В срок"
        if timezone.now() > self.deadline_at:
            return "Просрочено"
        return ""


class RegistrationWorkspaceFolder(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="workspace_folders",
    )
    level = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(3)],
    )
    name = models.CharField(max_length=255)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position"]

    def __str__(self):
        return f"L{self.level}: {self.name}"


class SourceDataTargetFolder(models.Model):
    """Хранит выбранную пользователем целевую папку уровня 1
    для создания пространства исходных данных."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="source_data_target_folder",
    )
    folder_name = models.CharField(max_length=255)

    class Meta:
        verbose_name = "Целевая папка исходных данных"
        verbose_name_plural = "Целевые папки исходных данных"

    def __str__(self):
        return f"{self.user}: {self.folder_name}"


class ContractProjectTargetFolder(models.Model):
    """Хранит выбранную пользователем целевую папку уровня 1
    для создания проекта договора."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="contract_project_target_folder",
    )
    folder_name = models.CharField(max_length=255)

    class Meta:
        verbose_name = "Целевая папка проекта договора"
        verbose_name_plural = "Целевые папки проекта договора"

    def __str__(self):
        return f"{self.user}: {self.folder_name}"