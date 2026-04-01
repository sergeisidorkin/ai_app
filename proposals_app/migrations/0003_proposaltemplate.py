from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("group_app", "0007_groupmember_country_order_number"),
        ("policy_app", "0025_create_group_lawyer"),
        ("proposals_app", "0002_proposalregistration_contact_email_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProposalTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sample_name", models.CharField(max_length=512, verbose_name="Наименование образца")),
                ("version", models.CharField(blank=True, default="", max_length=128, verbose_name="Версия")),
                ("file", models.FileField(blank=True, default="", upload_to="proposal_templates/", verbose_name="Файл")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "group_member",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="proposal_templates",
                        to="group_app.groupmember",
                        verbose_name="Группа",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proposal_templates",
                        to="policy_app.product",
                        verbose_name="Продукт",
                    ),
                ),
            ],
            options={
                "verbose_name": "Образец шаблона ТКП",
                "verbose_name_plural": "Образцы шаблонов ТКП",
                "ordering": ["position", "id"],
            },
        ),
    ]
