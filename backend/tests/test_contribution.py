"""Contribution action: seed, money figures, rules and the contribution service (spec 011)."""

import json
from decimal import Decimal

import pytest

from app.actions import contribution as c


# --- T004: demo payroll seed -------------------------------------------------------------

def _write(tmp_path, data):
    path = tmp_path / "payroll.json"
    path.write_text(data if isinstance(data, str) else json.dumps(data))
    return path


GOOD = {
    "currency": "USD",
    "annual_salary": 100000,
    "employer_match": {"match_pct": 100, "cap_pct_of_pay": 5},
    "starting_contribution_pct": 5,
}


def test_shipped_seed_values():
    seed = c.load_seed()
    assert seed.annual_salary == Decimal(100000)
    assert seed.match_pct == Decimal(100)
    assert seed.cap_pct == Decimal(5)
    assert seed.starting_pct == 5
    assert seed.currency == "USD"


def test_seed_missing_file_is_unavailable(tmp_path):
    with pytest.raises(c.SeedUnavailable):
        c.load_seed(tmp_path / "nope.json")


@pytest.mark.parametrize(
    "bad",
    [
        "not json at all",
        {**GOOD, "annual_salary": 0},
        {**GOOD, "annual_salary": -5},
        {**GOOD, "annual_salary": "100000"},
        {**GOOD, "employer_match": {"match_pct": 101, "cap_pct_of_pay": 5}},
        {**GOOD, "employer_match": {"match_pct": 100, "cap_pct_of_pay": -1}},
        {**GOOD, "employer_match": {"match_pct": 100}},
        {**GOOD, "starting_contribution_pct": 51},
        {**GOOD, "starting_contribution_pct": -1},
        [1, 2, 3],
    ],
)
def test_seed_invalid_file_is_unavailable(tmp_path, bad):
    with pytest.raises(c.SeedUnavailable):
        c.load_seed(_write(tmp_path, bad))


def test_seed_valid_custom_file_loads(tmp_path):
    seed = c.load_seed(_write(tmp_path, GOOD))
    assert seed.starting_pct == 5


# --- T005: money figures --------------------------------------------------------------------

@pytest.fixture
def seed():
    return c.load_seed()


def test_monthly_pay(seed):
    assert c.monthly_pay(seed) == Decimal("8333.33")


def test_increase_to_8_percent(seed):
    s = c.summarize(seed, current_pct=5, new_pct=8)
    assert (s.contribution_before, s.contribution_after, s.contribution_diff) == (
        Decimal("416.67"),
        Decimal("666.67"),
        Decimal("250.00"),
    )
    # The match is capped at 5%, so it does not move.
    assert (s.match_before, s.match_after, s.match_diff) == (
        Decimal("416.67"),
        Decimal("416.67"),
        Decimal("0.00"),
    )


def test_decrease_to_3_percent(seed):
    s = c.summarize(seed, current_pct=5, new_pct=3)
    assert (s.contribution_before, s.contribution_after, s.contribution_diff) == (
        Decimal("416.67"),
        Decimal("250.00"),
        Decimal("-166.67"),
    )
    assert (s.match_before, s.match_after, s.match_diff) == (
        Decimal("416.67"),
        Decimal("250.00"),
        Decimal("-166.67"),
    )


def test_rounding_is_half_up_from_exact_values(seed):
    # 5% -> 4%: the exact difference is 83.3333..., so 83.33. Subtracting the rounded figures
    # (416.67 - 333.33) would give 83.34, which FR-019 says must not happen.
    s = c.summarize(seed, current_pct=5, new_pct=4)
    assert s.contribution_diff == Decimal("-83.33")
    assert s.match_diff == Decimal("-83.33")


# --- T018: rules and the contribution service -------------------------------------------------

from datetime import datetime, timedelta, timezone  # noqa: E402

from sqlalchemy.orm import Session  # noqa: E402

from app import models  # noqa: E402
from app.actions import gate  # noqa: E402

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture
def service(db, seed):
    return c.DemoContributionService(db, seed)


def make_action(service, seed, **settings):
    return c.ContributionChange(service, seed, gate.GateSettings(**settings))


def test_current_rate_is_the_seed_rate_until_a_change(service):
    assert service.current_rate("alice") == 5


