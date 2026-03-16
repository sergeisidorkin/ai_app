from django.contrib import admin

from .models import LetterTemplate


@admin.register(LetterTemplate)
class LetterTemplateAdmin(admin.ModelAdmin):
    list_display = ("template_type", "user", "is_default", "subject_template", "updated_at")
    list_filter = ("template_type", "is_default")
    search_fields = ("user__username", "user__first_name", "user__last_name")
    raw_id_fields = ("user",)
    filter_horizontal = ("cc_recipients",)
