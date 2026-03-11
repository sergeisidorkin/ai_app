import json
import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.mail import send_mail
from django.db import models, transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from group_app.models import OrgUnit
from .forms import EmployeeForm, ExternalEmployeeForm, ExternalRegistrationForm
from .models import Employee, PendingRegistration

logger = logging.getLogger(__name__)

PARTIAL_TEMPLATE = "users_app/users_partial.html"
FORM_TEMPLATE = "users_app/employee_form.html"
EXT_FORM_TEMPLATE = "users_app/external_form.html"
HX_TRIGGER_HEADER = "HX-Trigger"
HX_EVENT = "users-updated"


def staff_required(u):
    return u.is_active and u.is_staff


def _users_context():
    all_employees = Employee.objects.select_related("user", "department").all()
    return {
        "staff_employees": all_employees.filter(user__is_staff=True),
        "external_employees": all_employees.filter(user__is_staff=False),
    }


def _render_updated(request):
    response = render(request, PARTIAL_TEMPLATE, _users_context())
    response[HX_TRIGGER_HEADER] = HX_EVENT
    return response


def _next_position(is_staff=True):
    mx = Employee.objects.filter(user__is_staff=is_staff).aggregate(m=Max("position"))["m"]
    return (mx or 0) + 1


def _normalize_positions(is_staff=True):
    for idx, obj in enumerate(Employee.objects.filter(user__is_staff=is_staff)):
        if obj.position != idx:
            Employee.objects.filter(pk=obj.pk).update(position=idx)


@login_required
@require_http_methods(["GET"])
def users_partial(request):
    return render(request, PARTIAL_TEMPLATE, _users_context())


def _emp_form_context(form, action, employee=None):
    units = list(
        OrgUnit.objects.select_related("company")
        .values("id", "department_name", company_short=models.F("company__short_name"))
    )
    ctx = {
        "form": form,
        "action": action,
        "org_units_json": json.dumps(units, ensure_ascii=False),
    }
    if employee is not None:
        ctx["employee"] = employee
    return ctx


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def employee_form_create(request):
    if request.method == "GET":
        form = EmployeeForm()
        return render(request, FORM_TEMPLATE, _emp_form_context(form, "create"))
    form = EmployeeForm(request.POST)
    if not form.is_valid():
        return render(request, FORM_TEMPLATE, _emp_form_context(form, "create"))
    emp = form.save()
    emp.position = _next_position(is_staff=True)
    emp.save(update_fields=["position"])
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def employee_form_edit(request, pk: int):
    employee = get_object_or_404(Employee.objects.select_related("user"), pk=pk)
    if request.method == "GET":
        form = EmployeeForm(instance=employee)
        return render(request, FORM_TEMPLATE, _emp_form_context(form, "edit", employee))
    form = EmployeeForm(request.POST, instance=employee)
    if not form.is_valid():
        return render(request, FORM_TEMPLATE, _emp_form_context(form, "edit", employee))
    form.save()
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def employee_delete(request, pk: int):
    emp = get_object_or_404(Employee, pk=pk)
    emp.user.delete()
    _normalize_positions(is_staff=True)
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def employee_move_up(request, pk: int):
    obj = get_object_or_404(Employee, pk=pk)
    prev = (
        Employee.objects
        .filter(user__is_staff=True, position__lt=obj.position)
        .order_by("-position")
        .first()
    )
    if prev:
        obj.position, prev.position = prev.position, obj.position
        Employee.objects.filter(pk=obj.pk).update(position=obj.position)
        Employee.objects.filter(pk=prev.pk).update(position=prev.position)
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def employee_move_down(request, pk: int):
    obj = get_object_or_404(Employee, pk=pk)
    nxt = (
        Employee.objects
        .filter(user__is_staff=True, position__gt=obj.position)
        .order_by("position")
        .first()
    )
    if nxt:
        obj.position, nxt.position = nxt.position, obj.position
        Employee.objects.filter(pk=obj.pk).update(position=obj.position)
        Employee.objects.filter(pk=nxt.pk).update(position=nxt.position)
    return _render_updated(request)


# ---------------------------------------------------------------------------
#  External (non-staff) user CRUD
# ---------------------------------------------------------------------------


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def ext_form_create(request):
    if request.method == "GET":
        form = ExternalEmployeeForm()
        return render(request, EXT_FORM_TEMPLATE, {"form": form, "action": "create"})
    form = ExternalEmployeeForm(request.POST)
    if not form.is_valid():
        return render(request, EXT_FORM_TEMPLATE, {"form": form, "action": "create"})
    emp = form.save()
    emp.position = _next_position(is_staff=False)
    emp.save(update_fields=["position"])
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_http_methods(["GET", "POST"])
def ext_form_edit(request, pk: int):
    employee = get_object_or_404(Employee.objects.select_related("user"), pk=pk, user__is_staff=False)
    if request.method == "GET":
        form = ExternalEmployeeForm(instance=employee)
        return render(request, EXT_FORM_TEMPLATE, {"form": form, "action": "edit", "employee": employee})
    form = ExternalEmployeeForm(request.POST, instance=employee)
    if not form.is_valid():
        return render(request, EXT_FORM_TEMPLATE, {"form": form, "action": "edit", "employee": employee})
    form.save()
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def ext_delete(request, pk: int):
    emp = get_object_or_404(Employee, pk=pk, user__is_staff=False)
    emp.user.delete()
    _normalize_positions(is_staff=False)
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def ext_move_up(request, pk: int):
    obj = get_object_or_404(Employee, pk=pk, user__is_staff=False)
    prev = (
        Employee.objects
        .filter(user__is_staff=False, position__lt=obj.position)
        .order_by("-position")
        .first()
    )
    if prev:
        obj.position, prev.position = prev.position, obj.position
        Employee.objects.filter(pk=obj.pk).update(position=obj.position)
        Employee.objects.filter(pk=prev.pk).update(position=prev.position)
    return _render_updated(request)


