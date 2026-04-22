from django.db import migrations


DEFAULT_CONSULTING_TYPES = [
    "Горный",
    "Геологический",
    "Экологический",
    "Спецуслуги",
]

DEFAULT_SERVICE_TYPES = [
    (
        "Аудит",
        "A",
        [
            "Аудит соответствия стандартам",
            "Аудит проектных решений",
            "Аудит эффективности",
            "Аудит рисков",
        ],
    ),
    (
        "Инжиниринг",
        "T",
        [
            "По международным стандартам",
            "По российским стандартам",
        ],
    ),
    (
        "Оценка",
        "O",
        [
            "Экспертиза по международным стандартам",
            "Экспертиза по российским стандартам",
            "Оценка ресурсов (MRE)",
        ],
    ),
    (
        "Сопровождение",
        "S",
        [
            "По международным стандартам",
            "По российским стандартам",
            "Прочее",
        ],
    ),
    (
        "Исследование",
        "R",
        [
            "3D моделирование",
            "Гидрогеология",
            "Рынок",
        ],
    ),
    (
        "Спецуслуги",
        "X",
        [
            "Технический перевод",
        ],
    ),
]


def seed_consulting_catalog(apps, schema_editor):
    ConsultingDirection = apps.get_model("policy_app", "ConsultingDirection")
    ConsultingDirectionType = apps.get_model("policy_app", "ConsultingDirectionType")
    ConsultingServiceType = apps.get_model("policy_app", "ConsultingServiceType")
    ConsultingServiceSubtype = apps.get_model("policy_app", "ConsultingServiceSubtype")
    Product = apps.get_model("policy_app", "Product")

    direction = ConsultingDirection.objects.order_by("position", "id").first()
    if direction is None:
        direction = ConsultingDirection.objects.create(position=1)

    consulting_types = {}
    for position, name in enumerate(DEFAULT_CONSULTING_TYPES, start=1):
        item, _created = ConsultingDirectionType.objects.get_or_create(
            name=name,
            defaults={"direction_id": direction.pk, "position": position},
        )
        if item.direction_id != direction.pk or item.position != position:
            item.direction_id = direction.pk
            item.position = position
            item.save(update_fields=["direction", "position"])
        consulting_types[name] = item

    service_types = {}
    service_subtypes = {}
    for consulting_name in DEFAULT_CONSULTING_TYPES:
        consulting_type = consulting_types[consulting_name]
        for position, (service_name, code, subtype_names) in enumerate(DEFAULT_SERVICE_TYPES, start=1):
            service_type, created = ConsultingServiceType.objects.get_or_create(
                consulting_type_id=consulting_type.pk,
                name=service_name,
                defaults={
                    "direction_id": direction.pk,
                    "code": code,
                    "position": position,
                },
            )
            if not created and service_type.code not in ("", code):
                raise RuntimeError(
                    f"Конфликт кода для типа услуг '{service_name}' и вида '{consulting_name}'."
                )
            updates = []
            if service_type.direction_id != direction.pk:
                service_type.direction_id = direction.pk
                updates.append("direction")
            if service_type.code != code:
                service_type.code = code
                updates.append("code")
            if service_type.position != position:
                service_type.position = position
                updates.append("position")
            if updates:
                service_type.save(update_fields=updates)
            service_types[(consulting_name, service_name)] = service_type

            for subtype_position, subtype_name in enumerate(subtype_names, start=1):
                subtype, _created = ConsultingServiceSubtype.objects.get_or_create(
                    service_type_id=service_type.pk,
                    name=subtype_name,
                    defaults={
                        "direction_id": direction.pk,
                        "position": subtype_position,
                    },
                )
                updates = []
                if subtype.direction_id != direction.pk:
                    subtype.direction_id = direction.pk
                    updates.append("direction")
                if subtype.position != subtype_position:
                    subtype.position = subtype_position
                    updates.append("position")
                if updates:
                    subtype.save(update_fields=updates)
                service_subtypes[(consulting_name, service_name, subtype_name)] = subtype

    next_consulting_position = ConsultingDirectionType.objects.order_by("-position").values_list("position", flat=True).first() or 0

    for product in Product.objects.order_by("position", "id").iterator():
        consulting_name = (product.consulting_type or "").strip()
        service_name = (product.service_category or "").strip()
        subtype_name = (product.service_subtype or "").strip()
        code = (product.service_code or "").strip()

        if not consulting_name or not service_name or not subtype_name:
            continue

        consulting_type = consulting_types.get(consulting_name)
        if consulting_type is None:
            next_consulting_position += 1
            consulting_type = ConsultingDirectionType.objects.create(
                direction_id=direction.pk,
                name=consulting_name,
                position=next_consulting_position,
            )
            consulting_types[consulting_name] = consulting_type

        service_type = service_types.get((consulting_name, service_name))
        if service_type is None:
            service_type = ConsultingServiceType.objects.create(
                direction_id=direction.pk,
                consulting_type_id=consulting_type.pk,
                name=service_name,
                code=code,
                position=(ConsultingServiceType.objects.filter(consulting_type_id=consulting_type.pk)
                          .order_by("-position").values_list("position", flat=True).first() or 0) + 1,
            )
            service_types[(consulting_name, service_name)] = service_type
        elif code and service_type.code not in ("", code):
            raise RuntimeError(
                f"Конфликт кода '{code}' для типа услуг '{service_name}' и вида '{consulting_name}'."
            )
        elif code and service_type.code == "":
            service_type.code = code
            service_type.save(update_fields=["code"])

        subtype = service_subtypes.get((consulting_name, service_name, subtype_name))
        if subtype is None:
            subtype = ConsultingServiceSubtype.objects.create(
                direction_id=direction.pk,
                service_type_id=service_type.pk,
                name=subtype_name,
                position=(ConsultingServiceSubtype.objects.filter(service_type_id=service_type.pk)
                          .order_by("-position").values_list("position", flat=True).first() or 0) + 1,
            )
            service_subtypes[(consulting_name, service_name, subtype_name)] = subtype

        product.consulting_type_ref_id = consulting_type.pk
        product.service_category_ref_id = service_type.pk
        product.service_subtype_ref_id = subtype.pk
        product.service_code = service_type.code or code
        product.save(
            update_fields=[
                "consulting_type_ref",
                "service_category_ref",
                "service_subtype_ref",
                "service_code",
            ]
        )


class Migration(migrations.Migration):
    dependencies = [
        ("policy_app", "0039_consulting_direction_catalog"),
    ]

    operations = [
        migrations.RunPython(seed_consulting_catalog, migrations.RunPython.noop),
    ]
