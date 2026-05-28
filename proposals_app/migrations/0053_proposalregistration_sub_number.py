from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("proposals_app", "0052_seed_stage_terms_variable"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposalregistration",
            name="sub_number",
            field=models.PositiveSmallIntegerField(
                default=0,
                validators=[MinValueValidator(0), MaxValueValidator(9)],
                verbose_name="№",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="proposalregistration",
            name="proposal_registration_identity_unique",
        ),
        migrations.AddConstraint(
            model_name="proposalregistration",
            constraint=models.UniqueConstraint(
                fields=("number", "sub_number", "group_member"),
                name="proposal_registration_identity_unique",
            ),
        ),
    ]
