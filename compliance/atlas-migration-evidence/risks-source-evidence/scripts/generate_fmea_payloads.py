"""
Generate Atlas FMEA-flow payloads from MASTER-RISK-LIST-FINAL.csv.

Emits one record per master row with three sub-payloads:

    - add_fmea_item   (1-10 S/O/D, no traceability fields)
    - update_risk     (1-5 S/P/D, rich ISO 14971 enrichment)
    - links           (UN HAS_RISK + DI MITIGATES)

The fire script consumes this file and orchestrates the four-step Atlas
sequence per row: add_fmea_item -> promote_fmea_item_to_risk ->
update_risk -> link_design_controls (x2).

Design notes on the 1-10 vs 1-5 asymmetry:
    - FMEA convention: 1-10 (we 2x our 1-5 master to preserve ordering).
    - ISO 14971 5x5 matrix: 1-5 (passed through unchanged on update_risk).
"""

import csv
import json
import re
from pathlib import Path

import yaml

import di_matcher

HERE = Path(__file__).parent
PRODUCT_ID = "PROD-LEO-CORE-AI-20260415-6AE8A23B"
WORKSHOP_ID = "fdb999d8-27c3-4e22-b871-5d5d4d2a49d7"
CSV_PATH = HERE / "MASTER-RISK-LIST-FINAL.csv"
YAML_INDEX = HERE / "all_yaml_risks_extracted.json"
ATLAS_INDEX = HERE / "_atlas_index.json"
OUT_PATH = HERE / "atlas_fmea_payloads.json"
DI_REPORT_PATH = HERE / "di_mapping_report.csv"

# Cache of fully-parsed YAML risk blocks keyed by R-LEO-AI-NNN id. Populated
# lazily by _yaml_block_for; supplies residual_risk_estimate that the legacy
# regex-based all_yaml_risks_extracted.json does not include.
_YAML_BLOCKS: dict[str, dict] = {}

DI_MATCH_TOP_N = 5
DI_MATCH_MIN_SCORE = 0.30

SEV_LABEL_5 = {1: "negligible", 2: "minor", 3: "serious",
               4: "critical", 5: "catastrophic"}
SEV_NUM_5 = {v: k for k, v in SEV_LABEL_5.items()}
PROB_NUM_5 = {
    "improbable": 1, "remote": 2, "occasional": 3, "probable": 4,
    "frequent": 5, "unlikely": 2, "possible": 3, "likely": 4,
    "almost_certain": 5,
}
ACCEPT_MAP = {
    "acceptable": "acceptable",
    "alarp": "alarp",
    "conditionally_acceptable": "alarp",
    "unacceptable": "unacceptable",
}
EFFECTIVENESS_MAP = {
    "adequate": "effective",
    "partial": "partially_effective",
    "gap": "not_effective",
}


def _to_int_5(value: str, vocab: dict[str, int]) -> int | None:
    if value is None:
        return None
    v = str(value).strip()
    if not v:
        return None
    if v.isdigit():
        n = int(v)
        return n if 1 <= n <= 5 else None
    return vocab.get(v.lower())


def _scale_to_10(score_5: int) -> int:
    return min(10, max(1, score_5 * 2))


def rpn_to_level(rpn: int, max_rpn: int = 125) -> str:
    """Bucket an RPN into low/medium/high/unacceptable. Defaults to 5x5x5."""
    pct = rpn / max_rpn
    if pct <= 0.10:
        return "low"
    if pct <= 0.25:
        return "medium"
    if pct <= 0.50:
        return "high"
    return "unacceptable"


def _clean_yaml_scalar(text: str) -> str:
    """Strip leftover YAML structure (trailing indented keys, surrounding quotes)
    that leaked into block scalars during YAML extraction."""
    if not text:
        return ""
    cut = re.split(r"\n\s+[a-z_]+:\s*", text, maxsplit=1)[0].strip()
    if len(cut) >= 2 and cut[0] == cut[-1] and cut[0] in ('"', "'"):
        cut = cut[1:-1].strip()
    return re.sub(r"\s+", " ", cut)


def _yaml_data() -> dict:
    if not YAML_INDEX.exists():
        return {}
    with YAML_INDEX.open() as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data
    return {y["id"]: y for y in data}


