"""
Generate post-workshop Atlas payloads from MASTER-RISK-LIST-FINAL.csv.

Differences from generate_master_payloads.py:
- Uses revised S/P/D from Clinical Safety Lead review
- Includes residual risk fields where a specialist reviewed it
- Respects Class C escalations -> safety_class="C" triggers VAL requirement note
- Carries production_blocker, missing_controls, and stride/wcag metadata
"""

import csv
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
PRODUCT_ID = "PROD-LEO-CORE-AI-20260415-6AE8A23B"
CSV_PATH = HERE / "MASTER-RISK-LIST-FINAL.csv"
OUT_PATH = HERE / "atlas_master_payloads_final.json"
YAML_INDEX = HERE / "all_yaml_risks_extracted.json"

SEV_LABEL = {"1": "negligible", "2": "minor", "3": "serious",
             "4": "critical", "5": "catastrophic"}
PROB_LABEL = {"1": "improbable", "2": "remote", "3": "occasional",
              "4": "probable", "5": "frequent"}
SEV_NUM = {v: k for k, v in SEV_LABEL.items()}
PROB_NUM = {v: k for k, v in PROB_LABEL.items()}
LEGACY_PROB_TO_NUM = {
    "remote": "1", "unlikely": "2", "possible": "3",
    "likely": "4", "almost_certain": "5",
    "improbable": "1", "occasional": "3", "probable": "4", "frequent": "5",
}
LEGACY_ACCEPT_MAP = {
    "acceptable": "acceptable",
    "conditionally_acceptable": "alarp",
    "alarp": "alarp",
    "unacceptable": "unacceptable",
}


def rpn_to_level(rpn: int) -> str:
    if rpn <= 10:
        return "low"
    if rpn <= 20:
        return "medium"
    if rpn <= 40:
        return "high"
    return "unacceptable"


def _to_score(value: str, vocab: dict[str, str]) -> int | None:
    if value is None:
        return None
    v = str(value).strip()
    if not v:
        return None
    if v.isdigit():
        n = int(v)
        return n if 1 <= n <= 5 else None
    n = vocab.get(v.lower())
    if n is None:
        return None
    return int(n)


def _yaml_data() -> dict:
    if not YAML_INDEX.exists():
        return {}
    with YAML_INDEX.open() as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data
    return {y["id"]: y for y in data}


def _derive_hazard_category(title: str, stride: str) -> str:
    title_lower = title.lower()
    if stride:
        if "I" in stride or "S" in stride or "E" in stride:
            return "security_breach"
    sec_kw = ("pii", "phi", "confidential", "data breach", "tenant",
              "unauthoris", "cve", "injection", "audit trail")
    if any(x in title_lower for x in sec_kw):
        return "security_breach"
    ux_kw = ("accessibility", "vestibul", "screen reader", "misread",
             "misinterpret")
    if any(x in title_lower for x in ux_kw):
        return "misuse"
    if "unavailable" in title_lower or "outage" in title_lower:
        return "infrastructure_failure"
    if "drift" in title_lower or "degrad" in title_lower:
        return "performance_degradation"
    return "software_defect"


def _build_tags(row: dict) -> list[str]:
    tags = [t.strip() for t in (row.get("Tags", "") or "").split(",")
            if t.strip()]
    tags.append("draft_pending_qa_signoff")
    tags.append(f"workshop_decision_{row['Safety_Review_Decision']}")
    tags.append(f"control_adequacy_{row['Control_Adequacy']}")
    if row.get("Needs_VAL") == "yes":
        tags.append("requires_VAL")
    if row.get("Production_Blocker") == "yes":
        tags.append("production_blocker")
    stride = row.get("STRIDE_Categories", "")
    if stride:
        tags.append(f"stride_{stride.replace(',', '_')}")
    if (row.get("Safety_Class") or "").upper() == "C":
        tags.append("workshop_originally_class_c_capped_to_B")
    return sorted(set(tags))


def _clean_yaml_scalar(text: str) -> str:
    """Strip leftover YAML structure (trailing indented keys, surrounding quotes)
    that leaked into extracted block scalars."""
    if not text:
        return ""
    # Cut off at first occurrence of trailing indented YAML key
    cut = re.split(r"\n\s+[a-z_]+:\s*", text, maxsplit=1)[0]
    cut = cut.strip()
    # Strip wrapping straight quotes if balanced
    if len(cut) >= 2 and cut[0] == cut[-1] and cut[0] in ('"', "'"):
        cut = cut[1:-1].strip()
    # Collapse whitespace
    cut = re.sub(r"\s+", " ", cut)
    return cut


