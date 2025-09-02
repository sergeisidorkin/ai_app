# tests/test_start_page.py
from django.urls import reverse

def test_home_page_smoke(client, settings):
    url = reverse("home")
    resp = client.get(url, follow=False)

    # Разрешаем либо сразу 200, либо редирект (например, на логин)
    assert resp.status_code in (200, 301, 302)

    if resp.status_code in (301, 302):
        # Если станет приватной — допустим редирект на /accounts/login/ или /admin/login/
        location = resp.headers.get("Location", "")
        assert any(x in location for x in ("/accounts/login", "/admin/login", "/login"))
    else:
        # Если публичная — проверяем HTML и маркер
        assert "text/html" in resp.headers.get("Content-Type", "")
        content = resp.content
        assert b'data-testid="app-root"' in content or b'name="app-id"' in content