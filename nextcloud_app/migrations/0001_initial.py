from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="NextcloudUserLink",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nextcloud_user_id", models.CharField(max_length=255, unique=True, verbose_name="ID пользователя в Nextcloud")),
                ("nextcloud_username", models.CharField(blank=True, default="", max_length=255, verbose_name="Логин в Nextcloud")),
                ("nextcloud_email", models.EmailField(blank=True, default="", max_length=254, verbose_name="Email в Nextcloud")),
                ("last_synced_at", models.DateTimeField(blank=True, null=True, verbose_name="Последняя синхронизация")),
                ("source_payload", models.JSONField(blank=True, default=dict, verbose_name="Сырые данные Nextcloud")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="nextcloud_link",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Связка пользователя с Nextcloud",
                "verbose_name_plural": "Связки пользователей с Nextcloud",
            },
        ),
    ]
