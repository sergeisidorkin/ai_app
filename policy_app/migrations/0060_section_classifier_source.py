import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def prepare_sections(apps, schema_editor):
    from policy_app.service_block_link import prepare_sections_for_required_service_block

    prepare_sections_for_required_service_block(
        apps.get_model("policy_app", "TypicalSection"),
        apps.get_model("policy_app", "ServiceBlockClassifier"),
        schema_editor,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0059_product_group"),
    ]

    operations = [
        migrations.AddField(
            model_name="serviceblockclassifier",
            name="name_en",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="Наименование раздела (услуги) на английском языке",
            ),
        ),
        migrations.AddField(
            model_name="serviceblockclassifier",
            name="name_ru",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="Наименование раздела (услуги) на русском языке",
            ),
        ),
        migrations.AlterField(
            model_name="serviceblockclassifier",
            name="code",
            field=models.CharField(
                error_messages={
                    "max_length": "Код должен состоять ровно из трёх латинских букв.",
                    "unique": "Блок услуг с таким кодом уже существует (без учёта регистра).",
                },
                help_text="Ровно три латинские буквы; сравнение без учёта регистра.",
                max_length=64,
                unique=True,
                validators=[
                    django.core.validators.RegexValidator(
                        message="Код должен состоять ровно из трёх латинских букв.",
                        regex="^[A-Za-z]{3}$",
                    )
                ],
                verbose_name="Код",
            ),
        ),
        migrations.RunPython(prepare_sections, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="typicalsection",
            name="service_block",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="typical_sections",
                to="policy_app.serviceblockclassifier",
                verbose_name="Блок услуг",
            ),
        ),
        migrations.RemoveField(
            model_name="typicalsection",
            name="specialties",
        ),
        migrations.DeleteModel(
            name="TypicalSectionSpecialty",
        ),
        migrations.RemoveField(
            model_name="typicalsection",
            name="short_name",
        ),
        migrations.RemoveField(
            model_name="typicalsection",
            name="short_name_ru",
        ),
        migrations.RemoveField(
            model_name="typicalsection",
            name="accounting_type",
        ),
        migrations.RemoveField(
            model_name="typicalsection",
            name="expertise_dir",
        ),
        migrations.RemoveField(
            model_name="typicalsection",
            name="expertise_direction",
        ),
        migrations.AddConstraint(
            model_name="typicalsection",
            constraint=models.UniqueConstraint(
                fields=("product", "service_block"),
                name="ux_section_product_service_block",
            ),
        ),
    ]
