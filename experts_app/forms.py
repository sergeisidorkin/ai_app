from datetime import date as date_type

from django import forms
from django.db.models import Q

from classifiers_app.models import OKSMCountry, TerritorialDivision
from group_app.models import OrgUnit
from policy_app.models import Grade
from users_app.models import Employee
from .models import ExpertSpecialty, ExpertProfile


class ExpertSpecialtyForm(forms.ModelForm):
    class Meta:
        model = ExpertSpecialty
        fields = ["expertise_direction", "specialty", "specialty_en", "head_of_direction"]
        widgets = {
            "expertise_direction": forms.Select(attrs={"class": "form-select"}),
            "specialty": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Специальность",
            }),
            "specialty_en": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Specialty (English)",
            }),
            "head_of_direction": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["expertise_direction"].queryset = OrgUnit.objects.filter(
            Q(unit_type="expertise") | Q(level=1)
        )
        self.fields["expertise_direction"].label_from_instance = (
            lambda obj: obj.department_name
        )
        self.fields["expertise_direction"].empty_label = "---------"
        self.fields["expertise_direction"].required = False

        self.fields["head_of_direction"].queryset = Employee.objects.filter(
            Q(role="Руководитель направления") | Q(role="Директор")
        )
        self.fields["head_of_direction"].label_from_instance = (
            lambda obj: obj.job_title
        )
        self.fields["head_of_direction"].empty_label = "---------"
        self.fields["head_of_direction"].required = False


def _active_countries_qs():
    today = date_type.today()
    return OKSMCountry.objects.filter(
        Q(approval_date__isnull=True) | Q(approval_date__lte=today),
    ).filter(
        Q(expiry_date__isnull=True) | Q(expiry_date__gte=today),
    ).order_by("short_name")


def _active_regions_qs(country_pk=None):
    today = date_type.today()
    qs = TerritorialDivision.objects.filter(
        effective_date__lte=today,
    ).filter(
        Q(abolished_date__isnull=True) | Q(abolished_date__gte=today),
    )
    if country_pk:
        qs = qs.filter(country_id=country_pk)
    return qs.order_by("region_name")


class ExpertProfileForm(forms.ModelForm):
    class Meta:
        model = ExpertProfile
        fields = [
            "extra_email", "extra_phone",
            "expertise_direction", "grade",
            "country", "region", "status",
        ]
        widgets = {
            "extra_email": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "name@mail.ru",
            }),
            "extra_phone": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "+7 000 000-00-00",
            }),
            "expertise_direction": forms.Select(attrs={
                "class": "form-select",
                "id": "ep-direction-select",
            }),
            "grade": forms.Select(attrs={
                "class": "form-select",
                "id": "ep-grade-select",
            }),
            "country": forms.Select(attrs={
                "class": "form-select",
                "id": "ep-country-select",
            }),
            "region": forms.Select(attrs={
                "class": "form-select",
                "id": "ep-region-select",
            }),
            "status": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Статус",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["expertise_direction"].queryset = OrgUnit.objects.filter(
            Q(unit_type="expertise") | Q(level=1)
        )
        self.fields["expertise_direction"].label_from_instance = (
            lambda obj: obj.department_name
        )
        self.fields["expertise_direction"].empty_label = "---------"
        self.fields["expertise_direction"].required = False

        direction_pk = self._resolve_fk("expertise_direction")
        if direction_pk:
            self.fields["grade"].queryset = Grade.objects.filter(
                created_by__employee_profile__department_id=direction_pk
            )
        else:
            self.fields["grade"].queryset = Grade.objects.all()
        self.fields["grade"].label_from_instance = lambda obj: obj.grade_ru
        self.fields["grade"].empty_label = "---------"
        self.fields["grade"].required = False

        self.fields["country"].queryset = _active_countries_qs()
        self.fields["country"].label_from_instance = lambda obj: obj.short_name
        self.fields["country"].empty_label = "---------"
        self.fields["country"].required = False

        if not self.instance or not self.instance.pk or not self.instance.country_id:
            russia = _active_countries_qs().filter(short_name="Россия").first()
            if russia:
                self.initial.setdefault("country", russia.pk)

        country_pk = self._resolve_fk("country")
        if country_pk:
            self.fields["region"].queryset = _active_regions_qs(country_pk)
        else:
            self.fields["region"].queryset = TerritorialDivision.objects.none()
        self.fields["region"].label_from_instance = lambda obj: obj.region_name
        self.fields["region"].empty_label = "---------"
        self.fields["region"].required = False

    def _resolve_fk(self, field_name):
        if self.data:
            val = self.data.get(field_name)
            if val:
                try:
                    return int(val)
                except (ValueError, TypeError):
                    pass
        if self.instance and self.instance.pk:
            val = getattr(self.instance, f"{field_name}_id", None)
            if val:
                return val
        if field_name in self.initial:
            try:
                return int(self.initial[field_name])
            except (ValueError, TypeError):
                pass
        return None
