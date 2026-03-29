from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="CloudStorageSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "primary_storage",
                    models.CharField(
                        choices=[("yandex_disk", "Яндекс Диск"), ("nextcloud", "Nextcloud")],
                        default="yandex_disk",
                        max_length=32,
                        verbose_name="Основное облачное хранилище",
                    ),
                ),
                ("nextcloud_root_path", models.CharField(blank=True, default="", max_length=1024, verbose_name="Корневой каталог Nextcloud")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлено")),
            ],
            options={
                "verbose_name": "Основное облачное хранилище",
                "verbose_name_plural": "Основное облачное хранилище",
            },
        ),
    ]
