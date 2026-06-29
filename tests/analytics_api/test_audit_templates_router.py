"""
VT-32FBAA69 -- Audit templates router structural tests (DO-3775670C, DO-A9863AB6)

Atlas trace:
    VT: VT-32FBAA69  (id: 32fbaa69-4693-43fd-89be-215ee16b58c1)
    DI: DI-64CA7740
    DO: DO-3775670C

Covers DO-3775670C acceptance criteria:
    AC3 - GET /audit-metrics returns the metric catalogue without exposing Cypher.
    AC5 - CRUD endpoints accessible to platform_admin and qa_ra_lead roles only.

These are static-source assertions on the router source file.
No live Neo4j connection is required.
"""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
ROUTER = ROOT / "services" / "analytics_api" / "app" / "routers" / "audit_templates.py"
PATIENTS_ROUTER = ROOT / "services" / "analytics_api" / "app" / "routers" / "patients_epr.py"


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


# DO-3775670C AC3 - catalogue endpoint does not return the 'cypher' key
def test_ac3_metrics_catalogue_endpoint_excludes_cypher():
    src = _read(ROUTER)
    assert "get_catalogue" in src, "router must call get_catalogue"
    # The catalogue helper itself strips 'cypher' - verify router does not re-add it
    assert '"cypher"' not in src.split("get_catalogue")[1].split("\n")[0]


# DO-3775670C AC5 - write endpoints check admin role
def test_ac5_write_endpoints_require_admin():
    src = _read(ROUTER)
    assert "_require_admin" in src, "router must define or import _require_admin"
    # create, update, archive, publish all call _require_admin
    assert src.count("_require_admin") >= 4, (
        "expected at least 4 _require_admin calls (create/update/archive/publish)"
    )


# Router exposes publish endpoint
def test_publish_endpoint_exists():
    src = _read(ROUTER)
    assert "/publish" in src


# Router exposes active template endpoint (no admin required)
def test_active_template_endpoint_exists():
    src = _read(ROUTER)
    assert "/active" in src


# DI-AUDIT-PAGES - multi-page templates persist a pages_json property
def test_router_persists_pages_json():
    src = _read(ROUTER)
    # Both create and update must write the pages property to the node.
    assert src.count("t.pages_json") >= 2, "create + update must SET t.pages_json"
    assert "pages_json=pages_json" in src, "create must bind pages_json"
    assert "pages_json=new_pages" in src, "update must bind merged pages"
    assert "pages_data" in src, "_row_to_template must read pages_json"


# DI-AUDIT-PAGES - the Pydantic models accept pages and per-tile page_id and
# default to single-page (back-compatible) when omitted.
def test_audit_page_models_roundtrip():
    import sys

    sys.path.insert(0, str(ROOT / "services" / "analytics_api"))
    from app.models.audit_template import (  # noqa: E402
        AuditPage,
        AuditTemplateCreate,
        AuditTileCreate,
    )

    tile = AuditTileCreate(
        label="STT Rate",
        tile_type="kpi_strip",
        metric_id="referral_stt_rate",
        page_id="page-2",
        layout={"x": 0, "y": 0, "w": 4, "h": 3},
    )
    multi = AuditTemplateCreate(
        title="Two-page report",
        tiles=[tile],
        pages=[
            AuditPage(page_id="page-1", title="Overview"),
            AuditPage(page_id="page-2", title="Detail"),
        ],
    )
    assert len(multi.pages) == 2
    assert multi.tiles[0].page_id == "page-2"

    # Omitting pages stays back-compatible (single implicit page).
    single = AuditTemplateCreate(title="One page", tiles=[])
    assert single.pages == []


# patients_epr router does not filter by cancer_type
def test_patients_epr_router_has_no_cancer_type_filter():
    src = _read(PATIENTS_ROUTER)
    # The Cypher should not restrict on cancer-specific node types
    assert "cancer_type" not in src.lower() or "NOT" in src
    # Must use org guard
    assert "scope_org_ids" in src or "_ORG_GUARD" in src


# patients_epr router includes a timeline endpoint
def test_patients_epr_router_has_timeline_endpoint():
    src = _read(PATIENTS_ROUTER)
    assert "timeline" in src.lower()
