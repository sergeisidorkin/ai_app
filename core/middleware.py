from django.conf import settings
from django.shortcuts import redirect, resolve_url

class EnforceLoginMiddleware:
    """
    Если пользователь не аутентифицирован — пускаем только на LOGIN_URL и статические ресурсы.
    Всё остальное (включая /admin) — редиректим на страницу входа.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Уже авторизован — пропускаем
        if request.user.is_authenticated:
            return self.get_response(request)

        path = request.path or "/"
        login_url = resolve_url(getattr(settings, "LOGIN_URL", "login"))

        # Разрешённые точные пути (login, logout может быть полезен)
        allowed_exact = {
            login_url,
            "/accounts/login/",
            "/accounts/logout/",
        }

        # Разрешённые префиксы (статика, health и т.п.)
        allowed_prefixes = (
            getattr(settings, "STATIC_URL", "/static/"),
        ) + tuple(getattr(settings, "ENFORCE_LOGIN_EXEMPT", ()))

        # Разрешаем доступ, если путь подпадает под исключения
        if path in allowed_exact or any(path.startswith(pfx) for pfx in allowed_prefixes):
            return self.get_response(request)

        # Иначе — редирект на страницу логина с возвратом обратно (next)
        return redirect(f"{login_url}?next={path}")