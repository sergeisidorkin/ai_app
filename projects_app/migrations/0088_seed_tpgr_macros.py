from django.db import migrations


def seed_tpgr_macros(apps, schema_editor):
    ReportMacro = apps.get_model("projects_app", "ReportMacro")
    from projects_app.report_macros import sync_tpgr_macros

    sync_tpgr_macros(ReportMacro)


def unseed_tpgr_macros(apps, schema_editor):
    ReportMacro = apps.get_model("projects_app", "ReportMacro")
    from projects_app.report_macros import TPGR_MACROS

    names = [item["name"] for item in TPGR_MACROS]
    ReportMacro.objects.filter(name__in=names).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0087_report_check_result_file"),
    ]

    operations = [
        migrations.RunPython(seed_tpgr_macros, unseed_tpgr_macros),
    ]
