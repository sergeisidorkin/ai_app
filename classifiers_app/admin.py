from django.contrib import admin

from .models import LegalEntityRecord


@admin.register(LegalEntityRecord)
class LegalEntityRecordAdmin(admin.ModelAdmin):
    list_display = ("short_name", "identifier", "registration_number", "registration_country", "record_date")
    list_filter = ("registration_country",)
    search_fields = ("short_name", "full_name", "identifier", "registration_number")
