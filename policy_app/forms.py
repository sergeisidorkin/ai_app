from django import forms
from django.contrib.auth.models import User

from .models import Product, TypicalSection, SectionStructure, Grade, DEPARTMENT_HEAD_GROUP

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["short_name", "name_en", "name_ru", "service_type"]
        widgets = {
            "short_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Краткое имя"}),
            "name_en": forms.TextInput(attrs={"class": "form-control", "placeholder": "English name"}),
            "name_ru": forms.TextInput(attrs={"class": "form-control", "placeholder": "Русское наименование"}),
            "service_type": forms.TextInput(attrs={"class": "form-control", "placeholder": "Тип услуги"}),
        }

class TypicalSectionForm(forms.ModelForm):
    product = forms.ModelChoiceField(
        label="Продукт",
        queryset=Product.objects.all(),
        widget=forms.Select(attrs={"class": "form-select"})
    )

    class Meta:
        model = TypicalSection
        fields = ["product", "code", "short_name", "name_en", "name_ru", "accounting_type", "executor"]
        widgets = {
            "code": forms.TextInput(attrs={"class": "form-control", "placeholder": "Код"}),
            "short_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Краткое имя"}),
            "name_en": forms.TextInput(attrs={"class": "form-control", "placeholder": "English section name"}),
            "name_ru": forms.TextInput(attrs={"class": "form-control", "placeholder": "Русское наименование раздела"}),
            "accounting_type": forms.TextInput(attrs={"class": "form-control", "placeholder": "Тип учета"}),
            "executor": forms.TextInput(attrs={"class": "form-control", "placeholder": "Исполнитель"}),
        }


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


class GradeForm(forms.ModelForm):
    owner = forms.ModelChoiceField(
        label="Руководитель направления",
        queryset=User.objects.filter(groups__name=DEPARTMENT_HEAD_GROUP),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = Grade
        fields = [
            "grade_en", "grade_ru", "qualification_levels",
            "qualification", "is_base_rate", "base_rate_share",
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
        }

    def __init__(self, *args, request_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request_user = request_user
        self.fields["base_rate_share"].required = False
        self.fields["owner"].queryset = User.objects.filter(
            groups__name=DEPARTMENT_HEAD_GROUP
        ).distinct()
        self.fields["owner"].label_from_instance = lambda u: (
            f"{u.last_name} {u.first_name}".strip() or u.username
        )
        if self.instance and self.instance.pk:
            self.initial["owner"] = self.instance.created_by_id

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