from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("contacts_app", "0013_user_management_fields"),
        ("users_app", "0004_employee_department"),
    ]

    operations = [
        migrations.AddField(
            model_name="employee",
            name="managed_email_record",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="employee_email_link",
                to="contacts_app.emailrecord",
            ),
        ),
        migrations.AddField(
            model_name="employee",
            name="managed_position_record",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="employee_position_link",
                to="contacts_app.positionrecord",
            ),
        ),
        migrations.AddField(
            model_name="employee",
            name="person_record",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="employee_link",
                to="contacts_app.personrecord",
            ),
        ),
        migrations.RemoveField(
            model_name="employee",
            name="phone",
        ),
    ]
