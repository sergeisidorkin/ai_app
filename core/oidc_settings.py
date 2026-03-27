def oidc_pkce_required(client_id):
    if not client_id:
        return True

    from oauth2_provider.models import get_application_model

    application_model = get_application_model()
    try:
        application = application_model.objects.only("client_type").get(client_id=client_id)
    except application_model.DoesNotExist:
        return True

    return application.client_type == application_model.CLIENT_PUBLIC