COMPONENT_RULES = [
    ("Accessibility", ("accessib", "wcag", "screen reader", "vestibul")),
    ("Security / IG", ("pii", "phi", "tenant", "unauthoris", "cve",
                       "injection", "audit trail", "encryption")),
    ("NLP extraction", ("nlp", "extract", "entity", "ner", "negation")),
    ("SNOMED coding", ("snomed", "coding", "code", "concept", "surface form",
                       "maps_to")),
    ("Escalation", ("escalation", "ask leo", "verifier")),
    ("Training pipeline", ("training", "gold label", "labelled", "drift",
                           "model registry", "writeback")),
    ("Pathway analytics", ("pathway", "milestone", "episode", "analytics")),
    ("Safety alerts", ("alert", "safety", "stale", "unactioned")),
    ("Data quality", ("dq ", "data quality", "orphan", "missing chain")),
    ("Infrastructure", ("outage", "unavailable", "service bus",
                        "container app", "key vault")),
]


def _derive_component(row: dict) -> str:
    framework = (row.get("Specialist_Review_Framework") or "").lower()
    if "accessibility" in framework:
        return "Accessibility"
    if "ig" in framework or "security" in framework:
        return "Security / IG"
    title = (row.get("Title") or "").lower()
    for label, keywords in COMPONENT_RULES:
        if any(kw in title for kw in keywords):
            return label
    return "LEO-AI-CORE pipeline"


def _derive_hazard_category(title: str, stride: str) -> str:
    title_lower = (title or "").lower()
    if stride and any(c in stride for c in ("S", "I", "E")):
        return "security_breach"
    sec_kw = ("pii", "phi", "confidential", "data breach", "tenant",
              "unauthoris", "cve", "injection", "audit trail")
    if any(x in title_lower for x in sec_kw):
        return "security_breach"
    if any(x in title_lower for x in ("accessibility", "vestibul",
                                      "screen reader", "misread")):
        return "misuse"
    if "unavailable" in title_lower or "outage" in title_lower:
        return "infrastructure_failure"
    if "drift" in title_lower or "degrad" in title_lower:
        return "performance_degradation"
    if "corrupt" in title_lower or "stale" in title_lower:
        return "data_corruption"
    return "software_defect"


CAUSE_BY_COMPONENT = {
    "NLP extraction": ("LLM/NER ambiguity on free-text narratives, ontology "
                       "drift, and incomplete training coverage."),
    "SNOMED coding": ("Surface-form to concept mapping ambiguity, "
                      "out-of-date concept index, and human reviewer error."),
    "Escalation": ("Heuristic gaps in escalation triggers and prompt "
                   "drift in escalation models."),
    "Training pipeline": ("Label drift, distribution shift between cohorts, "
                          "and unverified writeback channels."),
    "Pathway analytics": ("Incomplete episode chains, missing milestone "
                          "coverage, and stale pathway definitions."),
    "Safety alerts": ("Alert generation/dispatch gaps and unactioned alert "
                      "queue ageing."),
    "Data quality": ("Source-system data gaps, schema drift, and broken "
                     "ETL invariants."),
    "Security / IG": ("Inadequate access controls, insufficient anomaly "
                      "detection, and undocumented data flows."),
    "Accessibility": ("Components shipped without WCAG 2.2 AA verification "
                      "and missing screen reader labels."),
    "Infrastructure": ("Single-region dependencies, undersized capacity, "
                       "and missing health probes."),
}


def _derive_failure_cause(row: dict, yaml_data: dict | None) -> str:
    yaml_haz = _clean_yaml_scalar((yaml_data or {}).get(
        "hazard_description", ""))
    if yaml_haz and len(yaml_haz) > 10:
        return yaml_haz[:300]
    notes = (row.get("Notes") or "").strip()
    if notes and not notes.startswith("Existing YAML risk") \
            and not notes.startswith("Consolidates FMEA"):
        return notes[:300]
    component = _derive_component(row)
    if component in CAUSE_BY_COMPONENT:
        return CAUSE_BY_COMPONENT[component][:300]
    return ("Failure mode identified at LEO-AI-CORE hazard workshop "
            "2026-04-16; cause attributed to combined functional, data, "
            "and human factors per linked Mitigating_DIs.")[:300]


