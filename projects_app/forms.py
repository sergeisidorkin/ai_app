from django import forms
from .models import ProjectRegistration, WorkVolume, LegalEntity
from django import forms
from .models import Performer
from policy_app.models import TypicalSection
from django.utils import timezone

_common_input = {"class": "form-control form-control-sm"}
_common_select = {"class": "form-select form-select-sm"}
_common_date = {"class": "form-control form-control-sm", "type": "date"}

# Форматы для дат
DATE_FMT_UI = "%d.%m.%y"  # ДД.ММ.ГГ

READONLY_INPUT = {
    **_common_input,
    "class": _common_input["class"] + " readonly-field",
    "readonly": True,
    "tabindex": "-1",
}

# ------ Миксин для bootstrap-классов ------
class BootstrapMixin:
    def _bootstrapify(self):
        for name, field in self.fields.items():
            w = field.widget
            # Select / MultiSelect -> form-select, остальное -> form-control
            if isinstance(w, (forms.Select, forms.SelectMultiple)):
                need = "form-select"
            else:
                need = "form-control"
            # бережно добавляем класс, не перетирая существующие (например js-date)
            existing = w.attrs.get("class", "")
            classes = set(filter(None, existing.split()))
            classes.add(need)
            w.attrs["class"] = " ".join(classes)

# ------ Форма регистрации ------
DATE_INPUT_ATTRS = {"class": "js-date", "autocomplete": "off"}  # класс-хук для JS пикера
DATE_INPUT_FORMATS = ["%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"]

