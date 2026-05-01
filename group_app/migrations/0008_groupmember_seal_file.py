import group_app.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("group_app", "0007_groupmember_country_order_number"),
    ]

    operations = [
        migrations.AddField(
            model_name="groupmember",
            name="seal_file",
            field=models.FileField(
                blank=True,
                default="",
                upload_to=group_app.models.group_member_seal_upload_to,
                verbose_name="Печать",
            ),
        ),
    ]
