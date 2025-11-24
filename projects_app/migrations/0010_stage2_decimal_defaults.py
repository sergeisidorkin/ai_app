from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.validators import MinValueValidator
from django.db import migrations, models


def recalc_stage2_end(apps, schema_editor):
    ProjectRegistration = apps.get_model("projects_app", "ProjectRegistration")
    for pr in ProjectRegistration.objects.all():
        if not pr.stage1_end:
            pr.stage2_end = None
        else:
            weeks = Decimal(pr.stage2_weeks or 0) * Decimal("7")
            total = max(weeks, Decimal("0"))
            rounded = int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            pr.stage2_end = pr.stage1_end + timedelta(days=rounded)
        pr.save(update_fields=["stage2_end"])


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0009_stage1_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="projectregistration",
            name="input_data",
            field=models.PositiveIntegerField(
                "Исх. данные, дней",
                null=True,
                blank=True,
                default=0,
            ),
        ),
        migrations.AlterField(
            model_name="projectregistration",
            name="stage2_weeks",
            field=models.DecimalField(
                "Этап 2, недель",
                max_digits=4,
                decimal_places=1,
                default=0,
                validators=[MinValueValidator(0)],
            ),
        ),
        migrations.RunPython(recalc_stage2_end, migrations.RunPython.noop),
    ]