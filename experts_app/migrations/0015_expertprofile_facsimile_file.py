from django.db import migrations, models

import experts_app.models


class Migration(migrations.Migration):

    dependencies = [
        ("experts_app", "0014_expertprofile_professional_status_short"),
    ]

    operations = [
        migrations.AddField(
            model_name="expertprofile",
            name="facsimile_file",
            field=models.FileField(
                blank=True,
                default="",
                upload_to=experts_app.models.expert_facsimile_upload_to,
                verbose_name="Факсимиле",
            ),
        ),
    ]
