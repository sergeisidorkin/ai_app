from django import forms
from .models import Block

class BlockForm(forms.ModelForm):
    def __init__(self, *args, model_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Если передали список моделей — сделаем выпадающий список (с пустым значением)
        if model_choices is not None:
            self.fields["model"] = forms.ChoiceField(
                choices=[("", "— Не выбрано —"), *model_choices],
                required=False,
                label="Модель",
                widget=forms.Select(attrs={"class": "form-select"})
            )

    class Meta:
        model = Block
        fields = ["code", "name", "prompt", "context", "model", "temperature"]
        widgets = {
            "prompt": forms.Textarea(attrs={"rows": 6, "class": "form-control"}),
            "context": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "temperature": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.1",
                "min": "0",
                "max": "2",
                "placeholder": "Необязательно (по умолчанию модели)",
            }),
        }
        labels = {
            "code": "Код блока",
            "name": "Наименование блока",
            "prompt": "Промпт",
            "context": "Контекст",
            "model": "Модель",
            "temperature": "Температура",
        }