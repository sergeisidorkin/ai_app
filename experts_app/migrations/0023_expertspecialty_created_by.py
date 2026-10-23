import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("experts_app", "0022_expertspecialty_specialization_area"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="expertspecialty",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="created_expert_specialties",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Автор",
            ),
        ),
    ]
