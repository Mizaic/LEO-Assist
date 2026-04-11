"""Structured patient -> episode -> milestone report.

Format:
  Patient <id>  (<n> episodes)
   - Episode 1  [status]  <site>  ref:<date>
     -- Referral    : <date>  <concept>
     -- First Seen  : <date>  <concept>
     -- Diagnosis   : <date>  <concept>
     -- Treatment   : <date>  <concept>  (or 'none coded')
   - Episode 2  ...
"""

from __future__ import annotations
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

from libs.neo4j_client.client import PatientGraphClient

STATUS_SYMBOL = {
    "completed": "[DONE]",
    "closed_benign": "[BENIGN]",
    "in_progress": "[OPEN]",
    "stale_post_specialist": "[STALE-SPEC]",
    "stale_no_diagnosis": "[STALE-NODIAG]",
    "closed_related": "[RELATED]",
    "closed_phantom": "[PHANTOM]",
}

# All episodes with their stored milestone dates/concepts
_Q_EPISODES = """
MATCH (ep:EpisodeOfCare)
RETURN
  ep.patient_id            AS pid,
  ep.episode_id            AS eid,
  ep.cancer_type           AS site,
  ep.status                AS status,
  ep.referral_date         AS ref_date,
  ep.referral_site         AS ref_site,
  ep.specialist_seen       AS spec_seen,
  ep.specialist_visit_date AS spec_date,
  ep.cancer_diagnosis_date AS diag_date,
  ep.cancer_diagnosis_concept AS diag_concept,
  ep.hitl_flag             AS hitl,
  ep.auto_close_reason     AS close_reason
ORDER BY ep.patient_id, ep.referral_date
"""

# Referral concept: patient encounter on referral date matching fast-track referral patterns
_Q_REF_CONCEPT = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(enc:Encounter)-[:DOCUMENTS]->(c)
WHERE toString(p.id) = $pid AND enc.date = $ref_date
  AND (toLower(c.name) CONTAINS 'fast track' OR toLower(c.name) CONTAINS '2ww'
    OR toLower(c.name) CONTAINS 'two week' OR toLower(c.name) CONTAINS 'suspected cancer'
    OR toLower(c.name) CONTAINS 'urgent cancer')
RETURN c.name AS name
ORDER BY c.name
LIMIT 1
"""

# Specialist clinic concept: on specialist visit date
_Q_SPEC_CONCEPT = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(enc:Encounter)-[:DOCUMENTS]->(c)
WHERE toString(p.id) = $pid AND enc.date = $spec_date
  AND (toLower(c.name) CONTAINS 'fast track' OR toLower(c.name) CONTAINS 'clinic'
    OR toLower(c.name) CONTAINS 'seen in fast' OR toLower(c.name) CONTAINS 'suspected')
  AND c.semanticTag IN ['Clinical_finding', 'Procedure']
RETURN c.name AS name
ORDER BY c.name
LIMIT 1
"""

# Diagnosis: cancer concept between referral and end date (window = 365 days max)
_Q_DIAGNOSIS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(enc:Encounter)-[:DOCUMENTS]->(c)
WHERE toString(p.id) = $pid AND enc.date >= $ref_date AND enc.date <= $window_end
  AND c.semanticTag IN ['Disease', 'disorder', 'Clinical_finding', 'Situation']
  AND (
    toLower(c.name) CONTAINS 'malignant' OR toLower(c.name) CONTAINS 'cancer'
    OR toLower(c.name) CONTAINS 'carcinoma' OR toLower(c.name) CONTAINS 'neoplasm'
    OR toLower(c.name) CONTAINS 'lymphoma' OR toLower(c.name) CONTAINS 'leukaemia'
    OR toLower(c.name) CONTAINS 'leukemia' OR toLower(c.name) CONTAINS 'melanoma'
    OR toLower(c.name) CONTAINS 'sarcoma' OR toLower(c.name) CONTAINS 'myeloma'
    OR toLower(c.name) CONTAINS 'no evidence of cancer'
    OR toLower(c.name) CONTAINS 'irritable bowel' OR toLower(c.name) CONTAINS 'polyp'
    OR toLower(c.name) CONTAINS 'fibroadenoma' OR toLower(c.name) CONTAINS 'cyst of breast'
    OR toLower(c.name) CONTAINS 'diverticular' OR toLower(c.name) CONTAINS 'adenoma'
  )
RETURN enc.date AS date, c.name AS name
ORDER BY enc.date
LIMIT 1
"""

# Treatment: surgical/oncological procedure after referral
_Q_TREATMENT = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(enc:Encounter)-[:DOCUMENTS]->(c)
WHERE toString(p.id) = $pid AND enc.date >= $ref_date AND enc.date <= $window_end
  AND c.semanticTag IN ['Procedure']
  AND (toLower(c.name) CONTAINS 'chemotherapy' OR toLower(c.name) CONTAINS 'radiotherapy'
    OR toLower(c.name) CONTAINS 'excision' OR toLower(c.name) CONTAINS 'resection'
    OR toLower(c.name) CONTAINS 'mastectomy' OR toLower(c.name) CONTAINS 'colectomy'
    OR toLower(c.name) CONTAINS 'cystectomy' OR toLower(c.name) CONTAINS 'prostatectomy'
    OR toLower(c.name) CONTAINS 'nephrectomy' OR toLower(c.name) CONTAINS 'hemicolectomy'
    OR toLower(c.name) CONTAINS 'orchidectomy' OR toLower(c.name) CONTAINS 'thyroidectomy')
RETURN enc.date AS date, c.name AS name
ORDER BY enc.date
LIMIT 1
"""


