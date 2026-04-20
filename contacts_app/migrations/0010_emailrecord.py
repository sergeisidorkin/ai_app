from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contacts_app", "0009_contacts_actual_flags"),
    ]

    operations = [
        migrations.CreateModel(
            name="EmailRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.EmailField(blank=True, default="", max_length=254, verbose_name="Электронная почта")),
                ("valid_from", models.DateField(blank=True, null=True, verbose_name="Действ. от")),
                ("valid_to", models.DateField(blank=True, null=True, verbose_name="Действ. до")),
                ("is_active", models.BooleanField(default=True, verbose_name="Актуален")),
                ("record_date", models.DateField(blank=True, null=True, verbose_name="Дата записи")),
                ("record_author", models.CharField(blank=True, default="", max_length=255, verbose_name="Автор записи")),
                ("source", models.TextField(blank=True, default="", verbose_name="Источник")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "person",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="emails",
                        to="contacts_app.personrecord",
                        verbose_name="ID-PRS",
                    ),
                ),
            ],
            options={
                "verbose_name": "Адрес электронной почты",
                "verbose_name_plural": "Реестр адресов электронной почты",
                "ordering": ["position", "id"],
            },
        ),
    ]
