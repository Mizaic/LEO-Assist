"""Helper for upserting TrainingLabel nodes into Neo4j.

All learning sources (HITL resolution, coding-UX corrections, bulk script
imports) call ``upsert_training_label``.  This is the single write path so
de-identification, deduplication, and precision-gate checks are applied
consistently regardless of origin.

De-identification contract
--------------------------
- ``patient_id`` is hashed (SHA-256) before storage.
- ``text`` must already be de-identified by the caller (encounter text
  passes through the de-id pipeline before reaching this layer).
- Entity span text is derived from the stored ``text`` — no separate
  de-id needed for spans.

Deduplication key
-----------------
``label_id = SHA-256(encounter_id + canonical_entities_fingerprint)``

A record with the same encounter and identical entity spans is idempotent.
A correction to existing spans on the same encounter produces a new
``label_id`` (old record remains with ``include=true``; callers can
exclude the superseded version if desired).
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Optional

from libs.cypher.training_label_queries import UPSERT_TRAINING_LABEL

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0"


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _entity_fingerprint(entities: list[dict[str, Any]]) -> str:
    """Stable fingerprint for a list of entity dicts (order-independent)."""
    normalised = sorted(
        (e.get("label", ""), e.get("start", 0), e.get("end", 0), e.get("text", ""))
        for e in entities
    )
    return json.dumps(normalised, separators=(",", ":"))


def make_label_id(encounter_id: str, entities: list[dict[str, Any]]) -> str:
    fingerprint = encounter_id + _entity_fingerprint(entities)
    return _hash(fingerprint)


def upsert_training_label(
    *,
    encounter_id: str,
    patient_id: str,
    text: str,
    entities: list[dict[str, Any]],
    source: str,
    source_ref: str = "",
    quality_score: float = 1.0,
    client=None,
) -> str:
    """Write or update a TrainingLabel node in Neo4j.

    Args:
        encounter_id:  Encounter identifier (not hashed — used as graph key).
        patient_id:    Raw patient identifier — hashed before storage.
        text:          De-identified sentence text.
        entities:      List of canonical entity dicts with keys:
                       text, label, start, end, (optional) confidence.
        source:        One of "hitl_approval", "coding_correction",
                       "anchor_mining", "seed".
        source_ref:    Candidate ID, task ID, or script run ID for audit.
        quality_score: Precision-gate score (0.0–1.0); callers may pass
                       the score from ``libs.ner.precision_gates``.
        client:        Optional ``PatientGraphClient`` (creates one if absent).

    Returns:
        The ``label_id`` (SHA-256 hex string) of the upserted node.
    """
    from libs.neo4j_client.client import PatientGraphClient

    label_id = make_label_id(encounter_id, entities)
    patient_id_hash = _hash(patient_id)
    entities_json = json.dumps(entities, default=str)

    owned_client = client is None
    client = client or PatientGraphClient()
    try:
        with client.session() as session:
            session.run(
                UPSERT_TRAINING_LABEL,
                label_id=label_id,
                encounter_id=encounter_id,
                patient_id_hash=patient_id_hash,
                text=text,
                entities_json=entities_json,
                source=source,
                source_ref=source_ref,
                quality_score=quality_score,
                schema_version=SCHEMA_VERSION,
            )
        logger.debug(
            "upsert_training_label: %s source=%s ref=%s entities=%d",
            label_id[:8], source, source_ref, len(entities),
        )
    finally:
        if owned_client:
            client.close()

    return label_id


def bulk_upsert_training_labels(
    records: list[dict[str, Any]],
    *,
    source: str,
    source_ref: str = "",
    client=None,
) -> list[str]:
    """Upsert multiple TrainingLabel nodes in a single session.

    Each record must have: encounter_id, patient_id, text, entities.
    Optional: quality_score.

    Returns list of label_ids in the same order as input records.
    """
    from libs.neo4j_client.client import PatientGraphClient

    owned_client = client is None
    client = client or PatientGraphClient()
    label_ids: list[str] = []
    try:
        with client.session() as session:
            for rec in records:
                enc_id = rec["encounter_id"]
                entities = rec.get("entities", [])
                label_id = make_label_id(enc_id, entities)
                session.run(
                    UPSERT_TRAINING_LABEL,
                    label_id=label_id,
                    encounter_id=enc_id,
                    patient_id_hash=_hash(rec.get("patient_id", "")),
                    text=rec.get("text", ""),
                    entities_json=json.dumps(entities, default=str),
                    source=source,
                    source_ref=source_ref,
                    quality_score=float(rec.get("quality_score", 1.0)),
                    schema_version=SCHEMA_VERSION,
                )
                label_ids.append(label_id)
    finally:
        if owned_client:
            client.close()

    logger.info(
        "bulk_upsert_training_labels: %d records source=%s ref=%s",
        len(label_ids), source, source_ref,
    )
    return label_ids
