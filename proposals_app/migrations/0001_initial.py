from django.db import migrations, models
import django.db.models.deletion
import django.core.validators


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("classifiers_app", "0013_legalentityrecord"),
        ("group_app", "0007_groupmember_country_order_number"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProposalRegistration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                (
                    "number",
                    models.PositiveIntegerField(
                        validators=[
                            django.core.validators.MinValueValidator(3333),
                            django.core.validators.MaxValueValidator(9999),
                        ],
                        verbose_name="Номер",
                    ),
                ),
                ("group", models.CharField(db_index=True, default="RU", max_length=2, verbose_name="Группа")),
                ("short_uid", models.CharField(blank=True, db_index=True, editable=False, max_length=32, unique=True, verbose_name="ТКП ID")),
                (
                    "kind",
                    models.CharField(
                        choices=[("regular", "Обычные"), ("owed_to_us", "Должны нам")],
                        db_index=True,
                        default="regular",
                        max_length=20,
                        verbose_name="Вид",
                    ),
                ),
                ("year", models.PositiveIntegerField(blank=True, null=True, verbose_name="Год")),
                ("customer", models.CharField(blank=True, max_length=255, verbose_name="Заказчик")),
                ("identifier", models.CharField(blank=True, default="", max_length=64, verbose_name="Идентификатор")),
                ("registration_number", models.CharField(blank=True, max_length=100, verbose_name="Регистрационный номер")),
                ("registration_date", models.DateField(blank=True, null=True, verbose_name="Дата регистрации")),
                (
                    "country",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="proposal_registrations",
                        to="classifiers_app.oksmcountry",
                        verbose_name="Страна",
                    ),
                ),
                (
                    "group_member",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="proposal_registrations",
                        to="group_app.groupmember",
                        verbose_name="Группа",
                    ),
                ),
            ],
            options={
                "verbose_name": "ТКП",
                "verbose_name_plural": "Реестр ТКП",
                "ordering": ["position", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="proposalregistration",
            constraint=models.UniqueConstraint(fields=("number", "group_member"), name="proposal_registration_identity_unique"),
        ),
    ]
