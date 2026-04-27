from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0041_create_group_direction_director"),
    ]

    operations = [
        migrations.AlterField(
            model_name="servicegoalreport",
            name="report_title",
            field=models.TextField(
                blank=True,
                default="",
                verbose_name="Титул отчета/ТКП",
            ),
        ),
        migrations.AddField(
            model_name="servicegoalreport",
            name="product_name",
            field=models.TextField(
                blank=True,
                default="",
                verbose_name="Название продукта",
            ),
        ),
    ]
