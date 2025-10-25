# ai_app/docops_queue/models.py
import uuid
from django.db import models
from django.utils import timezone
from django.contrib.postgres.fields import ArrayField

from docops_queue.urlkeys import make_doc_key

class Job(models.Model):
    class Status(models.TextChoices):
        QUEUED      = "queued", "Queued"
        ASSIGNED    = "assigned", "Assigned"     # выдан агенту (тот открыл Word)
        IN_PROGRESS = "in_progress", "In progress" # аддин забрал и вставляет
        DONE        = "done", "Done"
        FAILED      = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Документ
    doc_url = models.URLField(max_length=1000, blank=True, default="")                # веб-URL OneDrive/SharePoint (без query)
    doc_key = models.CharField(max_length=512, db_index=True, default="", blank=True)
    drive_id  = models.CharField(max_length=200, blank=True)
    item_id   = models.CharField(max_length=200, blank=True)
    trace_id = models.UUIDField(null=True, blank=True, db_index=True)

    # Что вставлять (DocOps блоки или ваш payload)
    payload   = models.JSONField()

    # Управление
    status    = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    priority  = models.IntegerField(default=10)
    assigned_agent = models.CharField(max_length=100, blank=True)
    attempts  = models.IntegerField(default=0)
    last_error= models.TextField(blank=True)

    created_at= models.DateTimeField(default=timezone.now)
    updated_at= models.DateTimeField(auto_now=True)

    # Метрики (по желанию)
    started_at= models.DateTimeField(null=True, blank=True)
    finished_at= models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        # авто-пересчёт doc_key при любом изменении doc_url
        try:
            new_key = make_doc_key(self.doc_url)
        except Exception:
            new_key = ""
        self.doc_key = new_key or ""
        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            models.Index(fields=["doc_key", "status"]),
            models.Index(fields=["status", "-priority", "created_at"]),
        ]

    def __str__(self):
        return f"{self.id} {self.status} {self.doc_url}"