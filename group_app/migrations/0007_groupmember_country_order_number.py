from django.db import migrations, models


def forward(apps, schema_editor):
    GroupMember = apps.get_model("group_app", "GroupMember")
    counters = {}
    to_update = []

    for member in GroupMember.objects.order_by("position", "id"):
        key = (member.country_code or member.country_name or "").strip()
        next_number = counters.get(key, 0)
        if member.country_order_number != next_number:
            member.country_order_number = next_number
            to_update.append(member)
        counters[key] = next_number + 1

    if to_update:
        GroupMember.objects.bulk_update(to_update, ["country_order_number"])


def backward(apps, schema_editor):
    GroupMember = apps.get_model("group_app", "GroupMember")
    GroupMember.objects.exclude(country_order_number=0).update(country_order_number=0)


class Migration(migrations.Migration):

    dependencies = [
        ("group_app", "0006_orgunit_expertise_fk"),
    ]

    operations = [
        migrations.AddField(
            model_name="groupmember",
            name="country_order_number",
            field=models.PositiveIntegerField(db_index=True, default=0, editable=False, verbose_name="№"),
        ),
        migrations.RunPython(forward, backward),
    ]
