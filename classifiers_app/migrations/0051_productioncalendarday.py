from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0050_oksmcountry_short_name_genitive"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductionCalendarDay",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(db_index=True, verbose_name="Дата")),
                ("is_weekend", models.BooleanField(default=False, verbose_name="Выходной день")),
                ("is_holiday", models.BooleanField(default=False, verbose_name="Официальный праздник")),
                ("is_working_day", models.BooleanField(default=True, verbose_name="Рабочий день")),
                ("holiday_name", models.CharField(blank=True, default="", max_length=512, verbose_name="Название праздника")),
                ("source", models.CharField(blank=True, default="", max_length=255, verbose_name="Источник")),
                ("is_manual", models.BooleanField(default=False, verbose_name="Ручная корректировка")),
                ("comment", models.TextField(blank=True, default="", verbose_name="Комментарий")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "country",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="production_calendar_days",
                        to="classifiers_app.oksmcountry",
                        verbose_name="Страна",
                    ),
                ),
            ],
            options={
                "verbose_name": "День производственного календаря",
                "verbose_name_plural": "Производственный календарь",
                "ordering": ["country__short_name", "date", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="productioncalendarday",
            index=models.Index(fields=["country", "date"], name="pcd_country_date_idx"),
        ),
        migrations.AddConstraint(
            model_name="productioncalendarday",
            constraint=models.UniqueConstraint(
                fields=("country", "date"),
                name="production_calendar_unique_country_date",
            ),
        ),
    ]
