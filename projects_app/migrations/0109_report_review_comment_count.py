from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0108_report_review_entry"),
    ]

    operations = [
        migrations.AddField(
            model_name="reportreviewentry",
            name="comment_count",
            field=models.PositiveIntegerField(default=0, verbose_name="Примечаний"),
        ),
    ]
