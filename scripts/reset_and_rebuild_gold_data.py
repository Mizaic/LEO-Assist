"""Reset and rebuild gold training data through the hardened pipeline.

Steps:
  1. Count and delete all CodingReview nodes (clean slate)
  2. Trigger verify-all with mode=re_extract, reset_pending=true
     (re-extracts entities via LLM, then runs dual-model verification)
  3. Poll job status until complete
  4. Run validation queries (sampling 10%+ of successes, all disagreements)

Usage:
    .venv\\Scripts\\python scripts\\reset_and_rebuild_gold_data.py [--api-url http://localhost:8000]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env")

from neo4j import GraphDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Neo4j connection
# ---------------------------------------------------------------------------

def get_neo4j_driver():
    uri = os.getenv("NEO4J_URI", "")
    user = os.getenv("NEO4J_USER", "neo4j")
    pwd = os.getenv("NEO4J_PASSWORD", "")
    if not uri or not pwd:
        logger.error("NEO4J_URI / NEO4J_PASSWORD not set")
        sys.exit(1)
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    driver.verify_connectivity()
    return driver


# ---------------------------------------------------------------------------
# Step 1: Delete all CodingReview nodes
# ---------------------------------------------------------------------------

def reset_coding_reviews(driver) -> dict:
    """Delete all CodingReview nodes and return stats."""
    with driver.session() as session:
        count_row = session.run(
            "MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel) "
            "WHERE t.include = true "
            "RETURN count(cr) AS total, "
            "  sum(CASE WHEN cr.resolved = true THEN 1 ELSE 0 END) AS resolved, "
            "  sum(CASE WHEN cr.resolved = false THEN 1 ELSE 0 END) AS pending"
        ).single()
        stats = {
            "total": count_row["total"],
            "resolved": count_row["resolved"],
            "pending": count_row["pending"],
        }

    logger.info(
        "CodingReview stats before delete: total=%d, resolved=%d, pending=%d",
        stats["total"], stats["resolved"], stats["pending"],
    )

    with driver.session() as session:
        session.run(
            "MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel) "
            "WHERE t.include = true "
            "DETACH DELETE cr"
        )

    with driver.session() as session:
        verify = session.run(
            "MATCH (cr:CodingReview) RETURN count(cr) AS remaining"
        ).single()
        remaining = verify["remaining"]

    logger.info("CodingReview nodes after delete: %d remaining", remaining)
    return stats


# ---------------------------------------------------------------------------
# Step 2: Trigger verify-all with re_extract mode
# ---------------------------------------------------------------------------

def trigger_rebuild(api_url: str) -> bool:
    """POST /training/labels/verify-all with re_extract + reset_pending."""
    import httpx

    url = f"{api_url}/training/labels/verify-all"
    payload = {"mode": "re_extract", "reset_pending": True}

    logger.info("Triggering rebuild: POST %s", url)
    logger.info("Payload: %s", json.dumps(payload))

    try:
        resp = httpx.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        logger.info("Response: %s", json.dumps(data, indent=2))
        return True
    except httpx.ConnectError:
        logger.error("Cannot connect to API at %s -- is it running?", api_url)
        return False
    except Exception as exc:
        logger.error("Failed to trigger rebuild: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Step 3: Monitor job progress
# ---------------------------------------------------------------------------

def monitor_job(api_url: str, poll_interval: int = 15) -> dict:
    """Poll /training/labels/verifier-status until job completes."""
    import httpx

    url = f"{api_url}/training/labels/verifier-status"
    logger.info("Monitoring job at %s (poll every %ds)", url, poll_interval)

    last_done = -1
    stall_count = 0

    while True:
        try:
            resp = httpx.get(url, timeout=10)
            resp.raise_for_status()
            state = resp.json()
        except Exception as exc:
            logger.warning("Poll failed: %s", exc)
            time.sleep(poll_interval)
            continue

        status = state.get("status", "unknown")
        total = state.get("total", 0)
        done = state.get("done", 0)
        agreements = state.get("agreements", 0)
        disagreements = state.get("disagreements", 0)
        auto_resolved = state.get("auto_resolved", 0)
        errors = state.get("errors", 0)
        pending_review = state.get("pending_review", 0)

        pct = (done / total * 100) if total > 0 else 0

        logger.info(
            "Status=%s | %d/%d (%.1f%%) | agree=%d disagree=%d auto=%d errors=%d pending=%d",
            status, done, total, pct,
            agreements, disagreements, auto_resolved, errors, pending_review,
        )

        if status in ("idle", "completed", "stopped", "error"):
            logger.info("Job finished with status: %s", status)
            return state

        if done == last_done:
            stall_count += 1
            if stall_count > 20:
                logger.warning("Job appears stalled (%d polls with no progress)", stall_count)
        else:
            stall_count = 0
        last_done = done

        time.sleep(poll_interval)


# ---------------------------------------------------------------------------
# Step 4: Validation queries
# ---------------------------------------------------------------------------

def run_validation(driver, sample_pct: float = 0.10) -> dict:
    """Run validation queries against the rebuilt data."""
    results = {}

    # 4a: Overall stats
    with driver.session() as session:
        row = session.run(
            "MATCH (t:TrainingLabel) WHERE t.include = true "
            "RETURN count(t) AS total_labels, "
            "  sum(CASE WHEN t.entities_json IS NOT NULL AND t.entities_json <> '[]' THEN 1 ELSE 0 END) AS has_entities, "
            "  sum(CASE WHEN t.verified_at IS NOT NULL THEN 1 ELSE 0 END) AS verified, "
            "  avg(size(apoc.convert.fromJsonList(coalesce(t.entities_json, '[]')))) AS avg_entities"
        ).single()
        if row:
            results["overall"] = {
                "total_labels": row["total_labels"],
                "has_entities": row["has_entities"],
                "verified": row["verified"],
                "avg_entities": round(float(row["avg_entities"] or 0), 1),
            }
            logger.info("Overall: %s", json.dumps(results["overall"], indent=2))

    # 4b: CodingReview stats (new queue)
    with driver.session() as session:
        row = session.run(
            "MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel) "
            "WHERE t.include = true "
            "RETURN count(cr) AS total, "
            "  sum(CASE WHEN cr.coded = true THEN 1 ELSE 0 END) AS coded, "
            "  sum(CASE WHEN cr.coded = false THEN 1 ELSE 0 END) AS uncoded, "
            "  sum(CASE WHEN cr.resolved = true THEN 1 ELSE 0 END) AS resolved, "
            "  sum(CASE WHEN cr.resolved = false THEN 1 ELSE 0 END) AS pending"
        ).single()
        if row:
            results["coding_review"] = dict(row)
            logger.info("CodingReview queue: %s", json.dumps(results["coding_review"], indent=2))

    # 4c: LabelVerificationReview disagreement stats
    with driver.session() as session:
        rows = list(session.run(
            "MATCH (r:LabelVerificationReview)-[:REVIEWS_LABEL]->(t:TrainingLabel) "
            "WHERE t.include = true "
            "RETURN r.agreement AS agreement, count(r) AS cnt "
            "ORDER BY cnt DESC"
        ))
        results["verification_reviews"] = {str(r["agreement"]): r["cnt"] for r in rows}
        logger.info("Verification reviews: %s", json.dumps(results["verification_reviews"], indent=2))

    # 4d: Sample random successful labels (10%+)
    with driver.session() as session:
        all_verified = list(session.run(
            "MATCH (t:TrainingLabel) "
            "WHERE t.include = true AND t.verified_at IS NOT NULL "
            "  AND t.entities_json IS NOT NULL AND t.entities_json <> '[]' "
            "RETURN t.label_id AS label_id, t.text AS text, t.entities_json AS entities_json "
            "ORDER BY rand()"
        ))

    n_sample = max(int(len(all_verified) * sample_pct), min(100, len(all_verified)))
    sampled = all_verified[:n_sample]
    logger.info("Sampling %d / %d verified labels (%.1f%%)", n_sample, len(all_verified), n_sample / max(len(all_verified), 1) * 100)

    entity_type_dist = {}
    assertion_dist = {}
    empty_extraction_count = 0
    total_entities = 0

    for row in sampled:
        entities = json.loads(row["entities_json"] or "[]")
        if not entities:
            empty_extraction_count += 1
            continue
        for ent in entities:
            label = ent.get("label", "unknown")
            assertion = ent.get("assertion", "present")
            entity_type_dist[label] = entity_type_dist.get(label, 0) + 1
            assertion_dist[assertion] = assertion_dist.get(assertion, 0) + 1
            total_entities += 1

    results["sample"] = {
        "n_sampled": n_sample,
        "n_verified_total": len(all_verified),
        "empty_extractions": empty_extraction_count,
        "total_entities_in_sample": total_entities,
        "avg_entities_per_label": round(total_entities / max(n_sample - empty_extraction_count, 1), 1),
        "entity_type_distribution": dict(sorted(entity_type_dist.items(), key=lambda x: -x[1])),
        "assertion_distribution": dict(sorted(assertion_dist.items(), key=lambda x: -x[1])),
    }
    logger.info("Sample analysis:\n%s", json.dumps(results["sample"], indent=2))

    # 4e: All disagreements
    with driver.session() as session:
        disagreements = list(session.run(
            "MATCH (r:LabelVerificationReview)-[:REVIEWS_LABEL]->(t:TrainingLabel) "
            "WHERE t.include = true AND r.agreement = false "
            "RETURN r.review_id AS review_id, r.entity_index AS entity_index, "
            "  r.model_a_label AS model_a_label, r.model_b_label AS model_b_label, "
            "  r.resolved AS resolved, r.resolved_label AS resolved_label, "
            "  r.resolved_by AS resolved_by, "
            "  t.label_id AS label_id, "
            "  substring(t.text, 0, 200) AS text_preview "
            "ORDER BY r.resolved ASC, t.label_id"
        ))

    results["disagreements"] = {
        "total": len(disagreements),
        "resolved": sum(1 for d in disagreements if d.get("resolved")),
        "unresolved": sum(1 for d in disagreements if not d.get("resolved")),
    }
    logger.info("Disagreements: %s", json.dumps(results["disagreements"], indent=2))

    # Log a few sample disagreements for inspection
    for d in disagreements[:20]:
        logger.info(
            "  Disagreement: entity_idx=%s model_a=%s model_b=%s resolved=%s resolved_label=%s text=%s...",
            d.get("entity_index"), d.get("model_a_label"), d.get("model_b_label"),
            d.get("resolved"), d.get("resolved_label"),
            str(d.get("text_preview", ""))[:80],
        )

    # 4f: Known-bad encounter spot checks
    logger.info("--- Spot-check: known problem areas ---")
    with driver.session() as session:
        spot_checks = list(session.run(
            "MATCH (t:TrainingLabel) "
            "WHERE t.include = true "
            "  AND (t.text CONTAINS 'Cervical Screening' OR t.text CONTAINS 'cervical screening' "
            "       OR t.text CONTAINS 'Serum potassium' OR t.text CONTAINS 'serum potassium' "
            "       OR t.text CONTAINS 'Neutrophil count' OR t.text CONTAINS 'Red blood cell') "
            "RETURN t.label_id AS label_id, "
            "  substring(t.text, 0, 120) AS text_preview, "
            "  t.entities_json AS entities_json "
            "LIMIT 20"
        ))

    for sc in spot_checks:
        entities = json.loads(sc["entities_json"] or "[]")
        entity_summary = [
            f"{e.get('text', '?')[:40]} ({e.get('label', '?')}/{e.get('assertion', '?')})"
            for e in entities[:8]
        ]
        logger.info(
            "  [%s] %s | entities=%d: %s",
            str(sc["label_id"])[:8],
            sc["text_preview"][:80],
            len(entities),
            "; ".join(entity_summary),
        )

    results["spot_checks"] = len(spot_checks)

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Reset and rebuild gold training data")
    parser.add_argument("--api-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--skip-reset", action="store_true", help="Skip CodingReview deletion")
    parser.add_argument("--skip-rebuild", action="store_true", help="Skip triggering re-extract")
    parser.add_argument("--skip-monitor", action="store_true", help="Skip monitoring (just validate)")
    parser.add_argument("--validate-only", action="store_true", help="Only run validation queries")
    parser.add_argument("--sample-pct", type=float, default=0.10, help="Sample percentage (default 10%%)")
    parser.add_argument("--poll-interval", type=int, default=15, help="Monitoring poll interval in seconds")
    args = parser.parse_args()

    driver = get_neo4j_driver()
    logger.info("Connected to Neo4j")

    if args.validate_only:
        logger.info("=== VALIDATION ONLY MODE ===")
        results = run_validation(driver, sample_pct=args.sample_pct)
        driver.close()
        output_path = ROOT / "scripts" / "gold_data_validation_results.json"
        output_path.write_text(json.dumps(results, indent=2, default=str))
        logger.info("Results written to %s", output_path)
        return

    # Step 1: Reset
    if not args.skip_reset:
        logger.info("=== STEP 1: Deleting CodingReview nodes ===")
        stats = reset_coding_reviews(driver)
        logger.info("Deleted %d CodingReview nodes", stats["total"])
    else:
        logger.info("=== STEP 1: Skipped (--skip-reset) ===")

    # Step 2: Trigger rebuild
    if not args.skip_rebuild:
        logger.info("=== STEP 2: Triggering re-extract + verify-all ===")
        success = trigger_rebuild(args.api_url)
        if not success:
            logger.error("Failed to trigger rebuild. Is the API running?")
            logger.info("Start API with: scripts\\start_leo-ai-core.ps1 -SkipInstall -Services api")
            driver.close()
            sys.exit(1)
    else:
        logger.info("=== STEP 2: Skipped (--skip-rebuild) ===")

    # Step 3: Monitor
    if not args.skip_monitor and not args.skip_rebuild:
        logger.info("=== STEP 3: Monitoring pipeline run ===")
        final_state = monitor_job(args.api_url, poll_interval=args.poll_interval)
        logger.info("Final job state: %s", json.dumps(final_state, indent=2, default=str))
    else:
        logger.info("=== STEP 3: Skipped ===")

    # Step 4: Validate
    logger.info("=== STEP 4: Running validation queries ===")
    results = run_validation(driver, sample_pct=args.sample_pct)

    driver.close()

    output_path = ROOT / "scripts" / "gold_data_validation_results.json"
    output_path.write_text(json.dumps(results, indent=2, default=str))
    logger.info("Results written to %s", output_path)
    logger.info("=== REBUILD COMPLETE ===")


if __name__ == "__main__":
    main()