@login_required
@user_passes_test(staff_required)
@require_POST
def ext_move_down(request, pk: int):
    obj = get_object_or_404(Employee, pk=pk, user__is_staff=False)
    nxt = (
        Employee.objects
        .filter(user__is_staff=False, position__gt=obj.position)
        .order_by("position")
        .first()
    )
    if nxt:
        obj.position, nxt.position = nxt.position, obj.position
        Employee.objects.filter(pk=obj.pk).update(position=obj.position)
        Employee.objects.filter(pk=nxt.pk).update(position=nxt.position)
    return _render_updated(request)


# ---------------------------------------------------------------------------
#  Public registration (external users only, is_staff=False)
# ---------------------------------------------------------------------------

MAX_VERIFY_ATTEMPTS = 5


def _send_verification_email(pending: PendingRegistration) -> bool:
    """Return True if the email was sent successfully, False otherwise."""
    subject = "Код подтверждения — IMC Montan AI"
    body = (
        f"Здравствуйте!\n\n"
        f"Ваш код подтверждения: {pending.code}\n\n"
        f"Код действителен в течение 30 минут.\n"
        f"Если вы не запрашивали регистрацию, проигнорируйте это письмо.\n\n"
        f"С уважением,\nIMC Montan AI"
    )
    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [pending.user.email],
            fail_silently=False,
        )
        return True
    except Exception:
        logger.exception("Failed to send verification email to %s", pending.user.email)
        return False


@require_http_methods(["GET", "POST"])
def register_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "GET":
        form = ExternalRegistrationForm()
        return render(request, "core/register.html", {"form": form})

    form = ExternalRegistrationForm(request.POST)
    if not form.is_valid():
        return render(request, "core/register.html", {"form": form})

    try:
        with transaction.atomic():
            pending = form.save()
            if not _send_verification_email(pending):
                raise RuntimeError("email_send_failed")
    except RuntimeError:
        form.add_error(None, "Не удалось отправить письмо. Попробуйте позже.")
        return render(request, "core/register.html", {"form": form})

    return redirect("verify_email", token=pending.token)


@require_http_methods(["GET", "POST"])
def verify_view(request, token: str):
    if request.user.is_authenticated:
        return redirect("home")

    pending = PendingRegistration.objects.select_related("user").filter(token=token).first()
    if not pending:
        return render(request, "core/verify_email.html", {
            "error": "Ссылка для подтверждения недействительна.",
            "expired": True,
        })

    if pending.is_expired():
        pending.user.delete()
        return render(request, "core/verify_email.html", {
            "error": "Срок действия кода истёк. Пожалуйста, зарегистрируйтесь заново.",
            "expired": True,
        })

    if pending.attempts >= MAX_VERIFY_ATTEMPTS:
        pending.user.delete()
        return render(request, "core/verify_email.html", {
            "error": "Превышено количество попыток. Пожалуйста, зарегистрируйтесь заново.",
            "expired": True,
        })

    ctx = {"token": token, "email": pending.user.email, "can_resend": pending.can_resend()}

    if request.method == "GET":
        return render(request, "core/verify_email.html", ctx)

    entered_code = (request.POST.get("code") or "").strip()
    if entered_code == pending.code:
        user = pending.user
        user.is_active = True
        user.save(update_fields=["is_active"])
        pending.delete()
        return render(request, "core/verify_email.html", {"verified": True})

    pending.attempts += 1
    pending.save(update_fields=["attempts"])
    remaining = MAX_VERIFY_ATTEMPTS - pending.attempts
    ctx["error"] = f"Неверный код. Осталось попыток: {remaining}."
    ctx["can_resend"] = pending.can_resend()
    return render(request, "core/verify_email.html", ctx)


@require_POST
def resend_code_view(request, token: str):
    pending = PendingRegistration.objects.select_related("user").filter(token=token).first()
    if not pending or pending.is_expired():
        return redirect("register")

    if not pending.can_resend():
        return redirect("verify_email", token=token)

    pending.code = PendingRegistration.generate_code()
    pending.attempts = 0
    pending.last_sent_at = timezone.now()
    pending.save(update_fields=["code", "attempts", "last_sent_at"])
    _send_verification_email(pending)
    return redirect("verify_email", token=token)
