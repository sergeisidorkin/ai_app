from django.db import migrations


def sync_macros(apps, schema_editor):
    ReportMacro = apps.get_model("projects_app", "ReportMacro")
    from projects_app.report_macros import sync_tpgr_macros

    sync_tpgr_macros(ReportMacro)


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0099_sync_tpgr_dash_quantity"),
    ]

    operations = [
        migrations.RunPython(sync_macros, migrations.RunPython.noop),
    ]
