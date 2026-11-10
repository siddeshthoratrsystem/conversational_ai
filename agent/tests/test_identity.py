"""Token checks in the agent, porting the token cases of backend/tests/test_auth.py (spec 011, T017)."""

import base64
import json
import logging
import time

import jwt
import pytest
from conftest import AUDIENCE, ISSUER

from wealth_agent.actions.identity import verify_participant


def _b64(data):
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def check(token_or_header, as_header=False):
    header = token_or_header if as_header else f"Bearer {token_or_header}"
    return verify_participant(header)


def test_a_valid_token_gives_the_participant_and_claims(verifier, make_token):
    result = check(make_token("alice", name="Alice"))
    assert result.failure is None
    assert result.participant.id == "alice"
    assert result.participant.claims["name"] == "Alice"
    assert result.participant.claims["ai_planning"] is True


@pytest.mark.parametrize("scheme", ["Bearer", "bearer", "BEARER"])
def test_the_scheme_is_case_insensitive(verifier, make_token, scheme):
    assert verify_participant(f"{scheme} {make_token()}").participant.id == "alice"


@pytest.mark.parametrize(
    "header",
    [None, "", "Basic abc", "Bearer", "Bearer ", "Bearer a b", "abc", "Bearer  x"],
    ids=["none", "empty", "basic", "no-token", "blank-token", "two-parts", "no-scheme", "double-space"],
)
def test_a_missing_empty_or_non_bearer_header_is_sign_in_token_missing(verifier, header):
    result = verify_participant(header)
    assert result.participant is None
    assert result.failure == "sign_in_token_missing"


def test_an_expired_token_is_sign_in_token_expired(verifier, make_token):
    result = check(make_token(exp=int(time.time()) - 3600))
    assert (result.participant, result.failure) == (None, "sign_in_token_expired")


def test_a_token_just_past_expiry_is_accepted_within_the_leeway(verifier, make_token):
    assert check(make_token(exp=int(time.time()) - 30)).participant.id == "alice"


def test_a_token_beyond_the_leeway_is_expired(verifier, make_token):
    assert check(make_token(exp=int(time.time()) - 61 - 5)).failure == "sign_in_token_expired"


def test_wrong_issuer_is_invalid(verifier, make_token):
    assert check(make_token(iss="https://evil.test")).failure == "sign_in_token_invalid"


def test_wrong_audience_is_invalid(verifier, make_token):
    assert check(make_token(aud="someone-else")).failure == "sign_in_token_invalid"


def test_a_shared_secret_token_is_invalid(verifier):
    now = int(time.time())
    claims = {"iss": ISSUER, "aud": AUDIENCE, "exp": now + 300, "sub": "alice"}
    token = jwt.encode(claims, "x" * 32, algorithm="HS256", headers={"kid": "test-key"})
    assert check(token).failure == "sign_in_token_invalid"


def test_an_unsigned_token_is_invalid(verifier):
    now = int(time.time())
    claims = {"iss": ISSUER, "aud": AUDIENCE, "exp": now + 300, "sub": "alice"}
    assert check(f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64(claims)}.").failure == "sign_in_token_invalid"


def test_a_missing_sub_is_invalid(verifier, make_token):
    assert check(make_token(sub=None)).failure == "sign_in_token_invalid"


def test_an_empty_sub_is_invalid(verifier, make_token):
    assert check(make_token(sub="")).failure == "sign_in_token_invalid"


def test_a_bad_signature_is_invalid(verifier, make_token, wrong_key):
    assert check(make_token(key=wrong_key)).failure == "sign_in_token_invalid"


def test_an_unknown_key_id_is_invalid(verifier, make_token):
    assert check(make_token(headers={"kid": "nobody"})).failure == "sign_in_token_invalid"


@pytest.mark.parametrize("token", ["abc", "a.b.c", "....", "x" * 50])
def test_a_malformed_token_is_invalid(verifier, token):
    result = check(token)
    assert (result.participant, result.failure) == (None, "sign_in_token_invalid")


def test_an_unreachable_key_set_with_no_cached_keys_is_invalid(verifier, keys, make_token):
    keys.fail = True
    result = check(make_token())
    assert (result.participant, result.failure) == (None, "sign_in_token_invalid")


def test_an_unreachable_key_set_uses_the_last_good_keys(verifier, keys, make_token):
    assert check(make_token()).participant is not None  # fetches and remembers the key set
    keys.jwk_set_cache.lifespan = 0.0001  # the cache expires...
    time.sleep(0.01)
    keys.fail = True  # ...and the address is down
    assert check(make_token("bob")).participant.id == "bob"
    assert keys.fetches >= 2


def test_verifying_never_raises(verifier):
    for header in (None, "", "Bearer", "Bearer \x00\x00", "Bearer " + "9" * 5000):
        assert verify_participant(header).participant is None


def test_the_token_never_appears_in_logs(verifier, make_token, wrong_key, caplog):
    tokens = [make_token(key=wrong_key), make_token(exp=int(time.time()) - 3600), "SECRET.TOKEN.VALUE"]
    with caplog.at_level(logging.DEBUG):
        for token in tokens:
            check(token)
    for token in tokens:
        assert token not in caplog.text
