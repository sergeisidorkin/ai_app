from django.urls import path
from . import views

urlpatterns = [
    path("partial/", views.users_partial, name="users_partial"),
    path("create/", views.employee_form_create, name="emp_form_create"),
    path("<int:pk>/edit/", views.employee_form_edit, name="emp_form_edit"),
    path("<int:pk>/delete/", views.employee_delete, name="emp_delete"),
    path("<int:pk>/move-up/", views.employee_move_up, name="emp_move_up"),
    path("<int:pk>/move-down/", views.employee_move_down, name="emp_move_down"),
]
