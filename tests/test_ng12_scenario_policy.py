"""NG12 CI policy: bitmap harness skips non-active graph rows.

Rows with ``_graph_status != \"active\"``, ``_stub: true``, or no golden
harness rule must not run GuidelineEvaluator assertions in CI. The stable
pytest/doc reason string is ``BITMAP_HARNESS_SKIP_REASON`` in
``tests.helpers.ng12_scenario_policy``.
"""

from __future__ import annotations

import pytest

from tests.helpers.ng12_scenario_loader import load_paired_scenarios
from tests.helpers.ng12_scenario_policy import (
    ACTIVE_NG12_RULE_IDS,
    BITMAP_HARNESS_SKIP_REASON,
    bitmap_harness_assertion_skipped,
    bitmap_harness_skip_reason,
    should_run_bitmap_harness_assertion,
)

_GDL_SCENARIOS = load_paired_scenarios()[0]["scenarios"]


@pytest.mark.parametrize(
    "row",
    _GDL_SCENARIOS,
    ids=[r["id"] for r in _GDL_SCENARIOS],
)
def test_every_gdl_row_skip_reason_is_stable(row: dict) -> None:
    """NG12-AT-003: skipped rows share one documented reason string."""
    if bitmap_harness_assertion_skipped(row):
        assert bitmap_harness_skip_reason(row) == BITMAP_HARNESS_SKIP_REASON
    else:
        assert bitmap_harness_skip_reason(row) is None


def test_ng12_gdl_038_is_not_active_for_harness() -> None:
    """Representative ``not_coded`` row (was stub-038) skips with stable reason."""
    row = next(r for r in _GDL_SCENARIOS if r["id"] == "NG12-GDL-038")
    assert bitmap_harness_assertion_skipped(row)
    assert bitmap_harness_skip_reason(row) == BITMAP_HARNESS_SKIP_REASON


def test_stub_row_skips_harness() -> None:
    """Rows marked ``_stub`` must not participate in bitmap assertions."""
    row = {
        "_stub": True,
        "_graph_status": "active",
        "graph_rule_id": next(iter(ACTIVE_NG12_RULE_IDS)),
        "expect_graph_match": True,
    }
    assert bitmap_harness_assertion_skipped(row) is True


def test_active_row_participates() -> None:
    """Harness-eligible rows are not skipped."""
    rid = next(iter(ACTIVE_NG12_RULE_IDS))
    row = {
        "_graph_status": "active",
        "graph_rule_id": rid,
        "expect_graph_match": False,
    }
    assert bitmap_harness_assertion_skipped(row) is False
    assert should_run_bitmap_harness_assertion(row) is True


def test_not_coded_status_skips() -> None:
    """``not_coded`` rows skip even if a rule id is present."""
    row = {
        "_graph_status": "not_coded",
        "graph_rule_id": next(iter(ACTIVE_NG12_RULE_IDS)),
        "expect_graph_match": True,
    }
    assert bitmap_harness_assertion_skipped(row) is True


@pytest.mark.parametrize(
    "row,expect_skip",
    [
        (
            {
                "_graph_status": "active",
                "graph_rule_id": "rule:unknown",
                "expect_graph_match": True,
            },
            True,
        ),
        (
            {
                "_graph_status": "active",
                "graph_rule_id": None,
                "expect_graph_match": True,
            },
            True,
        ),
        (
            {
                "_graph_status": "active",
                "graph_rule_id": next(iter(ACTIVE_NG12_RULE_IDS)),
                "expect_graph_match": None,
            },
            True,
        ),
    ],
)
def test_harness_skip_matrix(row: dict, expect_skip: bool) -> None:
    """Unknown rule ids and null expectations stay out of CI bitmap checks."""
    assert bitmap_harness_assertion_skipped(row) is expect_skip
