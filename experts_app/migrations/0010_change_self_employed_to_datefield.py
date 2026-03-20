# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("experts_app", "0009_change_snils_to_charfield_and_rename_self_employed"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "ALTER TABLE experts_app_expertprofile "
                "ALTER COLUMN self_employed DROP DEFAULT, "
                "ALTER COLUMN self_employed TYPE date USING CASE WHEN self_employed THEN CURRENT_DATE ELSE NULL END, "
                "ALTER COLUMN self_employed DROP NOT NULL;"
            ),
            reverse_sql=(
                "ALTER TABLE experts_app_expertprofile "
                "ALTER COLUMN self_employed TYPE boolean USING (self_employed IS NOT NULL), "
                "ALTER COLUMN self_employed SET DEFAULT false, "
                "ALTER COLUMN self_employed SET NOT NULL;"
            ),
            state_operations=[
                migrations.AlterField(
                    model_name="expertprofile",
                    name="self_employed",
                    field=models.DateField(
                        "Самозанятость (дата постановки на учет)",
                        null=True,
                        blank=True,
                    ),
                ),
            ],
        ),
    ]
