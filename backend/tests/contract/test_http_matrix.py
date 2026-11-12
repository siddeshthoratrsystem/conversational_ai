"""TC-G07 (RTM 'All endpoints'): wrong HTTP methods are refused with 405, not silent 200s.

Part of the contract matrix (framework P1): negative classes in the 'Test scenarios'
sheet that the endpoint-specific suites do not already cover.
"""

import pytest
from fastapi.testclient import TestClient

from sqlalchemy.orm import Session

from app import models
from app.db import Session as Session_
from tests.builders import chat_turn

# (method, url) pairs that the endpoints do not implement
CASES = [
    ("PUT", "/api/chat"),
    ("DELETE", "/api/chat"),
    ("PATCH", "/api/chat"),
    ("POST", "/api/sessions"),
    ("DELETE", "/api/sessions"),
    ("PUT", "/api/health"),
]


@pytest.mark.parametrize("method,url", CASES)
def test_wrong_methods_return_405_not_200(client, method, url):
    res = client.request(method, url)

    assert res.status_code == 405, f"{method} {url} silently succeeded"


def test_feedback_endpoint_refuses_wrong_methods(client, engine):
    with Session_(engine) as db:
        message_id = chat_turn(db, "m2", "hi", "hello").id
    url = f"/api/messages/{message_id}/feedback"

    for method in ("GET", "PUT", "DELETE"):
        res = client.request(method, url)

        assert res.status_code == 405, f"{method} {url} silently succeeded"
