from django.urls import path

from . import views


urlpatterns = [
    path("save/", views.save_account, name="smtp_save_account"),
    path("test/", views.test_account, name="smtp_test_account"),
    path("send-test-email/", views.send_test_email_view, name="smtp_send_test_email"),
    path("disconnect/", views.disconnect_account, name="smtp_disconnect_account"),
]
