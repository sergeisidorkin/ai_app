from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [
        ('requests_app', '0005_backfill_requestitem_table'),
    ]
    operations = [
        migrations.AlterField(
            model_name='requestitem',
            name='table',
            field=models.ForeignKey(
                to='requests_app.requesttable',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='items',
                null=False, blank=False,
            ),
        ),
    ]