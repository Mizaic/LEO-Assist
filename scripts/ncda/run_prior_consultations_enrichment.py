#!/usr/bin/env python3
"""Standalone runner for the NCDA prior-consultations enrichment pass.

Re-derives the per-episode "consultations in the year before referral"
metrics + NCDA "multiple consultations" factors using Claude Haiku 4.5
on Bedrock and writes them back to ``EpisodeOfCare``.  Useful when
iterating on the prompt or pre-filter without re-running the full
episode-detection pipeline.

Usage:
    # Dry run -- prints per-episode counts + cost without writing.
    python scripts/ncda/run_prior_consultations_enrichment.py

    # Apply -- writes prior_consultations_* properties + AuditEvent.
    python scripts/ncda/run_prior_consultations_enrichment.py --apply

    # Single patient (debugging):
    python scripts/ncda/run_prior_consultations_enrichment.py --apply --patient 6040304227

    # Cap cost during prompt iteration:
    python scripts/ncda/run_prior_consultations_enrichment.py --limit 5
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.llm_client.usage_recorder import LLMUsageRecorder  # noqa: E402
from libs.llm_usage import LLMCostConfig  # noqa: E402
from libs.oncology.prior_consultations import (  # noqa: E402
    NCDA_FACTOR_LABELS,
    classify_episode_consultations,
)

_HAIKU_COST = LLMCostConfig.for_tier("small")


_FETCH_EPISODES_Q = """
MATCH (ep:EpisodeOfCare)
WHERE NOT ep.status IN ['merged','closed_phantom','closed_related']
  AND ($patient IS NULL OR ep.patient_id = $patient)
OPTIONAL MATCH (mE:Encounter)-[mR:IS_PART_OF]->(ep)
  WHERE mR.milestone_type IN
    ['referral','diagnosis','diagnosis_confirmed','seen','treatment']
WITH ep,
     min(toString(mE.date)) AS first_d,
     max(toString(mE.date)) AS last_d
WHERE first_d IS NOT NULL
WITH ep, first_d, last_d,
     CASE
       WHEN ep.referral_date IS NOT NULL
            AND trim(toString(ep.referral_date)) <> ''
       THEN date(toString(ep.referral_date))
       ELSE date(last_d)
     END AS window_end
WITH ep, window_end,
     window_end - duration({days: 365}) AS window_start
// Anchor context: text of the first-presentation and referral encounters
// so the LLM can judge relatedness against the SPECIFIC symptoms, not
// just the cancer type.
OPTIONAL MATCH (fpE:Encounter)-[fpR:IS_PART_OF]->(ep)
  WHERE fpR.milestone_type = 'first_presentation'
WITH ep, window_start, window_end,
     collect(DISTINCT coalesce(fpE.text, ''))[0] AS fp_encounter_text
OPTIONAL MATCH (refE:Encounter)-[refR:IS_PART_OF]->(ep)
  WHERE refR.milestone_type = 'referral'
WITH ep, window_start, window_end, fp_encounter_text,
     [t IN collect(DISTINCT coalesce(refE.text, '')) WHERE t <> '']
       AS referral_encounter_texts
MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep)
MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE date(toString(e.date)) >= window_start
  AND date(toString(e.date)) <= window_end
WITH ep.episode_id              AS eid,
     ep.patient_id              AS patient_id,
     ep.cancer_type             AS cancer_type,
     ep.cohort                  AS cohort,
     ep.first_presentation_date AS fp_date,
     ep.referral_date           AS referral_date,
     fp_encounter_text,
     referral_encounter_texts,
     collect({
         encounter_id: e.id,
         date:         toString(e.date),
         text:         coalesce(e.text, ''),
         flags:        coalesce(e.flags, '')
     }) AS encounters
RETURN eid, patient_id, cancer_type, cohort, fp_date, referral_date,
       fp_encounter_text, referral_encounter_texts, encounters
