from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("checklists_app", "0016_checklist_sort_local_inbox"),
    ]

    operations = [
        migrations.AddField(
            model_name="checklistsortproposal",
            name="verify_status",
            field=models.CharField(blank=True, default="", max_length=16, verbose_name="Статус проверки"),
        ),
        migrations.AddField(
            model_name="checklistsortproposal",
            name="verify_error",
            field=models.TextField(blank=True, default="", verbose_name="Ошибка проверки"),
        ),
    ]
