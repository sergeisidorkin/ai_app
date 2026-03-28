import pytest

from blocks_app.views import (
    _extract_project_uid,
    _extract_project_uid_from_label,
    _folder_project_uid_from_name,
)
from checklists_app.views import _project_options
from group_app.models import GroupMember, resequence_group_members
from projects_app.models import ProjectRegistration


@pytest.mark.django_db
def test_project_short_uid_uses_agreement_sequence_and_group_member_order():
    first_member = GroupMember.objects.create(
        short_name="IMC RU 1",
        country_name="Россия",
        country_code="643",
        country_alpha2="RU",
        position=0,
    )
    second_member = GroupMember.objects.create(
        short_name="IMC RU 2",
        country_name="Россия",
        country_code="643",
        country_alpha2="RU",
        position=1,
    )
    resequence_group_members(refresh_project_uids=False)

    first_project = ProjectRegistration.objects.create(
        number=4000,
        group_member=first_member,
        name="Project A",
    )
    second_project = ProjectRegistration.objects.create(
        number=4000,
        group_member=second_member,
        name="Project B",
    )

    first_project.refresh_from_db()
    second_project.refresh_from_db()

    assert first_project.agreement_sequence == 0
    assert first_project.short_uid == "400000RU"
    assert second_project.agreement_sequence == 1
    assert second_project.short_uid == "400011RU"


@pytest.mark.django_db
def test_resequence_group_members_refreshes_project_short_uid():
    first_member = GroupMember.objects.create(
        short_name="IMC RU 1",
        country_name="Россия",
        country_code="643",
        country_alpha2="RU",
        position=0,
    )
    second_member = GroupMember.objects.create(
        short_name="IMC RU 2",
        country_name="Россия",
        country_code="643",
        country_alpha2="RU",
        position=1,
    )
    resequence_group_members(refresh_project_uids=False)

    project = ProjectRegistration.objects.create(
        number=5000,
        group_member=second_member,
        name="Project C",
    )
    assert project.short_uid == "500001RU"

    GroupMember.objects.filter(pk=first_member.pk).update(position=1)
    GroupMember.objects.filter(pk=second_member.pk).update(position=0)
    resequence_group_members()

    second_member.refresh_from_db()
    project.refresh_from_db()

    assert second_member.country_order_number == 0
    assert project.short_uid == "500000RU"


def test_blocks_extract_project_uid_supports_new_format():
    assert _extract_project_uid("4444-1-0-RU") == "444410RU"
    assert _extract_project_uid_from_label("444410RU DD Test") == "444410RU"
    assert _folder_project_uid_from_name("444410RU DD Test") == "444410RU"


@pytest.mark.django_db
def test_checklists_project_options_use_new_project_uid():
    member = GroupMember.objects.create(
        short_name="IMC KZ 1",
        country_name="Казахстан",
        country_code="398",
        country_alpha2="KZ",
        position=0,
    )
    resequence_group_members(refresh_project_uids=False)
    project = ProjectRegistration.objects.create(
        number=6000,
        group_member=member,
        name="Project D",
    )

    options = _project_options()
    option = next(item for item in options if item["id"] == project.id)

    assert option["short_uid"] == "600000KZ"
    assert option["code"] == "600000KZ"