class ProjectRegistrationForm(BootstrapMixin, forms.ModelForm):
    number = forms.IntegerField(
        label="Номер",
        required=True,
        min_value=3333,
        max_value=9999,
        widget=forms.NumberInput(attrs={"min": 3333, "max": 9999, "placeholder": "3333–9999"}), 
    )

    # даты: текстовый инпут + js-date, чтобы инициализировался календарь
    contract_start = forms.DateField(required=False,
                                     widget=forms.TextInput(attrs=DATE_INPUT_ATTRS),
                                     input_formats=DATE_INPUT_FORMATS)
    contract_end   = forms.DateField(required=False,
                                     widget=forms.TextInput(attrs=DATE_INPUT_ATTRS),
                                     input_formats=DATE_INPUT_FORMATS)
    input_data = forms.IntegerField(
        label="Исх. данные, дней",
        required=False,
        min_value=0,
        initial=0,
        widget=forms.NumberInput(attrs={"min": 0, "step": 1, "class": "form-control js-input-data"}),
    )
    stage1_weeks = forms.DecimalField(
        label="Этап 1, недель",
        required=False,
        min_value=0,
        max_digits=4,
        decimal_places=1,
        widget=forms.NumberInput(attrs={"min": 0, "step": "0.1", "class": "form-control js-stage1-weeks"}),
    )
    stage1_end = forms.DateField(
        label="Этап 1, оконч.",
        required=False,
        disabled=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control js-stage1-end readonly-field",
                "readonly": True,
            }
        ),
    )
    completion_calc = forms.DateField(
        label="Оконч., расчет",
        required=False,
        disabled=True,
        widget=forms.TextInput(attrs={"class": "form-control js-completion-calc readonly-field", "readonly": True}),
    )
    stage2_weeks = forms.DecimalField(
        label="Этап 2, недель",
        required=False,
        min_value=0,
        max_digits=4,
        decimal_places=1,
        widget=forms.NumberInput(attrs={"min": 0, "step": "0.1", "class": "form-control js-stage2-weeks"}),
    )
    stage2_end = forms.DateField(
        label="Этап 2, оконч.",
        required=False,
        disabled=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control js-stage2-end readonly-field",
                "readonly": True,
            }
        ),
    )
    stage3_weeks = forms.DecimalField(
        label="Этап 3, недель",
        required=False,
        min_value=0,
        max_digits=4,
        decimal_places=1,
        widget=forms.NumberInput(attrs={"min": 0, "step": "0.1", "class": "form-control js-stage3-weeks"}),
    )
    term_weeks = forms.DecimalField(
        label="Срок, недель",
        required=False,
        decimal_places=1,
        max_digits=5,
        disabled=True,
        widget=forms.NumberInput(attrs={"class": "form-control js-term-weeks readonly-field", "readonly": True}),
    )
    stage3_end     = forms.DateField(required=False,
                                     widget=forms.TextInput(attrs=DATE_INPUT_ATTRS),
                                     input_formats=DATE_INPUT_FORMATS)
    deadline       = forms.DateField(required=False,
                                     widget=forms.TextInput(attrs=DATE_INPUT_ATTRS),
                                     input_formats=DATE_INPUT_FORMATS)
    class Meta:
        model = ProjectRegistration
        exclude = ("position",)
        widgets = {
            "year": forms.NumberInput(attrs={"placeholder": "ГГГГ"}),
            "contract_subject": forms.Textarea(
                attrs={"rows": 6, "style": "max-height:36vh; overflow:auto; resize:vertical;"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()
        if not self.instance.pk and "group" not in self.data:
            from .models import ProjectRegistration as PR
            self.fields["group"].initial = PR.Group.RU
        if not self.instance.pk and "year" not in self.data:
            self.fields["year"].initial = timezone.now().year       

class ProjectChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        type_label = getattr(obj.type, "short_name", obj.type) if obj.type_id else ""
        name_label = obj.name or ""
        parts = [obj.short_uid]
        if type_label:
            parts.append(str(type_label))
        if name_label:
            parts.append(name_label)
        return " ".join(parts)

class WorkVolumeForm(forms.ModelForm):
    project = ProjectChoiceField(
        queryset=ProjectRegistration.objects.order_by("-id"),
        label="Проект",
        widget=forms.Select(attrs=_common_select),
    )

    class Meta:
        model = WorkVolume
        fields = ["project", "type", "name", "asset_name", "registration_number", "manager"]
        widgets = {
            "type": forms.TextInput(attrs=READONLY_INPUT),
            "name": forms.TextInput(attrs=READONLY_INPUT),
            "asset_name": forms.TextInput(attrs=_common_input),
            "registration_number": forms.TextInput(attrs=_common_input),
            "manager": forms.TextInput(attrs=_common_input),
        }

class PerformerForm(forms.ModelForm):
    registration = ProjectChoiceField(
        queryset=ProjectRegistration.objects.order_by("-id"),
        label="Проект",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    # Актив — как выпадающий, опции наполним в шаблоне/JS
    asset_name = forms.ChoiceField(
        choices=[("", "— Не выбрано —")],
        required=False,
        label="Актив",
        widget=forms.Select(attrs={"class": "form-select"})
    )

    # Типовой раздел — тоже выпадающий, заполним по типу продукта выбранной регистрации
    typical_section = forms.ModelChoiceField(
        queryset=TypicalSection.objects.none(),
        required=False,
        label="Типовой раздел",
        widget=forms.Select(attrs={"class": "form-select"})
    )

    class Meta:
        model = Performer
        fields = [
            "registration", "asset_name", "executor", "grade", "typical_section",
            "actual_costs", "estimated_costs", "agreed_amount",
            "prepayment", "final_payment", "contract_number",
        ]
        widgets = {
            "executor": forms.TextInput(attrs={"class": "form-control"}),
            "grade": forms.TextInput(attrs={"class": "form-control"}),
            "actual_costs": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "estimated_costs": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "agreed_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "prepayment": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "final_payment": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "contract_number": forms.TextInput(attrs={"class": "form-control"}),
        }

class WorkItemChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        project = getattr(obj.project, "short_uid", "")
        type_label = obj.type or ""
        name_label = obj.name or ""
        asset_label = obj.asset_name or name_label or ""
        header_parts = [part for part in (project, type_label, name_label) if part]
        header = " ".join(header_parts)
        if header and asset_label:
            return f"{header} — {asset_label}"
        return header or asset_label or f"Актив #{obj.pk}"


class LegalEntityForm(forms.ModelForm):
    work_item = WorkItemChoiceField(
        queryset=WorkVolume.objects.select_related("project").order_by("-id"),
        label="Наименование актива",
        widget=forms.Select(attrs=_common_select),
    )

    class Meta:
        model = LegalEntity
        fields = ["work_item", "work_type", "work_name", "legal_name", "registration_number"]
        widgets = {
            "work_type": forms.TextInput(attrs=READONLY_INPUT),
            "work_name": forms.TextInput(attrs=READONLY_INPUT),
            "legal_name": forms.TextInput(attrs=_common_input),
            "registration_number": forms.TextInput(attrs=_common_input),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.work_item_id:
            instance.project = instance.work_item.project
            instance.work_type = instance.work_item.type or ""
            instance.work_name = instance.work_item.name or ""
        if commit:
            instance.save()
        return instance        