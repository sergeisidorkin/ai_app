from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.http import QueryDict
from django.test import RequestFactory, TestCase

from policy_app.forms import ProductForm, TypicalSectionForm
from policy_app.models import (
    ConsultingServiceSubtype,
    Product,
    ServiceBlockClassifier,
    SYSTEM_DSC_SECTION_CODE,
    SYSTEM_SPEC_PRODUCT_SHORT_NAME,
    TypicalSection,
    ensure_system_spec_product,
)
from policy_app.product_groups import validate_group_members
from policy_app.views import product_delete


def seed_spec_catalog():
    """Каталог «Спецуслуги» может отсутствовать после очистки тестовой базы."""
    from policy_app.models import ConsultingDirection, ConsultingDirectionType, ConsultingServiceType

    direction = ConsultingDirection.objects.order_by("id").first()
    if direction is None:
        direction = ConsultingDirection.objects.create(position=1)
    kind = ConsultingDirectionType.objects.filter(name="Спецуслуги").order_by("id").first()
    if kind is None:
        kind = ConsultingDirectionType.objects.create(
            name="Спецуслуги",
            direction=direction,
            position=1,
        )
    if not ConsultingServiceType.objects.filter(consulting_type=kind, name="Спецуслуги").exists():
        ConsultingServiceType.objects.create(
            direction=kind.direction,
            consulting_type=kind,
            name="Спецуслуги",
            code="X",
            position=1,
        )
    return ensure_system_spec_product()


class SystemSpecProductTests(TestCase):
    def setUp(self):
        self.spec = seed_spec_catalog()

    def test_ensure_creates_locked_card_and_repairs_it(self):
        self.assertIsNotNone(self.spec)
        self.assertEqual(self.spec.short_name, SYSTEM_SPEC_PRODUCT_SHORT_NAME)
        self.assertEqual(self.spec.display_name, "Спецпроект")
        self.assertEqual(self.spec.name_en, "Special Project")
        self.assertEqual(self.spec.name_ru, "Специальный проект")
        self.assertEqual(self.spec.service_code, "X")
        self.assertEqual(self.spec.accuracy, "")
        self.assertTrue(self.spec.is_group_owner)
        self.assertTrue(self.spec.is_system)
        self.assertEqual(self.spec.consulting_type_ref.name, "Спецуслуги")
        self.assertEqual(self.spec.service_category_ref.name, "Спецуслуги")
        self.assertEqual(self.spec.service_category_ref.code, "X")
        self.assertEqual(self.spec.service_subtype_ref.name, "Прочее")
        self.assertEqual(
            ConsultingServiceSubtype.objects.filter(name="Прочее", service_type=self.spec.service_category_ref).count(),
            1,
        )
        self.assertTrue(
            TypicalSection.objects.filter(product=self.spec, code=SYSTEM_DSC_SECTION_CODE, is_system=True).exists()
        )

        self.spec.display_name = "Чужое имя"
        self.spec.accuracy = ">50%"
        self.spec.is_system = False
        self.spec.save()
        repaired = ensure_system_spec_product()
        self.assertEqual(repaired.pk, self.spec.pk)
        self.assertEqual(repaired.display_name, "Спецпроект")
        self.assertEqual(repaired.accuracy, "")
        self.assertTrue(repaired.is_system)

    def test_form_ignores_posted_identity(self):
        data = QueryDict("", mutable=True)
        data.update(
            {
                "display_name": "Другое",
                "short_name": "OTHER",
                "name_en": "Other",
                "name_ru": "Другое",
                "accuracy": ">50%",
                "consulting_type_ref": str(self.spec.consulting_type_ref_id),
                "service_category_ref": str(self.spec.service_category_ref_id),
                "service_subtype_ref": str(self.spec.service_subtype_ref_id),
                "owner_ids": "__group__",
            }
        )
        form = ProductForm(data=data, instance=self.spec)
        self.assertTrue(form.fields["display_name"].disabled)
        self.assertTrue(form.fields["short_name"].disabled)
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.display_name, "Спецпроект")
        self.assertEqual(saved.short_name, "SPEC")
        self.assertEqual(saved.accuracy, "")
        self.assertTrue(saved.is_group_owner)

    def test_delete_is_rejected(self):
        user = get_user_model().objects.create_user(username="spec-delete", password="secret", is_staff=True)
        request = RequestFactory().post(f"/policy/product/{self.spec.pk}/delete/")
        request.user = user
        response = product_delete(request, self.spec.pk)
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Product.objects.filter(pk=self.spec.pk).exists())

    def test_grouping_is_rejected(self):
        other = Product.objects.create(
            short_name="SPEC-PEER",
            display_name="Рядом",
            name_en="Peer",
            name_ru="Рядом",
            consulting_type_ref=self.spec.consulting_type_ref,
            service_category_ref=self.spec.service_category_ref,
            service_subtype_ref=self.spec.service_subtype_ref,
            is_group_owner=True,
            position=9000,
        )
        with self.assertRaises(ValidationError):
            validate_group_members([self.spec, other])

    def test_extra_section_is_rejected(self):
        block = ServiceBlockClassifier.objects.create(
            code="ZZZ",
            short_name="extra",
            short_name_ru="лишний",
            name_ru="Лишний блок",
            accounting_type="Разделы",
            position=50,
        )
        form = TypicalSectionForm(
            data={
                "product": self.spec.pk,
                "service_block": block.pk,
                "name_en": "Extra",
                "name_ru": "Лишний",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("Спецпроект", str(form.errors))
