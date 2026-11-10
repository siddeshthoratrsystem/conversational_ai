"""The mock 401(k) contribution action: demo payroll seed and money figures (spec 011).

Everything here is demo data, the same for every participant. Amounts are Decimal, computed from
exact values and rounded half-up to cents only at the end (FR-019).
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path

from fastapi import Depends
from sqlalchemy.orm import Session as DbSession

from app import models
from app.actions import gate
from app.db import get_db

SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "payroll.json"
CENT = Decimal("0.01")


class SeedUnavailable(Exception):
    """The demo payroll seed is missing or invalid, so contribution changes can't be offered."""


@dataclass(frozen=True)
class Seed:
    currency: str
    annual_salary: Decimal
    match_pct: Decimal  # employer matches this percent of what the participant contributes...
    cap_pct: Decimal  # ...up to this percent of pay
    starting_pct: int


def _number(value, what: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SeedUnavailable(f"{what} must be a number")
    return Decimal(str(value))


def _percent(value, what: str) -> Decimal:
    number = _number(value, what)
    if not Decimal(0) <= number <= Decimal(100):
        raise SeedUnavailable(f"{what} must be between 0 and 100")
    return number


def load_seed(path: Path | None = None, min_pct: int = 0, max_pct: int = 50) -> Seed:
    """Read and validate the seed. Raises SeedUnavailable for a missing or invalid file."""
    try:
        data = json.loads(Path(path or SEED_PATH).read_text())
    except (OSError, ValueError) as exc:
        raise SeedUnavailable(f"cannot read the payroll seed: {exc}") from exc
    if not isinstance(data, dict):
        raise SeedUnavailable("payroll seed must be an object")
    match = data.get("employer_match")
    if not isinstance(match, dict):
        raise SeedUnavailable("employer_match is missing")
    salary = _number(data.get("annual_salary"), "annual_salary")
    if salary <= 0:
        raise SeedUnavailable("annual_salary must be positive")
    starting = _percent(data.get("starting_contribution_pct"), "starting_contribution_pct")
    if starting != starting.to_integral_value() or not min_pct <= starting <= max_pct:
        raise SeedUnavailable(f"starting_contribution_pct must be a whole number from {min_pct} to {max_pct}")
    return Seed(
        currency=str(data.get("currency", "USD")),
        annual_salary=salary,
        match_pct=_percent(match.get("match_pct"), "match_pct"),
        cap_pct=_percent(match.get("cap_pct_of_pay"), "cap_pct_of_pay"),
        starting_pct=int(starting),
    )


@lru_cache
def get_seed() -> Seed:
    """The shipped seed, read once. The file is never written at runtime."""
    return load_seed()


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


# --- the contribution service (the only way the gate reads or changes contributions; FR-021) -----

class DemoContributionService:
    """Demo source: the `contributions` table, falling back to the seed's starting rate."""

    def __init__(
        self,
        db: DbSession,
        seed: Seed | None = None,
        redeem: Callable[[gate.ConfirmationToken], None] | None = None,
    ):
        self.db = db
        self._seed = seed
        self._redeem = redeem or (lambda token: gate.redeem_token(db, token))

    @property
    def seed(self) -> Seed:
        return self._seed or get_seed()  # read when needed, so a missing seed only affects changes

    def current_rate(self, participant_id: str) -> int:
        row = self.db.get(models.Contribution, participant_id)
        return row.rate_pct if row is not None else self.seed.starting_pct

    def apply_change(self, participant_id: str, new_rate_pct: int, token: gate.ConfirmationToken) -> int:
        """Redeem the token (single use), then write the new rate. Returns the new rate."""
        if isinstance(new_rate_pct, bool) or not isinstance(new_rate_pct, int):
            raise ValueError("the demo store keeps whole percentages only")  # before the token is used
        if token.user_id != participant_id:  # a token is bound to the participant it was issued to
            raise gate.GateRefusal("token_invalid")
        self._redeem(token)
        row = self.db.get(models.Contribution, participant_id)
        now = datetime.now(timezone.utc)
        if row is None:
            self.db.add(models.Contribution(user_id=participant_id, rate_pct=new_rate_pct, updated_at=now))
        else:
            row.rate_pct, row.updated_at = new_rate_pct, now
        self.db.flush()
        return new_rate_pct


def get_contribution_service(db: DbSession = Depends(get_db)) -> gate.ContributionService:
    """FastAPI dependency, so tests and later deployments can swap the source."""
    return DemoContributionService(db)


# --- the action type ---------------------------------------------------------------------------------

def _dollars(amount: Decimal) -> str:
    return f"${amount:,.2f}"


def _signed(amount: Decimal) -> str:
    return f"{'+' if amount >= 0 else '-'}{_dollars(abs(amount))}"


class ContributionChange:
    """Change the participant's 401(k) contribution rate."""

    name = "contribution_change"

    def __init__(self, service: gate.ContributionService, seed: Seed, settings: gate.GateSettings):
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
        if self.settings.whole_pct_only and rate != rate.to_integral_value():
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


def _build_contribution_change(context: gate.ActionContext) -> ContributionChange:
    try:
        seed = get_seed()
    except SeedUnavailable as exc:
        raise gate.GateRefusal("seed_unavailable") from exc
    return ContributionChange(context.contributions, seed, context.settings)


gate.ACTION_TYPES[ContributionChange.name] = _build_contribution_change
