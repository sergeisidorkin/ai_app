from django import forms
from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone
import json

from classifiers_app.models import OKVCurrency
from experts_app.models import ExpertSpecialty
from group_app.models import OrgUnit
from group_app.models import GroupMember
from .models import (
    ConsultingDirection,
    ConsultingDirectionType,
    ConsultingServiceSubtype,
    ConsultingServiceType,
    Product,
    TypicalSection,
    SectionStructure,
    ServiceGoalReport,
    TypicalServiceComposition,
    TypicalServiceTerm,
    ExpertiseDirection,
    Grade,
    SpecialtyTariff,
    Tariff,
    DEPARTMENT_HEAD_GROUP,
    DIRECTOR_GROUP,
)

OWNER_GROUP_VALUE = "__group__"


def _coerce_positive_int(value):
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


class CommaDecimalField(forms.DecimalField):
    def to_python(self, value):
        if isinstance(value, str):
            value = value.replace("\u00a0", "").replace(" ", "").replace(",", ".")
        return super().to_python(value)

    def prepare_value(self, value):
        prepared = super().prepare_value(value)
        if prepared in self.empty_values:
            return prepared
        if isinstance(prepared, str):
            return prepared.replace(".", ",")
        return str(prepared).replace(".", ",")


class ProductForm(forms.ModelForm):
    consulting_type_ref = forms.ModelChoiceField(
        label="Вид консалтинга",
        queryset=ConsultingDirectionType.objects.none(),
        widget=forms.Select(attrs={"class": "form-select", "id": "id_consulting_type"}),
    )
    service_category_ref = forms.ModelChoiceField(
        label="Тип услуг",
        queryset=ConsultingServiceType.objects.none(),
        widget=forms.Select(attrs={"class": "form-select", "id": "id_service_category"}),
    )
    service_subtype_ref = forms.ModelChoiceField(
        label="Подтип услуги",
        queryset=ConsultingServiceSubtype.objects.none(),
        widget=forms.Select(attrs={"class": "form-select", "id": "id_service_subtype"}),
    )

    class Meta:
        model = Product
        fields = [
            "short_name",
            "name_en",
            "display_name",
            "name_ru",
            "consulting_type_ref",
            "service_category_ref",
            "service_subtype_ref",
        ]
        widgets = {
            "short_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Краткое имя"}),
            "name_en": forms.TextInput(attrs={"class": "form-control", "placeholder": "English name"}),
            "display_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Отображаемое в системе имя"}),
            "name_ru": forms.TextInput(attrs={"class": "form-control", "placeholder": "Русское наименование"}),
        }
        error_messages = {
            "short_name": {
                "unique": "Продукт с таким кратким именем уже существует.",
            },
        }

    def __init__(self, *args, request_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["consulting_type_ref"].required = True
        self.fields["service_category_ref"].required = True
        self.fields["service_subtype_ref"].required = True
        self.owner_options = list(GroupMember.objects.order_by("position", "id").values("pk", "short_name"))
        self.selected_owner_ids = []
        self.is_group_selected = False
        if self.is_bound:
            owner_values = self.data.getlist("owner_ids")
            if OWNER_GROUP_VALUE in owner_values:
                self.is_group_selected = True
            else:
                self.selected_owner_ids = [int(v) for v in owner_values if v != OWNER_GROUP_VALUE and v.isdigit()]
        elif self.instance and self.instance.pk:
            if self.instance.is_group_owner:
                self.is_group_selected = True
            else:
                self.selected_owner_ids = list(
                    self.instance.owners.values_list("pk", flat=True)
                )

        consulting_type = None
        category = None
        if self.data:
            consulting_type = _coerce_positive_int(self.data.get("consulting_type_ref"))
            category = _coerce_positive_int(self.data.get("service_category_ref"))
        elif self.instance.pk:
            consulting_type = self.instance.consulting_type_ref_id or None
            category = self.instance.service_category_ref_id or None
        self.fields["consulting_type_ref"].queryset = ConsultingDirectionType.objects.order_by("position", "id")
        category_qs = ConsultingServiceType.objects.select_related("consulting_type").order_by("consulting_type__position", "position", "id")
        if consulting_type:
            category_qs = category_qs.filter(consulting_type_id=consulting_type)
        else:
            category_qs = category_qs.none()
        self.fields["service_category_ref"].queryset = category_qs
        subtype_qs = ConsultingServiceSubtype.objects.select_related("service_type", "service_type__consulting_type").order_by(
            "service_type__consulting_type__position", "service_type__position", "position", "id"
        )
        if category:
            subtype_qs = subtype_qs.filter(service_type_id=category)
        else:
            subtype_qs = subtype_qs.none()
        self.fields["service_subtype_ref"].queryset = subtype_qs

    def clean(self):
        cleaned_data = super().clean()
        consulting_type = cleaned_data.get("consulting_type_ref")
        service_category = cleaned_data.get("service_category_ref")
        service_subtype = cleaned_data.get("service_subtype_ref")
        if not consulting_type:
            self.add_error("consulting_type_ref", "Обязательное поле.")
        if not service_category:
            self.add_error("service_category_ref", "Обязательное поле.")
        if not service_subtype:
            self.add_error("service_subtype_ref", "Обязательное поле.")
        if consulting_type and service_category and service_category.consulting_type_id != consulting_type.pk:
            self.add_error("service_category_ref", "Выберите значение из списка для выбранного вида консалтинга.")
        if service_category and service_subtype and service_subtype.service_type_id != service_category.pk:
            self.add_error("service_subtype_ref", "Выберите значение из списка для выбранного типа услуг.")
        return cleaned_data

    def save(self, commit=True):
        obj = super().save(commit=False)
        owner_values = self.data.getlist("owner_ids")
        if OWNER_GROUP_VALUE in owner_values:
            obj.is_group_owner = True
        else:
            obj.is_group_owner = False
        if commit:
            obj.save()
            if obj.is_group_owner:
                obj.owners.clear()
            else:
                member_ids = [int(v) for v in owner_values if v != OWNER_GROUP_VALUE and v.isdigit()]
                obj.owners.set(member_ids)
        return obj


class ConsultingDirectionForm(forms.ModelForm):
    consulting_types_payload = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"id": "id_consulting_types_payload"}),
    )
    service_types_payload = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"id": "id_service_types_payload"}),
    )
    service_subtypes_payload = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"id": "id_service_subtypes_payload"}),
    )

    class Meta:
        model = ConsultingDirection
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial_catalog = {
            "consulting_types": [],
            "service_types": [],
            "service_subtypes": [],
        }
        if self.is_bound:
            for payload_key, state_key in (
                ("consulting_types_payload", "consulting_types"),
                ("service_types_payload", "service_types"),
                ("service_subtypes_payload", "service_subtypes"),
            ):
                raw = (self.data.get(payload_key) or "").strip()
                if not raw:
                    continue
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, list):
                    self.initial_catalog[state_key] = parsed
        elif self.instance and self.instance.pk:
            self.initial_catalog = {
                "consulting_types": [
                    {"id": item.pk, "name": item.name}
                    for item in self.instance.consulting_types.order_by("position", "id")
                ],
                "service_types": [
                    {
                        "id": item.pk,
                        "consulting_type": item.consulting_type.name,
                        "name": item.name,
                        "code": item.code,
                    }
                    for item in self.instance.service_types.select_related("consulting_type").order_by("position", "id")
                ],
                "service_subtypes": [
                    {
                        "id": item.pk,
                        "consulting_type": item.service_type.consulting_type.name,
                        "service_type": item.service_type.name,
                        "code": item.service_type.code,
                        "name": item.name,
                    }
                    for item in self.instance.service_subtypes.select_related(
                        "service_type", "service_type__consulting_type"
                    ).order_by("position", "id")
                ],
            }
        self.cleaned_consulting_types = []
        self.cleaned_service_types = []
        self.cleaned_service_subtypes = []

    def _parse_payload(self, field_name):
        raw = (self.cleaned_data.get(field_name) or "").strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            raise forms.ValidationError("Не удалось разобрать данные формы.")
        if not isinstance(parsed, list):
            raise forms.ValidationError("Ожидался список значений.")
        return parsed

    def clean(self):
        cleaned_data = super().clean()
        consulting_types = self._parse_payload("consulting_types_payload")
        service_types = self._parse_payload("service_types_payload")
        service_subtypes = self._parse_payload("service_subtypes_payload")

        normalized_types = []
        type_names = set()
        for index, item in enumerate(consulting_types, start=1):
            if not isinstance(item, dict):
                raise forms.ValidationError("Строка вида консалтинга заполнена некорректно.")
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            if name in type_names:
                raise forms.ValidationError(f"Вид консалтинга «{name}» указан несколько раз.")
            type_names.add(name)
            normalized_types.append({"id": item.get("id") or "", "name": name, "position": index})
        if not normalized_types:
            raise forms.ValidationError("Добавьте хотя бы один вид консалтинга.")

        normalized_service_types = []
        service_type_keys = set()
        for index, item in enumerate(service_types, start=1):
            if not isinstance(item, dict):
                raise forms.ValidationError("Строка типа услуг заполнена некорректно.")
            consulting_type = str(item.get("consulting_type") or "").strip()
            name = str(item.get("name") or "").strip()
            code = str(item.get("code") or "").strip()
            if not consulting_type and not name and not code:
                continue
            if not consulting_type or consulting_type not in type_names:
                raise forms.ValidationError("Для каждого типа услуг выберите существующий вид консалтинга.")
            if not name:
                raise forms.ValidationError("Для каждого типа услуг заполните наименование.")
            if not code:
                raise forms.ValidationError("Для каждого типа услуг заполните код.")
            key = (consulting_type, name)
            if key in service_type_keys:
                raise forms.ValidationError(f"Тип услуг «{name}» для вида «{consulting_type}» указан несколько раз.")
            service_type_keys.add(key)
            normalized_service_types.append(
                {
                    "id": item.get("id") or "",
                    "consulting_type": consulting_type,
                    "name": name,
                    "code": code,
                    "position": index,
                }
            )

        normalized_service_subtypes = []
        subtype_keys = set()
        for index, item in enumerate(service_subtypes, start=1):
            if not isinstance(item, dict):
                raise forms.ValidationError("Строка подтипа услуги заполнена некорректно.")
            consulting_type = str(item.get("consulting_type") or "").strip()
            service_type = str(item.get("service_type") or "").strip()
            name = str(item.get("name") or "").strip()
            if not consulting_type and not service_type and not name:
                continue
            if (consulting_type, service_type) not in service_type_keys:
                raise forms.ValidationError("Для каждого подтипа выберите существующий тип услуг.")
            if not name:
                raise forms.ValidationError("Для каждого подтипа услуги заполните наименование.")
            key = (consulting_type, service_type, name)
            if key in subtype_keys:
                raise forms.ValidationError(
                    f"Подтип услуги «{name}» для типа «{service_type}» указан несколько раз."
                )
            subtype_keys.add(key)
            normalized_service_subtypes.append(
                {
                    "id": item.get("id") or "",
                    "consulting_type": consulting_type,
                    "service_type": service_type,
                    "name": name,
                    "position": index,
                }
            )

        self.cleaned_consulting_types = normalized_types
        self.cleaned_service_types = normalized_service_types
        self.cleaned_service_subtypes = normalized_service_subtypes
        return cleaned_data

    def save(self, commit=True):
        direction = super().save(commit=commit)
        existing_types = {str(item.pk): item for item in direction.consulting_types.all()}
        existing_service_types = {str(item.pk): item for item in direction.service_types.all()}
        existing_subtypes = {str(item.pk): item for item in direction.service_subtypes.all()}

        type_by_name = {}
        kept_type_ids = []
        for item in self.cleaned_consulting_types:
            obj = existing_types.get(str(item["id"])) if item.get("id") else None
            if obj is None:
                obj = ConsultingDirectionType(direction=direction)
            obj.direction = direction
            obj.name = item["name"]
            obj.position = item["position"]
            obj.save()
            kept_type_ids.append(obj.pk)
            type_by_name[obj.name] = obj

        service_type_by_key = {}
        kept_service_type_ids = []
        for item in self.cleaned_service_types:
            obj = existing_service_types.get(str(item["id"])) if item.get("id") else None
            if obj is None:
                obj = ConsultingServiceType(direction=direction)
            obj.direction = direction
            obj.consulting_type = type_by_name[item["consulting_type"]]
            obj.name = item["name"]
            obj.code = item["code"]
            obj.position = item["position"]
            obj.save()
            kept_service_type_ids.append(obj.pk)
            service_type_by_key[(obj.consulting_type.name, obj.name)] = obj

        kept_subtype_ids = []
        for item in self.cleaned_service_subtypes:
            obj = existing_subtypes.get(str(item["id"])) if item.get("id") else None
            if obj is None:
                obj = ConsultingServiceSubtype(direction=direction)
            obj.direction = direction
            obj.service_type = service_type_by_key[(item["consulting_type"], item["service_type"])]
            obj.name = item["name"]
            obj.position = item["position"]
            obj.save()
            kept_subtype_ids.append(obj.pk)

        direction.service_subtypes.exclude(pk__in=kept_subtype_ids).delete()
        direction.service_types.exclude(pk__in=kept_service_type_ids).delete()
        direction.consulting_types.exclude(pk__in=kept_type_ids).delete()

        affected_products = Product.objects.filter(
            Q(consulting_type_ref__direction=direction)
            | Q(service_category_ref__direction=direction)
            | Q(service_subtype_ref__direction=direction)
        ).distinct()
        for product in affected_products:
            product.save()
        return direction

