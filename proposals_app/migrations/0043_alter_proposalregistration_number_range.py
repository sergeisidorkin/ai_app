from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0042_proposalregistration_stage_payloads_and_products"),
    ]

    operations = [
        migrations.AlterField(
            model_name="proposalregistration",
            name="number",
            field=models.PositiveIntegerField(
                validators=[MinValueValidator(0), MaxValueValidator(9999)],
                verbose_name="Номер",
            ),
        ),
    ]
