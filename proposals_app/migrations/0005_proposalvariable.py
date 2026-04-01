from django.db import migrations, models


def seed_proposal_variables(apps, schema_editor):
    ProposalVariable = apps.get_model("proposals_app", "ProposalVariable")
    ProposalVariable.objects.get_or_create(
        key="{{name}}",
        defaults={
            "description": "Наименование Заказчика",
            "position": 1,
            "source_section": "proposals",
            "source_table": "registry",
            "source_column": "customer",
        },
    )
    ProposalVariable.objects.get_or_create(
        key="{{country_full_name}}",
        defaults={
            "description": "Наименование страны полное",
            "position": 2,
            "source_section": "proposals",
            "source_table": "registry",
            "source_column": "country",
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0004_proposalregistration_type_and_name"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProposalVariable",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(max_length=255, verbose_name="Переменная")),
                ("description", models.CharField(blank=True, default="", max_length=512, verbose_name="Описание")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                ("source_section", models.CharField(blank=True, default="", max_length=50, verbose_name="Раздел")),
                ("source_table", models.CharField(blank=True, default="", max_length=50, verbose_name="Таблица")),
                ("source_column", models.CharField(blank=True, default="", max_length=100, verbose_name="Столбец")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Переменная шаблона ТКП",
                "verbose_name_plural": "Переменные шаблонов ТКП",
                "ordering": ["position", "id"],
            },
        ),
        migrations.RunPython(seed_proposal_variables, migrations.RunPython.noop),
    ]