ORDER BY patient_id, eid
"""


_WRITE_EPISODE_Q = """
UNWIND $rows AS row
MATCH (ep:EpisodeOfCare {episode_id: row.eid})
SET ep.prior_consultations_n               = row.consultations_n,
    ep.prior_consultations_window_days     = row.window_days,
    ep.prior_consultations_f2f_n           = row.f2f_n,
    ep.prior_consultations_phone_n         = row.phone_n,
    ep.prior_consultations_nurse_n         = row.nurse_n,
    ep.prior_consultations_email_n         = row.email_n,
    ep.prior_consultations_specialist_clinic_n
                                           = row.specialist_clinic_n,
    ep.prior_consultations_home_visit_n    = row.home_visit_n,
    ep.prior_consultations_phlebotomy_n    = row.phlebotomy_n,
    ep.prior_consultations_result_review_n = row.result_review_n,
    ep.prior_consultations_unrelated_filtered_n
                                           = row.unrelated_filtered_n,
    ep.prior_consultations_evidence_json   = row.evidence_json,
    ep.multiple_consultations_factors_auto = row.factor_codes,
    ep.multiple_consultations_factors_evidence_json
                                           = row.factors_json,
    ep.prior_consultations_notes           = row.notes,
    ep.prior_consultations_llm_input_tokens  = row.llm_input_tokens,
    ep.prior_consultations_llm_output_tokens = row.llm_output_tokens,
    ep.prior_consultations_llm_cached_tokens = row.llm_cached_tokens,
    ep.prior_consultations_llm_total_tokens  = row.llm_total_tokens,
    ep.prior_consultations_llm_calls         = row.llm_calls,
    ep.prior_consultations_llm_cost_usd      = row.llm_cost_usd,
    ep.prior_consultations_llm_latency_ms    = row.llm_latency_ms,
    ep.prior_consultations_llm_model_id      = row.llm_model_id,
    ep.prior_consultations_llm_model_provider= row.llm_model_provider,
    ep.prior_consultations_llm_usage_json    = row.llm_usage_json,
    ep.prior_consultations_updated_at        = datetime()
"""

_WRITE_AUDIT_EVENT_Q = """
UNWIND $rows AS row
MATCH (p:Patient)
WHERE coalesce(toString(p.id), toString(p.patient_id)) = row.patient_id
MERGE (ae:AuditEvent {
    type:        'PipelineRun',
    event_type:  'ncda_prior_consultations',
    episode_id:  row.eid
})
SET ae.created_at         = datetime(),
    ae.consultations_n    = row.consultations_n,
    ae.window_days        = row.window_days,
    ae.factor_codes       = row.factor_codes,
    ae.llm_calls          = row.llm_calls,
    ae.llm_input_tokens   = row.llm_input_tokens,
    ae.llm_output_tokens  = row.llm_output_tokens,
    ae.llm_cached_tokens  = row.llm_cached_tokens,
    ae.llm_total_tokens   = row.llm_total_tokens,
    ae.llm_cost_usd       = row.llm_cost_usd,
    ae.llm_latency_ms     = row.llm_latency_ms,
    ae.llm_model_id       = row.llm_model_id,
    ae.llm_model_provider = row.llm_model_provider
