from django.urls import path

from . import views


urlpatterns = [
    path("partial/", views.worktime_partial, name="worktime_partial"),
    path("partial/personal/", views.personal_worktime_partial, name="personal_worktime_partial"),
    path("partial/personal/calendar-marks/", views.personal_worktime_calendar_marks, name="personal_worktime_calendar_marks"),
    path("csv-upload/", views.worktime_csv_upload, name="worktime_csv_upload"),
    path("csv-download/", views.worktime_csv_download, name="worktime_csv_download"),
    path("personal/add-row/", views.personal_worktime_row_form, name="personal_worktime_row_form"),
    path("personal/row-order/", views.personal_worktime_row_order, name="personal_worktime_row_order"),
    path("personal/row/<int:pk>/delete/", views.personal_worktime_row_delete, name="personal_worktime_row_delete"),
    path("personal/row/<int:pk>/move-up/", views.personal_worktime_row_move_up, name="personal_worktime_row_move_up"),
    path("personal/row/<int:pk>/move-down/", views.personal_worktime_row_move_down, name="personal_worktime_row_move_down"),
    path("save/", views.worktime_save, name="worktime_save"),
]