def _hazard_description(row: dict, yaml_data: dict | None) -> str:
    yaml_haz = _clean_yaml_scalar((yaml_data or {}).get("hazard_description", ""))
    if yaml_haz and len(yaml_haz) > 10:
        return yaml_haz[:500]
    return (row.get("Hazardous_Situation") or "")[:500]


def _harm_description(row: dict, yaml_data: dict | None) -> str:
    yaml_harm = _clean_yaml_scalar((yaml_data or {}).get("harm_description", ""))
    if yaml_harm and len(yaml_harm) > 10:
        return yaml_harm[:500]
    return (row.get("Hazardous_Situation") or "")[:300]


def _residual_body(row: dict) -> dict | None:
    sev_raw = row.get("Residual_Severity", "")
    prob_raw = row.get("Residual_Probability", "")
    det_raw = row.get("Residual_Detectability", "")
    accept_raw = (row.get("Residual_Acceptability", "") or "").strip().lower()
    if not (sev_raw and prob_raw and det_raw and accept_raw):
        return None
    s_n = _to_score(sev_raw, SEV_NUM)
    p_n = _to_score(prob_raw, LEGACY_PROB_TO_NUM)
    try:
        d_n = int(det_raw)
    except (TypeError, ValueError):
        return None
    if s_n is None or p_n is None:
        return None
    accept = LEGACY_ACCEPT_MAP.get(accept_raw, "alarp")
    rpn = s_n * p_n * d_n
    return {
        "residual_severity": s_n,
        "residual_probability": p_n,
        "residual_detectability": d_n,
        "residual_rpn": rpn,
        "residual_risk_level": rpn_to_level(rpn),
        "residual_acceptability": accept,
        "residual_justification": (
            f"Workshop residual (reviewed by "
            f"{row.get('Specialist_Review_Framework','clinical')}). "
            f"Missing controls: {row.get('Missing_Controls','')[:200]}"
        )[:500],
    }


def build_create_body(row: dict, yaml_data: dict | None) -> dict:
    s_raw = row["Revised_S"] or row["S"]
    p_raw = row["Revised_P"] or row["P"]
    d_raw = row["Revised_D"] or row["D"]
    s_n = _to_score(s_raw, SEV_NUM) or 3
    p_n = _to_score(p_raw, LEGACY_PROB_TO_NUM) or 3
    try:
        d_n = int(d_raw) if str(d_raw).strip().isdigit() else 3
    except (TypeError, ValueError):
        d_n = 3
    rpn = s_n * p_n * d_n

    category = _derive_hazard_category(
        row["Title"], row.get("STRIDE_Categories", ""))
    hazard_desc = _hazard_description(row, yaml_data)
    harm_desc = _harm_description(row, yaml_data)
    body = {
        "product_id": PRODUCT_ID,
        "title": row["Title"],
        "description": (
            f"Source: {row['Source']}. FMEA: "
            f"{row['Source_FMEA_IDs'] or 'n/a'}. "
            f"Workshop: {row['Safety_Review_Decision']}. "
            f"Control adequacy: {row['Control_Adequacy']}. "
            f"{row['Notes']}"
        )[:500],
        "hazard_description": hazard_desc,
        "hazard_category": category,
        "hazardous_situation": hazard_desc,
        "harm_description": harm_desc,
        "harm_severity": SEV_LABEL.get(str(s_n), "serious"),
        "initial_severity": s_n,
        "initial_probability": p_n,
        "initial_detectability": d_n,
        "initial_rpn": rpn,
        "safety_class": "B" if (row["Safety_Class"] or "B").upper() == "C"
        else (row["Safety_Class"] or "B"),
        "status": "Identified",
        "identified_by": (
            "LEO-AI-CORE Hazard Workshop 2026-04-16 "
            "(AI panel, facilitated by Rob Smith)"
        ),
        "identified_date": "2026-04-16",
        "tags": _build_tags(row),
        "monitoring_plan": (
            "Monitor via DQ dashboards, incident management system, and "
            "quarterly RPN trend review at Clinical Safety Committee. "
            f"Specialist framework: "
            f"{row.get('Specialist_Review_Framework','clinical safety')}"
        )[:500],
        "monitoring_metrics": [
            "RPN trend",
            "Incident count",
            "Mitigation effectiveness",
            "Post-market surveillance reports",
        ],
        "review_frequency": "Quarterly",
        "mitigation_control_type": "protective_measure",
        "mitigation_effectiveness": (
            "effective" if row["Control_Adequacy"] == "adequate"
            else "partially_effective"
            if row["Control_Adequacy"] == "partial" else "not_effective"
        ),
        "mitigation_measures_detail": (
            row["Notes"][:300] if row["Notes"]
            else "Refer to linked DIs via MITIGATES edges"
        ),
    }
    residual = _residual_body(row)
    if residual:
        body.update(residual)
    missing = row.get("Missing_Controls", "")
    if missing:
        body["mitigation_measures_detail"] = (
            f"{body['mitigation_measures_detail']} | "
            f"ADDITIONAL CONTROLS REQUIRED: {missing[:300]}"
        )[:500]
    body.update({
        "_master_id": row["Master_ID"],
        "_proposed_r_id": row["Atlas_R_ID"],
        "_action": row["Action"],
        "_source": row["Source"],
        "_rpn_level": rpn_to_level(rpn),
        "_needs_val": row.get("Needs_VAL", "no"),
        "_production_blocker": row.get("Production_Blocker", "no"),
        "_wcag_criteria": row.get("WCAG_Criteria", ""),
        "_stride_categories": row.get("STRIDE_Categories", ""),
    })
    return body


