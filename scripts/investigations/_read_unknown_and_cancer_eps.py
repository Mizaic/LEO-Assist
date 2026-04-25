"""Pull encounters for the 15 UNKNOWN + 5 CANCER_CONFIRMED in_progress episodes.
Print encounter text and all coded concepts with dates for manual root-cause analysis.

Run:
    python scripts/investigations/_read_unknown_and_cancer_eps.py
"""

from __future__ import annotations
import sys
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

# (pid, site, ref_date, category)
_TARGETS = [
    # CANCER_CONFIRMED - episode builder did not close them
    ("9990003001", "lower_gi", "2025-05-13", "CANCER_CONFIRMED"),
    ("9990010072", "breast", "2025-04-11", "CANCER_CONFIRMED"),
    ("9990002011", "upper_gi", "2025-06-27", "CANCER_CONFIRMED"),
    ("9990002011", "non_site_specific", "2024-03-19", "CANCER_CONFIRMED"),
    ("9990002008", "non_site_specific", "2025-09-05", "CANCER_CONFIRMED"),
    # UNKNOWN - no classifiable signal found
    ("9990010043", "head_and_neck", "2024-12-04", "UNKNOWN"),
    ("9990010043", "lower_gi", "2025-01-07", "UNKNOWN"),
    ("9990010032", "breast", "2025-02-10", "UNKNOWN"),
    ("9990010052", "lung", "2025-03-10", "UNKNOWN"),
    ("9990010046", "breast", "2025-04-17", "UNKNOWN"),
    ("9990010050", "head_and_neck", "2025-05-01", "UNKNOWN"),
    ("9990010033", "breast", "2025-07-01", "UNKNOWN"),
    ("9990010031", "lower_gi", "2025-07-02", "UNKNOWN"),
    ("9990010024", "breast", "2025-07-23", "UNKNOWN"),
    ("9990010038", "urological", "2025-07-24", "UNKNOWN"),
    ("9990002010", "breast", "2025-08-04", "UNKNOWN"),
    ("9990010053", "non_site_specific", "2025-08-10", "UNKNOWN"),
    ("9990001004", "upper_gi", "2025-08-12", "UNKNOWN"),
    ("9990001004", "breast", "2025-08-12", "UNKNOWN"),
    ("9990010051", "non_site_specific", "2025-09-13", "UNKNOWN"),
]

_Q_ENCS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE p.id = $pid
  AND toString(e.date) >= $from_date
OPTIONAL MATCH (e)-[doc:DOCUMENTS]->(concept)
WITH e, collect({
    name: coalesce(concept.name, ''),
    cid: coalesce(toString(concept.conceptId), ''),
    assertion: coalesce(doc.assertion, '')
}) AS codings
RETURN
    toString(e.date) AS edate,
    coalesce(e.text, e.note, e.description, '') AS enc_text,
    codings
ORDER BY e.date
"""


def main() -> None:
    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()

    seen_pids: set[str] = set()

    for pid, site, ref_date, category in _TARGETS:
        try:
            from_date = (
                date.fromisoformat(ref_date) if ref_date else date(2000, 1, 1)
            ).isoformat()
        except ValueError:
            from_date = "2000-01-01"

        # Only pull encounters once per patient even if they appear twice
        enc_key = pid
        if enc_key not in seen_pids:
            encs = client.run(_Q_ENCS, pid=pid, from_date=from_date) or []
            seen_pids.add(enc_key)

            print("=" * 80)
            print(f"[{category}] PATIENT {pid}  site={site}  ref={ref_date}")
            print("=" * 80)

            if not encs:
                print("  (no encounters found after referral date)")
            else:
                for enc in encs:
                    coded = [
                        (
                            f"{c['name']} [{c['assertion']}]"
                            if c["assertion"]
                            else c["name"]
                        )
                        for c in enc["codings"]
                        if c["name"]
                    ]
                    print(f"\n  [{enc['edate']}]")
                    if coded:
                        print("    CODED: " + " | ".join(coded))
                    text = (enc["enc_text"] or "").strip()
                    for line in text.splitlines():
                        line = line.strip()
                        if line:
                            print("    " + line[:200])
            print()
        else:
            print(
                f"  (same patient {pid} - encounters already printed above for {site})"
            )
            print()

    client.close()


if __name__ == "__main__":
    main()
