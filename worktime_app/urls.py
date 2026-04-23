from django.urls import path

from . import views


urlpatterns = [
    path("partial/", views.worktime_partial, name="worktime_partial"),
    path("partial/personal/", views.personal_worktime_partial, name="personal_worktime_partial"),
    path("csv-upload/", views.worktime_csv_upload, name="worktime_csv_upload"),
    path("csv-download/", views.worktime_csv_download, name="worktime_csv_download"),
    path("personal/add-row/", views.personal_worktime_row_form, name="personal_worktime_row_form"),
    path("save/", views.worktime_save, name="worktime_save"),
]
