"""Generate clean per-milestone training datasets from an anchor audit JSONL.

Reads the output of ``audit_patient_anchors.py`` and applies clinician-reviewed
inclusion/exclusion rules to produce four JSONL files — one per milestone type —
suitable for supervised training or evaluation.

Rules are codified from manual review of 104-patient audit output (2026-02-27):
  • Structural false-positive patterns are stripped before export
  • Diagnosis anchors that are actually specialist-visit findings are excluded
  • Investigation candidates are promoted to positive examples only when evidence
    is unambiguous (concept-coded, or resolver+LLM confirmed with high signal)

Pass ``--enrich`` to pull evidence text spans from the patient graph's
``:DOCUMENTS`` relationships.  This adds the ``evidence`` field — the exact
text the coding worker extracted when it linked an encounter to a SNOMED
concept.  These are clinician-quality labelled spans ideal for NER training.

Usage
-----
    python scripts/generate_training_datasets.py \\
        --input exports/anchor_audit_20260227_174718.jsonl \\
        --output-dir exports/training \\
        --enrich

Output
------
    <output-dir>/referral_training.jsonl
    <output-dir>/diagnosis_training.jsonl
    <output-dir>/treatment_start_training.jsonl
    <output-dir>/specialist_visit_training.jsonl
    <output-dir>/training_stats.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s"
)
logger = logging.getLogger("gen_training")


# ──────────────────────────────────────────────────────────────────────────────
# Exclusion patterns — sentences/phrases that are NOT clinical milestone evidence
# ──────────────────────────────────────────────────────────────────────────────

_STAFF_NAME_RE = re.compile(
    r"^Surgery:\s+[A-Z][A-Za-z'-]+,\s+[A-Z]",
    re.IGNORECASE,
)
_CONTACT_SURGERY_RE = re.compile(r"contact the surgery", re.IGNORECASE)
_BARIATRIC_TEMPLATE_RE = re.compile(r"bariatric surgery outside the UK", re.IGNORECASE)
_BRING_TO_SURGERY_RE = re.compile(r"bring .{0,40} to the surgery", re.IGNORECASE)
_DROP_TO_SURGERY_RE = re.compile(r"drop .{0,30} to surgery", re.IGNORECASE)

_SENTENCE_EXCLUDE_PATTERNS = [
    _STAFF_NAME_RE,
    _CONTACT_SURGERY_RE,
    _BARIATRIC_TEMPLATE_RE,
    _BRING_TO_SURGERY_RE,
    _DROP_TO_SURGERY_RE,
]

_CLINIC_FINDING_RE = re.compile(
    r"Seen in .+ clinic"
    r"|Did not attend .+ clinic"
    r"|Referral .+ clinic"
    r"|clinic \(finding\)",
    re.IGNORECASE,
)

_NEGATION_RE = re.compile(
    r"no evidence of|no fam.{0,5} h[xi]|no family history|rule out|unlikely to represent",
    re.IGNORECASE,
)

# Non-cancer-specific referral SNOMED terms that should not count as
# cancer pathway referrals
_NON_CANCER_REFERRAL_TERMS = {
    "university admission medical",
    "establishment of trust",
    "referral to community",
    "community nursing",
    "wound care",
    "transportation to",
}


def _phrase_is_excluded(phrase: str) -> bool:
    return any(pat.search(phrase) for pat in _SENTENCE_EXCLUDE_PATTERNS)


# ──────────────────────────────────────────────────────────────────────────────
# Per-milestone anchor filtering
# ──────────────────────────────────────────────────────────────────────────────


def _clean_referral_anchor(anchor: dict) -> dict | None:
    """Keep only cancer-pathway referrals; exclude generic GP/A&E/community."""
    name = (anchor.get("concept_name") or "").lower()
    if any(term in name for term in _NON_CANCER_REFERRAL_TERMS):
        return None
    phrase = anchor.get("phrase_matched") or anchor.get("phrase") or ""
    if _phrase_is_excluded(phrase):
        return None
    return anchor


def _clean_diagnosis_anchor(anchor: dict) -> dict | None:
    """Exclude clinic-finding concepts and negated mentions."""
    name = anchor.get("concept_name") or ""
    if _CLINIC_FINDING_RE.search(name):
        return None
    phrase = anchor.get("phrase_matched") or anchor.get("phrase") or ""
    if _NEGATION_RE.search(phrase):
        return None
    # "referral" in the phrase with a diagnosis concept = misclassified referral
    if "referral" in phrase.lower() and "diagnosis" not in phrase.lower():
        name_lower = name.lower()
        if "referral" in name_lower or "clinic" in name_lower:
            return None
    return anchor


def _clean_treatment_anchor(anchor: dict) -> dict | None:
    """Exclude staff-name matches, admin messages, and non-cancer procedures."""
    phrase = anchor.get("phrase_matched") or anchor.get("phrase") or ""
    if _phrase_is_excluded(phrase):
        return None
    name = (anchor.get("concept_name") or "").lower()
    # Mohs surgery matched from "Had a surgery" free text — too vague
    if "mohs" in name and "mohs" not in phrase.lower():
        return None
    return anchor


def _clean_specialist_anchor(anchor: dict) -> dict | None:
    """Exclude A&E / non-cancer clinic visits."""
    name = (anchor.get("concept_name") or "").lower()
    phrase = (anchor.get("phrase_matched") or anchor.get("phrase") or "").lower()
    if "a&e" in phrase or "accident and emergency" in phrase:
        return None
    if "rheum" in phrase or "ear check" in phrase:
        return None
    if _phrase_is_excluded(phrase):
        return None
    return anchor


_CLEANERS = {
    "referral": _clean_referral_anchor,
    "diagnosis": _clean_diagnosis_anchor,
    "treatment_start": _clean_treatment_anchor,
    "specialist_visit": _clean_specialist_anchor,
}


# ──────────────────────────────────────────────────────────────────────────────
# Investigation candidate promotion
# ──────────────────────────────────────────────────────────────────────────────


def _promotable_investigation_candidates(
    investigation: dict,
    milestone_type: str,
) -> list[dict]:
    """Extract high-confidence candidates from investigation that can be
    promoted to positive training examples.

    Only promotes candidates where:
    - context_signal == "confirmed" AND keyword_score >= 0.3
    - At least one resolver_hit with llm_label == "confirmed" and score >= 0.55
    - The phrase passes the same exclusion filters as direct anchors
    """
    candidates = investigation.get("candidates", [])
    promoted = []
    cleaner = _CLEANERS.get(milestone_type, lambda a: a)

    for cand in candidates:
        signal = cand.get("context_signal", "")
        kscore = cand.get("keyword_score", 0)
        if signal != "confirmed" or kscore < 0.3:
            continue

        snippet = cand.get("snippet", "")
        if _phrase_is_excluded(snippet):
            continue

        # Check resolver hits for strong LLM-confirmed evidence
        resolver_hits = cand.get("resolver_hits", [])
        best_confirmed = None
        for rh in resolver_hits:
            if rh.get("llm_label") == "confirmed" and rh.get("score", 0) >= 0.55:
                concept_name = rh.get("snomed_term", "")
                if milestone_type == "diagnosis" and _CLINIC_FINDING_RE.search(
                    concept_name
                ):
                    continue
                if milestone_type == "diagnosis" and _NEGATION_RE.search(
                    rh.get("sentence", "")
                ):
                    continue
                best_confirmed = rh
                break

        if best_confirmed is None:
            continue

        entry = {
            "encounter_id": cand.get("encounter_id", ""),
            "encounter_date": cand.get("date", ""),
            "concept_id": best_confirmed.get("snomed_id", ""),
            "concept_name": best_confirmed.get("snomed_term", ""),
            "confidence": round(best_confirmed.get("score", 0) * 0.8, 4),
            "source": "investigation_promoted",
            "detection_method": "investigation+llm",
            "phrase_matched": snippet[:200],
            "disambiguation": "confirmed",
        }

        if cleaner(entry) is not None:
            promoted.append(entry)

    return promoted


# ──────────────────────────────────────────────────────────────────────────────
# Negative example extraction
# ──────────────────────────────────────────────────────────────────────────────


def _extract_negatives_from_investigation(
    investigation: dict,
    milestone_type: str,
) -> list[dict]:
    """Extract clear negative examples from investigation candidates.

    Picks candidates where the LLM labelled hits as irrelevant/suspected, or
    where the phrase is structurally a known false positive.
    """
    candidates = investigation.get("candidates", [])
    negatives = []

    for cand in candidates:
        snippet = cand.get("snippet", "")
        resolver_hits = cand.get("resolver_hits", [])

        is_negative = False
        reason = ""

        if _phrase_is_excluded(snippet):
            is_negative = True
            reason = "excluded_pattern"
        elif _NEGATION_RE.search(snippet):
            is_negative = True
            reason = "negated_mention"
        elif milestone_type == "diagnosis":
            if (
                all(
                    rh.get("llm_label") in ("irrelevant", "suspected")
                    for rh in resolver_hits
                    if rh.get("llm_label")
                )
                and resolver_hits
            ):
                is_negative = True
                reason = "llm_all_irrelevant_or_suspected"

        if is_negative:
            negatives.append(
                {
                    "encounter_id": cand.get("encounter_id", ""),
                    "encounter_date": cand.get("date", ""),
                    "snippet": snippet[:200],
                    "label": 0,
                    "reason": reason,
                    "milestone_type": milestone_type,
                }
            )

    return negatives


# ──────────────────────────────────────────────────────────────────────────────
# Neo4j enrichment — pull evidence text spans from :DOCUMENTS
# ──────────────────────────────────────────────────────────────────────────────

# Batch query: for each patient, pull ALL :DOCUMENTS with evidence OR
# encounter text so we can derive spans.
_PATIENT_EVIDENCE_QUERY = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(c)
WHERE toString(p.id) = $pid
RETURN toString(e.id)   AS encounter_id,
       c.conceptId      AS concept_id,
       c.name           AS concept_name,
       r.evidence       AS evidence,
       e.text           AS encounter_text
"""


