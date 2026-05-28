from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("proposals_app", "0054_backfill_sub_number_proposal_short_uids"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalcommercialoffer",
            name="code",
            field=models.CharField(blank=True, default="", max_length=100, verbose_name="Код"),
        ),
        migrations.AddField(
            model_name="proposalcommercialoffer",
            name="merge_without_code",
            field=models.BooleanField(default=False, verbose_name="Объединять без учета кода"),
        ),
    ]
