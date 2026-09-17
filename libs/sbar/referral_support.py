"""Choose which matched rules may say the referral is supported.

A two-week-wait (or more urgent) rule is why a 2WW referral is
supported. Primary-care test rules stay visible as other matches.

Atlas trace:
  DO: DO-B226E498
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-B226E498")
"""

from __future__ import annotations

from typing import Any

_TIME_CRITICAL = frozenset({"immediate", "very_urgent", "2ww"})


def _rule_priority(rule: dict[str, Any]) -> str:
    actions = rule.get("actions")
    if isinstance(actions, list) and actions:
        return str(actions[0].get("priority") or "").lower()
    legacy = rule.get("action") or {}
    return str(legacy.get("priority") or "").lower()


def support_rules_for_referral(
    rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return only 2WW-or-higher refer rules that support the request.

    Offer, consider, routine, and urgent investigation rules never claim
    receiving-service support. When none of the time-critical rules
    match, return an empty list.
    """
    if not rules:
        return []
    return [rule for rule in rules if _rule_priority(rule) in _TIME_CRITICAL]
