"""
Apply Dedup Auditor decisions to MASTER-RISK-LIST.csv.

Decisions from _workshop_02_dedup.json:
- SPLIT-OUT 2 consolidations that were wrongly merged (add 2 new R-IDs).
- APPLY 4 high-confidence YAML-to-YAML merges (remove duplicate rows).
- FIX misconsolidation of FMEA-037 (holdout leakage should link to R-053 not R-065).
- FLAG 4 medium-confidence merges as workshop_decision notes (keep both rows).

Backs up MASTER-RISK-LIST.csv to MASTER-RISK-LIST.pre-dedup.csv.
"""

import csv
import shutil
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
MASTER = HERE / "MASTER-RISK-LIST.csv"
BACKUP = HERE / "MASTER-RISK-LIST.pre-dedup.csv"

# -- High-confidence merges: kill row B, fold its links into row A --
HIGH_CONF_MERGES = [
    ("R-LEO-AI-069", "R-LEO-AI-071"),
    ("R-LEO-AI-059", "R-LEO-AI-061"),
    ("R-LEO-AI-085", "R-LEO-AI-092"),
    ("R-LEO-AI-082", "R-LEO-AI-088"),
]

# -- Medium-confidence: keep both rows, add cross-link note --
MEDIUM_CONF_LINKS = [
    ("R-LEO-AI-067", "R-LEO-AI-068",
     "Workshop flag: Dedup Auditor flagged R-068 and R-067 as possible merge "
     "(same hazard, different pipeline stage). Medium confidence - retain both."),
    ("R-LEO-AI-033", "R-LEO-AI-054",
     "Workshop flag: Dedup Auditor flagged R-054 and R-033 as possible merge "
     "(non-clinical text miscoded as finding). Medium confidence - retain both."),
    ("R-LEO-AI-081", "R-LEO-AI-083",
     "Workshop flag: Dedup Auditor flagged R-083 health-literacy overlap "
     "with R-081. Medium confidence - retain both."),
    ("R-LEO-AI-081", "R-LEO-AI-094",
     "Workshop flag: Dedup Auditor flagged R-094 health-literacy overlap "
     "with R-081. Medium confidence - retain both."),
    ("R-LEO-AI-004", "R-LEO-AI-055",
     "Workshop flag: Dedup Auditor - keep both but cross-link. "
     "R-055 is a high-severity subset of R-004."),
]

# -- Split-outs: create new R-IDs for wrongly-merged FMEAs --
SPLIT_OUTS = [
    {
        "fmea_id": "FMEA-008",
        "remove_from_r_id": "R-LEO-AI-065",
        "new_title": "Automated episode quality-check rule fails to catch incorrect coding",
        "new_hazardous": (
            "The automated episode quality-check RULE SET has coverage gaps; "
            "incorrectly coded entities pass the rule layer and enter "
            "episodes without being flagged for human review."
        ),
        "safety_class": "B",
        "S": "3", "P": "3", "D": "3",
        "notes": (
            "Split from R-LEO-AI-065 per Dedup Auditor - different control "
            "layer (automated rule vs human auditor approval)."
        ),
    },
    {
        "fmea_id": "FMEA-050",
        "remove_from_r_id": "R-LEO-AI-056",
        "new_title": (
            "Human reviewer approves a wrong replacement code during coding "
            "correction due to terminology-expertise gap"
        ),
        "new_hazardous": (
            "A human reviewer selects an incorrect SNOMED replacement during "
            "a coding-correction workflow because they lack terminology "
            "expertise or clinical context for ambiguous terms."
        ),
        "safety_class": "B",
        "S": "3", "P": "3", "D": "3",
        "notes": (
            "Split from R-LEO-AI-056 per Dedup Auditor - R-056 is automated "
            "dual-LLM remediation; this is human reviewer expertise gap."
        ),
    },
]

# -- Data error fix: FMEA-037 currently on R-065 should be on R-053 --
FMEA_REROUTE = {
    "fmea_id": "FMEA-037",
    "from_r_id": "R-LEO-AI-065",
    "to_r_id": "R-LEO-AI-053",
}


def load_rows() -> list[dict]:
    with MASTER.open() as f:
        return list(csv.DictReader(f))


def _union_tokens(a: str, b: str) -> str:
    tokens = []
    for src in (a, b):
        for tok in (src or "").split():
            if tok and tok not in tokens:
                tokens.append(tok)
    return " ".join(tokens)


