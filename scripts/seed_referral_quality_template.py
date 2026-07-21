"""
Seed the Referral Quality Audit multi-page dashboard template.

Usage:
    python scripts/seed_referral_quality_template.py --base-url http://localhost:8001

Creates a 9-page template covering the full referral quality story:
    pg-exec      Executive Overview (headline KPIs across all workstreams)
    pg-gynae     Gynae Pathway Scorecard
    pg-lower-gi  Lower GI Pathway Scorecard
    pg-upper-gi  Upper GI Pathway Scorecard
    pg-breast    Breast Pathway Scorecard
    pg-rework    Operational Rework (missing info, backlog, practice-level)
    pg-gov       Clinical Governance (guideline fit, audit trail)
    pg-equity    Equity / CORE20PLUS5 (IMD, age, sex, conditions)
    pg-roi       ROI Summary (intervals, rework cost inputs)

Safe to re-run -- skips creation if a template titled TEMPLATE_TITLE already exists.

Metric gaps (require data model additions before they can be added as tiles):
    reclassification_rate      Needs EpisodeOfCare.original_referral_route or
                               a :ReclassificationEvent node + new metric.
    follow_up_request_rate     Needs a :FollowUpRequest node + new metric.
    follow_up_wait_days        Same as above.
    core20plus5_variation_flag Needs Patient.ethnicity + learning_disability fields,
                               plus a CORE20PLUS5 cohort classifier metric.
    missed_stt_by_condition    SBAR metrics currently have no condition_type param;
                               adding it requires extending the SBAR metric queries.

Environment variables:
    ANALYTICS_API_KEY   - service-to-service key (optional for local dev)
    RQ_ORG_ID           - org ID to auto-publish the template (optional)
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error

TEMPLATE_TITLE = "Referral Quality Audit"

PAGES = [
    {"page_id": "pg-exec", "title": "Executive Overview"},
    {"page_id": "pg-gynae", "title": "Gynae Pathway"},
    {"page_id": "pg-lower-gi", "title": "Lower GI Pathway"},
    {"page_id": "pg-upper-gi", "title": "Upper GI Pathway"},
    {"page_id": "pg-breast", "title": "Breast Pathway"},
    {"page_id": "pg-rework", "title": "Operational Rework"},
    {"page_id": "pg-gov", "title": "Clinical Governance"},
    {"page_id": "pg-equity", "title": "Equity (CORE20PLUS5)"},
    {"page_id": "pg-roi", "title": "ROI Summary"},
]

# Canonical condition_type values stored on EpisodeOfCare nodes.
# Confirm these with local data before publishing.
_CONDITION = {
    "gynae": "gynaecology",
    "lower_gi": "colorectal",
    "upper_gi": "upper_gi",
    "breast": "breast",
}


# ---------------------------------------------------------------------------
# Tile and story factory helpers
# ---------------------------------------------------------------------------


def _story(
    headline: str,
    highlight_key: str,
    threshold_label: str | None = None,
    threshold_value: float | None = None,
) -> dict:
    s: dict = {"headline": headline, "highlight_key": highlight_key, "annotations": []}
    if threshold_label and threshold_value is not None:
        s["annotations"].append(
            {
                "type": "threshold",
                "label": threshold_label,
                "value": threshold_value,
                "target_key": highlight_key,
            }
        )
    return s


def _tile(
    label: str,
    metric_id: str,
    tile_type: str,
    x: int,
    y: int,
    w: int,
    h: int,
    section: str | None = None,
    page_id: str | None = None,
    overrides: dict | None = None,
    story: dict | None = None,
) -> dict:
    t: dict = {
        "label": label,
        "tile_type": tile_type,
        "metric_id": metric_id,
        "param_overrides": overrides or {},
        "layout": {"x": x, "y": y, "w": w, "h": h},
    }
    if section:
        t["section"] = section
    if page_id:
        t["page_id"] = page_id
    if story:
        t["story"] = story
    return t


# ---------------------------------------------------------------------------
# Page builders
# ---------------------------------------------------------------------------


def _exec_tiles() -> list[dict]:
    # LONG FUNCTION: data declaration -- one entry per executive KPI tile
    pid = "pg-exec"
    return [
        _tile(
            "Total referrals processed",
            "patient_count",
            "kpi_strip",
            0, 0, 2, 2,
            section="Headline KPIs",
            page_id=pid,
        ),
        _tile(
            "Guideline match rate",
            "referral_guideline_compliance_rate",
            "kpi_strip",
            2, 0, 3, 2,
            section="Headline KPIs",
            page_id=pid,
            story=_story(
                "Referrals fully matching NICE pathway rules",
                "compliance_pct",
                threshold_label="80% target",
                threshold_value=80,
            ),
        ),
        _tile(
            "Completeness rate",
            "referral_completeness_rate",
            "kpi_strip",
            5, 0, 2, 2,
            section="Headline KPIs",
            page_id=pid,
            story=_story(
                "Referrals with all mandatory fields present",
                "completeness_pct",
                threshold_label="90% target",
                threshold_value=90,
            ),
        ),
        _tile(
            "Straight-to-test rate",
            "referral_stt_rate",
            "kpi_strip",
            7, 0, 2, 2,
            section="Headline KPIs",
            page_id=pid,
            story=_story(
                "Eligible referrals routed directly to test",
                "stt_pct",
                threshold_label="40% target",
                threshold_value=40,
            ),
        ),
        _tile(
            "Alternative pathway flagged",
            "referral_alternative_pathway_rate",
            "kpi_strip",
            9, 0, 3, 2,
            section="Headline KPIs",
            page_id=pid,
            story=_story(
                "Referrals where LEO identified a more appropriate pathway",
                "alt_pathway_pct",
            ),
        ),
        _tile(
            "Cancer conversion rate",
            "cancer_conversion_rate",
            "kpi_strip",
            0, 2, 3, 2,
            section="Outcomes",
            page_id=pid,
            story=_story(
                "2WW referrals resulting in confirmed cancer",
                "conversion_pct",
            ),
        ),
        _tile(
            "Early-stage detection rate",
            "early_stage_detection_rate",
            "kpi_strip",
            3, 2, 3, 2,
            section="Outcomes",
            page_id=pid,
            story=_story(
                "Cancer cases detected at stage 1 or 2",
                "early_stage_pct",
                threshold_label="75% ambition",
                threshold_value=75,
            ),
        ),
        _tile(
            "Pathway completion rate",
            "referral_completion_rate",
            "kpi_strip",
            6, 2, 3, 2,
            section="Outcomes",
            page_id=pid,
        ),
        _tile(
            "Unactioned safety alerts",
            "unactioned_alerts_by_age",
            "bar_chart",
            9, 2, 3, 4,
            section="Safety",
            page_id=pid,
        ),
        _tile(
            "Referral volume over time",
            "episodes_over_time",
            "line_chart",
            0, 4, 9, 4,
            section="Volume trends",
            page_id=pid,
        ),
        _tile(
            "Referral route distribution",
            "referral_route_distribution",
            "bar_chart",
            0, 8, 6, 3,
            section="Pathway mix",
            page_id=pid,
        ),
        _tile(
            "Episodes by condition",
            "episode_count_by_condition",
            "bar_chart",
            6, 8, 6, 3,
            section="Pathway mix",
            page_id=pid,
        ),
    ]


def _pathway_tiles(
    page_id: str, condition: str, pathway_label: str
) -> list[dict]:
    # LONG FUNCTION: data declaration -- scorecard tiles for one cancer pathway
    return [
        _tile(
            f"{pathway_label} referral volume",
            "episode_count_by_condition",
            "bar_chart",
            0, 0, 3, 2,
            section="Volume",
            page_id=page_id,
            overrides={"condition_type": condition},
        ),
        _tile(
            "Guideline match rate",
            "referral_guideline_compliance_rate",
            "kpi_strip",
            3, 0, 3, 2,
            section="Volume",
            page_id=page_id,
            story=_story(
                "Referrals matching active NG12/local rules",
                "compliance_pct",
                threshold_label="80% target",
                threshold_value=80,
            ),
        ),
        _tile(
            "Straight-to-test rate",
            "referral_stt_rate",
            "kpi_strip",
            6, 0, 3, 2,
            section="Volume",
            page_id=page_id,
            story=_story(
                "Eligible referrals bypassing initial clinic slot",
                "stt_pct",
                threshold_label="40% target",
                threshold_value=40,
            ),
        ),
        _tile(
            "Completeness rate",
            "referral_completeness_rate",
            "kpi_strip",
            9, 0, 3, 2,
            section="Volume",
            page_id=page_id,
            story=_story("Referrals with all mandatory fields", "completeness_pct"),
        ),
        _tile(
            "Alternative pathway flagged",
            "referral_alternative_pathway_rate",
            "kpi_strip",
            0, 2, 3, 2,
            section="Quality signals",
            page_id=page_id,
        ),
        _tile(
            "Cancer conversion rate",
            "cancer_conversion_rate",
            "kpi_strip",
            3, 2, 3, 2,
            section="Quality signals",
            page_id=page_id,
        ),
        _tile(
            "Early-stage detection rate",
            "early_stage_detection_rate",
            "kpi_strip",
            6, 2, 3, 2,
            section="Quality signals",
            page_id=page_id,
        ),
        _tile(
            "Emergency presentation rate",
            "emergency_presentation_rate",
            "kpi_strip",
            9, 2, 3, 2,
            section="Quality signals",
            page_id=page_id,
        ),
        _tile(
            "Monthly referral trend",
            "episodes_over_time",
            "line_chart",
            0, 4, 12, 4,
            section="Trend",
            page_id=page_id,
        ),
        _tile(
            "Primary care interval",
            "primary_care_interval",
            "interval_plot",
            0, 8, 12, 4,
            section="Intervals",
            page_id=page_id,
            overrides={"condition_type": condition},
        ),
        _tile(
            "Diagnostic interval",
            "diagnostic_interval",
            "interval_plot",
            0, 12, 12, 4,
            section="Intervals",
            page_id=page_id,
            overrides={"condition_type": condition},
        ),
        _tile(
            "Referring practices",
            "referral_site_distribution",
            "bar_chart",
            0, 16, 6, 3,
            section="Practice breakdown",
            page_id=page_id,
        ),
        _tile(
            "Repeat referral patients",
            "repeat_referral_patients",
            "table",
            6, 16, 6, 4,
            section="Practice breakdown",
            page_id=page_id,
        ),
    ]


def _rework_tiles() -> list[dict]:
    pid = "pg-rework"
    return [
        _tile(
            "Completeness rate",
            "referral_completeness_rate",
            "kpi_strip",
            0, 0, 4, 2,
            section="Rework signals",
            page_id=pid,
            story=_story(
                "Low completeness drives most admin rework",
                "completeness_pct",
                threshold_label="90% target",
                threshold_value=90,
            ),
        ),
        _tile(
            "Alternative pathway flagged",
            "referral_alternative_pathway_rate",
            "kpi_strip",
            4, 0, 4, 2,
            section="Rework signals",
            page_id=pid,
        ),
        _tile(
            "Alert escalation rate",
            "alert_escalation_rate",
            "kpi_strip",
            8, 0, 4, 2,
            section="Rework signals",
            page_id=pid,
        ),
        _tile(
            "Patients with repeat referrals",
            "repeat_referral_patients",
            "table",
            0, 2, 6, 5,
            section="Repeat activity",
            page_id=pid,
        ),
        _tile(
            "Coding backlog by GP practice",
            "coding_backlog_by_site",
            "table",
            6, 2, 6, 5,
            section="Repeat activity",
            page_id=pid,
        ),
        _tile(
            "Referring practice volume",
            "referral_site_distribution",
            "bar_chart",
            0, 7, 6, 3,
            section="Practice analysis",
            page_id=pid,
        ),
        _tile(
            "Safety net alerts by type",
            "safety_net_alerts_by_type",
            "bar_chart",
            6, 7, 6, 3,
            section="Practice analysis",
            page_id=pid,
        ),
        _tile(
            "Unactioned alerts by age",
            "unactioned_alerts_by_age",
            "bar_chart",
            0, 10, 6, 4,
            section="Overdue items",
            page_id=pid,
        ),
        _tile(
            "Open episodes by age",
            "episode_open_age_distribution",
            "bar_chart",
            6, 10, 6, 4,
            section="Overdue items",
            page_id=pid,
        ),
    ]


def _governance_tiles() -> list[dict]:
    pid = "pg-gov"
    return [
        _tile(
            "Guideline match rate",
            "referral_guideline_compliance_rate",
            "kpi_strip",
            0, 0, 4, 2,
            section="Guideline fit",
            page_id=pid,
            story=_story(
                "Proportion of referrals with at least one active rule matched",
                "compliance_pct",
            ),
        ),
        _tile(
            "Alternative pathway rate",
            "referral_alternative_pathway_rate",
            "kpi_strip",
            4, 0, 4, 2,
            section="Guideline fit",
            page_id=pid,
        ),
        _tile(
            "Pathway completion rate",
            "referral_completion_rate",
            "kpi_strip",
            8, 0, 4, 2,
            section="Guideline fit",
            page_id=pid,
        ),
        _tile(
            "Referral route distribution",
            "referral_route_distribution",
            "bar_chart",
            0, 2, 6, 4,
            section="Pathway evidence",
            page_id=pid,
        ),
        _tile(
            "Pathway outcome distribution",
            "outcome_distribution",
            "bar_chart",
            6, 2, 6, 4,
            section="Pathway evidence",
            page_id=pid,
        ),
        _tile(
            "Cancer type distribution",
            "cancer_type_distribution",
            "bar_chart",
            0, 6, 6, 3,
            section="Diagnostic outcomes",
            page_id=pid,
        ),
        _tile(
            "Cancer stage at diagnosis",
            "cancer_stage_distribution",
            "bar_chart",
            6, 6, 6, 3,
            section="Diagnostic outcomes",
            page_id=pid,
        ),
        _tile(
            "Coding completeness",
            "coding_completeness",
            "kpi_strip",
            0, 9, 4, 2,
            section="Audit trail",
            page_id=pid,
        ),
        _tile(
            "Top coded conditions",
            "top_coded_conditions",
            "table",
            4, 9, 8, 4,
            section="Audit trail",
            page_id=pid,
        ),
        _tile(
            "Safety net alerts by type",
            "safety_net_alerts_by_type",
            "bar_chart",
            0, 13, 6, 3,
            section="Safety signals",
            page_id=pid,
        ),
        _tile(
            "Alert escalation rate",
            "alert_escalation_rate",
            "kpi_strip",
            6, 13, 6, 2,
            section="Safety signals",
            page_id=pid,
        ),
    ]


def _equity_tiles() -> list[dict]:
    pid = "pg-equity"
    return [
        _tile(
            "Referrals by IMD decile",
            "imd_distribution",
            "bar_chart",
            0, 0, 6, 4,
            section="Deprivation (CORE20)",
            page_id=pid,
            story=_story(
                "CORE20: bottom two deciles are the highest-need cohort",
                "imd_decile",
            ),
        ),
        _tile(
            "Referral age distribution",
            "patient_age_band_distribution",
            "bar_chart",
            6, 0, 6, 4,
            section="Demographics",
            page_id=pid,
        ),
        _tile(
            "Referral sex distribution",
            "patient_gender_distribution",
            "bar_chart",
            0, 4, 4, 3,
            section="Demographics",
            page_id=pid,
        ),
        _tile(
            "Conditions by deprivation quintile",
            "conditions_by_deprivation",
            "table",
            4, 4, 8, 4,
            section="Deprivation (CORE20)",
            page_id=pid,
        ),
        _tile(
            "Emergency presentation rate",
            "emergency_presentation_rate",
            "kpi_strip",
            0, 8, 4, 2,
            section="Equity outcomes",
            page_id=pid,
            story=_story(
                "Emergency presentation is a marker of delayed detection",
                "emergency_pct",
            ),
        ),
        _tile(
            "Early-stage detection rate",
            "early_stage_detection_rate",
            "kpi_strip",
            4, 8, 4, 2,
            section="Equity outcomes",
            page_id=pid,
        ),
        _tile(
            "Cancer conversion rate",
            "cancer_conversion_rate",
            "kpi_strip",
            8, 8, 4, 2,
            section="Equity outcomes",
            page_id=pid,
        ),
        _tile(
            "Referral volume by condition",
            "episode_count_by_condition",
            "bar_chart",
            0, 10, 6, 3,
            section="Volume by group",
            page_id=pid,
        ),
        _tile(
            "Pathway outcome distribution",
            "outcome_distribution",
            "bar_chart",
            6, 10, 6, 3,
            section="Volume by group",
            page_id=pid,
        ),
    ]


def _roi_tiles() -> list[dict]:
    pid = "pg-roi"
    return [
        _tile(
            "Guideline match rate",
            "referral_guideline_compliance_rate",
            "kpi_strip",
            0, 0, 3, 2,
            section="Avoidable activity inputs",
            page_id=pid,
            story=_story(
                "Non-compliant rate drives estimated avoidable diagnostic spend",
                "compliance_pct",
            ),
        ),
        _tile(
            "Completeness rate",
            "referral_completeness_rate",
            "kpi_strip",
            3, 0, 3, 2,
            section="Avoidable activity inputs",
            page_id=pid,
            story=_story(
                "Incomplete referrals drive admin rework cost",
                "completeness_pct",
            ),
        ),
        _tile(
            "Straight-to-test rate",
            "referral_stt_rate",
            "kpi_strip",
            6, 0, 3, 2,
            section="Avoidable activity inputs",
            page_id=pid,
            story=_story(
                "Missed STT = avoidable clinic slot consumed",
                "stt_pct",
            ),
        ),
        _tile(
            "Pathway completion rate",
            "referral_completion_rate",
            "kpi_strip",
            9, 0, 3, 2,
            section="Avoidable activity inputs",
            page_id=pid,
        ),
        _tile(
            "Primary care interval (days)",
            "primary_care_interval",
            "interval_plot",
            0, 2, 12, 4,
            section="Delay cost inputs",
            page_id=pid,
        ),
        _tile(
            "Diagnostic interval (days)",
            "diagnostic_interval",
            "interval_plot",
            0, 6, 12, 4,
            section="Delay cost inputs",
            page_id=pid,
        ),
        _tile(
            "Repeat referral patients",
            "repeat_referral_patients",
            "table",
            0, 10, 6, 4,
            section="Rework cost inputs",
            page_id=pid,
        ),
        _tile(
            "Coding backlog by GP practice",
            "coding_backlog_by_site",
            "table",
            6, 10, 6, 4,
            section="Rework cost inputs",
            page_id=pid,
        ),
    ]


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def build_all_tiles() -> list[dict]:
    """Combine all page tile lists into the full template tile array."""
    tiles: list[dict] = []
    tiles += _exec_tiles()
    tiles += _pathway_tiles("pg-gynae", _CONDITION["gynae"], "Gynae")
    tiles += _pathway_tiles("pg-lower-gi", _CONDITION["lower_gi"], "Lower GI")
    tiles += _pathway_tiles("pg-upper-gi", _CONDITION["upper_gi"], "Upper GI")
    tiles += _pathway_tiles("pg-breast", _CONDITION["breast"], "Breast")
    tiles += _rework_tiles()
    tiles += _governance_tiles()
    tiles += _equity_tiles()
    tiles += _roi_tiles()
    return tiles


# ---------------------------------------------------------------------------
# HTTP helpers (no third-party deps)
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
    """Create (or skip) the Referral Quality template and optionally publish it."""
    parser = argparse.ArgumentParser(description="Seed Referral Quality Audit template")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8001",
        help="Analytics API base URL",
    )
    args = parser.parse_args()
    base = args.base_url.rstrip("/") + "/analytics"
    api_key = os.environ.get("ANALYTICS_API_KEY", "")
    org_id = os.environ.get("RQ_ORG_ID", "")

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
        print(f"Creating '{TEMPLATE_TITLE}' template ({len(PAGES)} pages)...")
        tiles = build_all_tiles()
        print(f"  {len(tiles)} tiles across {len(PAGES)} pages")
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
        print("RQ_ORG_ID not set -- skipping publish. Set it to auto-publish to an org.")
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