def _build_tags(row: dict) -> list[str]:
    tags = ["leo_ai_core_workshop_2026_04_16",
            f"source_{(row.get('Source') or '').lower()}",
            f"workshop_decision_{row.get('Safety_Review_Decision', '')}",
            f"control_adequacy_{row.get('Control_Adequacy', '')}"]
    if row.get("Needs_VAL") == "yes":
        tags.append("requires_VAL")
    if row.get("Production_Blocker") == "yes":
        tags.append("production_blocker")
    stride = row.get("STRIDE_Categories", "")
    if stride:
        tags.append(f"stride_{stride.replace(',', '_')}")
    if (row.get("Safety_Class") or "").upper() == "C":
        tags.append("workshop_originally_class_c_capped_to_B")
    return sorted(set(t for t in tags if t and not t.endswith("_")))


def _scores_5(row: dict) -> tuple[int, int, int]:
    s = _to_int_5(row.get("Revised_S") or row.get("S"), SEV_NUM_5) or 3
    p = _to_int_5(row.get("Revised_P") or row.get("P"), PROB_NUM_5) or 3
    d_raw = (row.get("Revised_D") or row.get("D") or "3").strip()
    try:
        d = int(d_raw) if d_raw.isdigit() else 3
    except (TypeError, ValueError):
        d = 3
    return s, max(1, min(5, p)), max(1, min(5, d))


def build_fmea_item(row: dict, yaml_data: dict | None) -> dict:
    s5, p5, d5 = _scores_5(row)
    raw_effect = row.get("Hazardous_Situation") or row.get("Title") or ""
    yaml_situation = _clean_yaml_scalar((yaml_data or {}).get(
        "hazardous_situation", ""))
    if yaml_situation and len(yaml_situation) > 10:
        effect = yaml_situation
    else:
        effect = _clean_yaml_scalar(raw_effect)
    return {
        "workshop_id": WORKSHOP_ID,
        "component": _derive_component(row),
        "failure_mode": (row.get("Title") or "Unspecified failure mode")[:300],
        "failure_effect": effect[:500],
        "failure_cause": _derive_failure_cause(row, yaml_data),
        "severity": _scale_to_10(s5),
        "occurrence": _scale_to_10(p5),
        "detection": _scale_to_10(d5),
        "current_controls": _current_controls(row),
        "recommended_actions": _recommended_actions(row),
        "owner": "Clinical Safety Officer",
    }


def _current_controls(row: dict) -> str:
    dis = [d for d in (row.get("Mitigating_DIs") or "").split()
           if d.startswith("DI-")]
    if dis:
        return f"Mitigating DIs: {', '.join(dis[:8])}"[:500]
    return "See linked Design Inputs (none registered yet)"


def _recommended_actions(row: dict) -> str:
    missing = (row.get("Missing_Controls") or "").strip()
    if missing:
        return f"Additional controls required: {missing}"[:500]
    return ("Maintain existing controls and review at quarterly Clinical "
            "Safety Committee.")


def _yaml_block_for(risk_id: str) -> dict | None:
    """Load the full YAML risk record (including residual_risk_estimate) for
    R-LEO-AI-NNN. Returns None when no file exists or it cannot be parsed.
    Cached so we only hit disk once per ID across the run.
    """
    if not risk_id:
        return None
    if risk_id in _YAML_BLOCKS:
        return _YAML_BLOCKS[risk_id]
    path = HERE / f"{risk_id}.yaml"
    if not path.exists():
        _YAML_BLOCKS[risk_id] = {}
        return None
    try:
        docs = list(yaml.safe_load_all(path.open()))
    except yaml.YAMLError:
        _YAML_BLOCKS[risk_id] = {}
        return None
    for doc in docs:
        if doc is None:
            continue
        items = doc if isinstance(doc, list) else [doc]
        for it in items:
            if isinstance(it, dict) and it.get("id") == risk_id:
                _YAML_BLOCKS[risk_id] = it
                return it
    _YAML_BLOCKS[risk_id] = {}
    return None


