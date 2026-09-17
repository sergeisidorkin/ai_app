from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("checklists_app", "0017_checklist_sort_verify"),
    ]

    operations = [
        migrations.AddField(
            model_name="checklistsortproposal",
            name="verify_started_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Начало проверки"),
        ),
    ]
