"""Apply reviewed GoldLabel records to the Knowledge Graph.

Reads the gold_label_records_<ts>.jsonl file produced by
build_gold_labels_from_cohort.py, along with an optional reviewed
needs_review CSV where a human has set accepted=yes for chosen candidates.

Steps
-----
1. Merge reviewed concept choices back into the JSONL records.
2. For each entity with a confirmed snomed_concept_id:
   a. Upsert a GoldLabel node to the KG.
   b. Upsert a SurfaceForm -> MAPS_TO -> Concept edge (for future auto-coding).
3. Entities still without a concept (no_match, unreviewed) are skipped but logged.

Usage
-----
    python scripts/cohort/apply_gold_labels_to_kg.py \\
        --records artifacts/cohort_gold/gold_label_records_<ts>.jsonl \\
        [--reviewed artifacts/cohort_gold/needs_review_<ts>.csv] \\
        [--dry-run]
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("apply_gold_labels")


# ---------------------------------------------------------------------------
# Cypher: upsert SurfaceForm and link to Concept
# ---------------------------------------------------------------------------

_UPSERT_SURFACE_FORM = """
MERGE (sf:SurfaceForm {normalizedText: $normalized_text})
ON CREATE SET
    sf.text = $raw_text,
    sf.normalizedText = $normalized_text,
    sf.use_count = 1,
    sf.first_used_at = datetime(),
    sf.created_at = datetime(),
    sf.updated_at = datetime()
ON MATCH SET
    sf.use_count = coalesce(sf.use_count, 0) + 1,
    sf.updated_at = datetime()
WITH sf
MATCH (c {conceptId: $concept_id})
MERGE (sf)-[m:MAPS_TO]->(c)
ON CREATE SET
    m.score = $score,
    m.source = $source,
    m.created_at = datetime()
ON MATCH SET
    m.score = CASE WHEN $score > m.score THEN $score ELSE m.score END,
    m.updated_at = datetime()
RETURN sf.normalizedText AS normalized_text, sf.use_count AS use_count
"""

_UPSERT_GOLD_LABEL = """
MERGE (g:GoldLabel {label_id: $label_id})
ON CREATE SET
    g.text = $text,
    g.entities_json = $entities_json,
    g.quality_score = $quality_score,
    g.source = $source,
    g.verified_by = $verified_by,
    g.verified_at = datetime(),
    g.candidate_id = $candidate_id,
    g.schema_version = $schema_version,
    g.created_at = datetime(),
    g.updated_at = datetime()
ON MATCH SET
    g.text = $text,
    g.entities_json = $entities_json,
    g.quality_score = $quality_score,
    g.source = $source,
    g.verified_by = $verified_by,
    g.verified_at = datetime(),
    g.candidate_id = $candidate_id,
    g.schema_version = $schema_version,
    g.updated_at = datetime()
