"""Settings and the start-up check (spec 011, T018): defaults, overrides and the timeout rules."""

import importlib.util
import logging
from pathlib import Path

import pytest

from wealth_agent.actions import config

BACKEND_AGENT = Path(__file__).resolve().parents[2] / "backend" / "app" / "agent.py"

SETTINGS_OK = {
    "OIDC_ISSUER": "https://idp.test/default",
    "OIDC_AUDIENCE": "convai-api",
    "OIDC_JWKS_URL": "https://idp.test/default/jwks",
    "DATABASE_URL": "postgresql://app:app@localhost/convai",
}


# --- settings ------------------------------------------------------------------------------------


def test_settings_defaults():
    s = config.load_settings({})
    assert s.expiry_seconds == 300
    assert s.confirm_replies == ("confirm",)
    assert s.cancel_replies == ("cancel",)
    assert (s.min_pct, s.max_pct) == (0, 50)
    assert s.stage_deadline_seconds == 50
    assert s.db_timeout_seconds == 3
    assert s.agent_timeout_seconds == 60


def test_settings_read_the_environment():
    s = config.load_settings(
        {
            "ACTION_EXPIRY_SECONDS": "10",
            "ACTION_CONFIRM_REPLIES": "confirm, yes",
            "ACTION_CANCEL_REPLIES": "cancel,stop",
            "CONTRIBUTION_MIN_PCT": "1",
            "CONTRIBUTION_MAX_PCT": "30",
            "ACTION_STAGE_DEADLINE_SECONDS": "20",
            "ACTION_DB_TIMEOUT_SECONDS": "2",
            "AGENT_TIMEOUT_SECONDS": "30",
        }
    )
    assert s.expiry_seconds == 10
    assert s.confirm_replies == ("confirm", "yes")
    assert s.cancel_replies == ("cancel", "stop")
    assert (s.min_pct, s.max_pct) == (1, 30)
    assert (s.stage_deadline_seconds, s.db_timeout_seconds, s.agent_timeout_seconds) == (20, 2, 30)


def test_settings_ignore_blank_values():
    s = config.load_settings({"ACTION_EXPIRY_SECONDS": "", "ACTION_CONFIRM_REPLIES": " "})
    assert s.expiry_seconds == 300
    assert s.confirm_replies == ("confirm",)


def test_the_whole_percentage_setting_is_gone():
    assert not hasattr(config.GateSettings(), "whole_pct_only")
    assert not hasattr(config.load_settings({"CONTRIBUTION_WHOLE_PCT_ONLY": "false"}), "whole_pct_only")


# --- startup_check ---------------------------------------------------------------------------------


def test_all_settings_present_enables_actions_with_no_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="wealth_agent.actions.config"):
        status = config.startup_check(SETTINGS_OK)
    assert status.enabled is True
    assert status.problems == ()
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


@pytest.mark.parametrize("missing", ["OIDC_ISSUER", "OIDC_AUDIENCE", "OIDC_JWKS_URL", "DATABASE_URL"])
def test_a_missing_setting_disables_actions_with_one_warning_naming_it(caplog, missing):
    env = {k: v for k, v in SETTINGS_OK.items() if k != missing}
    with caplog.at_level(logging.WARNING, logger="wealth_agent.actions.config"):
        status = config.startup_check(env)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert status.enabled is False
    assert len(warnings) == 1
    assert missing in warnings[0].getMessage()
    assert any(missing in p for p in status.problems)


def test_every_missing_setting_is_named_in_one_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="wealth_agent.actions.config"):
        status = config.startup_check({"OIDC_ISSUER": " "})
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert status.enabled is False and len(warnings) == 1
    for name in ("OIDC_ISSUER", "OIDC_AUDIENCE", "OIDC_JWKS_URL", "DATABASE_URL"):
        assert name in warnings[0].getMessage()


