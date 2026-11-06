from django.db import migrations, models
from django.db.models import Count, Q


def fill_product_usage_counts(apps, schema_editor):
    Product = apps.get_model("policy_app", "Product")
    ProjectRegistration = apps.get_model("projects_app", "ProjectRegistration")
    ProjectRegistrationProduct = apps.get_model("projects_app", "ProjectRegistrationProduct")
    parent_ids = ProjectRegistration.objects.filter(stage_project_id__isnull=False).values("stage_project_id")
    stages = ProjectRegistration.objects.filter(
        Q(stage_project_id__isnull=False)
        | (Q(stage_project_id__isnull=True) & ~Q(pk__in=parent_ids))
    )
    totals = {}
    for row in (
        ProjectRegistrationProduct.objects.filter(registration__in=stages)
        .values("product_id")
        .annotate(total=Count("registration_id", distinct=True))
    ):
        if row["product_id"]:
            totals[row["product_id"]] = row["total"]
    linked_registration_ids = ProjectRegistrationProduct.objects.filter(
        registration__in=stages
    ).values("registration_id")
    for row in (
        stages.exclude(pk__in=linked_registration_ids)
        .values("type_id")
        .annotate(total=Count("pk"))
    ):
        if row["type_id"]:
            totals[row["type_id"]] = totals.get(row["type_id"], 0) + row["total"]
    for product_id, total in totals.items():
        Product.objects.filter(pk=product_id).update(usage_count=total)


class Migration(migrations.Migration):

    dependencies = [
        ("policy_app", "0064_serviceblockclassifier_usage_count"),
        ("projects_app", "0133_report_review_entry_appealed_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="usage_count",
            field=models.PositiveIntegerField(
                db_index=True,
                default=0,
                editable=False,
                help_text="Сколько этапов реестра проектов используют продукт. Проект из одной строки тоже считается этапом.",
                verbose_name="Частота использования",
            ),
        ),
        migrations.RunPython(fill_product_usage_counts, migrations.RunPython.noop),
    ]
