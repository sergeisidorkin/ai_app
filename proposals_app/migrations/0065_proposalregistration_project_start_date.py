from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0064_overall_term_unit_and_variable"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalregistration",
            name="project_start_date",
            field=models.DateField(blank=True, null=True, verbose_name="Дата начала проекта"),
        ),
    ]
