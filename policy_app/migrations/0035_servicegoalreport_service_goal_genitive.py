from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("policy_app", "0034_remove_typicalsection_executor"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicegoalreport",
            name="service_goal_genitive",
            field=models.TextField(
                blank=True,
                default="",
                verbose_name="Цели оказания услуг в родительном падеже",
            ),
        ),
    ]
