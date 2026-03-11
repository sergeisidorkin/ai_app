from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("group_app", "0003_orgunit"),
        ("users_app", "0003_add_avatar"),
    ]

    operations = [
        migrations.AddField(
            model_name="employee",
            name="department",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="employees",
                to="group_app.orgunit",
                verbose_name="Подразделение",
            ),
        ),
    ]
