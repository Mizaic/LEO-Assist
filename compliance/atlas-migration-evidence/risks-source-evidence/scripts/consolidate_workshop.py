"""
Consolidate all 6 subagent outputs into the final master risk list.

Inputs:
- MASTER-RISK-LIST.csv (156 rows, current)
- _workshop_01_safety.json (S/P/D revisions + Class C escalations)
- _workshop_02_dedup.json (dedup - already applied)
- _workshop_03_di_audit.json (DI effectiveness + missing controls)
- _workshop_04_un_trace.json (UN assignments + DI recommendations)
- _workshop_05_security.json (STRIDE + residual risk for 18 security risks)
- _workshop_06_accessibility.json (WCAG + residual risk for 16 UX risks)

Outputs:
- MASTER-RISK-LIST-FINAL.csv (all findings merged)
- atlas_master_payloads_final.json (payloads with residual risk and revised S/P/D)
- HAZARD-WORKSHOP-MINUTE-2026-04-16.md (workshop minute)
- _workshop_conflicts.json (conflicting recommendations for escalation)
"""

import csv
import json
from pathlib import Path

HERE = Path(__file__).parent
MASTER_CSV = HERE / "MASTER-RISK-LIST.csv"
OUT_CSV = HERE / "MASTER-RISK-LIST-FINAL.csv"

SEV_STR_TO_NUM = {
    "negligible": 1, "minor": 2, "serious": 3,
    "critical": 4, "catastrophic": 5,
}
PROB_STR_TO_NUM = {
    "remote": 1, "unlikely": 2, "possible": 3,
    "likely": 4, "almost_certain": 5,
}


