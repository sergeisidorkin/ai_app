from django.db import migrations


def sync_macros(apps, schema_editor):
    ReportMacro = apps.get_model("projects_app", "ReportMacro")
    from projects_app.report_macros import sync_tpgr_macros

    sync_tpgr_macros(ReportMacro)


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0095_report_check_claim"),
    ]

    operations = [
        migrations.RunPython(sync_macros, migrations.RunPython.noop),
    ]
