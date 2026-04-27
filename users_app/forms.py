from django import forms
from django.contrib.auth.models import User, Group
from django.contrib.auth.password_validation import validate_password
from django.db.models import Case, IntegerField, Value, When

from contacts_app.models import PersonRecord
from group_app.models import GroupMember, OrgUnit
from policy_app.models import ROLE_GROUPS_ORDER, SUPERUSER_GROUPS
from .models import Employee, PendingRegistration

FREELANCER_LABEL = "Внештатный сотрудник"


def _employment_choices():
    choices = [("", "---------")]
    for gm in GroupMember.objects.all():
        choices.append((gm.short_name, gm.short_name))
    choices.append((FREELANCER_LABEL, FREELANCER_LABEL))
    return choices


def _role_queryset():
    order_expr = Case(
        *[When(name=name, then=Value(index)) for index, name in enumerate(ROLE_GROUPS_ORDER)],
        default=Value(len(ROLE_GROUPS_ORDER)),
        output_field=IntegerField(),
    )
    return Group.objects.annotate(_role_order=order_expr).order_by("_role_order", "name")


class EmployeeForm(forms.Form):
    last_name = forms.CharField(
        label="Фамилия",
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Фамилия"}),
    )
    first_name = forms.CharField(
        label="Имя",
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Имя"}),
    )
    patronymic = forms.CharField(
        label="Отчество",
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Отчество"}),
    )
    person_record = forms.ModelChoiceField(
        label="ID-PRS",
        queryset=PersonRecord.objects.none(),
        required=False,
        widget=forms.HiddenInput(),
    )
    email = forms.EmailField(
        label="Эл. почта (логин)",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "email@example.com",
                "autocomplete": "off",
                "autocapitalize": "off",
                "autocorrect": "off",
                "spellcheck": "false",
            }
        ),
    )
    password = forms.CharField(
        label="Пароль",
        required=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Пароль",
                "autocomplete": "new-password",
            }
        ),
    )
    employment = forms.ChoiceField(
        label="Трудоустройство",
        required=False,
        widget=forms.Select(attrs={"class": "form-select", "id": "emp-employment-select"}),
    )
    department = forms.ModelChoiceField(
        label="Подразделение",
        queryset=OrgUnit.objects.none(),
        required=False,
        empty_label="---------",
        widget=forms.Select(attrs={"class": "form-select", "id": "emp-department-select"}),
    )
    job_title = forms.CharField(
        label="Должность",
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Должность"}),
    )
    role = forms.ModelChoiceField(
        label="Роль",
        queryset=Group.objects.none(),
        required=False,
        empty_label="---------",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, instance=None, **kwargs):
        self.instance = instance
        super().__init__(*args, **kwargs)
        self.fields["person_record"].queryset = PersonRecord.objects.order_by("position", "id")
        self.fields["employment"].choices = _employment_choices()
        self.fields["department"].queryset = OrgUnit.objects.select_related("company").all()
        self.fields["department"].label_from_instance = lambda obj: obj.department_name
        self.fields["role"].queryset = _role_queryset()
        if instance:
            self.fields["password"].help_text = "Оставьте пустым, чтобы не менять"
            user = instance.user
            current_group = user.groups.first()
            self.initial.update({
                "last_name": user.last_name,
                "first_name": user.first_name,
                "patronymic": instance.patronymic,
                "person_record": instance.person_record_id,
                "email": user.email,
                "employment": instance.employment,
                "department": instance.department_id,
                "job_title": instance.job_title,
                "role": current_group.pk if current_group else None,
            })
        selected_person = self._selected_person_record()
        should_sync_from_person_record = (
            selected_person is not None
            and (
                self.instance is None
                or (
                    self.is_bound
                    and selected_person.pk != getattr(self.instance, "person_record_id", None)
                )
            )
        )
        if should_sync_from_person_record:
            self.initial["last_name"] = selected_person.last_name or ""
            self.initial["first_name"] = selected_person.first_name or ""
            self.initial["patronymic"] = selected_person.middle_name or ""
            self._lock_name_fields()

    def _selected_person_record(self):
        raw_person_id = None
        if self.is_bound:
            raw_person_id = self.data.get("person_record")
        elif self.instance and self.instance.person_record_id:
            raw_person_id = self.instance.person_record_id
        elif self.initial.get("person_record"):
            raw_person_id = self.initial.get("person_record")
        try:
            person_id = int(raw_person_id)
        except (TypeError, ValueError):
            return None
        return PersonRecord.objects.filter(pk=person_id).first()

    def _lock_name_fields(self):
        for field_name in ("last_name", "first_name", "patronymic"):
            field = self.fields[field_name]
            field.disabled = True
            field.widget.attrs["readonly"] = True
            field.widget.attrs["tabindex"] = "-1"
            field.widget.attrs["class"] = field.widget.attrs.get("class", "") + " readonly-field"

    def clean_email(self):
        email = self.cleaned_data["email"]
        if len(email) > 150:
            raise forms.ValidationError("Email не может быть длиннее 150 символов.")
        qs = User.objects.filter(username=email)
        if self.instance:
            qs = qs.exclude(pk=self.instance.user_id)
        if qs.exists():
            raise forms.ValidationError("Пользователь с таким email уже существует.")
        return email

    def clean_password(self):
        pwd = self.cleaned_data.get("password", "")
        if not self.instance and not pwd:
            raise forms.ValidationError("Пароль обязателен при создании сотрудника.")
        if pwd:
            validate_password(pwd)
        return pwd

    def clean_person_record(self):
        person_record = self.cleaned_data.get("person_record")
        if person_record is None and self.instance is not None:
            return self.instance.person_record
        return person_record

    def clean(self):
        cleaned_data = super().clean()
        person_record = cleaned_data.get("person_record")
        should_sync_from_person_record = (
            person_record is not None
            and (
                self.instance is None
                or person_record.pk != getattr(self.instance, "person_record_id", None)
            )
        )
        if should_sync_from_person_record:
            cleaned_data["last_name"] = person_record.last_name or ""
            cleaned_data["first_name"] = person_record.first_name or ""
            cleaned_data["patronymic"] = person_record.middle_name or ""
        return cleaned_data

    def save(self):
        data = self.cleaned_data
        if self.instance:
            user = self.instance.user
            employee = self.instance
        else:
            user = User(is_staff=True)
            employee = Employee(user=user)
        previous_person_record_id = employee.person_record_id

        user.last_name = data["last_name"]
        user.first_name = data["first_name"]
        user.email = data["email"]
        user.username = data["email"]
        if data.get("password"):
            user.set_password(data["password"])
        user.save()

        employee.user = user
        employee.patronymic = data.get("patronymic", "")
        employee.person_record = data.get("person_record")
        employee.employment = data.get("employment", "")
        employee.department = data.get("department")
        employee.job_title = data.get("job_title", "")
        employee._previous_person_record_id = previous_person_record_id

        group = data.get("role")
        user.groups.clear()
        if group:
            user.groups.add(group)
            employee.role = group.name
        else:
            employee.role = ""

        user.is_superuser = bool(group and group.name in SUPERUSER_GROUPS)
        user.save(update_fields=["is_superuser"])

        employee.save()

        return employee


