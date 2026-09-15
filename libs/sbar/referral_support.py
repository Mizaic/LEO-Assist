"""Choose which matched rules may say the referral is supported.

A two-week-wait (or more urgent) rule is why a 2WW referral is
supported. Primary-care test rules stay visible as other matches.

Atlas:
  DO: DO-B226E498
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
    """Return 2WW-or-higher rules when any exist; else keep all rules."""
    if not rules:
        return []
    critical = [rule for rule in rules if _rule_priority(rule) in _TIME_CRITICAL]
    if critical:
        return critical
    return list(rules)
