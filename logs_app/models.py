from __future__ import annotations
import uuid
from django.conf import settings
from django.db import models

class LogEvent(models.Model):
    class Level(models.TextChoices):
        DEBUG = "DEBUG"
        INFO  = "INFO"
        WARN  = "WARN"
        ERROR = "ERROR"

    id = models.BigAutoField(primary_key=True)
    created_at    = models.DateTimeField(auto_now_add=True, db_index=True)
    level         = models.CharField(max_length=10, choices=Level.choices, default=Level.INFO, db_index=True)
    # короткое имя этапа (для удобной фильтрации)
    phase         = models.CharField(max_length=64, db_index=True)      # e.g. request, extract, onedrive, gdrive, llm, pipeline, job, deliver, ws, ack
    # конкретное событие в рамках этапа
    event         = models.CharField(max_length=128, db_index=True)     # e.g. block_run.start, code6.ok, share_url.ok, llm.done, pipeline.ok, job.enqueued, ws.sent, addin.applied
    # краткое сообщение
    message       = models.TextField(blank=True)

    # кто инициировал
    user          = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    email         = models.CharField(max_length=320, blank=True)

    # сквозные корреляционные идентификаторы
    trace_id      = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    request_id    = models.UUIDField(null=True, blank=True, db_index=True)
    job_id        = models.UUIDField(null=True, blank=True, db_index=True)

    # полезные поля для быстрых фильтров
    via           = models.CharField(max_length=16, blank=True)         # ws|queue
    project_code6 = models.CharField(max_length=16, blank=True)
    company       = models.CharField(max_length=255, blank=True)
    section       = models.CharField(max_length=64, blank=True)
    anchor_text   = models.CharField(max_length=256, blank=True)

    # длинные данные — в JSON
    data          = models.JSONField(default=dict, blank=True)

    # связанный документ (может быть длинным — TextField)
    doc_url       = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["trace_id", "phase"]),
            models.Index(fields=["job_id"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.level}] {self.phase}/{self.event} #{self.id}"