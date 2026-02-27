from django import forms
from .models import Product, TypicalSection, SectionStructure

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