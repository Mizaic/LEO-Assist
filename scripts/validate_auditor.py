"""Auditor validation harness -- measure auditor precision, recall, and F1.

Takes the golden test set JSON (from select_golden_test_set.py) and a
clinician-labelled ground truth JSON as inputs. Runs the audit LLM against
each encounter and compares findings against the ground truth.

Outputs per-domain precision, recall, F1 and flags any safety-critical
category where recall < 0.90. Stores results as an AuditRun node in Neo4j
with triggered_by="validation".

Acceptance thresholds (DI-LEO-AI-072, VT-LEO-AI-072):
  - Overall: precision >= 0.80, recall >= 0.85
  - Safety-critical (cancer, safeguarding, mental health): recall >= 0.90

Usage
-----
    python scripts/validate_auditor.py \\
        --golden scripts/golden_test_set.json \\
        --ground-truth scripts/golden_test_set_ground_truth.json \\
        --output scripts/auditor_validation_report.json

    # Dry run (no Neo4j writes):
    python scripts/validate_auditor.py \\
        --golden scripts/golden_test_set.json \\
        --ground-truth scripts/golden_test_set_ground_truth.json \\
        --dry-run

Ground truth JSON format:
    {
        "<encounter_id>": {
            "clinician_reviewed_by": "Dr A Smith",
            "clinician_reviewed_date": "2026-04-10",
            "should_be_coded": ["<snomed_id>", ...],
            "should_not_be_coded": ["<snomed_id>", ...],
            "notes": ""
        },
        ...
    }

Design control: DI-LEO-AI-072, VT-LEO-AI-072
Risk: R-LEO-AI-047 (undetected coding regression)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from dotenv import load_dotenv  # noqa: E402
from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

from libs.llm_client.factory import create_llm  # noqa: E402
from libs.neo4j_client.client import PatientGraphClient  # noqa: E402
from scripts.investigations._audit_llm import call_llm_with_retry  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("validate_auditor")

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

PRECISION_THRESHOLD = 0.80
RECALL_THRESHOLD_OVERALL = 0.85
RECALL_THRESHOLD_SAFETY_CRITICAL = 0.90

SAFETY_CRITICAL_DOMAINS = {"oncology", "safeguarding", "mental_health"}

# ---------------------------------------------------------------------------
# Cypher
# ---------------------------------------------------------------------------

_Q_ENCOUNTER_DETAIL = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id AND toString(e.id) = $encounter_id
OPTIONAL MATCH (e)-[r:DOCUMENTS]->(s)
RETURN e.text          AS text,
       toString(e.date) AS date,
       s.conceptId     AS concept_id,
       s.name          AS term,
       s.semanticTag   AS semantic_tag,
       r.evidence      AS evidence,
       r.context       AS context,
       r.confidence    AS confidence,
       r.domain        AS domain
ORDER BY r.confidence DESC
"""

_Q_WRITE_AUDIT_RUN = """
MERGE (a:AuditRun {run_id: $run_id})
ON CREATE SET
    a.triggered_by         = $triggered_by,
    a.since_date           = $since_date,
    a.until_date           = $until_date,
    a.status               = $status,
    a.encounter_count      = $encounter_count,
    a.pct_clean            = $pct_clean,
    a.critical_count       = $critical_count,
    a.auditor_model_version = $auditor_model_version,
    a.started_at           = $started_at,
    a.completed_at         = $completed_at,
    a.validation_precision = $validation_precision,
    a.validation_recall    = $validation_recall,
    a.validation_f1        = $validation_f1,
    a.validation_by_domain = $validation_by_domain
ON MATCH SET
    a.status               = CASE WHEN a.status = 'complete' THEN a.status
                                   ELSE $status END
RETURN a.run_id AS run_id, a.status AS status
"""


# ---------------------------------------------------------------------------
# Load inputs
# ---------------------------------------------------------------------------


