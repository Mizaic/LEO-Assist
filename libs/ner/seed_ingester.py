"""Seed dataset ingestion with validation, dedupe, and provenance tracking.

Ingests exports/ner/training/exclusion_domain_v1.jsonl (and any future seed
files) as SILVER data into the gold-standard training corpus.

Pipeline per seed record:
1.  Schema validation   — must conform to canonical target schema
2.  Offset integrity    — text[start:end] == entity.text
3.  Label enum check    — all labels must be in VALID_LABELS
4.  De-id check         — no PHI in text or entity text
5.  Clinical sanity     — exclusion-domain plausibility rules
6.  Dedupe merge        — stable key = sha256(text.lower() + sorted_entity_spans)
7.  Provenance tagging  — metadata.source_origin = "seed_<seed_name>"

A full audit block is emitted covering seed_rows_in / kept / deduped / rejected
with per-reason counts.

Usage
-----
    from libs.ner.seed_ingester import SeedIngester

    ingester = SeedIngester(
        seed_path=Path("exports/ner/training/exclusion_domain_v1.jsonl"),
        seed_name="exclusion_v1",
    )
    result = ingester.ingest(existing_keys=corpus_keys)
    # result.kept_records   → records to add to corpus
    # result.audit_block    → dict for manifest.json seed_merge section
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from libs.ner.deid_validator import DeIdValidator
from libs.ner.precision_gates import check_record_entities
from libs.ner.schema_mapper import VALID_LABELS, _verify_offset

logger = logging.getLogger(__name__)

_deid_validator = DeIdValidator()

# ---------------------------------------------------------------------------
# Stable dedupe key
# ---------------------------------------------------------------------------


def _dedupe_key(record: dict[str, Any]) -> str:
    """Deterministic key based on normalised text + sorted entity spans."""
    text_norm = re.sub(r"\s+", " ", (record.get("text") or "").lower().strip())
    spans = sorted(
        (int(e.get("start", 0)), int(e.get("end", 0)), str(e.get("label", "")))
        for e in (record.get("entities") or [])
    )
    raw = text_norm + "|" + json.dumps(spans, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


import re  # noqa: E402  (needed above — re-import here for module-level use)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_schema(record: dict[str, Any]) -> list[str]:
    """Check required top-level fields."""
    reasons: list[str] = []
    for f in ("document_id", "text", "entities"):
        if not record.get(f):
            reasons.append(f"missing_required_field:{f}")
    if not isinstance(record.get("entities"), list):
        reasons.append("entities_not_list")
    return reasons


def _validate_entities(record: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    text = record.get("text") or ""
    for idx, ent in enumerate(record.get("entities") or []):
        label = ent.get("label")
        if label not in VALID_LABELS:
            reasons.append(f"entity[{idx}]_invalid_label:{label!r}")
        start = ent.get("start")
        end = ent.get("end")
        ent_text = ent.get("text") or ""
        if start is None or end is None:
            reasons.append(f"entity[{idx}]_missing_offset")
        elif not _verify_offset(text, int(start), int(end), ent_text):
            reasons.append(
                f"entity[{idx}]_offset_mismatch:"
                f"expected={repr(ent_text)!r}|got={repr(text[int(start):int(end)])!r}"
            )
    return reasons


def _validate_deid(record: dict[str, Any]) -> list[str]:
    issues = _deid_validator.check_record(record)
    meta_check = record.get("metadata") or {}
    # Seed records marked as "synthetic" are pre-cleared for de-id
    if meta_check.get("de_identification_method") == "synthetic":
        return []
    return [f"deid:{i.issue_type}:{i.field}" for i in issues]


def _validate_clinical_sanity(record: dict[str, Any]) -> list[str]:
    """Basic exclusion-domain clinical plausibility checks."""
    reasons: list[str] = []
    text = (record.get("text") or "").lower()
    entities = record.get("entities") or []

    milestone_ents = [e for e in entities if e.get("label") == "X_PATHWAY_MILESTONE"]
    if not milestone_ents and not any(
        e.get("label") in ("disorder", "finding") for e in entities
    ):
        reasons.append("no_clinical_entities_at_all")

    # Check precision rules
    precision_reasons = check_record_entities(record)
    reasons.extend(precision_reasons)

    return reasons


# ---------------------------------------------------------------------------
# Audit / result structures
# ---------------------------------------------------------------------------


@dataclass
class SeedIngestResult:
    seed_name: str
    seed_rows_in: int = 0
    kept: int = 0
    deduped: int = 0
    rejected: int = 0
    kept_records: list[dict[str, Any]] = field(default_factory=list)
    rejected_records: list[dict[str, Any]] = field(default_factory=list)
    reason_counts: dict[str, int] = field(default_factory=dict)

    def audit_block(self) -> dict[str, Any]:
        return {
            "seed_name": self.seed_name,
            "seed_rows_in": self.seed_rows_in,
            "kept": self.kept,
            "deduped": self.deduped,
            "rejected": self.rejected,
            "reason_counts": dict(sorted(self.reason_counts.items(), key=lambda x: -x[1])),
        }

    def _add_reason(self, reason: str) -> None:
        self.reason_counts[reason] = self.reason_counts.get(reason, 0) + 1


# ---------------------------------------------------------------------------
# Main ingester
# ---------------------------------------------------------------------------


class SeedIngester:
    def __init__(self, seed_path: Path, seed_name: str) -> None:
        self.seed_path = seed_path
        self.seed_name = seed_name

    def ingest(
        self,
        existing_keys: set[str] | None = None,
    ) -> SeedIngestResult:
        """Read seed file, validate, dedupe, and return ingest result.

        Parameters
        ----------
        existing_keys : set of dedupe keys already in the corpus.  Any seed
                        record whose key matches will be logged as deduplicated
                        and excluded from kept_records.
        """
        if existing_keys is None:
            existing_keys = set()

        result = SeedIngestResult(seed_name=self.seed_name)
        seen_in_seed: set[str] = set()

        if not self.seed_path.exists():
            logger.warning("Seed file not found: %s", self.seed_path)
            return result

        with self.seed_path.open("r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                result.seed_rows_in += 1

                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    logger.warning("Seed line %d JSON parse error: %s", line_no, exc)
                    result.rejected += 1
                    result._add_reason("json_parse_error")
                    result.rejected_records.append({"line": line_no, "reasons": ["json_parse_error"], "raw": line[:200]})
                    continue

                # Tag provenance
                meta = dict(record.get("metadata") or {})
                meta["source_origin"] = f"seed_{self.seed_name}"
                record["metadata"] = meta

                # Validation pipeline
                schema_reasons = _validate_schema(record)
                entity_reasons = _validate_entities(record)
                deid_reasons = _validate_deid(record)
                sanity_reasons = _validate_clinical_sanity(record)

                all_reasons = schema_reasons + entity_reasons + deid_reasons + sanity_reasons
                if all_reasons:
                    result.rejected += 1
                    for r in all_reasons:
                        result._add_reason(r)
                    result.rejected_records.append({
                        "document_id": record.get("document_id"),
                        "line": line_no,
                        "reasons": all_reasons,
                    })
                    continue

                # Dedupe check
                dk = _dedupe_key(record)
                if dk in existing_keys or dk in seen_in_seed:
                    result.deduped += 1
                    result._add_reason("deduplicated_against_corpus" if dk in existing_keys else "deduplicated_within_seed")
                    continue

                seen_in_seed.add(dk)
                result.kept += 1
                result.kept_records.append(record)

        logger.info(
            "Seed '%s': in=%d kept=%d deduped=%d rejected=%d",
            self.seed_name,
            result.seed_rows_in,
            result.kept,
            result.deduped,
            result.rejected,
        )
        return result


# ---------------------------------------------------------------------------
# Corpus key builder
# ---------------------------------------------------------------------------


def build_corpus_keys(records: list[dict[str, Any]]) -> set[str]:
    """Build a set of dedupe keys from an existing list of canonical records."""
    return {_dedupe_key(r) for r in records}
