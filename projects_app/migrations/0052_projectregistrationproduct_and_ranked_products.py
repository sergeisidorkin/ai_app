from django.db import migrations, models
import django.db.models.deletion


def backfill_ranked_project_products(apps, schema_editor):
    ProjectRegistration = apps.get_model("projects_app", "ProjectRegistration")
    ProjectRegistrationProduct = apps.get_model("projects_app", "ProjectRegistrationProduct")

    rows_to_create = []
    for registration in ProjectRegistration.objects.exclude(type_id__isnull=True).iterator():
        rows_to_create.append(
            ProjectRegistrationProduct(
                registration_id=registration.pk,
                product_id=registration.type_id,
                rank=1,
            )
        )
    if rows_to_create:
        ProjectRegistrationProduct.objects.bulk_create(rows_to_create, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0051_backfill_zero_padded_project_short_uids"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProjectRegistrationProduct",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("rank", models.PositiveIntegerField(default=1, verbose_name="Ранг")),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="project_registration_links",
                        to="policy_app.product",
                        verbose_name="Продукт",
                    ),
                ),
                (
                    "registration",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="product_links",
                        to="projects_app.projectregistration",
                        verbose_name="Регистрация проекта",
                    ),
                ),
            ],
            options={
                "verbose_name": "Продукт проекта",
                "verbose_name_plural": "Продукты проекта",
                "ordering": ["rank", "id"],
                "unique_together": {("registration", "product")},
            },
        ),
        migrations.AddField(
            model_name="projectregistration",
            name="products",
            field=models.ManyToManyField(
                blank=True,
                related_name="ranked_project_registrations",
                through="projects_app.ProjectRegistrationProduct",
                to="policy_app.product",
                verbose_name="Тип",
            ),
        ),
        migrations.RunPython(backfill_ranked_project_products, migrations.RunPython.noop),
    ]
