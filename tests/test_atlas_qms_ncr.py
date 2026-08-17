"""VT -- Validation Lab product NCR shape and locked product.

Atlas: DI-287FFFD0
"""

from __future__ import annotations

import pytest

from libs.atlas_qms.ncr_client import facade_headers, qms_base_url
from libs.atlas_qms.ncr_shape import (
    LEO_CDS_PRODUCT_ID,
    NcrShapeError,
    build_create_description,
    compact_ncr,
    filter_ncrs,
    is_open_ncr,
    validate_ncr_create,
)


def test_validate_create_locks_product_and_rejects_short_title() -> None:
    row = validate_ncr_create(
        title="Missed code",
        description="LEO missed a present finding.",
        severity="Major",
    )
    assert row["product_id"] == LEO_CDS_PRODUCT_ID
    assert row["severity"] == "major"
    with pytest.raises(NcrShapeError, match="five characters"):
        validate_ncr_create(title="ncr", description="enough text", severity="minor")


def test_validate_create_rejects_unknown_severity() -> None:
    with pytest.raises(NcrShapeError, match="Severity"):
        validate_ncr_create(
            title="Missed code",
            description="LEO missed a present finding.",
            severity="critical",
        )


def test_compact_ncr_drops_embedding() -> None:
    row = compact_ncr(
        {
            "id": "ncr-1",
            "title": "Missed code",
            "description": "What went wrong",
            "severity": "minor",
            "status": "identified",
            "product_id": LEO_CDS_PRODUCT_ID,
            "content_embedding": [0.1, 0.2],
        }
    )
    assert row["id"] == "ncr-1"
    assert "content_embedding" not in row


def test_filter_ncrs_matches_title() -> None:
    rows = [
        {"id": "1", "title": "Missed code", "description": "", "status": "identified"},
        {"id": "2", "title": "Wrong unit", "description": "", "status": "closed"},
    ]
    found = filter_ncrs(rows, "missed")
    assert [row["id"] for row in found] == ["1"]


def test_filter_ncrs_hides_closed_and_cancelled() -> None:
    rows = [
        {"id": "1", "title": "Open miss", "description": "", "status": "identified"},
        {"id": "2", "title": "Done", "description": "", "status": "closed"},
        {"id": "3", "title": "Withdrawn", "description": "", "status": "cancelled"},
        {"id": "4", "title": "In review", "description": "", "status": "investigated"},
    ]
    found = filter_ncrs(rows, "")
    assert [row["id"] for row in found] == ["1", "4"]
    assert is_open_ncr({"status": "contained"})
    assert is_open_ncr({"status": "disposition_pending"})
    assert not is_open_ncr({"status": "closed"})


def test_build_create_description_adds_run_not_patient() -> None:
    text = build_create_description(
        "LEO missed a finding.",
        run_id="run-9",
        why="Complaint from clinic",
    )
    assert "Pipeline run: run-9" in text
    assert "Complaint from clinic" in text
    assert "NHS" not in text


def test_facade_headers_use_service_token_and_org() -> None:
    headers = facade_headers("tok-1", "org-9")
    assert headers["X-Service-Token"] == "tok-1"
    assert headers["X-Organization-ID"] == "org-9"
    assert "Authorization" not in headers
    assert "Chrome/" in headers["User-Agent"]
    assert "Python-urllib" not in headers["User-Agent"]


def test_qms_base_url_strips_validation_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATLAS_QMS_GRAPH_BASE_URL", raising=False)
    monkeypatch.setenv(
        "ATLAS_VALIDATION_RUNS_BASE_URL",
        "https://atlas.example/api/v1/validation-runs",
    )
    assert qms_base_url() == "https://atlas.example/api/v1"
