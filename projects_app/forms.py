from django import forms
from .models import ProjectRegistration, WorkVolume
from django import forms
from .models import Performer
from policy_app.models import TypicalSection

_common_input = {"class": "form-control form-control-sm"}
_common_select = {"class": "form-select form-select-sm"}
_common_date = {"class": "form-control form-control-sm", "type": "date"}

# Форматы для дат
DATE_FMT_UI = "%d.%m.%y"  # ДД.ММ.ГГ

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
    completion_calc= forms.DateField(required=False,
                                     widget=forms.TextInput(attrs=DATE_INPUT_ATTRS),
                                     input_formats=DATE_INPUT_FORMATS)
    stage1_end     = forms.DateField(required=False,
                                     widget=forms.TextInput(attrs=DATE_INPUT_ATTRS),
                                     input_formats=DATE_INPUT_FORMATS)
    stage2_end     = forms.DateField(required=False,
                                     widget=forms.TextInput(attrs=DATE_INPUT_ATTRS),
                                     input_formats=DATE_INPUT_FORMATS)
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
        self._bootstrapify()  # <- унифицируем классы
        if not self.instance.pk and "group" not in self.data:
            from .models import ProjectRegistration as PR
            self.fields["group"].initial = PR.Group.RU

class ProjectChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        # без пробела между номером и группой
        return f"{getattr(obj, 'number', '')}{getattr(obj, 'group', '')}"

class WorkVolumeForm(forms.ModelForm):
    project = ProjectChoiceField(
        queryset=ProjectRegistration.objects.order_by("position", "id"),
        label="Номер проекта",
        widget=forms.Select(attrs=_common_select),
    )

    class Meta:
        model = WorkVolume
        fields = ["project", "type", "name", "asset_name", "registration_number", "manager"]
        widgets = {
            "type": forms.TextInput(attrs=_common_input),
            "name": forms.TextInput(attrs=_common_input),
            "asset_name": forms.TextInput(attrs=_common_input),
            "registration_number": forms.TextInput(attrs=_common_input),
            "manager": forms.TextInput(attrs=_common_input),
        }

class PerformerForm(forms.ModelForm):
    # «Номер» — выбираем регистрацию, метка "Номер Группа"
    registration = forms.ModelChoiceField(
        queryset=ProjectRegistration.objects.order_by("position", "id"),
        label="Номер",
        widget=forms.Select(attrs={"class": "form-select"})
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