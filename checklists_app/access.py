from policy_app.models import ADMIN_GROUP


def user_can_sort_checklists(user):
    if not user or not getattr(user, "is_authenticated", False) or not getattr(user, "is_staff", False):
        return False
    employee = getattr(user, "employee_profile", None)
    return (
        getattr(employee, "role", "") == ADMIN_GROUP
        or user.groups.filter(name=ADMIN_GROUP).exists()
    )
