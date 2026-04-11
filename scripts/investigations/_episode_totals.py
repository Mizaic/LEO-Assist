"""Full episode stats across all statuses and cancer types."""

from __future__ import annotations
import sys
from pathlib import Path
from collections import Counter, defaultdict

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
RETURN ep.status AS status,
       ep.cancer_type AS cancer_type,
       ep.inferred_outcome AS inferred_outcome,
       ep.inferred_confidence AS inferred_confidence,
       ep.specialist_seen AS specialist_seen
"""


def main() -> None:
    c = PatientGraphClient()
    try:
        rows = c.run(Q)
    finally:
        c.close()

    total = len(rows)
    status_counts: Counter = Counter()
    by_cancer: dict[str, Counter] = defaultdict(Counter)
    inferred_cancer = 0
    inferred_benign = 0
    hitl_required = 0

    for r in rows:
        st = r.get("status") or "unknown"
        ct = r.get("cancer_type") or "unknown"
        status_counts[st] += 1
        by_cancer[ct][st] += 1
        if st == "stale_post_specialist":
            io = r.get("inferred_outcome")
            if io == "cancer":
                inferred_cancer += 1
            elif io == "benign":
                inferred_benign += 1
            else:
                hitl_required += 1

    print(f"{'=' * 60}")
    print(f"TOTAL EPISODES: {total}")
    print(f"{'=' * 60}")
    print()

    GROUPS = {
        "Confirmed outcomes": ["completed", "closed_benign"],
        "Active / open": ["in_progress"],
        "Auto-closed HITL": [
            "stale_post_specialist",
            "stale_no_diagnosis",
            "closed_phantom",
            "closed_related",
        ],
    }

    for group, statuses in GROUPS.items():
        group_total = sum(status_counts.get(s, 0) for s in statuses)
        print(f"  {group} ({group_total})")
        for s in statuses:
            n = status_counts.get(s, 0)
            if n == 0:
                continue
            extra = ""
            if s == "stale_post_specialist":
                extra = (
                    f"  [inferred: cancer={inferred_cancer} "
                    f"benign={inferred_benign} HITL={hitl_required}]"
                )
            print(f"    {s:<35} {n:4d}{extra}")
    print()

    print(f"  {'BY CANCER TYPE':}")
    print(
        f"  {'Type':<22} {'Total':>6} {'completed':>10} {'in_progress':>12} {'stale_post_spec':>16} {'stale_no_diag':>14} {'other':>6}"
    )
    print(f"  {'-' * 90}")
    for ct in sorted(by_cancer):
        d = by_cancer[ct]
        ct_total = sum(d.values())
        other = (
            ct_total
            - d.get("completed", 0)
            - d.get("in_progress", 0)
            - d.get("stale_post_specialist", 0)
            - d.get("stale_no_diagnosis", 0)
        )
        print(
            f"  {ct:<22} {ct_total:>6} "
            f"{d.get('completed', 0):>10} "
            f"{d.get('in_progress', 0):>12} "
            f"{d.get('stale_post_specialist', 0):>16} "
            f"{d.get('stale_no_diagnosis', 0):>14} "
            f"{max(0,other):>6}"
        )
    print()

    # Effective outcome summary (confirmed + inferred)
    confirmed_complete = status_counts.get("completed", 0)
    confirmed_benign = status_counts.get("closed_benign", 0)
    eff_cancer = confirmed_complete + inferred_cancer
    eff_benign = confirmed_benign + inferred_benign
    eff_unresolved = status_counts.get("in_progress", 0) + hitl_required
    eff_stale_no_diag = status_counts.get("stale_no_diagnosis", 0)
    eff_other = status_counts.get("closed_related", 0) + status_counts.get(
        "closed_phantom", 0
    )

    print(f"  EFFECTIVE OUTCOME SUMMARY (confirmed + inferred):")
    print(f"    Cancer / confirmed or inferred    : {eff_cancer}")
    print(f"      of which confirmed (completed)  : {confirmed_complete}")
    print(f"      of which inferred               : {inferred_cancer}")
    print(f"    Benign / no cancer                : {eff_benign}")
    print(f"      of which confirmed (closed_benign): {confirmed_benign}")
    print(f"      of which inferred               : {inferred_benign}")
    print(f"    Unresolved (active + HITL)        : {eff_unresolved}")
    print(f"    Stale no diagnosis (>12m)         : {eff_stale_no_diag}")
    print(f"    Auto-closed other                 : {eff_other}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
