"""
Seed the NCDA audit template as the platform default.

Usage:
    python scripts/seed_ncda_template.py --base-url http://localhost:8001

This script POSTs to the analytics API to create the NCDA template and
publish it to the NCDA_ORG_ID org (if set). Safe to re-run - checks
for an existing "NCDA" title before creating.

Environment variables:
    ANALYTICS_API_KEY   - service-to-service key (or leave blank for local dev)
    NCDA_ORG_ID         - org ID to auto-publish the template to (optional)
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error


def _headers(api_key: str) -> dict:
    h = {"Content-Type": "application/json"}
    if api_key:
        h["X-API-Key"] = api_key
    return h


def _post(base: str, path: str, body: dict, api_key: str) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{base}{path}", data=data, headers=_headers(api_key), method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def _get(base: str, path: str, api_key: str) -> dict | list:
    req = urllib.request.Request(
        f"{base}{path}", headers=_headers(api_key)
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def build_ncda_tiles() -> list[dict]:
    """
    Map NCDA audit sections to metric tiles with appropriate positions.
    Each tile omits tile_id (server assigns it).
    """
    # LONG FUNCTION: data declaration -- one entry per NCDA section tile
    return [
        # -- Summary / Overview -----------------------------------------------
        {
            "label": "Total patients",
            "tile_type": "kpi_strip",
            "metric_id": "patient_count",
            "param_overrides": {},
            "layout": {"x": 0, "y": 0, "w": 3, "h": 2},
        },
        {
            "label": "Episode status breakdown",
            "tile_type": "bar_chart",
            "metric_id": "episode_count_by_status",
            "param_overrides": {},
            "layout": {"x": 3, "y": 0, "w": 4, "h": 3},
        },
        {
            "label": "Episodes over time",
            "tile_type": "line_chart",
            "metric_id": "episodes_over_time",
            "param_overrides": {},
            "layout": {"x": 7, "y": 0, "w": 5, "h": 3},
        },
        # -- Cancer characteristics -------------------------------------------
        {
            "label": "Cancer type distribution",
            "tile_type": "bar_chart",
            "metric_id": "cancer_type_distribution",
            "param_overrides": {},
            "layout": {"x": 0, "y": 3, "w": 6, "h": 3},
        },
        {
            "label": "Cancer stage distribution",
            "tile_type": "bar_chart",
            "metric_id": "cancer_stage_distribution",
            "param_overrides": {},
            "layout": {"x": 6, "y": 3, "w": 6, "h": 3},
        },
        # -- Conditions -------------------------------------------------------
        {
            "label": "Episodes by condition",
            "tile_type": "bar_chart",
            "metric_id": "episode_count_by_condition",
            "param_overrides": {},
            "layout": {"x": 0, "y": 6, "w": 6, "h": 3},
        },
        {
            "label": "Top coded conditions",
            "tile_type": "table",
            "metric_id": "top_coded_conditions",
            "param_overrides": {},
            "layout": {"x": 0, "y": 9, "w": 12, "h": 4},
        },
        # -- Referral pathways ------------------------------------------------
        {
            "label": "Referral route distribution",
            "tile_type": "bar_chart",
            "metric_id": "referral_route_distribution",
            "param_overrides": {},
            "layout": {"x": 0, "y": 13, "w": 6, "h": 3},
        },
        {
            "label": "Referral site distribution",
            "tile_type": "bar_chart",
            "metric_id": "referral_site_distribution",
            "param_overrides": {},
            "layout": {"x": 6, "y": 13, "w": 6, "h": 3},
        },
        {
            "label": "Place of presentation",
            "tile_type": "bar_chart",
            "metric_id": "place_of_presentation",
            "param_overrides": {},
            "layout": {"x": 0, "y": 16, "w": 6, "h": 3},
        },
        # -- Intervals --------------------------------------------------------
        {
            "label": "Primary care interval",
            "tile_type": "interval_plot",
            "metric_id": "primary_care_interval",
            "param_overrides": {},
            "layout": {"x": 0, "y": 19, "w": 12, "h": 4},
        },
        {
            "label": "Diagnostic interval",
            "tile_type": "interval_plot",
            "metric_id": "diagnostic_interval",
            "param_overrides": {},
            "layout": {"x": 0, "y": 23, "w": 12, "h": 4},
        },
        # -- Quality & safety -------------------------------------------------
        {
            "label": "Coding completeness",
            "tile_type": "kpi_strip",
            "metric_id": "coding_completeness",
            "param_overrides": {},
            "layout": {"x": 0, "y": 27, "w": 4, "h": 2},
        },
        {
            "label": "Safety net alerts by type",
            "tile_type": "bar_chart",
            "metric_id": "safety_net_alerts_by_type",
            "param_overrides": {},
            "layout": {"x": 4, "y": 27, "w": 8, "h": 3},
        },
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed NCDA audit template")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8001",
        help="Analytics API base URL",
    )
    args = parser.parse_args()
    base = args.base_url.rstrip("/") + "/analytics"
    api_key = os.environ.get("ANALYTICS_API_KEY", "")
    org_id = os.environ.get("NCDA_ORG_ID", "")

    print("Checking for existing NCDA template...")
    try:
        templates = _get(base, "/audit-templates", api_key)
    except urllib.error.HTTPError as exc:
        print(f"ERROR: GET /audit-templates -> {exc.code} {exc.reason}", file=sys.stderr)
        sys.exit(1)

    existing = next(
        (t for t in templates if t.get("title") == "NCDA Audit Report"), None
    )
    if existing:
        template_id = existing["template_id"]
        print(f"Found existing template: {template_id} (status={existing['status']})")
    else:
        print("Creating NCDA template...")
        payload = {
            "title": "NCDA Audit Report",
            "tiles": build_ncda_tiles(),
        }
        try:
            created = _post(base, "/audit-templates", payload, api_key)
            template_id = created["template_id"]
            print(f"Created template: {template_id}")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode()
            print(f"ERROR creating template: {exc.code} {body}", file=sys.stderr)
            sys.exit(1)

    if org_id:
        print(f"Publishing to org: {org_id}...")
        pub_payload = {
            "template_id": template_id,
            "scope_type": "org",
            "scope_id": org_id,
        }
        try:
            result = _post(
                base,
                f"/audit-templates/{template_id}/publish",
                pub_payload,
                api_key,
            )
            print(f"Published: assignment_id={result.get('assignment_id')}")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode()
            print(f"WARN: publish failed: {exc.code} {body}", file=sys.stderr)
    else:
        print("NCDA_ORG_ID not set -- skipping publish step.")

    print("Done.")


if __name__ == "__main__":
    main()
