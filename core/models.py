from django.db import models


class CloudStorageSettings(models.Model):
    class PrimaryStorage(models.TextChoices):
        YANDEX_DISK = "yandex_disk", "Яндекс Диск"
        NEXTCLOUD = "nextcloud", "Nextcloud"

    singleton_pk = 1

    primary_storage = models.CharField(
        "Основное облачное хранилище",
        max_length=32,
        choices=PrimaryStorage.choices,
        default=PrimaryStorage.YANDEX_DISK,
    )
    nextcloud_root_path = models.CharField(
        "Корневой каталог Nextcloud",
        max_length=1024,
        blank=True,
        default="",
    )
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Основное облачное хранилище"
        verbose_name_plural = "Основное облачное хранилище"

    def save(self, *args, **kwargs):
        self.pk = self.singleton_pk
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        return

    @classmethod
    def get_solo(cls):
        obj, _created = cls.objects.get_or_create(pk=cls.singleton_pk)
        return obj

    def __str__(self):
        return self.get_primary_storage_display()
