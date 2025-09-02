# tests/test_health.py
def test_health_endpoint(client):
    resp = client.get("/health/")
    assert resp.status_code == 200