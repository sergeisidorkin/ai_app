from django.core import validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("worktime_app", "0005_worktimeassignment_proposal_registration"),
    ]

    operations = [
        migrations.AlterField(
            model_name="worktimeentry",
            name="hours",
            field=models.DecimalField(
                decimal_places=2,
                max_digits=5,
                validators=[validators.MinValueValidator(0), validators.MaxValueValidator(24)],
                verbose_name="Количество часов",
            ),
        ),
    ]
