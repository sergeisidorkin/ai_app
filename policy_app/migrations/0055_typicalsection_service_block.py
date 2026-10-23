from django.db import migrations, models
import django.db.models.deletion


def link_sections(apps, schema_editor):
    from policy_app.service_block_link import link_typical_sections_to_service_blocks

    link_typical_sections_to_service_blocks(
        apps.get_model("policy_app", "TypicalSection"),
        apps.get_model("policy_app", "ServiceBlockClassifier"),
    )


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0054_policyexpertspecialty"),
    ]

    operations = [
        migrations.AddField(
            model_name="typicalsection",
            name="service_block",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="typical_sections",
                to="policy_app.serviceblockclassifier",
                verbose_name="Блок услуг",
            ),
        ),
        migrations.RunPython(link_sections, migrations.RunPython.noop),
    ]
