"""Dual-LLM domain review of normalised anchor training data.

Reads exports/training/all_training_merged.jsonl (produced by
normalize_training.py), sends batches of ~50 records to both AWS Haiku and
Azure GPT-5-mini, and writes a review JSONL with per-record domain labels,
concept validation, assertion types, and medspaCy TargetRules.

Results are also persisted to Neo4j as AnchorReview nodes so the
/anchor-review UI can surface disagreements for human voting.

Usage
-----
    python scripts/review_anchor_training.py \\
        --input  exports/training/all_training_merged.jsonl \\
        --output exports/training/anchor_review_results.jsonl \\
        [--batch-size 50] \\
        [--dry-run]        # parse + validate without calling LLMs \\
        [--no-neo4j]       # skip Neo4j persistence

Output schema (one record per input line)
------------------------------------------
    encounter_id      str
    milestone_type    str
    patient_id        str
    original_label    int
    text              str
    original_concept_id str | null
    model_a_domain    str
    model_a_concept_correct bool
    model_a_assertion str
    model_a_rationale str
    model_a_target_rule str
    model_b_domain    str
    model_b_concept_correct bool
    model_b_assertion str
    model_b_rationale str
    model_b_target_rule str
    consensus_agreement bool
    final_domain      str          (model_a if agree, else "DISAGREEMENT")
    non_cancer_flag   bool         (true if either model says NON_CANCER)
    reviewed_at       str          ISO datetime
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
logger = logging.getLogger("review_anchor_training")
logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

BATCH_SIZE = 50
VALID_DOMAINS = {
    "CANCER_DIAGNOSIS",
    "CANCER_DIAGNOSIS_EXCLUDED",
    "2WW_REFERRAL",
    "2WW_CLINIC_SEEN",
    "2WW_REFERRAL_REJECTED",
    "CANCER_TREATMENT",
    "CANCER_TREATMENT_HISTORICAL",
    "INVESTIGATION",
    "METASTATIC_DISEASE",
    "NON_CANCER",
    "AMBIGUOUS",
}

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


# ──────────────────────────────────────────────────────────────────────────────
# LLM helpers
# ──────────────────────────────────────────────────────────────────────────────

def _parse_model_output(text: str) -> list[dict[str, Any]]:
    """Extract JSON array from model response, tolerating markdown fences."""
    text = text.strip()
    # Strip markdown code fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    # Fall back to regex extraction
    m = _JSON_ARRAY_RE.search(text)
    if m:
        try:
            result = json.loads(m.group(0))
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
    logger.warning("Could not parse model output as JSON array (len=%d)", len(text))
    return []


def _normalise_domain(domain: str) -> str:
    domain = domain.upper().strip()
    if domain in VALID_DOMAINS:
        return domain
    # Simple fuzzy mappings
    if "NON" in domain or "NOT" in domain:
        return "NON_CANCER"
    if "AMBIG" in domain or "UNCLEAR" in domain:
        return "AMBIGUOUS"
    if "METASTA" in domain or "SECOND" in domain:
        return "METASTATIC_DISEASE"
    if "TREATMENT" in domain and "HIST" in domain:
        return "CANCER_TREATMENT_HISTORICAL"
    if "TREATMENT" in domain:
        return "CANCER_TREATMENT"
    if "CLINIC" in domain or "SEEN" in domain:
        return "2WW_CLINIC_SEEN"
    if "REFERR" in domain and "REJECT" in domain:
        return "2WW_REFERRAL_REJECTED"
    if "REFERR" in domain or "2WW" in domain:
        return "2WW_REFERRAL"
    if "DIAGNO" in domain:
        return "CANCER_DIAGNOSIS"
    if "INVEST" in domain:
        return "INVESTIGATION"
    return "AMBIGUOUS"


def _safe_review(item: dict[str, Any]) -> dict[str, Any]:
    """Return a default/safe review object for a single line."""
    return {
        "line_number": item.get("line_number", 0),
        "original_concept_id": item.get("concept_id"),
        "domain": "AMBIGUOUS",
        "concept_correct": None,
        "suggested_concept_id": None,
        "suggested_concept_name": None,
        "assertion": "present",
        "rationale": "Model did not return a result for this line.",
        "target_rule": "",
    }


def _call_model(
    provider: str,
    system_prompt: str,
    batch_text: str,
    label: str,
    dry_run: bool = False,
) -> str:
    """Call one model and return raw text response."""
    if dry_run:
        return "[]"
    from libs.llm_client.factory import create_llm
    client = create_llm(provider=provider, tier="small")
    try:
        response = client.converse(
            system=system_prompt,
            messages=[{"role": "user", "content": batch_text}],
            max_tokens=4096,
            temperature=0.0,
        )
        logger.debug(
            "%s: input_tokens=%d output_tokens=%d",
            label, response.input_tokens, response.output_tokens,
        )
        return response.text
    except Exception:
        logger.warning("%s call failed", label, exc_info=True)
        return "[]"


def _review_batch(
    batch: list[dict[str, Any]],
    system_prompt: str,
    dry_run: bool = False,
) -> tuple[list[dict], list[dict]]:
    """Run both models on a batch. Returns (model_a_results, model_b_results)."""
    # Build compact input — only the fields the prompt needs
    input_lines = []
    for i, rec in enumerate(batch, 1):
        input_lines.append({
            "line_number": i,
            "concept_id": rec.get("concept_id"),
            "concept_name": rec.get("concept_name"),
            "text": rec.get("text", ""),
            "confidence": rec.get("confidence"),
            "detection_method": rec.get("detection_method"),
            "milestone_type": rec.get("milestone_type"),
            "label": rec.get("label"),
        })

    batch_text = "Review the following JSONL records:\n\n" + "\n".join(
        json.dumps(line) for line in input_lines
    )

    # Run both models concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        fut_a = pool.submit(_call_model, "aws", system_prompt, batch_text, "Haiku", dry_run)
        fut_b = pool.submit(_call_model, "azure", system_prompt, batch_text, "GPT-5-mini", dry_run)
        raw_a = fut_a.result()
        raw_b = fut_b.result()

    parsed_a = _parse_model_output(raw_a)
    parsed_b = _parse_model_output(raw_b)

    # Pad with safe defaults if model returned fewer items than expected
    while len(parsed_a) < len(batch):
        parsed_a.append(_safe_review(input_lines[len(parsed_a)]))
    while len(parsed_b) < len(batch):
        parsed_b.append(_safe_review(input_lines[len(parsed_b)]))

    return parsed_a[: len(batch)], parsed_b[: len(batch)]


# ──────────────────────────────────────────────────────────────────────────────
# Neo4j persistence
# ──────────────────────────────────────────────────────────────────────────────

def _persist_to_neo4j(results: list[dict[str, Any]]) -> None:
    """Write AnchorReview nodes and REVIEWS relationships to Neo4j."""
    from libs.neo4j_client.client import PatientGraphClient
    from libs.cypher.anchor_review_queries import UPSERT_ANCHOR_REVIEW

    client = PatientGraphClient()
    written = 0
    errors = 0
    try:
        with client.session() as session:
            for rec in results:
                eid = rec.get("encounter_id", "")
                mt = rec.get("milestone_type", "")
                if not eid or not mt:
                    continue
                try:
                    session.run(
                        UPSERT_ANCHOR_REVIEW,
                        encounter_id=eid,
                        milestone_type=mt,
                        patient_id=rec.get("patient_id", ""),
                        original_label=int(rec.get("original_label", 0)),
                        text=rec.get("text", "")[:500],
                        original_concept_id=str(rec.get("original_concept_id") or ""),
                        model_a_domain=rec.get("model_a_domain", ""),
                        model_a_concept_correct=bool(rec.get("model_a_concept_correct")),
                        model_a_assertion=rec.get("model_a_assertion", ""),
                        model_a_rationale=rec.get("model_a_rationale", "")[:500],
                        model_a_target_rule=rec.get("model_a_target_rule", "")[:500],
                        model_b_domain=rec.get("model_b_domain", ""),
                        model_b_concept_correct=bool(rec.get("model_b_concept_correct")),
                        model_b_assertion=rec.get("model_b_assertion", ""),
                        model_b_rationale=rec.get("model_b_rationale", "")[:500],
                        model_b_target_rule=rec.get("model_b_target_rule", "")[:500],
                        consensus_agreement=bool(rec.get("consensus_agreement")),
                        final_domain=rec.get("final_domain", ""),
                        non_cancer_flag=bool(rec.get("non_cancer_flag")),
                    )
                    written += 1
                except Exception:
                    logger.warning(
                        "Neo4j write failed for encounter=%s mt=%s", eid, mt, exc_info=True,
                    )
                    errors += 1
    finally:
        client.close()
    logger.info("  Neo4j: %d written, %d errors", written, errors)


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def run_review(
    input_path: str,
    output_path: str,
    batch_size: int = BATCH_SIZE,
    dry_run: bool = False,
    persist_neo4j: bool = True,
) -> dict[str, Any]:
    from libs.prompts.registry import get_prompt
    system_prompt = get_prompt("anchor_domain_review", version=1)

    # Load all records
    records: list[dict[str, Any]] = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    total = len(records)
    logger.info("Loaded %d records from %s", total, input_path)
    logger.info("Batch size: %d  |  Dry run: %s  |  Neo4j: %s",
                batch_size, dry_run, persist_neo4j)

    all_results: list[dict[str, Any]] = []
    reviewed_at = datetime.now(timezone.utc).isoformat()

    stats = {
        "total": total,
        "batches": 0,
        "agreements": 0,
        "disagreements": 0,
        "non_cancer_flags": 0,
        "errors": 0,
    }

    for batch_start in range(0, total, batch_size):
        batch = records[batch_start: batch_start + batch_size]
        batch_num = batch_start // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size
        logger.info(
            "Batch %d/%d — records %d-%d",
            batch_num, total_batches,
            batch_start + 1, batch_start + len(batch),
        )

        try:
            results_a, results_b = _review_batch(batch, system_prompt, dry_run=dry_run)
        except Exception:
            logger.error("Batch %d failed", batch_num, exc_info=True)
            stats["errors"] += len(batch)
            for rec in batch:
                all_results.append({
                    **rec,
                    "model_a_domain": "AMBIGUOUS",
                    "model_b_domain": "AMBIGUOUS",
                    "consensus_agreement": True,
                    "final_domain": "AMBIGUOUS",
                    "non_cancer_flag": False,
                    "reviewed_at": reviewed_at,
                    "error": "batch_failed",
                })
            continue

        for i, (rec, ra, rb) in enumerate(zip(batch, results_a, results_b)):
            domain_a = _normalise_domain(ra.get("domain", "AMBIGUOUS"))
            domain_b = _normalise_domain(rb.get("domain", "AMBIGUOUS"))
            agreement = domain_a == domain_b
            final_domain = domain_a if agreement else "DISAGREEMENT"
            non_cancer = domain_a == "NON_CANCER" or domain_b == "NON_CANCER"

            if agreement:
                stats["agreements"] += 1
            else:
                stats["disagreements"] += 1
            if non_cancer:
                stats["non_cancer_flags"] += 1

            result = {
                "encounter_id": rec.get("encounter_id", ""),
                "milestone_type": rec.get("milestone_type", ""),
                "patient_id": rec.get("patient_id", ""),
                "original_label": rec.get("label", 0),
                "text": rec.get("text", ""),
                "original_concept_id": rec.get("concept_id"),
                "model_a_domain": domain_a,
                "model_a_concept_correct": bool(ra.get("concept_correct")),
                "model_a_assertion": ra.get("assertion", ""),
                "model_a_rationale": ra.get("rationale", ""),
                "model_a_target_rule": ra.get("target_rule", ""),
                "model_b_domain": domain_b,
                "model_b_concept_correct": bool(rb.get("concept_correct")),
                "model_b_assertion": rb.get("assertion", ""),
                "model_b_rationale": rb.get("rationale", ""),
                "model_b_target_rule": rb.get("target_rule", ""),
                "consensus_agreement": agreement,
                "final_domain": final_domain,
                "non_cancer_flag": non_cancer,
                "reviewed_at": reviewed_at,
                # Carry provenance
                "concept_name": rec.get("concept_name"),
                "detection_method": rec.get("detection_method"),
                "source_file": rec.get("source_file"),
                "original_milestone_label": rec.get("label"),
            }
            all_results.append(result)

        stats["batches"] += 1

        # Brief pause between batches to respect rate limits
        if not dry_run and batch_start + batch_size < total:
            time.sleep(1.5)

    # Write output JSONL
    with open(output_path, "w", encoding="utf-8") as f:
        for rec in all_results:
            f.write(json.dumps(rec, default=str) + "\n")

    # Persist to Neo4j
    if persist_neo4j and not dry_run:
        logger.info("Persisting %d records to Neo4j...", len(all_results))
        _persist_to_neo4j(all_results)

    logger.info("")
    logger.info("=" * 60)
    logger.info("REVIEW SUMMARY")
    logger.info("=" * 60)
    logger.info("  Total records:    %d", stats["total"])
    logger.info("  Batches run:      %d", stats["batches"])
    logger.info("  Agreements:       %d (%.1f%%)",
                stats["agreements"],
                100 * stats["agreements"] / max(stats["total"], 1))
    logger.info("  Disagreements:    %d", stats["disagreements"])
    logger.info("  NON_CANCER flags: %d", stats["non_cancer_flags"])
    logger.info("  Errors:           %d", stats["errors"])
    logger.info("  Output:           %s", output_path)
    logger.info("=" * 60)

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Dual-LLM domain review of anchor training data"
    )
    parser.add_argument(
        "--input",
        default="exports/training/all_training_merged.jsonl",
        help="Normalised merged training JSONL",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output path (default: <input_dir>/anchor_review_results.jsonl)",
    )
    parser.add_argument(
        "--batch-size", type=int, default=BATCH_SIZE,
        help=f"Records per LLM call (default {BATCH_SIZE})",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse and validate input without calling LLMs",
    )
    parser.add_argument(
        "--no-neo4j", action="store_true",
        help="Skip Neo4j persistence (write JSONL only)",
    )
    args = parser.parse_args()

    output_path = args.output or str(
        Path(args.input).parent / "anchor_review_results.jsonl"
    )

    run_review(
        input_path=args.input,
        output_path=output_path,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        persist_neo4j=not args.no_neo4j,
    )


if __name__ == "__main__":
    main()
