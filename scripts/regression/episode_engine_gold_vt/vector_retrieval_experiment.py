"""Vector-retrieval experiment: can Bio_ClinicalBERT semantic search
surface the right encounters for context-tier milestones?

For each gold patient x context milestone type, this script:
  1. Fetches every encounter + stored vector for that patient from Neo4j
  2. Embeds a seed text for each context type using Bio_ClinicalBERT
     (same model that wrote Encounter.vector via the pipeline worker)
  3. Computes cosine similarity in-process between the seed embedding
     and every patient encounter -- fully patient-scoped, no global
     index fan-out that would dilute results with other patients
  4. Checks whether the gold encounter appears in top-1 / top-3 / top-5

WHY NOT db.index.vector.queryNodes?
The global index returns the top-K across ALL patients. For a database
with tens of thousands of encounters, the probability that any of this
patient's ~400 encounters lands in the global top-5 is near zero. The
patient-scoped in-Python approach is both correct and fast (cosine over
400 vectors takes <1 ms).

USAGE
=====
    python scripts/regression/episode_engine_gold_vt/vector_retrieval_experiment.py

No LLM calls. Requires Neo4j connectivity and sentence-transformers.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=True)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("vec_exp")

GOLD_PATH = Path(__file__).with_name("gold_episodes.json")

# ---------------------------------------------------------------------------
# Seed texts -- written in the style of real GP record text so Bio_ClinicalBERT
# similarity is meaningful. Each is ~50-120 chars, clinical domain language.
# ---------------------------------------------------------------------------
SEED_TEXTS: dict[str, str] = {
    "related_gp_visit": (
        "Surgery face to face GP consultation history examination f2f review "
        "Clinical Practitioner"
    ),
    "primary_care_investigations": (
        "blood test FBC urea creatinine PSA urine sample ordered investigations "
        "requested bloods results CRP"
    ),
    "referral_admin": (
        "Choice and booking enhanced services administration XaMJa patient "
        "awaiting OPD appointment 2WW admin"
    ),
    "referral_sent": (
        "Fast track referral suspected cancer XaMeC Medical Secretary "
        "Choice and booking 2WW Hospital referral form sent"
    ),
    "related_specialist_visit": (
        "outpatient clinic appointment seen consultant hospital follow-up "
        "specialist attendance review"
    ),
    "specialist_diagnostics": (
        "biopsy CT scan MRI mammogram ultrasound colonoscopy endoscopy "
        "fine needle aspiration histology New Episode SNOMED"
    ),
    "related_correspondence": (
        "Medical Secretary clinic letter received hospital to surgery "
        "correspondence discharge summary outcome"
    ),
}

# Report recall at these ranks
TOP_K_REPORT = [1, 3, 5, 10, 20]
# Maximum retrieval depth -- we rank all patient encounters in-process
TOP_K_RETRIEVE = 20

# Cypher: fetch all stored encounter vectors for one patient in one round trip.
# Optionally filtered to a date window (episode first milestone -> last milestone + buffer).
_LOAD_PATIENT_VECTORS_Q = """
MATCH (p:Patient {id: $patient_id})-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE e.vector IS NOT NULL
  AND ($start_date IS NULL OR e.date >= $start_date)
  AND ($end_date   IS NULL OR e.date <= $end_date)
RETURN e.id      AS encounter_id,
       e.date    AS date,
       e.vector  AS vector,
       left(e.text, 200) AS preview
