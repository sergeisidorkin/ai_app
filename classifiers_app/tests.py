from datetime import date
import csv
import io
import json

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from classifiers_app.models import (
    BusinessEntityAttributeRecord,
    BusinessEntityIdentifierRecord,
    BusinessEntityReorganizationEvent,
    BusinessEntityRelationRecord,
    BusinessEntityRecord,
    LegalEntityIdentifier,
    LegalEntityRecord,
    NumcapRecord,
    OKSMCountry,
    PhysicalEntityIdentifier,
    RussianFederationSubjectCode,
    TerritorialDivision,
)
from classifiers_app.forms import (
    BusinessEntityIdentifierRecordForm,
    BusinessEntityLegalAddressRecordForm,
    BusinessEntityRecordForm,
)
from classifiers_app.views import BUSINESS_REGISTRY_CSV_FIELDS, sync_autocomplete_registry_entry


class OKSMCountryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="oksm-user",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)

    def test_table_partial_shows_genitive_short_name_column(self):
        OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            short_name_genitive="России",
            full_name="Российская Федерация",
            alpha2="RU",
            alpha3="RUS",
            position=1,
        )

        response = self.client.get(reverse("oksm_table_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Наименование (краткое) в род. пад.")
        self.assertContains(response, "России")

    def test_create_saves_genitive_short_name(self):
        response = self.client.post(
            reverse("oksm_form_create"),
            {
                "number": "643",
                "code": "643",
                "short_name": "Россия",
                "short_name_genitive": "России",
                "full_name": "Российская Федерация",
                "alpha2": "ru",
                "alpha3": "rus",
                "approval_date": "",
                "expiry_date": "",
                "source": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        country = OKSMCountry.objects.get()
        self.assertEqual(country.short_name_genitive, "России")
        self.assertEqual(country.alpha2, "RU")
        self.assertEqual(country.alpha3, "RUS")


class PhysicalEntityIdentifierTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="pei-user",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            full_name="Российская Федерация",
            alpha2="RU",
            alpha3="RUS",
            position=1,
        )

    def test_table_partial_shows_actions_block(self):
        PhysicalEntityIdentifier.objects.create(
            identifier="СНИЛС",
            full_name="Страховой номер индивидуального лицевого счета",
            country=self.country,
            code=self.country.code,
            position=1,
        )

        response = self.client.get(reverse("pei_table_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Код")
        self.assertContains(response, 'data-target-name="pei-select"')
        self.assertContains(response, 'id="pei-actions"')
        self.assertContains(response, "Добавить строку")

    def test_create_sets_code_from_country(self):
        response = self.client.post(
            reverse("pei_form_create"),
            {
                "identifier": "Паспорт",
                "full_name": "Паспорт гражданина Российской Федерации",
                "country": str(self.country.pk),
                "code": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        item = PhysicalEntityIdentifier.objects.get()
        self.assertEqual(item.code, "643")
        self.assertContains(response, "Классификатор идентификаторов физлиц")


class NumcapRecordTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="numcap-user",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)

    def test_table_partial_shows_actions_and_pagination(self):
        for idx in range(1, 53):
            NumcapRecord.objects.create(
                code="495",
                begin=f"{1000000 + idx}",
                end=f"{1000000 + idx}",
                capacity="1",
                operator="Тестовый оператор",
                region=f"Регион {idx}",
                position=idx,
            )

        response = self.client.get(reverse("numcap_table_partial"), {"numcap_page": 2})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-target-name="numcap-select"')
        self.assertContains(response, 'id="numcap-actions"')
        self.assertContains(response, 'id="numcap-page-input"')
        self.assertContains(response, "Регион 51")
        self.assertContains(response, "Регион 52")
        self.assertNotContains(response, "Регион 50")

    def test_create_normalizes_capacity_from_range(self):
        response = self.client.post(
            reverse("numcap_form_create"),
            {
                "code": "495",
                "begin": "1234500",
                "end": "1234599",
                "capacity": "",
                "operator": "Оператор",
                "region": "Москва",
                "gar_territory": "г. Москва",
                "inn": "7701234567",
            },
        )

        self.assertEqual(response.status_code, 200)
        item = NumcapRecord.objects.get()
        self.assertEqual(item.capacity, "100")
        self.assertEqual(item.gar_territory, "г. Москва")
        self.assertEqual(item.inn, "7701234567")
        self.assertContains(response, "Реестр российской системы и плана нумерации")
        self.assertContains(response, 'id="numcap-table-wrap"')

    def test_table_partial_filters_by_code_region_and_search(self):
        NumcapRecord.objects.create(
            code="495",
            begin="1234500",
            end="1234599",
            capacity="100",
            operator="Ростелеком",
            region="Москва",
            position=1,
        )
        NumcapRecord.objects.create(
            code="812",
            begin="7654300",
            end="7654399",
            capacity="100",
            operator="Мегафон Северо-Запад",
            region="Санкт-Петербург",
            position=2,
        )

        response = self.client.get(
            reverse("numcap_table_partial"),
            {
                "numcap_q": "Ростелеком",
                "numcap_code": "49",
                "numcap_region": "Моск",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Москва")
        self.assertContains(response, "Ростелеком")
        self.assertNotContains(response, "Санкт-Петербург")

    def test_table_partial_pagination_preserves_filters(self):
        for idx in range(1, 53):
            NumcapRecord.objects.create(
                code="495",
                begin=f"{1000000 + idx}",
                end=f"{1000000 + idx}",
                capacity="1",
                operator="Оператор Москва",
                region="Москва",
                position=idx,
            )

        response = self.client.get(
            reverse("numcap_table_partial"),
            {
                "numcap_page": 2,
                "numcap_region": "Москва",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "numcap_region=%D0%9C%D0%BE%D1%81%D0%BA%D0%B2%D0%B0")

    def test_numcap_csv_upload_replaces_records_from_official_format(self):
        NumcapRecord.objects.create(
            code="495",
            begin="0000000",
            end="0000001",
            capacity="2",
            operator='ООО "Старый оператор"',
            region="Старый регион",
            position=1,
        )
        csv_content = (
            "АВС/ DEF;От;До;Емкость;Оператор;Регион;Территория ГАР;ИНН\n"
            '495;1234500;1234599;100;ООО "Новый оператор";Москва;г. Москва;7701234567\n'
        ).encode("utf-8")
        upload = SimpleUploadedFile("ABC-3xx.csv", csv_content, content_type="text/csv")

        response = self.client.post(reverse("numcap_csv_upload"), {"csv_files": [upload]})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["created"], 1)
        self.assertEqual(NumcapRecord.objects.count(), 1)
        item = NumcapRecord.objects.get()
        self.assertEqual(item.operator, "ООО «Новый оператор»")
        self.assertEqual(item.region, "Москва")
        self.assertEqual(item.gar_territory, "г. Москва")
        self.assertEqual(item.inn, "7701234567")

    def test_numcap_csv_upload_can_append_without_replace(self):
        first_csv = (
            "АВС/ DEF;От;До;Емкость;Оператор;Регион;Территория ГАР;ИНН\n"
            '495;1234500;1234599;100;ООО "Первый оператор";Москва;г. Москва;7701234567\n'
        ).encode("utf-8")
        second_csv = (
            "АВС/ DEF;От;До;Емкость;Оператор;Регион;Территория ГАР;ИНН\n"
            '812;7654300;7654399;100;ООО "Второй оператор";Санкт-Петербург;г. Санкт-Петербург;7801234567\n'
        ).encode("utf-8")

        first_response = self.client.post(
            reverse("numcap_csv_upload"),
            {"csv_file": SimpleUploadedFile("ABC-3xx.csv", first_csv, content_type="text/csv")},
        )
        second_response = self.client.post(
            reverse("numcap_csv_upload"),
            {
                "replace": "0",
                "csv_file": SimpleUploadedFile("ABC-4xx.csv", second_csv, content_type="text/csv"),
            },
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertTrue(first_response.json()["ok"])
        self.assertTrue(second_response.json()["ok"])
        self.assertEqual(NumcapRecord.objects.count(), 2)
        self.assertTrue(NumcapRecord.objects.filter(code="495", region="Москва").exists())
        self.assertTrue(NumcapRecord.objects.filter(code="812", region="Санкт-Петербург").exists())


class LegalEntityAutocompleteTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="ler-search-user",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            full_name="Российская Федерация",
            alpha2="RU",
            alpha3="RUS",
            position=1,
        )

    def _create_identifier_chain(self, *, position, short_name, full_name="", region="Москва", active_name=True, active_address=True):
        business_entity = BusinessEntityRecord.objects.create(
            name=short_name,
            position=position,
        )
        identifier_record = BusinessEntityIdentifierRecord.objects.create(
            business_entity=business_entity,
            identifier_type="ОГРН",
            registration_country=self.country,
            registration_region=region,
            registration_date=date(2024, 1, 15),
            number=f"7700{position}",
            valid_to=None,
            is_active=True,
            position=position,
        )
        LegalEntityRecord.objects.create(
            attribute=LegalEntityRecord.ATTRIBUTE_NAME,
            identifier_record=identifier_record,
            short_name=short_name,
            full_name=full_name,
            identifier="LEGACY",
            registration_number="legacy-number",
            registration_date=date(2020, 1, 1),
            valid_to=None if active_name else date(2023, 1, 1),
            position=position,
        )
        LegalEntityRecord.objects.create(
            attribute=LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS,
            identifier_record=identifier_record,
            registration_country=self.country,
            registration_region=region,
            valid_to=None if active_address else date(2023, 1, 1),
            position=position + 100,
        )
        return identifier_record

    def test_ler_search_uses_identifier_and_address_registries(self):
        self._create_identifier_chain(
            position=1,
            short_name='ООО "Альфа"',
            full_name='Общество с ограниченной ответственностью "Альфа"',
            region="Москва",
        )
        self._create_identifier_chain(
            position=2,
            short_name='ООО "Бета"',
            region="Тюмень",
            active_address=False,
        )

        response = self.client.get(reverse("ler_search"), {"q": "Альф"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total_count"], 1)
        self.assertEqual(len(payload["results"]), 1)
        item = payload["results"][0]
        self.assertEqual(item["short_name"], 'ООО "Альфа"')
        self.assertEqual(item["full_name"], 'Общество с ограниченной ответственностью "Альфа"')
        self.assertEqual(item["identifier"], "ОГРН")
        self.assertEqual(item["identifier_type"], "ОГРН")
        self.assertEqual(item["registration_number"], "77001")
        self.assertEqual(item["number"], "77001")
        self.assertEqual(item["country_id"], self.country.pk)
        self.assertEqual(item["country_name"], "Россия")
        self.assertEqual(item["registration_date"], "2024-01-15")
        self.assertEqual(item["region"], "Москва")

    def test_ler_search_uses_latest_active_name_and_address(self):
        business_entity = BusinessEntityRecord.objects.create(name='ООО "Гамма"', position=1)
        identifier_record = BusinessEntityIdentifierRecord.objects.create(
            business_entity=business_entity,
            identifier_type="ИНН",
            registration_country=self.country,
            registration_region="Старый регион",
            registration_date=date(2024, 5, 20),
            number="5000",
            valid_to=None,
            is_active=True,
            position=1,
        )
        LegalEntityRecord.objects.create(
            attribute=LegalEntityRecord.ATTRIBUTE_NAME,
            identifier_record=identifier_record,
            short_name='ООО "Гамма старая"',
            full_name="Старая запись",
            name_received_date=date(2024, 1, 1),
            name_changed_date=date(2024, 6, 1),
            position=1,
        )
        LegalEntityRecord.objects.create(
            attribute=LegalEntityRecord.ATTRIBUTE_NAME,
            identifier_record=identifier_record,
            short_name='ООО "Гамма новая"',
            full_name="Новая запись",
            name_received_date=date(2024, 6, 1),
            name_changed_date=None,
            position=2,
        )
        LegalEntityRecord.objects.create(
            attribute=LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS,
            identifier_record=identifier_record,
            registration_country=self.country,
            registration_region="Старый регион",
            valid_from=date(2024, 1, 1),
            valid_to=date(2024, 5, 31),
            position=101,
        )
        LegalEntityRecord.objects.create(
            attribute=LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS,
            identifier_record=identifier_record,
            registration_country=self.country,
            registration_region="Новый регион",
            valid_from=date(2024, 6, 1),
            valid_to=None,
            position=102,
        )

        response = self.client.get(reverse("ler_search"), {"q": "Гамма"})

        self.assertEqual(response.status_code, 200)
        item = response.json()["results"][0]
        self.assertEqual(item["short_name"], 'ООО "Гамма новая"')
        self.assertEqual(item["full_name"], "Новая запись")
        self.assertEqual(item["region"], "Новый регион")

    def test_ler_region_autofill_uses_russian_fns_subject_codes_for_russia(self):
        RussianFederationSubjectCode.objects.create(
            subject_name="Тюменская область",
            oktmo_code="71000000",
            fns_code="72",
            position=1,
        )

        response = self.client.get(
            reverse("ler_region_autofill"),
            {
                "country_id": str(self.country.pk),
                "identifier": "ОГРН",
                "registration_number": "1177200000123",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["region"], "Тюменская область")

    def test_sync_autocomplete_registry_entry_creates_new_identifier_chain_for_manual_input(self):
        user = get_user_model().objects.create_user(
            username="registry-sync-user",
            password="secret",
            is_staff=True,
        )

        identifier_record = sync_autocomplete_registry_entry(
            short_name='ООО "Синхронизация"',
            country=self.country,
            identifier_type="ОГРН",
            registration_number="1234567890",
            registration_date=date(2025, 2, 10),
            registration_region="Тюменская область",
            user=user,
            business_entity_source="[Тесты / Ручной ввод]",
        )

        self.assertIsNotNone(identifier_record)
        self.assertEqual(identifier_record.identifier_type, "ОГРН")
        self.assertEqual(identifier_record.number, "1234567890")
        self.assertEqual(identifier_record.registration_country, self.country)
        self.assertEqual(identifier_record.registration_region, "Тюменская область")
        self.assertEqual(identifier_record.registration_date, date(2025, 2, 10))

        name_record = LegalEntityRecord.objects.get(
            attribute=LegalEntityRecord.ATTRIBUTE_NAME,
            identifier_record=identifier_record,
        )
        self.assertEqual(name_record.short_name, 'ООО "Синхронизация"')
        self.assertEqual(name_record.identifier, "ОГРН")
        self.assertEqual(name_record.registration_number, "1234567890")
        self.assertEqual(name_record.registration_date, date(2025, 2, 10))
        self.assertEqual(name_record.registration_region, "Тюменская область")
        self.assertEqual(name_record.name_received_date, date(2025, 2, 10))
        self.assertEqual(name_record.valid_from, date(2025, 2, 10))
        self.assertEqual(identifier_record.business_entity.record_author, "registry-sync-user")
        self.assertEqual(identifier_record.business_entity.source, "[Тесты / Ручной ввод]")

        address_record = LegalEntityRecord.objects.get(
            attribute=LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS,
            identifier_record=identifier_record,
        )
        self.assertEqual(address_record.registration_country, self.country)
        self.assertEqual(address_record.registration_region, "Тюменская область")

        second_identifier_record = sync_autocomplete_registry_entry(
            short_name='ООО "Синхронизация"',
            country=self.country,
            identifier_type="ОГРН",
            registration_number="1234567890",
            registration_date=date(2025, 2, 10),
            user=user,
        )

        self.assertNotEqual(identifier_record.pk, second_identifier_record.pk)
        self.assertEqual(BusinessEntityRecord.objects.count(), 2)
        self.assertEqual(
            LegalEntityRecord.objects.filter(attribute=LegalEntityRecord.ATTRIBUTE_NAME, short_name='ООО "Синхронизация"').count(),
            2,
        )

    def test_sync_autocomplete_registry_entry_keeps_existing_chain_when_explicitly_selected(self):
        user = get_user_model().objects.create_user(
            username="registry-sync-link-user",
            password="secret",
            is_staff=True,
        )
        identifier_record = self._create_identifier_chain(
            position=7,
            short_name='ООО "Выбранная"',
            full_name='Полное "Выбранная"',
            region="Тюмень",
        )
        original_business_entity_count = BusinessEntityRecord.objects.count()
        original_name_record = LegalEntityRecord.objects.get(
            attribute=LegalEntityRecord.ATTRIBUTE_NAME,
            identifier_record=identifier_record,
        )

        resolved_identifier_record = sync_autocomplete_registry_entry(
            short_name='ООО "Несовпадающий ввод"',
            country=self.country,
            identifier_type="ИНН",
            registration_number="9999999999",
            registration_date=date(2026, 1, 1),
            user=user,
            selected_identifier_record_id=str(identifier_record.pk),
            selected_from_autocomplete=True,
        )

        self.assertEqual(resolved_identifier_record.pk, identifier_record.pk)
        self.assertEqual(BusinessEntityRecord.objects.count(), original_business_entity_count)
        original_name_record.refresh_from_db()
        identifier_record.refresh_from_db()
        self.assertEqual(original_name_record.short_name, 'ООО "Выбранная"')
        self.assertEqual(identifier_record.number, f"7700{7}")


class BusinessEntityRelationAutocompleteTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="brl-autocomplete-user",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.entities = [
            BusinessEntityRecord.objects.create(name='ТОО "Ecil-Mining"', position=1),
            BusinessEntityRecord.objects.create(name='ООО "Ecil Trade"', position=2),
            BusinessEntityRecord.objects.create(name='АО "Ecil Geo"', position=3),
            BusinessEntityRecord.objects.create(name='ООО "Ecil Energy"', position=4),
        ]

    def test_search_matches_name_and_limits_visible_payload(self):
        response = self.client.get(reverse("brl_business_entity_search"), {"q": "Ecil"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total_count"], 4)
        self.assertEqual(len(payload["results"]), 4)
        self.assertEqual(
            payload["results"][0]["label"],
            f'{self.entities[0].pk:05d}-BSN ТОО "Ecil-Mining"',
        )

    def test_search_matches_formatted_bsn_id(self):
        expected_formatted_id = f"{self.entities[2].pk:05d}-BSN"
        response = self.client.get(reverse("brl_business_entity_search"), {"q": expected_formatted_id})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total_count"], 1)
        self.assertEqual(payload["results"][0]["id"], self.entities[2].pk)
        self.assertEqual(payload["results"][0]["formatted_id"], expected_formatted_id)


class BusinessEntityLegalAddressIdentifierAutocompleteTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="bea-autocomplete-user",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            full_name="Российская Федерация",
            alpha2="RU",
            alpha3="RUS",
            position=1,
        )
        business_entity = BusinessEntityRecord.objects.create(name='ООО "Альфа"', position=1)
        self.identifier_record = BusinessEntityIdentifierRecord.objects.create(
            business_entity=business_entity,
            identifier_type="ОГРН",
            registration_country=self.country,
            registration_region="Москва",
            number="7700123456",
            valid_from=date(2024, 1, 1),
            position=1,
        )
        LegalEntityRecord.objects.create(
            attribute=LegalEntityRecord.ATTRIBUTE_NAME,
            identifier_record=self.identifier_record,
            short_name='ООО "Альфа"',
            valid_to=None,
            position=1,
        )

    def test_search_matches_id_number_and_short_name(self):
        response = self.client.get(reverse("bea_identifier_record_search"), {"q": "7700123456"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total_count"], 1)
        self.assertEqual(payload["results"][0]["formatted_id"], f"{self.identifier_record.pk:05d}-IDN")
        self.assertEqual(payload["results"][0]["identifier_type"], "ОГРН")
        self.assertEqual(payload["results"][0]["number"], "7700123456")
        self.assertEqual(payload["results"][0]["short_name"], 'ООО "Альфа"')


class BusinessEntityLegalAddressFormTests(TestCase):
    def setUp(self):
        self.country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            full_name="Российская Федерация",
            alpha2="RU",
            alpha3="RUS",
            position=1,
        )
        TerritorialDivision.objects.create(
            country=self.country,
            region_name="Старый регион",
            region_code="OLD",
            effective_date=date(2020, 1, 1),
            abolished_date=date(2024, 12, 31),
            position=1,
        )
        TerritorialDivision.objects.create(
            country=self.country,
            region_name="Новый регион",
            region_code="NEW",
            effective_date=date(2025, 1, 1),
            position=2,
        )

    def test_form_filters_regions_by_valid_from_date(self):
        form = BusinessEntityLegalAddressRecordForm(
            data={
                "registration_country": str(self.country.pk),
                "registration_region": "",
                "valid_from": "2026-03-15",
            }
        )

        region_choices = [value for value, _label in form.fields["registration_region"].choices]

        self.assertIn("Новый регион", region_choices)
        self.assertNotIn("Старый регион", region_choices)

    def test_form_defaults_registration_country_to_russia(self):
        form = BusinessEntityLegalAddressRecordForm()

        self.assertEqual(form.fields["registration_country"].initial, self.country.pk)


class BusinessEntityLegalAddressReorderTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="bea-reorder-user",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            full_name="Российская Федерация",
            alpha2="RU",
            alpha3="RUS",
            position=1,
        )
        self.entity_a = BusinessEntityRecord.objects.create(name='ООО "Альфа"', position=1)
        self.entity_b = BusinessEntityRecord.objects.create(name='ООО "Бета"', position=2)
        self.identifier_a = BusinessEntityIdentifierRecord.objects.create(
            business_entity=self.entity_a,
            identifier_type="ОГРН",
            registration_country=self.country,
            number="7700000001",
            valid_from=date(2024, 1, 1),
            position=1,
        )
        self.identifier_b = BusinessEntityIdentifierRecord.objects.create(
            business_entity=self.entity_b,
            identifier_type="ОГРН",
            registration_country=self.country,
            number="7700000002",
            valid_from=date(2024, 1, 1),
            position=2,
        )
        self.name_a = LegalEntityRecord.objects.create(
            attribute=LegalEntityRecord.ATTRIBUTE_NAME,
            identifier_record=self.identifier_a,
            short_name='ООО "Альфа"',
            position=1,
        )
        self.address_a = LegalEntityRecord.objects.create(
            attribute=LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS,
            identifier_record=self.identifier_a,
            registration_country=self.country,
            registration_region="Москва",
            valid_from=date(2024, 1, 1),
            position=2,
        )
        self.name_b = LegalEntityRecord.objects.create(
            attribute=LegalEntityRecord.ATTRIBUTE_NAME,
            identifier_record=self.identifier_b,
            short_name='ООО "Бета"',
            position=3,
        )
        self.address_b = LegalEntityRecord.objects.create(
            attribute=LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS,
            identifier_record=self.identifier_b,
            registration_country=self.country,
            registration_region="Тюмень",
            valid_from=date(2024, 1, 1),
            position=4,
        )

    def test_move_up_reorders_only_legal_address_rows(self):
        response = self.client.get(reverse("bea_move_up", args=[self.address_b.pk]))

        self.assertEqual(response.status_code, 200)
        self.address_a.refresh_from_db()
        self.address_b.refresh_from_db()
        self.name_a.refresh_from_db()
        self.name_b.refresh_from_db()
        self.assertEqual((self.address_b.position, self.address_a.position), (1, 2))
        self.assertEqual((self.name_a.position, self.name_b.position), (1, 3))

    def test_move_down_reorders_only_legal_address_rows(self):
        response = self.client.get(reverse("bea_move_down", args=[self.address_a.pk]))

        self.assertEqual(response.status_code, 200)
        self.address_a.refresh_from_db()
        self.address_b.refresh_from_db()
        self.name_a.refresh_from_db()
        self.name_b.refresh_from_db()
        self.assertEqual((self.address_b.position, self.address_a.position), (1, 2))
        self.assertEqual((self.name_a.position, self.name_b.position), (1, 3))


class BusinessEntityAttributeTableTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="bat-view-user",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)
        BusinessEntityAttributeRecord.objects.create(
            attribute_name="Произвольное значение",
            subsection_name="Лишний подраздел",
            position=1,
        )

    def test_table_shows_only_system_attribute_rows(self):
        response = self.client.get(reverse("bat_table_partial"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Наименование")
        self.assertContains(response, "Юридический адрес")
        self.assertContains(response, "База юрлиц: наименование")
        self.assertContains(response, "База юрлиц: юрадрес")
        self.assertNotContains(response, "Произвольное значение")
        self.assertNotContains(response, "Лишний подраздел")


class BusinessEntityRecordFormTests(TestCase):
    def test_form_normalizes_straight_quotes_to_guillemets(self):
        form = BusinessEntityRecordForm(
            data={
                "name": 'ООО "Тест"',
                "record_date": "",
                "comment": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["name"], "ООО «Тест»")


class BusinessRegistryMasterFilterTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="registry-filter-user",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            full_name="Российская Федерация",
            alpha2="RU",
            alpha3="RUS",
            position=1,
        )
        self.alpha = BusinessEntityRecord.objects.create(name='ООО "Альфа"', position=1)
        self.beta = BusinessEntityRecord.objects.create(name='ООО "Бета"', position=2)
        self.alpha_identifier = BusinessEntityIdentifierRecord.objects.create(
            business_entity=self.alpha,
            identifier_type="ОГРН",
            registration_country=self.country,
            registration_region="Москва",
            registration_date=date(2024, 1, 15),
            number="7700000001",
            valid_from=date(2024, 1, 15),
            position=1,
        )
        self.beta_identifier = BusinessEntityIdentifierRecord.objects.create(
            business_entity=self.beta,
            identifier_type="ИНН",
            registration_country=self.country,
            registration_region="Тюмень",
            registration_date=date(2024, 2, 15),
            number="7200000002",
            valid_from=date(2024, 2, 15),
            position=2,
        )
        LegalEntityRecord.objects.create(
            attribute=LegalEntityRecord.ATTRIBUTE_NAME,
            identifier_record=self.alpha_identifier,
            short_name='ООО "Альфа"',
            full_name='Общество "Альфа"',
            record_date=date(2024, 1, 15),
            record_author="tester",
            name_received_date=date(2024, 1, 15),
            position=1,
        )
        LegalEntityRecord.objects.create(
            attribute=LegalEntityRecord.ATTRIBUTE_NAME,
            identifier_record=self.beta_identifier,
            short_name='ООО "Бета"',
            full_name='Общество "Бета"',
            record_date=date(2024, 2, 15),
            record_author="tester",
            name_received_date=date(2024, 2, 15),
            position=2,
        )
        LegalEntityRecord.objects.create(
            attribute=LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS,
            identifier_record=self.alpha_identifier,
            registration_country=self.country,
            registration_region="Москва",
            valid_from=date(2024, 1, 15),
            position=1,
        )
        LegalEntityRecord.objects.create(
            attribute=LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS,
            identifier_record=self.beta_identifier,
            registration_country=self.country,
            registration_region="Тюмень",
            valid_from=date(2024, 2, 15),
            position=2,
        )
        event = BusinessEntityReorganizationEvent.objects.create(
            reorganization_event_uid="00001-REO",
            relation_type="Присоединение",
            event_date=date(2025, 1, 10),
            position=1,
        )
        BusinessEntityRelationRecord.objects.create(
            event=event,
            from_business_entity=self.alpha,
            to_business_entity=self.beta,
            position=1,
        )

    def test_business_entity_filter_options_returns_all_bsn_values(self):
        response = self.client.get(reverse("business_entity_filter_options"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total_count"], 2)
        self.assertEqual(
            [item["formatted_id"] for item in payload["results"]],
            [f"{self.alpha.pk:05d}-BSN", f"{self.beta.pk:05d}-BSN"],
        )

    def test_business_entity_filter_options_supports_search_query(self):
        response = self.client.get(reverse("business_entity_filter_options"), {"q": "Альф"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total_count"], 1)
        self.assertEqual(payload["results"][0]["formatted_id"], f"{self.alpha.pk:05d}-BSN")
        self.assertIn("Альфа", payload["results"][0]["label"])

    def test_business_entity_filter_options_supports_selected_ids_lookup(self):
        response = self.client.get(
            reverse("business_entity_filter_options"),
            {"ids": [str(self.beta.pk)]},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total_count"], 1)
        self.assertEqual(payload["results"][0]["formatted_id"], f"{self.beta.pk:05d}-BSN")
        self.assertIn("Бета", payload["results"][0]["label"])

    def test_ber_table_partial_filters_by_selected_bsn(self):
        response = self.client.get(reverse("ber_table_partial"), {"business_entity_ids": str(self.alpha.pk)})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Альфа")
        self.assertNotContains(response, "Бета")

    def test_identifier_name_and_address_tables_filter_by_selected_bsn(self):
        params = {"business_entity_ids": str(self.alpha.pk)}

        bei_response = self.client.get(reverse("bei_table_partial"), params)
        ler_response = self.client.get(reverse("ler_table_partial"), params)
        bea_response = self.client.get(reverse("bea_table_partial"), params)

        self.assertContains(bei_response, f"{self.alpha.pk:05d}-BSN")
        self.assertNotContains(bei_response, f"{self.beta.pk:05d}-BSN")
        self.assertContains(ler_response, "Альфа")
        self.assertNotContains(ler_response, "Бета")
        self.assertContains(bea_response, "Москва")
        self.assertNotContains(bea_response, "Тюмень")

    def test_relations_table_filters_by_selected_bsn(self):
        response = self.client.get(reverse("brl_table_partial"), {"business_entity_ids": str(self.alpha.pk)})

        self.assertEqual(response.status_code, 200)
        relation = BusinessEntityRelationRecord.objects.get()
        self.assertContains(response, f"{relation.pk:05d}-RLT")

        response_beta = self.client.get(reverse("brl_table_partial"), {"business_entity_ids": "999999"})
        self.assertNotContains(response_beta, f"{relation.pk:05d}-RLT")

    def test_business_registry_tables_support_second_page(self):
        for idx in range(3, 56):
            entity = BusinessEntityRecord.objects.create(name=f"Тест {idx:02d}", position=idx)
            identifier = BusinessEntityIdentifierRecord.objects.create(
                business_entity=entity,
                identifier_type="ОГРН",
                registration_country=self.country,
                registration_region=f"Регион {idx:02d}",
                registration_date=date(2024, 1, min(idx, 28)),
                number=f"IDN-{idx:02d}",
                valid_from=date(2024, 1, 1),
                position=idx,
            )
            LegalEntityRecord.objects.create(
                attribute=LegalEntityRecord.ATTRIBUTE_NAME,
                identifier_record=identifier,
                short_name=f"Наименование {idx:02d}",
                full_name=f"Полное наименование {idx:02d}",
                record_date=date(2024, 1, 1),
                record_author="tester",
                name_received_date=date(2024, 1, 1),
                position=idx,
            )
            LegalEntityRecord.objects.create(
                attribute=LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS,
                identifier_record=identifier,
                registration_country=self.country,
                registration_region=f"Регион {idx:02d}",
                valid_from=date(2024, 1, 1),
                position=idx,
            )

        ber_response = self.client.get(reverse("ber_table_partial"), {"ber_page": "2"})
        bei_response = self.client.get(reverse("bei_table_partial"), {"bei_page": "2"})
        ler_response = self.client.get(reverse("ler_table_partial"), {"ler_page": "2"})
        bea_response = self.client.get(reverse("bea_table_partial"), {"bea_page": "2"})

        self.assertContains(ber_response, "Тест 55")
        self.assertNotContains(ber_response, "Альфа")
        self.assertContains(ber_response, "Показаны 51-55 из 55")

        self.assertContains(bei_response, "IDN-55")
        self.assertNotContains(bei_response, "7700000001")
        self.assertContains(bei_response, "Показаны 51-55 из 55")

        self.assertContains(ler_response, "Наименование 55")
        self.assertNotContains(ler_response, "Альфа")
        self.assertContains(ler_response, "Показаны 51-55 из 55")

        self.assertContains(bea_response, "Регион 55")
        self.assertNotContains(bea_response, "Москва")
        self.assertContains(bea_response, "Показаны 51-55 из 55")

    def test_relations_table_supports_second_page(self):
        for idx in range(2, 56):
            event = BusinessEntityReorganizationEvent.objects.create(
                reorganization_event_uid=f"{idx:05d}-REO",
                relation_type="Присоединение",
                event_date=date(2025, 1, min(idx, 28)),
                comment=f"Связь {idx:02d}",
                position=idx,
            )
            BusinessEntityRelationRecord.objects.create(
                event=event,
                from_business_entity=self.alpha,
                to_business_entity=self.beta,
                position=idx,
            )

        response = self.client.get(reverse("brl_table_partial"), {"brl_page": "2"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Связь 55")
        self.assertNotContains(response, "Связь 02")
        self.assertContains(response, "Показаны 51-55 из 55")

    def test_home_page_binds_business_registry_partials_to_their_own_wrappers(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="business-entities-table-wrap"')
        self.assertContains(response, 'id="business-entity-identifiers-table-wrap"')
        self.assertContains(response, 'id="business-entity-attributes-table-wrap"')
        self.assertContains(response, 'id="ler-table-wrap"')
        self.assertContains(response, 'id="business-entity-addresses-table-wrap"')
        self.assertContains(response, 'id="business-entity-relations-table-wrap"')
        self.assertGreaterEqual(response.content.decode().count('hx-target="this"'), 6)


class BusinessRegistryCsvTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="business-registry-csv-user",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            full_name="Российская Федерация",
            alpha2="RU",
            alpha3="RUS",
            position=1,
        )
        self.alpha = BusinessEntityRecord.objects.create(
            name='ООО "Альфа"',
            record_date=date(2024, 1, 10),
            record_author="tester",
            source="source-alpha",
            comment="comment-alpha",
            position=1,
        )
        self.beta = BusinessEntityRecord.objects.create(
            name='ООО "Бета"',
            record_date=date(2024, 1, 11),
            record_author="tester",
            source="source-beta",
            comment="comment-beta",
            position=2,
        )
        self.alpha_identifier = BusinessEntityIdentifierRecord.objects.create(
            business_entity=self.alpha,
            identifier_type="ОГРН",
            registration_country=self.country,
            registration_region="Москва",
            record_date=date(2024, 1, 10),
            record_author="tester",
            registration_date=date(2024, 1, 10),
            number="7700000001",
            valid_from=date(2024, 1, 10),
            position=1,
        )
        self.beta_identifier = BusinessEntityIdentifierRecord.objects.create(
            business_entity=self.beta,
            identifier_type="ИНН",
            registration_country=self.country,
            registration_region="Тюмень",
            record_date=date(2024, 1, 11),
            record_author="tester",
            registration_date=date(2024, 1, 11),
            number="7200000002",
            valid_from=date(2024, 1, 11),
            position=2,
        )
        LegalEntityRecord.objects.create(
            attribute=LegalEntityRecord.ATTRIBUTE_NAME,
            identifier_record=self.alpha_identifier,
            registration_country=self.country,
            registration_region="Москва",
            record_date=date(2024, 1, 10),
            record_author="tester",
            registration_date=date(2024, 1, 10),
            registration_number="7700000001",
            identifier="ОГРН",
            short_name='ООО "Альфа"',
            full_name='Общество с ограниченной ответственностью "Альфа"',
            name_received_date=date(2024, 1, 10),
            position=1,
        )
        LegalEntityRecord.objects.create(
            attribute=LegalEntityRecord.ATTRIBUTE_NAME,
            identifier_record=self.beta_identifier,
            registration_country=self.country,
            registration_region="Тюмень",
            record_date=date(2024, 1, 11),
            record_author="tester",
            registration_date=date(2024, 1, 11),
            registration_number="7200000002",
            identifier="ИНН",
            short_name='ООО "Бета"',
            full_name='Общество с ограниченной ответственностью "Бета"',
            name_received_date=date(2024, 1, 11),
            position=2,
        )
        LegalEntityRecord.objects.create(
            attribute=LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS,
            identifier_record=self.alpha_identifier,
            registration_country=self.country,
            registration_region="Москва",
            record_date=date(2024, 1, 10),
            record_author="tester",
            postal_code="101000",
            locality="Москва",
            street="Тверская",
            building="1",
            valid_from=date(2024, 1, 10),
            position=3,
        )
        LegalEntityRecord.objects.create(
            attribute=LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS,
            identifier_record=self.beta_identifier,
            registration_country=self.country,
            registration_region="Тюмень",
            record_date=date(2024, 1, 11),
            record_author="tester",
            postal_code="625000",
            locality="Тюмень",
            street="Республики",
            building="2",
            valid_from=date(2024, 1, 11),
            position=4,
        )
        self.event = BusinessEntityReorganizationEvent.objects.create(
            reorganization_event_uid="00001-REO",
            relation_type="Присоединение",
            event_date=date(2025, 1, 10),
            comment="Объединение реестров",
            position=1,
        )
        BusinessEntityRelationRecord.objects.create(
            event=self.event,
            from_business_entity=self.alpha,
            to_business_entity=self.beta,
            position=1,
        )

    def _make_csv_upload(self, rows):
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=BUSINESS_REGISTRY_CSV_FIELDS, delimiter=";", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            payload = {field: "" for field in BUSINESS_REGISTRY_CSV_FIELDS}
            payload.update(row)
            writer.writerow(payload)
        return SimpleUploadedFile(
            "business-registry.csv",
            ("\ufeff" + buffer.getvalue()).encode("utf-8"),
            content_type="text/csv",
        )

    def test_csv_download_exports_all_business_registry_sections(self):
        response = self.client.get(reverse("business_registry_csv_download"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn('attachment; filename="business-registry.csv"', response["Content-Disposition"])

        rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
        self.assertEqual(
            {row["section"] for row in rows},
            {"business_entity", "identifier", "name", "address", "relation"},
        )

        relation_row = next(row for row in rows if row["section"] == "relation")
        self.assertEqual(relation_row["event_ref"], "00001-REO")
        self.assertEqual(relation_row["from_business_entity_ref"], f"{self.alpha.pk:05d}-BSN")
        self.assertEqual(relation_row["to_business_entity_ref"], f"{self.beta.pk:05d}-BSN")

    def test_csv_upload_replaces_entire_business_registry(self):
        upload = self._make_csv_upload(
            [
                {
                    "section": "business_entity",
                    "business_entity_ref": "00010-BSN",
                    "position": "1",
                    "business_entity_name": 'ООО "Новый источник"',
                    "record_date": "2026-01-10",
                    "record_author": "csv-import",
                    "source": "csv-source",
                    "comment": "csv-comment",
                },
                {
                    "section": "business_entity",
                    "business_entity_ref": "00011-BSN",
                    "position": "2",
                    "business_entity_name": 'ООО "Новый приемник"',
                    "record_date": "2026-01-11",
                    "record_author": "csv-import",
                },
                {
                    "section": "identifier",
                    "business_entity_ref": "00010-BSN",
                    "identifier_ref": "00010-IDN",
                    "position": "1",
                    "record_date": "2026-01-10",
                    "record_author": "csv-import",
                    "identifier_type": "ОГРН",
                    "registration_country_code": "643",
                    "registration_country_name": "Россия",
                    "registration_region": "Москва",
                    "registration_date": "2026-01-10",
                    "registration_number": "7701234567890",
                    "valid_from": "2026-01-10",
                },
                {
                    "section": "identifier",
                    "business_entity_ref": "00011-BSN",
                    "identifier_ref": "00011-IDN",
                    "position": "2",
                    "record_date": "2026-01-11",
                    "record_author": "csv-import",
                    "identifier_type": "ИНН",
                    "registration_country_code": "643",
                    "registration_country_name": "Россия",
                    "registration_region": "Санкт-Петербург",
                    "registration_date": "2026-01-11",
                    "registration_number": "7801234567",
                    "valid_from": "2026-01-11",
                },
                {
                    "section": "name",
                    "business_entity_ref": "00010-BSN",
                    "identifier_ref": "00010-IDN",
                    "position": "1",
                    "record_date": "2026-01-10",
                    "record_author": "csv-import",
                    "registration_country_code": "643",
                    "registration_country_name": "Россия",
                    "registration_region": "Москва",
                    "registration_date": "2026-01-10",
                    "registration_number": "7701234567890",
                    "identifier_value": "ОГРН",
                    "short_name": 'ООО "Новый источник"',
                    "full_name": 'Общество с ограниченной ответственностью "Новый источник"',
                    "name_received_date": "2026-01-10",
                },
                {
                    "section": "name",
                    "business_entity_ref": "00011-BSN",
                    "identifier_ref": "00011-IDN",
                    "position": "2",
                    "record_date": "2026-01-11",
                    "record_author": "csv-import",
                    "registration_country_code": "643",
                    "registration_country_name": "Россия",
                    "registration_region": "Санкт-Петербург",
                    "registration_date": "2026-01-11",
                    "registration_number": "7801234567",
                    "identifier_value": "ИНН",
                    "short_name": 'ООО "Новый приемник"',
                    "full_name": 'Общество с ограниченной ответственностью "Новый приемник"',
                    "name_received_date": "2026-01-11",
                },
                {
                    "section": "address",
                    "business_entity_ref": "00010-BSN",
                    "identifier_ref": "00010-IDN",
                    "position": "3",
                    "record_date": "2026-01-10",
                    "record_author": "csv-import",
                    "registration_country_code": "643",
                    "registration_country_name": "Россия",
                    "registration_region": "Москва",
                    "valid_from": "2026-01-10",
                    "postal_code": "101000",
                    "locality": "Москва",
                    "street": "Новая",
                    "building": "10",
                },
                {
                    "section": "address",
                    "business_entity_ref": "00011-BSN",
                    "identifier_ref": "00011-IDN",
                    "position": "4",
                    "record_date": "2026-01-11",
                    "record_author": "csv-import",
                    "registration_country_code": "643",
                    "registration_country_name": "Россия",
                    "registration_region": "Санкт-Петербург",
                    "valid_from": "2026-01-11",
                    "postal_code": "190000",
                    "locality": "Санкт-Петербург",
                    "street": "Главная",
                    "building": "11",
                },
                {
                    "section": "relation",
                    "event_ref": "90001-REO",
                    "from_business_entity_ref": "00010-BSN",
                    "to_business_entity_ref": "00011-BSN",
                    "position": "1",
                    "relation_type": "Присоединение",
                    "event_uid": "90001-REO",
                    "event_date": "2026-02-01",
                    "event_position": "1",
                    "comment": "CSV relation",
                },
            ]
        )

        response = self.client.post(reverse("business_registry_csv_upload"), {"csv_file": upload})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["created"], 9)
        self.assertEqual(BusinessEntityRecord.objects.count(), 2)
        self.assertEqual(BusinessEntityIdentifierRecord.objects.count(), 2)
        self.assertEqual(
            LegalEntityRecord.objects.filter(attribute=LegalEntityRecord.ATTRIBUTE_NAME).count(),
            2,
        )
        self.assertEqual(
            LegalEntityRecord.objects.filter(attribute=LegalEntityRecord.ATTRIBUTE_LEGAL_ADDRESS).count(),
            2,
        )
        self.assertEqual(BusinessEntityRelationRecord.objects.count(), 1)
        self.assertEqual(BusinessEntityReorganizationEvent.objects.count(), 1)
        self.assertFalse(BusinessEntityRecord.objects.filter(name='ООО "Альфа"').exists())
        self.assertTrue(BusinessEntityRecord.objects.filter(name='ООО "Новый источник"').exists())
        relation = BusinessEntityRelationRecord.objects.select_related("event").get()
        self.assertEqual(relation.event.reorganization_event_uid, "90001-REO")
        self.assertEqual(relation.event.comment, "CSV relation")

    def test_csv_upload_rolls_back_when_references_are_invalid(self):
        upload = self._make_csv_upload(
            [
                {
                    "section": "business_entity",
                    "business_entity_ref": "00020-BSN",
                    "position": "1",
                    "business_entity_name": 'ООО "Промежуточная"',
                },
                {
                    "section": "identifier",
                    "business_entity_ref": "missing-BSN",
                    "identifier_ref": "00020-IDN",
                    "position": "1",
                    "identifier_type": "ОГРН",
                    "registration_country_code": "643",
                    "registration_country_name": "Россия",
                    "registration_number": "123",
                },
            ]
        )

        response = self.client.post(reverse("business_registry_csv_upload"), {"csv_file": upload})

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["warnings"])
        self.assertTrue(BusinessEntityRecord.objects.filter(name='ООО "Альфа"').exists())
        self.assertEqual(BusinessEntityRecord.objects.count(), 2)
        self.assertEqual(BusinessEntityIdentifierRecord.objects.count(), 2)
        self.assertEqual(BusinessEntityRelationRecord.objects.count(), 1)

    def test_csv_upload_accepts_multiple_relations_for_same_event_without_event_position(self):
        upload = self._make_csv_upload(
            [
                {
                    "section": "business_entity",
                    "business_entity_ref": "00030-BSN",
                    "position": "1",
                    "business_entity_name": 'ООО "Источник 1"',
                },
                {
                    "section": "business_entity",
                    "business_entity_ref": "00031-BSN",
                    "position": "2",
                    "business_entity_name": 'ООО "Источник 2"',
                },
                {
                    "section": "business_entity",
                    "business_entity_ref": "00032-BSN",
                    "position": "3",
                    "business_entity_name": 'ООО "Приемник"',
                },
                {
                    "section": "identifier",
                    "business_entity_ref": "00030-BSN",
                    "identifier_ref": "00030-IDN",
                    "position": "1",
                    "registration_country_code": "643",
                    "registration_country_name": "Россия",
                },
                {
                    "section": "identifier",
                    "business_entity_ref": "00031-BSN",
                    "identifier_ref": "00031-IDN",
                    "position": "2",
                    "registration_country_code": "643",
                    "registration_country_name": "Россия",
                },
                {
                    "section": "identifier",
                    "business_entity_ref": "00032-BSN",
                    "identifier_ref": "00032-IDN",
                    "position": "3",
                    "registration_country_code": "643",
                    "registration_country_name": "Россия",
                },
                {
                    "section": "name",
                    "business_entity_ref": "00030-BSN",
                    "identifier_ref": "00030-IDN",
                    "position": "1",
                    "short_name": 'ООО "Источник 1"',
                },
                {
                    "section": "name",
                    "business_entity_ref": "00031-BSN",
                    "identifier_ref": "00031-IDN",
                    "position": "2",
                    "short_name": 'ООО "Источник 2"',
                },
                {
                    "section": "name",
                    "business_entity_ref": "00032-BSN",
                    "identifier_ref": "00032-IDN",
                    "position": "3",
                    "short_name": 'ООО "Приемник"',
                },
                {
                    "section": "address",
                    "business_entity_ref": "00030-BSN",
                    "identifier_ref": "00030-IDN",
                    "position": "4",
                },
                {
                    "section": "address",
                    "business_entity_ref": "00031-BSN",
                    "identifier_ref": "00031-IDN",
                    "position": "5",
                },
                {
                    "section": "address",
                    "business_entity_ref": "00032-BSN",
                    "identifier_ref": "00032-IDN",
                    "position": "6",
                },
                {
                    "section": "relation",
                    "event_ref": "90010-REO",
                    "from_business_entity_ref": "00030-BSN",
                    "to_business_entity_ref": "00032-BSN",
                    "position": "1",
                    "relation_type": "Слияние",
                    "event_uid": "90010-REO",
                    "event_date": "2026-03-01",
                    "comment": "two sources",
                },
                {
                    "section": "relation",
                    "event_ref": "90010-REO",
                    "from_business_entity_ref": "00031-BSN",
                    "to_business_entity_ref": "00032-BSN",
                    "position": "2",
                    "relation_type": "Слияние",
                    "event_uid": "90010-REO",
                    "event_date": "2026-03-01",
                    "comment": "two sources",
                },
            ]
        )

        response = self.client.post(reverse("business_registry_csv_upload"), {"csv_file": upload})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(BusinessEntityReorganizationEvent.objects.count(), 1)
        self.assertEqual(BusinessEntityRelationRecord.objects.count(), 2)
        event = BusinessEntityReorganizationEvent.objects.get()
        self.assertEqual(event.reorganization_event_uid, "90010-REO")
        self.assertEqual(event.position, 1)


class BusinessEntityIdentifierFormTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="bei-form-user",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.country = OKSMCountry.objects.create(
            number=643,
            code="643",
            short_name="Россия",
            full_name="Российская Федерация",
            alpha2="RU",
            alpha3="RUS",
            position=1,
        )
        LegalEntityIdentifier.objects.create(
            identifier="ОГРН",
            full_name="Основной государственный регистрационный номер",
            country=self.country,
            position=1,
        )
        TerritorialDivision.objects.create(
            country=self.country,
            region_name="Москва",
            region_code="77",
            effective_date=date(2020, 1, 1),
            position=1,
        )
        self.business_entity = BusinessEntityRecord.objects.create(
            name='ООО "Дата"',
            position=1,
        )

    def test_create_form_wires_region_autofill_endpoint_for_identifier_number(self):
        response = self.client.get(reverse("bei_form_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("ler_region_autofill"))
        self.assertContains(response, 'id="id_number"', html=False)
        self.assertContains(response, 'id="id_registration_region"', html=False)

    def test_create_accepts_registration_date_in_russian_format(self):
        response = self.client.post(
            reverse("bei_form_create"),
            {
                "business_entity": str(self.business_entity.pk),
                "business_entity_autocomplete": f"{self.business_entity.pk:05d}-BSN",
                "registration_country": str(self.country.pk),
                "registration_region": "Москва",
                "identifier_type": "ОГРН",
                "number": "1234567890123",
                "registration_date": "15.03.2026",
                "valid_from": "",
                "valid_to": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        record = BusinessEntityIdentifierRecord.objects.get()
        self.assertEqual(record.registration_date, date(2026, 3, 15))
        self.assertEqual(record.registration_code, "643")
        self.assertEqual(record.registration_region_code, "77")
        self.assertIn("HX-Trigger", response.headers)
        hx_trigger = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(hx_trigger["classifiers-updated"]["source"], "bei-select")
        self.assertEqual(
            hx_trigger["classifiers-updated"]["affected"],
            ["ler-select", "bea-select"],
        )

    def test_regions_endpoint_filters_by_registration_date(self):
        TerritorialDivision.objects.create(
            country=self.country,
            region_name="Старая область",
            region_code="OLD",
            effective_date=date(2020, 1, 1),
            abolished_date=date(2024, 12, 31),
            position=1,
        )
        TerritorialDivision.objects.create(
            country=self.country,
            region_name="Новая область",
            region_code="NEW",
            effective_date=date(2025, 1, 1),
            position=2,
        )

        response = self.client.get(
            reverse("ler_regions_for_country"),
            {
                "country_id": self.country.pk,
                "date": "15.03.2026",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Новая область", response.json()["regions"])
        self.assertNotIn("Старая область", response.json()["regions"])

    def test_form_defaults_registration_country_to_russia(self):
        form = BusinessEntityIdentifierRecordForm()

        self.assertEqual(form.fields["registration_country"].initial, self.country.pk)

    def test_region_code_endpoint_filters_by_registration_date(self):
        TerritorialDivision.objects.create(
            country=self.country,
            region_name="Тестовый регион",
            region_code="01",
            effective_date=date(2020, 1, 1),
            abolished_date=date(2024, 12, 31),
            position=10,
        )
        TerritorialDivision.objects.create(
            country=self.country,
            region_name="Тестовый регион",
            region_code="02",
            effective_date=date(2025, 1, 1),
            position=11,
        )

        response = self.client.get(
            reverse("ler_region_code_for_country"),
            {
                "country_id": self.country.pk,
                "region_name": "Тестовый регион",
                "date": "15.03.2026",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], "02")


class BusinessEntityRelationMergeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="brl-merge-user",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.from_a = BusinessEntityRecord.objects.create(name='ООО "Альфа"', position=1)
        self.from_b = BusinessEntityRecord.objects.create(name='ООО "Бета"', position=2)
        self.from_c = BusinessEntityRecord.objects.create(name='ООО "Гамма"', position=3)

    def test_merge_requires_at_least_two_sources(self):
        response = self.client.post(
            reverse("brl_form_create"),
            {
                "relation_type": "Слияние",
                "from_business_entity_ids": [str(self.from_a.pk)],
                "merge_target_name": 'ООО "Объединенная"',
                "comment": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Для типа связи «Слияние» выберите минимум два значения")
        self.assertEqual(BusinessEntityRelationRecord.objects.count(), 0)
        self.assertEqual(BusinessEntityRecord.objects.count(), 3)

    def test_merge_create_creates_new_business_entity_and_relations(self):
        response = self.client.post(
            reverse("brl_form_create"),
            {
                "relation_type": "Слияние",
                "from_business_entity_ids": [str(self.from_a.pk), str(self.from_b.pk)],
                "merge_target_name": 'ООО "Объединенная"',
                "comment": "Комментарий",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(BusinessEntityRecord.objects.count(), 4)
        new_entity = BusinessEntityRecord.objects.order_by("-id").first()
        self.assertEqual(new_entity.name, 'ООО "Объединенная"')
        self.assertTrue(new_entity.identifiers.exists())

        relations = BusinessEntityRelationRecord.objects.order_by("from_business_entity_id")
        self.assertEqual(relations.count(), 2)
        self.assertEqual(BusinessEntityReorganizationEvent.objects.count(), 1)
        self.assertEqual(set(relations.values_list("event__reorganization_event_uid", flat=True)), {"00001-REO"})
        self.assertEqual(set(relations.values_list("event__relation_type", flat=True)), {"Слияние"})
        self.assertEqual(
            list(relations.values_list("from_business_entity_id", flat=True)),
            [self.from_a.pk, self.from_b.pk],
        )
        self.assertEqual(
            set(relations.values_list("to_business_entity_id", flat=True)),
            {new_entity.pk},
        )


class BusinessEntityRelationJoinTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="brl-join-user",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.from_entity = BusinessEntityRecord.objects.create(name='ООО "Альфа"', position=1)
        self.to_a = BusinessEntityRecord.objects.create(name='ООО "Бета"', position=2)
        self.to_b = BusinessEntityRecord.objects.create(name='ООО "Гамма"', position=3)

    def test_join_requires_single_target(self):
        response = self.client.post(
            reverse("brl_form_create"),
            {
                "relation_type": "Присоединение",
                "from_business_entity_ids": [str(self.from_entity.pk)],
                "to_business_entity_ids": [str(self.to_a.pk), str(self.to_b.pk)],
                "comment": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Для типа связи «Присоединение» выберите только одно значение")
        self.assertEqual(BusinessEntityRelationRecord.objects.count(), 0)


class BusinessEntityRelationSplitTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="brl-split-user",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.from_a = BusinessEntityRecord.objects.create(name='ООО "Альфа"', position=1)
        self.from_b = BusinessEntityRecord.objects.create(name='ООО "Бета"', position=2)
        BusinessEntityIdentifierRecord.objects.create(
            business_entity=self.from_a,
            identifier_type="ИНН",
            number="111",
            valid_from=date(2024, 1, 1),
            valid_to=date(2024, 5, 31),
            is_active=False,
            position=1,
        )
        self.latest_identifier = BusinessEntityIdentifierRecord.objects.create(
            business_entity=self.from_a,
            identifier_type="ОГРН",
            number="222",
            valid_from=date(2024, 6, 1),
            valid_to=None,
            is_active=True,
            position=2,
        )

    def test_split_requires_single_source(self):
        response = self.client.post(
            reverse("brl_form_create"),
            {
                "relation_type": "Разделение",
                "from_business_entity_ids": [str(self.from_a.pk), str(self.from_b.pk)],
                "split_target_existing_ids": ["", ""],
                "split_target_names": ['ООО "Новое 1"', 'ООО "Новое 2"'],
                "comment": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Для типа связи «Разделение» выберите только одно значение")
        self.assertEqual(BusinessEntityRelationRecord.objects.count(), 0)

    def test_split_create_creates_multiple_new_targets(self):
        response = self.client.post(
            reverse("brl_form_create"),
            {
                "relation_type": "Разделение",
                "from_business_entity_ids": [str(self.from_a.pk)],
                "split_target_existing_ids": ["", ""],
                "split_target_names": ['ООО "Новое 1"', 'ООО "Новое 2"'],
                "event_date": "2025-03-15",
                "comment": "Комментарий",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(BusinessEntityRecord.objects.count(), 4)
        new_entities = list(BusinessEntityRecord.objects.order_by("id")[2:])
        self.assertEqual([item.name for item in new_entities], ['ООО "Новое 1"', 'ООО "Новое 2"'])
        self.assertTrue(all(item.identifiers.exists() for item in new_entities))

        relations = BusinessEntityRelationRecord.objects.order_by("to_business_entity_id")
        self.assertEqual(relations.count(), 2)
        self.assertEqual(BusinessEntityReorganizationEvent.objects.count(), 1)
        self.assertEqual(set(relations.values_list("event__reorganization_event_uid", flat=True)), {"00001-REO"})
        self.assertEqual(set(relations.values_list("event__relation_type", flat=True)), {"Разделение"})
        self.assertEqual(
            set(relations.values_list("from_business_entity_id", flat=True)),
            {self.from_a.pk},
        )
        self.assertEqual(
            [item.to_business_entity.name for item in relations.select_related("to_business_entity")],
            ['ООО "Новое 1"', 'ООО "Новое 2"'],
        )
        self.latest_identifier.refresh_from_db()
        self.assertEqual(self.latest_identifier.valid_to, date(2025, 3, 15))

    def test_spin_off_create_uses_same_flow_as_split(self):
        response = self.client.post(
            reverse("brl_form_create"),
            {
                "relation_type": "Выделение",
                "from_business_entity_ids": [str(self.from_a.pk)],
                "split_target_existing_ids": ["", ""],
                "split_target_names": ['ООО "Выделенное 1"', 'ООО "Выделенное 2"'],
                "comment": "Комментарий",
            },
        )

        self.assertEqual(response.status_code, 200)
        relations = BusinessEntityRelationRecord.objects.order_by("to_business_entity_id")
        self.assertEqual(relations.count(), 2)
        self.assertEqual(BusinessEntityReorganizationEvent.objects.count(), 1)
        self.assertEqual(set(relations.values_list("event__reorganization_event_uid", flat=True)), {"00001-REO"})
        self.assertEqual(set(relations.values_list("event__relation_type", flat=True)), {"Выделение"})
        self.assertEqual(
            [item.to_business_entity.name for item in relations.select_related("to_business_entity")],
            ['ООО "Выделенное 1"', 'ООО "Выделенное 2"'],
        )


class BusinessEntityRelationEventEditingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="brl-edit-user",
            password="secret",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.from_a = BusinessEntityRecord.objects.create(name='ООО "Альфа"', position=1)
        self.from_b = BusinessEntityRecord.objects.create(name='ООО "Бета"', position=2)
        self.to_a = BusinessEntityRecord.objects.create(name='ООО "Гамма"', position=3)
        self.to_b = BusinessEntityRecord.objects.create(name='ООО "Дельта"', position=4)
        self.to_c = BusinessEntityRecord.objects.create(name='ООО "Эпсилон"', position=5)
        self.event = BusinessEntityReorganizationEvent.objects.create(
            reorganization_event_uid="00042-REO",
            relation_type="Слияние",
            event_date=date(2025, 1, 10),
            comment="Старый комментарий",
            position=1,
        )
        self.rel_a = BusinessEntityRelationRecord.objects.create(
            event=self.event,
            from_business_entity=self.from_a,
            to_business_entity=self.to_a,
            position=1,
        )
        self.rel_b = BusinessEntityRelationRecord.objects.create(
            event=self.event,
            from_business_entity=self.from_b,
            to_business_entity=self.to_a,
            position=2,
        )

    def test_editing_one_row_updates_event_and_rebuilds_only_its_relations(self):
        response = self.client.post(
            reverse("brl_form_edit", args=[self.rel_a.pk]),
            {
                "relation_type": "Присоединение",
                "event_date": "2025-04-01",
                "comment": "Новый комментарий",
                "from_business_entity_ids": [str(self.from_a.pk), str(self.from_b.pk)],
                "to_business_entity_ids": [str(self.to_c.pk)],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.event.refresh_from_db()
        self.assertEqual(self.event.relation_type, "Присоединение")
        self.assertEqual(self.event.event_date, date(2025, 4, 1))
        self.assertEqual(self.event.comment, "Новый комментарий")

        relations = list(self.event.relations.order_by("position", "id"))
        self.assertEqual(len(relations), 2)
        self.assertEqual(
            {(item.from_business_entity_id, item.to_business_entity_id) for item in relations},
            {(self.from_a.pk, self.to_c.pk), (self.from_b.pk, self.to_c.pk)},
        )
        self.assertEqual(BusinessEntityReorganizationEvent.objects.count(), 1)

    def test_deleting_last_row_also_deletes_event(self):
        self.client.post(reverse("brl_delete", args=[self.rel_a.pk]))
        self.assertTrue(BusinessEntityReorganizationEvent.objects.filter(pk=self.event.pk).exists())
        self.assertEqual(BusinessEntityRelationRecord.objects.filter(event=self.event).count(), 1)

        remaining = BusinessEntityRelationRecord.objects.get(event=self.event)
        self.client.post(reverse("brl_delete", args=[remaining.pk]))
        self.assertFalse(BusinessEntityReorganizationEvent.objects.filter(pk=self.event.pk).exists())
        self.assertEqual(BusinessEntityRelationRecord.objects.count(), 0)


class BusinessEntityReorganizationMigrationTests(TransactionTestCase):
    serialized_rollback = True
    migrate_from = [("classifiers_app", "0042_businessentityreorganizationevent_and_relation_event")]
    migrate_to = [("classifiers_app", "0044_finalize_reorganization_event_normalization")]

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.migrate_from)
        old_apps = self.executor.loader.project_state(self.migrate_from).apps

        BusinessEntityRecord = old_apps.get_model("classifiers_app", "BusinessEntityRecord")
        BusinessEntityRelationRecord = old_apps.get_model("classifiers_app", "BusinessEntityRelationRecord")

        from_entity = BusinessEntityRecord.objects.create(name='ООО "Источник"', position=1)
        to_entity = BusinessEntityRecord.objects.create(name='ООО "Приемник"', position=2)
        BusinessEntityRelationRecord.objects.create(
            reorganization_event_uid="00077-REO",
            relation_type="Слияние",
            event_date=date(2025, 2, 15),
            comment="Историческая строка",
            from_business_entity_id=from_entity.pk,
            to_business_entity_id=to_entity.pk,
            position=1,
        )

        self.executor = MigrationExecutor(connection)
        self.executor.loader.build_graph()
        self.executor.migrate(self.migrate_to)
        self.apps = self.executor.loader.project_state(self.migrate_to).apps

    def test_backfill_creates_one_event_per_legacy_relation_row(self):
        BusinessEntityReorganizationEvent = self.apps.get_model(
            "classifiers_app",
            "BusinessEntityReorganizationEvent",
        )
        BusinessEntityRelationRecord = self.apps.get_model("classifiers_app", "BusinessEntityRelationRecord")

        relation = BusinessEntityRelationRecord.objects.select_related("event").get()
        self.assertIsNotNone(relation.event_id)
        self.assertEqual(BusinessEntityReorganizationEvent.objects.count(), 1)
        self.assertEqual(relation.event.reorganization_event_uid, "00077-REO")
        self.assertEqual(relation.event.relation_type, "Слияние")
        self.assertEqual(relation.event.event_date, date(2025, 2, 15))
        self.assertEqual(relation.event.comment, "Историческая строка")