def _trunc(s: str, n: int = 70) -> str:
    s = str(s or "")
    return s[:n] + "..." if len(s) > n else s


def _fmt(val, missing: str = "not coded") -> str:
    return str(val) if val else missing


def main() -> None:
    client = PatientGraphClient()
    try:
        with client.session() as s:
            episodes = s.run(_Q_EPISODES).data()

        by_patient: dict[str, list[dict]] = defaultdict(list)
        for ep in episodes:
            by_patient[str(ep["pid"])].append(ep)

        # Summary counters
        total_eps = len(episodes)
        status_counts: dict[str, int] = defaultdict(int)
        hitl_count = 0

        print()
        print("=" * 80)
        print("CANCER AUDIT -- PATIENT EPISODE REPORT")
        print("=" * 80)

        for pid in sorted(by_patient.keys()):
            eps = by_patient[pid]
            print()
            print(f"Patient {pid}  ({len(eps)} episode{'s' if len(eps) != 1 else ''})")

            for i, ep in enumerate(eps, 1):
                eid = ep["eid"]
                status = ep["status"] or "unknown"
                symbol = STATUS_SYMBOL.get(status, f"[{status.upper()}]")
                site = str(ep["site"] or "unknown").replace("_", " ")
                hitl_marker = " [!HITL]" if ep.get("hitl") else ""
                status_counts[status] += 1
                if ep.get("hitl"):
                    hitl_count += 1

                print(f"  Episode {i}  {symbol}  {site}{hitl_marker}")

                from datetime import date, timedelta

                ref_date_str = str(ep.get("ref_date") or "")
                try:
                    ref_dt = date.fromisoformat(ref_date_str)
                    window_end = (ref_dt + timedelta(days=365)).isoformat()
                except (ValueError, TypeError):
                    window_end = "2099-12-31"

                # Referral
                ref_date = _fmt(ref_date_str, "no referral")
                with client.session() as s:
                    rc = s.run(_Q_REF_CONCEPT, pid=pid, ref_date=ref_date_str).single()
                ref_concept = _trunc(rc["name"] if rc else "", 65)
                print(f"    -- Referral   : {ref_date}  {ref_concept}")

                # First Seen
                spec_date = ep.get("spec_date")
                if spec_date and ep.get("spec_seen"):
                    with client.session() as s:
                        sc = s.run(
                            _Q_SPEC_CONCEPT, pid=pid, spec_date=str(spec_date)
                        ).single()
                    spec_concept = _trunc(sc["name"] if sc else "", 65)
                    print(f"    -- First Seen : {spec_date}  {spec_concept}")
                else:
                    print(f"    -- First Seen : not recorded")

                # Diagnosis
                with client.session() as s:
                    dg = s.run(
                        _Q_DIAGNOSIS,
                        pid=pid,
                        ref_date=ref_date_str,
                        window_end=window_end,
                    ).single()
                if dg:
                    print(f"    -- Diagnosis  : {dg['date']}  {_trunc(dg['name'], 65)}")
                else:
                    print(f"    -- Diagnosis  : not coded")

                # Treatment
                with client.session() as s:
                    tr = s.run(
                        _Q_TREATMENT,
                        pid=pid,
                        ref_date=ref_date_str,
                        window_end=window_end,
                    ).single()
                if tr:
                    print(f"    -- Treatment  : {tr['date']}  {_trunc(tr['name'], 65)}")
                else:
                    print(f"    -- Treatment  : none coded")

        # Summary
        print()
        print("=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"  Patients          : {len(by_patient)}")
        print(f"  Total episodes    : {total_eps}")
        print(f"  HITL flagged      : {hitl_count}")
        print()
        print("  Status breakdown:")
        for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
            symbol = STATUS_SYMBOL.get(status, status)
            pct = 100 * count / total_eps if total_eps else 0
            print(f"    {symbol:<18} {count:>4}  ({pct:.0f}%)")
        print()

        completed = status_counts.get("completed", 0)
        stale = status_counts.get("stale_post_specialist", 0) + status_counts.get(
            "stale_no_diagnosis", 0
        )
        in_prog = status_counts.get("in_progress", 0)
        print(f"  Completed pathways         : {completed}")
        print(f"  Active in-progress         : {in_prog}")
        print(f"  Stale (HITL review needed) : {stale}")
        print(
            f"  Closed related/phantom     : {status_counts.get('closed_related', 0) + status_counts.get('closed_phantom', 0)}"
        )

    finally:
        client.close()


if __name__ == "__main__":
    main()
