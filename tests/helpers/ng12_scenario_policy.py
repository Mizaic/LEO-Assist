"""NG12 scenario policy helpers for CI bitmap vs fixture-only rows."""

from __future__ import annotations

# Stable skip reason for pytest and docs (NG12-AT-003).
BITMAP_HARNESS_SKIP_REASON = "Rule not active in graph"

ACTIVE_NG12_RULE_IDS: frozenset[str] = frozenset(
    {
        "rule:NG12:v1:CH002:SEC000:R004:6d4e9c13"
        ":edit:dd11e8d3:edit:a0b74f59",
        "rule:NG12:v1:CH002:SEC002:R002:3b6a24e5:edit:308ce725",
        "rule:NG12:v1:CH002:SEC002:R004:1e614d35:edit:b242528c",
    }
)


def bitmap_harness_assertion_skipped(gdl_row: dict) -> bool:
    """Return True when CI must not assert GuidelineEvaluator output for this row.

    Skips stub fixtures, non-active graph status, absent rule id, or unknown
    active-rule id for the golden harness.
    """
    if gdl_row.get("_stub") is True:
        return True
    status = gdl_row.get("_graph_status")
    if status != "active":
        return True
    rid = gdl_row.get("graph_rule_id")
    if not rid or rid not in ACTIVE_NG12_RULE_IDS:
        return True
    if gdl_row.get("expect_graph_match") is None:
        return True
    return False


def should_run_bitmap_harness_assertion(gdl_row: dict) -> bool:
    """Inverse of :func:`bitmap_harness_assertion_skipped` for parametrisation."""
    return not bitmap_harness_assertion_skipped(gdl_row)


def bitmap_harness_skip_reason(gdl_row: dict) -> str | None:
    """Return ``BITMAP_HARNESS_SKIP_REASON`` when the row skips the harness."""
    if bitmap_harness_assertion_skipped(gdl_row):
        return BITMAP_HARNESS_SKIP_REASON
    return None
