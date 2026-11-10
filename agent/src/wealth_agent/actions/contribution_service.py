"""Where contributions come from: the demo payroll seed and the demo service (spec 011, FR-021).

`ContributionService` is the only way the gate reads or changes a participant's contribution. The
demo service reads the `contributions` table and falls back to the seed's starting rate. A later
`PrincipalContributionService` keeps the same two methods and sends `token.pending_action_id` as the
idempotency key.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import insert, select, update

from wealth_agent.actions import gate, store

SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "payroll.json"


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


class ContributionService(Protocol):
    """The only way the gate reads or changes contributions (FR-021)."""

    def current_rate(self, participant_id: str) -> int: ...

    def apply_change(self, participant_id: str, new_rate_pct: int, token: gate.ConfirmationToken) -> int:
        """Redeem the token (single use), apply the change and return the new rate."""


class DemoContributionService:
    """Demo source: the `contributions` table, falling back to the seed's starting rate.

    `conn` is the gate's connection inside its transaction.
    """

    def __init__(
        self,
        conn: Any,
        seed: Seed | None = None,
        redeem: Callable[[gate.ConfirmationToken], None] | None = None,
    ):
        self.conn = conn
        self._seed = seed
        self._redeem = redeem or (lambda token: gate.redeem_token(conn, token))

    @property
    def seed(self) -> Seed:
        return self._seed or get_seed()  # read when needed, so a missing seed only affects changes

    def current_rate(self, participant_id: str) -> int:
        row = self.conn.execute(
            select(store.contributions.c.rate_pct).where(store.contributions.c.user_id == participant_id)
        ).first()
        return row.rate_pct if row is not None else self.seed.starting_pct

    def apply_change(self, participant_id: str, new_rate_pct: int, token: gate.ConfirmationToken) -> int:
        """Redeem the token (single use), then write the new rate. Returns the new rate."""
        if isinstance(new_rate_pct, bool) or not isinstance(new_rate_pct, int):
            raise ValueError("the demo store keeps whole percentages only")  # before the token is used
        if token.user_id != participant_id:  # a token is bound to the participant it was issued to
            raise gate.GateRefusal("token_invalid")
        self._redeem(token)
        now = datetime.now(timezone.utc)
        table = store.contributions
        updated = self.conn.execute(
            update(table).where(table.c.user_id == participant_id).values(rate_pct=new_rate_pct, updated_at=now)
        )
        if updated.rowcount == 0:
            self.conn.execute(insert(table).values(user_id=participant_id, rate_pct=new_rate_pct, updated_at=now))
        return new_rate_pct
