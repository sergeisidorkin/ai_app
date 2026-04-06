from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import HttpResponseRedirect
from django.urls import path, reverse

from .models import (
    LegalEntityRecord,
    BusinessEntityRecord,
    BusinessEntityIdentifierRecord,
    BusinessEntityAttributeRecord,
    BusinessEntityReorganizationEvent,
    BusinessEntityRelationRecord,
)


@admin.register(LegalEntityRecord)
class LegalEntityRecordAdmin(admin.ModelAdmin):
    list_display = (
        "attribute",
        "short_name",
        "identifier_record",
        "identifier",
        "registration_number",
        "registration_country",
        "registration_region",
        "postal_code",
        "record_date",
    )
    list_filter = ("attribute", "registration_country", "is_active")
    search_fields = (
        "short_name",
        "full_name",
        "identifier",
        "registration_number",
        "registration_region",
        "postal_code",
        "municipality",
        "settlement",
        "locality",
        "street",
        "building",
    )


@admin.register(BusinessEntityRecord)
class BusinessEntityRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "record_date", "comment")
    search_fields = ("name", "comment")
    change_list_template = "admin/classifiers_app/businessentityrecord/change_list.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "reset-counter/",
                self.admin_site.admin_view(self.reset_counter_view),
                name="classifiers_app_businessentityrecord_reset_counter",
            ),
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["reset_counter_url"] = reverse("admin:classifiers_app_businessentityrecord_reset_counter")
        return super().changelist_view(request, extra_context=extra_context)

    def reset_counter_view(self, request):
        if request.method != "POST":
            raise PermissionDenied
        if not self.has_change_permission(request):
            raise PermissionDenied

        max_id = BusinessEntityRecord.objects.order_by("-id").values_list("id", flat=True).first() or 0
        table_name = BusinessEntityRecord._meta.db_table

        with connection.cursor() as cursor:
            if connection.vendor == "sqlite":
                cursor.execute("UPDATE sqlite_sequence SET seq = %s WHERE name = %s", [max_id, table_name])
                if cursor.rowcount == 0:
                    cursor.execute(
                        "INSERT INTO sqlite_sequence(name, seq) VALUES (%s, %s)",
                        [table_name, max_id],
                    )
            elif connection.vendor == "postgresql":
                set_value = max_id if max_id > 0 else 1
                is_called = max_id > 0
                cursor.execute(
                    "SELECT setval(pg_get_serial_sequence(%s, %s), %s, %s)",
                    [table_name, "id", set_value, is_called],
                )
            elif connection.vendor == "mysql":
                next_value = max_id + 1 if max_id > 0 else 1
                quoted_table = connection.ops.quote_name(table_name)
                cursor.execute(f"ALTER TABLE {quoted_table} AUTO_INCREMENT = %s", [next_value])
            else:
                self.message_user(
                    request,
                    f"Сброс счетчика не поддерживается для БД '{connection.vendor}'.",
                    level=messages.ERROR,
                )
                return HttpResponseRedirect(reverse("admin:classifiers_app_businessentityrecord_changelist"))

        next_display = f"{max_id + 1:05d}-BSN" if max_id > 0 else "00001-BSN"
        self.message_user(
            request,
            f"Счетчик ID-BSN синхронизирован. Следующее значение: {next_display}.",
            level=messages.SUCCESS,
        )
        return HttpResponseRedirect(reverse("admin:classifiers_app_businessentityrecord_changelist"))


@admin.register(BusinessEntityIdentifierRecord)
class BusinessEntityIdentifierRecordAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "business_entity",
        "registration_code",
        "registration_region_code",
        "registration_country",
        "identifier_type",
        "number",
        "registration_region",
        "registration_date",
        "valid_from",
        "valid_to",
        "is_active",
    )
    list_filter = ("identifier_type", "is_active")
    search_fields = ("number", "identifier_type", "business_entity__name")
    change_list_template = "admin/classifiers_app/businessentityidentifierrecord/change_list.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "reset-counter/",
                self.admin_site.admin_view(self.reset_counter_view),
                name="classifiers_app_businessentityidentifierrecord_reset_counter",
            ),
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["reset_counter_url"] = reverse("admin:classifiers_app_businessentityidentifierrecord_reset_counter")
        return super().changelist_view(request, extra_context=extra_context)

    def reset_counter_view(self, request):
        if request.method != "POST":
            raise PermissionDenied
        if not self.has_change_permission(request):
            raise PermissionDenied

        max_id = BusinessEntityIdentifierRecord.objects.order_by("-id").values_list("id", flat=True).first() or 0
        table_name = BusinessEntityIdentifierRecord._meta.db_table

        with connection.cursor() as cursor:
            if connection.vendor == "sqlite":
                cursor.execute("UPDATE sqlite_sequence SET seq = %s WHERE name = %s", [max_id, table_name])
                if cursor.rowcount == 0:
                    cursor.execute(
                        "INSERT INTO sqlite_sequence(name, seq) VALUES (%s, %s)",
                        [table_name, max_id],
                    )
            elif connection.vendor == "postgresql":
                set_value = max_id if max_id > 0 else 1
                is_called = max_id > 0
                cursor.execute(
                    "SELECT setval(pg_get_serial_sequence(%s, %s), %s, %s)",
                    [table_name, "id", set_value, is_called],
                )
            elif connection.vendor == "mysql":
                next_value = max_id + 1 if max_id > 0 else 1
                quoted_table = connection.ops.quote_name(table_name)
                cursor.execute(f"ALTER TABLE {quoted_table} AUTO_INCREMENT = %s", [next_value])
            else:
                self.message_user(
                    request,
                    f"Сброс счетчика не поддерживается для БД '{connection.vendor}'.",
                    level=messages.ERROR,
                )
                return HttpResponseRedirect(reverse("admin:classifiers_app_businessentityidentifierrecord_changelist"))

        next_display = f"{max_id + 1:05d}-IDN" if max_id > 0 else "00001-IDN"
        self.message_user(
            request,
            f"Счетчик ID-IDN синхронизирован. Следующее значение: {next_display}.",
            level=messages.SUCCESS,
        )
        return HttpResponseRedirect(reverse("admin:classifiers_app_businessentityidentifierrecord_changelist"))


