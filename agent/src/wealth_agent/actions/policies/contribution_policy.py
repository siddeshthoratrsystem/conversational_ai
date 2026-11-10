"""The mock 401(k) contribution policy: rules, money figures and texts (spec 011).

Everything here is demo data, the same for every participant. Amounts are Decimal, computed from
exact values and rounded half-up to cents only at the end (FR-019).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from wealth_agent.actions import gate
from wealth_agent.actions.config import GateSettings
from wealth_agent.actions.contribution_service import (  # noqa: F401  (re-exported for callers and tests)
    SEED_PATH,
    ContributionService,
    Seed,
    SeedUnavailable,
    get_seed,
    load_seed,
)

CENT = Decimal("0.01")


def _cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _exact_pay(seed: Seed) -> Decimal:
    return seed.annual_salary / 12


def monthly_pay(seed: Seed) -> Decimal:
    return _cents(_exact_pay(seed))


def _contribution(seed: Seed, rate_pct: int) -> Decimal:
    return _exact_pay(seed) * Decimal(rate_pct) / 100


def _match(seed: Seed, rate_pct: int) -> Decimal:
    matched_rate = min(Decimal(rate_pct), seed.cap_pct)
    return _exact_pay(seed) * matched_rate / 100 * seed.match_pct / 100


@dataclass(frozen=True)
class ContributionSummary:
    current_pct: int
    new_pct: int
    contribution_before: Decimal
    contribution_after: Decimal
    contribution_diff: Decimal
    match_before: Decimal
    match_after: Decimal
    match_diff: Decimal


def summarize(seed: Seed, current_pct: int, new_pct: int) -> ContributionSummary:
    """Per-month figures for changing the rate. Each amount, including each difference, is
    rounded from exact values, so a difference can be a cent away from subtracting two rounded ones."""
    c0, c1 = _contribution(seed, current_pct), _contribution(seed, new_pct)
    m0, m1 = _match(seed, current_pct), _match(seed, new_pct)
    return ContributionSummary(
        current_pct=current_pct,
        new_pct=new_pct,
        contribution_before=_cents(c0),
        contribution_after=_cents(c1),
        contribution_diff=_cents(c1 - c0),
        match_before=_cents(m0),
        match_after=_cents(m1),
        match_diff=_cents(m1 - m0),
    )


# --- the policy ---------------------------------------------------------------------------------

def _dollars(amount: Decimal) -> str:
    return f"${amount:,.2f}"


def _signed(amount: Decimal) -> str:
    return f"{'+' if amount >= 0 else '-'}{_dollars(abs(amount))}"


class ContributionPolicy:
    """Change the participant's 401(k) contribution rate."""

    name = "contribution_change"

    def __init__(self, service: ContributionService, seed: Seed, settings: GateSettings):
        self.service, self.seed, self.settings = service, seed, settings

    def parse(self, params: dict) -> dict:
        if not isinstance(params, dict) or set(params) != {"new_rate_pct"}:
            raise gate.GateRefusal("invalid_params")
        rate = params["new_rate_pct"]
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not math.isfinite(rate):
            raise gate.GateRefusal("invalid_params")
        return {"new_rate_pct": int(rate) if float(rate).is_integer() else rate}

    def check(self, participant_id: str, params: dict) -> dict:
        rate = Decimal(str(params["new_rate_pct"]))
        low, high = self.settings.min_pct, self.settings.max_pct
        if not low <= rate <= high:
            raise gate.GateRefusal(
                "out_of_range", f"The contribution rate must be between {low}% and {high}%."
            )
        if rate != rate.to_integral_value():
            raise gate.GateRefusal(
                "not_whole_pct", "The contribution rate must be a whole percentage, for example 8%."
            )
        current = self.service.current_rate(participant_id)
        if rate == current:
            raise gate.GateRefusal("same_as_current", f"Your contribution is already {current}%.")
        return {"current_rate_pct": current}

    def summary(self, params: dict, snapshot: dict, expiry_minutes: int) -> str:
        current, new = snapshot["current_rate_pct"], params["new_rate_pct"]
        figures = summarize(self.seed, current, new)
        if figures.match_diff == 0:
            match = f"- Employer match: {_dollars(figures.match_before)} a month (no change)"
        else:
            match = (
                f"- Employer match: {_dollars(figures.match_before)} \u2192 "
                f"{_dollars(figures.match_after)} a month ({_signed(figures.match_diff)})"
            )
        return "\n".join(
            [
                "Here's the change you asked for. Nothing has changed yet.",
                f"- 401(k) contribution: {current}% \u2192 {new}%",
                f"- Your contribution: {_dollars(figures.contribution_before)} \u2192 "
                f"{_dollars(figures.contribution_after)} a month ({_signed(figures.contribution_diff)})",
                match,
                "",
                f"Reply **confirm** within {expiry_minutes} minutes to make this change, "
                f"or **cancel** to keep {current}%.",
            ]
        )

    def execute(
        self, participant_id: str, params: dict, snapshot: dict, token: gate.ConfirmationToken
    ) -> str:
        new = self.service.apply_change(participant_id, params["new_rate_pct"], token)
        return f"Done. Your 401(k) contribution is now {new}% (it was {snapshot['current_rate_pct']}%)."

    def cancel_message(self, snapshot: dict) -> str:
        return f"Cancelled. Your 401(k) contribution stays at {snapshot['current_rate_pct']}%."


def build_contribution_policy(context: gate.PolicyContext) -> ContributionPolicy:
    try:
        seed = get_seed()
    except SeedUnavailable as exc:
        raise gate.GateRefusal("seed_unavailable") from exc
    return ContributionPolicy(context.contributions, seed, context.settings)
