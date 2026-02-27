from django import forms
from .models import OKSMCountry


class OKSMCountryForm(forms.ModelForm):
    class Meta:
        model = OKSMCountry
        fields = ["number", "code", "short_name", "full_name", "alpha2", "alpha3"]
        widgets = {
            "number": forms.NumberInput(attrs={"class": "form-control", "placeholder": "Порядковый номер"}),
            "code": forms.TextInput(attrs={"class": "form-control", "placeholder": "000", "maxlength": "3"}),
            "short_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Краткое наименование страны"}),
            "full_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Полное наименование страны"}),
            "alpha2": forms.TextInput(attrs={"class": "form-control", "placeholder": "AA", "maxlength": "2", "style": "text-transform:uppercase"}),
            "alpha3": forms.TextInput(attrs={"class": "form-control", "placeholder": "AAA", "maxlength": "3", "style": "text-transform:uppercase"}),
        }

    def clean_alpha2(self):
        return (self.cleaned_data.get("alpha2") or "").upper()

    def clean_alpha3(self):
        return (self.cleaned_data.get("alpha3") or "").upper()

    def clean_code(self):
        val = self.cleaned_data.get("code") or ""
        if not val.isdigit() or len(val) != 3:
            raise forms.ValidationError("Код должен состоять из трёх цифр.")
        return val
