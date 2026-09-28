"""Порядок проверок отчёта: ИИ и ручные шаги РН, КП, РП."""

from __future__ import annotations

REVIEW_AI = "ai"
REVIEW_RN = "rn"
REVIEW_KP = "kp"
REVIEW_RP = "rp"
REVIEW_DONE = "done"
REVIEW_PHASE_REVIEW = "review"
REVIEW_PHASE_REWORK = "rework"

REVIEW_ORDER_CODES = (REVIEW_AI, REVIEW_RN, REVIEW_KP, REVIEW_RP)
MANUAL_REVIEW_CODES = (REVIEW_RN, REVIEW_KP, REVIEW_RP)
REVIEW_STEP_LABELS = {
    REVIEW_AI: "ИИ",
    REVIEW_RN: "РН",
    REVIEW_KP: "КП",
    REVIEW_RP: "РП",
}
REVIEW_ORDER_FORM_LABELS = {
    REVIEW_AI: "Искусственный интеллект (ИИ)",
    REVIEW_RN: "Руководитель направления (РН)",
    REVIEW_KP: "Координатор проекта (КП)",
    REVIEW_RP: "Руководитель проекта (РП)",
}
MANUAL_STATUS_LABELS = {
    REVIEW_AI: ("На проверке ИИ", "В работе после ИИ"),
    REVIEW_RN: ("На проверке РН", "В работе после РН"),
    REVIEW_KP: ("На проверке КП", "В работе после КП"),
    REVIEW_RP: ("На проверке РП", "В работе после РП"),
}


class ReviewOrderError(ValueError):
    pass


def normalize_review_order(steps) -> list[str]:
    cleaned = []
    for step in steps or []:
        code = str(step or "").strip()
        if code not in REVIEW_ORDER_CODES:
            raise ReviewOrderError("Неизвестный шаг порядка проверки.")
        if code in cleaned:
            raise ReviewOrderError("Шаг порядка указан дважды.")
        cleaned.append(code)
    if not cleaned:
        raise ReviewOrderError("Укажите порядок проверки.")
    if REVIEW_AI in cleaned and cleaned[0] != REVIEW_AI:
        raise ReviewOrderError("ИИ может быть только первым шагом или быть выключен.")
    return cleaned


def format_review_order(steps) -> str:
    try:
        cleaned = normalize_review_order(steps)
    except ReviewOrderError:
        cleaned = [code for code in (steps or []) if code in REVIEW_STEP_LABELS]
    if not cleaned:
        return "—"
    return " → ".join(REVIEW_STEP_LABELS[code] for code in cleaned)


def manual_steps(chain) -> list[str]:
    return [step for step in chain if step in MANUAL_REVIEW_CODES]


def next_manual_step(chain, step: str) -> str:
    steps = manual_steps(chain)
    if step not in steps:
        return ""
    index = steps.index(step)
    if index + 1 >= len(steps):
        return ""
    return steps[index + 1]


def _rule_rank(rule) -> tuple[int, int, int]:
    section_score = 1 if (getattr(rule, "section_id", None) or getattr(rule, "is_full_report", False)) else 0
    product_score = 1 if getattr(rule, "product_id", None) else 0
    expertise_score = 1 if getattr(rule, "expertise_dir_id", None) else 0
    return section_score, product_score, expertise_score


def most_specific_check_rule(upload, rules=None):
    from .report_macro_runner import matching_check_rules

    matched = matching_check_rules(upload, rules)
    if not matched:
        return None
    return min(
        matched,
        key=lambda rule: (
            -_rule_rank(rule)[0],
            -_rule_rank(rule)[1],
            -_rule_rank(rule)[2],
            int(getattr(rule, "position", 0) or 0),
            int(getattr(rule, "pk", 0) or 0),
        ),
    )


def review_chain_for_upload(upload, rules=None) -> list[str]:
    rule = most_specific_check_rule(upload, rules)
    if rule is None:
        return [REVIEW_AI]
    stored = getattr(rule, "review_order", None)
    if not stored:
        return [REVIEW_AI]
    try:
        return normalize_review_order(stored)
    except ReviewOrderError:
        return [REVIEW_AI]


def passed_step_status(step: str, chain) -> str:
    """Пройденный шаг: «Сдан …», последний в цепочке — «Согласован …»."""
    label = REVIEW_STEP_LABELS.get(step, "")
    steps = list(chain or [])
    later = steps[steps.index(step) + 1:] if step in steps else []
    prefix = "Сдан" if later else "Согласован"
    return f"{prefix} {label}".strip()


def manual_status_label(step: str, phase: str) -> str:
    labels = MANUAL_STATUS_LABELS.get(step)
    if not labels:
        return ""
    if phase == REVIEW_PHASE_REWORK:
        return labels[1]
    return labels[0]


