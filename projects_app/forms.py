from django import forms
from django.db import models
from django.db.models import Max
from django.utils import timezone

from classifiers_app.models import OKSMCountry, OKVCurrency, LegalEntityIdentifier
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


class ProjectRegistrationForm(BootstrapMixin, forms.ModelForm):
    number = forms.IntegerField(
        label="Номер",
        required=True,
        min_value=3333,
        max_value=9999,
        widget=forms.NumberInput(attrs={"min": 3333, "max": 9999, "placeholder": "3333–9999"}),
    )
    deadline = forms.DateField(required=False,
                               widget=forms.TextInput(attrs=DATE_INPUT_ATTRS),
                               input_formats=DATE_INPUT_FORMATS)
    group = forms.ChoiceField(
        label="Группа",
        choices=(),
        required=True,
        widget=forms.Select(attrs={"id": "registration-group-select"}),
    )
    country = forms.ModelChoiceField(
        label="Страна",
        queryset=OKSMCountry.objects.none(),
        required=False,
        widget=forms.Select(attrs={"id": "reg-country-select"}),
    )
    identifier = forms.CharField(
        label="Идентификатор",
        required=False,
        widget=forms.TextInput(attrs={
            "readonly": True,
            "tabindex": "-1",
            "class": "form-control readonly-field",
            "id": "reg-identifier-field",
        }),
    )
    project_manager = forms.ChoiceField(
        label="Руководитель проекта",
        required=False,
        choices=(),
        widget=forms.Select(),
    )
    registration_date = forms.DateField(
        label="Дата регистр.",
        required=False,
        widget=forms.TextInput(attrs=DATE_INPUT_ATTRS),
        input_formats=DATE_INPUT_FORMATS,
    )

    class Meta:
        model = ProjectRegistration
        fields = [
            "number", "group", "agreement_type", "type", "name",
            "status", "deadline", "year",
            "country", "customer", "identifier", "registration_number",
            "registration_date", "project_manager",
        ]
        widgets = {
            "year": forms.NumberInput(attrs={"placeholder": "ГГГГ"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_group = self.data.get("group") or (self.instance.group if self.instance else "")
        current_manager = self.data.get("project_manager") or (self.instance.project_manager if self.instance else "")
        self.fields["group"].choices = _group_choices(current_group)
        self.fields["project_manager"].choices = _project_manager_choices(current_manager)

        today = timezone.now().date()
        country_qs = OKSMCountry.objects.filter(
            models.Q(expiry_date__isnull=True) | models.Q(expiry_date__gte=today)
        ).order_by("short_name")
        if self.instance and self.instance.pk and self.instance.country_id:
            country_qs = (country_qs | OKSMCountry.objects.filter(pk=self.instance.country_id)).distinct().order_by("short_name")
        self.fields["country"].queryset = country_qs
        self.fields["country"].label_from_instance = lambda obj: obj.short_name

        if self.instance and self.instance.pk and self.instance.identifier:
            self.fields["identifier"].initial = self.instance.identifier

        self._bootstrapify()
        if not self.instance.pk and "group" not in self.data:
            ru_value = next((value for value, _label in self.fields["group"].choices if value == "RU"), "")
            self.fields["group"].initial = ru_value
        if not self.instance.pk and "country" not in self.data:
            russia = country_qs.filter(short_name="Россия").first()
            if russia:
                self.fields["country"].initial = russia.pk
                lei = LegalEntityIdentifier.objects.filter(country=russia).values_list("identifier", flat=True).first()
                if lei:
                    self.fields["identifier"].initial = lei
        if not self.instance.pk and "year" not in self.data:
            self.fields["year"].initial = timezone.now().year
        if not self.instance.pk and "number" not in self.data:
            self.fields["number"].initial = _next_project_number()

    def clean_project_manager(self):
        return (self.cleaned_data.get("project_manager") or "").strip()


class ContractConditionsForm(BootstrapMixin, forms.ModelForm):
    contract_start = forms.DateField(required=False,
                                     widget=forms.TextInput(attrs=DATE_INPUT_ATTRS),
                                     input_formats=DATE_INPUT_FORMATS)
    contract_end = forms.DateField(required=False,
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
            attrs={"class": "form-control js-stage1-end readonly-field", "readonly": True}
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
            attrs={"class": "form-control js-stage2-end readonly-field", "readonly": True}
        ),
    )
    stage1_date = forms.DateField(
        label="Этап 1, дата",
        required=False,
        disabled=True,
        widget=forms.TextInput(
            attrs={"class": "form-control js-stage1-date readonly-field", "readonly": True}
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
    stage3_end = forms.DateField(
        label="Этап 3, оконч.",
        required=False,
        disabled=True,
        widget=forms.TextInput(
            attrs={"class": "form-control js-stage3-end readonly-field", "readonly": True}
        ),
    )
    term_weeks = forms.DecimalField(
        label="Срок, недель",
        required=False,
        decimal_places=1,
        max_digits=5,
        disabled=True,
        widget=forms.NumberInput(attrs={"class": "form-control js-term-weeks readonly-field", "readonly": True}),
    )

    class Meta:
        model = ProjectRegistration
        fields = [
            "agreement_type", "agreement_number",
            "contract_start", "contract_end", "completion_calc",
            "input_data", "stage1_weeks", "stage1_end",
            "stage2_weeks", "stage2_end", "stage3_weeks",
            "contract_subject",
        ]
        widgets = {
            "contract_subject": forms.Textarea(
                attrs={"rows": 6, "style": "max-height:36vh; overflow:auto; resize:vertical;"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()

    def clean_input_data(self):
        return self.cleaned_data.get("input_data") or 0

    def clean_stage1_weeks(self):
        return self.cleaned_data.get("stage1_weeks") or 0

    def clean_stage2_weeks(self):
        return self.cleaned_data.get("stage2_weeks") or 0

    def clean_stage3_weeks(self):
        return self.cleaned_data.get("stage3_weeks") or 0

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
    country = forms.ModelChoiceField(
        label="Страна",
        queryset=OKSMCountry.objects.none(),
        required=False,
        widget=forms.Select(attrs={**_common_select, "id": "work-country-select"}),
    )
    identifier = forms.CharField(
        label="Идентификатор",
        required=False,
        widget=forms.TextInput(attrs={**READONLY_INPUT, "id": "work-identifier-field"}),
    )
    registration_date = forms.DateField(
        label="Дата",
        required=False,
        widget=forms.TextInput(attrs={**_common_input, **DATE_INPUT_ATTRS, "class": _common_input["class"] + " js-date"}),
        input_formats=DATE_INPUT_FORMATS,
    )
    manager = forms.ChoiceField(
        label="Менеджер",
        required=False,
        choices=(),
        widget=forms.Select(attrs=_common_select),
    )

    class Meta:
        model = WorkVolume
        fields = [
            "project", "type", "name", "asset_name",
            "country", "identifier",
            "registration_number", "registration_date", "manager",
        ]
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

        today = timezone.now().date()
        country_qs = OKSMCountry.objects.filter(
            models.Q(expiry_date__isnull=True) | models.Q(expiry_date__gte=today)
        ).order_by("short_name")
        if self.instance and self.instance.pk and self.instance.country_id:
            country_qs = (country_qs | OKSMCountry.objects.filter(pk=self.instance.country_id)).distinct().order_by("short_name")
        self.fields["country"].queryset = country_qs
        self.fields["country"].label_from_instance = lambda obj: obj.short_name
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
    currency = forms.ModelChoiceField(
        label="Валюта",
        queryset=OKVCurrency.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    final_payment = forms.DecimalField(
        label="Окон. платеж",
        required=False,
        disabled=True,
        widget=forms.NumberInput(attrs={
            "class": "form-control readonly-field",
            "readonly": True,
            "step": "1",
        }),
    )

    class Meta:
        model = Performer
        fields = [
            "registration", "asset_name", "executor", "grade", "grade_name",
            "currency", "typical_section",
            "actual_costs", "estimated_costs", "agreed_amount",
            "prepayment", "final_payment", "contract_number",
        ]
        widgets = {
            "grade": forms.HiddenInput(),
            "grade_name": forms.HiddenInput(),
            "actual_costs": forms.TextInput(attrs={"class": "form-control js-money-input", "inputmode": "decimal"}),
            "estimated_costs": forms.HiddenInput(),
            "agreed_amount": forms.HiddenInput(),
            "prepayment": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "1",
                "min": "0",
                "max": "100",
            }),
            "contract_number": forms.TextInput(attrs={"class": "form-control"}),
        }

    _money_fields = ("actual_costs", "estimated_costs", "agreed_amount")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.data:
            data = self.data.copy()
            for fn in self._money_fields:
                v = data.get(fn, "")
                if v:
                    data[fn] = str(v).replace("\u00a0", "").replace(" ", "").replace(",", ".")
            self.data = data
        current_executor = self.data.get("executor") or (self.instance.executor if self.instance else "")
        self.fields["executor"].choices = _all_employee_choices(current_executor)

        today = timezone.now().date()
        currency_qs = OKVCurrency.objects.filter(
            models.Q(approval_date__isnull=True) | models.Q(approval_date__lte=today),
            models.Q(expiry_date__isnull=True) | models.Q(expiry_date__gte=today),
        ).order_by("code_alpha")
        if self.instance and self.instance.pk and self.instance.currency_id:
            currency_qs = (currency_qs | OKVCurrency.objects.filter(pk=self.instance.currency_id)).distinct().order_by("code_alpha")
        self.fields["currency"].queryset = currency_qs
        self.fields["currency"].label_from_instance = lambda obj: f"{obj.code_alpha} {obj.name}"
        if not (self.instance and self.instance.pk):
            rub = currency_qs.filter(code_alpha="RUB").first()
            if rub:
                self.initial["currency"] = rub.pk
            self.initial["prepayment"] = 50
            self.initial["final_payment"] = 50
        else:
            for fn in ("prepayment", "final_payment"):
                v = self.initial.get(fn)
                if v is not None:
                    self.initial[fn] = int(v)

    @staticmethod
    def _clean_money(value):
        if not value:
            return value
        return str(value).replace("\u00a0", "").replace(" ", "").replace(",", ".")

    def clean_actual_costs(self):
        return self._clean_money(self.cleaned_data.get("actual_costs"))

    def clean_estimated_costs(self):
        return self._clean_money(self.cleaned_data.get("estimated_costs"))

    def clean_agreed_amount(self):
        return self._clean_money(self.cleaned_data.get("agreed_amount"))

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
    country = forms.ModelChoiceField(
        label="Страна регистрации",
        queryset=OKSMCountry.objects.none(),
        required=False,
        widget=forms.Select(attrs={**_common_select, "id": "legal-country-select"}),
    )
    identifier = forms.CharField(
        label="Идентификатор",
        required=False,
        widget=forms.TextInput(attrs={**READONLY_INPUT, "id": "legal-identifier-field"}),
    )
    registration_date = forms.DateField(
        label="Дата регистрации",
        required=False,
        widget=forms.TextInput(attrs={**_common_input, **DATE_INPUT_ATTRS, "class": _common_input["class"] + " js-date"}),
        input_formats=DATE_INPUT_FORMATS,
    )

    class Meta:
        model = LegalEntity
        fields = [
            "work_item", "work_type", "work_name", "legal_name",
            "country", "identifier",
            "registration_number", "registration_date",
        ]
        widgets = {
            "work_type": forms.TextInput(attrs=READONLY_INPUT),
            "work_name": forms.TextInput(attrs=READONLY_INPUT),
            "legal_name": forms.TextInput(attrs=_common_input),
            "registration_number": forms.TextInput(attrs=_common_input),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        today = timezone.now().date()
        country_qs = OKSMCountry.objects.filter(
            models.Q(expiry_date__isnull=True) | models.Q(expiry_date__gte=today)
        ).order_by("short_name")
        if self.instance and self.instance.pk and self.instance.country_id:
            country_qs = (country_qs | OKSMCountry.objects.filter(pk=self.instance.country_id)).distinct().order_by("short_name")
        self.fields["country"].queryset = country_qs
        self.fields["country"].label_from_instance = lambda obj: obj.short_name

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.work_item_id:
            instance.project = instance.work_item.project
            instance.work_type = instance.work_item.type or ""
            instance.work_name = instance.work_item.name or ""
        if commit:
            instance.save()
        return instance        