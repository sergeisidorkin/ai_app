from django.db import migrations, models


def fill_usage_counts(apps, schema_editor):
    ServiceBlockClassifier = apps.get_model("policy_app", "ServiceBlockClassifier")
    TypicalSection = apps.get_model("policy_app", "TypicalSection")
    counts = (
        TypicalSection.objects.values("service_block_id")
        .annotate(total=models.Count("pk"))
    )
    for row in counts:
        block_id = row["service_block_id"]
        if not block_id:
            continue
        ServiceBlockClassifier.objects.filter(pk=block_id).update(usage_count=row["total"])


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0063_delete_group_projects_head"),
    ]

    operations = [
        migrations.AddField(
            model_name="serviceblockclassifier",
            name="usage_count",
            field=models.PositiveIntegerField(
                db_index=True,
                default=0,
                editable=False,
                help_text="Сколько раз блок входит в состав продуктов: число строк таблицы «Типовые блоки услуг».",
                verbose_name="Частота использования",
            ),
        ),
        migrations.RunPython(fill_usage_counts, migrations.RunPython.noop),
    ]
