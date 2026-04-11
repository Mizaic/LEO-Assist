"""Prototype test: run exclusion detection against live Neo4j data.

Finds patients with cancer referrals in the patient graph, then runs the
exclusion detector to classify post-referral encounters. Outputs a
per-patient summary showing what was found.

Usage examples
--------------
  # Run for specific patients
  python scripts/test_exclusion_detector.py --patients 4563591157,4505618269

  # Run for top N patients by encounter count (who have referrals)
  python scripts/test_exclusion_detector.py --limit 10

  # Dry-run: find referrals but skip LLM calls (rule-based only)
  python scripts/test_exclusion_detector.py --limit 5 --rules-only

  # Custom window (days after referral to search)
  python scripts/test_exclusion_detector.py --patients 4245896566 --window 150
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("test_exclusion")

for _noisy in ("httpx", "httpcore", "botocore", "urllib3"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

from libs.neo4j_client.client import PatientGraphClient
from libs.exclusion_detector.detector import (
    ExclusionResult,
    detect_exclusion,
    fetch_referrals,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIND_PATIENTS_WITH_REFERRALS = """\
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE e.text CONTAINS 'Fast track referral for suspected'
   OR e.text CONTAINS 'fast track referral for suspected'
   OR e.text CONTAINS 'Seen in fast track suspected'
   OR e.text CONTAINS 'seen in fast track suspected'
WITH p, e
ORDER BY e.date
WITH p,
     collect({
         encounter_id: toString(e.id),
         encounter_date: toString(e.date),
         text: e.text
     })[0] AS first_ref
RETURN toString(p.id) AS patient_id,
       first_ref.encounter_date AS referral_date,
       first_ref.text AS referral_text,
       first_ref.encounter_id AS referral_encounter_id
ORDER BY first_ref.encounter_date DESC
LIMIT $limit
"""

_FIND_REFERRALS_FOR_PATIENT = """\
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $pid
  AND (e.text CONTAINS 'Fast track referral for suspected'
    OR e.text CONTAINS 'fast track referral for suspected'
    OR e.text CONTAINS 'Seen in fast track suspected'
    OR e.text CONTAINS 'seen in fast track suspected')
RETURN toString(e.id) AS encounter_id,
       toString(e.date) AS encounter_date,
       e.text AS referral_text