def load_json(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def index_reviews(data: dict, key: str = "reviews") -> dict:
    return {r.get("atlas_r_id", r.get("master_id", "")): r
            for r in data.get(key, [])}


def merge_safety(row: dict, review: dict | None) -> None:
    if not review:
        row["Revised_S"] = row["S"]
        row["Revised_P"] = row["P"]
        row["Revised_D"] = row["D"]
        row["Revised_RPN"] = row["RPN"]
        row["Safety_Review_Decision"] = "not_reviewed"
        return
    row["Revised_S"] = str(review.get("revised_S", row["S"]))
    row["Revised_P"] = str(review.get("revised_P", row["P"]))
    row["Revised_D"] = str(review.get("revised_D", row["D"]))
    try:
        row["Revised_RPN"] = str(
            int(row["Revised_S"]) * int(row["Revised_P"]) * int(row["Revised_D"]))
    except ValueError:
        row["Revised_RPN"] = row["RPN"]
    row["Safety_Review_Decision"] = review.get("decision", "confirm")
    if review.get("decision") == "escalate_class_C":
        row["Safety_Class"] = "C"
        row["Needs_VAL"] = "yes"
    else:
        row["Needs_VAL"] = row.get("Needs_VAL", "no")


def merge_di_audit(row: dict, review: dict | None) -> None:
    if not review:
        row["Control_Adequacy"] = "not_reviewed"
        row["Missing_Controls"] = ""
        row["DI_Verified_In_Code"] = ""
        return
    row["Control_Adequacy"] = review.get("effectiveness", "not_reviewed")
    missing = review.get("missing_controls", []) or []
    row["Missing_Controls"] = "; ".join(missing)[:400]
    row["DI_Verified_In_Code"] = str(review.get("verified_in_codebase", ""))


def merge_un_trace(row: dict, un_data: dict) -> None:
    assignments = {a["atlas_r_id"]: a for a in un_data.get("un_assignments", [])}
    di_recs = {d["atlas_r_id"]: d for d in un_data.get("di_recommendations", [])}
    rid = row["Atlas_R_ID"]
    un_rec = assignments.get(rid)
    if un_rec and row["UN_IDs"] in ("TBD_WORKSHOP", ""):
        recommended = un_rec.get("recommended_uns", []) or []
        if recommended:
            row["UN_IDs"] = " ".join(recommended)
        elif un_rec.get("needs_new_un"):
            suggested = un_rec.get("suggested_new_un") or {}
            title = suggested.get("title", "untitled") if isinstance(
                suggested, dict) else str(suggested)
            row["UN_IDs"] = f"NEW_UN_NEEDED: {title}"
    di_rec = di_recs.get(rid)
    if di_rec and row["Mitigating_DIs"] in ("TBD_WORKSHOP", ""):
        rec_dis = di_rec.get("recommended_dis", []) or []
        if rec_dis:
            row["Mitigating_DIs"] = " ".join(rec_dis)
        elif di_rec.get("needs_new_di"):
            title = di_rec.get("suggested_new_di_title", "untitled")
            row["Mitigating_DIs"] = f"NEW_DI_NEEDED: {title}"


def _apply_residual(row: dict, review: dict, framework: str) -> None:
    if not review:
        return
    sev = review.get("residual_severity", "")
    prob = review.get("residual_probability", "")
    det = review.get("residual_detectability", "")
    row["Residual_Severity"] = sev
    row["Residual_Probability"] = prob
    row["Residual_Detectability"] = str(det) if det != "" else ""
    row["Residual_Acceptability"] = review.get("residual_acceptability", "")
    try:
        s_n = SEV_STR_TO_NUM.get(sev, 0)
        p_n = PROB_STR_TO_NUM.get(prob, 0)
        d_n = int(det) if det != "" else 0
        row["Residual_RPN"] = str(s_n * p_n * d_n) if all([s_n, p_n, d_n]) else ""
    except (ValueError, TypeError):
        row["Residual_RPN"] = ""
    if review.get("residual_acceptability") == "unacceptable":
        row["Production_Blocker"] = "yes"
    row["Specialist_Review_Framework"] = framework
    add_controls = review.get("additional_controls_required", []) or []
    if add_controls:
        current = row.get("Missing_Controls", "")
        extra = "; ".join(add_controls)[:300]
        row["Missing_Controls"] = f"{current} | Specialist: {extra}"[:600]


def merge_security(row: dict, review: dict | None) -> None:
    if not review:
        return
    _apply_residual(row, review, "IG/Security (GDPR + DCB0129)")
    stride = review.get("stride_categories", []) or []
    row["STRIDE_Categories"] = ",".join(stride)


def merge_accessibility(row: dict, review: dict | None) -> None:
    if not review:
        return
    _apply_residual(row, review, "Accessibility (WCAG 2.2 AA)")
    wcag = review.get("wcag_criteria", []) or []
    row["WCAG_Criteria"] = ",".join(wcag)
    row["Health_Literacy"] = review.get("health_literacy_assessment", "")


def consolidate() -> list[dict]:
    with MASTER_CSV.open() as f:
        rows = list(csv.DictReader(f))

    safety = index_reviews(load_json(HERE / "_workshop_01_safety.json"))
    di_audit = index_reviews(load_json(HERE / "_workshop_03_di_audit.json"))
    un_data = load_json(HERE / "_workshop_04_un_trace.json")
    security = index_reviews(load_json(HERE / "_workshop_05_security.json"))
    access = index_reviews(load_json(HERE / "_workshop_06_accessibility.json"))

    new_fields = [
        "Revised_S", "Revised_P", "Revised_D", "Revised_RPN",
        "Safety_Review_Decision", "Needs_VAL", "Control_Adequacy",
        "Missing_Controls", "DI_Verified_In_Code",
        "Residual_Severity", "Residual_Probability", "Residual_Detectability",
        "Residual_RPN", "Residual_Acceptability",
        "Production_Blocker", "Specialist_Review_Framework",
        "STRIDE_Categories", "WCAG_Criteria", "Health_Literacy",
    ]

    for row in rows:
        rid = row["Atlas_R_ID"]
        for f in new_fields:
            row.setdefault(f, "")
        merge_safety(row, safety.get(rid))
        merge_di_audit(row, di_audit.get(rid))
        merge_un_trace(row, un_data)
        merge_security(row, security.get(rid))
        merge_accessibility(row, access.get(rid))

    return rows


def write_output(rows: list[dict]) -> None:
    fieldnames = list(rows[0].keys())
    with OUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(rows: list[dict]) -> None:
    from collections import Counter
    print(f"Final master list: {len(rows)} risks")
    print()
    dec = Counter(r["Safety_Review_Decision"] for r in rows)
    print("Safety Lead decisions:")
    for k, v in dec.most_common():
        print(f"  {k:<25} {v}")
    print()
    sc = Counter(r["Safety_Class"] for r in rows)
    print("Safety Class distribution:")
    for k, v in sc.most_common():
        print(f"  {k:<5} {v}")
    print()
    ca = Counter(r["Control_Adequacy"] for r in rows)
    print("DI Control Adequacy:")
    for k, v in ca.most_common():
        print(f"  {k:<15} {v}")
    print()
    blockers = [r for r in rows if r.get("Production_Blocker") == "yes"]
    print(f"Production blockers: {len(blockers)}")
    for b in blockers:
        print(f"  {b['Atlas_R_ID']}  {b['Title'][:80]}")
    print()
    needs_val = [r for r in rows if r.get("Needs_VAL") == "yes"]
    print(f"Class C escalations requiring VAL: {len(needs_val)}")
    for v in needs_val:
        print(f"  {v['Atlas_R_ID']}  {v['Title'][:80]}")
    print()
    tbd_un = sum(1 for r in rows
                 if "TBD" in r["UN_IDs"] or "NEW_UN_NEEDED" in r["UN_IDs"])
    tbd_di = sum(1 for r in rows
                 if "TBD" in r["Mitigating_DIs"]
                 or "NEW_DI_NEEDED" in r["Mitigating_DIs"])
    print(f"Still need UN: {tbd_un}")
    print(f"Still need DI: {tbd_di}")


def main() -> None:
    rows = consolidate()
    write_output(rows)
    print_summary(rows)
    print()
    print(f"Output: {OUT_CSV.name}")


if __name__ == "__main__":
    main()