"""


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

def _load_embedder():
    from sentence_transformers import SentenceTransformer

    model_name = os.getenv("VECTOR_MODEL", "emilyalsentzer/Bio_ClinicalBERT")
    log.info("Loading embedder: %s", model_name)
    return SentenceTransformer(model_name)


def _embed(model, text: str) -> "np.ndarray":
    import numpy as np  # noqa: F401 -- used by caller

    return model.encode([text], normalize_embeddings=True)[0]


# ---------------------------------------------------------------------------
# Patient-scoped cosine similarity (avoids global index fan-out)
# ---------------------------------------------------------------------------

def _patient_enc_vectors(
    client,
    patient_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """Load encounter id + vector + preview for one patient, optionally date-windowed."""
    return (
        client.run(
            _LOAD_PATIENT_VECTORS_Q,
            patient_id=patient_id,
            start_date=start_date,
            end_date=end_date,
        )
        or []
    )


def _rank_by_cosine(
    query_vec: "np.ndarray",
    enc_rows: list[dict],
    top_k: int,
) -> list[dict]:
    """Rank enc_rows by cosine similarity to query_vec, return top_k."""
    import numpy as np

    if not enc_rows:
        return []

    matrix = np.array([r["vector"] for r in enc_rows], dtype=np.float32)
    # vectors are already L2-normalised (normalize_embeddings=True at write time)
    scores = matrix @ query_vec.astype(np.float32)
    top_idx = np.argsort(scores)[::-1][:top_k]
    return [
        {
            "encounter_id": enc_rows[i]["encounter_id"],
            "score": float(scores[i]),
            "preview": enc_rows[i]["preview"],
        }
        for i in top_idx
    ]


def _episode_date_window(episode: dict) -> tuple[str | None, str | None]:
    """Return (start_date, end_date) from an episode's milestone list."""
    dates = sorted(
        m["date"] for m in episode["milestones"] if m.get("date")
    )
    if not dates:
        return None, None
    # Add a 30-day buffer beyond the last milestone
    from datetime import date, timedelta

    last = date.fromisoformat(dates[-1])
    end = (last + timedelta(days=30)).isoformat()
    return dates[0], end


# ---------------------------------------------------------------------------
# Evaluate
# ---------------------------------------------------------------------------

