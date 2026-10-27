from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0057_create_group_projects_coordinator"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="accuracy",
            field=models.CharField(
                blank=True,
                choices=[
                    (">50%", ">50%"),
                    ("±30–50%", "±30–50%"),
                    ("±20–30%", "±20–30%"),
                    ("±10–20%", "±10–20%"),
                    ("<10%", "<10%"),
                ],
                default="",
                max_length=16,
                verbose_name="Точность",
            ),
        ),
    ]
