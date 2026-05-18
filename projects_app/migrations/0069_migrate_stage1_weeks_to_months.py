import calendar
from datetime import date as dt_date, timedelta
from decimal import Decimal, ROUND_HALF_UP

import django.core.validators
from django.db import migrations, models


def _weeks_to_contract_months(value):
    weeks = Decimal(value or 0)
    if weeks < 0:
        weeks = Decimal("0")
    months = (weeks * Decimal("7")) / Decimal("30")
    return months.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def _contract_month_end_day(year, month):
    return calendar.monthrange(year, month)[1]


def _add_contract_months(value, months):
    if not value:
        return None
    safe_months = max(Decimal(months or 0), Decimal("0"))
    whole_months = int(safe_months)
    fractional_days = int(((safe_months - whole_months) * Decimal("30")) + Decimal("0.5"))
    month_index = (value.month - 1) + whole_months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, _contract_month_end_day(year, month))
    return dt_date(year, month, day) + timedelta(days=fractional_days)


def _add_stage2_weeks(value, weeks):
    if not value:
        return None
    safe_weeks = max(Decimal(weeks or 0), Decimal("0"))
    days = int((safe_weeks * Decimal("7")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return value + timedelta(days=days)


def _term_weeks(stage1_months, stage2_weeks):
    stage1 = (Decimal(stage1_months or 0) * Decimal("30")) / Decimal("7")
    stage2 = Decimal(stage2_weeks or 0)
    total = max(stage1 + stage2, Decimal("0"))
    return total.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def forwards(apps, schema_editor):
    ProjectRegistration = apps.get_model("projects_app", "ProjectRegistration")
    updates = []
    update_fields = ["stage1_weeks", "stage1_end", "stage2_end", "term_weeks", "completion_calc"]

    for registration in ProjectRegistration.objects.all().iterator(chunk_size=500):
        stage1_months = _weeks_to_contract_months(registration.stage1_weeks)
        stage1_end = _add_contract_months(registration.contract_start, stage1_months)
        stage2_end = _add_stage2_weeks(stage1_end, registration.stage2_weeks)

        registration.stage1_weeks = stage1_months
        registration.stage1_end = stage1_end
        registration.stage2_end = stage2_end
        registration.term_weeks = _term_weeks(stage1_months, registration.stage2_weeks)
        registration.completion_calc = stage2_end
        updates.append(registration)

        if len(updates) >= 500:
            ProjectRegistration.objects.bulk_update(updates, update_fields)
            updates = []

    if updates:
        ProjectRegistration.objects.bulk_update(updates, update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0068_drop_projectschedule"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="projectregistration",
            name="stage1_weeks",
            field=models.DecimalField(
                default=0,
                decimal_places=1,
                max_digits=4,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name="Срок подготовки Предварительного отчёта, мес.",
            ),
        ),
    ]
