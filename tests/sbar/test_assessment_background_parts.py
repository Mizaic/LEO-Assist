"""DI-740BE510 -- background_parts is persisted and round-tripped.

Verifies that the SBAR assessment query layer carries the structured
per-part source-records summary end-to-end:

  - SET_BACKGROUND accepts a JSON-encoded ``background_parts`` value
    (TC-001 invariant only -- the SQL is asserted in the integration
    test against a real Neo4j; here we just pin the parameter in the
    query string so a future drop is caught).
  - GET_ASSESSMENT exposes ``background_parts`` to ``assessment_to_dict``
    and the helper decodes a JSON string into a list of dicts.
  - Legacy Assessments written before DI-740BE510 (column = None) map
    to an empty list, so the UI's ``backgroundParts.length > 0`` branch
    never fires for legacy data.
  - Malformed JSON in the column does NOT raise; it returns ``[]`` so
    GET /sbar/assessments/{id} keeps returning 200.

See DI-740BE510, R-4965BCD2.
"""

from __future__ import annotations

import json
from typing import Any

from libs.cypher import sbar_assessment_queries as q


def test_set_background_query_takes_background_parts_param() -> None:
    """SET_BACKGROUND must reference $background_parts.

    Drift here would mean the orchestrator passes the parameter but
    the Cypher silently drops it, so source-records would never land
    on the :Assessment node. The TC catches that drift before it
    reaches the integration test.
    """
    assert "$background_parts" in q.SET_BACKGROUND
    assert "a.background_parts" in q.SET_BACKGROUND


def test_get_assessment_query_returns_background_parts() -> None:
    """GET_ASSESSMENT must SELECT a.background_parts.

    Symmetric drift check: if the persistence side writes the column
    but the read side never returns it, the API and the UI both go
    quiet -- no error, just a silent loss of source-records.
    """
    assert "a.background_parts" in q.GET_ASSESSMENT
    assert "AS background_parts" in q.GET_ASSESSMENT


def _record(**overrides: Any) -> dict[str, Any]:
    """Build a fake Neo4j record dict matching the GET_ASSESSMENT shape."""
    base: dict[str, Any] = {
        "id": "asm-1",
        "type": "SBAR",
        "status": "completed",
        "created_at": None,
        "updated_at": None,
        "run_id": "run-1",
        "requested_by": "user-1",
        "tenant_id": "tenant-1",
        "guideline_ids": [],
        "patient_id": "patient-1",
        "situation": "S",
        "background": "B",
        "background_parts": None,
        "assessment": "A",
        "assessment_codes": [],
        "assessment_rules": "[]",
        "recommendation": "R",
        "recommendation_actions": "[]",
        "content": "# SBAR\n\n## S\n\nx",
        "stt": None,
        "stt_evidence": None,
        "alternative_pathway": None,
        "alternative_pathway_evidence": None,
        "rtr": None,
        "rtr_evidence": None,
        "errors": [],
    }
    base.update(overrides)
    return base


def test_assessment_to_dict_decodes_background_parts_json_string() -> None:
    """JSON-encoded column round-trips into a list of dicts."""
    parts = [
        {
            "index": 1,
            "total": 2,
            "record_count": 3,
            "record_range": [1, 3],
            "source_ids": ["enc-1", "enc-2", "enc-3"],
            "status": "completed",
            "error_code": None,
            "error_message": None,
        },
        {
            "index": 2,
            "total": 2,
            "record_count": 2,
            "record_range": [4, 5],
            "source_ids": ["enc-4", "enc-5"],
            "status": "completed",
            "error_code": None,
            "error_message": None,
        },
    ]
    record = _record(background_parts=json.dumps(parts))
    out = q.assessment_to_dict(record)
    assert out["background_parts"] == parts
    # Source IDs must round-trip exactly so the UI can render them.
    assert out["background_parts"][0]["source_ids"] == ["enc-1", "enc-2", "enc-3"]


def test_assessment_to_dict_returns_empty_list_for_legacy_assessment() -> None:
    """Pre-DI-740BE510 Assessments have a NULL column; map to []."""
    record = _record(background_parts=None)
    out = q.assessment_to_dict(record)
    assert out["background_parts"] == []


def test_assessment_to_dict_returns_empty_list_for_empty_string() -> None:
    """An empty-string column (defensive) also maps to []."""
    record = _record(background_parts="")
    out = q.assessment_to_dict(record)
    assert out["background_parts"] == []


def test_assessment_to_dict_swallows_malformed_json() -> None:
    """Malformed JSON returns [] -- never raises.

    The disclosure is non-essential chrome and a malformed column
    must not 500 the GET endpoint that drives the entire dialog.
    """
    record = _record(background_parts="not-json{")
    out = q.assessment_to_dict(record)
    assert out["background_parts"] == []


def test_assessment_to_dict_filters_non_dict_entries() -> None:
    """A list with stray scalars yields only the dict entries.

    Defensive: a future migration that stores a stringified id by
    accident shouldn't crash the renderer.
    """
    raw = json.dumps(
        [
            "stray-string",
            42,
            {"index": 1, "total": 1, "source_ids": ["enc-1"]},
        ]
    )
    record = _record(background_parts=raw)
    out = q.assessment_to_dict(record)
    assert len(out["background_parts"]) == 1
    assert out["background_parts"][0]["source_ids"] == ["enc-1"]


def test_assessment_to_dict_accepts_already_decoded_list() -> None:
    """A future driver that pre-decodes JSON columns must still work."""
    parts = [{"index": 1, "total": 1, "source_ids": ["enc-1"]}]
    record = _record(background_parts=parts)
    out = q.assessment_to_dict(record)
    assert out["background_parts"] == parts
