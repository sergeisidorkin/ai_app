from django.contrib import admin
from blocks_app.models import Block


@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "model", "updated_at")
    search_fields = ("code", "name", "model")