def apply_high_conf_merges(rows: list[dict]) -> list[dict]:
    by_id = {r["Atlas_R_ID"]: r for r in rows}
    removed = set()
    for keep_id, drop_id in HIGH_CONF_MERGES:
        keep = by_id.get(keep_id)
        drop = by_id.get(drop_id)
        if not keep or not drop:
            continue
        keep["Mitigating_DIs"] = _union_tokens(
            keep["Mitigating_DIs"], drop["Mitigating_DIs"])
        keep["UN_IDs"] = _union_tokens(keep["UN_IDs"], drop["UN_IDs"])
        keep["Source_FMEA_IDs"] = _union_tokens(
            keep["Source_FMEA_IDs"], drop["Source_FMEA_IDs"])
        keep["Notes"] = (
            f"{keep['Notes']} | MERGED_IN: {drop_id} "
            f"({drop['Title'][:80]}) per Dedup Auditor"
        )[:500]
        removed.add(drop_id)
    return [r for r in rows if r["Atlas_R_ID"] not in removed]


def apply_medium_conf_links(rows: list[dict]) -> None:
    by_id = {r["Atlas_R_ID"]: r for r in rows}
    for rid_a, rid_b, note in MEDIUM_CONF_LINKS:
        for rid in (rid_a, rid_b):
            r = by_id.get(rid)
            if r and "Workshop flag" not in r["Notes"]:
                r["Notes"] = f"{r['Notes']} | {note}"[:500]


def apply_fmea_reroute(rows: list[dict]) -> None:
    by_id = {r["Atlas_R_ID"]: r for r in rows}
    src = by_id.get(FMEA_REROUTE["from_r_id"])
    dst = by_id.get(FMEA_REROUTE["to_r_id"])
    fid = FMEA_REROUTE["fmea_id"]
    if src:
        src["Source_FMEA_IDs"] = " ".join(
            t for t in src["Source_FMEA_IDs"].split() if t != fid)
        src["Notes"] = (
            f"{src['Notes']} | Data fix: {fid} re-routed to "
            f"{FMEA_REROUTE['to_r_id']} per Dedup Auditor"
        )[:500]
    if dst:
        dst["Source_FMEA_IDs"] = _union_tokens(dst["Source_FMEA_IDs"], fid)
        dst["Notes"] = (
            f"{dst['Notes']} | Added FMEA link: {fid} (holdout leakage)"
        )[:500]


def apply_split_outs(rows: list[dict]) -> list[dict]:
    by_id = {r["Atlas_R_ID"]: r for r in rows}
    next_new = max(
        int(r["Atlas_R_ID"].split("-")[-1])
        for r in rows
    ) + 1
    new_rows: list[dict] = []
    for split in SPLIT_OUTS:
        src = by_id.get(split["remove_from_r_id"])
        if not src:
            continue
        src["Source_FMEA_IDs"] = " ".join(
            t for t in src["Source_FMEA_IDs"].split()
            if t != split["fmea_id"])
        src["Notes"] = (
            f"{src['Notes']} | Split out: {split['fmea_id']} moved to new "
            f"R-LEO-AI-{next_new:03d} per Dedup Auditor"
        )[:500]
        new_rid = f"R-LEO-AI-{next_new:03d}"
        new_rows.append({
            "Master_ID": f"MR-{len(rows) + len(new_rows) + 1:03d}",
            "Atlas_R_ID": new_rid,
            "Source": "FMEA_GAP",
            "Action": "CREATE_NEW",
            "Title": split["new_title"],
            "Hazardous_Situation": split["new_hazardous"],
            "S": split["S"], "P": split["P"], "D": split["D"],
            "RPN": str(int(split["S"]) * int(split["P"]) * int(split["D"])),
            "Harm_Severity": "",
            "Safety_Class": split["safety_class"],
            "UN_IDs": "TBD_WORKSHOP",
            "Mitigating_DIs": "TBD_WORKSHOP",
            "Source_FMEA_IDs": split["fmea_id"],
            "Notes": split["notes"],
        })
        next_new += 1
    return rows + new_rows


def main() -> None:
    shutil.copyfile(MASTER, BACKUP)
    rows = load_rows()
    original_count = len(rows)

    rows = apply_high_conf_merges(rows)
    apply_medium_conf_links(rows)
    apply_fmea_reroute(rows)
    rows = apply_split_outs(rows)

    for i, r in enumerate(rows, start=1):
        r["Master_ID"] = f"MR-{i:03d}"

    fieldnames = list(rows[0].keys())
    with MASTER.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    net = len(rows) - original_count
    print(f"Original rows:     {original_count}")
    print(f"High-conf merges:  {len(HIGH_CONF_MERGES)}  (removed)")
    print(f"Split-outs:        {len(SPLIT_OUTS)}  (added)")
    print(f"Medium-conf links: {len(MEDIUM_CONF_LINKS)}  (flagged)")
    print(f"FMEA re-routes:    1  (FMEA-037 R-065 -> R-053)")
    print(f"Final rows:        {len(rows)}  (net {net:+d})")
    print(f"Backup:            {BACKUP.name}")


if __name__ == "__main__":
    main()
