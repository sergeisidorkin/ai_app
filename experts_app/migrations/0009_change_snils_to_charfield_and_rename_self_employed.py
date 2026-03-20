# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("experts_app", "0008_add_contract_details_to_expert_profile"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "ALTER TABLE experts_app_expertprofile "
                "ALTER COLUMN snils TYPE varchar(14) USING COALESCE(snils::text, ''), "
                "ALTER COLUMN snils SET DEFAULT '', "
                "ALTER COLUMN snils SET NOT NULL;"
            ),
            reverse_sql=(
                "ALTER TABLE experts_app_expertprofile "
                "ALTER COLUMN snils DROP NOT NULL, "
                "ALTER COLUMN snils DROP DEFAULT, "
                "ALTER COLUMN snils TYPE date USING CASE WHEN snils = '' THEN NULL ELSE snils::date END;"
            ),
            state_operations=[
                migrations.AlterField(
                    model_name="expertprofile",
                    name="snils",
                    field=models.CharField("СНИЛС", max_length=14, blank=True, default=""),
                ),
            ],
        ),
        migrations.AlterField(
            model_name="expertprofile",
            name="self_employed",
            field=models.BooleanField("Самозанятость", default=False),
        ),
    ]
