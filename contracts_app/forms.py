from datetime import date as date_type

from django import forms
from django.db.models import Q

from classifiers_app.models import OKSMCountry
from group_app.models import GroupMember
from policy_app.models import Product, TypicalSection
from projects_app.models import Performer
from .models import ContractSubject, ContractTemplate, ContractVariable

SECTION_ALL_VALUE = "__all__"


class _ContractFileInput(forms.ClearableFileInput):
    initial_text = "Текущий файл"
    input_text = "Загрузить другой"
    clear_checkbox_label = "Удалить"
    template_name = "contracts_app/widgets/clearable_file_input.html"

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        if ctx["widget"].get("is_initial") and value and hasattr(value, "name"):
            import os
            ctx["widget"]["file_basename"] = os.path.basename(value.name)
        return ctx

PARTY_SHORT = {"individual": "ФЗЛ", "legal_entity": "ЮРЛ", "ip": "ИП"}
TYPE_SHORT = {"gph": "ГПХ", "smz": "СМЗ"}


class ContractEditForm(forms.ModelForm):
    class Meta:
        model = Performer
        fields = [
            "contract_number",
            "contract_date",
            "contract_file",
        ]
        widgets = {
            "contract_number": forms.TextInput(attrs={"class": "form-control"}),
            "contract_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "contract_file": forms.TextInput(attrs={"class": "form-control"}),
        }


