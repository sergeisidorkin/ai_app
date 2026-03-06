from django import forms
from django.contrib.auth.models import User, Group
from django.contrib.auth.password_validation import validate_password

from group_app.models import GroupMember
from .models import Employee, PendingRegistration

FREELANCER_LABEL = "Внештатный сотрудник"


def _employment_choices():
    choices = [("", "---------")]
    for gm in GroupMember.objects.all():
        choices.append((gm.short_name, gm.short_name))
    choices.append((FREELANCER_LABEL, FREELANCER_LABEL))
    return choices


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
    email = forms.EmailField(
        label="Эл. почта (логин)",
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "email@example.com"}),
    )
    password = forms.CharField(
        label="Пароль",
        required=False,
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Пароль"}),
    )
    phone = forms.CharField(
        label="Телефон",
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "+7 000 000-00-00"}),
    )
    employment = forms.ChoiceField(
        label="Трудоустройство",
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    job_title = forms.CharField(
        label="Должность",
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Должность"}),
    )
    role = forms.ModelChoiceField(
        label="Роль",
        queryset=Group.objects.all(),
        required=False,
        empty_label="---------",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, instance=None, **kwargs):
        self.instance = instance
        super().__init__(*args, **kwargs)
        self.fields["employment"].choices = _employment_choices()
        if instance:
            self.fields["password"].help_text = "Оставьте пустым, чтобы не менять"
            user = instance.user
            current_group = user.groups.first()
            self.initial.update({
                "last_name": user.last_name,
                "first_name": user.first_name,
                "patronymic": instance.patronymic,
                "email": user.email,
                "phone": instance.phone,
                "employment": instance.employment,
                "job_title": instance.job_title,
                "role": current_group.pk if current_group else None,
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
            raise forms.ValidationError("Пароль обязателен при создании сотрудника.")
        if pwd:
            validate_password(pwd)
        return pwd

    def save(self):
        data = self.cleaned_data
        if self.instance:
            user = self.instance.user
            employee = self.instance
        else:
            user = User(is_staff=True)
            employee = Employee(user=user)

        user.last_name = data["last_name"]
        user.first_name = data["first_name"]
        user.email = data["email"]
        user.username = data["email"]
        if data.get("password"):
            user.set_password(data["password"])
        user.save()

        employee.user = user
        employee.patronymic = data.get("patronymic", "")
        employee.phone = data.get("phone", "")
        employee.employment = data.get("employment", "")
        employee.job_title = data.get("job_title", "")

        group = data.get("role")
        user.groups.clear()
        if group:
            user.groups.add(group)
            employee.role = group.name
        else:
            employee.role = ""
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
    phone = forms.CharField(
        label="Телефон", max_length=50, required=False,
        widget=forms.TextInput(attrs={**_REG_INPUT, "placeholder": "+7 000 000-00-00"}),
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
            phone=data.get("phone", ""),
        )

        pending = PendingRegistration.objects.create(
            user=user,
            token=PendingRegistration.generate_token(),
            code=PendingRegistration.generate_code(),
        )
        return pending
