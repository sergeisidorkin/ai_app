from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("classifiers_app", "0043_backfill_reorganization_events"),
    ]

    operations = [
        migrations.AlterField(
            model_name="businessentityrelationrecord",
            name="event",
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE,
                related_name="relations",
                to="classifiers_app.businessentityreorganizationevent",
                verbose_name="Событие реорганизации",
            ),
        ),
        migrations.RemoveField(
            model_name="businessentityrelationrecord",
            name="reorganization_event_uid",
        ),
        migrations.RemoveField(
            model_name="businessentityrelationrecord",
            name="relation_type",
        ),
        migrations.RemoveField(
            model_name="businessentityrelationrecord",
            name="event_date",
        ),
        migrations.RemoveField(
            model_name="businessentityrelationrecord",
            name="comment",
        ),
    ]
