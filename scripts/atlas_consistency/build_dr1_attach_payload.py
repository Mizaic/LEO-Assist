"""Build the payload to attach MVP UNs + Risks to DR-1 (2a5e98df-...).

Cross-references:
  - MVP UN set from build_backlog.classify_release() applied to the cached
    traceability matrix
  - server-side candidate lists (already fetched to agent-tools/*.txt)

Emits:
  dr1_attach_payload.json  { "review_id": "...", "uns": [...], "risks": [...] }
  dr1_attach_summary.txt
"""

import json
from pathlib import Path

from build_backlog import MATRIX_PATH, classify_release

OUT_DIR = Path(__file__).parent
REVIEW_ID = "2a5e98df-96b0-4a37-8c80-4cbaf8b80cb1"
UN_CANDIDATES = Path(
    "/Users/robsmith/.cursor/projects/"
    "Users-robsmith-Documents-github-LEO-AI-CORE/agent-tools/"
    "1ac261f3-59f6-4d9f-9bcf-e1cb9359f75d.txt"
)
RISK_CANDIDATES = Path(
    "/Users/robsmith/.cursor/projects/"
    "Users-robsmith-Documents-github-LEO-AI-CORE/agent-tools/"
    "6fcd2e1c-1a39-4450-a719-1cadbbb9f7cc.txt"
)


def main() -> None:
    data = json.loads(MATRIX_PATH.read_text())
    nodes = {n["id"]: n for n in data["nodes"]}

    # 1. Classify MVP UNs
    mvp_un_uuids: set[str] = set()
    wave_of_un: dict[str, str] = {}
    for uuid, node in nodes.items():
        if node.get("dcType") != "user-need":
            continue
        wave = classify_release(
            node["dcId"], node.get("title", ""), node.get("description", "")
        )
        if wave in {"R1", "R3", "R4", "R5", "R7"}:
            mvp_un_uuids.add(uuid)
            wave_of_un[uuid] = wave

    # 2. Walk UN -> Risk via HAS_RISK, plus DI -> Risk via MITIGATES for MVP DIs
    di_for_un: dict[str, list[str]] = {}
    risk_for_di: dict[str, list[str]] = {}
    risk_for_un: dict[str, list[str]] = {}
    for link in data["links"]:
        rel = link["relationship"]
        src = link["source"]
        tgt = link["target"]
        if rel == "HAS_DESIGN_INPUT":
            di_for_un.setdefault(src, []).append(tgt)
        elif rel == "MITIGATES":
            risk_for_di.setdefault(src, []).append(tgt)
        elif rel == "HAS_RISK":
            risk_for_un.setdefault(src, []).append(tgt)

    mvp_di_uuids: set[str] = set()
    for un in mvp_un_uuids:
        mvp_di_uuids.update(di_for_un.get(un, []))

    mvp_risk_uuids: set[str] = set()
    for di in mvp_di_uuids:
        mvp_risk_uuids.update(risk_for_di.get(di, []))
    for un in mvp_un_uuids:
        mvp_risk_uuids.update(risk_for_un.get(un, []))

    # 3. Load server candidate lists
    un_cands = json.loads(UN_CANDIDATES.read_text())["items"]
    risk_cands = json.loads(RISK_CANDIDATES.read_text())["items"]
    un_cand_ids = {c["entity_id"] for c in un_cands}
    risk_cand_ids = {c["entity_id"] for c in risk_cands}

    # 4. Intersect
    un_attach = sorted(mvp_un_uuids & un_cand_ids)
    risk_attach = sorted(mvp_risk_uuids & risk_cand_ids)

    un_missing = sorted(mvp_un_uuids - un_cand_ids)
    risk_missing = sorted(mvp_risk_uuids - risk_cand_ids)

    payload = {
        "review_id": REVIEW_ID,
        "uns": [
            {"entity_type": "user-need", "entity_id": uid} for uid in un_attach
        ],
        "risks": [
            {"entity_type": "risk", "entity_id": rid} for rid in risk_attach
        ],
    }
    out_json = OUT_DIR / "dr1_attach_payload.json"
    out_json.write_text(json.dumps(payload, indent=2))

    # Wave breakdown for UNs
    by_wave: dict[str, int] = {}
    for uid in un_attach:
        by_wave[wave_of_un.get(uid, "?")] = by_wave.get(wave_of_un.get(uid, "?"), 0) + 1

    lines = [
        f"DR-1 review ID: {REVIEW_ID}",
        "",
        f"MVP UNs identified by classifier: {len(mvp_un_uuids)}",
        f"MVP UNs present in server candidates: {len(un_attach)}",
        f"MVP UNs NOT in server candidates: {len(un_missing)}",
        "",
        f"MVP Risks identified by matrix walk: {len(mvp_risk_uuids)}",
        f"MVP Risks present in server candidates: {len(risk_attach)}",
        f"MVP Risks NOT in server candidates: {len(risk_missing)}",
        "",
        "UNs by wave (attachable):",
    ]
    for wave in ("R1", "R3", "R4", "R5", "R7"):
        lines.append(f"  {wave}: {by_wave.get(wave, 0)}")

    if un_missing:
        lines.append("")
        lines.append("UN UUIDs classified as MVP but absent from server candidates:")
        for uid in un_missing[:10]:
            node = nodes.get(uid, {})
            lines.append(f"  {uid}  {node.get('dcId','?')}  {node.get('title','?')[:70]}")
        if len(un_missing) > 10:
            lines.append(f"  ... and {len(un_missing) - 10} more")

    if risk_missing:
        lines.append("")
        lines.append("Risk UUIDs classified as MVP but absent from server candidates:")
        for rid in risk_missing[:10]:
            node = nodes.get(rid, {})
            lines.append(f"  {rid}  {node.get('dcId','?')}  {node.get('title','?')[:70]}")
        if len(risk_missing) > 10:
            lines.append(f"  ... and {len(risk_missing) - 10} more")

    out_summary = OUT_DIR / "dr1_attach_summary.txt"
    out_summary.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print()
    print(f"Wrote {out_json}")
    print(f"Wrote {out_summary}")


if __name__ == "__main__":
    main()
