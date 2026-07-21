"""WS8: audit draft propose_dashboard pages / widgets / zone fields."""

from __future__ import annotations

from services.analytics_api.app.routers.audit_draft import (
    DraftRequest,
    _PROPOSE_DASHBOARD_TOOL,
    _VALID_WIDGETS,
    _build_phase,
)


def test_valid_widgets_matches_full_catalogue() -> None:
    expected = {
        "symptoms_ppv",
        "blood_signal",
        "cancer_type",
        "cancer_stage",
        "diagnostic_intervals",
        "consultations",
        "safety_netting",
        "investigations",
        "avoidable_delays",
        "care_obstructions",
        "place_of_presentation",
        "demographics",
        "comorbidities",
    }
    assert _VALID_WIDGETS == expected


def test_propose_dashboard_schema_has_pages_and_zone_fields() -> None:
    props = _PROPOSE_DASHBOARD_TOOL["toolSpec"]["inputSchema"]["json"]["properties"]
    assert "pages" in props
    assert "zone1_narrative" in props
    assert "zone2_narrative" in props
    tile_props = props["tiles"]["items"]["properties"]
    assert "page_id" in tile_props


def test_build_phase_accepts_widget_and_emits_pages() -> None:
    body = DraftRequest(
        messages=[],
        phase="build",
        approved_pages=[{"page_id": "p1", "label": "Snapshot", "kind": "snapshot"}],
        approved_tiles=[
            {
                "metric_id": "cancer_type",
                "label": "Cancer types",
                "tile_type": "widget",
                "page_id": "p1",
                "reason": "parity",
            }
        ],
        zone1_narrative="Zone one summary",
        zone2_narrative="Zone two priorities",
    )
    events = list(_build_phase(body))
    joined = "".join(events)
    assert "pages-proposed" in joined
    assert "narratives-proposed" in joined
    assert "tile-added" in joined
    assert "cancer_type" in joined
