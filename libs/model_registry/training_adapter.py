"""Training artifact → runtime DTO adapter.

This module is the explicit boundary between the NER training pipeline (which
owns raw training JSON files under exports/) and the coding runtime (which owns
ExtractionItem and DOCUMENTS writes).

Rules
-----
- The runtime MUST NOT import raw training JSON structures directly.
- The training pipeline MUST NOT import ExtractionItem.
- All conversion goes through TrainingAdapter.to_extraction_items().
- Any schema mismatch raises AdapterError so it surfaces early.

Training record format (produced by ner_training_set_refactor plan)
--------------------------------------------------------------------
{
  "text": "Referred for suspected colorectal cancer",
  "entities": [
    {
      "start": 12, "end": 40,
      "label": "FAST_TRACK_REFERRAL",
      "text": "suspected colorectal cancer",
      "assertion": "present",
      "normalized": "Fast track referral for suspected colorectal cancer",
      "confidence": 1.0
    }
  ],
  "sentence_id": "s001",
  "schema_version": "1.0",
  "deid_version": "1.0",
  "label_mapping_version": "1.0"
}
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from services.coding_worker.app.pipeline.extractor_contract import (
    CONTRACT_VERSION,
    ExtractionItem,
)

logger = logging.getLogger(__name__)

_SUPPORTED_SCHEMA_VERSIONS = frozenset({"1.0"})
_SUPPORTED_DEID_VERSIONS = frozenset({"1.0"})
_SUPPORTED_LABEL_VERSIONS = frozenset({"1.0"})

_VALID_ASSERTIONS = frozenset(
    {"present", "absent", "possible", "historical", "hypothetical", "family"}
)

_LABEL_TO_SEMANTIC_TAG: dict[str, str] = {
    "FAST_TRACK_REFERRAL": "finding",
    "CANCER_DIAGNOSIS": "disease",
    "CANCER_TREATMENT": "procedure",
    "CANCER_EXCLUSION": "finding",
    "SYMPTOM": "finding",
    "COMORBIDITY": "disease",
    "INVESTIGATION": "procedure",
    "OBSERVABLE": "observableentity",
}


class AdapterError(ValueError):
    """Raised when the training record cannot be safely converted."""


@dataclass
class TrainingRecord:
    """Parsed training record from the NER training dataset."""
    text: str
    entities: list[dict[str, Any]]
    sentence_id: str
    schema_version: str
    deid_version: str
    label_mapping_version: str
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TrainingRecord":
        return cls(
            text=d.get("text", ""),
            entities=d.get("entities", []),
            sentence_id=d.get("sentence_id", ""),
            schema_version=str(d.get("schema_version", "")),
            deid_version=str(d.get("deid_version", "")),
            label_mapping_version=str(d.get("label_mapping_version", "")),
            raw=d,
        )


class TrainingAdapter:
    """Converts training records to runtime ExtractionItem instances.

    Validates version compatibility before conversion.  Raises AdapterError
    if any version is unsupported to prevent silent schema drift.
    """

    def __init__(
        self,
        source_tag: str = "training_label",
        model_name: str = "training_corpus",
        model_version: str = "1.0",
    ) -> None:
        self._source_tag = source_tag
        self._model_name = model_name
        self._model_version = model_version

    def validate_record(self, record: TrainingRecord) -> None:
        """Raise AdapterError if the record's versions are unsupported."""
        if record.schema_version not in _SUPPORTED_SCHEMA_VERSIONS:
            raise AdapterError(
                f"TrainingAdapter: unsupported schema_version={record.schema_version!r}"
            )
        if record.deid_version not in _SUPPORTED_DEID_VERSIONS:
            raise AdapterError(
                f"TrainingAdapter: unsupported deid_version={record.deid_version!r}"
            )
        if record.label_mapping_version not in _SUPPORTED_LABEL_VERSIONS:
            raise AdapterError(
                f"TrainingAdapter: unsupported label_mapping_version={record.label_mapping_version!r}"
            )

    def to_extraction_items(self, record: TrainingRecord) -> list[ExtractionItem]:
        """Convert a TrainingRecord to a list of ExtractionItem.

        Validates version compatibility.  Returns an empty list if the record
        has no entities.  Individual entity conversion errors are logged and
        skipped rather than failing the whole record.

        Args:
            record: Parsed training record.

        Returns:
            List of ExtractionItem conforming to CONTRACT_VERSION.

        Raises:
            AdapterError: If the record schema/deid/label versions are unsupported.
        """
        self.validate_record(record)
        items: list[ExtractionItem] = []
        for ent in record.entities:
            try:
                item = self._convert_entity(ent, record.sentence_id)
                items.append(item)
            except Exception as exc:
                logger.warning(
                    "TrainingAdapter: skipping entity in sentence=%s: %s",
                    record.sentence_id, exc,
                )
        return items

    def _convert_entity(self, ent: dict[str, Any], sentence_id: str) -> ExtractionItem:
        label = str(ent.get("label", "")).upper()
        semantic_tag = _LABEL_TO_SEMANTIC_TAG.get(label, "finding")

        assertion = str(ent.get("assertion", "present")).lower()
        if assertion not in _VALID_ASSERTIONS:
            assertion = "present"

        confidence = float(ent.get("confidence", 1.0))
        text = str(ent.get("text", ""))
        if not text:
            raise AdapterError("entity text is empty")

        return ExtractionItem(
            sentence_id=sentence_id,
            text=text,
            span_start=int(ent.get("start", 0)),
            span_end=int(ent.get("end", 0)),
            semantic_tag=semantic_tag,
            assertion=assertion,
            confidence=confidence,
            normalized=str(ent.get("normalized", text)),
            source_meta={"training_label": label},
            relations=[],
            source=self._source_tag,
            model_name=self._model_name,
            model_version=self._model_version,
            contract_version=CONTRACT_VERSION,
        )

    @classmethod
    def from_jsonl(
        cls,
        lines: list[str],
        source_tag: str = "training_label",
        model_name: str = "training_corpus",
        model_version: str = "1.0",
    ) -> list[ExtractionItem]:
        """Batch convert JSONL training lines to ExtractionItems.

        Skips invalid lines with a warning rather than aborting.
        """
        import json

        adapter = cls(
            source_tag=source_tag,
            model_name=model_name,
            model_version=model_version,
        )
        results: list[ExtractionItem] = []
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                record = TrainingRecord.from_dict(d)
                results.extend(adapter.to_extraction_items(record))
            except AdapterError as exc:
                logger.warning("TrainingAdapter: line %d AdapterError: %s", i, exc)
            except Exception as exc:
                logger.warning("TrainingAdapter: line %d parse error: %s", i, exc)
        return results
