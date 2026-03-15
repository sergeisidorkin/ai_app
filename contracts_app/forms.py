from django import forms
from projects_app.models import Performer


class ContractEditForm(forms.ModelForm):
    class Meta:
        model = Performer
        fields = [
            "contract_number",
            "contract_file",
        ]
        widgets = {
            "contract_number": forms.TextInput(attrs={"class": "form-control"}),
            "contract_file": forms.TextInput(attrs={"class": "form-control"}),
        }
