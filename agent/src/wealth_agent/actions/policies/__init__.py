"""The registry of action policies: name -> builder (spec 011, FR-002).

A new action adds `<name>_policy.py` here and one line below; `gate.py` does not change.
"""

from __future__ import annotations

from wealth_agent.actions.gate import PolicyFactory

POLICIES: dict[str, PolicyFactory] = {}

from wealth_agent.actions.policies import contribution_policy  # noqa: E402

POLICIES[contribution_policy.ContributionPolicy.name] = contribution_policy.build_contribution_policy
