from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("contracts_app", "0026_move_contract_details_variables_to_contracts"),
        ("projects_app", "0060_alter_performer_contract_signing_date"),
    ]

    operations = [
        migrations.CreateModel(
            name="ContractReturnComment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("contract_batch_id", models.UUIDField(blank=True, db_index=True, null=True, verbose_name="ID батча договора")),
                ("text", models.TextField(verbose_name="Комментарий")),
                (
                    "author_role",
                    models.CharField(
                        choices=[("lawyer", "Юрист"), ("expert", "Эксперт"), ("other", "Другое")],
                        db_index=True,
                        default="other",
                        max_length=16,
                        verbose_name="Роль автора",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")),
                (
                    "author",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="contract_return_comments",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Автор",
                    ),
                ),
                (
                    "performer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="contract_return_comments",
                        to="projects_app.performer",
                        verbose_name="Исполнитель договора",
                    ),
                ),
            ],
            options={
                "verbose_name": "Комментарий возврата договора",
                "verbose_name_plural": "Комментарии возврата договоров",
                "ordering": ["created_at", "id"],
            },
        ),
    ]
