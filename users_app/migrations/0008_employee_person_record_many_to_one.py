from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users_app", "0007_backfill_employee_contact_sources"),
    ]

    operations = [
        migrations.AlterField(
            model_name="employee",
            name="person_record",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="employee_links",
                to="contacts_app.personrecord",
            ),
        ),
    ]
