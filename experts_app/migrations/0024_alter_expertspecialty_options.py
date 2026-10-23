from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("experts_app", "0023_expertspecialty_created_by"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="expertspecialty",
            options={
                "ordering": ["position", "id"],
                "verbose_name": "Специальность исполнителя",
                "verbose_name_plural": "Специальности исполнителей",
            },
        ),
    ]
