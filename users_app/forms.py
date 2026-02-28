from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password

from group_app.models import GroupMember
from .models import Employee

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
    role = forms.CharField(
        label="Роль",
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Роль"}),
    )

    def __init__(self, *args, instance=None, **kwargs):
        self.instance = instance
        super().__init__(*args, **kwargs)
        self.fields["employment"].choices = _employment_choices()
        if instance:
            self.fields["password"].help_text = "Оставьте пустым, чтобы не менять"
            user = instance.user
            self.initial.update({
                "last_name": user.last_name,
                "first_name": user.first_name,
                "patronymic": instance.patronymic,
                "email": user.email,
                "phone": instance.phone,
                "employment": instance.employment,
                "job_title": instance.job_title,
                "role": instance.role,
            })

    def clean_email(self):
        email = self.cleaned_data["email"]
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
        employee.role = data.get("role", "")
        employee.save()

        return employee
