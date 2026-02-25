"""Diagnostic script for V3 extraction prompt tuning.

Runs the V3 LLM extractor against real patient encounters and prints
detailed extraction output for human review ("eyeball tuning").

Usage:
    python scripts/diagnose_v3_extraction.py --patient-id 4202301609 --max-encounters 5
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_PATH = ROOT / "services" / "api"
if str(API_PATH) not in sys.path:
    sys.path.insert(0, str(API_PATH))

from app.db.neo4j_client import CodingGraphClient, PatientGraphClient
from app.services.term_patcher import normalize_surface
from app.services.v3.coding_resolver import CodingResolver
from app.services.v3.llm_extractor import LLMExtractor
from app.services.v3.sentence_splitter import SentenceSplitter

_BATCH_SIZE = 5


def _load_deidentify():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scripts.training_v2_utils import deidentify_text
    return deidentify_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--patient-id", default="4202301609",
        help="Patient ID to diagnose (default: 4202301609).",
    )
    parser.add_argument(
        "--max-encounters", type=int, default=5,
        help="Max encounters to process (default: 5).",
    )
    parser.add_argument(
        "--no-resolve", action="store_true",
        help="Skip SNOMED resolution (faster, extraction only).",
    )
    parser.add_argument(
        "--raw-json", action="store_true",
        help="Also print the raw JSON from each LLM call.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    deidentify_text = _load_deidentify()

    patient_client = PatientGraphClient()
    coding_client = CodingGraphClient() if not args.no_resolve else None
    resolver = CodingResolver() if not args.no_resolve else None

    import os
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "eu-west-2"
    model_id = os.getenv("AWS_SMALL_MODEL", "unconfigured")
    extractor = LLMExtractor(model_id=model_id, region=region)
    splitter = SentenceSplitter()

    print("=" * 80)
    print("V3 EXTRACTION DIAGNOSTIC")
    print("=" * 80)
    print(f"  Patient ID:       {args.patient_id}")
    print(f"  Max encounters:   {args.max_encounters}")
    print(f"  Model ID:         {model_id}")
    print(f"  LLM enabled:      {extractor.enabled}")
    print(f"  Sentence splitter: {splitter.mode}")
    print(f"  SNOMED resolution: {'yes' if resolver else 'skip'}")
    print()

    with patient_client.session() as session:
        result = session.run(
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
            "WHERE toString(p.id) = $pid "
            "RETURN e.id AS encounter_id, toString(e.date) AS date, e.text AS text "
            "ORDER BY e.date LIMIT $limit",
            pid=args.patient_id,
            limit=args.max_encounters,
        )
        encounters = [dict(r) for r in result]

    if not encounters:
        print(f"ERROR: No encounters found for patient {args.patient_id}")
        patient_client.close()
        return 1

    print(f"Found {len(encounters)} encounters\n")

    total_terms = 0
    total_resolved = 0
    total_span_aligned = 0
    total_abbreviation_expanded = 0
    assertion_counts: Counter[str] = Counter()
    tag_counts: Counter[str] = Counter()

    for enc_idx, encounter in enumerate(encounters):
        encounter_id = encounter.get("encounter_id")
        encounter_text = str(encounter.get("text") or "")
        date = encounter.get("date", "?")

        deidentified = deidentify_text(encounter_text)
        sentences = splitter.split(deidentified)

        print("-" * 80)
        print(f"ENCOUNTER {enc_idx + 1}/{len(encounters)}  |  ID: {encounter_id}  |  Date: {date}")
        print(f"  Sentences: {len(sentences)}  |  Chars: {len(deidentified)}")
        print("-" * 80)
        print()
        print("  DEIDENTIFIED TEXT:")
        for line in deidentified.split("\n"):
            print(f"    {line}")
        print()

        all_terms = []
        for batch_start in range(0, len(sentences), _BATCH_SIZE):
            batch = sentences[batch_start : batch_start + _BATCH_SIZE]
            extracted = extractor.extract_batch(deidentified, batch)
            all_terms.extend(extracted)

        if resolver and coding_client and all_terms:
            lookup_texts = [t.lookup_term for t in all_terms]
            with coding_client.session() as coding_session:
                candidates_map = resolver.resolve_candidates(
                    lookup_texts, neo4j_session=coding_session,
                )
        else:
            candidates_map = {}

        for sentence in sentences:
            sentence_terms = [t for t in all_terms if t.sentence_id == sentence.sentence_id]
            print(f"  [{sentence.sentence_id}] \"{sentence.text}\"")

            if not sentence_terms:
                print("    (no terms extracted)")
            else:
                for term in sentence_terms:
                    total_terms += 1
                    assertion_counts[term.assertion] += 1
                    tag_counts[term.semantic_tag] += 1

                    expanded = term.text != term.lookup_term
                    if expanded:
                        total_abbreviation_expanded += 1

                    span_ok = sentence.text.lower().find(term.text.lower()) >= 0
                    if span_ok:
                        total_span_aligned += 1

                    candidates = candidates_map.get(term.lookup_term, [])
                    resolved = len(candidates) > 0
                    if resolved:
                        total_resolved += 1
                        best = candidates[0]
                        snomed_info = f"-> {best.snomed_concept_id} ({best.snomed_term})"
                    else:
                        snomed_info = "-> [NO MATCH]"

                    flags = []
                    if expanded:
                        flags.append("EXPANDED")
                    if not span_ok:
                        flags.append("SPAN_MISS")
                    if not resolved and resolver:
                        flags.append("UNRESOLVED")
                    flag_str = f"  [{', '.join(flags)}]" if flags else ""

                    text_display = term.text
                    if expanded:
                        text_display = f"{term.text} -> {term.lookup_term}"

                    print(
                        f"    * {text_display}"
                        f"  [{term.semantic_tag}]"
                        f"  [{term.assertion}]"
                        f"  {snomed_info if resolver else ''}"
                        f"{flag_str}"
                    )
            print()

    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"  Encounters processed:    {len(encounters)}")
    print(f"  Total terms extracted:   {total_terms}")
    if resolver:
        rate = (total_resolved / total_terms * 100) if total_terms else 0
        print(f"  SNOMED resolved:         {total_resolved}/{total_terms} ({rate:.0f}%)")
    span_rate = (total_span_aligned / total_terms * 100) if total_terms else 0
    print(f"  Span-aligned:            {total_span_aligned}/{total_terms} ({span_rate:.0f}%)")
    print(f"  Abbreviation expansions: {total_abbreviation_expanded}")
    print()
    print("  Assertion distribution:")
    for assertion, count in assertion_counts.most_common():
        print(f"    {assertion:15s}  {count}")
    print()
    print("  Semantic tag distribution:")
    for tag, count in tag_counts.most_common():
        print(f"    {tag:20s}  {count}")
    print()

    patient_client.close()
    if coding_client:
        coding_client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
