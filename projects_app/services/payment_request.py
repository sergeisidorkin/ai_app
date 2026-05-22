from decimal import Decimal

from django.db import transaction

from projects_app.models import PaymentRequestCounter, Performer


def payment_request_sender_display(user):
    last_name = (getattr(user, "last_name", "") or "").strip()
    first_name = (getattr(user, "first_name", "") or "").strip()
    patronymic = (
        getattr(getattr(user, "employee_profile", None), "patronymic", "") or ""
    ).strip()
    if not last_name:
        return (getattr(user, "get_full_name", lambda: "")() or "").strip() or user.username

    initials = ""
    if first_name:
        initials += f"{first_name[0]}."
    if patronymic:
        initials += f"{patronymic[0]}."
    if initials:
        return f"{last_name} {initials}"
    return last_name


def payment_request_stage(performer):
    prepayment = performer.prepayment if performer.prepayment is not None else Decimal(0)
    if performer.advance_payment_request_sent_at is None and prepayment > 0:
        return "advance"
    if performer.final_payment_request_sent_at is None:
        return "final"
    return None


@transaction.atomic
def allocate_payment_request_number():
    counter, _created = PaymentRequestCounter.objects.select_for_update().get_or_create(
        pk=1,
        defaults={"last_number": 0},
    )
    counter.last_number += 1
    counter.save(update_fields=["last_number"])
    return counter.last_number


def payment_request_sender_for_row(performer):
    if (performer.final_payment_request_sender or "").strip():
        return performer.final_payment_request_sender
    if (performer.advance_payment_request_sender or "").strip():
        return performer.advance_payment_request_sender
    return ""
