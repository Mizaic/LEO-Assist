"""Quick extractor: prior-consultations data from Neo4j for the canvas."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)


def main() -> int:
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
    )
    try:
        with driver.session() as s:
            rows = s.run(
                """
                MATCH (ep:EpisodeOfCare)
                WHERE ep.prior_consultations_n IS NOT NULL
                  AND NOT ep.status IN ['merged','closed_phantom','closed_related']
                  AND coalesce(ep.patient_id, '') <> ''
                RETURN ep.episode_id AS eid,
                       ep.patient_id AS patient_id,
                       ep.cancer_type AS cancer_type,
                       ep.cohort AS cohort,
                       toString(ep.first_presentation_date) AS fp_date,
                       toString(ep.referral_date) AS referral_date,
                       ep.prior_consultations_n AS n,
                       ep.prior_consultations_f2f_n AS f2f_n,
                       ep.prior_consultations_phone_n AS phone_n,
                       ep.prior_consultations_nurse_n AS nurse_n,
                       ep.prior_consultations_specialist_clinic_n AS clinic_n,
                       ep.prior_consultations_phlebotomy_n AS phleb_n,
                       ep.prior_consultations_result_review_n AS result_review_n,
                       ep.prior_consultations_unrelated_filtered_n AS unrelated_n,
                       ep.multiple_consultations_factors_auto AS factors,
                       ep.prior_consultations_llm_cost_usd AS cost,
                       ep.prior_consultations_llm_input_tokens AS in_tok,
                       ep.prior_consultations_llm_output_tokens AS out_tok
                ORDER BY ep.patient_id, ep.first_presentation_date
                """
            ).data()
        print(f"# rows: {len(rows)}")
        total_cost = sum(float(r.get("cost") or 0) for r in rows)
        total_in = sum(int(r.get("in_tok") or 0) for r in rows)
        total_out = sum(int(r.get("out_tok") or 0) for r in rows)
        print(f"# total cost: ${total_cost:.4f}")
        print(f"# tokens:    {total_in} in / {total_out} out")
        total_consultations = sum(int(r.get("n") or 0) for r in rows)
        print(f"# total cancer-related consultations: {total_consultations}")
        multi = sum(1 for r in rows if (r.get("n") or 0) >= 2)
        print(
            f"# multi-consult episodes: {multi}/{len(rows)} = "
            f"{multi*100/max(len(rows),1):.1f}%"
        )
        factor_counts: dict[str, int] = {}
        for r in rows:
            for f in (r.get("factors") or []):
                if f and f != "no_multiple_consultations":
                    factor_counts[f] = factor_counts.get(f, 0) + 1
        print("# top factors (by frequency):")
        for f, n in sorted(factor_counts.items(), key=lambda x: -x[1]):
            print(f"#   {f}: {n}")
        # Buckets
        bucket = {"0": 0, "1": 0, "2-3": 0, "4-6": 0, "7+": 0}
        for r in rows:
            n = int(r.get("n") or 0)
            if n == 0:
                bucket["0"] += 1
            elif n == 1:
                bucket["1"] += 1
            elif n <= 3:
                bucket["2-3"] += 1
            elif n <= 6:
                bucket["4-6"] += 1
            else:
                bucket["7+"] += 1
        print("# buckets:", bucket)
        # Dump full rows as JSON
        out_path = ROOT / "artifacts" / "prior_consultations_canvas.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(rows, indent=2, default=str))
        print(f"# wrote: {out_path}")
        return 0
    finally:
        driver.close()


if __name__ == "__main__":
    raise SystemExit(main())
