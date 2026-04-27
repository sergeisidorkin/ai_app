from django.db import migrations, models
import django.db.models.deletion


def copy_legacy_template_scope(apps, schema_editor):
    ProposalTemplate = apps.get_model("proposals_app", "ProposalTemplate")
    for template in ProposalTemplate.objects.all():
        if template.group_member_id:
            template.group_members.add(template.group_member_id)
        if template.product_id:
            template.products.add(template.product_id)


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):
    dependencies = [
        ("group_app", "0001_initial"),
        ("policy_app", "0042_servicegoalreport_product_name_and_report_title_label"),
        ("proposals_app", "0045_seed_payment_schedule_variable"),
    ]

    operations = [
        migrations.AlterField(
            model_name="proposaltemplate",
            name="group_member",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="proposal_templates",
                to="group_app.groupmember",
                verbose_name="Группа",
            ),
        ),
        migrations.AlterField(
            model_name="proposaltemplate",
            name="product",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="proposal_templates",
                to="policy_app.product",
                verbose_name="Продукт",
            ),
        ),
        migrations.AddField(
            model_name="proposaltemplate",
            name="group_members",
            field=models.ManyToManyField(
                blank=True,
                related_name="proposal_template_sets",
                to="group_app.groupmember",
                verbose_name="Группы",
            ),
        ),
        migrations.AddField(
            model_name="proposaltemplate",
            name="products",
            field=models.ManyToManyField(
                blank=True,
                related_name="proposal_template_sets",
                to="policy_app.product",
                verbose_name="Продукты",
            ),
        ),
        migrations.RunPython(copy_legacy_template_scope, noop_reverse),
    ]
