import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("group_app", "0004_orgunit_unit_type"),
        ("policy_app", "0014_create_group_project_head"),
    ]

    operations = [
        migrations.AddField(
            model_name="typicalsection",
            name="expertise_direction",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="typical_sections",
                to="group_app.orgunit",
                verbose_name="Направление экспертизы",
            ),
        ),
    ]
