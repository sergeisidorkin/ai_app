from django.db import migrations, models
from django.db.models import Max


def _split_macro_codes(apps, schema_editor):
    from projects_app.report_macro_code import (
        allocate_number,
        code_parts_are_valid,
        format_macro_code,
        split_catalog_title,
    )

    Macro = apps.get_model("projects_app", "ReportMacro")
    used: set[str] = set()
    for macro in Macro.objects.order_by("position", "id"):
        parsed = split_catalog_title(macro.name)
        if parsed:
            course, section, part, number, short_name = parsed
        elif code_parts_are_valid(macro.course, macro.section, getattr(macro, "part", ""), getattr(macro, "number", "")):
            used.add(format_macro_code(macro.course, macro.section, macro.part, macro.number))
            continue
        else:
            course, section, part = "MISC", "XX", "00"
            number = "00"
            short_name = (macro.name or "").strip()
        number = allocate_number(course, section, part, number, used)
        macro.course = course
        macro.section = section
        macro.part = part
        macro.number = number
        if short_name:
            macro.name = short_name[:255]
        macro.save(update_fields=["course", "section", "part", "number", "name"])


def _copy_rules_to_lines(apps, schema_editor):
    from projects_app.report_macro_code import allocate_number

    Macro = apps.get_model("projects_app", "ReportMacro")
    Rule = apps.get_model("projects_app", "ReportCheckRule")
    Line = apps.get_model("projects_app", "ReportCheckLine")
    used = {
        f"{macro.course}-{macro.section}-{macro.part}.{macro.number}"
        for macro in Macro.objects.all()
        if macro.course and macro.section and macro.part and macro.number
    }
    next_pos = int(Macro.objects.aggregate(m=Max("position")).get("m") or 0)
    for rule in Rule.objects.order_by("position", "id"):
        if rule.check_type == "macro":
            macros = list(rule.macros.all().order_by("position", "id"))
            for index, macro in enumerate(macros, start=1):
                Line.objects.create(
                    rule=rule,
                    position=index,
                    check_type="macro",
                    macro=macro,
                    finding_threshold=0,
                )
            continue
        skill_name = (rule.check_value or "").strip()
        model_id = (rule.model_id or "").strip()
        if not skill_name:
            continue
        macro = Macro.objects.filter(
            check_kind="skill",
            skill_name=skill_name,
            model_id=model_id,
        ).first()
        if macro is None:
            next_pos += 1
            number = allocate_number("DSKL", "SK", "00", "00", used)
            macro = Macro.objects.create(
                course="DSKL",
                section="SK",
                part="00",
                number=number,
                name=skill_name[:255],
                check_kind="skill",
                skill_name=skill_name[:255],
                model_id=model_id[:255],
                position=next_pos,
            )
        Line.objects.create(
            rule=rule,
            position=1,
            check_type="skill",
            macro=macro,
            finding_threshold=0,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0103_report_macro_check_kind"),
    ]

    operations = [
        migrations.AddField(
            model_name="reportmacro",
            name="part",
            field=models.CharField(blank=True, default="", max_length=2, verbose_name="Раздел"),
        ),
        migrations.AddField(
            model_name="reportmacro",
            name="number",
            field=models.CharField(blank=True, default="", max_length=2, verbose_name="Номер"),
        ),
        migrations.AddField(
            model_name="reportcheckrule",
            name="completion_mode",
            field=models.CharField(
                choices=[
                    ("sum", "Сумма замечаний"),
                    ("per_item", "Контроль порога макросов и навыков"),
                    ("sum_and_per_item", "Сумма замечаний с контролем порогов"),
                ],
                db_index=True,
                default="sum",
                max_length=32,
                verbose_name="Условия завершения",
            ),
        ),
        migrations.AddField(
            model_name="performerreportupload",
            name="check_finding_by_author",
            field=models.JSONField(blank=True, default=dict, verbose_name="Замечания по авторам"),
        ),
        migrations.CreateModel(
            name="ReportCheckLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("position", models.PositiveIntegerField(db_index=True, default=0, verbose_name="Позиция")),
                (
                    "check_type",
                    models.CharField(
                        choices=[("skill", "Навык"), ("macro", "Макрос")],
                        db_index=True,
                        default="macro",
                        max_length=16,
                        verbose_name="Тип проверки",
                    ),
                ),
                ("finding_threshold", models.PositiveIntegerField(default=0, verbose_name="Пороговое значение")),
                (
                    "macro",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="check_lines",
                        to="projects_app.reportmacro",
                        verbose_name="Название",
                    ),
                ),
                (
                    "rule",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="lines",
                        to="projects_app.reportcheckrule",
                        verbose_name="Запуск",
                    ),
                ),
            ],
            options={
                "verbose_name": "Строка запуска проверки",
                "verbose_name_plural": "Строки запуска проверки",
                "ordering": ["position", "id"],
            },
        ),
        migrations.RunPython(_split_macro_codes, migrations.RunPython.noop),
        migrations.RunPython(_copy_rules_to_lines, migrations.RunPython.noop),
        migrations.RemoveField(model_name="reportcheckrule", name="check_type"),
        migrations.RemoveField(model_name="reportcheckrule", name="check_value"),
        migrations.RemoveField(model_name="reportcheckrule", name="model_id"),
        migrations.RemoveField(model_name="reportcheckrule", name="macros"),
        migrations.AlterField(
            model_name="reportmacro",
            name="course",
            field=models.CharField(blank=True, default="", max_length=4, verbose_name="Курс"),
        ),
        migrations.AlterField(
            model_name="reportmacro",
            name="section",
            field=models.CharField(blank=True, default="", max_length=2, verbose_name="Секция"),
        ),
        migrations.AlterField(
            model_name="reportcheckrule",
            name="finding_threshold",
            field=models.PositiveIntegerField(default=0, verbose_name="Пороговое значение"),
        ),
        migrations.AlterModelOptions(
            name="reportcheckrule",
            options={
                "ordering": ["position", "id"],
                "verbose_name": "Запуск проверки отчёта",
                "verbose_name_plural": "Запуски проверки отчётов",
            },
        ),
        migrations.AddConstraint(
            model_name="reportmacro",
            constraint=models.UniqueConstraint(
                condition=(
                    ~models.Q(course="")
                    & ~models.Q(section="")
                    & ~models.Q(part="")
                    & ~models.Q(number="")
                ),
                fields=("course", "section", "part", "number"),
                name="uniq_report_macro_code",
            ),
        ),
    ]
