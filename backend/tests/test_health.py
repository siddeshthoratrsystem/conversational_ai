"""Health check (RTM TC-E02): GET /api/health -> {"status": "ok"}."""


def test_health_reports_ok(client):
    r = client.get("/api/health")

    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
