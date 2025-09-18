from django import forms
from .models import ProjectRegistration, WorkVolume

_common_input = {"class": "form-control form-control-sm"}
_common_select = {"class": "form-select form-select-sm"}
_common_date = {"class": "form-control form-control-sm", "type": "date"}

class ProjectRegistrationForm(forms.ModelForm):
    class Meta:
        model = ProjectRegistration
        fields = [
            "number", "type", "name", "status",
            "contract_start", "contract_end", "completion_calc",
            "input_data",
            "stage1_weeks", "stage1_end",
            "stage2_weeks", "stage2_end",
            "stage3_weeks",
            "term_weeks",
            "deadline", "year", "customer", "registration_number",
            "project_manager", "deadline_format", "contract_subject",
        ]
        widgets = {
            "number": forms.TextInput(attrs=_common_input),
            "type": forms.TextInput(attrs=_common_input),
            "name": forms.TextInput(attrs=_common_input),
            "status": forms.TextInput(attrs=_common_input),
            "contract_start": forms.DateInput(attrs=_common_date),
            "contract_end": forms.DateInput(attrs=_common_date),
            "completion_calc": forms.DateInput(attrs=_common_date),
            "input_data": forms.TextInput(attrs=_common_input),
            "stage1_weeks": forms.NumberInput(attrs=_common_input),
            "stage1_end": forms.DateInput(attrs=_common_date),
            "stage2_weeks": forms.NumberInput(attrs=_common_input),
            "stage2_end": forms.DateInput(attrs=_common_date),
            "stage3_weeks": forms.NumberInput(attrs=_common_input),
            "term_weeks": forms.NumberInput(attrs=_common_input),
            "deadline": forms.DateInput(attrs=_common_date),
            "year": forms.NumberInput(attrs=_common_input),
            "customer": forms.TextInput(attrs=_common_input),
            "registration_number": forms.TextInput(attrs=_common_input),
            "project_manager": forms.TextInput(attrs=_common_input),
            "deadline_format": forms.TextInput(attrs=_common_input),
            "contract_subject": forms.Textarea(attrs={**_common_input, "rows": 3}),
        }


class WorkVolumeForm(forms.ModelForm):
    class Meta:
        model = WorkVolume
        fields = ["project", "type", "name", "asset_name", "registration_number", "manager"]
        widgets = {
            "project": forms.Select(attrs=_common_select),
            "type": forms.TextInput(attrs=_common_input),
            "name": forms.TextInput(attrs=_common_input),
            "asset_name": forms.TextInput(attrs=_common_input),
            "registration_number": forms.TextInput(attrs=_common_input),
            "manager": forms.TextInput(attrs=_common_input),
        }