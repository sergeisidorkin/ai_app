from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("contacts_app", "0019_alter_personrecord_gender"),
        ("experts_app", "0020_alter_expertcontractdetails_gender"),
    ]

    operations = [
        migrations.CreateModel(
            name="SpecialtyRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("valid_from", models.DateField(blank=True, null=True, verbose_name="Действ. от")),
                ("valid_to", models.DateField(blank=True, null=True, verbose_name="Действ. до")),
                ("is_active", models.BooleanField(default=True, verbose_name="Актуален")),
                ("is_user_managed", models.BooleanField(default=False, verbose_name="Управляется пользователем")),
                (
                    "user_kind",
                    models.CharField(
                        blank=True,
                        choices=[("employee", "Сотрудник"), ("external", "Внешний пользователь")],
                        default="",
                        max_length=16,
                        verbose_name="Пользователь",
                    ),
                ),
                ("record_date", models.DateField(blank=True, null=True, verbose_name="Дата записи")),
                ("record_author", models.CharField(blank=True, default="", max_length=255, verbose_name="Автор записи")),
                ("source", models.TextField(blank=True, default="", verbose_name="Источник")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "person",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="specialty_records",
                        to="contacts_app.personrecord",
                        verbose_name="ID-PRS",
                    ),
                ),
                (
                    "specialty",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="contact_records",
                        to="experts_app.expertspecialty",
                        verbose_name="Специальность",
                    ),
                ),
            ],
            options={
                "verbose_name": "Специальность",
                "verbose_name_plural": "Реестр специальностей",
                "ordering": ["position", "id"],
            },
        ),
    ]