def _residual_from_yaml(risk_id: str, row: dict) -> dict:
    block = _yaml_block_for(risk_id)
    if not block:
        return {}
    res = block.get("residual_risk_estimate") or {}
    sev = res.get("severity")
    prob = res.get("probability")
    det = res.get("detectability")
    if not (isinstance(sev, int) and isinstance(prob, int) and isinstance(det, int)):
        return {}
    rpn = sev * prob * det
    accept_raw = (res.get("acceptability") or "").strip().lower()
    accept = ACCEPT_MAP.get(accept_raw) or ACCEPT_MAP.get(
        rpn_to_level(rpn), "alarp"
    )
    return {
        "residual_severity": sev,
        "residual_probability": prob,
        "residual_detectability": det,
        "residual_rpn": rpn,
        "residual_risk_level": rpn_to_level(rpn),
        "residual_acceptability": accept,
        "residual_justification": (
            res.get("justification")
            or (
                f"Residual estimate from {risk_id}.yaml. "
                f"Specialist review framework: "
                f"{row.get('Specialist_Review_Framework') or 'clinical safety'}."
            )
        )[:500],
    }


def _residual_initial_fallback(row: dict) -> dict:
    """Conservative ISO 14971 fallback: until residual is workshop-reviewed,
    treat residual = initial. Surfaces the risk in the matrix at its
    pre-mitigation cell rather than dropping it silently.
    """
    s5, p5, d5 = _scores_5(row)
    rpn = s5 * p5 * d5
    return {
        "residual_severity": s5,
        "residual_probability": p5,
        "residual_detectability": d5,
        "residual_rpn": rpn,
        "residual_risk_level": rpn_to_level(rpn),
        "residual_acceptability": ACCEPT_MAP.get(rpn_to_level(rpn), "alarp"),
        "residual_justification": (
            "Provisional residual = initial estimate. Pending workshop "
            "review of mitigation effectiveness for this FMEA gap "
            f"({row.get('Master_ID', '')}). Specialist framework: "
            f"{row.get('Specialist_Review_Framework') or 'clinical safety'}."
        )[:500],
    }


def _residual_block(row: dict) -> dict:
    sev_raw = row.get("Residual_Severity", "")
    prob_raw = row.get("Residual_Probability", "")
    det_raw = row.get("Residual_Detectability", "")
    accept_raw = (row.get("Residual_Acceptability") or "").strip().lower()
    rid = row.get("Atlas_R_ID", "")
    if not (sev_raw and prob_raw and det_raw and accept_raw):
        return _residual_from_yaml(rid, row) or _residual_initial_fallback(row)
    s = _to_int_5(sev_raw, SEV_NUM_5)
    p = _to_int_5(prob_raw, PROB_NUM_5)
    try:
        d = int(det_raw)
    except (TypeError, ValueError):
        return _residual_from_yaml(rid, row) or _residual_initial_fallback(row)
    if s is None or p is None:
        return _residual_from_yaml(rid, row) or _residual_initial_fallback(row)
    rpn = s * p * d
    return {
        "residual_severity": s,
        "residual_probability": p,
        "residual_detectability": d,
        "residual_rpn": rpn,
        "residual_risk_level": rpn_to_level(rpn),
        "residual_acceptability": ACCEPT_MAP.get(accept_raw, "alarp"),
        "residual_justification": (
            f"Workshop residual reviewed by "
            f"{row.get('Specialist_Review_Framework') or 'clinical safety'}. "
            f"Missing controls: {row.get('Missing_Controls', '')[:200]}"
        )[:500],
    }


