"""TC-L03 (boot fails fast) and TC-E01 (latency smoke, P4 batch 4).

- L03: DATABASE_URL unset -> RuntimeError, no silent misuse (db.py get_database_url)
- E01: 200 sequential mock turns, p95 < 3s, no lost writes.
  Honest scope: sequential TestClient smoke (mock agent). 200-concurrent via
  k6/locust remains P5; this test does NOT claim concurrency coverage.
"""

import statistics
import time

import pytest

from app.db import get_database_url, normalize_database_url


def test_l03_boot_fails_fast_when_database_url_unset(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        get_database_url()


@pytest.mark.parametrize("url,expected", [
    ("postgresql://user@host/db", "postgresql+psycopg://user@host/db"),
    ("postgres://user@host/db", "postgresql+psycopg://user@host/db"),
    ("sqlite:////tmp/x.db", "sqlite:////tmp/x.db"),
])
def test_l03_postgres_url_normalized_to_psycopg(url, expected):
    assert normalize_database_url(url) == expected


def test_e01_p95_chat_latency_under_3s_mock_200_turns(client):
    # Characterization smoke: sequential mock turns. Concurrency is P5 (k6/locust).
    n = 200
    lat = []
    for i in range(n):
        sid = f"perf-{i % 10}"
        t0 = time.perf_counter()
        res = client.post("/api/chat", json={"session_id": sid, "message": f"turn {i}"})
        dt = time.perf_counter() - t0
        assert res.status_code == 200, f"turn {i} failed"
        lat.append(dt)
    lat.sort()
    p95 = lat[int(0.95 * len(lat)) - 1]
    assert p95 < 3.0, f"p95 {p95*1000:.0f}ms exceeds 3s"
    # No lost writes: each session holds 20 turns (user + assistant each)
    body = client.get("/api/chat/perf-0/history").json()
    assert len(body["messages"]) == 40