class TypicalSectionForm(forms.ModelForm):
    product = forms.ModelChoiceField(
        label="Продукт",
        queryset=Product.objects.all(),
        widget=forms.Select(attrs={"class": "form-select"})
    )
    expertise_dir = forms.ModelChoiceField(
        label="Экспертиза",
        queryset=ExpertiseDirection.objects.all(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    expertise_direction = forms.ModelChoiceField(
        label="Направление экспертизы",
        queryset=OrgUnit.objects.filter(
            Q(unit_type="expertise") | Q(unit_type="administrative", level=1)
        ),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = TypicalSection
        fields = [
            "product",
            "code",
            "short_name",
            "short_name_ru",
            "name_en",
            "name_ru",
            "accounting_type",
            "expertise_dir",
            "expertise_direction",
            "exclude_from_tkp_autofill",
        ]
        widgets = {
            "code": forms.TextInput(attrs={"class": "form-control", "placeholder": "Код"}),
            "short_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Short name EN"}),
            "short_name_ru": forms.TextInput(attrs={"class": "form-control", "placeholder": "Краткое имя RU"}),
            "name_en": forms.TextInput(attrs={"class": "form-control", "placeholder": "English section name"}),
            "name_ru": forms.TextInput(attrs={"class": "form-control", "placeholder": "Русское наименование раздела"}),
            "accounting_type": forms.Select(attrs={"class": "form-select"}),
            "exclude_from_tkp_autofill": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, request_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["expertise_dir"].queryset = ExpertiseDirection.objects.order_by("position", "id")
        self.fields["expertise_dir"].label_from_instance = (
            lambda obj: f"{obj.short_name} {obj.name}"
        )
        qs = OrgUnit.objects.filter(
            Q(unit_type="expertise") | Q(unit_type="administrative", level=1)
        )
        self.fields["expertise_direction"].queryset = qs
        self.fields["expertise_direction"].label_from_instance = lambda obj: obj.department_name


class SectionStructureForm(forms.ModelForm):
    product = forms.ModelChoiceField(
        label="Продукт",
        queryset=Product.objects.all(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    section = forms.ModelChoiceField(
        label="Раздел",
        queryset=TypicalSection.objects.select_related("product").all(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, request_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["section"].label_from_instance = (
            lambda obj: f"{obj.code}: {obj.name_ru or obj.name_en}"
        )

    class Meta:
        model = SectionStructure
        fields = ["product", "section", "subsections"]
        widgets = {
            "subsections": forms.Textarea(attrs={
                "class": "form-control",
                "placeholder": "Наименование подраздела",
                "rows": 4,
            }),
        }


class ServiceGoalReportForm(forms.ModelForm):
    product = forms.ModelChoiceField(
        label="Продукт",
        queryset=Product.objects.all(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = ServiceGoalReport
        fields = ["product", "service_goal", "service_goal_genitive", "report_title"]
        widgets = {
            "service_goal": forms.Textarea(attrs={
                "class": "form-control",
                "placeholder": "Цели оказания услуг",
                "rows": 4,
            }),
            "service_goal_genitive": forms.Textarea(attrs={
                "class": "form-control",
                "placeholder": "Цели оказания услуг в родительном падеже",
                "rows": 4,
            }),
            "report_title": forms.Textarea(attrs={
                "class": "form-control",
                "placeholder": "Название отчета",
                "rows": 4,
            }),
        }


class TypicalServiceCompositionForm(forms.ModelForm):
    product = forms.ModelChoiceField(
        label="Продукт",
        queryset=Product.objects.all(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    section = forms.ModelChoiceField(
        label="Раздел (услуга)",
        queryset=TypicalSection.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    service_composition_editor_state = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"id": "id_service_composition_editor_state"}),
    )

    class Meta:
        model = TypicalServiceComposition
        fields = ["product", "section", "service_composition", "service_composition_editor_state"]
        widgets = {
            "service_composition": forms.Textarea(attrs={
                "class": "form-control",
                "placeholder": "Состав услуг",
                "rows": 6,
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].label_from_instance = lambda obj: obj.short_name
        self.fields["section"].label_from_instance = lambda obj: obj.name_ru

        product_id = None
        section_id = None
        if self.is_bound:
            product_id = self.data.get("product")
            section_id = self.data.get("section")
        elif self.instance and self.instance.pk:
            product_id = self.instance.product_id
            section_id = self.instance.section_id
        else:
            product_id = self.initial.get("product")
            section_id = self.initial.get("section")

        section_qs = TypicalSection.objects.select_related("product").order_by("position", "id")
        if product_id:
            filtered_qs = section_qs.filter(product_id=product_id)
            if section_id:
                filtered_qs = section_qs.filter(Q(product_id=product_id) | Q(pk=section_id))
            self.fields["section"].queryset = filtered_qs
        elif self.instance and self.instance.pk:
            self.fields["section"].queryset = section_qs.filter(pk=self.instance.section_id)
        else:
            self.fields["section"].queryset = section_qs.none()
        if self.instance and self.instance.pk and not self.is_bound:
            self.initial["service_composition_editor_state"] = json.dumps(
                self.instance.service_composition_editor_state or {},
                ensure_ascii=False,
            )
        elif not self.is_bound:
            self.initial["service_composition_editor_state"] = ""

    def clean(self):
        cleaned = super().clean()
        product = cleaned.get("product")
        section = cleaned.get("section")
        if product and section and section.product_id != product.id:
            self.add_error("section", "Раздел должен относиться к выбранному продукту.")
        return cleaned

    def clean_service_composition_editor_state(self):
        raw = str(self.cleaned_data.get("service_composition_editor_state") or "").strip()
        if not raw:
            self.cleaned_service_composition_editor_state = {}
            return ""
        try:
            value = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            raise forms.ValidationError("Некорректное состояние редактора состава услуг.")
        if not isinstance(value, dict):
            raise forms.ValidationError("Некорректный формат состояния редактора состава услуг.")
        normalized = {
            "html": str(value.get("html") or "").strip(),
            "plain_text": str(value.get("plain_text") or "").strip(),
        }
        self.cleaned_service_composition_editor_state = normalized
        return json.dumps(normalized, ensure_ascii=False)

    def clean_service_composition(self):
        value = str(self.cleaned_data.get("service_composition") or "").strip()
        editor_state = getattr(self, "cleaned_service_composition_editor_state", None)
        if editor_state is None:
            raw = str(self.data.get("service_composition_editor_state") or "").strip()
            if raw:
                try:
                    parsed = json.loads(raw)
                except (TypeError, ValueError, json.JSONDecodeError):
                    parsed = {}
                editor_state = parsed if isinstance(parsed, dict) else {}
            else:
                editor_state = {}
        plain_text = str((editor_state or {}).get("plain_text") or "").strip()
        return plain_text or value

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.service_composition_editor_state = getattr(self, "cleaned_service_composition_editor_state", {})
        if commit:
            instance.save()
        return instance


class TypicalServiceTermForm(forms.ModelForm):
    product = forms.ModelChoiceField(
        label="Продукт",
        queryset=Product.objects.all(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    preliminary_report_months = CommaDecimalField(
        label="Срок подготовки Предварительного отчёта, мес.",
        min_value=0,
        decimal_places=1,
        max_digits=6,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "inputmode": "decimal",
            "placeholder": "0,0",
        }),
    )

    class Meta:
        model = TypicalServiceTerm
        fields = ["product", "preliminary_report_months", "final_report_weeks"]
        widgets = {
            "final_report_weeks": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "0",
                "step": "1",
                "placeholder": "0",
            }),
        }


class ExpertiseDirectionForm(forms.ModelForm):
    class Meta:
        model = ExpertiseDirection
        fields = ["name", "short_name", "pricing_method"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Наименование направления"}),
            "short_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Краткое обозначение"}),
            "pricing_method": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner_options = list(GroupMember.objects.order_by("position", "id").values("pk", "short_name"))
        self.selected_owner_ids = []
        self.is_group_selected = False
        if self.instance and self.instance.pk:
            if self.instance.is_group_owner:
                self.is_group_selected = True
            else:
                self.selected_owner_ids = list(
                    self.instance.owners.values_list("pk", flat=True)
                )

    def save(self, commit=True):
        obj = super().save(commit=False)
        owner_values = self.data.getlist("owner_ids")
        if OWNER_GROUP_VALUE in owner_values:
            obj.is_group_owner = True
        else:
            obj.is_group_owner = False
        if commit:
            obj.save()
            if obj.is_group_owner:
                obj.owners.clear()
            else:
                member_ids = [int(v) for v in owner_values if v != OWNER_GROUP_VALUE and v.isdigit()]
                obj.owners.set(member_ids)
        return obj


class GradeForm(forms.ModelForm):
    owner = forms.ModelChoiceField(
        label="Руководитель",
        queryset=User.objects.filter(
            Q(groups__name=DEPARTMENT_HEAD_GROUP) | Q(groups__name=DIRECTOR_GROUP)
        ),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    currency = forms.ModelChoiceField(
        label="Валюта",
        queryset=OKVCurrency.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_currency"}),
    )

    class Meta:
        model = Grade
        fields = [
            "grade_en", "grade_ru", "qualification_levels",
            "qualification", "is_base_rate", "base_rate_share",
            "hourly_rate", "currency",
        ]
        widgets = {
            "grade_en": forms.TextInput(attrs={"class": "form-control", "placeholder": "Grade (English)"}),
            "grade_ru": forms.TextInput(attrs={"class": "form-control", "placeholder": "Грейд (русский)"}),
            "qualification_levels": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 20}),
            "qualification": forms.HiddenInput(),
            "is_base_rate": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "base_rate_share": forms.NumberInput(attrs={
                "class": "form-control", "min": -500, "max": 500,
                "style": "max-width:120px;",
            }),
            "hourly_rate": forms.TextInput(attrs={
                "class": "form-control js-grade-money", "inputmode": "decimal",
                "placeholder": "0,00",
            }),
        }

    def __init__(self, *args, request_user=None, **kwargs):
        if args and args[0]:
            data = args[0].copy()
            v = data.get("hourly_rate", "")
            if v:
                data["hourly_rate"] = str(v).replace("\u00a0", "").replace(" ", "").replace(",", ".")
            args = (data,) + args[1:]
        elif "data" in kwargs and kwargs["data"]:
            data = kwargs["data"].copy()
            v = data.get("hourly_rate", "")
            if v:
                data["hourly_rate"] = str(v).replace("\u00a0", "").replace(" ", "").replace(",", ".")
            kwargs["data"] = data
        super().__init__(*args, **kwargs)
        self.request_user = request_user
        self.fields["base_rate_share"].required = False
        self.fields["hourly_rate"].required = False
        self.fields["owner"].queryset = User.objects.filter(
            Q(groups__name=DEPARTMENT_HEAD_GROUP) | Q(groups__name=DIRECTOR_GROUP)
        ).distinct().order_by("last_name", "first_name", "username")
        self.fields["owner"].label_from_instance = lambda u: (
            f"{u.last_name} {u.first_name}".strip() or u.username
        )
        if self.instance and self.instance.pk:
            self.initial["owner"] = self.instance.created_by_id

        today = timezone.now().date()
        currency_qs = OKVCurrency.objects.filter(
            Q(approval_date__isnull=True) | Q(approval_date__lte=today),
            Q(expiry_date__isnull=True) | Q(expiry_date__gte=today),
        ).order_by("code_alpha")
        if self.instance and self.instance.pk and self.instance.currency_id:
            currency_qs = (currency_qs | OKVCurrency.objects.filter(pk=self.instance.currency_id)).distinct().order_by("code_alpha")
        self.fields["currency"].queryset = currency_qs
        self.fields["currency"].label_from_instance = lambda obj: f"{obj.code_alpha} {obj.name}"
        self.fields["currency"].empty_label = "---------"
        if not (self.instance and self.instance.pk):
            rub = currency_qs.filter(code_alpha="RUB").first()
            if rub:
                self.initial["currency"] = rub.pk

    def clean_base_rate_share(self):
        val = self.cleaned_data.get("base_rate_share", 0) or 0
        if val < -500 or val > 500:
            raise forms.ValidationError("Значение должно быть от -500 до +500.")
        return val

    def clean_qualification(self):
        q = self.cleaned_data.get("qualification", 0) or 0
        levels = self.cleaned_data.get("qualification_levels") or self.instance.qualification_levels if self.instance else 5
        if q < 0 or q > levels:
            raise forms.ValidationError(f"Значение должно быть от 0 до {levels}.")
        return q


class SpecialtyTariffForm(forms.ModelForm):
    owner = forms.ModelChoiceField(
        label="Руководитель",
        queryset=User.objects.filter(
            Q(groups__name=DEPARTMENT_HEAD_GROUP) | Q(groups__name=DIRECTOR_GROUP)
        ),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    specialties = forms.ModelMultipleChoiceField(
        label="Специальности",
        queryset=ExpertSpecialty.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "d-none"}),
    )
    expertise_direction_display = forms.CharField(
        label="Направления экспертизы",
        required=False,
        widget=forms.TextInput(attrs={
            "readonly": True,
            "tabindex": "-1",
            "class": "form-control readonly-field",
            "id": "specialty-tariff-expertise-direction-field",
        }),
    )
    currency = forms.ModelChoiceField(
        label="Валюта",
        queryset=OKVCurrency.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = SpecialtyTariff
        fields = [
            "specialty_group",
            "specialties",
            "daily_rate_tkp_eur",
            "daily_rate_ss",
            "currency",
        ]
        widgets = {
            "specialty_group": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Группа специальностей",
            }),
            "daily_rate_tkp_eur": forms.TextInput(attrs={
                "class": "form-control js-specialty-tariff-money",
                "inputmode": "decimal",
                "placeholder": "0,00",
            }),
            "daily_rate_ss": forms.TextInput(attrs={
                "class": "form-control js-specialty-tariff-money",
                "inputmode": "decimal",
                "placeholder": "0,00",
            }),
        }

    def __init__(self, *args, request_user=None, **kwargs):
        if args and args[0]:
            data = args[0].copy()
            for field_name in ("daily_rate_tkp_eur", "daily_rate_ss"):
                value = data.get(field_name, "")
                if value:
                    data[field_name] = str(value).replace("\u00a0", "").replace(" ", "").replace(",", ".")
            args = (data,) + args[1:]
        elif "data" in kwargs and kwargs["data"]:
            data = kwargs["data"].copy()
            for field_name in ("daily_rate_tkp_eur", "daily_rate_ss"):
                value = data.get(field_name, "")
                if value:
                    data[field_name] = str(value).replace("\u00a0", "").replace(" ", "").replace(",", ".")
            kwargs["data"] = data

        super().__init__(*args, **kwargs)
        self.request_user = request_user

        specialty_qs = ExpertSpecialty.objects.exclude(specialty="").select_related(
            "expertise_dir"
        ).order_by("position", "id")
        self.fields["specialties"].queryset = specialty_qs
        self.fields["specialties"].label_from_instance = lambda obj: obj.specialty
        self.initial["expertise_direction_display"] = self._get_expertise_direction_display()

        self.fields["owner"].queryset = User.objects.filter(
            Q(groups__name=DEPARTMENT_HEAD_GROUP) | Q(groups__name=DIRECTOR_GROUP)
        ).distinct().order_by("last_name", "first_name", "username")
        self.fields["owner"].label_from_instance = lambda u: (
            f"{u.last_name} {u.first_name}".strip() or u.username
        )
        if self.instance and self.instance.pk:
            self.initial["owner"] = self.instance.created_by_id

        today = timezone.now().date()
        currency_qs = OKVCurrency.objects.filter(
            Q(approval_date__isnull=True) | Q(approval_date__lte=today),
            Q(expiry_date__isnull=True) | Q(expiry_date__gte=today),
        ).order_by("code_alpha")
        if self.instance and self.instance.pk and self.instance.currency_id:
            currency_qs = (
                currency_qs | OKVCurrency.objects.filter(pk=self.instance.currency_id)
            ).distinct().order_by("code_alpha")
        self.fields["currency"].queryset = currency_qs
        self.fields["currency"].label_from_instance = lambda obj: f"{obj.code_alpha} {obj.name}"
        self.fields["currency"].empty_label = "---------"
        if not (self.instance and self.instance.pk):
            rub = currency_qs.filter(code_alpha="RUB").first()
            if rub:
                self.initial["currency"] = rub.pk

    def _get_expertise_direction_display(self):
        specialties = []
        if self.is_bound:
            raw_ids = self.data.getlist("specialties")
            specialty_map = {
                str(item.pk): item for item in self.fields["specialties"].queryset
            }
            specialties = [specialty_map[raw_id] for raw_id in raw_ids if raw_id in specialty_map]
        elif self.instance and self.instance.pk:
            specialties = list(
                self.instance.specialties.select_related("expertise_direction").order_by("position", "id")
            )

        labels = []
        seen = set()
        for specialty in specialties:
            label = (getattr(specialty.expertise_dir, "short_name", "") or "").strip()
            if label == "—":
                label = ""
            if label and label not in seen:
                seen.add(label)
                labels.append(label)
        return ", ".join(labels)

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.expertise_direction = None
        if commit:
            obj.save()
            self.save_m2m()
        return obj


class TariffForm(forms.ModelForm):
    owner = forms.ModelChoiceField(
        label="Руководитель",
        queryset=User.objects.filter(
            Q(groups__name=DEPARTMENT_HEAD_GROUP) | Q(groups__name=DIRECTOR_GROUP)
        ),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    product = forms.ModelChoiceField(
        label="Продукт",
        queryset=Product.objects.all(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    section = forms.ModelChoiceField(
        label="Раздел",
        queryset=TypicalSection.objects.select_related("product").all(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = Tariff
        fields = ["product", "section", "base_rate_vpm", "service_hours", "service_days_tkp"]
        widgets = {
            "base_rate_vpm": forms.NumberInput(attrs={
                "class": "form-control", "step": "0.01", "min": "0",
                "placeholder": "1,00",
            }),
            "service_hours": forms.NumberInput(attrs={
                "class": "form-control", "min": "0", "step": "1",
                "placeholder": "0",
            }),
            "service_days_tkp": forms.NumberInput(attrs={
                "class": "form-control", "min": "0", "step": "1",
                "placeholder": "0",
            }),
        }

    def __init__(self, *args, request_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request_user = request_user
        self.fields["product"].label_from_instance = lambda obj: obj.short_name
        self.fields["section"].label_from_instance = (
            lambda obj: f"{obj.code}: {obj.name_ru or obj.name_en}"
        )
        self.fields["owner"].queryset = User.objects.filter(
            Q(groups__name=DEPARTMENT_HEAD_GROUP) | Q(groups__name=DIRECTOR_GROUP)
        ).distinct().order_by("last_name", "first_name", "username")
        self.fields["owner"].label_from_instance = lambda u: (
            f"{u.last_name} {u.first_name}".strip() or u.username
        )
        if self.instance and self.instance.pk:
            self.initial["owner"] = self.instance.created_by_id