ORDER BY e.date
LIMIT 5
"""

_REFERRAL_PATTERN = re.compile(
    r"(?:Fast track referral for suspected|Seen in fast track suspected)\s+"
    r"(.+?)(?:\s*\(|cancer clinic|\s*$)",
    re.IGNORECASE,
)


def _extract_cancer_type(text: str) -> str:
    """Extract a readable cancer type from encounter text.

    Searches for 'Fast track referral for suspected ...' or
    'Seen in fast track suspected ...' patterns.
    """
    m = _REFERRAL_PATTERN.search(text)
    if m:
        cancer = m.group(1).strip().rstrip(".")
        cancer = cancer.replace("cancer clinic", "cancer").strip()
        return cancer or "cancer"
    return "cancer"


def find_patients_with_referrals(
    client: PatientGraphClient,
    limit: int,
) -> list[dict]:
    """Find patients who have fast-track referral text in encounters."""
    rows = client.run(_FIND_PATIENTS_WITH_REFERRALS, limit=limit)
    return [dict(r) for r in rows]


def find_referrals_for_patient(
    client: PatientGraphClient,
    patient_id: str,
) -> list[dict]:
    """Find referral encounters for a specific patient by text search."""
    rows = client.run(_FIND_REFERRALS_FOR_PATIENT, pid=patient_id)
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

_OUTCOME_EMOJI = {
    "cancer_excluded": "[ EXCLUDED ]",
    "cancer_confirmed": "[CONFIRMED ]",
    "still_investigating": "[INVESTIG. ]",
    "pending_letter": "[ LETTER   ]",
    "inconclusive": "[INCONCLUS.]",
    "conflicting": "[CONFLICT! ]",
    "not_relevant": "[    --    ]",
}


def _print_result(result: ExclusionResult) -> None:
    tag = _OUTCOME_EMOJI.get(result.outcome, "[???]")
    print(f"\n{'='*72}")
    print(f"  Patient: {result.patient_id}")
    print(f"  Referral: {result.referral_cancer_type} ({result.referral_date})")
    print(f"  Window: {result.referral_date} -> {result.window_end}")
    print(
        f"  Encounters scanned: {result.encounters_scanned}"
        f" (skipped: {result.encounters_skipped})"
    )
    print(
        f"  OUTCOME: {tag}  {result.outcome}" f"  (confidence: {result.confidence:.2f})"
    )
    print(f"{'='*72}")

    if result.encounter_outcomes:
        print(f"\n  Classified encounters ({len(result.encounter_outcomes)}):")
        for eo in result.encounter_outcomes:
            eo_tag = _OUTCOME_EMOJI.get(eo.outcome, "")
            agreement = (
                "agreement"
                if eo.detection_method == "llm_consensus"
                else eo.detection_method
            )
            print(f"    {eo_tag} {eo.encounter_date}  [{agreement}]")
            if eo.evidence_text:
                print(f"       Evidence: {eo.evidence_text[:120]}")
            if eo.reasoning:
                print(f"       Reason:   {eo.reasoning[:120]}")
            if eo.detection_method.startswith("llm"):
                print(
                    f"       Models:   A={eo.model_a_outcome}"
                    f"  B={eo.model_b_outcome}"
                )

    if result.pending_letters:
        print(f"\n  Pending letters ({len(result.pending_letters)}):")
        for pl in result.pending_letters:
            print(
                f"    [{pl.detection_method}] {pl.encounter_date}"
                f"  {pl.text_excerpt[:100]}"
            )

    if not result.encounter_outcomes and not result.pending_letters:
        print("\n  No clinically relevant encounters found in window.")


def _print_summary(results: list[ExclusionResult]) -> None:
    print(f"\n{'='*72}")
    print(f"  SUMMARY — {len(results)} patients processed")
    print(f"{'='*72}")
    counts: dict[str, int] = {}
    for r in results:
        counts[r.outcome] = counts.get(r.outcome, 0) + 1
    for outcome, count in sorted(counts.items()):
        tag = _OUTCOME_EMOJI.get(outcome, "")
        print(f"    {tag}  {outcome}: {count}")
    total_llm = sum(
        1
        for r in results
        for eo in r.encounter_outcomes
        if eo.detection_method.startswith("llm")
    )
    total_rule = sum(
        1
        for r in results
        for eo in r.encounter_outcomes
        if eo.detection_method == "rule"
    )
    print(f"\n    LLM classifications: {total_llm}")
    print(f"    Rule classifications: {total_rule}")


# ---------------------------------------------------------------------------
# Rules-only mode (no LLM calls)
# ---------------------------------------------------------------------------


def _detect_exclusion_rules_only(
    patient_id: str,
    referral_date: str,
    referral_cancer_type: str,
    patient_client: PatientGraphClient,
    window_days: int,
) -> ExclusionResult:
    """Run rule-based detection only — skips LLM calls for quick prototyping."""
    from libs.exclusion_detector.detector import (
        ExclusionResult,
        EncounterOutcome,
        PendingLetter,
        _fetch_post_referral_encounters,
        _is_skip_encounter,
        _is_cancer_letter,
        _is_cancer_relevant,
        _has_keywords,
        _aggregate_outcome,
        EXCLUSION_KEYWORDS,
        SOFT_EXCLUSION_KEYWORDS,
        DIAGNOSIS_KEYWORDS,
        INVESTIGATION_KEYWORDS,
    )

    encounters, window_end = _fetch_post_referral_encounters(
        patient_client,
        patient_id,
        referral_date,
        window_days,
    )

    result = ExclusionResult(
        patient_id=patient_id,
        referral_date=referral_date,
        referral_cancer_type=referral_cancer_type,
        outcome="inconclusive",
        window_end=window_end,
        encounters_scanned=len(encounters),
    )

    for enc in encounters:
        enc_id = str(enc.get("encounter_id", ""))
        enc_date = str(enc.get("encounter_date", ""))
        text = str(enc.get("text") or "")
        content_type = enc.get("content_type") or ""

        if not text.strip() or _is_skip_encounter(text):
            result.encounters_skipped += 1
            continue

        is_letter = content_type == "document_transfer" or _is_cancer_letter(text)
        has_cancer_kw = _is_cancer_relevant(text)

        if is_letter and not has_cancer_kw:
            result.pending_letters.append(
                PendingLetter(
                    encounter_id=enc_id,
                    encounter_date=enc_date,
                    text_excerpt=text[:200],
                    detection_method="rule",
                )
            )
            result.encounter_outcomes.append(
                EncounterOutcome(
                    encounter_id=enc_id,
                    encounter_date=enc_date,
                    outcome="pending_letter",
                    confidence=0.6,
                    evidence_text=text[:100],
                    reasoning="Cancer-specialty letter detected by rule",
                    detection_method="rule",
                )
            )
            continue

        if not has_cancer_kw and not is_letter:
            result.encounters_skipped += 1
            continue

        if _has_keywords(text, EXCLUSION_KEYWORDS):
            result.encounter_outcomes.append(
                EncounterOutcome(
                    encounter_id=enc_id,
                    encounter_date=enc_date,
                    outcome="cancer_excluded",
                    confidence=0.6,
                    evidence_text=text[:100],
                    reasoning="Strong exclusion keyword (needs LLM verification)",
                    detection_method="rule",
                )
            )
        elif _has_keywords(text, DIAGNOSIS_KEYWORDS):
            result.encounter_outcomes.append(
                EncounterOutcome(
                    encounter_id=enc_id,
                    encounter_date=enc_date,
                    outcome="cancer_confirmed",
                    confidence=0.6,
                    evidence_text=text[:100],
                    reasoning="Cancer diagnosis keyword (needs LLM verification)",
                    detection_method="rule",
                )
            )
        elif _has_keywords(text, INVESTIGATION_KEYWORDS):
            result.encounter_outcomes.append(
                EncounterOutcome(
                    encounter_id=enc_id,
                    encounter_date=enc_date,
                    outcome="still_investigating",
                    confidence=0.4,
                    evidence_text=text[:100],
                    reasoning="Investigation keyword match (needs LLM verification)",
                    detection_method="rule",
                )
            )
        elif _has_keywords(text, SOFT_EXCLUSION_KEYWORDS):
            result.encounter_outcomes.append(
                EncounterOutcome(
                    encounter_id=enc_id,
                    encounter_date=enc_date,
                    outcome="cancer_excluded",
                    confidence=0.3,
                    evidence_text=text[:100],
                    reasoning="Soft exclusion keyword (needs LLM verification)",
                    detection_method="rule",
                )
            )
        elif is_letter:
            result.encounter_outcomes.append(
                EncounterOutcome(
                    encounter_id=enc_id,
                    encounter_date=enc_date,
                    outcome="pending_letter",
                    confidence=0.5,
                    evidence_text=text[:100],
                    reasoning="Cancer-specialty letter with keywords",
                    detection_method="rule",
                )
            )
            result.pending_letters.append(
                PendingLetter(
                    encounter_id=enc_id,
                    encounter_date=enc_date,
                    text_excerpt=text[:200],
                    detection_method="rule",
                )
            )
        else:
            result.encounters_skipped += 1

    result.outcome = _aggregate_outcome(result)
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test exclusion detection against Neo4j patient data",
    )
    parser.add_argument(
        "--patients",
        type=str,
        default="",
        help="Comma-separated patient IDs (overrides --limit)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Number of patients to process (default: 5)",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=100,
        help="Days after referral to search (default: 100)",
    )
    parser.add_argument(
        "--rules-only",
        action="store_true",
        help="Skip LLM calls, use rule-based detection only",
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default="",
        help="Optional file path to write JSON results",
    )
    args = parser.parse_args()

    client = PatientGraphClient()
    results: list[ExclusionResult] = []

    try:
        if args.patients:
            patient_ids = [p.strip() for p in args.patients.split(",")]
            targets = []
            for pid in patient_ids:
                refs = find_referrals_for_patient(client, pid)
                if refs:
                    ref = refs[0]
                    targets.append(
                        {
                            "patient_id": pid,
                            "referral_date": ref["encounter_date"],
                            "referral_text": ref["referral_text"],
                        }
                    )
                else:
                    logger.warning("Patient %s has no referral text — skipping", pid)
        else:
            targets = find_patients_with_referrals(client, limit=args.limit)

        if not targets:
            logger.error("No patients with fast-track referrals found")
            return

        logger.info("Found %d patient(s) with referrals", len(targets))
        t0 = time.time()

        for i, target in enumerate(targets, 1):
            pid = target["patient_id"]
            ref_date = target["referral_date"]
            cancer_type = _extract_cancer_type(target.get("referral_text", ""))

            logger.info(
                "[%d/%d] Patient %s — %s referred %s (window=%d days)",
                i,
                len(targets),
                pid,
                cancer_type,
                ref_date,
                args.window,
            )

            if args.rules_only:
                result = _detect_exclusion_rules_only(
                    pid,
                    ref_date,
                    cancer_type,
                    client,
                    args.window,
                )
            else:
                result = detect_exclusion(
                    pid,
                    ref_date,
                    cancer_type,
                    client,
                    args.window,
                )

            results.append(result)
            _print_result(result)

        _print_summary(results)
        elapsed = time.time() - t0
        logger.info(
            "Completed in %.1fs (%.1fs per patient)", elapsed, elapsed / len(targets)
        )

        if args.json_out:
            _write_json(results, args.json_out)
            logger.info("JSON results written to %s", args.json_out)

    finally:
        client.close()


def _write_json(results: list[ExclusionResult], path: str) -> None:
    import dataclasses

    data = [dataclasses.asdict(r) for r in results]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


if __name__ == "__main__":
    main()
