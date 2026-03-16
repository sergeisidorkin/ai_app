from django.urls import path

from . import views

urlpatterns = [
    path(
        "partial/<str:template_type>/",
        views.letter_template_partial,
        name="letter_template_partial",
    ),
    path(
        "save/<str:template_type>/",
        views.letter_template_save,
        name="letter_template_save",
    ),
    path(
        "reset/<str:template_type>/",
        views.letter_template_reset,
        name="letter_template_reset",
    ),
    path(
        "employees/search/",
        views.employees_search,
        name="letter_employees_search",
    ),
]
