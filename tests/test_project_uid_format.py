import pytest

from blocks_app.views import (
    _extract_project_uid,
    _extract_project_uid_from_label,
    _folder_project_uid_from_name,
)
from checklists_app.views import _project_options
from contracts_app.models import ContractProjectRegistration
from group_app.models import GroupMember, resequence_group_members
from projects_app.models import ProjectRegistration
from proposals_app.models import ProposalRegistration


@pytest.mark.django_db
def test_project_short_uid_uses_product_stage_sequence_and_group_member_order():
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

    assert first_project.agreement_sequence == 1
    assert first_project.short_uid == "40000010RU"
    assert second_project.agreement_sequence == 2
    assert second_project.short_uid == "40000021RU"


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
    assert project.short_uid == "50000001RU"

    GroupMember.objects.filter(pk=first_member.pk).update(position=1)
    GroupMember.objects.filter(pk=second_member.pk).update(position=0)
    resequence_group_members()

    second_member.refresh_from_db()
    project.refresh_from_db()

    assert second_member.country_order_number == 0
    assert project.short_uid == "50000000RU"


def test_blocks_extract_project_uid_supports_new_format():
    assert _extract_project_uid("4444-00-1-0-RU") == "44440010RU"
    assert _extract_project_uid_from_label("44440010RU DD Test") == "44440010RU"
    assert _folder_project_uid_from_name("44440010RU DD Test") == "44440010RU"
    assert _extract_project_uid("4444-1-0-RU") == "444410RU"
    assert _extract_project_uid_from_label("444410RU DD Test") == "444410RU"
    assert _folder_project_uid_from_name("444410RU DD Test") == "444410RU"


@pytest.mark.django_db
def test_project_short_uid_uses_contract_project_sequence_digits():
    member = GroupMember.objects.create(
        short_name="IMC RU 1",
        country_name="Россия",
        country_code="643",
        country_alpha2="RU",
        position=0,
    )
    resequence_group_members(refresh_project_uids=False)
    proposal = ProposalRegistration.objects.create(
        number=7301,
        sub_number=4,
        group_member=member,
        name="Proposal TK",
    )
    contract = ContractProjectRegistration.objects.create(
        number=7401,
        sub_number=3,
        proposal_registration=proposal,
        group_member=member,
        name="Contract TK",
    )

    project = ProjectRegistration.objects.create(
        number=4444,
        group_member=member,
        contract_project_registration=contract,
        name="Project TK",
    )

    assert contract.short_uid == "7401430RU"
    assert project.short_uid == "44444300RU"


@pytest.mark.django_db
def test_project_short_uid_uses_zero_contract_sequence_when_contract_is_empty():
    member = GroupMember.objects.create(
        short_name="IMC RU 1",
        country_name="Россия",
        country_code="643",
        country_alpha2="RU",
        position=0,
    )
    resequence_group_members(refresh_project_uids=False)

    project = ProjectRegistration.objects.create(
        number=4444,
        group_member=member,
        name="Project without contract",
    )

    assert project.short_uid == "44440000RU"


@pytest.mark.django_db
def test_project_short_uid_refreshes_when_contract_project_changes():
    member = GroupMember.objects.create(
        short_name="IMC RU 1",
        country_name="Россия",
        country_code="643",
        country_alpha2="RU",
        position=0,
    )
    resequence_group_members(refresh_project_uids=False)
    proposal = ProposalRegistration.objects.create(
        number=7301,
        sub_number=4,
        group_member=member,
        name="Proposal TK",
    )
    first_contract = ContractProjectRegistration.objects.create(
        number=7401,
        sub_number=3,
        proposal_registration=proposal,
        group_member=member,
        name="Contract TK 43",
    )
    second_contract = ContractProjectRegistration.objects.create(
        number=7402,
        sub_number=5,
        group_member=member,
        name="Contract TK 05",
    )
    project = ProjectRegistration.objects.create(
        number=4444,
        group_member=member,
        name="Project changing contract",
    )

    assert project.short_uid == "44440000RU"

    project.contract_project_registration = first_contract
    project.save(update_fields=["contract_project_registration"])
    project.refresh_from_db()
    assert project.short_uid == "44444300RU"

    project.contract_project_registration = second_contract
    project.save(update_fields=["contract_project_registration"])
    project.refresh_from_db()
    assert project.short_uid == "44440500RU"

    project.contract_project_registration = None
    project.save(update_fields=["contract_project_registration"])
    project.refresh_from_db()
    assert project.short_uid == "44440000RU"


@pytest.mark.django_db
def test_project_short_uid_refreshes_when_linked_contract_id_changes():
    member = GroupMember.objects.create(
        short_name="IMC RU 1",
        country_name="Россия",
        country_code="643",
        country_alpha2="RU",
        position=0,
    )
    resequence_group_members(refresh_project_uids=False)
    proposal = ProposalRegistration.objects.create(
        number=7301,
        sub_number=4,
        group_member=member,
        name="Proposal TK",
    )
    contract = ContractProjectRegistration.objects.create(
        number=7401,
        sub_number=3,
        proposal_registration=proposal,
        group_member=member,
        name="Contract TK",
    )
    project = ProjectRegistration.objects.create(
        number=4444,
        group_member=member,
        contract_project_registration=contract,
        name="Project linked contract",
    )

    assert project.short_uid == "44444300RU"

    contract.sub_number = 5
    contract.save(update_fields=["sub_number"])
    project.refresh_from_db()

    assert contract.short_uid == "7401450RU"
    assert project.short_uid == "44444500RU"


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

    assert option["short_uid"] == "60000000KZ"
    assert option["code"] == "60000000KZ"


@pytest.mark.django_db
def test_proposal_short_uid_uses_sub_number_and_group_member_order():
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

    first_proposal = ProposalRegistration.objects.create(
        number=3546,
        sub_number=0,
        group_member=first_member,
        name="Proposal A",
    )
    duplicate_number = ProposalRegistration.objects.create(
        number=3546,
        sub_number=1,
        group_member=first_member,
        name="Proposal B",
    )
    second_group = ProposalRegistration.objects.create(
        number=3546,
        sub_number=0,
        group_member=second_member,
        name="Proposal C",
    )

    assert first_proposal.short_uid == "354600RU"
    assert duplicate_number.short_uid == "354610RU"
    assert second_group.short_uid == "354601RU"


@pytest.mark.django_db
def test_resequence_group_members_refreshes_proposal_short_uid():
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

    proposal = ProposalRegistration.objects.create(
        number=5000,
        sub_number=0,
        group_member=second_member,
        name="Proposal D",
    )
    assert proposal.short_uid == "500001RU"

    GroupMember.objects.filter(pk=first_member.pk).update(position=1)
    GroupMember.objects.filter(pk=second_member.pk).update(position=0)
    resequence_group_members()

    second_member.refresh_from_db()
    proposal.refresh_from_db()

    assert second_member.country_order_number == 0
    assert proposal.short_uid == "500000RU"
