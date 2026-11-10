"""Contribution policy: seed, money figures and rules (spec 011, ported by T020)."""

import json
from decimal import Decimal

import pytest

from wealth_agent.actions import config
from wealth_agent.actions.contribution_service import DemoContributionService
from wealth_agent.actions.policies import contribution_policy as c
from wealth_agent.actions import gate


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


# --- rules -------------------------------------------------

@pytest.fixture
def conn(engine):
    with engine.connect() as connection:
        yield connection


@pytest.fixture
def service(conn, seed):
    return DemoContributionService(conn, seed)


def make_action(service, seed, **settings):
    return c.ContributionPolicy(service, seed, config.GateSettings(**settings))


def test_the_shipped_seed_is_in_the_agent_package():
    from pathlib import Path

    assert c.SEED_PATH == Path(c.__file__).resolve().parents[2] / "data" / "payroll.json"
    assert c.SEED_PATH.exists()


def test_8_5_is_always_not_whole_pct_whatever_the_environment(service, seed, monkeypatch):
    monkeypatch.setenv("CONTRIBUTION_WHOLE_PCT_ONLY", "false")
    action = make_action(service, seed)
    with pytest.raises(gate.GateRefusal) as refused:
        action.check("alice", action.parse({"new_rate_pct": 8.5}))
    assert refused.value.reason == "not_whole_pct"


def test_the_policy_is_registered_in_policies(service, seed):
    from wealth_agent.actions.policies import POLICIES

    assert "contribution_change" in POLICIES


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
