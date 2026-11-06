"""The in-repo stand-in identity provider (spec 008 T018-T019). Called directly: no network."""

import json
import time
from urllib.parse import urlencode

import jwt
import pytest
from jwt import PyJWKSet

from devtools.stand_in_idp import StandIn

ISSUER = "http://localhost:8090/default"
AUDIENCE = "convai-api"


@pytest.fixture(scope="module")
def idp():
    return StandIn(issuer=ISSUER, audience=AUDIENCE)


def token_request(idp, headers=None, **form):
    body = urlencode(form).encode()
    return idp.handle("POST", "/default/token", headers or {}, body)


def test_token_for_alice_passes_the_backends_checks(idp):
    status, _, body = token_request(idp, grant_type="password", username="alice", password="x")
    assert status == 200
    data = json.loads(body)
    assert data["token_type"] == "Bearer" and data["expires_in"] == 3600

    _, _, jwks_body = idp.handle("GET", "/default/jwks", {}, b"")
    jwk_set = PyJWKSet.from_dict(json.loads(jwks_body))
    token = data["access_token"]
    kid = jwt.get_unverified_header(token)["kid"]
    key = next(k for k in jwk_set.keys if k.key_id == kid)
    claims = jwt.decode(token, key.key, algorithms=["RS256"], audience=AUDIENCE, issuer=ISSUER, leeway=60)
    assert claims["sub"] == "alice"
    assert claims["aud"] == [AUDIENCE]
    assert claims["exp"] - claims["iat"] == 3600
    assert claims["exp"] > time.time()
    assert claims["ai_planning"] is True


def test_username_is_trimmed(idp):
    _, _, body = token_request(idp, grant_type="password", username="  jane  ", password="x")
    token = json.loads(body)["access_token"]
    assert jwt.decode(token, options={"verify_signature": False})["sub"] == "jane"


@pytest.mark.parametrize(
    "form",
    [
        {"grant_type": "client_credentials", "username": "alice"},
        {"grant_type": "password", "username": ""},
        {"grant_type": "password", "username": "   "},
        {"grant_type": "password"},
        {},
    ],
)
def test_bad_token_requests_are_refused(idp, form):
    status, _, body = token_request(idp, **form)
    assert status == 400
    assert json.loads(body) == {"error": "invalid_request"}


def test_discovery_document(idp):
    status, _, body = idp.handle("GET", "/default/.well-known/openid-configuration", {}, b"")
    doc = json.loads(body)
    assert status == 200
    assert doc == {
        "issuer": ISSUER,
        "token_endpoint": "http://localhost:8090/default/token",
        "jwks_uri": "http://localhost:8090/default/jwks",
    }


def test_responses_echo_the_origin_for_cors(idp):
    origin = {"Origin": "http://localhost:5173"}
    _, headers, _ = token_request(idp, headers=origin, grant_type="password", username="a")
    assert headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    status, headers, _ = idp.handle(
        "OPTIONS", "/default/token", {**origin, "Access-Control-Request-Headers": "content-type"}, b""
    )
    assert status == 204
    assert "POST" in headers["Access-Control-Allow-Methods"]
    assert headers["Access-Control-Allow-Headers"] == "content-type"


def test_unknown_path_is_404(idp):
    assert idp.handle("GET", "/nope", {}, b"")[0] == 404
