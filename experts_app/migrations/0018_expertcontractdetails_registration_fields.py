from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("experts_app", "0017_expertcontractdetails"),
    ]

    operations = [
        migrations.AddField(
            model_name="expertcontractdetails",
            name="registration_building",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Регистрация: здание"),
        ),
        migrations.AddField(
            model_name="expertcontractdetails",
            name="registration_locality",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Регистрация: населенный пункт"),
        ),
        migrations.AddField(
            model_name="expertcontractdetails",
            name="registration_postal_code",
            field=models.CharField(blank=True, default="", max_length=32, verbose_name="Регистрация: индекс"),
        ),
        migrations.AddField(
            model_name="expertcontractdetails",
            name="registration_premise",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Регистрация: помещение"),
        ),
        migrations.AddField(
            model_name="expertcontractdetails",
            name="registration_premise_part",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Регистрация: часть помещения"),
        ),
        migrations.AddField(
            model_name="expertcontractdetails",
            name="registration_region",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Регистрация: регион"),
        ),
        migrations.AddField(
            model_name="expertcontractdetails",
            name="registration_street",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Регистрация: улица"),
        ),
    ]
