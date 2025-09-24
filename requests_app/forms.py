from django import forms
from .models import RequestItem

class RequestForm(forms.ModelForm):
    class Meta:
        model = RequestItem
        fields = ["code", "number", "short_name", "name"]
        widgets = {
            "code": forms.TextInput(attrs={"class": "form-control"}),
            "number": forms.NumberInput(attrs={"class": "form-control"}),
            "short_name": forms.TextInput(attrs={"class": "form-control"}),
            "name": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }
