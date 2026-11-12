from django import forms
from django.contrib import admin

from .forms import apply_explicit_prs_id, clean_new_prs_id
from .models import (
    CitizenshipRecord,
    EmailRecord,
    PersonRecord,
    PhoneRecord,
    PositionRecord,
    ResidenceAddressRecord,
    SpecialtyRecord,
)


class PersonRecordAdminForm(forms.ModelForm):
    prs_id = forms.CharField(
        label="ID-PRS",
        required=False,
        help_text="Оставьте пустым, чтобы выдать следующий номер. Чтобы вернуть удалённый номер, укажите его, например 00027-PRS.",
    )

    class Meta:
        model = PersonRecord
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["prs_id"].initial = self.instance.formatted_id
            self.fields["prs_id"].disabled = True
            self.fields["prs_id"].help_text = "Номер уже выдан, его нельзя изменить."

    def clean_prs_id(self):
        return clean_new_prs_id(self.cleaned_data.get("prs_id"), self.instance)

    def save(self, commit=True):
        instance = super().save(commit=False)
        apply_explicit_prs_id(instance, self.cleaned_data.get("prs_id"))
        if commit:
            instance.save()
            self.save_m2m()
        return instance


@admin.register(PersonRecord)
class PersonRecordAdmin(admin.ModelAdmin):
    form = PersonRecordAdminForm
    fields = (
        "prs_id",
        "last_name",
        "first_name",
        "middle_name",
        "full_name_genitive",
        "gender",
        "birth_date",
        "citizenship",
        "user_kind",
        "position",
    )
    list_display = ("prs_label", "last_name", "first_name", "middle_name", "full_name_genitive", "gender", "birth_date")
    search_fields = ("last_name", "first_name", "middle_name", "full_name_genitive")
    list_filter = ("citizenship", "gender")

    @admin.display(description="ID-PRS", ordering="id")
    def prs_label(self, obj):
        return obj.formatted_id


@admin.register(PositionRecord)
class PositionRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "person", "organization_short_name", "job_title", "valid_from", "valid_to", "is_active", "record_date")
    search_fields = ("person__last_name", "person__first_name", "organization_short_name", "job_title", "source")


@admin.register(PhoneRecord)
class PhoneRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "person", "phone_type", "country", "region", "code", "phone_number", "extension", "valid_from", "valid_to", "is_active", "record_date")
    search_fields = ("person__last_name", "person__first_name", "region", "code", "phone_number", "extension", "source")
    list_filter = ("phone_type", "country", "region")


@admin.register(EmailRecord)
class EmailRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "person", "email", "valid_from", "valid_to", "is_active", "record_date")
    search_fields = ("person__last_name", "person__first_name", "email", "source")


@admin.register(SpecialtyRecord)
class SpecialtyRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "person", "specialty", "valid_from", "valid_to", "is_active", "record_date")
    search_fields = ("person__last_name", "person__first_name", "specialty__specialty", "source")
    list_filter = ("specialty",)


@admin.register(ResidenceAddressRecord)
class ResidenceAddressRecordAdmin(admin.ModelAdmin):
    list_display = (
        "id", "person", "country", "region", "postal_code", "locality", "street",
        "building", "premise", "premise_part", "valid_from", "valid_to", "is_active", "record_date",
    )
    search_fields = (
        "person__last_name", "person__first_name", "region", "postal_code", "locality",
        "street", "building", "premise", "premise_part", "source",
    )
    list_filter = ("country", "region")


@admin.register(CitizenshipRecord)
class CitizenshipRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "person", "country", "status", "identifier", "number", "valid_from", "valid_to", "is_active", "record_date")
    search_fields = ("person__last_name", "person__first_name", "status", "identifier", "number", "source")
    list_filter = ("country",)
