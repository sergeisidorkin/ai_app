from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0105_report_check_line_enabled"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReportCheckRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_sha256", models.CharField(db_index=True, max_length=64)),
                ("config_sha256", models.CharField(blank=True, default="", max_length=64)),
                ("status", models.CharField(choices=[("queued", "В очереди"), ("extracting", "Чтение документа"), ("running", "Проверка"), ("validating", "Проверка результатов"), ("rendering", "Вставка примечаний"), ("done", "Завершено"), ("partial", "Частично"), ("error", "Ошибка"), ("cancelled", "Отменено")], db_index=True, default="queued", max_length=16)),
                ("strategy", models.CharField(blank=True, default="", max_length=64)),
                ("clear_comments", models.BooleanField(default=False)),
                ("error", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("upload", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="check_runs", to="projects_app.performerreportupload")),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.CreateModel(
            name="ReportModelThrottle",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("route_key", models.CharField(max_length=320, unique=True)),
                ("active_token", models.CharField(blank=True, default="", max_length=64)),
                ("active_until", models.DateTimeField(blank=True, null=True)),
                ("cooldown_until", models.DateTimeField(blank=True, null=True)),
                ("last_started_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="ReportCheckChunk",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("skill_name", models.CharField(max_length=255)),
                ("skill_version", models.CharField(blank=True, default="", max_length=64)),
                ("model_id", models.CharField(blank=True, default="", max_length=255)),
                ("chunk_id", models.CharField(max_length=96)),
                ("ordinal", models.PositiveIntegerField(default=0)),
                ("total", models.PositiveIntegerField(default=0)),
                ("payload_sha256", models.CharField(max_length=64)),
                ("payload", models.JSONField(default=dict)),
                ("response", models.JSONField(blank=True, default=dict)),
                ("status", models.CharField(choices=[("pending", "Ожидает"), ("running", "Выполняется"), ("retry", "Повтор"), ("done", "Готово"), ("error", "Ошибка"), ("cancelled", "Отменено")], db_index=True, default="pending", max_length=16)),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("retry_at", models.DateTimeField(blank=True, null=True)),
                ("error", models.TextField(blank=True, default="")),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("line", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="check_chunks", to="projects_app.reportcheckline")),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="chunks", to="projects_app.reportcheckrun")),
            ],
            options={"ordering": ["ordinal", "id"]},
        ),
        migrations.CreateModel(
            name="ReportCheckFinding",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fingerprint", models.CharField(db_index=True, max_length=64)),
                ("status", models.CharField(choices=[("accepted", "Принято"), ("rejected", "Отклонено"), ("suppressed", "Подавлено"), ("placed", "Вставлено")], max_length=16)),
                ("rule_id", models.CharField(blank=True, default="", max_length=128)),
                ("anchor_id", models.CharField(blank=True, default="", max_length=255)),
                ("start", models.PositiveIntegerField(default=0)),
                ("end", models.PositiveIntegerField(default=0)),
                ("quote", models.TextField(blank=True, default="")),
                ("message", models.TextField(blank=True, default="")),
                ("replacement", models.TextField(blank=True, default="")),
                ("reason", models.TextField(blank=True, default="")),
                ("raw", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("chunk", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="findings", to="projects_app.reportcheckchunk")),
            ],
            options={"ordering": ["start", "end", "id"]},
        ),
        migrations.AddIndex(
            model_name="reportcheckrun",
            index=models.Index(fields=["upload", "source_sha256", "status"], name="projects_ap_upload__98f13e_idx"),
        ),
        migrations.AddConstraint(
            model_name="reportcheckchunk",
            constraint=models.UniqueConstraint(fields=("run", "line", "chunk_id"), name="uniq_report_check_chunk"),
        ),
        migrations.AddIndex(
            model_name="reportcheckchunk",
            index=models.Index(fields=["status", "retry_at"], name="projects_ap_status_2b34b5_idx"),
        ),
        migrations.AddConstraint(
            model_name="reportcheckfinding",
            constraint=models.UniqueConstraint(fields=("chunk", "fingerprint"), name="uniq_report_check_finding"),
        ),
    ]
