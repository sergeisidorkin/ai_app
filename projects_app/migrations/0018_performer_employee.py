from django.db import migrations, models
import django.db.models.deletion


def fill_performer_employee(apps, schema_editor):
    Performer = apps.get_model("projects_app", "Performer")
    Employee = apps.get_model("users_app", "Employee")

    employee_map = {}
    for employee in Employee.objects.select_related("user").all():
        user = employee.user
        parts = [
            (getattr(user, "last_name", "") or "").strip(),
            (getattr(user, "first_name", "") or "").strip(),
            (getattr(employee, "patronymic", "") or "").strip(),
        ]
        full_name = " ".join(part for part in parts if part).strip()
        if full_name and full_name not in employee_map:
            employee_map[full_name] = employee.id

    for performer in Performer.objects.all():
        normalized_executor = " ".join(str(performer.executor or "").split()).strip()
        employee_id = employee_map.get(normalized_executor)
        updates = {}
        if normalized_executor != performer.executor:
            updates["executor"] = normalized_executor
        if employee_id:
            updates["employee_id"] = employee_id
        if updates:
            Performer.objects.filter(pk=performer.pk).update(**updates)


class Migration(migrations.Migration):
    dependencies = [
        ("users_app", "0003_add_avatar"),
        ("projects_app", "0017_performer_participation_confirmation"),
    ]

    operations = [
        migrations.AddField(
            model_name="performer",
            name="employee",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="performers",
                to="users_app.employee",
                verbose_name="Сотрудник",
            ),
        ),
        migrations.RunPython(fill_performer_employee, migrations.RunPython.noop),
    ]
