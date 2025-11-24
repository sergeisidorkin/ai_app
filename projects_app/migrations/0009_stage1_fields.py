from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.validators import MinValueValidator
from django.db import migrations, models


def copy_input_data_forward(apps, schema_editor):
    ProjectRegistration = apps.get_model("projects_app", "ProjectRegistration")
    for pr in ProjectRegistration.objects.all():
        raw = (pr.input_data or "").strip()
        digits = "".join(ch for ch in raw if ch.isdigit())
        pr.input_data_days = int(digits) if digits else None
        pr.save(update_fields=["input_data_days"])


def copy_input_data_backward(apps, schema_editor):
    ProjectRegistration = apps.get_model("projects_app", "ProjectRegistration")
    for pr in ProjectRegistration.objects.all():
        pr.input_data = str(pr.input_data_days) if pr.input_data_days is not None else ""
        pr.save(update_fields=["input_data"])


def recalc_stage1_end(apps, schema_editor):
    ProjectRegistration = apps.get_model("projects_app", "ProjectRegistration")
    for pr in ProjectRegistration.objects.all():
        if not pr.contract_start:
            pr.stage1_end = None
        else:
            days = Decimal(pr.input_data or 0)
            weeks = Decimal(pr.stage1_weeks or 0) * Decimal("7")
            total = max(days + weeks, Decimal("0"))
            rounded = int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            pr.stage1_end = pr.contract_start + timedelta(days=rounded)
        pr.save(update_fields=["stage1_end"])


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0008_reformat_short_uid"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectregistration",
            name="input_data_days",
            field=models.PositiveIntegerField(
                verbose_name="Исх. данные, дней",
                null=True,
                blank=True,
            ),
        ),
        migrations.RunPython(copy_input_data_forward, copy_input_data_backward),
        migrations.RemoveField(model_name="projectregistration", name="input_data"),
        migrations.RenameField(
            model_name="projectregistration",
            old_name="input_data_days",
            new_name="input_data",
        ),
        migrations.AlterField(
            model_name="projectregistration",
            name="stage1_weeks",
            field=models.DecimalField(
                verbose_name="Этап 1, недель",
                max_digits=4,
                decimal_places=1,
                default=0,
                validators=[MinValueValidator(0)],
            ),
        ),
        migrations.RunPython(recalc_stage1_end, migrations.RunPython.noop),
    ]