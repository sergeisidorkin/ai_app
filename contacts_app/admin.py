from django.contrib import admin

from .models import CitizenshipRecord, EmailRecord, PersonRecord, PhoneRecord, PositionRecord, ResidenceAddressRecord


@admin.register(PersonRecord)
class PersonRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "last_name", "first_name", "middle_name", "full_name_genitive", "gender", "birth_date")
    search_fields = ("last_name", "first_name", "middle_name", "full_name_genitive")
    list_filter = ("citizenship", "gender")


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
