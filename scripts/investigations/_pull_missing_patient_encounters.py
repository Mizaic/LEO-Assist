"""Pull all encounters (no date filter) for specific patients whose
EpisodeOfCare nodes had no referral_date, so they were skipped by the
standard review scripts.

Usage:
    python scripts/investigations/_pull_missing_patient_encounters.py
    python scripts/investigations/_pull_missing_patient_encounters.py --out missing_patients_review.txt
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

_PATIENT_IDS = [
    "9990010042",
    "9990010062",
    "9990010069",
]

_Q_EPISODES = """
MATCH (ep:EpisodeOfCare {patient_id: $pid})
RETURN
    ep.id               AS ep_id,
    ep.status           AS status,
    ep.cancer_type      AS cancer_type,
    ep.referral_date    AS referral_date,
    ep.specialist_seen  AS specialist_seen
ORDER BY ep.referral_date
"""

_Q_ENCOUNTERS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $pid
OPTIONAL MATCH (e)-[doc:DOCUMENTS]->(concept)
WITH e, collect(coalesce(concept.name, toString(concept.conceptId))) AS codings
RETURN
    toString(e.id)                                  AS eid,
    toString(e.date)                                AS date,
    coalesce(e.text, e.note, e.description, '')     AS enc_text,
    codings
ORDER BY e.date
"""

_LINE_WIDTH = 100
_MAX_LINES_PER_ENC = 80


def _wrap(text: str, prefix: str = "    ") -> list[str]:
    lines = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        wrapped = textwrap.wrap(stripped, width=_LINE_WIDTH - len(prefix))
        lines.extend(prefix + w for w in (wrapped or [stripped]))
    return lines


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", help="Output file path")
    args = parser.parse_args()

    out_fh = None
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_fh = out_path.open("w", encoding="utf-8", errors="replace")

    def emit(line: str = "") -> None:
        print(line)
        if out_fh:
            out_fh.write(line + "\n")

    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()

    for idx, pid in enumerate(_PATIENT_IDS, 1):
        sep = "=" * 80
        emit()
        emit(sep)
        emit(
            f"PATIENT {idx}/{len(_PATIENT_IDS)}  id={pid}  (no referral_date - full history)"
        )
        emit(sep)

        episodes = client.run(_Q_EPISODES, pid=pid) or []
        if episodes:
            emit(f"  Episodes in graph: {len(episodes)}")
            for ep in episodes:
                emit(
                    f"    status={ep.get('status')}  type={ep.get('cancer_type')}  "
                    f"ref={ep.get('referral_date')}  spec={ep.get('specialist_seen')}"
                )
        else:
            emit("  [No EpisodeOfCare nodes found]")

        emit()
        encounters = client.run(_Q_ENCOUNTERS, pid=pid) or []
        emit(f"  {len(encounters)} encounter(s) (all time, no date filter):")
        emit()

        for enc in encounters:
            eid = str(enc.get("eid") or "")
            date = enc.get("date", "????-??-??")
            text = enc.get("enc_text") or ""
            codings = enc.get("codings") or []

            emit(f"  -- {date}  enc={eid[:8]} --")
            if codings:
                coded_str = ", ".join(str(c) for c in codings if c)
                emit(f"  Coded: {coded_str}")

            if text.strip():
                lines = _wrap(text)[:_MAX_LINES_PER_ENC]
                for ln in lines:
                    emit(ln)
                if len(_wrap(text)) > _MAX_LINES_PER_ENC:
                    emit(
                        f"    ... [{len(_wrap(text)) - _MAX_LINES_PER_ENC} more lines truncated]"
                    )
            else:
                emit("    (no text)")
            emit()

    if out_fh:
        out_fh.close()
        print(f"\nWrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
