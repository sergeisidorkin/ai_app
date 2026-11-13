from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0059_proposal_dispatch_recipients"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalregistration",
            name="version",
            field=models.PositiveIntegerField(default=1, verbose_name="Версия"),
        ),
        migrations.AlterField(
            model_name="proposalregistration",
            name="short_uid",
            field=models.CharField(
                blank=True,
                db_index=True,
                editable=False,
                max_length=32,
                verbose_name="ТКП ID",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="proposalregistration",
            name="proposal_registration_identity_unique",
        ),
        migrations.AddConstraint(
            model_name="proposalregistration",
            constraint=models.UniqueConstraint(
                fields=("number", "sub_number", "group_member", "version"),
                name="proposal_registration_identity_unique",
            ),
        ),
    ]
