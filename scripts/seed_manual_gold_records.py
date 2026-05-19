"""Seed manual gold training records into the Knowledge Graph.

Reads data/training/manual-gold-seed-2026-04-17.yaml
(or any compatible manifest) and writes one TrainingCandidate +
GoldLabel pair per record into the Knowledge Graph.

Idempotent: re-running with the same manifest is a no-op.
- candidate_id = sha256(text)
- label_id     = "GL-" + first 16 hex chars of sha256(text + sorted entity texts)
Both are deterministic, so MERGE just refreshes timestamps.

DI-ID gate: each record's text is re-validated by DeIdValidator before
write. Any record with residual PHI aborts the run.

Usage:
  # Dry-run is the default; nothing is written.
  python scripts/seed_manual_gold_records.py \
      data/training/manual-gold-seed-2026-04-17.yaml

  # Actually write to the Knowledge Graph.
  python scripts/seed_manual_gold_records.py \
      data/training/manual-gold-seed-2026-04-17.yaml \
      --commit

Exit codes:
  0  success
  1  validation failure (residual PHI, bad assertion, span not found, ...)
  2  Neo4j write failure
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / "secrets" / ".env.config", override=False)
load_dotenv(REPO / "secrets" / ".env.secrets", override=False)
load_dotenv(REPO / "secrets" / ".env", override=False)

from libs.cypher.gold_label_queries import UPSERT_GOLD_LABEL  # noqa: E402
from libs.cypher.training_candidate_queries import (  # noqa: E402
    UPSERT_TRAINING_CANDIDATE,
)
from libs.ner.deid_validator import DeIdValidator  # noqa: E402
from libs.ner.span_finder import find_span  # noqa: E402
from libs.utils.deidentify import deidentify_text  # noqa: E402
from libs.training.gold_label_snomed_check import (  # noqa: E402
    _CLINICAL_LABELS,
    _NON_CLINICAL_SEMANTIC_TAGS,
    _TAG_SYNONYMS,
    _derive_semantic_tag_from_term,
)

logger = logging.getLogger("seed_manual_gold_records")

VALID_ASSERTIONS = frozenset(
    {
        "present",
        "absent",
        "refuted",
        "possible",
        "historical",
        "planned",
        "hypothetical",
        "family",
        "declined",
        "cancelled",
    }
)

VALID_LABELS = frozenset(
    {
        "disorder",
        "finding",
        "procedure",
        "observable_entity",
        "qualifier_value",
        "substance",
        "medicinal_product",
        "clinical_drug",
        "situation",
        "event",
        "body_structure",
        "tumor_staging",
        "assessment_scale",
        "staging_scale",
        "regime_therapy",
        "record_artifact",
        "physical_object",
        "organism",
        "morphologic_abnormality",
        "occupation",
        "attribute",
        "environment",
        "product",
    }
)


@dataclass
class PreparedRecord:
    tag: str
    text: str
    candidate_id: str
    label_id: str
    entities: list[dict[str, Any]]


def _candidate_id(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _label_id(text: str, entities: list[dict[str, Any]]) -> str:
    parts = sorted(str(e.get("text", "")) for e in entities)
    raw = f"{text}|{'|'.join(parts)}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"GL-{digest[:16]}"


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        manifest = yaml.safe_load(f)
    if not isinstance(manifest, dict):
        raise ValueError(f"manifest is not a mapping: {path}")
    if "records" not in manifest or not isinstance(manifest["records"], list):
        raise ValueError(f"manifest missing records[] list: {path}")
    return manifest


def _validate_entity(tag: str, text: str, ent: dict[str, Any]) -> dict[str, Any]:
    """Validate one entity from the seed manifest.

    Critical safety rule (added 2026-04-17 after the manual_gold_seed
    qualifier-value regression): the entity's `semantic_tag` field is
    derived from the SNOMED preferred-term suffix when one is present,
    NOT from the human-typed label. If the human-typed label disagrees
    with what the SNOMED concept actually IS (and the disagreement is
    not a covered synonym), the seed write is rejected.

    Otherwise we silently persist e.g. label="finding" backed by
    "Normal (qualifier value)" -- the exact bug R-LEO-AI-180 mitigates.
    """
    surface = str(ent.get("text", "")).strip()
    if not surface:
        raise ValueError(f"[{tag}] entity has empty text")
    label = str(ent.get("label", "")).strip().lower()
    if label not in VALID_LABELS:
        raise ValueError(f"[{tag}] entity label {label!r} not in VALID_LABELS")
    assertion = str(ent.get("assertion", "present")).strip().lower()
    if assertion not in VALID_ASSERTIONS:
        raise ValueError(f"[{tag}] assertion {assertion!r} not in VALID_ASSERTIONS")
    span = find_span(text, surface)
    if span is None:
        raise ValueError(
            f"[{tag}] cannot locate surface text {surface!r} in sentence text"
        )
    start, end = span

    snomed_concept_id = str(ent.get("snomed_concept_id") or "")
    raw_snomed_term = str(ent.get("snomed_term") or "").strip()
    # Default the snomed_term to the surface ONLY if no concept is
    # asserted. If the seed author asserted a concept_id, they MUST
    # provide the canonical preferred term so we can derive the
    # semantic_tag.
    if snomed_concept_id and not raw_snomed_term:
        raise ValueError(
            f"[{tag}] entity {surface!r} has snomed_concept_id="
            f"{snomed_concept_id!r} but no snomed_term -- cannot derive "
            f"semantic_tag for safety check"
        )
    snomed_term = raw_snomed_term or surface

    derived_tag = _derive_semantic_tag_from_term(snomed_term)
    declared_tag = str(ent.get("semantic_tag", "")).strip().lower()

    # Authoritative semantic_tag: SNOMED preferred-term suffix wins
    # over the human-declared field. If neither is present, fall back
    # to the declared label (for surfaces with no SNOMED mapping).
    semantic_tag = derived_tag or declared_tag or label

    if derived_tag and declared_tag and derived_tag != declared_tag:
        synonyms = _TAG_SYNONYMS.get(declared_tag, frozenset())
        if derived_tag not in synonyms:
            raise ValueError(
                f"[{tag}] entity {surface!r}: declared semantic_tag="
                f"{declared_tag!r} disagrees with SNOMED preferred-term "
                f"suffix derived_tag={derived_tag!r} (term={snomed_term!r})"
            )

    if (
        label in _CLINICAL_LABELS
        and semantic_tag in _NON_CLINICAL_SEMANTIC_TAGS
    ):
        raise ValueError(
            f"[{tag}] entity {surface!r}: label={label!r} is clinical "
            f"(finding/disorder/procedure/observable_entity) but the "
            f"attached SNOMED concept is {semantic_tag!r} (term="
            f"{snomed_term!r}). This is the R-LEO-AI-180 regression "
            f"class; either re-code to a clinical concept or relabel "
            f"the entity to qualifier_value."
        )

    if (
        label != semantic_tag
        and semantic_tag not in _TAG_SYNONYMS.get(label, frozenset())
        and derived_tag  # only enforce when we have an authoritative tag
    ):
        raise ValueError(
            f"[{tag}] entity {surface!r}: label={label!r} disagrees "
            f"with SNOMED-derived semantic_tag={semantic_tag!r} "
            f"(term={snomed_term!r}) and is not in the synonym table"
        )

    return {
        "text": surface,
        "label": label,
        "semantic_tag": semantic_tag,
        "snomed_concept_id": snomed_concept_id,
        "snomed_term": snomed_term,
        "start": int(start),
        "end": int(end),
        "assertion": assertion,
    }


def prepare_record(rec: dict[str, Any]) -> PreparedRecord:
    tag = str(rec.get("tag") or "").strip()
    text = str(rec.get("text") or "").strip()
    if not tag or not text:
        raise ValueError(f"record missing tag or text: {rec!r}")

    deid = deidentify_text(text, ner=False)
    if deid != text:
        raise ValueError(f"[{tag}] text mutates under deidentify_text(): not pre-de-identified")

    issues = DeIdValidator().check_record({"text": text, "entities": []})
    if issues:
        types = ",".join(i.issue_type for i in issues[:5])
        raise ValueError(f"[{tag}] DeIdValidator residual PHI: {types}")

    raw_entities = rec.get("entities") or []
    if not isinstance(raw_entities, list) or not raw_entities:
        raise ValueError(f"[{tag}] no entities defined")

    canonical = [_validate_entity(tag, text, ent) for ent in raw_entities]

    return PreparedRecord(
        tag=tag,
        text=text,
        candidate_id=_candidate_id(text),
        label_id=_label_id(text, canonical),
        entities=canonical,
    )


def prepare_all(manifest: dict[str, Any]) -> list[PreparedRecord]:
    return [prepare_record(rec) for rec in manifest["records"]]


def write_records(
    prepared: list[PreparedRecord],
    *,
    source: str,
    verified_by: str,
    quality_score: float,
) -> dict[str, int]:
    from libs.neo4j_client.client import KnowledgeGraphClient

    stats = {"upserted_candidates": 0, "upserted_gold_labels": 0}
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            for rec in prepared:
                entities_json = json.dumps(rec.entities)
                session.run(
                    UPSERT_TRAINING_CANDIDATE,
                    candidate_id=rec.candidate_id,
                    text=rec.text,
                    entities_json=entities_json,
                    relation_changes=json.dumps([]),
                    source=source,
                    status="completed",
                    hitl_reason="manual_gold_seed",
                    hitl_guidance="Hand-authored cancer-positive / benign control gold record.",
                    schema_version="v4",
                )
                stats["upserted_candidates"] += 1
                session.run(
                    UPSERT_GOLD_LABEL,
                    label_id=rec.label_id,
                    text=rec.text,
                    entities_json=entities_json,
                    quality_score=float(quality_score),
                    source=source,
                    verified_by=verified_by,
                    candidate_id=rec.candidate_id,
                    schema_version="2.0",
                )
                stats["upserted_gold_labels"] += 1
    finally:
        client.close()
    return stats


def _print_dry_run(prepared: list[PreparedRecord], manifest: dict[str, Any]) -> None:
    logger.info("--- dry-run: %d record(s) prepared ---", len(prepared))
    logger.info(
        "source=%s verified_by=%s quality_score=%.2f",
        manifest.get("source"),
        manifest.get("verified_by"),
        float(manifest.get("quality_score") or 0.0),
    )
    label_counts: dict[str, int] = {}
    assertion_counts: dict[str, int] = {}
    for rec in prepared:
        for ent in rec.entities:
            label_counts[ent["label"]] = label_counts.get(ent["label"], 0) + 1
            assertion_counts[ent["assertion"]] = (
                assertion_counts.get(ent["assertion"], 0) + 1
            )
        logger.info(
            "  %s candidate_id=%s... label_id=%s entities=%d",
            rec.tag.ljust(32),
            rec.candidate_id[:16],
            rec.label_id,
            len(rec.entities),
        )
    logger.info("label distribution : %s", sorted(label_counts.items()))
    logger.info("assertion distribution: %s", sorted(assertion_counts.items()))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "manifest",
        type=Path,
        help="Path to the manual gold seed YAML manifest.",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Actually write to the Knowledge Graph (default is dry-run).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (default INFO).",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(levelname)s %(name)s: %(message)s",
    )

    if not args.manifest.exists():
        logger.error("manifest not found: %s", args.manifest)
        return 1

    try:
        manifest = load_manifest(args.manifest)
        prepared = prepare_all(manifest)
    except ValueError as exc:
        logger.error("manifest validation failed: %s", exc)
        return 1

    _print_dry_run(prepared, manifest)

    if not args.commit:
        logger.info("dry-run: not writing to Neo4j (use --commit to write)")
        return 0

    try:
        stats = write_records(
            prepared,
            source=str(manifest.get("source") or "manual_gold_seed"),
            verified_by=str(manifest.get("verified_by") or "manual_gold_seed"),
            quality_score=float(manifest.get("quality_score") or 0.95),
        )
    except Exception:
        logger.exception("Knowledge Graph write failed")
        return 2

    logger.info(
        "wrote %d TrainingCandidate(s) and %d GoldLabel(s)",
        stats["upserted_candidates"],
        stats["upserted_gold_labels"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
