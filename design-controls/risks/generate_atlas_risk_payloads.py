"""
Generate Atlas risk creation payloads from FMEA CSV.

Produces two output files:
  - atlas_risk_payloads_gap.json   -- 63 new risks (GAP rows) ready to POST
  - atlas_risk_payloads_existing.json -- 31 existing risks (EXISTING rows) for reference

Each entry has:
  - "create"  : body for POST /api/risks
  - "link_un" : body for POST /api/risks/:id/links  (HAS_RISK from UN)
  - "link_dis": body for POST /api/risks/:id/links  (MITIGATES from DIs, where known)

Run: python generate_atlas_risk_payloads.py
"""

import csv
import json
import re
from pathlib import Path

PRODUCT_ID = "PROD-LEO-CORE-AI-20260415-6AE8A23B"

SEVERITY_MAP = {
    1: "negligible",
    2: "minor",
    3: "serious",
    4: "critical",
    5: "catastrophic",
}

PROBABILITY_MAP = {
    1: "remote",
    2: "unlikely",
    3: "possible",
    4: "likely",
    5: "almost_certain",
}

RISK_LEVEL_MAP = {
    (1, "low"): "low",
    (2, "low"): "low",
}


def rpn_to_level(rpn: int) -> str:
    if rpn <= 10:
        return "low"
    if rpn <= 20:
        return "medium"
    if rpn <= 40:
        return "high"
    return "critical"


DOMAIN_TO_CATEGORY = {
    "NLP Core": "clinical_safety",
    "Clinical Governance": "clinical_safety",
    "Data Protection": "data_protection",
    "Clinical Safety": "clinical_safety",
    "Clinical Decision Support": "clinical_safety",
    "Model Training": "clinical_safety",
    "Model Deployment": "clinical_safety",
    "Knowledge Base": "clinical_safety",
    "Platform": "availability",
    "Analytics": "clinical_safety",
    "Developer Platform": "security",
    "Security": "security",
    "Interoperability": "clinical_safety",
}


def parse_int(val: str, default: int = 1) -> int:
    try:
        return int(val.strip())
    except (ValueError, AttributeError):
        return default


def split_ids(val: str) -> list[str]:
    """Split space- or comma-separated ID lists."""
    if not val or not val.strip():
        return []
    return [x.strip() for x in re.split(r"[\s,]+", val.strip()) if x.strip()]


def build_payload(row: dict) -> dict:
    s = parse_int(row["S"])
    p = parse_int(row["P"])
    d = parse_int(row["D"])
    rpn = parse_int(row["RPN"], default=s * p * d)

    hazard_description = (
        f"{row['Failure_Mode']}. Caused by: {row['Failure_Cause']}"
    )
    harm_description = row["Failure_Effect"]

    create_body = {
        "product_id": PRODUCT_ID,
        "title": row["Failure_Mode"],
        "description": (
            f"UN: {row['UN_Short_Title']} ({row['UN_ID']}). "
            f"Effect: {row['Failure_Effect']}. "
            f"Cause: {row['Failure_Cause']}"
        ),
        "hazard_description": hazard_description,
        "hazard_category": DOMAIN_TO_CATEGORY.get(row["Domain"], "clinical_safety"),
        "hazardous_situation": row["Failure_Cause"],
        "harm_description": harm_description,
        "harm_severity": SEVERITY_MAP.get(s, "serious"),
        "initial_severity": s,
        "initial_probability": p,
        "initial_detectability": d,
        "safety_class": row["Safety_Class"],
        "status": "identified",
        "tags": [
            row["Domain"].lower().replace(" ", "_"),
            row["UN_Short_Title"].lower().replace(" ", "_"),
        ],
        "identified_by": "FMEA-workshop-draft-2026-04-16",
        "identified_date": "2026-04-16",
        "_fmea_id": row["FMEA_ID"],
        "_rpn": rpn,
        "_risk_level": rpn_to_level(rpn),
        "_priority": row["Priority"],
        "_workshop_notes": row["Notes_for_Workshop"],
    }

    link_un = {
        "target_ids": [row["UN_ID"]],
        "relationship": "HAS_RISK",
    }

    di_ids = split_ids(row.get("Mitigating_DIs_Atlas", ""))
    link_dis = (
        {
            "target_ids": di_ids,
            "relationship": "MITIGATES",
        }
        if di_ids
        else None
    )

    return {
        "fmea_id": row["FMEA_ID"],
        "un_id": row["UN_ID"],
        "un_title": row["UN_Short_Title"],
        "workshop_status": row["Workshop_Status"],
        "existing_r_ids": split_ids(row.get("Existing_R_IDs", "")),
        "create": create_body,
        "link_un": link_un,
        "link_dis": link_dis,
    }


def main() -> None:
    script_dir = Path(__file__).parent
    csv_path = script_dir / "FMEA-LEO-AI-CORE-workshop-draft.csv"

    gap_payloads: list[dict] = []
    existing_payloads: list[dict] = []

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row.get("FMEA_ID"):
                continue
            payload = build_payload(row)
            if row["Workshop_Status"] == "GAP":
                gap_payloads.append(payload)
            else:
                existing_payloads.append(payload)

    gap_path = script_dir / "atlas_risk_payloads_gap.json"
    existing_path = script_dir / "atlas_risk_payloads_existing.json"

    with gap_path.open("w", encoding="utf-8") as f:
        json.dump(gap_payloads, f, indent=2)

    with existing_path.open("w", encoding="utf-8") as f:
        json.dump(existing_payloads, f, indent=2)

    print(f"GAP payloads:      {len(gap_payloads):>3}  ->  {gap_path.name}")
    print(f"EXISTING payloads: {len(existing_payloads):>3}  ->  {existing_path.name}")
    print()
    print("Next step: once Atlas enhanced endpoint is deployed, run:")
    print("  python fire_atlas_risks.py --file atlas_risk_payloads_gap.json")


if __name__ == "__main__":
    main()
