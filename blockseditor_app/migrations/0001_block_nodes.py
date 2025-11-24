from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("blocks_app", "0005_block_product_block_section"),
    ]

    operations = [
        migrations.CreateModel(
            name="BlockNode",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(max_length=64, verbose_name="Системное имя")),
                ("title", models.CharField(max_length=150, verbose_name="Название")),
                ("node_type", models.CharField(choices=[("agent", "Агент"), ("checklist", "Статус чек-листа")], max_length=32, verbose_name="Тип узла")),
                ("display_order", models.PositiveIntegerField(default=0, verbose_name="Порядок показа")),
                ("position_x", models.PositiveIntegerField(default=0, verbose_name="Позиция X")),
                ("position_y", models.PositiveIntegerField(default=0, verbose_name="Позиция Y")),
                ("width", models.PositiveIntegerField(blank=True, null=True, verbose_name="Ширина")),
                ("height", models.PositiveIntegerField(blank=True, null=True, verbose_name="Высота")),
                ("payload", models.JSONField(blank=True, default=dict, verbose_name="Настройки узла")),
                ("meta", models.JSONField(blank=True, default=dict, verbose_name="Служебные данные")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("block", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="editor_nodes", to="blocks_app.block", verbose_name="Блок")),
            ],
            options={
                "ordering": ["display_order", "pk"],
                "unique_together": {("block", "slug")},
            },
        ),
    ]