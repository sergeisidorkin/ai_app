from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [("docops_queue", "0003_add_doc_key_and_indexes")]

    operations = [
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS docops_queu_doc_key_a59e87_idx "
            "ON docops_queue_job (doc_key, status);"
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS docops_queu_status_783057_idx "
            "ON docops_queue_job (status, priority DESC, created_at);"
        ),
    ]