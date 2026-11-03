from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0126_projectregistration_terms_columns"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectregistration",
            name="contract_end_enabled",
            field=models.BooleanField(default=True, verbose_name="Окончание договора включено"),
        ),
        migrations.AlterField(
            model_name="projectregistration",
            name="contract_end",
            field=models.DateField(blank=True, null=True, verbose_name="Окончание договора"),
        ),
    ]
