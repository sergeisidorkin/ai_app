from django.urls import path, re_path

from oauth2_provider import views as oauth2_views

from .oidc import StaffAwareAuthorizationView


app_name = "oauth2_provider"


urlpatterns = [
    path("authorize/", StaffAwareAuthorizationView.as_view(), name="authorize"),
    path("token/", oauth2_views.TokenView.as_view(), name="token"),
    path("revoke_token/", oauth2_views.RevokeTokenView.as_view(), name="revoke-token"),
    path("introspect/", oauth2_views.IntrospectTokenView.as_view(), name="introspect"),
    re_path(
        r"^\.well-known/openid-configuration/?$",
        oauth2_views.ConnectDiscoveryInfoView.as_view(),
        name="oidc-connect-discovery-info",
    ),
    path(".well-known/jwks.json", oauth2_views.JwksInfoView.as_view(), name="jwks-info"),
    path("userinfo/", oauth2_views.UserInfoView.as_view(), name="user-info"),
    path("logout/", oauth2_views.RPInitiatedLogoutView.as_view(), name="rp-initiated-logout"),
]
