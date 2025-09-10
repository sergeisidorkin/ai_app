from django.contrib import admin
from .models import Product

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("short_name", "name_en", "name_ru", "service_type", "updated_at")
    search_fields = ("short_name", "name_en", "name_ru", "service_type")
    ordering = ("short_name",)