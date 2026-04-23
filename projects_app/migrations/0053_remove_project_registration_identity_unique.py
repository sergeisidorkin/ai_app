from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("projects_app", "0052_projectregistrationproduct_and_ranked_products"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="projectregistration",
            name="project_registration_identity_unique",
        ),
    ]
