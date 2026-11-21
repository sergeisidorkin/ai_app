from django.db import migrations, models


SPEC_SHORT_NAME = "SPEC"
SPEC_DEFAULTS = {
    "display_name": "Спецпроект",
    "name_en": "Special Project",
    "name_ru": "Специальный проект",
    "consulting_type": "Спецуслуги",
    "service_category": "Спецуслуги",
    "service_code": "X",
    "service_subtype": "Прочее",
    "accuracy": "",
    "is_group_owner": True,
    "is_system": True,
    "is_product_group": False,
    "group_id": None,
}
DSC_CODE = "DSC"


def seed_system_spec_product(apps, schema_editor):
    ConsultingDirectionType = apps.get_model("policy_app", "ConsultingDirectionType")
    ConsultingServiceType = apps.get_model("policy_app", "ConsultingServiceType")
    ConsultingServiceSubtype = apps.get_model("policy_app", "ConsultingServiceSubtype")
    Product = apps.get_model("policy_app", "Product")
    ServiceBlockClassifier = apps.get_model("policy_app", "ServiceBlockClassifier")
    TypicalSection = apps.get_model("policy_app", "TypicalSection")
    db_alias = schema_editor.connection.alias

    consulting_type = (
        ConsultingDirectionType.objects.using(db_alias)
        .filter(name="Спецуслуги")
        .order_by("position", "id")
        .first()
    )
    if consulting_type is None:
        return
    service_type = (
        ConsultingServiceType.objects.using(db_alias)
        .filter(consulting_type_id=consulting_type.pk, name="Спецуслуги", code="X")
        .order_by("position", "id")
        .first()
    )
    if service_type is None:
        service_type = (
            ConsultingServiceType.objects.using(db_alias)
            .filter(consulting_type_id=consulting_type.pk, name="Спецуслуги")
            .order_by("position", "id")
            .first()
        )
    if service_type is None:
        return
    subtype = (
        ConsultingServiceSubtype.objects.using(db_alias)
        .filter(service_type_id=service_type.pk, name="Прочее")
        .order_by("position", "id")
        .first()
    )
    if subtype is None:
        last_position = (
            ConsultingServiceSubtype.objects.using(db_alias)
            .filter(service_type_id=service_type.pk)
            .order_by("-position")
            .values_list("position", flat=True)
            .first()
            or 0
        )
        subtype = ConsultingServiceSubtype.objects.using(db_alias).create(
            direction_id=service_type.direction_id,
            service_type_id=service_type.pk,
            name="Прочее",
            position=last_position + 1,
        )

    product = (
        Product.objects.using(db_alias)
        .filter(short_name=SPEC_SHORT_NAME)
        .order_by("id")
        .first()
    )
    fields = {
        **SPEC_DEFAULTS,
        "consulting_type_ref_id": consulting_type.pk,
        "service_category_ref_id": service_type.pk,
        "service_subtype_ref_id": subtype.pk,
    }
    if product is None:
        position = (
            Product.objects.using(db_alias).order_by("-position").values_list("position", flat=True).first()
            or 0
        ) + 1
        product = Product.objects.using(db_alias).create(
            short_name=SPEC_SHORT_NAME,
            position=position,
            **fields,
        )
    else:
        for name, value in fields.items():
            setattr(product, name, value)
        product.save(using=db_alias)

    block = (
        ServiceBlockClassifier.objects.using(db_alias)
        .filter(code=DSC_CODE)
        .order_by("id")
        .first()
    )
    if block is None:
        position = (
            ServiceBlockClassifier.objects.using(db_alias)
            .order_by("-position")
            .values_list("position", flat=True)
            .first()
            or 0
        ) + 1
        block = ServiceBlockClassifier.objects.using(db_alias).create(
            code=DSC_CODE,
            short_name="Description",
            short_name_ru="Описание",
            name_en="Product description",
            name_ru="Описание продукта",
            accounting_type="Разделы",
            position=position,
        )
    section = (
        TypicalSection.objects.using(db_alias)
        .filter(product_id=product.pk, code=DSC_CODE)
        .order_by("position", "id")
        .first()
    )
    if section is None:
        TypicalSection.objects.using(db_alias).create(
            product_id=product.pk,
            service_block_id=block.pk,
            code=DSC_CODE,
            name_en=block.name_en or "Product description",
            name_ru=block.name_ru or "Описание продукта",
            exclude_from_tkp_autofill=False,
            is_system=True,
            position=1,
        )
    else:
        section.service_block_id = block.pk
        section.is_system = True
        section.exclude_from_tkp_autofill = False
        section.name_en = block.name_en or section.name_en
        section.name_ru = block.name_ru or section.name_ru
        section.save(using=db_alias)


class Migration(migrations.Migration):
    # Индекс нельзя создать в той же транзакции, где seed меняет строки.
    atomic = False

    dependencies = [
        ("policy_app", "0065_product_usage_count"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="is_system",
            field=models.BooleanField(db_index=True, default=False, verbose_name="Системный продукт"),
        ),
        migrations.RunPython(seed_system_spec_product, migrations.RunPython.noop),
    ]
