from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.validators import MinValueValidator
from django.db import migrations, models


def recalc_stage_fields(apps, schema_editor):
    ProjectRegistration = apps.get_model("projects_app", "ProjectRegistration")
    for pr in ProjectRegistration.objects.all():
        # term_weeks = input_days / 7 + stage1 + stage2 + stage3
        days = Decimal(pr.input_data or 0) / Decimal("7")
        stage1 = Decimal(pr.stage1_weeks or 0)
        stage2 = Decimal(pr.stage2_weeks or 0)
        stage3 = Decimal(pr.stage3_weeks or 0)
        term = days + stage1 + stage2 + stage3
        if term < 0:
            term = Decimal("0")
        pr.term_weeks = term.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

        # completion_calc = stage2_end + stage3_weeks * 7
        if pr.stage2_end:
            stage3_days = Decimal(pr.stage3_weeks or 0) * Decimal("7")
            stage3_days = max(stage3_days, Decimal("0"))
            rounded_days = int(stage3_days.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            pr.completion_calc = pr.stage2_end + timedelta(days=rounded_days)
        else:
            pr.completion_calc = None

        pr.save(update_fields=["term_weeks", "completion_calc"])


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0010_stage2_decimal_defaults"),
    ]

    operations = [
        migrations.AlterField(
            model_name="projectregistration",
            name="stage3_weeks",
            field=models.DecimalField(
                verbose_name="Этап 3, недель",
                max_digits=4,
                decimal_places=1,
                default=0,
                validators=[MinValueValidator(0)],
            ),
        ),
        migrations.AlterField(
            model_name="projectregistration",
            name="term_weeks",
            field=models.DecimalField(
                verbose_name="Срок, недель",
                max_digits=5,
                decimal_places=1,
                default=0,
                validators=[MinValueValidator(0)],
                editable=False,
            ),
        ),
        migrations.RunPython(recalc_stage_fields, migrations.RunPython.noop),
    ]