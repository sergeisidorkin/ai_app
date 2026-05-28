import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0052_production_calendar_day_details"),
        ("contracts_app", "0029_update_chapters_name_description"),
        ("group_app", "0008_groupmember_seal_file"),
        ("policy_app", "0046_typicalsection_is_system_index"),
        ("proposals_app", "0054_backfill_sub_number_proposal_short_uids"),
    ]

    operations = [
        migrations.CreateModel(
            name="ContractProjectRegistration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                (
                    "number",
                    models.PositiveIntegerField(
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(9999),
                        ],
                        verbose_name="Номер",
                    ),
                ),
                (
                    "sub_number",
                    models.PositiveSmallIntegerField(
                        default=0,
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(9),
                        ],
                        verbose_name="№",
                    ),
                ),
                ("group", models.CharField(db_index=True, default="RU", max_length=2, verbose_name="Группа")),
                (
                    "agreement_sequence",
                    models.PositiveIntegerField(db_index=True, default=0, editable=False, verbose_name="№ этапа-продукта"),
                ),
                (
                    "agreement_type",
                    models.CharField(
                        choices=[("MAIN", "Основной договор"), ("ADDENDUM", "Допсоглашение")],
                        db_index=True,
                        default="MAIN",
                        max_length=20,
                        verbose_name="Вид соглашения",
                    ),
                ),
                ("agreement_number", models.CharField(blank=True, max_length=100, verbose_name="№ соглашения")),
                (
                    "name",
                    models.CharField(max_length=255, verbose_name="Название"),
                ),
                (
                    "short_uid",
                    models.CharField(blank=True, db_index=True, editable=False, max_length=32, unique=True, verbose_name="Договор ID"),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("Не начат", "Не начат"),
                            ("В работе", "В работе"),
                            ("На проверке", "На проверке"),
                            ("Завершён", "Завершён"),
                            ("Отложен", "Отложен"),
                        ],
                        default="Не начат",
                        max_length=20,
                        verbose_name="Статус",
                    ),
                ),
                ("year", models.PositiveIntegerField(blank=True, null=True, verbose_name="Год")),
                ("customer", models.CharField(blank=True, max_length=255, verbose_name="Заказчик")),
                ("identifier", models.CharField(blank=True, default="", max_length=64, verbose_name="Идентификатор")),
                ("registration_number", models.CharField(blank=True, max_length=100, verbose_name="Регистрационный номер")),
                ("registration_region", models.CharField(blank=True, default="", max_length=255, verbose_name="Регион")),
                ("registration_date", models.DateField(blank=True, null=True, verbose_name="Дата регистрации")),
                ("asset_owner", models.CharField(blank=True, default="", max_length=255, verbose_name="Владелец активов")),
                ("asset_owner_matches_customer", models.BooleanField(default=True, verbose_name="Совпадает с Заказчиком")),
                (
                    "asset_owner_identifier",
                    models.CharField(blank=True, default="", max_length=64, verbose_name="Идентификатор владельца активов"),
                ),
                (
                    "asset_owner_registration_number",
                    models.CharField(blank=True, default="", max_length=100, verbose_name="Регистрационный номер владельца активов"),
                ),
                ("asset_owner_region", models.CharField(blank=True, default="", max_length=255, verbose_name="Регион владельца активов")),
                (
                    "asset_owner_registration_date",
                    models.DateField(blank=True, null=True, verbose_name="Дата регистрации владельца активов"),
                ),
                ("project_manager", models.CharField(blank=True, max_length=255, verbose_name="Руководитель проекта")),
                (
                    "project_manager_prs_id",
                    models.CharField(blank=True, default="", max_length=32, verbose_name="ID-PRS руководителя проекта"),
                ),
                (
                    "asset_owner_country",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="contract_project_asset_owner_registrations",
                        to="classifiers_app.oksmcountry",
                        verbose_name="Страна владельца активов",
                    ),
                ),
                (
                    "country",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="contract_project_registrations",
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
                        related_name="contract_project_registrations",
                        to="group_app.groupmember",
                        verbose_name="Группа",
                    ),
                ),
                (
                    "proposal_registration",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="linked_contract_project_registrations",
                        to="proposals_app.proposalregistration",
                        verbose_name="ТКП ID",
                    ),
                ),
                (
                    "type",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="contract_project_registrations",
                        to="policy_app.product",
                        verbose_name="Тип",
                    ),
                ),
            ],
            options={
                "verbose_name": "Проект договора с клиентом",
                "verbose_name_plural": "Проекты договоров с клиентами",
                "ordering": ["position", "id"],
            },
        ),
        migrations.CreateModel(
            name="ContractProjectRegistrationProduct",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("rank", models.PositiveIntegerField(default=1, verbose_name="Ранг")),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="contract_project_registration_links",
                        to="policy_app.product",
                        verbose_name="Продукт",
                    ),
                ),
                (
                    "registration",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="product_links",
                        to="contracts_app.contractprojectregistration",
                        verbose_name="Проект договора с клиентом",
                    ),
                ),
            ],
            options={
                "verbose_name": "Продукт проекта договора",
                "verbose_name_plural": "Продукты проектов договоров",
                "ordering": ["rank", "id"],
                "unique_together": {("registration", "product")},
            },
        ),
        migrations.AddField(
            model_name="contractprojectregistration",
            name="products",
            field=models.ManyToManyField(
                blank=True,
                related_name="ranked_contract_project_registrations",
                through="contracts_app.ContractProjectRegistrationProduct",
                to="policy_app.product",
                verbose_name="Тип",
            ),
        ),
    ]
