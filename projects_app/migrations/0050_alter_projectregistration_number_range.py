from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0049_performer_work_hours"),
    ]

    operations = [
        migrations.AlterField(
            model_name="projectregistration",
            name="number",
            field=models.PositiveIntegerField(
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(9999),
                ],
                verbose_name="Номер",
            ),
        ),
    ]
