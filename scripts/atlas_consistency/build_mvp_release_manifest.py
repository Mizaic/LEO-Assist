"""Compute full MVP-scope design-control manifest for release El Medano.

Walks downstream from MVP UNs (as classified in build_backlog.py) to collect
every DI, DO, VT, Risk, and VAL that must be scoped into release
8e5bb2c8-af34-4f26-997b-ab4781ad7b24.

Writes:
  - mvp_release_manifest.csv  (one row per DC, columns dc_type, dc_id, dc_title, release)
  - mvp_release_manifest_summary.txt

Edges used (all directed):
  HAS_DESIGN_INPUT : UN -> DI
  IMPLEMENTS       : DO -> DI
  VERIFIES         : VT -> DI
  TESTS            : VT -> DO
  MITIGATES        : DI -> Risk
  HAS_RISK         : UN -> Risk
  VALIDATES        : DI -> VAL
"""

import csv
import json
from collections import defaultdict
from pathlib import Path

from build_backlog import MATRIX_PATH, classify_release

OUT_DIR = Path(__file__).parent

RELEASE_ID = "8e5bb2c8-af34-4f26-997b-ab4781ad7b24"


def main() -> None:
    data = json.loads(MATRIX_PATH.read_text())
    nodes = {n["id"]: n for n in data["nodes"]}
    links = data["links"]

    # Forward indexes
    di_for_un: dict[str, list[str]] = defaultdict(list)
    do_for_di: dict[str, list[str]] = defaultdict(list)
    vt_for_di: dict[str, list[str]] = defaultdict(list)
    vt_for_do: dict[str, list[str]] = defaultdict(list)
    risk_for_di: dict[str, list[str]] = defaultdict(list)
    risk_for_un: dict[str, list[str]] = defaultdict(list)
    val_for_di: dict[str, list[str]] = defaultdict(list)

    for link in links:
        src, tgt, rel = link["source"], link["target"], link["relationship"]
        if rel == "HAS_DESIGN_INPUT":
            di_for_un[src].append(tgt)
        elif rel == "IMPLEMENTS":
            do_for_di[tgt].append(src)
        elif rel == "VERIFIES":
            vt_for_di[tgt].append(src)
        elif rel == "TESTS":
            vt_for_do[tgt].append(src)
        elif rel == "MITIGATES":
            risk_for_di[src].append(tgt)
        elif rel == "HAS_RISK":
            risk_for_un[src].append(tgt)
        elif rel == "VALIDATES":
            val_for_di[src].append(tgt)

    # 1. Classify UNs into MVP releases
    un_release: dict[str, str] = {}
    for uuid, node in nodes.items():
        if node.get("dcType") != "user-need":
            continue
        un_release[uuid] = classify_release(
            node["dcId"], node.get("title", ""), node.get("description", "")
        )

    mvp_un = {u for u, r in un_release.items() if r in {"R1", "R3", "R4", "R5", "R7"}}

    # 2. Walk UN -> DI
    mvp_di: set[str] = set()
    for un in mvp_un:
        mvp_di.update(di_for_un.get(un, []))

    # 3. Walk DI -> DO (inverse of IMPLEMENTS)
    mvp_do: set[str] = set()
    for di in mvp_di:
        mvp_do.update(do_for_di.get(di, []))

    # 4. Walk DI -> VT and DO -> VT
    mvp_vt: set[str] = set()
    for di in mvp_di:
        mvp_vt.update(vt_for_di.get(di, []))
    for do in mvp_do:
        mvp_vt.update(vt_for_do.get(do, []))

    # 5. Walk DI -> Risk and UN -> Risk
    mvp_risk: set[str] = set()
    for di in mvp_di:
        mvp_risk.update(risk_for_di.get(di, []))
    for un in mvp_un:
        mvp_risk.update(risk_for_un.get(un, []))

    # 6. Walk DI -> VAL
    mvp_val: set[str] = set()
    for di in mvp_di:
        mvp_val.update(val_for_di.get(di, []))

    # Assemble manifest rows
    rows: list[dict] = []
    release_of_di: dict[str, str] = {}
    # Map each DI to the release label of its first MVP UN
    di_to_un_release: dict[str, str] = {}
    for un in mvp_un:
        for di in di_for_un.get(un, []):
            if di in mvp_di and di not in di_to_un_release:
                di_to_un_release[di] = un_release[un]

    def dc_release(uuid: str) -> str:
        if uuid in di_to_un_release:
            return di_to_un_release[uuid]
        return ""

    for group_label, type_name, uuid_set in [
        ("design-input", "design-input", mvp_di),
        ("design-output", "design-output", mvp_do),
        ("verification-test", "verification-test", mvp_vt),
        ("risk", "risk", mvp_risk),
        ("validation-test", "validation-test", mvp_val),
    ]:
        for uuid in sorted(uuid_set):
            node = nodes[uuid]
            rows.append(
                {
                    "dc_type": type_name,
                    "dc_uuid": uuid,
                    "dc_id": node["dcId"],
                    "dc_title": node.get("title", ""),
                    "safety_class": node.get("safetyClass") or "",
                    "release_wave": dc_release(uuid),
                }
            )

    out_csv = OUT_DIR / "mvp_release_manifest.csv"
    with out_csv.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # Per-wave breakdown for DIs
    by_wave_di: dict[str, int] = defaultdict(int)
    for di in mvp_di:
        by_wave_di[di_to_un_release.get(di, "?")] += 1

    summary = [
        f"MVP UN count: {len(mvp_un)}",
        f"MVP DI count: {len(mvp_di)}",
        f"MVP DO count: {len(mvp_do)}",
        f"MVP VT count: {len(mvp_vt)}",
        f"MVP Risk count: {len(mvp_risk)}",
        f"MVP VAL count: {len(mvp_val)}",
        "",
        f"Total DCs to scope into release ({RELEASE_ID}):",
        f"  {len(mvp_di) + len(mvp_do) + len(mvp_vt) + len(mvp_risk) + len(mvp_val)}",
        "",
        "DIs by release wave:",
    ]
    for wave in ("R1", "R3", "R4", "R5", "R7"):
        summary.append(f"  {wave}: {by_wave_di.get(wave, 0)}")

    out_summary = OUT_DIR / "mvp_release_manifest_summary.txt"
    out_summary.write_text("\n".join(summary) + "\n")
    print("\n".join(summary))
    print()
    print(f"Wrote {out_csv}")
    print(f"Wrote {out_summary}")


if __name__ == "__main__":
    main()
