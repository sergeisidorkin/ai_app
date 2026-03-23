from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import ExternalSMTPAccountForm
from .models import ExternalSMTPAccount
from .services import SMTPServiceError, send_test_email, test_smtp_connection


def _home_tab(tab: str) -> str:
    return reverse("home") + f"#{tab}"


def _render_connections_or_redirect(request):
    if request.headers.get("HX-Request") == "true":
        from onedrive_app.views import connections_partial as full_connections_partial

        return full_connections_partial(request)
    return redirect(_home_tab("connections"))


def _join_form_errors(form) -> str:
    return "; ".join(
        f"{field}: {'; '.join(errors)}"
        for field, errors in form.errors.items()
    )


def _build_account_from_request(request):
    existing_account = ExternalSMTPAccount.objects.filter(user=request.user).first()
    form = ExternalSMTPAccountForm(request.POST, instance=existing_account, user=request.user)
    if not form.is_valid():
        messages.error(request, f"Не удалось обработать SMTP-настройки. {_join_form_errors(form)}")
        return None
    return form.save(commit=False)


@login_required
@require_POST
def save_account(request):
    account = ExternalSMTPAccount.objects.filter(user=request.user).first()
    form = ExternalSMTPAccountForm(request.POST, instance=account, user=request.user)
    if form.is_valid():
        saved = form.save()
        messages.success(request, "Внешний SMTP-аккаунт сохранён.")
        if saved.use_for_notifications and not saved.is_active:
            messages.warning(request, "Подключение сохранено, но отключено и не будет использоваться для уведомлений.")
    else:
        messages.error(request, f"Не удалось сохранить SMTP-аккаунт. {_join_form_errors(form)}")
    return _render_connections_or_redirect(request)


@login_required
@require_POST
def test_account(request):
    account = _build_account_from_request(request)
    if account is None:
        return _render_connections_or_redirect(request)

    result = test_smtp_connection(account)
    if result["ok"]:
        messages.success(request, "SMTP-подключение успешно проверено.")
    else:
        messages.error(request, f"SMTP-подключение не удалось проверить: {result['error']}")
    return _render_connections_or_redirect(request)


@login_required
@require_POST
def send_test_email_view(request):
    account = _build_account_from_request(request)
    if account is None:
        return _render_connections_or_redirect(request)

    recipient_email = (request.user.email or "").strip()
    if not recipient_email:
        messages.error(request, "У текущего пользователя не указан email для тестового письма.")
        return _render_connections_or_redirect(request)

    try:
        result = send_test_email(account, recipient_email)
    except SMTPServiceError as exc:
        messages.error(request, str(exc))
        return _render_connections_or_redirect(request)

    messages.success(request, f"Тестовое письмо отправлено на {result['recipient_email']}.")
    return _render_connections_or_redirect(request)


@login_required
@require_POST
def disconnect_account(request):
    account = ExternalSMTPAccount.objects.filter(user=request.user).first()
    if account:
        account.is_active = False
        account.use_for_notifications = False
        account.save(update_fields=["is_active", "use_for_notifications", "updated_at"])
        messages.success(request, "Внешний SMTP-аккаунт отключён.")
    else:
        messages.info(request, "SMTP-подключение не было настроено.")
    return _render_connections_or_redirect(request)
