from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from contracts_app.models import ContractProjectRegistration
from policy_app.models import ServiceBlockClassifier
from policy_app.test_spec_product import seed_spec_catalog
from projects_app.models import Performer, ProjectRegistration, WorkVolume
from proposals_app.models import ProposalRegistration


class SpecProjectPerformerTests(TestCase):
    def setUp(self):
        self.spec = seed_spec_catalog()
        self.block = ServiceBlockClassifier.objects.create(
            code="GEO",
            short_name="geology",
            short_name_ru="геология",
            name_ru="Геология участка",
            accounting_type="Разделы",
            position=40,
        )
        self.other = ServiceBlockClassifier.objects.create(
            code="HYD",
            short_name="hydro",
            short_name_ru="гидрогеология",
            name_ru="Гидрогеология",
            accounting_type="Разделы",
            position=41,
        )

    def _contract(self, sections):
        return ContractProjectRegistration.objects.create(
            number=7701,
            name="Договор спецпроекта",
            type=self.spec,
            stage_payloads_json=[
                {
                    "product_id": str(self.spec.pk),
                    "service_sections_json": sections,
                }
            ],
        )

    def _project(self, **extra):
        payload = {
            "number": 8801,
            "name": "Проект спецпроекта",
            "type": self.spec,
        }
        payload.update(extra)
        return ProjectRegistration.objects.create(**payload)

    def test_performers_come_from_contract_and_are_kept(self):
        contract = self._contract(
            [
                {"service_name": "DSC", "code": "DSC"},
                {"service_name": "Ручное", "code": "GEO"},
                {"service_name": "Нет", "code": "QQQ"},
            ]
        )
        project = self._project(contract_project_registration=contract)
        WorkVolume.objects.create(project=project, name="Рудник", asset_name="Рудник", position=1)

        performers = list(Performer.objects.filter(registration=project).order_by("id"))
        self.assertEqual(len(performers), 1)
        self.assertIsNone(performers[0].typical_section_id)
        self.assertEqual(performers[0].service_block_id, self.block.pk)
        self.assertIsNone(performers[0].estimated_costs)
        self.assertEqual(performers[0].work_section_key, f"block-{self.block.pk}")

        performers[0].executor = "Иванов"
        performers[0].save(update_fields=["executor"])
        volume = project.work_items.get()
        volume.name = "Рудник"
        volume.save()

        performers = list(Performer.objects.filter(registration=project).order_by("id"))
        self.assertEqual(len(performers), 1)
        self.assertEqual(performers[0].executor, "Иванов")

    def test_renaming_asset_does_not_duplicate_spec_performers(self):
        contract = self._contract([{"service_name": "Геология участка", "code": "GEO"}])
        project = self._project(contract_project_registration=contract, number=8804)
        volume = WorkVolume.objects.create(project=project, name="Рудник", asset_name="Рудник", position=1)
        volume.asset_name = "Карьер"
        volume.save()

        performers = list(Performer.objects.filter(work_item=volume))
        self.assertEqual(len(performers), 1)
        self.assertEqual(performers[0].service_block_id, self.block.pk)
        self.assertEqual(performers[0].asset_name, "Карьер")

    @patch("projects_app.views.create_info_request_notifications")
    def test_spec_section_performer_can_receive_info_request(self, _notify):
        user = get_user_model().objects.create_user(username="spec-info", password="secret", is_staff=True)
        self.client.force_login(user)
        contract = self._contract([{"service_name": "Геология участка", "code": "GEO"}])
        project = self._project(contract_project_registration=contract, number=8805)
        WorkVolume.objects.create(project=project, name="Рудник", asset_name="Рудник", position=1)
        performer = Performer.objects.get(registration=project)
        performer.executor = "Иванов"
        performer.participation_response = Performer.ParticipationResponse.CONFIRMED
        performer.save(update_fields=["executor", "participation_response"])

        listed = self.client.get(reverse("performers_partial"))
        self.assertEqual(listed.status_code, 200)
        self.assertContains(listed, f'id="info-request-sel-{performer.pk}"')

        request_sent_at = timezone.localtime().replace(second=0, microsecond=0)
        response = self.client.post(
            reverse("info_request_approval"),
            {
                "performer_ids[]": [str(performer.pk)],
                "duration_hours": "48",
                "request_sent_at": request_sent_at.isoformat(timespec="minutes"),
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["ok"])
        performer.refresh_from_db()
        self.assertIsNotNone(performer.info_request_sent_at)

    def test_empty_contract_does_not_fall_through_to_proposal(self):
        proposal = ProposalRegistration.objects.create(
            number=6601,
            name="ТКП",
            type=self.spec,
            stage_payloads_json=[
                {
                    "product_id": str(self.spec.pk),
                    "service_sections_json": [{"service_name": "Гидрогеология", "code": "HYD"}],
                }
            ],
        )
        contract = self._contract([])
        project = self._project(
            contract_project_registration=contract,
            proposal_registration=proposal,
        )
        WorkVolume.objects.create(project=project, name="Пусто", asset_name="Пусто", position=1)
        self.assertFalse(Performer.objects.filter(registration=project).exists())

    def test_proposal_is_used_when_contract_is_missing(self):
        proposal = ProposalRegistration.objects.create(
            number=6602,
            name="ТКП без договора",
            type=self.spec,
            stage_payloads_json=[
                {
                    "product_id": str(self.spec.pk),
                    "service_sections_json": [{"service_name": "Гидрогеология", "code": "HYD"}],
                }
            ],
        )
        project = self._project(proposal_registration=proposal, number=8802)
        WorkVolume.objects.create(project=project, name="Карьер", asset_name="Карьер", position=1)
        performers = list(Performer.objects.filter(registration=project))
        self.assertEqual([item.service_block_id for item in performers], [self.other.pk])

    def test_no_source_means_no_performers(self):
        project = self._project(number=8803)
        WorkVolume.objects.create(project=project, name="Один", asset_name="Один", position=1)
        self.assertFalse(Performer.objects.filter(registration=project).exists())
