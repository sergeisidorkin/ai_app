from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("group_app", "0008_groupmember_seal_file"),
    ]

    operations = [
        migrations.AddField(
            model_name="groupmember",
            name="is_management_company",
            field=models.BooleanField(default=False, verbose_name="Управляющая компания"),
        ),
    ]
