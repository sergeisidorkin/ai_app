from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("policy_app", "0025_create_group_lawyer"),
        ("proposals_app", "0003_proposaltemplate"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalregistration",
            name="name",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Название"),
        ),
        migrations.AddField(
            model_name="proposalregistration",
            name="type",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="proposal_registrations",
                to="policy_app.product",
                verbose_name="Тип",
            ),
        ),
    ]
