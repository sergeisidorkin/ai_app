from django.db import models, transaction


def _country_key(member) -> str:
    return (member.country_code or member.country_name or "").strip()


class GroupMember(models.Model):
    short_name = models.CharField("Наименование компании (краткое)", max_length=255)
    full_name = models.CharField("Наименование компании (полное)", max_length=512, blank=True, default="")
    name_en = models.CharField("Наименование на английском языке", max_length=512, blank=True, default="")
    country_name = models.CharField("Страна регистрации", max_length=255)
    country_code = models.CharField("Код страны (ОКСМ)", max_length=3, blank=True, default="")
    country_alpha2 = models.CharField("Буквенный код (Альфа-2)", max_length=2, blank=True, default="")
    country_order_number = models.PositiveIntegerField("№", default=0, db_index=True, editable=False)
    identifier = models.CharField("Идентификатор", max_length=255, blank=True, default="")
    registration_number = models.CharField("Регистрационный номер", max_length=255, blank=True, default="")
    registration_date = models.DateField("Дата регистрации", blank=True, null=True)
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Участник группы"
        verbose_name_plural = "Состав группы"

    def __str__(self):
        return self.short_name

    @property
    def group_code_label(self) -> str:
        alpha2 = (self.country_alpha2 or "").strip().upper()
        if not alpha2:
            return ""
        if int(self.country_order_number or 0) == 0:
            return alpha2
        return f"{self.country_order_number}-{alpha2}"

    @property
    def group_display_label(self) -> str:
        prefix = self.group_code_label or f"№{self.country_order_number}"
        return f"{prefix} {self.short_name}".strip()


def resequence_group_members(*, refresh_project_uids: bool = True):
    members = list(
        GroupMember.objects
        .order_by("position", "id")
        .only("id", "country_code", "country_name", "country_order_number")
    )
    counters = {}
    to_update = []
    affected_ids = set()

    for member in members:
        key = _country_key(member)
        next_number = counters.get(key, 0)
        if member.country_order_number != next_number:
            member.country_order_number = next_number
            to_update.append(member)
            affected_ids.add(member.pk)
        counters[key] = next_number + 1

    if to_update:
        GroupMember.objects.bulk_update(to_update, ["country_order_number"])

    if refresh_project_uids and affected_ids:
        from projects_app.models import ProjectRegistration

        with transaction.atomic():
            ProjectRegistration.refresh_short_uids_for_group_members(affected_ids)

    return affected_ids


class OrgUnit(models.Model):
    UNIT_TYPE_CHOICES = [
        ("administrative", "Административное подразделение"),
        ("expertise", "Направление экспертизы"),
        ("project_roles", "Группа проектных ролей"),
    ]

    company = models.ForeignKey(
        GroupMember,
        on_delete=models.CASCADE,
        related_name="org_units",
        verbose_name="Наименование компании (краткое)",
    )
    level = models.PositiveIntegerField("Уровень", default=1)
    department_name = models.CharField(
        "Наименование структурного подразделения", max_length=512
    )
    short_name = models.CharField(
        "Краткое имя", max_length=128, blank=True, default=""
    )
    expertise = models.ForeignKey(
        "policy_app.ExpertiseDirection",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="org_units",
        verbose_name="Экспертиза",
    )
    functional_subordination = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subordinates",
        verbose_name="Функциональное подчинение",
    )
    unit_type = models.CharField(
        "Тип подразделения",
        max_length=32,
        choices=UNIT_TYPE_CHOICES,
        blank=True,
        default="",
    )
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Структурное подразделение"
        verbose_name_plural = "Организационная структура"

    def __str__(self):
        return self.department_name
