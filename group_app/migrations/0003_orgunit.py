from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("group_app", "0002_groupmember_country_alpha2"),
    ]

    operations = [
        migrations.CreateModel(
            name="OrgUnit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("level", models.PositiveIntegerField(default=1, verbose_name="Уровень")),
                ("department_name", models.CharField(max_length=512, verbose_name="Наименование структурного подразделения")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="org_units",
                        to="group_app.groupmember",
                        verbose_name="Наименование компании (краткое)",
                    ),
                ),
                (
                    "functional_subordination",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="subordinates",
                        to="group_app.orgunit",
                        verbose_name="Функциональное подчинение",
                    ),
                ),
            ],
            options={
                "verbose_name": "Структурное подразделение",
                "verbose_name_plural": "Организационная структура",
                "ordering": ["position", "id"],
            },
        ),
    ]
