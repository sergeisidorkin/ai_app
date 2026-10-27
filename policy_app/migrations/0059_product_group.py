from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0058_product_accuracy"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="is_product_group",
            field=models.BooleanField(default=False, verbose_name="Групповой продукт"),
        ),
        migrations.AddField(
            model_name="product",
            name="group",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="grouped_products",
                to="policy_app.product",
                verbose_name="Групповой продукт",
            ),
        ),
    ]
