from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("policy_app", "0038_product_consulting_service_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="ConsultingDirection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Направление консалтинга",
                "verbose_name_plural": "Направления консалтинга",
                "ordering": ["position", "id"],
            },
        ),
        migrations.CreateModel(
            name="ConsultingDirectionType",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=128, unique=True, verbose_name="Вид консалтинга")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "direction",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="consulting_types",
                        to="policy_app.consultingdirection",
                        verbose_name="Направление консалтинга",
                    ),
                ),
            ],
            options={
                "verbose_name": "Вид консалтинга",
                "verbose_name_plural": "Виды консалтинга",
                "ordering": ["direction__position", "position", "id"],
            },
        ),
        migrations.CreateModel(
            name="ConsultingServiceType",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=128, verbose_name="Тип услуг")),
                ("code", models.CharField(max_length=32, verbose_name="Код")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "consulting_type",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="service_types",
                        to="policy_app.consultingdirectiontype",
                        verbose_name="Вид консалтинга",
                    ),
                ),
                (
                    "direction",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="service_types",
                        to="policy_app.consultingdirection",
                        verbose_name="Направление консалтинга",
                    ),
                ),
            ],
            options={
                "verbose_name": "Тип услуги консалтинга",
                "verbose_name_plural": "Типы услуг консалтинга",
                "ordering": ["direction__position", "consulting_type__position", "position", "id"],
            },
        ),
        migrations.CreateModel(
            name="ConsultingServiceSubtype",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, verbose_name="Подтип услуги")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "direction",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="service_subtypes",
                        to="policy_app.consultingdirection",
                        verbose_name="Направление консалтинга",
                    ),
                ),
                (
                    "service_type",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="service_subtypes",
                        to="policy_app.consultingservicetype",
                        verbose_name="Тип услуг",
                    ),
                ),
            ],
            options={
                "verbose_name": "Подтип услуги консалтинга",
                "verbose_name_plural": "Подтипы услуг консалтинга",
                "ordering": ["direction__position", "service_type__position", "position", "id"],
            },
        ),
        migrations.AlterField(
            model_name="product",
            name="consulting_type",
            field=models.CharField(blank=True, default="", max_length=128, verbose_name="Вид консалтинга"),
        ),
        migrations.AlterField(
            model_name="product",
            name="service_category",
            field=models.CharField(blank=True, default="", max_length=128, verbose_name="Тип услуг"),
        ),
        migrations.AlterField(
            model_name="product",
            name="service_code",
            field=models.CharField(blank=True, default="", max_length=32, verbose_name="Код"),
        ),
        migrations.AddField(
            model_name="product",
            name="consulting_type_ref",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="products",
                to="policy_app.consultingdirectiontype",
                verbose_name="Вид консалтинга",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="service_category_ref",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="products",
                to="policy_app.consultingservicetype",
                verbose_name="Тип услуг",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="service_subtype_ref",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="products",
                to="policy_app.consultingservicesubtype",
                verbose_name="Подтип услуги",
            ),
        ),
        migrations.AddConstraint(
            model_name="consultingservicetype",
            constraint=models.UniqueConstraint(
                fields=("consulting_type", "name"),
                name="ux_consulting_service_type_by_kind",
            ),
        ),
        migrations.AddConstraint(
            model_name="consultingservicesubtype",
            constraint=models.UniqueConstraint(
                fields=("service_type", "name"),
                name="ux_consulting_service_subtype_by_type",
            ),
        ),
    ]
