import sys

from django.db import models

from classifiers_app.models import LegalEntityRecord, OKSMCountry

sys.modules.setdefault("contacts_app.models", sys.modules[__name__])
sys.modules.setdefault("ai_app.contacts_app.models", sys.modules[__name__])


CONTACT_POSITION_SOURCE = "[ТКП / Отправка ТКП]"


def _normalize_compare_value(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


class PersonRecord(models.Model):
    last_name = models.CharField("Фамилия", max_length=255, blank=True, default="")
    first_name = models.CharField("Имя", max_length=255, blank=True, default="")
    middle_name = models.CharField("Отчество", max_length=255, blank=True, default="")
    citizenship = models.ForeignKey(
        OKSMCountry,
        verbose_name="Гражданство",
        on_delete=models.SET_NULL,
        related_name="contact_person_records",
        null=True,
        blank=True,
    )
    identifier = models.CharField("Идентификатор", max_length=255, blank=True, default="")
    number = models.CharField("Номер", max_length=255, blank=True, default="")
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "contacts_app"
        ordering = ["position", "id"]
        verbose_name = "Лицо"
        verbose_name_plural = "Реестр лиц"

    def __str__(self):
        return self.display_name or f"{self.pk:05d}-PRS"

    @property
    def formatted_id(self):
        if not self.pk:
            return ""
        return f"{self.pk:05d}-PRS"

    @property
    def display_name(self):
        parts = [self.last_name, self.first_name, self.middle_name]
        return " ".join(part for part in parts if part).strip()


class PositionRecord(models.Model):
    person = models.ForeignKey(
        PersonRecord,
        verbose_name="ID-PRS",
        on_delete=models.CASCADE,
        related_name="positions",
    )
    organization_short_name = models.CharField(
        "Наименование организации (краткое)",
        max_length=512,
        blank=True,
        default="",
    )
    job_title = models.CharField("Должность", max_length=255, blank=True, default="")
    valid_from = models.DateField("Действ. от", blank=True, null=True)
    valid_to = models.DateField("Действ. до", blank=True, null=True)
    record_date = models.DateField("Дата записи", blank=True, null=True)
    record_author = models.CharField("Автор записи", max_length=255, blank=True, default="")
    source = models.TextField("Источник", blank=True, default="")
    position = models.PositiveIntegerField("Позиция", default=0, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "contacts_app"
        ordering = ["position", "id"]
        verbose_name = "Должность"
        verbose_name_plural = "Реестр должностей"

    def __str__(self):
        return f"{self.formatted_id} {self.job_title}".strip()

    @property
    def formatted_id(self):
        if not self.pk:
            return ""
        return f"{self.pk:05d}-PSN"

    @classmethod
    def organization_choices(cls):
        values = (
            LegalEntityRecord.objects.filter(
                attribute=LegalEntityRecord.ATTRIBUTE_NAME,
                is_active=True,
            )
            .exclude(short_name="")
            .order_by("position", "id")
            .values_list("short_name", flat=True)
        )
        result = []
        seen = set()
        for value in values:
            normalized = value.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result

    def resolve_source(self) -> str:
        from proposals_app.models import ProposalRegistration

        title = _normalize_compare_value(self.job_title)
        surname = _normalize_compare_value(self.person.last_name if self.person_id else "")
        if not title or not surname:
            return ""
        qs = ProposalRegistration.objects.exclude(contact_full_name="").order_by("position", "id")
        for proposal in qs.iterator():
            if _normalize_compare_value(proposal.recipient_job_title) != title:
                continue
            full_name = _normalize_compare_value(proposal.contact_full_name)
            proposal_surname = full_name.split(" ", 1)[0] if full_name else ""
            if proposal_surname == surname:
                return CONTACT_POSITION_SOURCE
        return ""
