from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("projects_app", "0075_performer_payment_paid_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectregistration",
            name="sub_number",
            field=models.PositiveSmallIntegerField(
                default=0,
                validators=[MinValueValidator(0), MaxValueValidator(9)],
                verbose_name="№",
            ),
        ),
    ]