class ContractSigningForm(forms.ModelForm):
    class Meta:
        model = Performer
        fields = [
            "contract_employee_scan",
            "contract_send_date",
            "contract_signed_scan",
            "contract_upload_date",
        ]
        widgets = {
            "contract_employee_scan": _ContractFileInput(attrs={"class": "form-control"}),
            "contract_send_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "contract_signed_scan": forms.TextInput(attrs={"class": "form-control"}),
            "contract_upload_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }


def _active_countries_qs():
    today = date_type.today()
    return OKSMCountry.objects.filter(
        Q(approval_date__isnull=True) | Q(approval_date__lte=today),
    ).filter(
        Q(expiry_date__isnull=True) | Q(expiry_date__gte=today),
    ).order_by("short_name")


def _group_member_order_map():
    counters = {}
    result = {}
    for m in GroupMember.objects.all():
        key = m.country_code or m.country_name or ""
        idx = counters.get(key, 0)
        result[m.pk] = idx
        counters[key] = idx + 1
    return result


def _group_member_label(member, order):
    alpha2 = member.country_alpha2 or ""
    prefix = f"{alpha2}-{order}" if order else alpha2
    return f"{prefix} {member.short_name}"


def _group_member_short(member, order):
    alpha2 = member.country_alpha2 or ""
    return f"{alpha2}-{order}" if order else alpha2


class ContractTemplateForm(forms.ModelForm):
    country = forms.ModelChoiceField(
        label="Страна",
        queryset=OKSMCountry.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = ContractTemplate
        fields = [
            "group_member", "product", "contract_type", "party",
            "sample_name", "version", "file",
        ]
        widgets = {
            "group_member": forms.Select(attrs={"class": "form-select"}),
            "product": forms.Select(attrs={"class": "form-select"}),
            "contract_type": forms.Select(attrs={"class": "form-select"}),
            "party": forms.Select(attrs={"class": "form-select"}),
            "sample_name": forms.TextInput(attrs={"class": "form-control readonly-field", "readonly": True, "tabindex": "-1"}),
            "version": forms.TextInput(attrs={"class": "form-control readonly-field", "readonly": True, "tabindex": "-1"}),
            "file": _ContractFileInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._orig_sample_name = ""
        self._orig_version = ""
        if self.instance and self.instance.pk:
            self._orig_sample_name = self.instance.sample_name or ""
            self._orig_version = self.instance.version or ""

        order_map = _group_member_order_map()
        members_qs = GroupMember.objects.all()
        self.fields["group_member"].queryset = members_qs
        self.fields["group_member"].label_from_instance = lambda obj: _group_member_label(obj, order_map.get(obj.pk, 0))
        self.fields["group_member"].required = True

        self.fields["file"].required = not (self.instance and self.instance.pk and self.instance.file)

        self.group_short_map = {
            str(m.pk): _group_member_short(m, order_map.get(m.pk, 0)) for m in members_qs
        }

        self.fields["product"].queryset = Product.objects.order_by("position", "id")
        self.fields["product"].label_from_instance = lambda obj: obj.short_name

        qs = _active_countries_qs()
        if self.instance and self.instance.pk and self.instance.country_code:
            qs = (qs | OKSMCountry.objects.filter(code=self.instance.country_code)).distinct().order_by("short_name")
        self.fields["country"].queryset = qs
        self.fields["country"].label_from_instance = lambda obj: f"{obj.alpha3} {obj.short_name}"

        if self.instance and self.instance.pk and self.instance.country_code:
            try:
                self.initial["country"] = OKSMCountry.objects.get(code=self.instance.country_code).pk
            except OKSMCountry.DoesNotExist:
                pass
        elif not self.instance.pk:
            try:
                self.initial["country"] = qs.get(alpha3="RUS").pk
            except OKSMCountry.DoesNotExist:
                pass

        self.country_alpha3 = {
            str(c.pk): c.alpha3 for c in self.fields["country"].queryset
        }

        sections = (
            TypicalSection.objects
            .select_related("product")
            .order_by("product__position", "position", "id")
        )
        self.section_options = [
            {
                "id": s.id,
                "code": s.code,
                "short_name": s.short_name,
                "short_name_ru": s.short_name_ru,
                "label": f"{s.product.short_name}:{s.code} {s.short_name_ru}",
            }
            for s in sections
        ]

        self.is_all_selected = True
        self.selected_section_codes = set()
        if self.instance and self.instance.pk:
            self.is_all_selected = self.instance.is_all_sections
            if not self.is_all_selected:
                self.selected_section_codes = {
                    entry.get("code") for entry in (self.instance.typical_sections_json or [])
                }

        existing = ContractTemplate.objects.all()
        if self.instance and self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        version_map = {}
        for t in existing:
            base = t.sample_name.rsplit("_v", 1)[0] if t.sample_name else ""
            try:
                v = int(t.version)
            except (ValueError, TypeError):
                v = 0
            version_map[base] = max(version_map.get(base, 0), v)
        self.version_map = version_map

        self.current_base = ""
        self.current_version = ""
        if self.instance and self.instance.pk and self.instance.sample_name:
            self.current_base = self.instance.sample_name.rsplit("_v", 1)[0]
            self.current_version = self.instance.version or ""

    def save(self, commit=True):
        instance = super().save(commit=False)
        country = self.cleaned_data.get("country")
        if country:
            instance.country_name = country.short_name
            instance.country_code = country.code
        else:
            instance.country_name = ""
            instance.country_code = ""

        section_values = self.data.getlist("section_ids")
        if SECTION_ALL_VALUE in section_values or not section_values:
            instance.is_all_sections = True
            instance.typical_sections_json = []
        else:
            instance.is_all_sections = False
            selected_ids = {int(v) for v in section_values if v.isdigit()}
            chosen = (
                TypicalSection.objects
                .filter(pk__in=selected_ids)
                .order_by("product__position", "position", "id")
            )
            instance.typical_sections_json = [
                {"code": s.code, "short_name": s.short_name}
                for s in chosen
            ]

        party_short = PARTY_SHORT.get(instance.party, "")
        type_short = TYPE_SHORT.get(instance.contract_type, "")
        alpha3 = country.alpha3 if country else ""
        product_name = ""
        if instance.product_id:
            product_name = instance.product.short_name
        if instance.is_all_sections:
            sections_part = "Общий"
        else:
            codes = [e.get("code", "") for e in instance.typical_sections_json or [] if e.get("code")]
            sections_part = "-".join(codes) if codes else "Общий"
        group_prefix = ""
        if instance.group_member_id:
            order_map = _group_member_order_map()
            group_prefix = _group_member_short(instance.group_member, order_map.get(instance.group_member_id, 0)) + " "
        base_name = (
            f"{group_prefix}Шаблон договора {party_short} {type_short} "
            f"{alpha3}_{product_name}-{sections_part}"
        )

        existing = ContractTemplate.objects.all()
        if instance.pk:
            orig_base = self._orig_sample_name.rsplit("_v", 1)[0] if self._orig_sample_name else ""
            if orig_base == base_name:
                version = self._orig_version or "1"
            else:
                existing = existing.exclude(pk=instance.pk)
                version = str(self._next_version(existing, base_name))
        else:
            version = str(self._next_version(existing, base_name))

        instance.version = version
        instance.sample_name = f"{base_name}_v{version}"

        import os
        uploaded = self.cleaned_data.get("file")
        if uploaded:
            ext = os.path.splitext(uploaded.name)[1]
            instance.file.name = instance.sample_name + ext
        elif instance.pk and instance.file:
            old_path = instance.file.name
            ext = os.path.splitext(old_path)[1]
            new_name = "contract_templates/" + instance.sample_name + ext
            if old_path != new_name:
                storage = instance.file.storage
                if storage.exists(old_path):
                    old_full = storage.path(old_path)
                    new_full = storage.path(new_name)
                    os.makedirs(os.path.dirname(new_full), exist_ok=True)
                    os.rename(old_full, new_full)
                instance.file.name = new_name

        if commit:
            instance.save()
        return instance

    @staticmethod
    def _next_version(qs, base_name):
        max_v = 0
        for t in qs:
            t_base = t.sample_name.rsplit("_v", 1)[0] if t.sample_name else ""
            if t_base == base_name:
                try:
                    v = int(t.version)
                except (ValueError, TypeError):
                    v = 0
                max_v = max(max_v, v)
        return max_v + 1


class ContractVariableForm(forms.ModelForm):
    source_section = forms.ChoiceField(
        label="Раздел", required=False,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_source_section"}),
    )
    source_table = forms.ChoiceField(
        label="Таблица", required=False,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_source_table"}),
    )
    source_column = forms.ChoiceField(
        label="Столбец", required=False,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_source_column"}),
    )

    class Meta:
        model = ContractVariable
        fields = [
            "key", "description",
            "source_section", "source_table", "source_column",
        ]
        widgets = {
            "key": forms.TextInput(attrs={"class": "form-control", "placeholder": "{{variable_name}}"}),
            "description": forms.TextInput(attrs={"class": "form-control", "placeholder": "Описание переменной"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.column_registry import (
            get_section_choices, get_table_choices, get_column_choices,
        )

        self.is_computed = bool(
            self.instance and self.instance.pk and self.instance.is_computed
        )

        if self.is_computed:
            locked_style = "background-color:#f8f9fa; color:#6c757d;"
            self.fields["key"].widget.attrs.update({
                "readonly": True, "tabindex": "-1", "style": locked_style,
            })
            for fname in ("source_section", "source_table", "source_column"):
                self.fields[fname].widget.attrs.update({
                    "disabled": True, "style": locked_style,
                })

        self.fields["source_section"].choices = get_section_choices()

        sec = (
            self.data.get("source_section", "")
            or self.initial.get("source_section", "")
            or (self.instance.source_section if self.instance and self.instance.pk else "")
        )
        tbl = (
            self.data.get("source_table", "")
            or self.initial.get("source_table", "")
            or (self.instance.source_table if self.instance and self.instance.pk else "")
        )
        if sec:
            self.fields["source_table"].choices = get_table_choices(sec)
        else:
            self.fields["source_table"].choices = [("", "---")]
        if sec and tbl:
            self.fields["source_column"].choices = get_column_choices(sec, tbl)
        else:
            self.fields["source_column"].choices = [("", "---")]

    def clean_key(self):
        import re
        if self.is_computed:
            return self.instance.key
        raw = self.cleaned_data.get("key", "").strip()
        inner = raw.removeprefix("{{").removesuffix("}}")
        inner = inner.removeprefix("{").removesuffix("}")
        inner = inner.strip()
        if not inner:
            raise forms.ValidationError("Поле не может быть пустым.")
        if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*", inner):
            raise forms.ValidationError(
                "Допускаются только латинские буквы, цифры и подчёркивания. "
                "Значение должно начинаться с буквы."
            )
        return "{{" + inner + "}}"

    def clean(self):
        cleaned = super().clean()
        if self.is_computed:
            return cleaned
        sec = cleaned.get("source_section", "")
        tbl = cleaned.get("source_table", "")
        col = cleaned.get("source_column", "")
        filled = [f for f in (sec, tbl, col) if f]
        if filled and len(filled) != 3:
            raise forms.ValidationError(
                "Необходимо заполнить все три поля: Раздел, Таблица и Столбец."
            )
        if sec and tbl and col:
            from core.column_registry import validate_column_ref
            if not validate_column_ref(sec, tbl, col):
                raise forms.ValidationError("Указанная комбинация Раздел/Таблица/Столбец не существует.")
        return cleaned


class ContractSubjectForm(forms.ModelForm):
    class Meta:
        model = ContractSubject
        fields = ["product", "subject_text"]
        widgets = {
            "product": forms.Select(attrs={"class": "form-select"}),
            "subject_text": forms.Textarea(attrs={
                "class": "form-control",
                "placeholder": "Предмет договора",
                "rows": 4,
                "style": "resize: vertical;",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.order_by("position", "id")
        self.fields["product"].label_from_instance = lambda obj: obj.short_name