def build_payload(row: dict, yaml_index: dict) -> dict:
    rid = row["Atlas_R_ID"]
    yaml_data = yaml_index.get(rid)
    body = build_create_body(row, yaml_data)
    un_ids = [u for u in row["UN_IDs"].split()
              if u and not u.startswith("NEW_UN_NEEDED")
              and not u.startswith("TBD")]
    di_ids = [d for d in row["Mitigating_DIs"].split()
              if d and not d.startswith("NEW_DI_NEEDED")
              and not d.startswith("TBD")]
    return {
        "master_id": row["Master_ID"],
        "atlas_r_id": rid,
        "action": row["Action"],
        "source": row["Source"],
        "workshop_decision": row["Safety_Review_Decision"],
        "needs_new_un": "NEW_UN_NEEDED" in row["UN_IDs"],
        "needs_new_di": "NEW_DI_NEEDED" in row["Mitigating_DIs"],
        "create": body,
        "link_uns": {
            "target_ids": un_ids, "relationship": "HAS_RISK"
        } if un_ids else None,
        "link_dis": {
            "target_ids": di_ids, "relationship": "MITIGATES"
        } if di_ids else None,
    }


def main() -> None:
    yaml_index = _yaml_data()
    with CSV_PATH.open() as f:
        rows = list(csv.DictReader(f))
    payloads = [build_payload(r, yaml_index) for r in rows]
    with OUT_PATH.open("w") as f:
        json.dump(payloads, f, indent=2)

    with_uns = sum(1 for p in payloads if p["link_uns"])
    with_dis = sum(1 for p in payloads if p["link_dis"])
    with_residual = sum(1 for p in payloads
                        if p["create"].get("residual_severity"))
    class_c = sum(1 for p in payloads
                  if p["create"]["safety_class"] == "C")
    blockers = sum(1 for p in payloads
                   if p["create"].get("_production_blocker") == "yes")
    needs_new_un = sum(1 for p in payloads if p["needs_new_un"])
    needs_new_di = sum(1 for p in payloads if p["needs_new_di"])

    print(f"Final payloads:       {len(payloads)}")
    print(f"  With UN links:      {with_uns}")
    print(f"  With DI links:      {with_dis}")
    print(f"  With residual risk: {with_residual}")
    print(f"  Class C:            {class_c}")
    print(f"  Production blockers:{blockers}")
    print(f"  Needs new UN:       {needs_new_un}")
    print(f"  Needs new DI:       {needs_new_di}")
    print(f"Output: {OUT_PATH.name}")


if __name__ == "__main__":
    main()
