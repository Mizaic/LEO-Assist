"""Quick check: how many stale_post_specialist episodes got inference scores."""
from __future__ import annotations
import sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()
from libs.neo4j_client.client import PatientGraphClient

Q = """
MATCH (ep:EpisodeOfCare)
WHERE ep.status = 'stale_post_specialist'
RETURN ep.episode_id AS episode_id, ep.cancer_type AS cancer_type,
       ep.inferred_outcome AS inferred_outcome,
       ep.inferred_outcome_date AS inferred_outcome_date,
       ep.inferred_confidence AS inferred_confidence,
       ep.inference_signals AS inference_signals
ORDER BY ep.cancer_type, ep.inferred_outcome
"""

def main() -> None:
    c = PatientGraphClient()
    try:
        rows = c.run(Q)
    finally:
        c.close()

    total = len(rows)
    verdict_counts: Counter = Counter()
    for r in rows:
        outcome = r.get("inferred_outcome")
        verdict_counts[outcome or "HITL_REQUIRED"] += 1

    print(f"stale_post_specialist total: {total}")
    print()
    print("INFERENCE VERDICT BREAKDOWN:")
    for verdict, n in sorted(verdict_counts.items(), key=lambda x: -x[1]):
        pct = 100 * n / total if total else 0
        print(f"  {verdict:<20} {n:3d}  ({pct:.0f}%)")

    inferred = sum(1 for r in rows if r.get("inferred_outcome") is not None)
    print()
    print(f"  Got inference  : {inferred}/{total}  ({100*inferred//total if total else 0}%)")
    print(f"  HITL required  : {total - inferred}/{total}")

    print()
    print("SAMPLE INFERRED EPISODES:")
    print(f"{'Cancer type':<18} {'Outcome':<8} {'Conf':>6} {'Date':<12} {'Signals'}")
    print("-" * 90)
    for r in rows:
        if r.get("inferred_outcome"):
            conf = r.get("inferred_confidence")
            conf_s = f"{conf:.2f}" if conf is not None else "-"
            signals = (r.get("inference_signals") or "")[:50]
            print(
                f"{r.get('cancer_type') or '-':<18} "
                f"{r.get('inferred_outcome') or '-':<8} "
                f"{conf_s:>6} "
                f"{r.get('inferred_outcome_date') or '-':<12} "
                f"{signals}"
            )

if __name__ == "__main__":
    main()
