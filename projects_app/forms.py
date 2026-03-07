from django import forms
from django.db.models import Max
from django.utils import timezone

from group_app.models import GroupMember
from policy_app.models import TypicalSection
from users_app.models import Employee

from .models import LegalEntity, Performer, ProjectRegistration, WorkVolume

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

PROJECT_MANAGER_ROLE = "Руководитель проектов"


def _employee_full_name(employee):
    parts = [
        employee.user.last_name.strip(),
        employee.user.first_name.strip(),
        employee.patronymic.strip(),
    ]
    return " ".join(part for part in parts if part).strip()


def _project_manager_queryset():
    return (
        Employee.objects
        .select_related("user")
        .filter(role=PROJECT_MANAGER_ROLE)
        .order_by("user__last_name", "user__first_name", "patronymic", "position", "id")
    )


def _employee_queryset():
    return (
        Employee.objects
        .select_related("user")
        .order_by("user__last_name", "user__first_name", "patronymic", "position", "id")
    )


def _employee_choices(queryset, current_value=""):
    choices = [("", "— Не выбрано —")]
    current_value = (current_value or "").strip()
    current_in_choices = False

    for employee in queryset:
        full_name = _employee_full_name(employee)
        if not full_name:
            continue
        choices.append((full_name, full_name))
        if full_name == current_value:
            current_in_choices = True

    if current_value and not current_in_choices:
        choices.insert(1, (current_value, current_value))

    return choices


def _project_manager_choices(current_value=""):
    return _employee_choices(_project_manager_queryset(), current_value)


def _all_employee_choices(current_value=""):
    return _employee_choices(_employee_queryset(), current_value)


def _next_project_number():
    current_max = ProjectRegistration.objects.aggregate(max_number=Max("number")).get("max_number")
    if current_max is None:
        return 3333
    return 9999 if current_max >= 9999 else current_max + 1

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
    group = forms.ChoiceField(
        label="Группа",
        choices=(),
        required=True,
        widget=forms.Select(attrs={"id": "registration-group-select"}),
    )
    project_manager = forms.ChoiceField(
        label="Руководитель проекта",
        required=False,
        choices=(),
        widget=forms.Select(),
    )
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
        current_group = self.data.get("group") or (self.instance.group if self.instance else "")
        current_manager = self.data.get("project_manager") or (self.instance.project_manager if self.instance else "")
        self.fields["group"].choices = self._group_choices(current_group)
        self.fields["project_manager"].choices = _project_manager_choices(current_manager)
        self._bootstrapify()
        if not self.instance.pk and "group" not in self.data:
            ru_value = next((value for value, _label in self.fields["group"].choices if value == "RU"), "")
            self.fields["group"].initial = ru_value
        if not self.instance.pk and "year" not in self.data:
            self.fields["year"].initial = timezone.now().year
        if not self.instance.pk and "number" not in self.data:
            self.fields["number"].initial = _next_project_number()

    @staticmethod
    def _group_choices(current_value=""):
        items = (
            GroupMember.objects
            .exclude(country_alpha2="")
            .values_list("country_alpha2", "short_name")
            .order_by("position", "id")
        )
        seen = set()
        choices = [("", "— Не выбрано —")]
        for alpha2, short_name in items:
            if alpha2 in seen:
                continue
            seen.add(alpha2)
            choices.append((alpha2, f"{alpha2} {short_name}"))
        if current_value and all(value != current_value for value, _label in choices):
            choices.insert(0, (current_value, current_value))
        return choices

    def clean_input_data(self):
        return self.cleaned_data.get("input_data") or 0

    def clean_stage1_weeks(self):
        return self.cleaned_data.get("stage1_weeks") or 0

    def clean_stage2_weeks(self):
        return self.cleaned_data.get("stage2_weeks") or 0

    def clean_stage3_weeks(self):
        return self.cleaned_data.get("stage3_weeks") or 0

    def clean_project_manager(self):
        return (self.cleaned_data.get("project_manager") or "").strip()

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
    manager = forms.ChoiceField(
        label="Менеджер",
        required=False,
        choices=(),
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
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_manager = self.data.get("manager") or (self.instance.manager if self.instance else "")
        self.fields["manager"].choices = _project_manager_choices(current_manager)
        if not self.data and not current_manager and getattr(self.instance, "project_id", None):
            self.fields["manager"].initial = self.instance.project.project_manager or ""

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
    executor = forms.ChoiceField(
        label="Исполнитель",
        required=False,
        choices=(),
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
            "grade": forms.TextInput(attrs={"class": "form-control"}),
            "actual_costs": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "estimated_costs": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "agreed_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "prepayment": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "final_payment": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "contract_number": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_executor = self.data.get("executor") or (self.instance.executor if self.instance else "")
        self.fields["executor"].choices = _all_employee_choices(current_executor)

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