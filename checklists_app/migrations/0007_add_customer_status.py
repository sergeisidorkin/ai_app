import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("checklists_app", "0006_add_project_workspace_and_checklist_item_folder"),
        ("projects_app", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ChecklistCustomerStatus",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(
                    choices=[
                        ("not_transferred", "Не передано"),
                        ("partial_transfer", "Передано частично"),
                        ("transferred", "Передано все"),
                        ("no_data", "Нет данных"),
                    ],
                    default="not_transferred",
                    max_length=32,
                )),
                ("status_changed_at", models.DateTimeField(null=True, blank=True, verbose_name="Дата изменения статуса")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("checklist_item", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="customer_statuses",
                    to="checklists_app.checklistitem",
                )),
                ("legal_entity", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="checklist_customer_statuses",
                    to="projects_app.legalentity",
                )),
                ("updated_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="checklist_customer_statuses",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "verbose_name": "Статус заказчика",
                "verbose_name_plural": "Статусы заказчика",
                "unique_together": {("checklist_item", "legal_entity")},
            },
        ),
        migrations.CreateModel(
            name="ChecklistCustomerStatusHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("previous_status", models.CharField(
                    blank=True,
                    choices=[
                        ("not_transferred", "Не передано"),
                        ("partial_transfer", "Передано частично"),
                        ("transferred", "Передано все"),
                        ("no_data", "Нет данных"),
                    ],
                    max_length=32,
                )),
                ("new_status", models.CharField(
                    choices=[
                        ("not_transferred", "Не передано"),
                        ("partial_transfer", "Передано частично"),
                        ("transferred", "Передано все"),
                        ("no_data", "Нет данных"),
                    ],
                    max_length=32,
                )),
                ("changed_at", models.DateTimeField(auto_now_add=True)),
                ("changed_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="checklist_customer_status_history",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("checklist_item", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="customer_status_history",
                    to="checklists_app.checklistitem",
                )),
                ("customer_status", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="history",
                    to="checklists_app.checklistcustomerstatus",
                )),
                ("legal_entity", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    to="projects_app.legalentity",
                )),
            ],
            options={
                "verbose_name": "История статуса заказчика",
                "verbose_name_plural": "История статусов заказчика",
                "ordering": ["-changed_at"],
            },
        ),
    ]
