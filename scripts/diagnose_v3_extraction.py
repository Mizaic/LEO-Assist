"""Diagnostic script for V3 extraction prompt tuning.

Runs the V3 LLM extractor against real patient encounters and prints
detailed extraction output for human review ("eyeball tuning").

Usage:
    python scripts/diagnose_v3_extraction.py --patient-id 4202301609 --max-encounters 15
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_PATH = ROOT / "services" / "api"
if str(API_PATH) not in sys.path:
    sys.path.insert(0, str(API_PATH))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-40s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("PyRuSH").setLevel(logging.WARNING)
logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("transformers").setLevel(logging.WARNING)

# PyRuSH uses loguru, not stdlib logging - suppress its DEBUG spam
try:
    from loguru import logger as _loguru_logger
    _loguru_logger.disable("PyRuSH")
except ImportError:
    pass

# Suppress sentence-transformers model loading progress bars
os.environ.setdefault("SENTENCE_TRANSFORMERS_VERBOSITY", "warning")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "warning")

from app.db.neo4j_client import CodingGraphClient, PatientGraphClient
from app.services.v3.coding_resolver import CodingResolver
from app.services.v3.llm_extractor import ExtractionError, LLMExtractor
from app.services.v3.llm_usage import LLMCostConfig, LLMUsage
from app.services.v3.sentence_splitter import SentenceSplitter, deduplicate_lines

log = logging.getLogger("diagnose_v3")

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
        "--max-encounters", type=int, default=15,
        help="Max encounters to process (default: 15).",
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

    log.info("Connecting to Neo4j...")
    patient_client = PatientGraphClient()
    coding_client = CodingGraphClient() if not args.no_resolve else None

    embedder = None
    if not args.no_resolve:
        try:
            from scripts.embedding_utils import TextEmbedder, load_vector_settings
            settings = load_vector_settings()
            embedder = TextEmbedder(settings)
            log.info("Vector embedder loaded: model=%s", settings.model_name)
        except Exception:
            log.info("Vector embedder unavailable - using exact+fulltext only")

    resolver = CodingResolver(embedder=embedder) if not args.no_resolve else None

    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "eu-west-2"
    model_id = os.getenv("AWS_SMALL_MODEL", "unconfigured")
    log.info("Initialising LLM extractor (model=%s, region=%s)", model_id, region)
    extractor = LLMExtractor(model_id=model_id, region=region)
    splitter = SentenceSplitter()
    cost_config = LLMCostConfig.from_env()
    total_usage = LLMUsage.zero()

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

    log.info("Fetching encounters for patient %s...", args.patient_id)
    with patient_client.session() as session:
        result = session.run(
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
            "WHERE toString(p.id) = $pid "
            "RETURN e.id AS encounter_id, toString(e.date) AS date, e.text AS text "
            "ORDER BY e.date DESC LIMIT $limit",
            pid=args.patient_id,
            limit=args.max_encounters,
        )
        encounters = [dict(r) for r in result]

    if not encounters:
        log.error("No encounters found for patient %s", args.patient_id)
        patient_client.close()
        return 1

    log.info("Found %d encounters", len(encounters))
    print(f"Found {len(encounters)} encounters\n")

    total_terms = 0
    total_resolved = 0
    total_span_aligned = 0
    total_abbreviation_expanded = 0
    total_extraction_failures = 0
    assertion_counts: Counter[str] = Counter()
    tag_counts: Counter[str] = Counter()

    for enc_idx, encounter in enumerate(encounters):
        encounter_id = encounter.get("encounter_id")
        encounter_text = str(encounter.get("text") or "")
        date = encounter.get("date", "?")

        log.info(
            "Processing encounter %d/%d  [%s]  date=%s  (%d chars)",
            enc_idx + 1, len(encounters), encounter_id, date, len(encounter_text),
        )

        log.info("De-identifying text...")
        deidentified = deidentify_text(encounter_text)
        deidentified = deduplicate_lines(deidentified)
        log.info("Splitting into sentences...")
        sentences = splitter.split(deidentified)
        log.info("Got %d sentences", len(sentences))

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
        encounter_usage = LLMUsage.zero()
        extraction_failed = False
        for batch_start in range(0, len(sentences), _BATCH_SIZE):
            batch = sentences[batch_start : batch_start + _BATCH_SIZE]
            batch_ids = [s.sentence_id for s in batch]
            log.info("Sending batch %s to LLM...", batch_ids)
            try:
                extracted, batch_usage = extractor.extract_batch(deidentified, batch)
                encounter_usage += batch_usage
                log.info("LLM returned %d terms (%d tokens)", len(extracted), batch_usage.total_tokens)
                all_terms.extend(extracted)
            except ExtractionError as exc:
                log.error("Extraction failed for batch %s: %s", batch_ids, exc)
                extraction_failed = True

        total_usage += encounter_usage

        if extraction_failed:
            total_extraction_failures += 1
            print("  *** EXTRACTION FAILED - see log above ***\n")
            continue

        if resolver and coding_client and all_terms:
            lookup_texts = [t.lookup_term for t in all_terms]
            expected_tags = {t.lookup_term: t.semantic_tag for t in all_terms}
            log.info("Sending %d terms for SNOMED resolution...", len(lookup_texts))
            with coding_client.session() as coding_session:
                candidates_map = resolver.resolve_candidates(
                    lookup_texts, neo4j_session=coding_session,
                    expected_tags=expected_tags,
                )
            log.info("SNOMED resolution complete")
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
    print(f"  Extraction failures:     {total_extraction_failures}")
    print(f"  Total terms extracted:   {total_terms}")
    if resolver:
        rate = (total_resolved / total_terms * 100) if total_terms else 0
        print(f"  SNOMED resolved:         {total_resolved}/{total_terms} ({rate:.0f}%)")
    span_rate = (total_span_aligned / total_terms * 100) if total_terms else 0
    print(f"  Span-aligned:            {total_span_aligned}/{total_terms} ({span_rate:.0f}%)")
    print(f"  Abbreviation expansions: {total_abbreviation_expanded}")
    print()
    print("  LLM Usage:")
    print(f"    API calls:             {total_usage.llm_calls}")
    print(f"    Input tokens:          {total_usage.input_tokens:,}")
    print(f"    Output tokens:         {total_usage.output_tokens:,}")
    print(f"    Cached input tokens:   {total_usage.cached_input_tokens:,}")
    print(f"    Total tokens:          {total_usage.total_tokens:,}")
    cost = total_usage.cost_usd(cost_config)
    print(f"    Estimated cost:        ${cost:.4f}")
    if len(encounters) > 0 and cost > 0:
        projected_300 = cost * (300 / len(encounters))
        print(f"    Projected (300 enc):   ${projected_300:.2f}")
    if total_usage.llm_calls > 0:
        avg_in = total_usage.input_tokens / total_usage.llm_calls
        avg_out = total_usage.output_tokens / total_usage.llm_calls
        print(f"    Avg tokens/call:       {avg_in:.0f} in / {avg_out:.0f} out")
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
