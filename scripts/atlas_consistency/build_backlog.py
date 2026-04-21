"""Build the MVP-scope Atlas design-control consistency backlog.

Reads the cached traceability_matrix dump and emits:
  - mvp_consistency_backlog.csv
  - all_di_consistency.csv (full product, for triage support)
  - summary.txt

Tier 3 dimensions captured per DI:
  - missing_do (TRACK A)
  - missing_vt (TRACK B - hand off)
  - do_class_conflict (TRACK C)
  - missing_risk_for_class_b (TRACK D)
"""

import csv
import json
from collections import defaultdict
from pathlib import Path


MATRIX_PATH = Path(
    "/Users/robsmith/.cursor/projects/"
    "Users-robsmith-Documents-github-LEO-AI-CORE/agent-tools/"
    "6b57d34c-b6ac-4b8b-88d3-6ac09982d3f3.txt"
)

OUT_DIR = Path(__file__).parent
OUT_DIR.mkdir(parents=True, exist_ok=True)

# MVP-scope UN dcIds. R1 explicit, R7 anchored on UN-64F0E9C3 plus its 6 DIs'
# parent UN. R3/R4/R5 derived by classifying titles (see classify_release).
R1_UNS = {
    "UN-AA722A75", "UN-A949A642", "UN-C2F187E9", "UN-412D1ECD",
    "UN-65571220", "UN-30A82196", "UN-7913344A", "UN-FBBFD5CB",
    "UN-AFFA1FB3", "UN-575E8DCB", "UN-0374FE26", "UN-04E94B6F",
    "UN-79318B40", "UN-D7186F4F", "UN-EE9C8DC9", "UN-2D6BD78B",
    "UN-AA00A211", "UN-39591899", "UN-94BCC4DC", "UN-EAD58F62",
}
R7_UNS = {"UN-64F0E9C3"}

R3_KEYWORDS = (
    "review", "reviewer", "correction", "ask leo", "gold label",
    "assertion", "training feedback", "label",
)
R4_KEYWORDS = (
    "knowledge author", "guideline rule", "terminology", "approval",
    "cso review", "deployment gate", "change request", "rule activation",
    "biomap", "rule edit",
)
R5_KEYWORDS = (
    "tenant", "admin", "user management", "audit log", "multi-tenant",
    "rbac", "ods sync", "billing", "onboarding",
)
R7_KEYWORDS = ("widget", "sdk", "embed", "embedding")


def classify_release(un_dcid: str, title: str, description: str) -> str:
    if un_dcid in R1_UNS:
        return "R1"
    if un_dcid in R7_UNS:
        return "R7"
    text = f"{title} {description}".lower()
    if any(k in text for k in R7_KEYWORDS):
        return "R7"
    if any(k in text for k in R4_KEYWORDS):
        return "R4"
    if any(k in text for k in R3_KEYWORDS):
        return "R3"
    if any(k in text for k in R5_KEYWORDS):
        return "R5"
    return "post-MVP"