def test_a_deadline_not_lower_than_the_agent_timeout_disables_actions(caplog):
    env = {**SETTINGS_OK, "ACTION_STAGE_DEADLINE_SECONDS": "60", "AGENT_TIMEOUT_SECONDS": "60"}
    with caplog.at_level(logging.WARNING, logger="wealth_agent.actions.config"):
        status = config.startup_check(env)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert status.enabled is False and len(warnings) == 1
    assert "60" in warnings[0].getMessage()
    assert "ACTION_STAGE_DEADLINE_SECONDS" in warnings[0].getMessage()
    assert "AGENT_TIMEOUT_SECONDS" in warnings[0].getMessage()


def test_the_timeout_is_read_from_the_environment_it_is_given():
    # deadline (default 50) is not lower than a timeout of 40: fails and names both values
    status = config.startup_check({**SETTINGS_OK, "AGENT_TIMEOUT_SECONDS": "40"})
    assert status.enabled is False
    assert any("50" in p and "40" in p for p in status.problems)

    # equal also fails
    equal = {**SETTINGS_OK, "ACTION_STAGE_DEADLINE_SECONDS": "40", "AGENT_TIMEOUT_SECONDS": "40"}
    assert config.startup_check(equal).enabled is False

    # 49 under 50 passes
    ok = {**SETTINGS_OK, "ACTION_STAGE_DEADLINE_SECONDS": "49", "AGENT_TIMEOUT_SECONDS": "50"}
    assert config.startup_check(ok).enabled is True

    # unset timeout uses 60, so the default deadline of 50 passes
    assert config.startup_check(SETTINGS_OK).enabled is True


def test_start_up_logs_the_timeout_and_the_deadline_in_use(caplog):
    env = {**SETTINGS_OK, "AGENT_TIMEOUT_SECONDS": "45", "ACTION_STAGE_DEADLINE_SECONDS": "40"}
    with caplog.at_level(logging.INFO, logger="wealth_agent.actions.config"):
        config.startup_check(env)
    lines = [r.getMessage() for r in caplog.records if "AGENT_TIMEOUT_SECONDS" in r.getMessage() and r.levelno == logging.INFO]
    assert len(lines) == 1
    assert "45" in lines[0] and "ACTION_STAGE_DEADLINE_SECONDS" in lines[0] and "40" in lines[0]


def test_the_start_up_line_is_logged_when_actions_are_disabled_too(caplog):
    with caplog.at_level(logging.INFO, logger="wealth_agent.actions.config"):
        config.startup_check({})
    assert any("AGENT_TIMEOUT_SECONDS" in r.getMessage() and "60" in r.getMessage() for r in caplog.records)


def test_start_up_never_logs_secrets(caplog):
    env = {**SETTINGS_OK, "DATABASE_URL": "postgresql://user:SECRET-PW@localhost/db"}
    with caplog.at_level(logging.DEBUG):
        config.startup_check(env)
        config.startup_check({"DATABASE_URL": env["DATABASE_URL"]})
    assert "SECRET-PW" not in caplog.text


# --- no drift from the back end ---------------------------------------------------------------------------


def _backend_agent_module():
    spec = importlib.util.spec_from_file_location("backend_agent_under_test", BACKEND_AGENT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_back_end_and_agent_share_the_default_and_the_variable_name(monkeypatch):
    backend = _backend_agent_module()
    assert backend.DEFAULT_AGENT_TIMEOUT_SECONDS == config.DEFAULT_AGENT_TIMEOUT_SECONDS == 60

    # Both read the variable named AGENT_TIMEOUT_SECONDS: set it and both follow.
    assert config.AGENT_TIMEOUT_ENV == "AGENT_TIMEOUT_SECONDS"
    monkeypatch.setenv("AGENT_TIMEOUT_SECONDS", "33")
    assert backend.agent_timeout_seconds() == 33
    assert config.load_settings().agent_timeout_seconds == 33
    monkeypatch.delenv("AGENT_TIMEOUT_SECONDS")
    assert backend.agent_timeout_seconds() == config.load_settings().agent_timeout_seconds == 60
