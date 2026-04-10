from django import forms

from projects_app.models import Performer


class WorktimeEditForm(forms.ModelForm):
    class Meta:
        model = Performer
        fields = ["work_hours"]
        widgets = {
            "work_hours": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "0",
                    "step": "1",
                }
            ),
        }