def _load_golden_test_set(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    return data


def _load_ground_truth(path: Path) -> dict[str, dict[str, Any]]:
    data = json.loads(path.read_text())
    if "encounters" in data:
        return data["encounters"]
    return data


def _build_encounter_index(golden: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build encounter_id -> {patient_id, domain} lookup."""
    index: dict[str, dict[str, Any]] = {}
    for domain, encs in golden.get("encounters_by_domain", {}).items():
        for enc in encs:
            index[enc["encounter_id"]] = {
                "patient_id": enc["patient_id"],
                "domain": domain,
            }
    return index


# ---------------------------------------------------------------------------
# Audit one encounter
# ---------------------------------------------------------------------------


def _load_encounter_from_neo4j(
    client: PatientGraphClient,
    patient_id: str,
    encounter_id: str,
) -> tuple[str, list[dict[str, Any]]]:
    """Load encounter text and coded concepts from Neo4j."""
    rows = client.run(
        _Q_ENCOUNTER_DETAIL,
        patient_id=patient_id,
        encounter_id=encounter_id,
    )
    if not rows:
        return "", []
    text = str(rows[0].get("text") or "")
    coded = [r for r in rows if r.get("concept_id") is not None]
    return text, coded


def _run_audit_llm(
    llm: Any,
    encounter_text: str,
    coded_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Call the audit LLM to assess coding accuracy for one encounter.

    Reuses the audit LLM prompt infrastructure from audit_encounter_coding.py.
    Returns a dict with: assessment, missing_concepts, overcoded_concepts.
    """
    # Build the same prompt structure as the main audit script
    coded_summary = "\n".join(
        f"  - [{r['concept_id']}] {r['term']} ({r['semantic_tag']}) "
        f"evidence: '{r['evidence']}'"
        for r in coded_items[:20]
    ) or "  (no coded concepts)"

    prompt = f"""You are a clinical coding auditor. Review whether the SNOMED CT codes
assigned to this encounter are correct and complete.

ENCOUNTER TEXT:
{encounter_text[:2000]}

CURRENT CODED CONCEPTS:
{coded_summary}

For each coded concept: is it correct and supported by the encounter text?
Are there important clinical concepts in the text that are NOT coded?

Respond in JSON:
{{
  "assessment": "clean" | "missing_codes" | "overcoded" | "both",
  "missing_concepts": [
    {{"name": "...", "snomed_id": "...", "evidence_quote": "...", "severity": "critical|high|medium|low"}}
  ],
  "overcoded_concepts": [
    {{"snomed_id": "...", "name": "...", "reason": "..."}}
  ],
  "reasoning": "..."
}}"""

    result = call_llm_with_retry(llm, prompt)
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            logger.warning("Could not parse LLM JSON response")
            result = {"assessment": "error", "missing_concepts": [], "overcoded_concepts": []}
    return result


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def _compute_metrics(
    auditor_found: set[str],
    ground_truth_present: set[str],
    ground_truth_absent: set[str],
) -> dict[str, float]:
    """Compute precision and recall for one encounter.

    precision: of concepts auditor flagged as missing, how many were
               actually missing (in ground truth present but not coded)?
    recall: of concepts clinician says should be coded, how many did
            the auditor find?
    """
    # True positives: auditor flagged as missing AND clinician agrees should be coded
    tp = len(auditor_found & ground_truth_present)
    # False positives: auditor flagged as missing BUT clinician says coded correctly
    fp = len(auditor_found - ground_truth_present)
    # False negatives: clinician says should be coded, auditor missed it
    fn = len(ground_truth_present - auditor_found)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn}


def _aggregate_domain_metrics(
    encounter_results: list[dict[str, Any]],
) -> dict[str, dict[str, float]]:
    """Aggregate per-encounter metrics into per-domain summary."""
    domain_buckets: dict[str, list[dict[str, float]]] = defaultdict(list)
    for result in encounter_results:
        domain = result["domain"]
        domain_buckets[domain].append(result["metrics"])

    aggregated: dict[str, dict[str, float]] = {}
    for domain, metrics_list in domain_buckets.items():
        n = len(metrics_list)
        agg: dict[str, float] = {}
        for key in ("precision", "recall", "f1"):
            agg[key] = sum(m[key] for m in metrics_list) / n
        agg["encounter_count"] = float(n)
        aggregated[domain] = agg

    return aggregated


def _flag_safety_failures(
    domain_metrics: dict[str, dict[str, float]],
) -> list[str]:
    """Return list of failure messages for safety-critical domains below threshold."""
    failures = []
    for domain in SAFETY_CRITICAL_DOMAINS:
        if domain not in domain_metrics:
            continue
        recall = domain_metrics[domain]["recall"]
        if recall < RECALL_THRESHOLD_SAFETY_CRITICAL:
            failures.append(
                f"SAFETY FAILURE: {domain} recall={recall:.3f} "
                f"< {RECALL_THRESHOLD_SAFETY_CRITICAL} threshold. "
                "Do NOT deploy Loop 1 until the audit prompt is tuned for this category."
            )
    return failures


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _build_report(
    encounter_results: list[dict[str, Any]],
    domain_metrics: dict[str, dict[str, float]],
    overall_metrics: dict[str, float],
    safety_failures: list[str],
    run_id: str,
    model_version: str,
    started_at: str,
    completed_at: str,
) -> dict[str, Any]:
    return {
        "metadata": {
            "run_id": run_id,
            "triggered_by": "validation",
            "model_version": model_version,
            "started_at": started_at,
            "completed_at": completed_at,
            "encounter_count": len(encounter_results),
            "thresholds": {
                "overall_precision": PRECISION_THRESHOLD,
                "overall_recall": RECALL_THRESHOLD_OVERALL,
                "safety_critical_recall": RECALL_THRESHOLD_SAFETY_CRITICAL,
            },
        },
        "overall": overall_metrics,
        "by_domain": domain_metrics,
        "safety_failures": safety_failures,
        "deployment_blocked": len(safety_failures) > 0,
        "encounter_results": encounter_results,
    }


# ---------------------------------------------------------------------------
# Neo4j write
# ---------------------------------------------------------------------------


def _write_audit_run(
    client: PatientGraphClient,
    report: dict[str, Any],
    dry_run: bool,
) -> None:
    if dry_run:
        logger.info("DRY RUN: would write AuditRun to Neo4j")
        return

    meta = report["metadata"]
    overall = report["overall"]
    by_domain = report["by_domain"]

    client.run(
        _Q_WRITE_AUDIT_RUN,
        run_id=meta["run_id"],
        triggered_by="validation",
        since_date=meta["started_at"][:10],
        until_date=meta["completed_at"][:10],
        status="complete",
        encounter_count=meta["encounter_count"],
        pct_clean=overall.get("pct_clean", 0.0),
        critical_count=0,
        auditor_model_version=meta["model_version"],
        started_at=meta["started_at"],
        completed_at=meta["completed_at"],
        validation_precision=overall["precision"],
        validation_recall=overall["recall"],
        validation_f1=overall["f1"],
        validation_by_domain=json.dumps(
            {d: {"precision": v["precision"], "recall": v["recall"], "f1": v["f1"]}
             for d, v in by_domain.items()}
        ),
    )
    logger.info("AuditRun written to Neo4j: %s", meta["run_id"])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Auditor validation harness: measure precision, recall, F1 vs clinician ground truth"
    )
    parser.add_argument(
        "--golden",
        required=True,
        help="Path to golden test set JSON (from select_golden_test_set.py)",
    )
    parser.add_argument(
        "--ground-truth",
        required=True,
        help="Path to clinician-labelled ground truth JSON",
    )
    parser.add_argument(
        "--output",
        default="scripts/auditor_validation_report.json",
        help="Output validation report path",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write AuditRun to Neo4j",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=3,
        help="Parallel worker count for LLM calls (default: 3)",
    )
    args = parser.parse_args()

    golden_path = Path(args.golden)
    gt_path = Path(args.ground_truth)

    if not golden_path.exists():
        logger.error("Golden test set not found: %s", golden_path)
        sys.exit(1)
    if not gt_path.exists():
        logger.error("Ground truth file not found: %s", gt_path)
        sys.exit(1)

    logger.info("Loading golden test set from: %s", golden_path)
    golden = _load_golden_test_set(golden_path)

    logger.info("Loading ground truth from: %s", gt_path)
    ground_truth = _load_ground_truth(gt_path)

    enc_index = _build_encounter_index(golden)
    encounter_ids = list(enc_index.keys())
    logger.info("Encounters to validate: %d", len(encounter_ids))

    # Check ground truth coverage
    gt_covered = set(ground_truth.keys()) & set(encounter_ids)
    if len(gt_covered) < len(encounter_ids):
        missing = set(encounter_ids) - gt_covered
        logger.warning(
            "%d encounters not in ground truth -- they will be skipped: %s...",
            len(missing), list(missing)[:5],
        )

    client = PatientGraphClient()
    llm = create_llm(tier="big")
    model_version = getattr(llm, "model_id", "unknown")

    started_at = datetime.utcnow().isoformat() + "Z"
    run_id = f"validation-{uuid.uuid4().hex[:8]}"
    logger.info("Validation run_id: %s, model: %s", run_id, model_version)

    encounter_results: list[dict[str, Any]] = []

    for i, enc_id in enumerate(encounter_ids):
        if enc_id not in ground_truth:
            continue

        meta = enc_index[enc_id]
        patient_id = meta["patient_id"]
        domain = meta["domain"]
        gt = ground_truth[enc_id]

        logger.info("[%d/%d] Auditing %s (domain: %s)",
                    i + 1, len(encounter_ids), enc_id, domain)

        text, coded = _load_encounter_from_neo4j(client, patient_id, enc_id)
        if not text:
            logger.warning("Encounter %s has no text -- skipping", enc_id)
            continue

        try:
            llm_result = _run_audit_llm(llm, text, coded)
        except Exception as exc:
            logger.error("LLM call failed for %s: %s", enc_id, exc)
            continue

        # Extract concepts auditor flagged as missing
        auditor_missing: set[str] = {
            str(c.get("snomed_id", ""))
            for c in llm_result.get("missing_concepts", [])
            if c.get("snomed_id")
        }

        # Ground truth: what SHOULD be coded but may be missing
        gt_should_be_coded: set[str] = set(str(x) for x in gt.get("should_be_coded", []))
        gt_should_not: set[str] = set(str(x) for x in gt.get("should_not_be_coded", []))

        metrics = _compute_metrics(auditor_missing, gt_should_be_coded, gt_should_not)

        encounter_results.append({
            "encounter_id": enc_id,
            "patient_id": patient_id,
            "domain": domain,
            "auditor_assessment": llm_result.get("assessment", "unknown"),
            "auditor_missing_count": len(auditor_missing),
            "gt_should_be_coded_count": len(gt_should_be_coded),
            "metrics": metrics,
            "clinician_reviewed_by": gt.get("clinician_reviewed_by", ""),
            "notes": gt.get("notes", ""),
        })

    # Aggregate metrics
    domain_metrics = _aggregate_domain_metrics(encounter_results)

    # Overall metrics (macro-average across domains)
    if domain_metrics:
        overall_precision = sum(v["precision"] for v in domain_metrics.values()) / len(domain_metrics)
        overall_recall = sum(v["recall"] for v in domain_metrics.values()) / len(domain_metrics)
        overall_f1 = sum(v["f1"] for v in domain_metrics.values()) / len(domain_metrics)
    else:
        overall_precision = overall_recall = overall_f1 = 0.0

    overall_metrics = {
        "precision": overall_precision,
        "recall": overall_recall,
        "f1": overall_f1,
        "encounter_count": len(encounter_results),
        "precision_threshold_met": overall_precision >= PRECISION_THRESHOLD,
        "recall_threshold_met": overall_recall >= RECALL_THRESHOLD_OVERALL,
        "pct_clean": 0.0,  # not applicable for validation runs
    }

    safety_failures = _flag_safety_failures(domain_metrics)

    completed_at = datetime.utcnow().isoformat() + "Z"
    report = _build_report(
        encounter_results, domain_metrics, overall_metrics,
        safety_failures, run_id, model_version, started_at, completed_at,
    )

    # Write output
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2))
    logger.info("Validation report written to: %s", out_path)

    # Write to Neo4j
    _write_audit_run(client, report, args.dry_run)

    # Summary
    logger.info("=== VALIDATION SUMMARY ===")
    logger.info("Encounters validated: %d", len(encounter_results))
    logger.info(
        "Overall: precision=%.3f (%s), recall=%.3f (%s), F1=%.3f",
        overall_precision,
        "PASS" if overall_metrics["precision_threshold_met"] else "FAIL",
        overall_recall,
        "PASS" if overall_metrics["recall_threshold_met"] else "FAIL",
        overall_f1,
    )
    for domain, metrics in sorted(domain_metrics.items()):
        flag = " [SAFETY-CRITICAL]" if domain in SAFETY_CRITICAL_DOMAINS else ""
        logger.info(
            "  %-20s precision=%.3f recall=%.3f f1=%.3f (n=%d)%s",
            domain,
            metrics["precision"],
            metrics["recall"],
            metrics["f1"],
            int(metrics["encounter_count"]),
            flag,
        )

    if safety_failures:
        logger.error("=== SAFETY FAILURES ===")
        for failure in safety_failures:
            logger.error(failure)
        logger.error(
            "Do NOT deploy Loop 1 until all safety-critical recall thresholds are met. "
            "Tune the audit prompt for the failing categories and re-run validation."
        )
        sys.exit(2)
    else:
        logger.info("All safety-critical recall thresholds met. Auditor validation PASSED.")


if __name__ == "__main__":
    main()
