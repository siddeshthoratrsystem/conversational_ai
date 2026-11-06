"""Access to AI planning (spec 009 US3, research R8).

A stand-in until the business supplies real rules. It fails closed: when access can't be
decided, the chat offers general education only.
"""

import os
from typing import Any, Literal

Access = Literal["granted", "denied", "unavailable"]


def _deny_list() -> set[str]:
    return {v.strip() for v in os.getenv("ENTITLEMENT_DENY", "").split(",") if v.strip()}


def check_access(claims: dict[str, Any]) -> Access:
    """Decide from the verified token: the deny list wins, then the `ai_planning` claim."""
    deny = _deny_list()
    if claims["sub"] in deny or claims.get("preferred_username") in deny:
        return "denied"
    if os.getenv("ENTITLEMENT_MODE", "claim").strip().lower() == "unavailable":
        return "unavailable"
    planning = claims.get("ai_planning")
    if not isinstance(planning, bool):
        return "unavailable"  # missing or unreadable claim: fail closed
    return "granted" if planning else "denied"
