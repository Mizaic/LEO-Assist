"""Model training label store for spaCy NER retraining corpus.

This store is SEPARATE from ``libs/prompts/few_shot_builder.py``.

Separation contract
-------------------
``few_shot_builder``       — LLM prompt injection only.  Used by encounter
                             classification and exclusion detector LLM stages.
                             Keys off human-reviewed AnchorReview / ClassVotes.

``model_training_labels``  — spaCy retraining corpus.  Used by the NER training
                             pipeline (ner_training_set_refactor plan).
                             Keys off approved EncounterCandidate sentences.

These two stores must NEVER be merged.  LLM few-shot examples reflect
reviewer preference; model training labels reflect ground-truth annotation
quality.  Conflating them corrupts both.

Usage::

    from libs.prompts.model_training_labels import fetch_training_labels

    labels = fetch_training_labels(limit=5000)
    # labels is a list of TrainingLabelRecord
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

_FETCH_APPROVED_LABELS_QUERY = """
MATCH (c:EncounterCandidate)
WHERE c.approval_status = 'approved'
  AND c.sentences_json IS NOT NULL
RETURN c.candidate_id     AS candidate_id,
       c.encounter_id     AS encounter_id,
       c.patient_id       AS patient_id,
       c.sentences_json   AS sentences_json,
       c.extraction_source AS extraction_source,
       c.contract_version  AS contract_version,
       c.extraction_model_name    AS model_name,
       c.extraction_model_version AS model_version,
       c.updated_at        AS updated_at
ORDER BY c.updated_at DESC
LIMIT $limit
"""


@dataclass
class TrainingLabelRecord:
    """A single approved candidate record as a training label."""

    candidate_id: str
    encounter_id: str
    patient_id: str
    sentences_json: str
    extraction_source: str = ""
    contract_version: str = ""
    model_name: str = ""
    model_version: str = ""
    updated_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        import json as _json

        return {
            "candidate_id": self.candidate_id,
            "encounter_id": self.encounter_id,
            "patient_id": self.patient_id,
            "sentences": _json.loads(self.sentences_json or "[]"),
            "extraction_source": self.extraction_source,
            "contract_version": self.contract_version,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "updated_at": self.updated_at,
        }


def fetch_training_labels(
    limit: int = 5000,
    client=None,
) -> list[TrainingLabelRecord]:
    """Fetch approved EncounterCandidate records as NER training labels.

    Only returns candidates that have been reviewed and approved by a human.
    These labels feed the spaCy retraining pipeline, NOT LLM few-shot prompts.

    Args:
        limit: Maximum number of candidates to return.
        client: Optional PatientGraphClient (creates one if not supplied).

    Returns:
        List of TrainingLabelRecord.
    """
    from libs.neo4j_client.client import PatientGraphClient

    owned_client = client is None
    client = client or PatientGraphClient()

    try:
        with client.session() as session:
            rows = session.run(_FETCH_APPROVED_LABELS_QUERY, limit=limit)
            records = [
                TrainingLabelRecord(
                    candidate_id=str(r["candidate_id"] or ""),
                    encounter_id=str(r["encounter_id"] or ""),
                    patient_id=str(r["patient_id"] or ""),
                    sentences_json=str(r["sentences_json"] or "[]"),
                    extraction_source=str(r["extraction_source"] or ""),
                    contract_version=str(r["contract_version"] or ""),
                    model_name=str(r["model_name"] or ""),
                    model_version=str(r["model_version"] or ""),
                    updated_at=str(r["updated_at"]) if r["updated_at"] else None,
                )
                for r in rows
            ]
        logger.info(
            "fetch_training_labels: fetched %d approved labels (limit=%d)",
            len(records),
            limit,
        )
        return records
    finally:
        if owned_client:
            client.close()
