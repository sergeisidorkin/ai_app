from django import forms
from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone

from classifiers_app.models import OKVCurrency
from group_app.models import OrgUnit
from group_app.models import GroupMember
from .models import Product, TypicalSection, SectionStructure, ExpertiseDirection, Grade, Tariff, DEPARTMENT_HEAD_GROUP, DIRECTOR_GROUP

OWNER_GROUP_VALUE = "__group__"


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["short_name", "name_en", "display_name", "name_ru", "service_type"]
        widgets = {
            "short_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Краткое имя"}),
            "name_en": forms.TextInput(attrs={"class": "form-control", "placeholder": "English name"}),
            "display_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Отображаемое в системе имя"}),
            "name_ru": forms.TextInput(attrs={"class": "form-control", "placeholder": "Русское наименование"}),
            "service_type": forms.TextInput(attrs={"class": "form-control", "placeholder": "Тип услуги"}),
        }
        error_messages = {
            "short_name": {
                "unique": "Продукт с таким кратким именем уже существует.",
            },
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner_options = list(GroupMember.objects.order_by("position", "id").values("pk", "short_name"))
        self.selected_owner_ids = []
        self.is_group_selected = False
        if self.is_bound:
            owner_values = self.data.getlist("owner_ids")
            if OWNER_GROUP_VALUE in owner_values:
                self.is_group_selected = True
            else:
                self.selected_owner_ids = [int(v) for v in owner_values if v != OWNER_GROUP_VALUE and v.isdigit()]
        elif self.instance and self.instance.pk:
            if self.instance.is_group_owner:
                self.is_group_selected = True
            else:
                self.selected_owner_ids = list(
                    self.instance.owners.values_list("pk", flat=True)
                )

    def save(self, commit=True):
        obj = super().save(commit=False)
        owner_values = self.data.getlist("owner_ids")
        if OWNER_GROUP_VALUE in owner_values:
            obj.is_group_owner = True
        else:
            obj.is_group_owner = False
        if commit:
            obj.save()
            if obj.is_group_owner:
                obj.owners.clear()
            else:
                member_ids = [int(v) for v in owner_values if v != OWNER_GROUP_VALUE and v.isdigit()]
                obj.owners.set(member_ids)
        return obj

class TypicalSectionForm(forms.ModelForm):
    product = forms.ModelChoiceField(
        label="Продукт",
        queryset=Product.objects.all(),
        widget=forms.Select(attrs={"class": "form-select"})
    )
    expertise_dir = forms.ModelChoiceField(
        label="Экспертиза",
        queryset=ExpertiseDirection.objects.all(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    expertise_direction = forms.ModelChoiceField(
        label="Направление экспертизы",
        queryset=OrgUnit.objects.filter(
            Q(unit_type="expertise") | Q(unit_type="administrative", level=1)
        ),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = TypicalSection
        fields = ["product", "code", "short_name", "short_name_ru", "name_en", "name_ru", "accounting_type", "expertise_dir", "expertise_direction"]
        widgets = {
            "code": forms.TextInput(attrs={"class": "form-control", "placeholder": "Код"}),
            "short_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Short name EN"}),
            "short_name_ru": forms.TextInput(attrs={"class": "form-control", "placeholder": "Краткое имя RU"}),
            "name_en": forms.TextInput(attrs={"class": "form-control", "placeholder": "English section name"}),
            "name_ru": forms.TextInput(attrs={"class": "form-control", "placeholder": "Русское наименование раздела"}),
            "accounting_type": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["expertise_dir"].queryset = ExpertiseDirection.objects.order_by("position", "id")
        self.fields["expertise_dir"].label_from_instance = (
            lambda obj: f"{obj.short_name} {obj.name}"
        )
        qs = OrgUnit.objects.filter(
            Q(unit_type="expertise") | Q(unit_type="administrative", level=1)
        )
        self.fields["expertise_direction"].queryset = qs
        self.fields["expertise_direction"].label_from_instance = lambda obj: obj.department_name


class SectionStructureForm(forms.ModelForm):
    product = forms.ModelChoiceField(
        label="Продукт",
        queryset=Product.objects.all(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    section = forms.ModelChoiceField(
        label="Раздел",
        queryset=TypicalSection.objects.select_related("product").all(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["section"].label_from_instance = (
            lambda obj: f"{obj.product.short_name}: {obj.short_name}"
        )

    class Meta:
        model = SectionStructure
        fields = ["product", "section", "subsections"]
        widgets = {
            "subsections": forms.Textarea(attrs={
                "class": "form-control",
                "placeholder": "Наименование подраздела",
                "rows": 4,
            }),
        }


class ExpertiseDirectionForm(forms.ModelForm):
    class Meta:
        model = ExpertiseDirection
        fields = ["name", "short_name", "pricing_method"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Наименование направления"}),
            "short_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Краткое обозначение"}),
            "pricing_method": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner_options = list(GroupMember.objects.order_by("position", "id").values("pk", "short_name"))
        self.selected_owner_ids = []
        self.is_group_selected = False
        if self.instance and self.instance.pk:
            if self.instance.is_group_owner:
                self.is_group_selected = True
            else:
                self.selected_owner_ids = list(
                    self.instance.owners.values_list("pk", flat=True)
                )

    def save(self, commit=True):
        obj = super().save(commit=False)
        owner_values = self.data.getlist("owner_ids")
        if OWNER_GROUP_VALUE in owner_values:
            obj.is_group_owner = True
        else:
            obj.is_group_owner = False
        if commit:
            obj.save()
            if obj.is_group_owner:
                obj.owners.clear()
            else:
                member_ids = [int(v) for v in owner_values if v != OWNER_GROUP_VALUE and v.isdigit()]
                obj.owners.set(member_ids)
        return obj


class GradeForm(forms.ModelForm):
    owner = forms.ModelChoiceField(
        label="Руководитель",
        queryset=User.objects.filter(
            Q(groups__name=DEPARTMENT_HEAD_GROUP) | Q(groups__name=DIRECTOR_GROUP)
        ),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    currency = forms.ModelChoiceField(
        label="Валюта",
        queryset=OKVCurrency.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_currency"}),
    )

    class Meta:
        model = Grade
        fields = [
            "grade_en", "grade_ru", "qualification_levels",
            "qualification", "is_base_rate", "base_rate_share",
            "hourly_rate", "currency",
        ]
        widgets = {
            "grade_en": forms.TextInput(attrs={"class": "form-control", "placeholder": "Grade (English)"}),
            "grade_ru": forms.TextInput(attrs={"class": "form-control", "placeholder": "Грейд (русский)"}),
            "qualification_levels": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 20}),
            "qualification": forms.HiddenInput(),
            "is_base_rate": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "base_rate_share": forms.NumberInput(attrs={
                "class": "form-control", "min": -500, "max": 500,
                "style": "max-width:120px;",
            }),
            "hourly_rate": forms.TextInput(attrs={
                "class": "form-control js-grade-money", "inputmode": "decimal",
                "placeholder": "0,00",
            }),
        }

    def __init__(self, *args, request_user=None, **kwargs):
        if args and args[0]:
            data = args[0].copy()
            v = data.get("hourly_rate", "")
            if v:
                data["hourly_rate"] = str(v).replace("\u00a0", "").replace(" ", "").replace(",", ".")
            args = (data,) + args[1:]
        elif "data" in kwargs and kwargs["data"]:
            data = kwargs["data"].copy()
            v = data.get("hourly_rate", "")
            if v:
                data["hourly_rate"] = str(v).replace("\u00a0", "").replace(" ", "").replace(",", ".")
            kwargs["data"] = data
        super().__init__(*args, **kwargs)
        self.request_user = request_user
        self.fields["base_rate_share"].required = False
        self.fields["hourly_rate"].required = False
        self.fields["owner"].queryset = User.objects.filter(
            Q(groups__name=DEPARTMENT_HEAD_GROUP) | Q(groups__name=DIRECTOR_GROUP)
        ).distinct().order_by("last_name", "first_name", "username")
        self.fields["owner"].label_from_instance = lambda u: (
            f"{u.last_name} {u.first_name}".strip() or u.username
        )
        if self.instance and self.instance.pk:
            self.initial["owner"] = self.instance.created_by_id

        today = timezone.now().date()
        currency_qs = OKVCurrency.objects.filter(
            Q(approval_date__isnull=True) | Q(approval_date__lte=today),
            Q(expiry_date__isnull=True) | Q(expiry_date__gte=today),
        ).order_by("code_alpha")
        if self.instance and self.instance.pk and self.instance.currency_id:
            currency_qs = (currency_qs | OKVCurrency.objects.filter(pk=self.instance.currency_id)).distinct().order_by("code_alpha")
        self.fields["currency"].queryset = currency_qs
        self.fields["currency"].label_from_instance = lambda obj: f"{obj.code_alpha} {obj.name}"
        self.fields["currency"].empty_label = "---------"
        if not (self.instance and self.instance.pk):
            rub = currency_qs.filter(code_alpha="RUB").first()
            if rub:
                self.initial["currency"] = rub.pk

    def clean_base_rate_share(self):
        val = self.cleaned_data.get("base_rate_share", 0) or 0
        if val < -500 or val > 500:
            raise forms.ValidationError("Значение должно быть от -500 до +500.")
        return val

    def clean_qualification(self):
        q = self.cleaned_data.get("qualification", 0) or 0
        levels = self.cleaned_data.get("qualification_levels") or self.instance.qualification_levels if self.instance else 5
        if q < 0 or q > levels:
            raise forms.ValidationError(f"Значение должно быть от 0 до {levels}.")
        return q


class TariffForm(forms.ModelForm):
    owner = forms.ModelChoiceField(
        label="Руководитель",
        queryset=User.objects.filter(
            Q(groups__name=DEPARTMENT_HEAD_GROUP) | Q(groups__name=DIRECTOR_GROUP)
        ),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    product = forms.ModelChoiceField(
        label="Продукт",
        queryset=Product.objects.all(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    section = forms.ModelChoiceField(
        label="Раздел",
        queryset=TypicalSection.objects.select_related("product").all(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = Tariff
        fields = ["product", "section", "base_rate_vpm", "service_hours"]
        widgets = {
            "base_rate_vpm": forms.NumberInput(attrs={
                "class": "form-control", "step": "0.01", "min": "0",
                "placeholder": "1,00",
            }),
            "service_hours": forms.NumberInput(attrs={
                "class": "form-control", "min": "0", "step": "1",
                "placeholder": "0",
            }),
        }

    def __init__(self, *args, request_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request_user = request_user
        self.fields["product"].label_from_instance = lambda obj: obj.short_name
        self.fields["section"].label_from_instance = (
            lambda obj: f"{obj.product.short_name}: {obj.short_name}"
        )
        self.fields["owner"].queryset = User.objects.filter(
            Q(groups__name=DEPARTMENT_HEAD_GROUP) | Q(groups__name=DIRECTOR_GROUP)
        ).distinct().order_by("last_name", "first_name", "username")
        self.fields["owner"].label_from_instance = lambda u: (
            f"{u.last_name} {u.first_name}".strip() or u.username
        )
        if self.instance and self.instance.pk:
            self.initial["owner"] = self.instance.created_by_id