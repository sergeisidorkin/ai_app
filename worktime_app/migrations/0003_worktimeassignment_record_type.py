from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("worktime_app", "0002_personalworktimeweekassignment"),
    ]

    operations = [
        migrations.AddField(
            model_name="worktimeassignment",
            name="record_type",
            field=models.CharField(
                choices=[
                    ("tkp", "ТКП"),
                    ("project", "Проект"),
                    ("sick_leave", "Больничный"),
                    ("other_absence", "Прочее отсутствие"),
                    ("administration", "Администрирование"),
                    ("business_development", "Бизнес-девелопмент"),
                    ("strategic_development", "Стратегическое развитие"),
                    ("downtime", "Простой"),
                    ("time_off", "Отгул"),
                ],
                default="project",
                max_length=40,
                verbose_name="Вид записи",
            ),
        ),
    ]
