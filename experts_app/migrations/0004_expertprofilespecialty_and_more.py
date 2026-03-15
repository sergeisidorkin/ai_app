import django.db.models.deletion
from django.db import migrations, models


def copy_m2m_to_through(apps, schema_editor):
    """Copy existing M2M rows into the new through table with rank=row number."""
    ExpertProfileSpecialty = apps.get_model("experts_app", "ExpertProfileSpecialty")
    db = schema_editor.connection.alias
    cursor = schema_editor.connection.cursor()
    cursor.execute(
        "SELECT expertprofile_id, expertspecialty_id "
        "FROM experts_app_expertprofile_specialties "
        "ORDER BY expertprofile_id, id"
    )
    rows = cursor.fetchall()
    counters = {}
    to_create = []
    for profile_id, specialty_id in rows:
        counters[profile_id] = counters.get(profile_id, 0) + 1
        to_create.append(ExpertProfileSpecialty(
            profile_id=profile_id,
            specialty_id=specialty_id,
            rank=counters[profile_id],
        ))
    if to_create:
        ExpertProfileSpecialty.objects.using(db).bulk_create(to_create)


class Migration(migrations.Migration):

    dependencies = [
        ("experts_app", "0003_remove_expertprofile_specialty_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExpertProfileSpecialty",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("rank", models.PositiveIntegerField(default=1, verbose_name="Ранг")),
                ("profile", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ranked_specialties", to="experts_app.expertprofile")),
                ("specialty", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="profile_links", to="experts_app.expertspecialty")),
            ],
            options={
                "verbose_name": "Специальность профиля",
                "verbose_name_plural": "Специальности профиля",
                "ordering": ["rank"],
                "unique_together": {("profile", "specialty")},
            },
        ),
        migrations.RunPython(copy_m2m_to_through, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="expertprofile",
            name="specialties",
        ),
        migrations.AddField(
            model_name="expertprofile",
            name="specialties",
            field=models.ManyToManyField(
                blank=True,
                related_name="expert_profiles",
                through="experts_app.ExpertProfileSpecialty",
                to="experts_app.expertspecialty",
                verbose_name="Специальности",
            ),
        ),
    ]
