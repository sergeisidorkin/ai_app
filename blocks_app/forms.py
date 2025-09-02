from django import forms
from .models import Block

class BlockForm(forms.ModelForm):
    class Meta:
        model = Block
        fields = ["code", "name", "prompt", "context"]
        widgets = {
            "prompt": forms.Textarea(attrs={"rows": 6, "class": "form-control"}),
            "context": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
        }
        labels = {
            "code": "Код блока",
            "name": "Наименование блока",
            "prompt": "Промпт",
            "context": "Контекст",
        }