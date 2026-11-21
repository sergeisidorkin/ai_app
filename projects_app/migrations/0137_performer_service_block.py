from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0066_product_is_system_spec"),
        ("projects_app", "0136_sync_tpgr_curly_braces"),
    ]

    operations = [
        migrations.AddField(
            model_name="performer",
            name="service_block",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="spec_performer_items",
                to="policy_app.serviceblockclassifier",
                verbose_name="Блок услуг спецпроекта",
            ),
        ),
    ]
