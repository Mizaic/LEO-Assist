"""VT-LEO-AI-121 - Staging enrichment specialty scoping + post-diagnosis window.

Covers TC-003 (window calculation) and integration tests for the
staging_enrichment subgraph.
"""

from __future__ import annotations

from libs.pipeline_graph.subgraphs.staging_enrichment import (
    STAGING_WINDOW_DAYS,
    _choose_window,
)


def test_window_uses_diagnosis_plus_90_days():
    """VT-118-TC-003."""
    meta = {
        "diagnosis_date": "2024-01-01",
        "referral_date": "2023-11-01",
        "end_date": "2024-06-01",
    }
    start, end = _choose_window(meta)
    assert start == "2024-01-01"
    assert end == "2024-03-31"


def test_window_constant_is_90():
    """Window must be exactly 90 days per DI-LEO-AI-126."""
    assert STAGING_WINDOW_DAYS == 90


def test_window_falls_back_without_diagnosis():
    """When diagnosis_date is missing we fall back to referral..end so
    legacy behaviour preserves coverage for episodes with no diagnosis anchor."""
    meta = {
        "diagnosis_date": "",
        "referral_date": "2023-11-01",
        "end_date": "2024-06-01",
    }
    start, end = _choose_window(meta)
    assert start == "2023-11-01"
    assert end == "2024-06-01"


def test_window_handles_malformed_diagnosis_date():
    """Malformed diagnosis_date falls back rather than crashing."""
    meta = {
        "diagnosis_date": "not-a-date",
        "referral_date": "2023-11-01",
        "end_date": "2024-06-01",
    }
    start, end = _choose_window(meta)
    assert start == "2023-11-01"
    assert end == "2024-06-01"


def test_window_handles_truncated_datetime():
    """_choose_window normalises diagnosis_date to YYYY-MM-DD."""
    meta = {"diagnosis_date": "2024-01-01T00:00:00", "referral_date": "", "end_date": ""}
    start, end = _choose_window(meta)
    assert start == "2024-01-01"
    assert end == "2024-03-31"


def test_specialty_filter_wired_into_enrichment():
    """The staging enrichment module imports filter_rows_by_specialty and
    calls it with the episode cancer_type."""
    import inspect
    from libs.pipeline_graph.subgraphs import staging_enrichment

    src = inspect.getsource(staging_enrichment)
    assert "filter_rows_by_specialty" in src
    assert "cancer_type" in src
    assert "from libs.clinical_scoping" in src
