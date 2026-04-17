"""Dry-run: classify each existing episode against the mined dictionary.

Walks every EpisodeOfCare, concatenates the text of all encounters linked
via IS_PART_OF, runs match_cancer_site, and reports the top-N predicted
sites alongside the current cancer_type.
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=True)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=True)

from libs.neo4j_client.client import PatientGraphClient  # noqa: E402
from services.analysis_worker.app.analyzers.cancer_site_terms import (  # noqa: E402
    _CANCER_SITE_REGEXES,
    match_cancer_site,
)


def main() -> None:
    c = PatientGraphClient()
    try:
        rows = c.run(
            """
            MATCH (ep:EpisodeOfCare)
            OPTIONAL MATCH (e:Encounter)-[:IS_PART_OF]->(ep)
            WITH ep, collect(coalesce(e.text, ''))[0..30] AS texts
            RETURN
              ep.episode_id   AS ep_id,
              ep.patient_id   AS pid,
              ep.cancer_type  AS current_site,
              ep.status       AS status,
              ep.referral_date AS d_ref,
              reduce(s = '', t IN texts | s + '\n' + t) AS combined
            """
        )
        results: list[dict] = []
        site_counter: Counter[str] = Counter()
        per_site_examples: dict[str, list[str]] = defaultdict(list)

        for r in rows:
            text = r["combined"] or ""
            best = match_cancer_site(text)
            site = best[0] if best else "non_site_specific"
            site_counter[site] += 1
            results.append(
                {
                    "ep_id": r["ep_id"],
                    "pid": r["pid"],
                    "current": r["current_site"],
                    "predicted": site,
                    "score": best[1] if best else 0,
                }
            )
            if best and len(per_site_examples[site]) < 2:
                per_site_examples[site].append(r["pid"])
    finally:
        c.close()

    print(f"Episodes scanned: {len(results)}")
    print()
    print("Predicted cancer-site distribution (vs current 230 / 230 = non_site_specific):")
    for site, n in site_counter.most_common():
        sample = ", ".join(per_site_examples.get(site, [])[:2])
        print(f"  {site:<28} {n:>4d}   sample patients: {sample}")
    print()
    coverage = sum(n for s, n in site_counter.items() if s != "non_site_specific")
    print(
        f"Coverage: {coverage}/{len(results)} episodes get a site classification "
        f"({coverage * 100 // max(len(results), 1)}%)"
    )

    print()
    print("Top per-site form match counts (across the patient corpus):")
    for site, _n in site_counter.most_common():
        if site == "non_site_specific":
            continue
        rx = _CANCER_SITE_REGEXES.get(site)
        if rx is None:
            continue
        from_match = Counter()
        for r in results:
            if r["predicted"] == site:
                pass
        # Just show first few patterns and their hit counts
        print(f"  {site}: {len([r for r in results if r['predicted']==site])} episodes")


if __name__ == "__main__":
    main()
