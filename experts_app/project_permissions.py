"""Каталог прав в проекте, которые даёт специальность при назначении на позицию в Реестре проектов."""

PROJECT_COORDINATOR_SPECIALTY = "Координатор"
PROJECT_MANAGER_SPECIALTY = "Руководитель проекта"
PROJECT_DIRECTOR_SPECIALTY = "Директор"

PERM_VIEW_PROJECT = "view_project"
PERM_VIEW_REPORTS = "view_reports"
PERM_UPLOAD_FULL_REPORT = "upload_full_report"
PERM_UPLOAD_FREE_SECTIONS = "upload_free_sections"
PERM_REVIEW_KP = "review_kp"
PERM_REVIEW_RP = "review_rp"
PERM_CHECKLIST_APPROVE = "checklist_approve"
PERM_NEXTCLOUD_EDITOR = "nextcloud_editor"
PERM_WORKTIME_AUTO = "worktime_auto"
PERM_EXECUTOR_LOCK = "executor_lock"

PROJECT_PERMISSIONS = (
    (PERM_VIEW_PROJECT, "Видеть проект в Реестре, Исполнителях и Чек-листах (на чтение)"),
    (PERM_VIEW_REPORTS, "Видеть отчёты проекта"),
    (PERM_UPLOAD_FULL_REPORT, "Загружать и отправлять итоговый отчёт"),
    (PERM_UPLOAD_FREE_SECTIONS, "Загружать разделы без направления экспертизы"),
    (PERM_REVIEW_KP, "Проверка отчёта на шаге КП"),
    (PERM_REVIEW_RP, "Проверка отчёта на шаге РП"),
    (PERM_CHECKLIST_APPROVE, "Согласование запросов информации и правка всех разделов в Чек-листах"),
    (PERM_NEXTCLOUD_EDITOR, "Редактор рабочей папки проекта в Nextcloud"),
    (PERM_WORKTIME_AUTO, "Автоназначение проекта в Рабочем времени"),
    (PERM_EXECUTOR_LOCK, "Смена исполнителя по правилам руководителя проекта"),
)
PROJECT_PERMISSION_CODES = tuple(code for code, _label in PROJECT_PERMISSIONS)

DEFAULT_PROJECT_PERMISSIONS = {
    PROJECT_COORDINATOR_SPECIALTY: (
        PERM_VIEW_PROJECT,
        PERM_VIEW_REPORTS,
        PERM_UPLOAD_FULL_REPORT,
        PERM_UPLOAD_FREE_SECTIONS,
        PERM_REVIEW_KP,
        PERM_NEXTCLOUD_EDITOR,
        PERM_EXECUTOR_LOCK,
    ),
    PROJECT_MANAGER_SPECIALTY: (
        PERM_VIEW_PROJECT,
        PERM_VIEW_REPORTS,
        PERM_UPLOAD_FULL_REPORT,
        PERM_REVIEW_RP,
        PERM_CHECKLIST_APPROVE,
        PERM_NEXTCLOUD_EDITOR,
        PERM_WORKTIME_AUTO,
        PERM_EXECUTOR_LOCK,
    ),
}


def normalize_project_permissions(values) -> list[str]:
    selected = set(values or [])
    return [code for code in PROJECT_PERMISSION_CODES if code in selected]
