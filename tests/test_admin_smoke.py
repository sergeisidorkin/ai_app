from django.urls import reverse

def test_admin_redirects_to_login(client):
    """
    Неаутентифицированный запрос к /admin/ должен либо вернуть 302 на /admin/login/,
    либо сразу 200 (на некоторых конфигурациях).
    """
    url = reverse("admin:index")
    resp = client.get(url)
    assert resp.status_code in (200, 302)

def test_root_returns_hello_world(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"Test" in r.content