def test_rule_accepts_the_whole_range(service, seed):
    action = make_action(service, seed)
    for rate in (0, 1, 4, 6, 49, 50):
        assert action.check("alice", action.parse({"new_rate_pct": rate})) == {"current_rate_pct": 5}


@pytest.mark.parametrize(
    "rate, reason",
    [
        (51, "out_of_range"),
        (-1, "out_of_range"),
        (100, "out_of_range"),
        (8.5, "not_whole_pct"),
        (5, "same_as_current"),
        (5.0, "same_as_current"),
    ],
)
def test_rule_refuses(service, seed, rate, reason):
    action = make_action(service, seed)
    with pytest.raises(gate.GateRefusal) as refused:
        action.check("alice", action.parse({"new_rate_pct": rate}))
    assert refused.value.reason == reason


@pytest.mark.parametrize(
    "params",
    [{}, {"new_rate_pct": "8"}, {"new_rate_pct": None}, {"new_rate_pct": True}, {"rate": 8},
     {"new_rate_pct": 8, "extra": 1}, "8", None],
)
def test_parse_refuses_missing_unknown_or_non_numeric_params(service, seed, params):
    action = make_action(service, seed)
    with pytest.raises(gate.GateRefusal) as refused:
        action.parse(params)
    assert refused.value.reason == "invalid_params"


def test_range_follows_the_settings(service, seed):
    action = make_action(service, seed, min_pct=2, max_pct=10)
    assert action.check("alice", action.parse({"new_rate_pct": 10}))
    for rate, reason in ((11, "out_of_range"), (1, "out_of_range")):
        with pytest.raises(gate.GateRefusal) as refused:
            action.check("alice", action.parse({"new_rate_pct": rate}))
        assert refused.value.reason == reason


# --- T019: confirmation token ---------------------------------------------------------------------

def stage(db, user="alice", session_id="s1", rate=8):
    if db.get(models.Session, session_id) is None:
        db.add(models.Session(id=session_id, user_id=user))
        db.flush()
    pending = models.PendingAction(
        user_id=user,
        session_id=session_id,
        action_type="contribution_change",
        params={"new_rate_pct": rate},
        snapshot={"current_rate_pct": 5},
        status="confirmed",
        staged_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    db.add(pending)
    db.flush()
    return pending


def test_valid_token_applies_the_change(db, service):
    token = gate.issue_token(db, stage(db))
    assert service.apply_change("alice", 8, token) == 8
    assert service.current_rate("alice") == 8
    assert db.get(models.Contribution, "alice").rate_pct == 8


def test_reused_token_is_refused_and_the_rate_changes_once(db, service):
    token = gate.issue_token(db, stage(db))
    service.apply_change("alice", 8, token)
    with pytest.raises(gate.GateRefusal) as refused:
        service.apply_change("alice", 9, token)
    assert refused.value.reason == "already_handled"
    assert service.current_rate("alice") == 8


def test_token_for_another_participant_is_refused(db, service):
    token = gate.issue_token(db, stage(db, user="alice"))
    with pytest.raises(gate.GateRefusal) as refused:
        service.apply_change("bob", 8, token)
    assert refused.value.reason == "token_invalid"
    assert db.get(models.Contribution, "bob") is None
    assert db.get(models.Contribution, "alice") is None


def test_a_wrong_token_is_refused(db, service):
    pending = stage(db)
    gate.issue_token(db, pending)
    forged = gate.ConfirmationToken("forged", pending.id, "alice", "s1")
    with pytest.raises(gate.GateRefusal) as refused:
        service.apply_change("alice", 8, forged)
    assert refused.value.reason == "token_invalid"
    assert db.get(models.Contribution, "alice") is None


def test_only_the_hash_of_the_token_is_stored(db):
    import hashlib

    pending = stage(db)
    token = gate.issue_token(db, pending)
    db.commit()
    db.refresh(pending)
    assert pending.token_hash == hashlib.sha256(token.raw.encode()).hexdigest()
    assert token.raw not in {str(v) for v in vars(pending).values()}
    assert len(token.raw) >= 32


def test_each_participants_rate_is_their_own(db, service):
    service.apply_change("alice", 8, gate.issue_token(db, stage(db, "alice", "s1")))
    assert service.current_rate("alice") == 8
    assert service.current_rate("bob") == 5