class ExternalEmployeeForm(forms.Form):
    last_name = forms.CharField(
        label="Фамилия",
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Фамилия"}),
    )
    first_name = forms.CharField(
        label="Имя",
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Имя"}),
    )
    patronymic = forms.CharField(
        label="Отчество",
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Отчество"}),
    )
    email = forms.EmailField(
        label="Эл. почта (логин)",
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "email@example.com"}),
    )
    password = forms.CharField(
        label="Пароль",
        required=False,
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Пароль"}),
    )
    organization = forms.CharField(
        label="Организация",
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Организация"}),
    )
    job_title = forms.CharField(
        label="Должность",
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Должность"}),
    )

    def __init__(self, *args, instance=None, **kwargs):
        self.instance = instance
        super().__init__(*args, **kwargs)
        if instance:
            self.fields["password"].help_text = "Оставьте пустым, чтобы не менять"
            user = instance.user
            self.initial.update({
                "last_name": user.last_name,
                "first_name": user.first_name,
                "patronymic": instance.patronymic,
                "email": user.email,
                "organization": instance.organization,
                "job_title": instance.job_title,
            })

    def clean_email(self):
        email = self.cleaned_data["email"]
        if len(email) > 150:
            raise forms.ValidationError("Email не может быть длиннее 150 символов.")
        qs = User.objects.filter(username=email)
        if self.instance:
            qs = qs.exclude(pk=self.instance.user_id)
        if qs.exists():
            raise forms.ValidationError("Пользователь с таким email уже существует.")
        return email

    def clean_password(self):
        pwd = self.cleaned_data.get("password", "")
        if not self.instance and not pwd:
            raise forms.ValidationError("Пароль обязателен при создании пользователя.")
        if pwd:
            validate_password(pwd)
        return pwd

    def save(self):
        data = self.cleaned_data
        if self.instance:
            user = self.instance.user
            employee = self.instance
        else:
            user = User(is_staff=False)
            employee = Employee(user=user)
        previous_person_record_id = employee.person_record_id

        user.last_name = data["last_name"]
        user.first_name = data["first_name"]
        user.email = data["email"]
        user.username = data["email"]
        if data.get("password"):
            user.set_password(data["password"])
        user.save()

        employee.user = user
        employee.patronymic = data.get("patronymic", "")
        employee.organization = data.get("organization", "")
        employee.job_title = data.get("job_title", "")
        employee._previous_person_record_id = previous_person_record_id
        employee.save()

        return employee