MERGE (p)-[:HAS_AUDIT_EVENT]->(ae)
"""


def _connect():
    uri = os.environ["NEO4J_URI"]
    auth = (os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"])
    return GraphDatabase.driver(uri, auth=auth)


def _build_update_row(
    *,
    eid: str,
    patient_id: str,
    result: Any,
    usage: dict[str, Any],
) -> dict[str, Any]:
    verdicts_payload = [
        {
            "encounter_id": v.encounter_id,
            "date":         v.date,
            "related":      v.related,
            "contact_type": v.contact_type,
            "evidence":     v.evidence,
        }
        for v in result.verdicts
    ]
    factors_payload = [
        {
            "factor": f.factor,
            "label":  NCDA_FACTOR_LABELS.get(f.factor, f.factor),
            "evidence_encounter_ids": list(f.evidence_encounter_ids),
            "rationale": f.rationale,
        }
        for f in result.factors
    ]
    return {
        "eid":              eid,
        "patient_id":       patient_id,
        "consultations_n":  result.consultations_n,
        "f2f_n":            result.f2f_n,
        "phone_n":          result.phone_n,
        "nurse_n":          result.nurse_n,
        "email_n":          result.email_n,
        "specialist_clinic_n": result.specialist_clinic_n,
        "home_visit_n":     result.home_visit_n,
        "phlebotomy_n":     result.phlebotomy_n,
        "result_review_n":  result.result_review_n,
        "unrelated_filtered_n": result.unrelated_filtered_n,
        "factor_codes":     [f.factor for f in result.factors],
        "evidence_json":    json.dumps(verdicts_payload),
        "factors_json":     json.dumps(factors_payload),
        "notes":            result.notes,
        "window_days":      365,
        "llm_calls":        usage["llm_calls"],
        "llm_input_tokens": usage["input_tokens"],
        "llm_output_tokens":usage["output_tokens"],
        "llm_cached_tokens":usage["cached_input_tokens"],
        "llm_total_tokens": usage["total_tokens"],
        "llm_cost_usd":     usage["cost_usd"],
        "llm_latency_ms":   usage["total_latency_ms"],
        "llm_model_id":     usage["model_name"],
        "llm_model_provider": usage["model_provider"],
        "llm_usage_json":   json.dumps(usage),
    }


def _flush_writes(driver: Any, batch: list[dict[str, Any]]) -> None:
    """Open a fresh session for each batch flush -- the Neo4j Aura
    routing table goes stale after long LLM phases (>5 min idle), so
    we acquire a brand-new connection just for the write."""
    if not batch:
        return
    with driver.session() as write_session:
        write_session.run(_WRITE_EPISODE_Q, rows=batch)
        write_session.run(_WRITE_AUDIT_EVENT_Q, rows=batch)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patient", default=None, help="Limit to one patient ID.")
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Cap the number of episodes processed (cost guard).",
    )
    parser.add_argument(
        "--apply", action="store_true", default=False,
        help="Write results to Neo4j.  Without this flag the script "
             "is dry-run only and prints per-episode summary lines.",
    )
    parser.add_argument(
        "--batch-size", type=int, default=5,
        help="Flush writes every N episodes to avoid the Neo4j Aura "
             "routing table going stale during long LLM phases.",
    )
    args = parser.parse_args(argv)

    driver = _connect()
    rows: list[dict[str, Any]] = []
    pending_batch: list[dict[str, Any]] = []
    total_cost = 0.0
    total_in = 0
    total_out = 0
    total_calls = 0
    skipped = 0
    written = 0

    try:
        # Episode list snapshot.  After this read, sessions are
        # opened lazily for each LLM-completed batch so the Aura
        # connection never sits idle for more than a few minutes.
        with driver.session() as session:
            episode_rows = list(session.run(_FETCH_EPISODES_Q, patient=args.patient))
        if args.limit is not None:
            episode_rows = episode_rows[: args.limit]
        print(f"Loaded {len(episode_rows)} episodes for enrichment.")

        for i, row in enumerate(episode_rows, start=1):
            eid = row["eid"]
            patient_id = str(row["patient_id"] or "")
            cancer_type = row["cancer_type"] or ""
            cohort = row["cohort"] or ""
            fp_date = str(row["fp_date"] or "")
            referral_date = str(row["referral_date"] or "")
            fp_encounter_text = str(row["fp_encounter_text"] or "") or None
            referral_encounter_texts = [
                str(t) for t in (row["referral_encounter_texts"] or []) if t
            ] or None
            encounters = row["encounters"] or []
            if not encounters:
                skipped += 1
                print(
                    f"  [{i:>2}/{len(episode_rows)}] {patient_id} {cancer_type:<15} "
                    f"({cohort}) -- no encounters in window, skipped"
                )
                continue

            with LLMUsageRecorder() as rec:
                result = classify_episode_consultations(
                    cancer_type=cancer_type,
                    first_presentation_date=fp_date,
                    referral_date=referral_date,
                    encounters=encounters,
                    first_presentation_text=fp_encounter_text,
                    referral_texts=referral_encounter_texts,
                    patient_id=patient_id,
                )
                usage = rec.to_audit_dict(_HAIKU_COST)

            total_cost += float(usage["cost_usd"] or 0)
            total_in += int(usage["input_tokens"] or 0)
            total_out += int(usage["output_tokens"] or 0)
            total_calls += int(usage["llm_calls"] or 0)

            factor_str = ", ".join(f.factor for f in result.factors) or "-"
            print(
                f"  [{i:>2}/{len(episode_rows)}] {patient_id} {cancer_type:<15} "
                f"({cohort}) -> consultations_n={result.consultations_n:>2} "
                f"(f2f={result.f2f_n} phone={result.phone_n} "
                f"nurse={result.nurse_n} clinic={result.specialist_clinic_n} "
                f"phleb={result.phlebotomy_n}) "
                f"factors=[{factor_str}] "
                f"unrel_filtered={result.unrelated_filtered_n} "
                f"cost=${usage['cost_usd']:.4f}"
            )

            update_row = _build_update_row(
                eid=eid,
                patient_id=patient_id,
                result=result,
                usage=usage,
            )
            rows.append(update_row)
            pending_batch.append(update_row)

            if args.apply and len(pending_batch) >= args.batch_size:
                _flush_writes(driver, pending_batch)
                written += len(pending_batch)
                print(
                    f"  ... flushed batch of {len(pending_batch)} "
                    f"({written}/{len(rows)} episodes persisted)"
                )
                pending_batch = []

        if args.apply and pending_batch:
            _flush_writes(driver, pending_batch)
            written += len(pending_batch)
            print(
                f"  ... flushed final batch of {len(pending_batch)} "
                f"({written}/{len(rows)} episodes persisted)"
            )

    finally:
        driver.close()

    print()
    print("Run summary:")
    print(f"  Episodes enriched : {len(rows)}")
    print(f"  Episodes skipped  : {skipped}  (no encounters in window)")
    print(f"  Total LLM calls   : {total_calls}")
    print(f"  Total tokens      : {total_in} in / {total_out} out")
    print(f"  Total cost        : ${total_cost:.4f}")
    if args.apply:
        print(f"  Wrote {written} EpisodeOfCare + AuditEvent rows to Neo4j.")
    else:
        print("  Dry run -- no graph writes.  Use --apply to persist.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