def build_update_risk(row: dict, yaml_data: dict | None) -> dict:
    s5, p5, d5 = _scores_5(row)
    rpn = s5 * p5 * d5
    yaml_haz = _clean_yaml_scalar((yaml_data or {}).get(
        "hazard_description", ""))
    yaml_situation = _clean_yaml_scalar((yaml_data or {}).get(
        "hazardous_situation", ""))
    yaml_harm = _clean_yaml_scalar((yaml_data or {}).get(
        "harm_description", ""))
    csv_situation = _clean_yaml_scalar(row.get("Hazardous_Situation") or "")
    hazard_desc = (yaml_haz if len(yaml_haz) > 10 else csv_situation)[:500]
    situation = (yaml_situation if len(yaml_situation) > 10
                 else csv_situation)[:500]
    harm_desc = (yaml_harm if len(yaml_harm) > 10 else csv_situation)[:300]
    body = {
        "title": (row.get("Title") or "")[:200],
        "description": _description(row),
        "hazard_description": hazard_desc,
        "hazard_category": _derive_hazard_category(
            row.get("Title", ""), row.get("STRIDE_Categories", "")),
        "hazardous_situation": situation,
        "harm_description": harm_desc,
        "harm_severity": SEV_LABEL_5.get(s5, "serious"),
        "initial_severity": s5,
        "initial_probability": p5,
        "initial_detectability": d5,
        "initial_rpn": rpn,
        "safety_class": "B" if (row.get("Safety_Class") or "B").upper() == "C"
        else (row.get("Safety_Class") or "B"),
        "status": "Identified",
        "identified_by": ("LEO-AI-CORE Hazard Workshop 2026-04-16 "
                          "(facilitated by Rob Smith)"),
        "identified_date": "2026-04-16",
        "tags": _build_tags(row),
        "monitoring_plan": _monitoring_plan(row),
        "monitoring_metrics": ["RPN trend", "Incident count",
                               "Mitigation effectiveness",
                               "Post-market surveillance reports"],
        "review_frequency": "Quarterly",
        "mitigation_control_type": "protective_measure",
        "mitigation_effectiveness": EFFECTIVENESS_MAP.get(
            row.get("Control_Adequacy", ""), "partially_effective"),
        "mitigation_measures_detail": _mitigation_detail(row),
    }
    body.update(_residual_block(row))
    return body


def _description(row: dict) -> str:
    return (
        f"Source: {row.get('Source', '')}. "
        f"FMEA refs: {row.get('Source_FMEA_IDs') or 'n/a'}. "
        f"Workshop decision: {row.get('Safety_Review_Decision', '')}. "
        f"Control adequacy: {row.get('Control_Adequacy', '')}. "
        f"{(row.get('Notes') or '')[:200]}"
    )[:500]


def _monitoring_plan(row: dict) -> str:
    framework = row.get("Specialist_Review_Framework") or "clinical safety"
    return (
        "Monitor via DQ dashboards, incident management, and quarterly RPN "
        f"trend review at Clinical Safety Committee. Specialist framework: "
        f"{framework}."
    )[:500]


def _mitigation_detail(row: dict) -> str:
    notes = (row.get("Notes") or "")[:200]
    base = notes if notes else "See linked Design Inputs via MITIGATES edges"
    missing = (row.get("Missing_Controls") or "").strip()
    if missing:
        return f"{base} | ADDITIONAL CONTROLS REQUIRED: {missing[:250]}"[:500]
    return base[:500]


ATLAS_ID_RE = re.compile(r"^[A-Z]+-[A-F0-9]{8}$")


def _atlas_form_only(raw: str) -> list[str]:
    """Keep only Atlas-form IDs (PREFIX-XXXXXXXX), drop local DI-LEO-AI-NNN."""
    return [tok for tok in (raw or "").split() if ATLAS_ID_RE.match(tok)]


def _build_risk_fingerprint(row: dict, fmea_item: dict,
                            update_body: dict) -> str:
    return " ".join([
        row.get("Title") or "",
        fmea_item.get("failure_mode") or "",
        fmea_item.get("failure_effect") or "",
        fmea_item.get("failure_cause") or "",
        update_body.get("hazard_description") or "",
        update_body.get("harm_description") or "",
    ])


def _matched_dis(fingerprint: str, index: di_matcher.Index,
                 workshop_dis: list[str]) -> tuple[list[str], list[dict]]:
    matches = di_matcher.match(
        fingerprint, index,
        top_n=DI_MATCH_TOP_N, min_score=DI_MATCH_MIN_SCORE,
    )
    auto_ids = [m.dc_id for m in matches]
    merged: list[str] = []
    seen: set[str] = set()
    for did in workshop_dis + auto_ids:
        if did and did not in seen:
            seen.add(did)
            merged.append(did)
    audit = [
        {"dc_id": m.dc_id, "title": m.title, "score": m.score,
         "overlap": m.overlap, "source": "auto"}
        for m in matches
    ]
    for did in workshop_dis:
        if did not in {a["dc_id"] for a in audit}:
            audit.append({"dc_id": did, "title": "(workshop pick)",
                          "score": None, "overlap": [], "source": "workshop"})
    return merged, audit