_REG_INPUT = {"class": "form-control"}
_REG_INPUT_SM = {"class": "form-control", "autocomplete": "off"}
_REQ = {"required": "Поле является обязательным."}


class ExternalRegistrationForm(forms.Form):
    email = forms.EmailField(
        label="Электронная почта (логин)",
        error_messages=_REQ,
        widget=forms.EmailInput(attrs={**_REG_INPUT, "placeholder": "email@business.ru", "autofocus": True}),
    )
    password = forms.CharField(
        label="Пароль",
        error_messages=_REQ,
        widget=forms.PasswordInput(attrs={**_REG_INPUT, "placeholder": "Пароль"}),
    )
    password_confirm = forms.CharField(
        label="Подтверждение пароля",
        error_messages=_REQ,
        widget=forms.PasswordInput(attrs={**_REG_INPUT, "placeholder": "Повторите пароль"}),
    )
    last_name = forms.CharField(
        label="Фамилия", max_length=150,
        error_messages=_REQ,
        widget=forms.TextInput(attrs={**_REG_INPUT, "placeholder": "Фамилия"}),
    )
    first_name = forms.CharField(
        label="Имя", max_length=150,
        error_messages=_REQ,
        widget=forms.TextInput(attrs={**_REG_INPUT, "placeholder": "Имя"}),
    )
    patronymic = forms.CharField(
        label="Отчество", max_length=150,
        error_messages=_REQ,
        widget=forms.TextInput(attrs={**_REG_INPUT, "placeholder": "Отчество"}),
    )
    organization = forms.CharField(
        label="Организация", max_length=255,
        error_messages=_REQ,
        widget=forms.TextInput(attrs={**_REG_INPUT, "placeholder": "Название организации"}),
    )
    job_title = forms.CharField(
        label="Должность", max_length=255,
        error_messages=_REQ,
        widget=forms.TextInput(attrs={**_REG_INPUT, "placeholder": "Должность"}),
    )
    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        if len(email) > 150:
            raise forms.ValidationError("Email не может быть длиннее 150 символов.")
        if User.objects.filter(username=email).exists():
            raise forms.ValidationError("Пользователь с таким email уже зарегистрирован.")
        return email

    def clean_password(self):
        pwd = self.cleaned_data.get("password", "")
        if pwd:
            validate_password(pwd)
        return pwd

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password")
        p2 = cleaned.get("password_confirm")
        if p1 and p2 and p1 != p2:
            self.add_error("password_confirm", "Пароли не совпадают.")
        return cleaned

    def save(self):
        data = self.cleaned_data
        user = User(
            username=data["email"],
            email=data["email"],
            first_name=data["first_name"],
            last_name=data["last_name"],
            is_active=False,
            is_staff=False,
        )
        user.set_password(data["password"])
        user.save()

        Employee.objects.create(
            user=user,
            patronymic=data.get("patronymic", ""),
            organization=data.get("organization", ""),
            job_title=data.get("job_title", ""),
        )

        pending = PendingRegistration.objects.create(
            user=user,
            token=PendingRegistration.generate_token(),
            code=PendingRegistration.generate_code(),
        )
        return pending
