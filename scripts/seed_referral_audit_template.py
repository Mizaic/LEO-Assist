"""Seed the Clinical Referral Audit multi-page template.

Maps the 23-component DashboardComponent schema onto the AuditTemplate system.

Pages:
    pg-rr-overview     Overview           Status, priority, timeline, KPIs
    pg-rr-service      Service Analysis   By service, org, wait times
    pg-rr-clinical     Clinical Analysis  Peer review, conditions, meds, obs
    pg-rr-demographics Demographics       Gender, age, IMD, documents
    pg-rr-dq           Data Quality       Completeness by field, DQ score

Usage:
    python scripts/seed_referral_audit_template.py --base-url http://localhost:8003

Environment variables:
    ANALYTICS_API_KEY   Optional service-to-service key
    RR_ORG_ID           Org ID to auto-publish the template after creation

Safe to re-run -- skips creation if the template title already exists.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

TEMPLATE_TITLE = "Clinical Referral Audit"

PAGES = [
    {"page_id": "pg-rr-overview", "title": "Overview"},
    {"page_id": "pg-rr-service", "title": "Service Analysis"},
    {"page_id": "pg-rr-clinical", "title": "Clinical Analysis"},
    {"page_id": "pg-rr-demographics", "title": "Demographics"},
    {"page_id": "pg-rr-dq", "title": "Data Quality"},
]


def _tile(
    label: str,
    metric_id: str,
    tile_type: str,
    x: int,
    y: int,
    w: int,
    h: int,
    page_id: str,
    section: str | None = None,
    story: dict | None = None,
) -> dict:
    t: dict = {
        "tile_id": str(uuid.uuid4()),
        "label": label,
        "tile_type": tile_type,
        "metric_id": metric_id,
        "param_overrides": {},
        "layout": {"x": x, "y": y, "w": w, "h": h},
        "page_id": page_id,
    }
    if section:
        t["section"] = section
    if story:
        t["story"] = story
    return t


def _story(headline: str, highlight_key: str) -> dict:
    return {"headline": headline, "highlight_key": highlight_key, "annotations": []}


# ---------------------------------------------------------------------------
# Page 1: Overview
# ---------------------------------------------------------------------------


def _overview_tiles() -> list[dict]:
    pid = "pg-rr-overview"
    return [
        _tile(
            "Avg days to first appointment",
            "rr_avg_days_to_appointment", "kpi_strip",
            0, 0, 4, 2, pid,
            section="Key Performance Indicators",
            story=_story("Average wait from referral to first appointment", "avg_days"),
        ),
        _tile(
            "Data quality score",
            "rr_dq_score", "kpi_strip",
            4, 0, 4, 2, pid,
            section="Key Performance Indicators",
            story=_story("% referrals with service, patient, and document present", "dq_score"),
        ),
        _tile(
            "Referral workflow state",
            "rr_workflow_state", "bar_chart",
            8, 0, 4, 2, pid,
            section="Key Performance Indicators",
        ),
        _tile(
            "Referral status",
            "rr_status_distribution", "bar_chart",
            0, 2, 4, 4, pid,
            section="Referral Status",
            story=_story("Current status of all referrals", "count"),
        ),
        _tile(
            "Priority breakdown",
            "rr_priority_distribution", "bar_chart",
            4, 2, 4, 4, pid,
            section="Referral Status",
            story=_story("Most referrals should be TWO_WEEK_WAIT", "count"),
        ),
        _tile(
            "Priority to state flow",
            "rr_outcome_flow", "table",
            8, 2, 4, 4, pid,
            section="Referral Status",
        ),
        _tile(
            "Monthly referral volume",
            "rr_monthly_trend", "line_chart",
            0, 6, 6, 4, pid,
            section="Trends",
            story=_story("Monthly referral volume over time", "count"),
        ),
        _tile(
            "Year-on-year comparison",
            "rr_yoy_trend", "line_chart",
            6, 6, 6, 4, pid,
            section="Trends",
        ),
    ]


# ---------------------------------------------------------------------------
# Page 2: Service Analysis
# ---------------------------------------------------------------------------


def _service_tiles() -> list[dict]:
    pid = "pg-rr-service"
    return [
        _tile(
            "Referrals by service",
            "rr_by_service", "bar_chart",
            0, 0, 6, 4, pid,
            section="Service",
            story=_story("Which services are receiving the most referrals?", "count"),
        ),
        _tile(
            "Referrals by commissioning organisation",
            "rr_by_commissioning_org", "bar_chart",
            6, 0, 6, 4, pid,
            section="Service",
        ),
        _tile(
            "Wait time distribution",
            "rr_wait_time_distribution", "bar_chart",
            0, 4, 6, 4, pid,
            section="Wait Times",
            story=_story("How long are patients waiting from referral to first appointment?", "count"),
        ),
        _tile(
            "62-day breaches by service",
            "rr_wait_time_breaches_by_service", "bar_chart",
            6, 4, 6, 4, pid,
            section="Wait Times",
            story=_story("Services exceeding the 62-day wait target", "breach_pct"),
        ),
    ]


# ---------------------------------------------------------------------------
# Page 3: Clinical Analysis
# ---------------------------------------------------------------------------


def _clinical_tiles() -> list[dict]:
    pid = "pg-rr-clinical"
    return [
        _tile(
            "Peer review AI assessment",
            "rr_peer_review_analysis", "bar_chart",
            0, 0, 6, 4, pid,
            section="Clinical Data",
            story=_story("AI assessment verdicts on peer-reviewed referrals", "count"),
        ),
        _tile(
            "Top conditions on referred patients",
            "rr_top_conditions", "bar_chart",
            6, 0, 6, 4, pid,
            section="Clinical Data",
        ),
        _tile(
            "Top medications on referred patients",
            "rr_top_medications", "bar_chart",
            0, 4, 6, 4, pid,
            section="Clinical Data",
        ),
        _tile(
            "Abnormal observations on referred patients",
            "rr_abnormal_observations", "bar_chart",
            6, 4, 6, 4, pid,
            section="Clinical Data",
        ),
    ]


# ---------------------------------------------------------------------------
# Page 4: Demographics
# ---------------------------------------------------------------------------


def _demographics_tiles() -> list[dict]:
    pid = "pg-rr-demographics"
    return [
        _tile(
            "Patient gender",
            "rr_patient_gender", "bar_chart",
            0, 0, 3, 4, pid,
            section="Patient Demographics",
        ),
        _tile(
            "Patient age distribution",
            "rr_patient_age_bands", "bar_chart",
            3, 0, 6, 4, pid,
            section="Patient Demographics",
            story=_story("Age profile of referred patients", "count"),
        ),
        _tile(
            "Deprivation (IMD)",
            "rr_imd_distribution", "bar_chart",
            9, 0, 3, 4, pid,
            section="Patient Demographics",
        ),
        _tile(
            "Document types",
            "rr_document_types", "bar_chart",
            0, 4, 12, 4, pid,
            section="Supporting Documents",
            story=_story("Types of documents attached to referrals", "count"),
        ),
    ]


# ---------------------------------------------------------------------------
# Page 5: Data Quality
# ---------------------------------------------------------------------------


def _dq_tiles() -> list[dict]:
    pid = "pg-rr-dq"
    return [
        _tile(
            "Data quality score",
            "rr_dq_score", "kpi_strip",
            0, 0, 4, 2, pid,
            section="Overall Score",
            story=_story(
                "% referrals with service, patient, and document present", "dq_score"
            ),
        ),
        _tile(
            "Completeness by field",
            "rr_data_completeness", "bar_chart",
            0, 2, 12, 4, pid,
            section="Field Completeness",
            story=_story("Which fields are missing most often?", "pct"),
        ),
    ]


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def build_tiles() -> list[dict]:
    tiles: list[dict] = []
    tiles += _overview_tiles()
    tiles += _service_tiles()
    tiles += _clinical_tiles()
    tiles += _demographics_tiles()
    tiles += _dq_tiles()
    return tiles


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _headers(api_key: str) -> dict:
    h = {"Content-Type": "application/json"}
    if api_key:
        h["X-API-Key"] = api_key
    return h


def _get(base: str, path: str, api_key: str) -> list | dict:
    req = urllib.request.Request(f"{base}{path}", headers=_headers(api_key))
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def _post(base: str, path: str, body: dict, api_key: str) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{base}{path}", data=data, headers=_headers(api_key), method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Clinical Referral Audit template")
    parser.add_argument(
        "--base-url", default="http://localhost:8003", help="Analytics API base URL"
    )
    args = parser.parse_args()
    base = args.base_url.rstrip("/") + "/analytics"
    api_key = os.environ.get("ANALYTICS_API_KEY", "")
    org_id = os.environ.get("RR_ORG_ID", "")

    print(f"Checking for existing '{TEMPLATE_TITLE}' template...")
    try:
        templates = _get(base, "/audit-templates", api_key)
    except urllib.error.HTTPError as exc:
        print(f"ERROR: GET /audit-templates -> {exc.code} {exc.reason}", file=sys.stderr)
        sys.exit(1)

    existing = next((t for t in templates if t.get("title") == TEMPLATE_TITLE), None)

    if existing:
        template_id = existing["template_id"]
        print(f"Found existing template {template_id} (status={existing['status']}) -- skipping.")
    else:
        tiles = build_tiles()
        print(f"Creating '{TEMPLATE_TITLE}' ({len(PAGES)} pages, {len(tiles)} tiles)...")
        payload = {"title": TEMPLATE_TITLE, "tiles": tiles, "pages": PAGES}
        try:
            created = _post(base, "/audit-templates", payload, api_key)
            template_id = created["template_id"]
            print(f"Created template: {template_id}")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode()
            print(f"ERROR creating template: {exc.code} {body}", file=sys.stderr)
            sys.exit(1)

    if not org_id:
        print("RR_ORG_ID not set -- skipping publish.")
        print("Done.")
        return

    print(f"Publishing to org: {org_id}...")
    pub_payload = {"template_id": template_id, "scope_type": "org", "scope_id": org_id}
    try:
        result = _post(base, f"/audit-templates/{template_id}/publish", pub_payload, api_key)
        print(f"Published: assignment_id={result.get('assignment_id')}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        print(f"WARN: publish failed: {exc.code} {body}", file=sys.stderr)

    print("Done.")


if __name__ == "__main__":
    main()
