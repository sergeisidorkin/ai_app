from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("checklists_app", "0018_checklist_sort_verify_started_at"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="checklistsortproposal",
            name="verify_started_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="checklist_sort_verifications",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