def build_links(row: dict, fmea_item: dict, update_body: dict,
                index: di_matcher.Index) -> dict:
    workshop_dis = _atlas_form_only(row.get("Mitigating_DIs", ""))
    fingerprint = _build_risk_fingerprint(row, fmea_item, update_body)
    di_ids, audit = _matched_dis(fingerprint, index, workshop_dis)
    return {
        "product_id": PRODUCT_ID,
        "un_ids": _atlas_form_only(row.get("UN_IDs", "")),
        "di_ids": di_ids,
        "di_audit": audit,
    }


def build_record(row: dict, yaml_index: dict,
                 di_index: di_matcher.Index) -> dict:
    yaml_data = yaml_index.get(row.get("Atlas_R_ID"))
    fmea_item = build_fmea_item(row, yaml_data)
    update_body = build_update_risk(row, yaml_data)
    links = build_links(row, fmea_item, update_body, di_index)
    return {
        "master_id": row["Master_ID"],
        "proposed_atlas_r_id": row.get("Atlas_R_ID"),
        "source": row.get("Source"),
        "action": row.get("Action"),
        "needs_new_un": "NEW_UN_NEEDED" in (row.get("UN_IDs") or ""),
        "needs_new_di": "NEW_DI_NEEDED" in (row.get("Mitigating_DIs") or ""),
        "production_blocker": row.get("Production_Blocker") == "yes",
        "promote_to_risk": True,
        "add_fmea_item": fmea_item,
        "update_risk": update_body,
        "links": links,
    }


def _print_summary(records: list[dict]) -> None:
    with_un = sum(1 for r in records if r["links"]["un_ids"])
    with_di = sum(1 for r in records if r["links"]["di_ids"])
    with_residual = sum(1 for r in records
                        if r["update_risk"].get("residual_severity"))
    blockers = sum(1 for r in records if r["production_blocker"])
    needs_un = sum(1 for r in records if r["needs_new_un"])
    needs_di = sum(1 for r in records if r["needs_new_di"])
    promote = sum(1 for r in records if r["promote_to_risk"])
    print(f"FMEA payload records:  {len(records)}")
    print(f"  With UN HAS_RISK:    {with_un}")
    print(f"  With DI MITIGATES:   {with_di}")
    print(f"  With residual block: {with_residual}")
    print(f"  Production blockers: {blockers}")
    print(f"  Needs new UN:        {needs_un}")
    print(f"  Needs new DI:        {needs_di}")
    print(f"  Will promote:        {promote}")
    di_counts = [len(r["links"]["di_ids"]) for r in records]
    avg_di = sum(di_counts) / max(len(di_counts), 1)
    no_di = sum(1 for c in di_counts if c == 0)
    print(f"  Avg DI links/risk:   {avg_di:.1f}")
    print(f"  Risks with 0 DIs:    {no_di}")
    print(f"Output: {OUT_PATH.name}")
    print(f"DI audit report: {DI_REPORT_PATH.name}")


def _load_atlas_di_index() -> di_matcher.Index:
    atlas = json.loads(ATLAS_INDEX.read_text())
    return di_matcher.build_index(atlas["design_inputs"])


def _write_di_report(records: list[dict]) -> None:
    with DI_REPORT_PATH.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["master_id", "title", "source", "atlas_di_id",
                    "atlas_di_title", "score", "overlap_terms"])
        for rec in records:
            for entry in rec["links"]["di_audit"]:
                w.writerow([
                    rec["master_id"],
                    rec["add_fmea_item"]["failure_mode"][:80],
                    entry["source"],
                    entry["dc_id"],
                    entry["title"][:80],
                    entry["score"] if entry["score"] is not None else "",
                    "|".join(entry["overlap"]),
                ])


def main() -> None:
    yaml_index = _yaml_data()
    di_index = _load_atlas_di_index()
    with CSV_PATH.open() as f:
        rows = list(csv.DictReader(f))
    records = [build_record(r, yaml_index, di_index) for r in rows]
    _write_di_report(records)
    with OUT_PATH.open("w") as f:
        json.dump({
            "workshop_id": WORKSHOP_ID,
            "product_id": PRODUCT_ID,
            "scoring_note": ("FMEA item S/O/D on 1-10 scale (2x master's "
                             "1-5). update_risk fields stay on ISO 14971 "
                             "1-5 scale."),
            "records": records,
        }, f, indent=2)
    _print_summary(records)


if __name__ == "__main__":
    main()