@admin.register(BusinessEntityAttributeRecord)
class BusinessEntityAttributeRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "attribute_name", "subsection_name")
    search_fields = ("attribute_name", "subsection_name")


@admin.register(BusinessEntityReorganizationEvent)
class BusinessEntityReorganizationEventAdmin(admin.ModelAdmin):
    list_display = ("id", "reorganization_event_uid", "relation_type", "event_date")
    list_filter = ("relation_type",)
    search_fields = ("reorganization_event_uid", "relation_type", "comment")


@admin.register(BusinessEntityRelationRecord)
class BusinessEntityRelationRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "event_uid", "relation_type_display", "from_business_entity", "to_business_entity", "event_date_display")
    list_filter = ("event__relation_type",)
    search_fields = (
        "event__reorganization_event_uid",
        "event__relation_type",
        "event__comment",
        "from_business_entity__name",
        "to_business_entity__name",
    )
    change_list_template = "admin/classifiers_app/businessentityrelationrecord/change_list.html"

    @admin.display(description="ID-REO", ordering="event__reorganization_event_uid")
    def event_uid(self, obj):
        return obj.event.reorganization_event_uid if obj.event_id else ""

    @admin.display(description="Тип связи", ordering="event__relation_type")
    def relation_type_display(self, obj):
        return obj.event.relation_type if obj.event_id else ""

    @admin.display(description="Дата события", ordering="event__event_date")
    def event_date_display(self, obj):
        return obj.event.event_date if obj.event_id else None

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "reset-counter/",
                self.admin_site.admin_view(self.reset_counter_view),
                name="classifiers_app_businessentityrelationrecord_reset_counter",
            ),
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["reset_counter_url"] = reverse("admin:classifiers_app_businessentityrelationrecord_reset_counter")
        return super().changelist_view(request, extra_context=extra_context)

    def reset_counter_view(self, request):
        if request.method != "POST":
            raise PermissionDenied
        if not self.has_change_permission(request):
            raise PermissionDenied

        max_id = BusinessEntityRelationRecord.objects.order_by("-id").values_list("id", flat=True).first() or 0
        table_name = BusinessEntityRelationRecord._meta.db_table

        with connection.cursor() as cursor:
            if connection.vendor == "sqlite":
                cursor.execute("UPDATE sqlite_sequence SET seq = %s WHERE name = %s", [max_id, table_name])
                if cursor.rowcount == 0:
                    cursor.execute(
                        "INSERT INTO sqlite_sequence(name, seq) VALUES (%s, %s)",
                        [table_name, max_id],
                    )
            elif connection.vendor == "postgresql":
                set_value = max_id if max_id > 0 else 1
                is_called = max_id > 0
                cursor.execute(
                    "SELECT setval(pg_get_serial_sequence(%s, %s), %s, %s)",
                    [table_name, "id", set_value, is_called],
                )
            elif connection.vendor == "mysql":
                next_value = max_id + 1 if max_id > 0 else 1
                quoted_table = connection.ops.quote_name(table_name)
                cursor.execute(f"ALTER TABLE {quoted_table} AUTO_INCREMENT = %s", [next_value])
            else:
                self.message_user(
                    request,
                    f"Сброс счетчика не поддерживается для БД '{connection.vendor}'.",
                    level=messages.ERROR,
                )
                return HttpResponseRedirect(reverse("admin:classifiers_app_businessentityrelationrecord_changelist"))

        next_display = f"{max_id + 1:05d}-RLT" if max_id > 0 else "00001-RLT"
        self.message_user(
            request,
            f"Счетчик ID-RLT синхронизирован. Следующее значение: {next_display}.",
            level=messages.SUCCESS,
        )
        return HttpResponseRedirect(reverse("admin:classifiers_app_businessentityrelationrecord_changelist"))
