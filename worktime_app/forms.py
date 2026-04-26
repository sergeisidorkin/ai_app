from django import forms

from projects_app.models import ProjectRegistration
from proposals_app.models import ProposalRegistration
from .models import WorktimeAssignment


class WorktimeRegistrationChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        type_label = ""
        if getattr(obj, "type", None):
            type_label = getattr(obj.type, "short_name", "") or str(obj.type)
        parts = [obj.short_uid or "", type_label, obj.name or ""]
        return " ".join(part for part in parts if part).strip() or str(obj)


class WorktimeProposalChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        type_label = ""
        if getattr(obj, "type", None):
            type_label = getattr(obj.type, "short_name", "") or str(obj.type)
        parts = [obj.short_uid or "", type_label, obj.name or ""]
        return " ".join(part for part in parts if part).strip() or str(obj)


class PersonalWorktimeWeekAssignmentForm(forms.Form):
    record_type = forms.ChoiceField(
        choices=WorktimeAssignment.RecordType.choices,
        label="Вид записи",
        initial=WorktimeAssignment.RecordType.PROJECT,
        widget=forms.Select(attrs={"class": "form-select", "data-worktime-record-type-select": "true"}),
    )
    registration = WorktimeRegistrationChoiceField(
        queryset=ProjectRegistration.objects.none(),
        label="Учет часов работы",
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    proposal_registration = WorktimeProposalChoiceField(
        queryset=ProposalRegistration.objects.none(),
        label="Учет часов работы",
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    week = forms.DateField(widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        registration_queryset = kwargs.pop("registration_queryset", ProjectRegistration.objects.none())
        proposal_queryset = kwargs.pop("proposal_queryset", ProposalRegistration.objects.none())
        super().__init__(*args, **kwargs)
        self.fields["record_type"].choices = [
            choice
            for choice in WorktimeAssignment.RecordType.choices
            if choice[0] != WorktimeAssignment.RecordType.DOWNTIME
        ]
        self.fields["registration"].queryset = registration_queryset
        self.fields["proposal_registration"].queryset = proposal_queryset

    def clean(self):
        cleaned_data = super().clean()
        record_type = cleaned_data.get("record_type")
        registration = cleaned_data.get("registration")
        proposal_registration = cleaned_data.get("proposal_registration")

        if record_type == WorktimeAssignment.RecordType.PROJECT:
            if registration is None:
                self.add_error("registration", "Выберите проект для учета часов работы.")
            cleaned_data["proposal_registration"] = None
        elif record_type == WorktimeAssignment.RecordType.TKP:
            if proposal_registration is None:
                self.add_error("proposal_registration", "Выберите ТКП для учета часов работы.")
            cleaned_data["registration"] = None
        else:
            cleaned_data["registration"] = None
            cleaned_data["proposal_registration"] = None

        return cleaned_data