RETURN g.label_id AS label_id
"""


def _normalize_surface_form(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def _load_reviewed_choices(reviewed_csv: Path) -> dict[tuple, dict]:
    """Returns a dict keyed by (label_id, entity_id, candidate_rank) -> row
    where accepted == 'yes'.
    Also keyed by (label_id, entity_id) -> chosen row (first accepted rank).
    """
    # Key: (label_id, entity_id) -> chosen candidate dict
    choices: dict[tuple[str, str], dict] = {}
    with reviewed_csv.open() as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if str(row.get("accepted", "")).strip().lower() not in ("yes", "y", "1", "true"):
                continue
            key = (row["label_id"], row["entity_id"])
            if key not in choices:  # take first accepted rank
                choices[key] = row
    logger.info("Loaded %d accepted concept choices from %s", len(choices), reviewed_csv)
    return choices


def _build_entities_json(
    entities: list[dict],
    reviewed_choices: dict[tuple[str, str], dict],
    label_id: str,
) -> tuple[list[dict], int, int]:
    """Build the final entities_json list for a GoldLabel.

    Returns (entities_json, written_count, skipped_count).
    """
    written: list[dict] = []
    skipped = 0

    for ent in entities:
        entity_id = ent.get("_entity_id") or ""
        resolution_status = ent.get("_resolution_status", "unknown")

        concept_id = ent.get("snomed_concept_id")
        snomed_term = ent.get("snomed_term")
        snomed_tag = ent.get("semantic_tag") or ent.get("label")

        # Override with reviewed choice if provided
        if resolution_status == "needs_review":
            choice = reviewed_choices.get((label_id, entity_id))
            if choice:
                concept_id = choice.get("concept_id")
                snomed_term = choice.get("preferred_term")
                snomed_tag = choice.get("semantic_tag") or snomed_tag

        # Skip entities with no concept (no_match, unreviewed needs_review)
        if not concept_id and resolution_status not in ("dry_run",):
            skipped += 1
            continue

        kg_ent = {
            "snomed_concept_id": concept_id,
            "snomed_term": snomed_term,
            "start": ent.get("start", -1),
            "end": ent.get("end", -1),
            "assertion": ent.get("assertion", "present"),
            "text": ent.get("text") or "",
            "label": ent.get("label") or "",
            "semantic_tag": snomed_tag or ent.get("label") or "",
        }
        written.append(kg_ent)

    return written, len(written), skipped


def _quality_score(entities: list[dict]) -> float:
    """Compute quality score: fraction of entities with a SNOMED concept."""
    if not entities:
        return 0.0
    with_concept = sum(1 for e in entities if e.get("snomed_concept_id"))
    return round(with_concept / len(entities), 3)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", required=True, help="gold_label_records_<ts>.jsonl path")
    parser.add_argument("--reviewed", help="needs_review_<ts>.csv path (optional)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--source",
        default="cancer_cohort_annotation_v1",
        help="GoldLabel.source value",
    )
    args = parser.parse_args()

    records_path = Path(args.records)
    if not records_path.exists():
        logger.error("Records file not found: %s", records_path)
        sys.exit(1)

    reviewed_choices: dict[tuple[str, str], dict] = {}
    if args.reviewed:
        reviewed_path = Path(args.reviewed)
        if reviewed_path.exists():
            reviewed_choices = _load_reviewed_choices(reviewed_path)
        else:
            logger.warning("Reviewed CSV not found: %s -- proceeding with auto_accept only", reviewed_path)

    # Connect to KG
    if not args.dry_run:
        from neo4j import GraphDatabase

        kg = GraphDatabase.driver(
            os.environ["KNOWLEDGE_GRAPH_NEO4J_URI"],
            auth=(
                os.environ["KNOWLEDGE_GRAPH_NEO4J_USERNAME"],
                os.environ["KNOWLEDGE_GRAPH_NEO4J_PASSWORD"],
            ),
        )
    else:
        kg = None

    records = []
    with records_path.open() as fh:
        for line in fh:
            if line.strip():
                records.append(json.loads(line))

    logger.info("Loaded %d sentence records from %s", len(records), records_path)

    gold_written = 0
    gold_skipped = 0
    surface_forms_written = 0
    entities_written = 0
    entities_skipped = 0

    for rec in records:
        label_id = rec["label_id"]
        candidate_id = rec["candidate_id"]
        text = rec["text"]
        entities = rec.get("entities") or []

        final_ents, written, skipped = _build_entities_json(
            entities, reviewed_choices, label_id
        )
        entities_written += written
        entities_skipped += skipped

        if not final_ents:
            gold_skipped += 1
            continue

        quality = _quality_score(final_ents)
        entities_json_str = json.dumps(final_ents, ensure_ascii=False)

        if args.dry_run:
            gold_written += 1
            logger.debug("DRY RUN: would write label_id=%s ents=%d", label_id, len(final_ents))
            continue

        # Write GoldLabel
        with kg.session() as s:
            s.run(
                _UPSERT_GOLD_LABEL,
                label_id=label_id,
                candidate_id=candidate_id,
                text=text,
                entities_json=entities_json_str,
                quality_score=quality,
                source=args.source,
                verified_by="cancer_cohort_pipeline",
                schema_version=rec.get("schema_version", "cohort_v1"),
            )
        gold_written += 1

        # Upsert SurfaceForm for each entity with a confirmed concept
        for ent in final_ents:
            if not ent.get("snomed_concept_id"):
                continue
            raw_text = ent["text"]
            normalized = _normalize_surface_form(raw_text)
            if not normalized:
                continue
            try:
                with kg.session() as s:
                    s.run(
                        _UPSERT_SURFACE_FORM,
                        raw_text=raw_text,
                        normalized_text=normalized,
                        concept_id=ent["snomed_concept_id"],
                        score=1.0,  # gold-label provenance = max confidence
                        source="cancer_cohort_gold",
                    )
                surface_forms_written += 1
            except Exception:
                logger.warning(
                    "SurfaceForm upsert failed for %r -> %s",
                    raw_text,
                    ent["snomed_concept_id"],
                    exc_info=True,
                )

    if kg:
        kg.close()

    logger.info("=== DONE ===")
    logger.info("GoldLabel nodes written:  %d", gold_written)
    logger.info("GoldLabel nodes skipped:  %d (no entities with concept)", gold_skipped)
    logger.info("Entities written:         %d", entities_written)
    logger.info("Entities skipped:         %d (no_match / unreviewed)", entities_skipped)
    logger.info("SurfaceForm edges:        %d", surface_forms_written)
    if args.dry_run:
        logger.info("(dry-run mode -- nothing written to KG)")


if __name__ == "__main__":
    main()
