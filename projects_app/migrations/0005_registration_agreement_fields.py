from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ("projects_app", "0004_performer"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectregistration",
            name="agreement_type",
            field=models.CharField(
                max_length=20,
                choices=[
                    ("MAIN", "Основной договор"),
                    ("ADDENDUM", "Допсоглашение"),
                ],
                default="MAIN",
                verbose_name="Вид соглашения",
                db_index=True,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="projectregistration",
            name="agreement_number",
            field=models.CharField(max_length=100, verbose_name="№ соглашения", blank=True),
        ),
        migrations.AddConstraint(
            model_name="projectregistration",
            constraint=models.UniqueConstraint(
                fields=("number", "group", "agreement_type", "agreement_number"),
                name="project_registration_identity_unique",
            ),
        ),
    ]