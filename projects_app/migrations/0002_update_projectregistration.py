from django.db import migrations, models
import django.db.models.deletion
from django.core.validators import MinValueValidator, MaxValueValidator


def forwards(apps, schema_editor):
    ProjectRegistration = apps.get_model("projects_app", "ProjectRegistration")
    Product = apps.get_model("policy_app", "Product")

    # number (str) -> number_new (int 3333..9999)
    for row in ProjectRegistration.objects.all():
        raw = getattr(row, "number", None)
        num = None
        if isinstance(raw, int):
            num = raw
        elif isinstance(raw, str):
            s = "".join(ch for ch in raw if ch.isdigit())
            if s.isdigit():
                n = int(s)
                if 3333 <= n <= 9999:
                    num = n
        row.number_new = num
        row.save(update_fields=["number_new"])

    # type (str Product.short_name) -> type_fk (FK)
    for row in ProjectRegistration.objects.all():
        short = getattr(row, "type", None)
        fk_id = None
        if isinstance(short, str) and short.strip():
            prod = Product.objects.filter(short_name=short.strip()).only("id").first()
            if prod:
                fk_id = prod.id
        row.type_fk_id = fk_id
        row.save(update_fields=["type_fk"])


def backwards(apps, schema_editor):
    # Ничего не делаем при откате (можно дописать, если нужно)
    pass


class Migration(migrations.Migration):

    # ВАЖНО: если у тебя другой номер последней миграции в projects_app,
    # поставь его вместо "0001_initial".
    dependencies = [
        ("projects_app", "0001_initial"),
        ("policy_app", "0001_initial"),
    ]

    operations = [
        # 1) Добавляем новые поля
        migrations.AddField(
            model_name="projectregistration",
            name="group",
            field=models.CharField(
                verbose_name="Группа",
                max_length=2,
                choices=[("RU", "RU"), ("KZ", "KZ"), ("AM", "AM")],
                default="RU",
                db_index=True,
            ),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name="projectregistration",
            name="type_fk",
            field=models.ForeignKey(
                to="policy_app.product",
                on_delete=django.db.models.deletion.PROTECT,
                null=True,
                blank=True,
                related_name="project_registrations",
                verbose_name="Тип",
            ),
        ),
        migrations.AddField(
            model_name="projectregistration",
            name="number_new",
            field=models.PositiveIntegerField(
                verbose_name="Номер",
                validators=[MinValueValidator(3333), MaxValueValidator(9999)],
                null=True,
                blank=True,
            ),
        ),

        # 2) Перенос данных
        migrations.RunPython(forwards, backwards),

        # 3) Удаляем старые / переименовываем новые
        migrations.RemoveField(
            model_name="projectregistration",
            name="deadline_format",
        ),
        migrations.RemoveField(
            model_name="projectregistration",
            name="type",  # старое текстовое поле
        ),
        migrations.RenameField(
            model_name="projectregistration",
            old_name="type_fk",
            new_name="type",  # теперь это FK
        ),
        migrations.RemoveField(
            model_name="projectregistration",
            name="number",  # старое текстовое поле
        ),
        migrations.RenameField(
            model_name="projectregistration",
            old_name="number_new",
            new_name="number",  # теперь это int c валидаторами
        ),

        # 4) Прочие уточнения
        migrations.AlterField(
            model_name="projectregistration",
            name="year",
            field=models.PositiveIntegerField(null=True, blank=True, verbose_name="Год"),
        ),
        migrations.AlterField(
            model_name="projectregistration",
            name="status",
            field=models.CharField(
                verbose_name="Статус",
                max_length=20,
                choices=[
                    ("Не начат", "Не начат"),
                    ("В работе", "В работе"),
                    ("На проверке", "На проверке"),
                    ("Завершён", "Завершён"),
                    ("Отложен", "Отложен"),
                ],
                default="Не начат",
            ),
        ),
    ]