def main() -> None:
    data = json.loads(MATRIX_PATH.read_text())
    nodes = {n["id"]: n for n in data["nodes"]}
    links = data["links"]

    # Indexes by DI uuid
    do_for_di: dict[str, list[str]] = defaultdict(list)
    vt_for_di: dict[str, list[str]] = defaultdict(list)
    risk_for_di: dict[str, list[str]] = defaultdict(list)
    di_for_un: dict[str, list[str]] = defaultdict(list)
    risk_for_un: dict[str, list[str]] = defaultdict(list)

    for link in links:
        src, tgt, rel = link["source"], link["target"], link["relationship"]
        if rel == "IMPLEMENTS":
            do_for_di[tgt].append(src)
        elif rel == "VERIFIES":
            vt_for_di[tgt].append(src)
        elif rel == "MITIGATES":
            risk_for_di[src].append(tgt)
        elif rel == "HAS_DESIGN_INPUT":
            di_for_un[src].append(tgt)
        elif rel == "HAS_RISK":
            risk_for_un[src].append(tgt)

    # Reverse: DI -> UN(s)
    un_for_di: dict[str, list[str]] = defaultdict(list)
    for un_id, di_ids in di_for_un.items():
        for di_id in di_ids:
            un_for_di[di_id].append(un_id)

    rows_full: list[dict] = []
    for di_uuid, di in nodes.items():
        if di.get("dcType") != "design-input":
            continue
        un_uuids = un_for_di.get(di_uuid, [])
        un_dcids = [nodes[u]["dcId"] for u in un_uuids if u in nodes]
        un_titles = [nodes[u]["title"] for u in un_uuids if u in nodes]
        release = "unmapped"
        for un_uuid, un_dcid, un_title in zip(un_uuids, un_dcids, un_titles):
            r = classify_release(
                un_dcid, un_title, nodes[un_uuid].get("description", "")
            )
            if r != "post-MVP":
                release = r
                break
        else:
            if un_uuids:
                release = "post-MVP"

        do_ids = do_for_di.get(di_uuid, [])
        vt_ids = vt_for_di.get(di_uuid, [])
        risk_ids_via_di = risk_for_di.get(di_uuid, [])
        # Risks linked to UN are also acceptable risk-coverage for the DI
        risk_ids_via_un = []
        for un_uuid in un_uuids:
            risk_ids_via_un.extend(risk_for_un.get(un_uuid, []))
        risk_ids_total = set(risk_ids_via_di) | set(risk_ids_via_un)

        do_classes = [nodes[d].get("safetyClass") for d in do_ids if d in nodes]
        do_conflict = any(c and c != di.get("safetyClass") for c in do_classes)

        gaps: list[str] = []
        if not do_ids:
            gaps.append("missing_do")
        if not vt_ids:
            gaps.append("missing_vt")
        if do_conflict:
            gaps.append("do_class_conflict")
        if di.get("safetyClass") == "B" and not risk_ids_total:
            gaps.append("missing_risk_for_class_b")

        rows_full.append(
            {
                "di_dcid": di["dcId"],
                "di_title": di["title"],
                "di_safety_class": di.get("safetyClass") or "",
                "un_dcids": "|".join(un_dcids),
                "release": release,
                "do_dcids": "|".join(nodes[d]["dcId"] for d in do_ids if d in nodes),
                "do_safety_classes": "|".join(c or "" for c in do_classes),
                "vt_dcids": "|".join(
                    nodes[v]["dcId"] for v in vt_ids if v in nodes
                ),
                "risk_dcids": "|".join(
                    nodes[r]["dcId"] for r in risk_ids_total if r in nodes
                ),
                "do_count": len(do_ids),
                "vt_count": len(vt_ids),
                "risk_count": len(risk_ids_total),
                "gap_class": ";".join(gaps) if gaps else "no_gaps",
            }
        )

    full_csv = OUT_DIR / "all_di_consistency.csv"
    write_csv(full_csv, rows_full)

    mvp_rows = [r for r in rows_full if r["release"] in {"R1", "R3", "R4", "R5", "R7"}]
    mvp_csv = OUT_DIR / "mvp_consistency_backlog.csv"
    write_csv(mvp_csv, mvp_rows)

    # Summary
    by_release_gap: dict[tuple[str, str], int] = defaultdict(int)
    for r in mvp_rows:
        for g in r["gap_class"].split(";"):
            by_release_gap[(r["release"], g)] += 1

    summary_lines = [
        f"Total DIs in product: {len(rows_full)}",
        f"DIs in MVP scope (R1/R3/R4/R5/R7): {len(mvp_rows)}",
        f"DIs unmapped to any UN: {sum(1 for r in rows_full if r['release']=='unmapped')}",
        "",
        "MVP-scope gap counts by release x gap:",
    ]
    for (rel, gap), n in sorted(by_release_gap.items()):
        summary_lines.append(f"  {rel:10s} {gap:30s} {n}")

    summary_lines.append("")
    summary_lines.append("MVP-scope DIs with no_gaps:")
    summary_lines.append(
        f"  {sum(1 for r in mvp_rows if r['gap_class']=='no_gaps')}"
    )

    out_summary = OUT_DIR / "summary.txt"
    out_summary.write_text("\n".join(summary_lines) + "\n")
    print("\n".join(summary_lines))
    print()
    print(f"Wrote {full_csv}")
    print(f"Wrote {mvp_csv}")
    print(f"Wrote {out_summary}")


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
