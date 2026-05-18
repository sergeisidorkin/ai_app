from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0043_typicalserviceterm_gantt_data"),
    ]

    operations = [
        migrations.AddField(
            model_name="typicalserviceterm",
            name="source_data_weeks",
            field=models.PositiveIntegerField(default=0, verbose_name="Сроки предоставления исходных данных, нед."),
        ),
    ]
