#!/usr/bin/env python3
"""For every NEW candidate in the dry-run, show the patient's confirmed
diagnosis concepts vs the FTR / Dx evidence the detector picked.

Goal: confirm that every NEW episode is anchored to a real FTR and/or a
real diagnosis encounter (not an admin note or unrelated milestone).
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
  coalesce(e.source,'<null>') AS source
"""


def _short(s: str | None, n: int = 220) -> str:
    if not s:
        return ""
    s = s.replace("\n", " ").strip()
    if len(s) > n:
        s = s[:n] + " ..."
    return s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dry_run_json", type=Path)
    ap.add_argument("--only-new", action="store_true", default=True)
    args = ap.parse_args()

    payload = json.loads(args.dry_run_json.read_text())
    candidates = payload["episode_candidates"]

    cand_by_pid: dict[str, list[dict]] = defaultdict(list)
    diags_by_pid: dict[str, list[dict]] = {}
    for c in candidates:
        pid = str(c["patient_id"])
        site = c.get("site") or "unknown"
        ftr_date = (c.get("ftr") or {}).get("encounter_date") or ""
        dx_date = (c.get("dx") or {}).get("encounter_date") or ""
        anchor = ftr_date or dx_date
        c["_eid"] = _det_episode_id(pid, site, anchor)
        cand_by_pid[pid].append(c)
        diags_by_pid[pid] = c.get("diagnosis_concepts") or []

    pids = sorted(cand_by_pid.keys())
    driver = _connect()
    existing_eids: dict[str, set[str]] = defaultdict(set)
    try:
        with driver.session() as s:
            for r in s.run(_GRAPH_QUERY, pids=pids):
                if r["source"] == "ncda_detector":
                    existing_eids[r["pid"]].add(r["eid"])
    finally:
        driver.close()

    print(f"\n{'='*84}\nNEW CANDIDATES vs PATIENT DIAGNOSES\n{'='*84}")
    for pid in pids:
        cands = cand_by_pid[pid]
        new = [c for c in cands if c["_eid"] not in existing_eids.get(pid, set())]
        if args.only_new and not new:
            continue
        print(f"\n=== Patient {pid} ===")
        if diags_by_pid.get(pid):
            print("  Confirmed diagnosis concepts (DOCUMENTS edges):")
            for d in diags_by_pid[pid][:10]:
                print(f"    - {d.get('concept_id'):>14}  {d.get('concept_name')}")
        for c in new:
            ftr = c.get("ftr") or {}
            dx = c.get("dx") or {}
            print(f"\n  NEW {c['_eid']}  cohort={c.get('cohort')}  site={c.get('site')}  route={c.get('diagnosis_route')}")
            print(f"    FTR ({ftr.get('encounter_date') or '-'}): role={ftr.get('role') or '-'} site={ftr.get('site') or '-'}")
            print(f"      \"{_short(ftr.get('text_preview'))}\"")
            print(f"    Dx  ({dx.get('encounter_date') or '-'}): role={dx.get('role') or '-'} outcome={dx.get('outcome') or '-'} site={dx.get('site') or '-'}")
            print(f"      \"{_short(dx.get('text_preview'))}\"")
            for note in (c.get("notes") or [])[:3]:
                print(f"    note: {note}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
