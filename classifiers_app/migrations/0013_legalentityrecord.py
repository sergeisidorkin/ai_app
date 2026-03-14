from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0012_legalentityidentifier_code"),
    ]

    operations = [
        migrations.CreateModel(
            name="LegalEntityRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("short_name", models.CharField(max_length=512, verbose_name="Наименование (краткое)")),
                ("full_name", models.CharField(blank=True, default="", max_length=1024, verbose_name="Наименование (полное)")),
                ("identifier", models.CharField(blank=True, default="", max_length=255, verbose_name="Идентификатор")),
                ("registration_number", models.CharField(blank=True, default="", max_length=255, verbose_name="Регистрационный номер")),
                ("registration_date", models.DateField(blank=True, null=True, verbose_name="Дата регистрации")),
                ("registration_country", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="legal_entity_records", to="classifiers_app.oksmcountry", verbose_name="Страна регистрации")),
                ("record_date", models.DateField(blank=True, null=True, verbose_name="Дата записи")),
                ("record_author", models.CharField(blank=True, default="", max_length=255, verbose_name="Автор записи")),
                ("name_received_date", models.DateField(blank=True, null=True, verbose_name="Дата получения наименования")),
                ("name_changed_date", models.DateField(blank=True, null=True, verbose_name="Дата смены наименования")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Юридическое лицо",
                "verbose_name_plural": "Юридические лица",
                "ordering": ["position", "id"],
            },
        ),
    ]
