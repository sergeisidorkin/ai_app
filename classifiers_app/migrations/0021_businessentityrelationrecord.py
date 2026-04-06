from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0020_businessentitylegaladdressrecord"),
    ]

    operations = [
        migrations.CreateModel(
            name="BusinessEntityRelationRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("relation_type", models.CharField(blank=True, default="", max_length=255, verbose_name="Тип связи")),
                ("event_date", models.DateField(blank=True, null=True, verbose_name="Дата события")),
                ("comment", models.TextField(blank=True, default="", verbose_name="Комментарий")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("from_business_entity", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="outgoing_relations", to="classifiers_app.businessentityrecord", verbose_name="От ID-BSN")),
                ("to_business_entity", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="incoming_relations", to="classifiers_app.businessentityrecord", verbose_name="К ID-BSN")),
            ],
            options={
                "verbose_name": "Связь бизнес-сущностей",
                "verbose_name_plural": "Реестр реорганизаций",
                "ordering": ["position", "id"],
            },
        ),
    ]