def _evaluate_patient(
    model,
    client,
    patient_id: str,
    patient_gold: dict,
) -> dict[str, Any]:
    """For each context milestone in this patient's gold set, check whether
    patient-scoped cosine search surfaces the right encounter.

    Runs twice per patient:
    - UNWINDOWED: all encounters (baseline)
    - WINDOWED: encounters within each episode's date range + 30 days
    """
    results_by_episode: list[dict] = []

    for episode in patient_gold["episodes"]:
        start_date, end_date = _episode_date_window(episode)

        # Load encounter vectors both with and without windowing
        all_rows = _patient_enc_vectors(client, patient_id)
        win_rows = _patient_enc_vectors(
            client, patient_id, start_date=start_date, end_date=end_date
        )

        log.info(
            "  episode %s: all=%d windowed(%s->%s)=%d",
            episode["episode_id"],
            len(all_rows),
            start_date,
            end_date,
            len(win_rows),
        )

        ep_results: dict[str, dict] = {}
        for m in episode["milestones"]:
            mt = m["milestone_type"]
            if mt not in SEED_TEXTS:
                continue
            gold_enc_id = m["encounter_id"]

            seed = SEED_TEXTS[mt]
            qvec = _embed(model, seed)

            for label, rows in [("unwindowed", all_rows), ("windowed", win_rows)]:
                hits = _rank_by_cosine(qvec, rows, top_k=TOP_K_RETRIEVE)
                hit_ids = [h["encounter_id"] for h in hits]

                found_at = None
                for rank, eid in enumerate(hit_ids, start=1):
                    if eid == gold_enc_id:
                        found_at = rank
                        break

                key = f"{mt}__{label}"
                ep_results[key] = {
                    "milestone_type": mt,
                    "mode": label,
                    "pool_size": len(rows),
                    "gold_encounter_id": gold_enc_id,
                    "found_at_rank": found_at,
                    **{f"hit_at_top{k}": (found_at is not None and found_at <= k)
                       for k in TOP_K_REPORT},
                    "top5": [
                        {
                            "rank": i + 1,
                            "encounter_id": h["encounter_id"],
                            "score": round(h["score"], 4),
                            "is_gold": h["encounter_id"] == gold_enc_id,
                            "preview": h["preview"][:100],
                        }
                        for i, h in enumerate(hits[:5])
                    ],
                }

        results_by_episode.append(
            {
                "episode_id": episode["episode_id"],
                "cancer_type": episode.get("cancer_type"),
                "date_window": f"{start_date} -> {end_date}",
                "milestones": ep_results,
            }
        )

    return {
        "patient_id": patient_id,
        "label": patient_gold.get("label"),
        "episodes": results_by_episode,
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _print_report(all_results: list[dict]) -> None:
    print("\n" + "=" * 70)
    print("VECTOR RETRIEVAL EXPERIMENT -- Bio_ClinicalBERT context milestone")
    print("=" * 70)

    # Aggregate by mode
    counts: dict[str, dict] = {
        "unwindowed": {"total": 0, **{f"hit{k}": 0 for k in TOP_K_REPORT}},
        "windowed": {"total": 0, **{f"hit{k}": 0 for k in TOP_K_REPORT}},
    }

    for pr in all_results:
        label = pr.get("label", pr["patient_id"])
        print(f"\n=== {label} ({pr['patient_id']}) ===")

        for ep in pr.get("episodes", []):
            print(f"  Episode: {ep['episode_id']} [{ep['cancer_type']}]")
            print(f"  Window:  {ep['date_window']}  pool_windowed=?")

            # Group by milestone_type to show unwindowed vs windowed side by side
            seen_mt: dict[str, dict] = {}
            for key, res in ep["milestones"].items():
                mt = res["milestone_type"]
                mode = res["mode"]
                seen_mt.setdefault(mt, {})[mode] = res

            for mt, modes in seen_mt.items():
                uw = modes.get("unwindowed")
                wi = modes.get("windowed")
                uw_rank = uw["found_at_rank"] if uw else "-"
                wi_rank = wi["found_at_rank"] if wi else "-"
                uw_pool = uw["pool_size"] if uw else "-"
                wi_pool = wi["pool_size"] if wi else "-"
                print(
                    f"    {mt:<30}  "
                    f"unwindowed(pool={uw_pool}) rank={uw_rank}  |  "
                    f"windowed(pool={wi_pool}) rank={wi_rank}"
                )

                for mode, res in [("unwindowed", uw), ("windowed", wi)]:
                    if res is None:
                        continue
                    counts[mode]["total"] += 1
                    for k in TOP_K_REPORT:
                        if res.get(f"hit_at_top{k}"):
                            counts[mode][f"hit{k}"] += 1

    print("\n" + "=" * 70)
    print("SUMMARY (per-mode recall)")
    print("=" * 70)
    for mode in ("unwindowed", "windowed"):
        c = counts[mode]
        n = c["total"]
        if n == 0:
            continue
        print(f"\n  Mode: {mode}  (n={n})")
        for k in TOP_K_REPORT:
            h = c[f"hit{k}"]
            print(f"    top-{k:2d}: {h}/{n}  ({100*h/n:.0f}%)")

    # Verdict based on windowed top-10
    wc = counts["windowed"]
    n = wc["total"]
    if n > 0:
        h10 = wc["hit10"]
        print()
        if h10 / n >= 0.70:
            print(f"  VERDICT: windowed top-10 recall {100*h10/n:.0f}% >= 70% "
                  "-- vector hints are useful as LLM context pre-filter")
        elif h10 / n >= 0.50:
            print(f"  VERDICT: windowed top-10 recall {100*h10/n:.0f}% -- "
                  "marginal, seed texts need refinement")
        else:
            print(f"  VERDICT: windowed top-10 recall {100*h10/n:.0f}% -- "
                  "too low; consider archetype-vector approach")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    import numpy as np  # noqa: F401 -- used inside helpers

    from libs.neo4j_client.client import PatientGraphClient

    gold_data = json.loads(GOLD_PATH.read_text())

    model = _load_embedder()
    client = PatientGraphClient()

    all_results: list[dict] = []
    try:
        for patient_id, patient_gold in gold_data["patients"].items():
            log.info("Evaluating patient %s (%s)", patient_id, patient_gold.get("label"))
            result = _evaluate_patient(model, client, patient_id, patient_gold)
            all_results.append(result)
    finally:
        client.close()

    _print_report(all_results)

    # Write JSON results for further analysis
    out = Path(__file__).with_name("vector_experiment_results.json")
    out.write_text(json.dumps(all_results, indent=2, default=str))
    log.info("Results written to %s", out)


if __name__ == "__main__":
    main()
