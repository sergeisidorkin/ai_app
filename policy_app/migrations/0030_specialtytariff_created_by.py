from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0029_specialtytariff"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="specialtytariff",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="specialty_tariffs",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Автор",
            ),
        ),
        migrations.AlterModelOptions(
            name="specialtytariff",
            options={
                "ordering": ["created_by", "position", "id"],
                "verbose_name": "Тариф специальностей",
                "verbose_name_plural": "Тарифы специальностей",
            },
        ),
    ]
