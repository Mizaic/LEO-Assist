"""For each patient with referral + specialist but NO diagnosis anchor,
pull all encounters within 100 days of their earliest referral and
print them for review.

Run:
    python scripts/investigations/_investigate_no_diagnosis_patients.py
    python scripts/investigations/_investigate_no_diagnosis_patients.py --out results.txt
"""

from __future__ import annotations

import argparse
import sys
import textwrap

# Force UTF-8 output on Windows consoles that default to cp1252
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

# 36 patients with referral + specialist but zero diagnosis anchors
# (from _run_episodes_and_stats.py output, 2026-04-06)
NO_DIAG_PATIENTS = [
    "9990010021",
    "9990010024",
    "9990010026",
    "9990010027",
    "9990001001",
    "9990010030",
    "9990001002",
    "9990010032",
    "9990010033",
    "9990010035",
    "9990010036",
    "9990010040",
    "9990010042",
    "9990010044",
    "9990010045",
    "9990010047",
    "9990001004",
    "9990010048",
    "9990010051",
    "9990010052",
    "9990010056",
    "9990010057",
    "9990010058",
    "9990010059",
    "9990002015",
    "9990010062",
    "9990010063",
    "9990010064",
    "9990010065",
    "9990010066",
    "9990010068",
    "9990010069",
    "9990010070",
    "9990010071",
    "9990010073",
    "9990010074",
]

WINDOW_DAYS = 365

# Earliest referral date from EpisodeOfCare
_Q_EARLIEST_REFERRAL = """
MATCH (ep:EpisodeOfCare {patient_id: $patient_id})
WHERE ep.referral_date IS NOT NULL
RETURN min(ep.referral_date) AS earliest_referral
"""

# All encounters in a date window, with their existing codings
_Q_ENCOUNTERS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id
  AND e.date >= $start_date
  AND e.date <= $end_date
OPTIONAL MATCH (e)-[doc:DOCUMENTS]->(concept)
WITH e, collect(
    coalesce(concept.name, toString(concept.conceptId)) + ' [' +
    coalesce(doc.context, '') + ']'
) AS codings
RETURN
    toString(e.id)                                  AS encounter_id,
    toString(e.date)                                AS date,
    coalesce(e.text, e.note, e.description, '')     AS enc_text,
    codings
ORDER BY e.date
"""

# Referral and specialist anchors on these encounters
_Q_ANCHORS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[doc:DOCUMENTS]->(c)
WHERE toString(p.id) = $patient_id
  AND c.conceptId IN $fast_track_concepts
RETURN
    toString(e.id)   AS encounter_id,
    toString(e.date) AS date,
    c.name           AS concept_name,
    c.conceptId      AS concept_id
ORDER BY e.date
"""

# Fast-track referral and specialist SNOMED concept IDs (broad set)
FAST_TRACK_CONCEPT_PREFIXES = [
    "27",  # fast track referrals start with 27...
    "38",  # seen in fast track start with 38...
    "19925",  # generic fast track referral
]


def _is_fast_track(concept_id) -> bool:
    s = str(concept_id)
    return any(s.startswith(p) for p in FAST_TRACK_CONCEPT_PREFIXES)


def _date_from_neo4j(val) -> datetime | None:
    if val is None:
        return None
    if hasattr(val, "year"):
        return datetime(val.year, val.month, val.day)
    try:
        s = str(val)[:10]
        return datetime.strptime(s, "%Y-%m-%d")
    except Exception:
        return None


def _wrap(text: str, width: int = 100, indent: str = "    ") -> str:
    if not text:
        return f"{indent}(no text)"
    lines = text.splitlines()
    out = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        out.extend(
            textwrap.wrap(
                stripped, width=width, initial_indent=indent, subsequent_indent=indent
            )
        )
    return "\n".join(out[:40])  # cap at 40 lines per encounter


def investigate(patient_ids: list[str], out_path: Path | None) -> None:
    from libs.neo4j_client.client import PatientGraphClient

    sink = open(out_path, "w", encoding="utf-8") if out_path else None

    def emit(line: str = "") -> None:
        print(line)
        if sink:
            sink.write(line + "\n")

    client = PatientGraphClient()

    for idx, patient_id in enumerate(patient_ids, 1):
        emit()
        emit("=" * 80)
        emit(
            f"PATIENT {idx}/{len(patient_ids)}  id={patient_id}"
            "  (referral + specialist, no diagnosis)"
        )
        emit("=" * 80)

        # Fresh session per patient to avoid timeout
        try:
            with client.session() as session:
                row = session.run(_Q_EARLIEST_REFERRAL, patient_id=patient_id).single()
                earliest = _date_from_neo4j(row["earliest_referral"]) if row else None

            if not earliest:
                emit("  [NO REFERRAL DATE in EpisodeOfCare - skipping]")
                continue

            end_dt = earliest + timedelta(days=WINDOW_DAYS)
            emit(
                f"  Earliest referral : {earliest.date()}"
                f"  |  Window: {earliest.date()} -> {end_dt.date()} ({WINDOW_DAYS} days)"
            )
            emit()

            with client.session() as session:
                encounters = list(
                    session.run(
                        _Q_ENCOUNTERS,
                        patient_id=patient_id,
                        start_date=earliest.strftime("%Y-%m-%d"),
                        end_date=end_dt.strftime("%Y-%m-%d"),
                    )
                )

        except Exception as exc:
            emit(f"  [ERROR: {exc}]")
            continue

        if not encounters:
            emit("  [No encounters found in window]")
            continue

        emit(f"  {len(encounters)} encounter(s) in window:")
        emit()

        for enc in encounters:
            enc_id = enc["encounter_id"] or ""
            date = enc["date"] or ""
            text = enc["enc_text"] or ""
            codings = [c for c in (enc["codings"] or []) if c.strip() and c != " []"]

            emit(f"  -- {date}  enc={enc_id[:8]} --")
            if codings:
                emit(f"  Coded: {', '.join(codings)}")
            if text:
                emit(_wrap(text))
            else:
                emit("    (no text)")
            emit()

    client.close()
    if sink:
        sink.close()
        print(f"\nOutput written to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional file path to write output (in addition to stdout)",
    )
    parser.add_argument(
        "--patient",
        default=None,
        help="Run for a single patient ID only (for testing)",
    )
    args = parser.parse_args()

    patients = [args.patient] if args.patient else NO_DIAG_PATIENTS
    investigate(patients, args.out)


if __name__ == "__main__":
    main()
