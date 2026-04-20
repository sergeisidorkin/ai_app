from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("experts_app", "0015_expertprofile_facsimile_file"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="expertprofile",
            name="yandex_mail",
        ),
    ]
