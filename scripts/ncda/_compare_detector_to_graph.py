#!/usr/bin/env python3
"""Compare a dry-run detector JSON against current graph state.

Reads the latest dry-run JSON in artifacts/ncda_full_run, recomputes the
deterministic episode_id for each candidate, then queries Neo4j for all
EpisodeOfCare nodes for the same patients and prints a diff:

  NEW       : detector candidate not in graph (would be created)
  SAME      : detector candidate already exists (idempotent refresh)
  DELETED   : existing ncda_detector episode that detector no longer emits
              (would be hard-deleted by the --apply pass)
  GUARDED   : reviewed episode for the same patient (always preserved)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)


def _det_episode_id(patient_id: str, site: str, anchor_date: str) -> str:
    raw = f"{patient_id}|{site}|{anchor_date}|ncda"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _connect():
    uri = os.environ.get("NEO4J_PATIENT_URI", "").strip() or os.environ.get("NEO4J_URI", "").strip()
    user = os.environ.get("NEO4J_PATIENT_USER", "").strip() or os.environ.get("NEO4J_USER", "").strip()
    pw = os.environ.get("NEO4J_PATIENT_PASSWORD", "").strip() or os.environ.get("NEO4J_PASSWORD", "").strip()
    return GraphDatabase.driver(uri, auth=(user, pw))


_GRAPH_QUERY = """
MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE|HAS_EPISODE]->(e:EpisodeOfCare)
WHERE coalesce(toString(p.id), toString(p.patient_id)) IN $pids
RETURN
  coalesce(toString(p.id), toString(p.patient_id)) AS pid,
  e.episode_id   AS eid,
  coalesce(e.source,'<null>') AS source,
  coalesce(e.cancer_type,'')  AS ct,
  coalesce(e.site,'')         AS site,
  coalesce(e.cohort,'')       AS cohort,
  coalesce(e.referral_date,'') AS ref,
  coalesce(e.end_date,'')      AS end_date,
  coalesce(e.review_verdict,'') AS verdict
ORDER BY pid, source, ref
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dry_run_json", type=Path)
    args = ap.parse_args()

    payload = json.loads(args.dry_run_json.read_text())
    candidates = payload["episode_candidates"]

    cand_by_pid: dict[str, list[dict]] = defaultdict(list)
    for c in candidates:
        pid = str(c["patient_id"])
        site = c.get("site") or "unknown"
        ftr_date = (c.get("ftr") or {}).get("encounter_date") or ""
        dx_date = (c.get("dx") or {}).get("encounter_date") or ""
        anchor = ftr_date or dx_date
        # Honour anchor stabilisation: when the detector's guard layer reused an
        # existing detector eid (drift <= N days), the candidate carries a
        # _stable_eid that is the eid actually used at MERGE time.
        eid = c.get("_stable_eid") or _det_episode_id(pid, site, anchor)
        cand_by_pid[pid].append({
            "eid": eid,
            "site": site,
            "cohort": c.get("cohort"),
            "ftr_date": ftr_date,
            "dx_date": dx_date,
            "stabilised": bool(c.get("_stable_eid")),
            "ct_hint": (c.get("dx") or {}).get("text_preview", "")[:60].replace("\n", " "),
        })

    pids = sorted(cand_by_pid.keys())

    driver = _connect()
    graph_by_pid: dict[str, list[dict]] = defaultdict(list)
    try:
        with driver.session() as s:
            for r in s.run(_GRAPH_QUERY, pids=pids):
                graph_by_pid[r["pid"]].append({
                    "eid": r["eid"],
                    "source": r["source"],
                    "ct": r["ct"],
                    "site": r["site"],
                    "cohort": r["cohort"],
                    "ref": r["ref"],
                    "end_date": r["end_date"],
                    "verdict": r["verdict"],
                })
    finally:
        driver.close()

    n_new = n_same = n_deleted = n_guarded = 0
    print(f"\n{'='*78}\nDETECTOR DRY-RUN vs GRAPH (per-patient diff)\n{'='*78}")
    print(f"Source JSON     : {args.dry_run_json}")
    print(f"Patients in run : {len(pids)}")
    print(f"Total candidates: {sum(len(v) for v in cand_by_pid.values())}\n")

    for pid in pids:
        cands = cand_by_pid[pid]
        existing = graph_by_pid.get(pid, [])
        cand_eids = {c["eid"] for c in cands}
        det_existing = {e["eid"]: e for e in existing if e["source"] == "ncda_detector"}
        reviewed_existing = [e for e in existing if e["source"] != "ncda_detector"]

        new_eids = cand_eids - det_existing.keys()
        same_eids = cand_eids & det_existing.keys()
        deleted_eids = det_existing.keys() - cand_eids

        if not new_eids and not deleted_eids and not reviewed_existing:
            n_same += len(same_eids)
            continue

        print(f"\n--- {pid} -----------------------------------------------------")
        for c in cands:
            tag = "NEW" if c["eid"] in new_eids else ("STABLE" if c.get("stabilised") else "SAME")
            ref = c["ftr_date"] or c["dx_date"]
            print(f"  [{tag:7}] {c['eid']}  cohort={c['cohort']:<3} site={c['site']:<14} ref/dx={ref}  hint='{c['ct_hint']}'")
        for eid in deleted_eids:
            e = det_existing[eid]
            print(f"  [DELETED] {eid}  cohort={e['cohort']:<3} site={e['site']:<14} ref={e['ref'] or e['end_date']}  ct={e['ct']}")
        for e in reviewed_existing:
            print(f"  [GUARDED] {e['eid']}  source={e['source']:<13} ct={e['ct']:<14} ref={e['ref'] or e['end_date']}  verdict={e['verdict']}")

        n_new += len(new_eids)
        n_same += len(same_eids)
        n_deleted += len(deleted_eids)
        n_guarded += len(reviewed_existing)

    print(f"\n{'='*78}\nSUMMARY")
    print(f"  NEW (would create)        : {n_new}")
    print(f"  SAME (idempotent refresh) : {n_same}")
    print(f"  DELETED (would drop)      : {n_deleted}")
    print(f"  GUARDED (reviewed kept)   : {n_guarded}")
    print(f"{'='*78}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
