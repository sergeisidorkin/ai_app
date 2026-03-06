from django.urls import path

from .views import profile_view, profile_edit, avatar_upload, avatar_delete, profile_delete

urlpatterns = [
    path("", profile_view, name="user_profile"),
    path("edit/", profile_edit, name="user_profile_edit"),
    path("avatar/", avatar_upload, name="user_profile_avatar"),
    path("avatar/delete/", avatar_delete, name="user_profile_avatar_delete"),
    path("delete/", profile_delete, name="user_profile_delete"),
]
