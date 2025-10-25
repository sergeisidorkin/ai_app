# ai_app/docops_queue/admin.py
from django.contrib import admin
from .models import Job

@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("id","status","priority","doc_url","assigned_agent","attempts","created_at")
    list_filter = ("status","assigned_agent")
    search_fields = ("doc_url","id")