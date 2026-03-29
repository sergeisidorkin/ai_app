from __future__ import annotations

from django.conf import settings
from django.http import HttpResponseForbidden

from oauth2_provider.oauth2_validators import OAuth2Validator
from oauth2_provider.views import AuthorizationView


class IMCOAuth2Validator(OAuth2Validator):
    oidc_claim_scope = dict(OAuth2Validator.oidc_claim_scope)
    oidc_claim_scope.update(
        {
            "is_staff": "profile",
            "nextcloud_uid": "profile",
            "groups": "profile",
            "quota": "profile",
        }
    )

    def get_additional_claims(self):
        return {
            "name": lambda request: " ".join(
                part for part in [request.user.first_name, request.user.last_name] if part
            )
            or request.user.get_username(),
            "given_name": lambda request: (request.user.first_name or "").strip(),
            "family_name": lambda request: (request.user.last_name or "").strip(),
            "preferred_username": lambda request: request.user.get_username(),
            "email": lambda request: (request.user.email or "").strip(),
            "email_verified": lambda request: bool((request.user.email or "").strip()),
            "is_staff": lambda request: bool(request.user.is_staff),
            "nextcloud_uid": lambda request: f"ncstaff-{request.user.pk}",
            "groups": lambda request: list(request.user.groups.order_by("name").values_list("name", flat=True)),
            "quota": lambda request: "",
        }

    def get_claim_dict(self, request):
        claims = super().get_claim_dict(request)
        claims["sub"] = lambda r: f"django:{r.user.pk}"
        return claims


class StaffAwareAuthorizationView(AuthorizationView):
    def dispatch(self, request, *args, **kwargs):
        client_id = request.GET.get("client_id") or request.POST.get("client_id")
        staff_only_client_ids = set(getattr(settings, "OIDC_STAFF_ONLY_CLIENT_IDS", ()))

        if request.user.is_authenticated and client_id in staff_only_client_ids and not request.user.is_staff:
            return HttpResponseForbidden("This OIDC client is available only for staff users.")

        return super().dispatch(request, *args, **kwargs)
