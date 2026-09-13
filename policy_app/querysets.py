from django.db.models import Prefetch

from experts_app.models import ExpertSpecialty
from group_app.models import GroupMember

from .models import (
    ConsultingDirection,
    ConsultingDirectionType,
    ConsultingServiceSubtype,
    ConsultingServiceType,
)


def ordered_owner_display_prefetch():
    return Prefetch(
        "owners",
        queryset=GroupMember.objects.only(
            "id",
            "short_name",
            "position",
        ).order_by("position", "id"),
        to_attr="_policy_owner_display_items",
    )


def with_policy_consulting_catalog(queryset):
    return queryset.prefetch_related(
        Prefetch(
            "consulting_types",
            queryset=ConsultingDirectionType.objects.order_by("position", "id"),
            to_attr="_policy_consulting_types",
        ),
        Prefetch(
            "service_types",
            queryset=ConsultingServiceType.objects.select_related(
                "consulting_type",
            ).order_by(
                "consulting_type__position",
                "position",
                "id",
            ),
            to_attr="_policy_service_types",
        ),
        Prefetch(
            "service_subtypes",
            queryset=ConsultingServiceSubtype.objects.select_related(
                "service_type",
                "service_type__consulting_type",
            ).order_by(
                "service_type__consulting_type__position",
                "service_type__position",
                "position",
                "id",
            ),
            to_attr="_policy_service_subtypes",
        ),
    )


def policy_consulting_directions_queryset():
    return with_policy_consulting_catalog(
        ConsultingDirection.objects.all()
    ).order_by("position", "id")


def ordered_specialties_display_prefetch():
    return Prefetch(
        "specialties",
        queryset=ExpertSpecialty.objects.select_related(
            "expertise_dir",
        ).order_by("position", "id"),
        to_attr="_policy_display_specialties",
    )