def _build_evidence_cache(
    records: list[dict],
    client,
) -> dict[str, dict]:
    """Query Neo4j for evidence spans and encounter text.

    Returns a dict keyed by ``encounter_id|concept_id`` → {evidence, encounter_text}.
    Batches by patient to minimize round-trips.
    """
    patient_ids = {
        rec["patient_id"]
        for rec in records
        if rec.get("detection_method") == "concept" and rec.get("patient_id")
    }

    cache: dict[str, dict] = {}
    for pid in sorted(patient_ids):
        try:
            rows = client.run(_PATIENT_EVIDENCE_QUERY, pid=pid)
            for row in rows:
                eid = str(row.get("encounter_id", ""))
                cid = str(row.get("concept_id", ""))
                key = f"{eid}|{cid}"
                evidence = row.get("evidence") or ""
                enc_text = row.get("encounter_text") or ""
                cache[key] = {"evidence": evidence, "encounter_text": enc_text}
        except Exception:
            logger.warning("Evidence query failed for patient %s", pid, exc_info=True)

    ev_count = sum(1 for v in cache.values() if v["evidence"])
    logger.info(
        "  Enrichment: %d patients → %d DOCUMENTS links, %d with evidence property",
        len(patient_ids),
        len(cache),
        ev_count,
    )
    return cache


