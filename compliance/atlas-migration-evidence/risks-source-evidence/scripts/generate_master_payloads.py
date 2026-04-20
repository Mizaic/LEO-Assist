"""
Generate Atlas risk creation payloads from the consolidated master risk list.

Reads MASTER-RISK-LIST.csv and produces atlas_master_payloads.json, which is
a single ordered list of risks to fire at Atlas. Each entry contains:
  - create        : body for POST /api/risks (all ISO 14971 fields)
  - link_uns      : HAS_RISK from each UN in UN_IDs
  - link_dis      : MITIGATES from each DI in Mitigating_DIs

Run:
  python3 generate_master_payloads.py
"""

import csv
import json
import re
from pathlib import Path

PRODUCT_ID = "PROD-LEO-CORE-AI-20260415-6AE8A23B"

SEVERITY_LABEL = {
    "1": "negligible", "2": "minor", "3": "serious",
    "4": "critical", "5": "catastrophic",
}
PROBABILITY_LABEL = {
    "1": "remote", "2": "unlikely", "3": "possible",
    "4": "likely", "5": "almost_certain",
}


def rpn_to_level(rpn: int) -> str:
    if rpn <= 10:
        return "low"
    if rpn <= 20:
        return "medium"
    if rpn <= 40:
        return "high"
    return "critical"


def load_yaml_details(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def split_ids(val: str) -> list[str]:
    if not val or not val.strip():
        return []
    if "TBD" in val:
        return []
    return [x.strip() for x in re.split(r"[\s,]+", val.strip()) if x.strip()]


def build_create_body(row: dict, yaml_data: dict | None) -> dict:
    s = row["S"] or (yaml_data.get("S") if yaml_data else "3") or "3"
    p = row["P"] or (yaml_data.get("P") if yaml_data else "3") or "3"
    d = row["D"] or (yaml_data.get("D") if yaml_data else "2") or "2"

    try:
        s_i, p_i, d_i = int(s), int(p), int(d)
    except ValueError:
        s_i, p_i, d_i = 3, 3, 2
    rpn = s_i * p_i * d_i

    hazard_desc = row["Hazardous_Situation"] or ""
    if yaml_data:
        hs = yaml_data.get("hazardous_situation", "")
        hs = re.split(r"\n\s*(harm|initial_risk_estimate|mitigation):", hs)[0]
        hazard_desc = hs.strip().strip('"').replace("\n", " ")[:500] or hazard_desc

    harm_desc = ""
    if yaml_data:
        harm = yaml_data.get("harm_description", "")
        harm = re.split(r"\n\s*severity:", harm)[0]
        harm_desc = harm.strip().strip('"').replace("\n", " ")[:400]

    category = "software_defect"
    title_lower = row["Title"].lower()
    if any(x in title_lower for x in ("pii", "phi", "confidential", "data breach")):
        category = "security_breach"
    elif any(x in title_lower for x in ("tenant", "unauthoris", "cve", "injection")):
        category = "security_breach"
    elif any(x in title_lower for x in ("accessibility", "vestibul", "screen reader")):
        category = "misuse"
    elif "unavailable" in title_lower or "outage" in title_lower:
        category = "infrastructure_failure"

    return {
        "product_id": PRODUCT_ID,
        "title": row["Title"],
        "description": (
            f"Source: {row['Source']}. "
            f"FMEA: {row['Source_FMEA_IDs'] or 'n/a'}. {row['Notes']}"
        )[:500],
        "hazard_description": hazard_desc[:500],
        "hazard_category": category,
        "hazardous_situation": hazard_desc[:500],
        "harm_description": harm_desc or hazard_desc[:300],
        "harm_severity": SEVERITY_LABEL.get(s, "serious"),
        "initial_severity": SEVERITY_LABEL.get(s, "serious"),
        "initial_probability": PROBABILITY_LABEL.get(p, "possible"),
        "initial_detectability": d_i,
        "initial_rpn": rpn,
        "safety_class": row["Safety_Class"] or "B",
        "status": "identified",
        "identified_by": "LEO-AI-CORE FMEA master list 2026-04-16",
        "identified_date": "2026-04-16",
        "tags": _build_tags(row, yaml_data),
        "monitoring_plan": (
            "Monitor via DQ dashboards, coding quality alerts, and post-market "
            "surveillance. Review quarterly at hazard workshop."
        ),
        "monitoring_metrics": ["RPN trend", "Incident count", "Mitigation effectiveness"],
        "review_frequency": "Quarterly",
        "mitigation_control_type": "protective_measure",
        "mitigation_effectiveness": "pending",
        "mitigation_measures_detail": (
            row["Notes"][:300] if row["Notes"] else
            "Refer to linked DIs via MITIGATES edges"
        ),
        # -- internal metadata, stripped before firing --
        "_master_id": row["Master_ID"],
        "_proposed_r_id": row["Atlas_R_ID"],
        "_action": row["Action"],
        "_source": row["Source"],
        "_rpn_level": rpn_to_level(rpn),
    }


def _build_tags(row: dict, yaml_data: dict | None) -> list[str]:
    tags = [row["Source"].lower()]
    if yaml_data and yaml_data.get("tags"):
        tags.extend(yaml_data["tags"][:5])
    if row["Source_FMEA_IDs"]:
        tags.append(row["Source_FMEA_IDs"].split()[0].lower())
    return tags[:10]


def build_payload(row: dict, yaml_details: dict) -> dict:
    yaml_data = yaml_details.get(row["Atlas_R_ID"])
    create = build_create_body(row, yaml_data)

    un_ids = split_ids(row["UN_IDs"])
    di_ids = split_ids(row["Mitigating_DIs"])

    return {
        "master_id": row["Master_ID"],
        "atlas_r_id": row["Atlas_R_ID"],
        "action": row["Action"],
        "source": row["Source"],
        "create": create,
        "link_uns": {"target_ids": un_ids, "relationship": "HAS_RISK"} if un_ids else None,
        "link_dis": {"target_ids": di_ids, "relationship": "MITIGATES"} if di_ids else None,
    }


def main() -> None:
    script_dir = Path(__file__).parent
    master_csv = script_dir / "MASTER-RISK-LIST.csv"
    yaml_json = script_dir / "all_yaml_risks_extracted.json"

    yaml_details = load_yaml_details(yaml_json)

    payloads: list[dict] = []
    with master_csv.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            payloads.append(build_payload(row, yaml_details))

    out_path = script_dir / "atlas_master_payloads.json"
    with out_path.open("w") as f:
        json.dump(payloads, f, indent=2)

    # -- Summary stats --
    total = len(payloads)
    with_un = sum(1 for p in payloads if p["link_uns"])
    with_di = sum(1 for p in payloads if p["link_dis"])
    tbd_un = total - with_un
    tbd_di = total - with_di
    un_link_count = sum(
        len(p["link_uns"]["target_ids"]) for p in payloads if p["link_uns"]
    )
    di_link_count = sum(
        len(p["link_dis"]["target_ids"]) for p in payloads if p["link_dis"]
    )

    print(f"Master payloads:              {total}")
    print(f"  With UN links:              {with_un}  ({un_link_count} total HAS_RISK edges)")
    print(f"  With DI links:              {with_di}  ({di_link_count} total MITIGATES edges)")
    print(f"  TBD UN (workshop needed):   {tbd_un}")
    print(f"  TBD DI (workshop needed):   {tbd_di}")
    print(f"Output: {out_path.name}")


if __name__ == "__main__":
    main()
