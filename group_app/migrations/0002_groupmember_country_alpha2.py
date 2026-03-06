from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("group_app", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="groupmember",
            name="country_alpha2",
            field=models.CharField(blank=True, default="", max_length=2, verbose_name="Буквенный код (Альфа-2)"),
        ),
    ]
