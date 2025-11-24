from django.db import models
from blocks_app.models import Block


class BlockNode(models.Model):
    class NodeType(models.TextChoices):
        AGENT = "agent", "Агент"
        CHECKLIST = "checklist", "Статус чек-листа"

    block = models.ForeignKey(
        Block,
        on_delete=models.CASCADE,
        related_name="editor_nodes",
        verbose_name="Блок",
    )
    slug = models.SlugField("Системное имя", max_length=64)
    title = models.CharField("Название", max_length=150)
    node_type = models.CharField(
        "Тип узла",
        max_length=32,
        choices=NodeType.choices,
    )
    display_order = models.PositiveIntegerField("Порядок показа", default=0)

    position_x = models.PositiveIntegerField("Позиция X", default=0)
    position_y = models.PositiveIntegerField("Позиция Y", default=0)
    width = models.PositiveIntegerField("Ширина", null=True, blank=True)
    height = models.PositiveIntegerField("Высота", null=True, blank=True)

    payload = models.JSONField("Настройки узла", default=dict, blank=True)
    meta = models.JSONField("Служебные данные", default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "pk"]
        unique_together = ("block", "slug")
        verbose_name = "Узел редактора"
        verbose_name_plural = "Узлы редактора"

    def __str__(self):
        return f"{self.block_id}:{self.slug}"