def _extract_evidence_span(concept_name: str, encounter_text: str) -> str:
    """Try to locate the concept mention in the encounter text and return
    a context window around it — suitable as an NER training span."""
    if not encounter_text or not concept_name:
        return ""
    text_lower = encounter_text.lower()
    # Try the concept name itself
    needle = concept_name.lower()
    # Strip trailing semantic tag like "(procedure)" or "(disorder)"
    clean = re.sub(r"\s*\([^)]+\)\s*$", "", needle).strip()
    idx = text_lower.find(clean)
    if idx == -1 and len(clean) > 20:
        # Try first few words
        words = clean.split()
        short = " ".join(words[:3])
        idx = text_lower.find(short)

    if idx >= 0:
        # Return a window: 30 chars before, the match, 50 chars after
        start = max(0, idx - 30)
        end = min(len(encounter_text), idx + len(clean) + 50)
        return encounter_text[start:end].strip()
    return ""


def _enrich_records_with_evidence(
    records: list[dict],
    cache: dict[str, dict],
) -> int:
    """Add ``evidence`` and ``encounter_text`` fields from the cache.
    Returns count enriched."""
    enriched = 0
    for rec in records:
        if rec.get("evidence"):
            continue
        eid = rec.get("encounter_id", "")
        cid = str(rec.get("concept_id", ""))
        key = f"{eid}|{cid}"
        hit = cache.get(key)
        if not hit:
            continue

        # Prefer the explicit evidence property
        if hit["evidence"]:
            rec["evidence"] = hit["evidence"]
            enriched += 1
        elif hit["encounter_text"]:
            # Derive a span from encounter text
            span = _extract_evidence_span(
                rec.get("concept_name", ""),
                hit["encounter_text"],
            )
            if span:
                rec["evidence"] = span
                enriched += 1
            else:
                # Fall back to first 200 chars of encounter text as context
                rec["evidence"] = hit["encounter_text"][:200]
                enriched += 1

    return enriched


