from django import forms
from .models import Product, TypicalSection

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