def sync_review_after_check(upload) -> None:
    """После автопроверки открыть первый ручной шаг, если порог пройден."""
    from django.utils import timezone

    from .models import PerformerReportUpload
    from .report_submission import report_launches_accepted

    if (getattr(upload, "check_status", "") or "") != PerformerReportUpload.CheckStatus.DONE:
        return
    chain = review_chain_for_upload(upload)
    if REVIEW_AI not in chain:
        return
    now = getattr(upload, "checked_at", None) or timezone.now()
    if upload.review_step or upload.review_phase:
        upload.review_step = ""
        upload.review_phase = ""
        upload.save(update_fields=["review_step", "review_phase"])
    from .models import ReportReviewEntry

    if not report_launches_accepted(upload):
        if not upload.review_entries.filter(step=REVIEW_AI, phase=REVIEW_PHASE_REWORK).exists():
            ReportReviewEntry.objects.create(
                upload=upload,
                step=REVIEW_AI,
                phase=REVIEW_PHASE_REWORK,
            )
        return
    steps = manual_steps(chain)
    if not steps or upload.review_entries.exists():
        return
    ReportReviewEntry.objects.create(
        upload=upload,
        step=steps[0],
        phase=REVIEW_PHASE_REVIEW,
    )


def upload_org_direction_ids(upload) -> set[int]:
    from .models import Performer

    ids = set()
    performer = getattr(upload, "performer", None)
    section = getattr(performer, "typical_section", None) if performer is not None else None
    direction_id = getattr(section, "expertise_direction_id", None)
    if direction_id:
        ids.add(direction_id)
    if ids and not getattr(upload, "is_all_sections", False) and not getattr(upload, "is_full_report", False):
        return ids
    qs = Performer.objects.filter(
        registration_id=upload.registration_id,
        asset_name=getattr(upload, "asset_name", "") or "",
    )
    if not getattr(upload, "is_full_report", False):
        qs = qs.filter(executor=getattr(upload, "executor", "") or "")
    ids.update(
        qs.exclude(typical_section__expertise_direction_id=None)
        .values_list("typical_section__expertise_direction_id", flat=True)
    )
    return {int(item) for item in ids if item}


def user_matches_review_step(user, upload, step: str) -> bool:
    from .report_access import (
        _employee_of,
        _normalize,
        is_admin_user,
        is_direction_head_user,
        is_project_manager_of,
    )
    from .models import Performer

    if step in MANUAL_REVIEW_CODES and is_admin_user(user):
        return True
    if step == REVIEW_RP:
        return is_project_manager_of(user, getattr(upload, "registration", None))
    if step == REVIEW_KP:
        employee = _employee_of(user)
        registration = getattr(upload, "registration", None)
        if not employee or not registration:
            return False
        prs = _normalize(getattr(employee, "formatted_prs_id", "") or "")
        name = _normalize(Performer.employee_full_name(employee))
        if prs and _normalize(getattr(registration, "project_coordinator_prs_id", "")) == prs:
            return True
        return bool(name) and _normalize(getattr(registration, "project_coordinator", "")) == name
    if step == REVIEW_RN:
        if not is_direction_head_user(user):
            return False
        employee = _employee_of(user)
        department_id = getattr(employee, "department_id", None)
        if not department_id:
            return False
        return int(department_id) in upload_org_direction_ids(upload)
    return False


def entry_status(entry) -> str:
    from .report_submission import REPORT_STATUS_AGREED

    phase = getattr(entry, "phase", "") or ""
    step = getattr(entry, "step", "") or ""
    if phase == "agreed":
        step = step or getattr(getattr(entry, "basis_entry", None), "step", "") or ""
        if step:
            return passed_step_status(step, [step])
        return REPORT_STATUS_AGREED
    if getattr(entry, "settled", False) and phase == REVIEW_PHASE_REVIEW and step:
        upload = getattr(entry, "upload", None)
        return passed_step_status(step, review_chain_for_upload(upload) if upload is not None else [step])
    if (
        phase == REVIEW_PHASE_REVIEW
        and step
        and (getattr(entry, "review_file_name", "") or getattr(entry, "review_cloud_path", ""))
        and int(getattr(entry, "comment_count", 0) or 0) > 0
    ):
        label = REVIEW_STEP_LABELS.get(step, "")
        return f"Проверен {label}".strip()
    return manual_status_label(step, phase)


def latest_open_entry(upload):
    """Текущая строка шага слота, в которую ещё можно загрузить файл."""
    from .models import ReportReviewEntry

    slot_ids = _slot_upload_ids(upload)
    return (
        ReportReviewEntry.objects
        .filter(upload_id__in=slot_ids, settled=False)
        .exclude(phase="agreed")
        .order_by("-created_at", "-id")
        .first()
    )


def _slot_upload_ids(upload) -> list[int]:
    from .models import PerformerReportUpload

    qs = PerformerReportUpload.objects.filter(registration_id=upload.registration_id)
    if upload.is_full_report:
        qs = qs.filter(is_full_report=True, asset_name=upload.asset_name or "")
    elif upload.is_all_sections:
        qs = qs.filter(
            is_all_sections=True,
            is_full_report=False,
            executor=upload.executor or "",
            asset_name=upload.asset_name or "",
        )
    elif upload.performer_id:
        qs = qs.filter(performer_id=upload.performer_id, is_all_sections=False, is_full_report=False)
    else:
        qs = qs.filter(pk=upload.pk)
    return list(qs.values_list("pk", flat=True))


def user_can_submit_review(user, upload) -> bool:
    entry = latest_open_entry(upload)
    if entry is None or entry.phase != REVIEW_PHASE_REVIEW or entry.step not in MANUAL_REVIEW_CODES:
        return False
    return user_matches_review_step(user, entry.upload, entry.step)
