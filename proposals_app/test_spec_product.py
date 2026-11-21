import json
import tempfile
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from django.test import TestCase, override_settings

from contracts_app.forms import ContractProjectRegistrationForm
from policy_app.models import ServiceBlockClassifier
from policy_app.test_spec_product import seed_spec_catalog
from proposals_app.document_generation import _media_url_for_path, delete_proposal_scan_file
from proposals_app.forms import ProposalRegistrationForm
from proposals_app.variable_resolver import (
    _proposal_product_name,
    _proposal_report_title,
    _proposal_service_goal,
    _proposal_service_goal_genitive,
)


class SpecCompositionFormTests(TestCase):
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
        self.proposal_form = ProposalRegistrationForm.__new__(ProposalRegistrationForm)
        self.contract_form = ContractProjectRegistrationForm.__new__(ContractProjectRegistrationForm)

    def test_known_code_is_rewritten_and_unknown_code_is_dropped(self):
        raw = json.dumps(
            [
                {"service_name": "Ручное имя", "code": "GEO"},
                {"service_name": "Чужой", "code": "QQQ"},
                {"service_name": "DSC", "code": "DSC"},
            ]
        )
        rows = self.proposal_form._normalize_stage_service_sections(raw, row_index=1, product=self.spec)
        self.assertEqual([row["code"] for row in rows], ["DSC", "GEO"])
        self.assertEqual(rows[1]["service_name"], "Геология участка")

        contract_rows = self.contract_form._normalize_contract_stage_service_sections(
            raw, row_index=1, product=self.spec
        )
        self.assertEqual([row["code"] for row in contract_rows], ["DSC", "GEO"])
        self.assertEqual(contract_rows[1]["service_name"], "Геология участка")

    def test_editor_html_stays_manual_and_commercial_rate_is_kept(self):
        sections = self.proposal_form._normalize_stage_service_sections(
            json.dumps([{"service_name": "Ручное имя", "code": "geo"}]),
            row_index=1,
            product=self.spec,
        )
        state = self.proposal_form._normalize_stage_editor_state(
            json.dumps([{"code": "GEO", "service_name": "Ручное имя", "html": "<p>свой текст</p>", "plain_text": "свой текст"}]),
            row_index=1,
            product=self.spec,
            service_sections=sections,
        )
        geo = next(item for item in state if item["code"] == "GEO")
        self.assertEqual(geo["html"], "<p>свой текст</p>")
        self.assertEqual(geo["service_name"], "Геология участка")

        commercial = self.proposal_form._normalize_stage_commercial_rows(
            json.dumps(
                [
                    {
                        "service_name": "Ручное имя",
                        "code": "GEO",
                        "job_title": "Черновик",
                        "rate_eur_per_day": "150",
                        "asset_day_counts": ["3"],
                    },
                    {"service_name": "Нет", "code": "QQQ", "rate_eur_per_day": "9", "asset_day_counts": ["1"]},
                ]
            ),
            row_index=1,
            product=self.spec,
            service_sections=sections,
        )
        self.assertEqual(len(commercial), 1)
        self.assertEqual(commercial[0]["code"], "GEO")
        self.assertEqual(commercial[0]["service_name"], "Геология участка")
        self.assertEqual(commercial[0]["rate_eur_per_day"], Decimal("150"))


class SpecDocumentVariableTests(TestCase):
    def test_goal_and_title_come_from_the_document(self):
        spec = seed_spec_catalog()
        proposal = SimpleNamespace(
            pk=None,
            type=spec,
            type_id=spec.pk,
            purpose="Цель сделки",
            proposal_project_name="Название сделки",
        )
        self.assertEqual(_proposal_service_goal(proposal), "Цель сделки")
        self.assertEqual(_proposal_report_title(proposal), "Название сделки")
        self.assertEqual(_proposal_product_name(proposal), "Название сделки")
        self.assertEqual(_proposal_service_goal_genitive(proposal), "")


class SpecScanDeleteTests(TestCase):
    def test_media_scan_with_encoded_cyrillic_name_is_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(MEDIA_ROOT=tmp, MEDIA_URL="/media/"):
                path = Path(tmp) / "Offer_скан.pdf"
                path.write_bytes(b"scan")
                stored = _media_url_for_path(path)
                self.assertIn("%", stored)
                self.assertNotIn("скан", stored)

                delete_proposal_scan_file(None, stored)

                self.assertFalse(path.exists())
