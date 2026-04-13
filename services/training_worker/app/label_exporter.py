"""Export GoldLabel nodes from Neo4j into spaCy DocBin format.

Called by the training job runner as Phase 1 of the training pipeline.
Produces train.spacy and dev.spacy files in a temporary directory.

De-id guarantee
---------------
GoldLabel text is de-identified before persistence in the knowledge graph.
This module never reads or writes raw patient identifiers.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import random
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = "1.0"

# Label normalisation — maps stored labels to canonical uppercase spaCy labels.
_LABEL_MAP: dict[str, str] = {
    "disorder": "DISORDER",
    "finding": "FINDING",
    "procedure": "PROCEDURE",
    "observable_entity": "OBSERVABLE",
    "qualifier_value": "QUALIFIER",
    "substance": "SUBSTANCE",
    "medicinal_product": "MEDICINAL_PRODUCT",
    "clinical_drug": "CLINICAL_DRUG",
    "situation": "SITUATION",
    "event": "EVENT",
    "body_structure": "BODY_STRUCTURE",
    "tumor_staging": "TUMOR_STAGING",
    "assessment_scale": "ASSESSMENT_SCALE",
    "staging_scale": "STAGING_SCALE",
    "regime_therapy": "REGIME_THERAPY",
    "record_artifact": "RECORD_ARTIFACT",
    "physical_object": "PHYSICAL_OBJECT",
    "organism": "ORGANISM",
    "morphologic_abnormality": "MORPHOLOGIC_ABNORMALITY",
    "occupation": "OCCUPATION",
    "attribute": "ATTRIBUTE",
    "environment": "ENVIRONMENT",
    "product": "PRODUCT",
    "X_TEMPORAL": "TEMPORAL",
    "X_DOSAGE": "DOSAGE",
    "X_FREQUENCY": "FREQUENCY",
    "X_ROUTE": "ROUTE",
}


def _normalise_label(raw: str) -> str:
    return _LABEL_MAP.get(raw, raw.upper())


def _record_to_spacy_doc(nlp, text: str, entities: list[dict[str, Any]]):
    """Convert a single training record to a spaCy Doc with entity spans."""
    doc = nlp.make_doc(text)
    spans = []
    seen_tokens: set[int] = set()

    for ent in entities:
        start_char = int(ent.get("start", 0))
        end_char = int(ent.get("end", 0))
        label = _normalise_label(str(ent.get("label", "")))

        if not label or end_char <= start_char:
            continue

        span = doc.char_span(start_char, end_char, label=label, alignment_mode="expand")
        if span is None:
            continue

        # Skip overlapping spans
        token_range = frozenset(range(span.start, span.end))
        if token_range & seen_tokens:
            continue
        seen_tokens |= token_range
        spans.append(span)

    doc.ents = spans
    return doc


def export_labels(
    output_dir: Path,
    *,
    train_ratio: float = 0.8,
    seed: int = 42,
    log_fn=None,
) -> dict[str, Any]:
    """Fetch all exportable GoldLabel nodes and write train/dev DocBins.

    Args:
        output_dir: Directory to write train.spacy, dev.spacy, meta.json.
        train_ratio: Fraction of records to use for training (rest = dev).
        seed: Random seed for reproducible split.
        log_fn: Optional callable(str) for progress logging.

    Returns:
        dict with keys: total, train_count, dev_count, labels_found,
        train_path, dev_path.

    Raises:
        ValueError: If fewer records than TRAINING_MIN_LABEL_COUNT.
    """
    import spacy
    from spacy.tokens import DocBin

    from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient
    from libs.cypher.gold_label_queries import GET_ALL_GOLD_LABELS_FOR_EXPORT
    from libs.cypher.post_processor_rule_queries import GET_ACTIVE_POST_PROCESSOR_RULES
    from libs.ner.post_processor_rules import apply_rules_to_entities, parse_rules

    min_count = int(os.getenv("TRAINING_MIN_LABEL_COUNT", "50"))

    def _log(msg: str) -> None:
        logger.info(msg)
        if log_fn:
            log_fn(msg)

    _log("Phase 1/5 — Fetching GoldLabel records from Neo4j…")
    kg_client = KnowledgeGraphClient()
    records = []
    try:
        patient_client = PatientGraphClient()
        try:
            with patient_client.session() as session:
                rule_rows = [dict(r) for r in session.run(GET_ACTIVE_POST_PROCESSOR_RULES)]
                rules = parse_rules(rule_rows)
                if rules:
                    _log(f"Loaded {len(rules)} active post-processor rules.")
        finally:
            patient_client.close()

        with kg_client.session() as session:
            rows = session.run(GET_ALL_GOLD_LABELS_FOR_EXPORT)
            for row in rows:
                entities = json.loads(row["entities_json"] or "[]")
                if rules:
                    entities = apply_rules_to_entities(
                        str(row["text"] or ""), entities, rules
                    )
                if not entities:
                    continue
                records.append(
                    {
                        "text": row["text"] or "",
                        "entities": entities,
                        "source": row.get("source", ""),
                    }
                )
    finally:
        kg_client.close()

    _log(f"Fetched {len(records)} labelled records.")

    if len(records) < min_count:
        raise ValueError(
            f"Only {len(records)} GoldLabel records — minimum is {min_count}. "
            "Add more verified gold labels before training."
        )

    # Deterministic split
    random.seed(seed)
    shuffled = records[:]
    random.shuffle(shuffled)
    split_idx = max(1, int(len(shuffled) * train_ratio))
    train_records = shuffled[:split_idx]
    dev_records = shuffled[split_idx:] or shuffled[:1]  # at least 1 dev record

    _log(f"Split: {len(train_records)} train / {len(dev_records)} dev")

    nlp = spacy.blank("en")

    output_dir.mkdir(parents=True, exist_ok=True)
    train_bin = DocBin()
    dev_bin = DocBin()
    all_labels: set[str] = set()
    skipped = 0

    # Single pass over all records: collect labels and build DocBins together.
    for is_train, rec in [(True, r) for r in train_records] + [
        (False, r) for r in dev_records
    ]:
        for ent in rec["entities"]:
            all_labels.add(_normalise_label(str(ent.get("label", ""))))
        try:
            doc = _record_to_spacy_doc(nlp, rec["text"], rec["entities"])
            (train_bin if is_train else dev_bin).add(doc)
        except Exception:
            skipped += 1

    train_path = output_dir / "train.spacy"
    dev_path = output_dir / "dev.spacy"
    train_bin.to_disk(train_path)
    dev_bin.to_disk(dev_path)

    if skipped:
        _log(f"Warning: {skipped} records skipped due to span alignment issues.")

    meta = {
        "exported_at": datetime.datetime.utcnow().isoformat(),
        "total_records": len(records),
        "train_records": len(train_records),
        "dev_records": len(dev_records),
        "skipped": skipped,
        "label_set": sorted(all_labels),
        "train_ratio": train_ratio,
        "seed": seed,
        "schema_version": _SCHEMA_VERSION,
    }
    (output_dir / "export_meta.json").write_text(json.dumps(meta, indent=2))
    _log(f"DocBins written to {output_dir}")

    exported_at = datetime.datetime.utcnow().isoformat()
    return {
        "total": len(records),
        "train_count": len(train_records),
        "dev_count": len(dev_records),
        "skipped": skipped,
        "labels_found": sorted(all_labels),
        "label_set": sorted(all_labels),
        "exported_at": exported_at,
        "train_path": str(train_path),
        "dev_path": str(dev_path),
    }
