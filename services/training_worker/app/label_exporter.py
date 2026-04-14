"""Export GoldLabel nodes from Neo4j into spaCy DocBin format.

Called by the training job runner as Phase 1 of the training pipeline.
Produces train.spacy and dev.spacy files in a temporary directory.

De-id guarantee
---------------
GoldLabel text is de-identified before persistence in the knowledge graph.
This module never reads or writes raw patient identifiers.

Span integrity
--------------
Each entity's start/end is re-derived from its surface text using find_span
before building the DocBin. This corrects stale offsets caused by edits to
sentence text or entity text after original span computation.

Assertion handling
------------------
By default ALL entities are included regardless of assertion value.
The spancat model is trained on (start, end, label) only -- assertion is not
part of the training signal.  ConText detects assertion post-extraction.
Excluding negated spans reduces recall with no benefit to the detector.

Set TRAINING_EXCLUDE_ASSERTIONS (comma-separated) to opt-in to filtering
specific assertion values if needed (e.g. "family_history" for a use-case
where you never want to detect family-history spans).
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import random
from pathlib import Path
from typing import Any

from libs.pipeline.label_filter import (
    DEFAULT_EXCLUDED_ASSERTIONS as _DEFAULT_EXCLUDED_ASSERTIONS,
    filter_and_realign as _filter_and_realign,
    get_excluded_assertions as _get_excluded_assertions,
    realign_entity as _realign_entity,
)

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = "1.0"

# Label normalisation -- maps stored labels to canonical uppercase spaCy labels.
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
    """Convert a single training record to a spaCy Doc with entity spans.

    Entities passed here must already be assertion-filtered and span-realigned.
    Overlapping and co-located spans with different labels are all written to
    doc.spans["sc"] to support multi-label spancat training. The seen_tokens
    dedup guard used by the legacy NER pipeline is intentionally absent.
    """
    doc = nlp.make_doc(text)
    spans = []

    for ent in entities:
        start_char = int(ent.get("start", 0))
        end_char = int(ent.get("end", 0))
        label = _normalise_label(str(ent.get("label", "")))

        if not label or end_char <= start_char:
            continue

        span = doc.char_span(start_char, end_char, label=label, alignment_mode="expand")
        if span is None:
            continue

        spans.append(span)

    doc.spans["sc"] = spans
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
    excluded_assertions = _get_excluded_assertions()
    kg_client = KnowledgeGraphClient()
    records = []
    total_assertion_filtered = 0
    total_span_misaligned = 0
    diagnostics: list[dict[str, Any]] = []
    try:
        patient_client = PatientGraphClient()
        try:
            with patient_client.session() as session:
                rule_rows = [
                    dict(r) for r in session.run(GET_ACTIVE_POST_PROCESSOR_RULES)
                ]
                rules = parse_rules(rule_rows)
                if rules:
                    _log(f"Loaded {len(rules)} active post-processor rules.")
        finally:
            patient_client.close()

        with kg_client.session() as session:
            rows = session.run(GET_ALL_GOLD_LABELS_FOR_EXPORT)
            for row in rows:
                text = str(row["text"] or "")
                entities = json.loads(row["entities_json"] or "[]")
                label_id = str(row.get("label_id") or "")
                source = str(row.get("source") or "")
                if rules:
                    entities = apply_rules_to_entities(text, entities, rules)

                entities, n_assert, n_span = _filter_and_realign(
                    text,
                    entities,
                    excluded_assertions,
                    diagnostics=diagnostics,
                    label_id=label_id,
                    source=source,
                )
                total_assertion_filtered += n_assert
                total_span_misaligned += n_span

                if not entities:
                    continue
                records.append(
                    {
                        "text": text,
                        "entities": entities,
                        "source": source,
                    }
                )
    finally:
        kg_client.close()

    _log(f"Fetched {len(records)} labelled records.")
    if total_assertion_filtered:
        _log(
            f"Assertion filter: {total_assertion_filtered} entities removed "
            f"(excluded: {sorted(excluded_assertions)})."
        )
    if total_span_misaligned:
        _log(
            f"Span realignment: {total_span_misaligned} entities dropped "
            "(surface text not found in sentence)."
        )

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
        _log(f"Warning: {skipped} records skipped during DocBin conversion.")

    exported_at = datetime.datetime.utcnow().isoformat()
    meta = {
        "exported_at": exported_at,
        "total_records": len(records),
        "train_records": len(train_records),
        "dev_records": len(dev_records),
        "skipped": skipped,
        "assertion_filtered": total_assertion_filtered,
        "span_misaligned": total_span_misaligned,
        "excluded_assertions": sorted(excluded_assertions),
        "label_set": sorted(all_labels),
        "train_ratio": train_ratio,
        "seed": seed,
        "schema_version": _SCHEMA_VERSION,
    }
    (output_dir / "export_meta.json").write_text(json.dumps(meta, indent=2))

    diag_payload = {
        "exported_at": exported_at,
        "excluded_assertions": sorted(excluded_assertions),
        "summary": {
            "assertion_filtered_count": total_assertion_filtered,
            "span_misaligned_count": total_span_misaligned,
        },
        "assertion_filtered": [
            d for d in diagnostics if d["reason"] == "assertion_filtered"
        ],
        "span_misaligned": [d for d in diagnostics if d["reason"] == "span_misaligned"],
    }
    (output_dir / "export_diagnostics.json").write_text(
        json.dumps(diag_payload, indent=2)
    )
    _log(f"DocBins written to {output_dir}")

    return {
        "total": len(records),
        "train_count": len(train_records),
        "dev_count": len(dev_records),
        "skipped": skipped,
        "assertion_filtered": total_assertion_filtered,
        "span_misaligned": total_span_misaligned,
        "labels_found": sorted(all_labels),
        "label_set": sorted(all_labels),
        "exported_at": exported_at,
        "train_path": str(train_path),
        "dev_path": str(dev_path),
    }