# ──────────────────────────────────────────────────────────────────────────────
# Main pipeline
# ──────────────────────────────────────────────────────────────────────────────


def process_audit_file(
    input_path: str, output_dir: str, enrich: bool = False
) -> dict[str, Any]:
    os.makedirs(output_dir, exist_ok=True)

    milestones = ["referral", "diagnosis", "treatment_start", "specialist_visit"]
    positive_records: dict[str, list[dict]] = {m: [] for m in milestones}
    negative_records: dict[str, list[dict]] = {m: [] for m in milestones}
    stats: dict[str, dict] = {
        m: {
            "concept_positives": 0,
            "hybrid_positives": 0,
            "promoted_positives": 0,
            "excluded_anchors": 0,
            "negatives": 0,
            "patients_with_positive": 0,
        }
        for m in milestones
    }

    with open(input_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Skipping invalid JSON on line %d", line_num)
                continue

            patient_id = row.get("patient_id", "unknown")
            anchors = row.get("anchors", {})
            investigation = row.get("investigation", {})

            for milestone in milestones:
                cleaner = _CLEANERS.get(milestone, lambda a: a)
                raw_anchors = anchors.get(milestone, [])
                patient_has_positive = False

                # Clean direct anchors
                for anchor in raw_anchors:
                    cleaned = cleaner(anchor)
                    if cleaned is None:
                        stats[milestone]["excluded_anchors"] += 1
                        continue
                    record = {
                        "patient_id": patient_id,
                        "label": 1,
                        **cleaned,
                    }
                    if "concept_id" in record:
                        record["concept_id"] = str(record["concept_id"])
                    positive_records[milestone].append(record)
                    patient_has_positive = True
                    method = cleaned.get("detection_method", "")
                    if method == "concept":
                        stats[milestone]["concept_positives"] += 1
                    else:
                        stats[milestone]["hybrid_positives"] += 1

                # Promote high-confidence investigation candidates
                inv_block = investigation.get(milestone, {})
                if inv_block:
                    promoted = _promotable_investigation_candidates(
                        inv_block, milestone
                    )
                    for entry in promoted:
                        record = {"patient_id": patient_id, "label": 1, **entry}
                        positive_records[milestone].append(record)
                        stats[milestone]["promoted_positives"] += 1
                        patient_has_positive = True

                    # Extract negatives
                    negs = _extract_negatives_from_investigation(inv_block, milestone)
                    for neg in negs:
                        neg["patient_id"] = patient_id
                        negative_records[milestone].append(neg)
                        stats[milestone]["negatives"] += 1

                if patient_has_positive:
                    stats[milestone]["patients_with_positive"] += 1

    # Enrich with evidence text spans from Neo4j
    if enrich:
        from libs.neo4j_client import PatientGraphClient

        logger.info("  Connecting to patient graph for evidence enrichment...")
        pg_client = PatientGraphClient()
        try:
            all_positives = []
            for m in milestones:
                all_positives.extend(positive_records[m])
            cache = _build_evidence_cache(all_positives, pg_client)
            total_enriched = 0
            for m in milestones:
                n = _enrich_records_with_evidence(positive_records[m], cache)
                total_enriched += n
                if n:
                    logger.info("    %s: enriched %d records with evidence spans", m, n)
            stats["_enrichment"] = {
                "evidence_spans_found": len(cache),
                "records_enriched": total_enriched,
            }
        finally:
            pg_client.close()

    # Write output files
    for milestone in milestones:
        out_path = os.path.join(output_dir, f"{milestone}_training.jsonl")
        all_records = positive_records[milestone] + negative_records[milestone]
        with open(out_path, "w", encoding="utf-8") as f:
            for record in all_records:
                f.write(json.dumps(record, default=str) + "\n")
        pos_count = len(positive_records[milestone])
        neg_count = len(negative_records[milestone])
        logger.info(
            "  %s: %d positives + %d negatives → %s",
            milestone,
            pos_count,
            neg_count,
            out_path,
        )
        stats[milestone]["total_positives"] = pos_count
        stats[milestone]["total_negatives"] = neg_count

    # Write stats
    stats_path = os.path.join(output_dir, "training_stats.json")
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)
    logger.info("  Stats → %s", stats_path)

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Generate per-milestone training datasets"
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to anchor_audit JSONL file",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: <input_dir>/training)",
    )
    parser.add_argument(
        "--enrich",
        action="store_true",
        help="Pull evidence text spans from the patient graph's :DOCUMENTS "
        "relationships (requires PATIENT_NEO4J_URI env var)",
    )
    args = parser.parse_args()

    if args.output_dir is None:
        args.output_dir = str(Path(args.input).parent / "training")

    logger.info("Generating training datasets from %s", args.input)
    logger.info("Output directory: %s", args.output_dir)
    if args.enrich:
        logger.info("Evidence enrichment: ENABLED")
    stats = process_audit_file(args.input, args.output_dir, enrich=args.enrich)

    logger.info("")
    logger.info("=" * 60)
    logger.info("TRAINING DATASET SUMMARY")
    logger.info("=" * 60)
    milestones = ["referral", "diagnosis", "treatment_start", "specialist_visit"]
    for milestone in milestones:
        s = stats.get(milestone, {})
        logger.info(
            "  %-20s %4d pos (concept=%d hybrid=%d promoted=%d) "
            "%4d neg  [excluded=%d, %d patients]",
            milestone,
            s.get("total_positives", 0),
            s.get("concept_positives", 0),
            s.get("hybrid_positives", 0),
            s.get("promoted_positives", 0),
            s.get("total_negatives", 0),
            s.get("excluded_anchors", 0),
            s.get("patients_with_positive", 0),
        )
    if "_enrichment" in stats:
        e = stats["_enrichment"]
        logger.info(
            "  Evidence spans: %d found, %d records enriched",
            e.get("evidence_spans_found", 0),
            e.get("records_enriched", 0),
        )
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
