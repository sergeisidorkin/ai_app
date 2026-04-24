from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from policy_app.models import DIRECTOR_GROUP

from .models import LetterTemplate
from .services import get_effective_template


VALID_TYPES = dict(LetterTemplate.TEMPLATE_TYPE_CHOICES)


def _format_employee_name(user):
    """Имя Фамилия for display."""
    first = (user.first_name or "").strip()
    last = (user.last_name or "").strip()
    if first and last:
        return f"{first} {last}"
    return first or last or user.username


def _cc_display_list(tpl):
    """Return list of CC recipient display names."""
    if not tpl or not tpl.pk:
        return []
    return [
        {"id": u.pk, "name": _format_employee_name(u)}
        for u in tpl.cc_recipients.select_related().all()
    ]


def _user_templates_list(template_type):
    """All user-specific templates for a given type (for superuser view)."""
    tpls = (
        LetterTemplate.objects
        .filter(template_type=template_type, user__isnull=False)
        .select_related("user")
        .prefetch_related("cc_recipients")
        .order_by("-updated_at")
    )
    result = []
    for t in tpls:
        result.append({
            "id": t.pk,
            "author": _format_employee_name(t.user),
            "subject": t.subject_template or "—",
            "body_html": t.body_html,
            "updated_at": t.updated_at,
            "cc": [
                _format_employee_name(u)
                for u in t.cc_recipients.all()
            ],
        })
    return result


def _shared_templates_queryset(template_type):
    return LetterTemplate.objects.filter(
        template_type=template_type,
        user__isnull=True,
    ).order_by("-updated_at", "-pk")


def _can_manage_shared_letter_templates(user):
    if not user.is_superuser:
        return False
    employee = getattr(user, "employee_profile", None)
    return getattr(employee, "role", "") != DIRECTOR_GROUP


def _save_shared_letter_template(*, template_type, subject, body_html):
    with transaction.atomic():
        tpl = _shared_templates_queryset(template_type).select_for_update().first()
        if tpl is None:
            return LetterTemplate.objects.create(
                template_type=template_type,
                user=None,
                subject_template=subject,
                body_html=body_html,
                is_default=True,
            )

        tpl.subject_template = subject
        tpl.body_html = body_html
        tpl.is_default = True
        tpl.save(update_fields=["subject_template", "body_html", "is_default", "updated_at"])
        (
            LetterTemplate.objects
            .filter(template_type=template_type, user__isnull=True, is_default=True)
            .exclude(pk=tpl.pk)
            .update(is_default=False)
        )
        return tpl


def _base_context(request, template_type, tpl, **extra):
    variables = LetterTemplate.TEMPLATE_VARIABLES.get(template_type, [])
    can_manage_shared_templates = _can_manage_shared_letter_templates(request.user)
    ctx = {
        "template": tpl,
        "template_type": template_type,
        "template_type_display": VALID_TYPES[template_type],
        "card_title": LetterTemplate.TEMPLATE_CARD_TITLES.get(template_type, ""),
        "variables": variables,
        "can_manage_shared_templates": can_manage_shared_templates,
        "cc_recipients": _cc_display_list(tpl),
    }
    if can_manage_shared_templates:
        ctx["user_templates"] = _user_templates_list(template_type)
    ctx.update(extra)
    return ctx


@login_required
@require_GET
def letter_template_partial(request, template_type):
    if template_type not in VALID_TYPES:
        return JsonResponse({"error": "invalid type"}, status=400)

    tpl = get_effective_template(template_type, request.user)
    user_has_custom = LetterTemplate.objects.filter(
        template_type=template_type, user=request.user
    ).exists()

    return render(request, "letters_app/template_card.html",
                  _base_context(request, template_type, tpl,
                                user_has_custom=user_has_custom))


@login_required
@require_POST
def letter_template_save(request, template_type):
    if template_type not in VALID_TYPES:
        return JsonResponse({"error": "invalid type"}, status=400)

    subject = request.POST.get("subject_template", "").strip()
    body_html = request.POST.get("body_html", "").strip()
    cc_ids = request.POST.getlist("cc_recipients[]")
    if not body_html:
        return JsonResponse({"error": "empty body"}, status=400)

    if _can_manage_shared_letter_templates(request.user):
        tpl = _save_shared_letter_template(
            template_type=template_type,
            subject=subject,
            body_html=body_html,
        )
    else:
        tpl, _created = LetterTemplate.objects.update_or_create(
            template_type=template_type,
            user=request.user,
            defaults={
                "subject_template": subject,
                "body_html": body_html,
                "is_default": False,
            },
        )

    from django.contrib.auth import get_user_model
    User = get_user_model()
    valid_ids = list(
        User.objects.filter(pk__in=cc_ids, employee_profile__isnull=False)
        .values_list("pk", flat=True)
    )
    tpl.cc_recipients.set(valid_ids)

    user_has_custom = LetterTemplate.objects.filter(
        template_type=template_type, user=request.user
    ).exists()

    return render(request, "letters_app/template_card.html",
                  _base_context(request, template_type, tpl,
                                user_has_custom=user_has_custom,
                                just_saved=True))


@login_required
@require_POST
def letter_template_reset(request, template_type):
    if template_type not in VALID_TYPES:
        return JsonResponse({"error": "invalid type"}, status=400)

    LetterTemplate.objects.filter(
        template_type=template_type, user=request.user
    ).delete()

    tpl = get_effective_template(template_type, request.user)

    return render(request, "letters_app/template_card.html",
                  _base_context(request, template_type, tpl,
                                user_has_custom=False))


@login_required
@require_GET
def employees_search(request):
    """Return employees matching query for CC autocomplete."""
    q = request.GET.get("q", "").strip()
    from users_app.models import Employee
    qs = Employee.objects.select_related("user").all()
    if q:
        from django.db.models import Q
        qs = qs.filter(
            Q(user__first_name__icontains=q)
            | Q(user__last_name__icontains=q)
            | Q(user__username__icontains=q)
        )
    results = []
    for emp in qs[:20]:
        u = emp.user
        results.append({
            "id": u.pk,
            "name": _format_employee_name(u),
        })
    return JsonResponse({"results": results})
