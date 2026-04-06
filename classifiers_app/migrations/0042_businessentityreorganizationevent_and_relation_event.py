from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0041_businessentityrelationrecord_reorganization_event_uid"),
    ]

    operations = [
        migrations.CreateModel(
            name="BusinessEntityReorganizationEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reorganization_event_uid", models.CharField(db_index=True, max_length=32, unique=True, verbose_name="ID-REO")),
                ("relation_type", models.CharField(blank=True, default="", max_length=255, verbose_name="Тип связи")),
                ("event_date", models.DateField(blank=True, null=True, verbose_name="Дата события")),
                ("comment", models.TextField(blank=True, default="", verbose_name="Комментарий")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Событие реорганизации",
                "verbose_name_plural": "События реорганизации",
                "ordering": ["position", "id"],
            },
        ),
        migrations.AddField(
            model_name="businessentityrelationrecord",
            name="event",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="relations",
                to="classifiers_app.businessentityreorganizationevent",
                verbose_name="Событие реорганизации",
            ),
        ),
    ]
