"""Verify the numbers the /care/audit and /care/dashboard pages should now show."""

from __future__ import annotations
import sys
from pathlib import Path
from datetime import date as _date

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()
from libs.neo4j_client.client import PatientGraphClient

_CLOSED = {
    "closed",
    "completed",
    "merged",
    "excluded",
    "closed_benign",
    "closed_related",
    "closed_phantom",
    "stale_no_diagnosis",
    "stale_post_specialist",
}

Q_SUMMARY = """
MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
OPTIONAL MATCH (diag_enc:Encounter)-[dr:IS_PART_OF]->(ep)
  WHERE dr.milestone_type IN ['diagnosis', 'diagnosis_confirmed']
WITH ep, min(toString(diag_enc.date)) AS diag_date
WITH ep, diag_date,
  CASE
    WHEN diag_date IS NOT NULL THEN diag_date
    WHEN ep.inferred_outcome = 'cancer' AND ep.inferred_outcome_date IS NOT NULL
      THEN ep.inferred_outcome_date
    WHEN ep.status = 'completed' AND ep.end_date IS NOT NULL
      THEN toString(ep.end_date)
    ELSE null
  END AS effective_diag_date,
  coalesce(ep.first_presentation_date, toString(ep.referral_date)) AS fp_date
RETURN ep.status AS status,
       ep.referral_date AS referral_date,
       ep.end_date AS end_date,
       effective_diag_date AS diag_date,
       fp_date
"""


def _safe_days(a, b):
    try:
        da = _date.fromisoformat(str(a)) if a else None
        db = _date.fromisoformat(str(b)) if b else None
        return (db - da).days if da and db else None
    except Exception:
        return None


def main() -> None:
    c = PatientGraphClient()
    try:
        rows = c.run(Q_SUMMARY)
    finally:
        c.close()

    total = len(rows)
    active = sum(1 for r in rows if r["status"] not in _CLOSED)
    confirmed = sum(1 for r in rows if r["diag_date"] is not None)

    pci_vals = sorted(
        [
            v
            for r in rows
            if (v := _safe_days(r["fp_date"], r.get("referral_date"))) is not None
            and v >= 0
        ]
    )
    di_vals = sorted(
        [
            v
            for r in rows
            if (v := _safe_days(r["fp_date"], r["diag_date"])) is not None and v >= 0
        ]
    )

    def median(vals):
        if not vals:
            return None
        n = len(vals)
        return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2

    print("=== What /care/audit Summary should now show ===")
    print(f"  Total pathways  : {total}")
    print(f"  Active          : {active}  (in_progress only)")
    print(f"  Confirmed       : {confirmed}  (completed + inferred cancer)")
    print(
        f"  Median PCI      : {median(pci_vals):.0f} days  (n={len(pci_vals)})"
        if pci_vals
        else "  Median PCI      : — (no data)"
    )
    print(
        f"  Median DI       : {median(di_vals):.0f} days  (n={len(di_vals)})"
        if di_vals
        else "  Median DI       : — (no first_presentation_date on any episode)"
    )
    print()
    print("  Status breakdown:")
    from collections import Counter

    sc = Counter(r["status"] for r in rows)
    for s, n in sorted(sc.items(), key=lambda x: -x[1]):
        flag = " <-- active" if s not in _CLOSED else ""
        print(f"    {s:<35} {n:4d}{flag}")
    print()
    print("  Confirmed breakdown:")
    print(f"    Has diag_date (effective) : {confirmed}")
    print(
        f"    of which ep.status=completed : {sum(1 for r in rows if r['status']=='completed')}"
    )
    print(
        f"    of which inferred cancer  : {sum(1 for r in rows if r['status']=='stale_post_specialist' and r['diag_date'])}"
    )


if __name__ == "__main__":
    main()
