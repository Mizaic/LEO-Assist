"""Export GoldLabel nodes from Neo4j into spaCy DocBin format.

Atlas trace:
  DO: DO-2695BE52
  Also implements: DO-54397CCD, DO-A35D2D57
  DI: DI-37B3DC71, DI-3DFEE507, DI-6EFD68D0
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-2695BE52")

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
import hashlib
import json
import logging
import os
import random
import shutil
from pathlib import Path
from typing import Any

from libs.pipeline.label_filter import (
    DEFAULT_EXCLUDED_ASSERTIONS as _DEFAULT_EXCLUDED_ASSERTIONS,
    filter_and_realign as _filter_and_realign,
    get_excluded_assertions as _get_excluded_assertions,
    realign_entity as _realign_entity,
)
from libs.training_ext.corpus_balancer import (
    BalanceConfig,
    TierOneLabelStarvationError,
    balance_corpus,
)
from libs.training_ext.stratified_split import (
    SplitRatios,
    iterative_multilabel_split,
)
from libs.training_ext.suggesters import _DEFAULT_CLINICAL_SIZES
from libs.training_ext.training_quality import summarise_export_support

_ORTH_VARIANTS_SOURCE = (
    Path(__file__).resolve().parents[3]
    / "libs"
    / "training_ext"
    / "orth_variants_en_clinical.json"
)

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = "1.0"

_CANDIDATE_SIZE_CONTRACTS: dict[str, tuple[int, ...]] = {
    "narrow": (1, 2, 3, 4, 5, 22, 23, 24),
    "balanced": _DEFAULT_CLINICAL_SIZES,
    "broad_1_24": tuple(range(1, 25)),
}

# Label normalisation -- maps stored labels to canonical uppercase spaCy labels.
# Includes both underscore form (current canonical) and legacy space form (SNOMED
# display string) so that any historical records with space-separated labels are
# correctly exported rather than producing a spurious new spaCy class.
_LABEL_MAP: dict[str, str] = {
    "disorder": "DISORDER",
    "finding": "FINDING",
    "procedure": "PROCEDURE",
    "observable_entity": "OBSERVABLE",
    "observable entity": "OBSERVABLE",          # legacy space form
    "qualifier_value": "QUALIFIER",
    "qualifier value": "QUALIFIER",             # legacy space form
    "substance": "SUBSTANCE",
    "medicinal_product": "MEDICINAL_PRODUCT",
    "medicinal product": "MEDICINAL_PRODUCT",   # legacy space form
    "clinical_drug": "CLINICAL_DRUG",
    "clinical drug": "CLINICAL_DRUG",           # legacy space form
    "situation": "SITUATION",
    "event": "EVENT",
    "body_structure": "BODY_STRUCTURE",
    "body structure": "BODY_STRUCTURE",         # legacy space form
    "tumor_staging": "TUMOR_STAGING",
    "tumor staging": "TUMOR_STAGING",           # legacy space form
    "assessment_scale": "ASSESSMENT_SCALE",
    "assessment scale": "ASSESSMENT_SCALE",     # legacy space form
    "staging_scale": "STAGING_SCALE",
    "staging scale": "STAGING_SCALE",           # legacy space form
    "regime_therapy": "REGIME_THERAPY",
    "regime/therapy": "REGIME_THERAPY",         # legacy slash form
    "record_artifact": "RECORD_ARTIFACT",
    "record artifact": "RECORD_ARTIFACT",       # legacy space form
    "physical_object": "PHYSICAL_OBJECT",
    "physical object": "PHYSICAL_OBJECT",       # legacy space form
    "organism": "ORGANISM",
    "morphologic_abnormality": "MORPHOLOGIC_ABNORMALITY",
    "morphologic abnormality": "MORPHOLOGIC_ABNORMALITY",  # legacy space form
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


def _new_candidate_coverage(
    split_names: list[str],
) -> dict[str, dict[str, dict[str, dict[str, int]]]]:
    return {
        name: {split: {} for split in split_names}
        for name in _CANDIDATE_SIZE_CONTRACTS
    }


def _add_span_coverage(
    bucket: dict[str, dict[str, int]],
    *,
    label: str,
    token_length: int,
    sizes: tuple[int, ...],
) -> None:
    row = bucket.setdefault(label, {"total": 0, "covered": 0})
    row["total"] += 1
    if token_length in sizes:
        row["covered"] += 1


def _add_doc_candidate_coverage(
    coverage: dict[str, dict[str, dict[str, dict[str, int]]]],
    split_name: str,
    doc,
) -> None:
    for span in doc.spans.get("sc", []):
        label = str(span.label_)
        token_length = int(span.end - span.start)
        for contract, sizes in _CANDIDATE_SIZE_CONTRACTS.items():
            _add_span_coverage(
                coverage[contract][split_name],
                label=label,
                token_length=token_length,
                sizes=sizes,
            )


def _candidate_coverage_report(
    coverage: dict[str, dict[str, dict[str, dict[str, int]]]],
) -> dict[str, Any]:
    return {
        contract: {
            split: {
                label: _coverage_row(row)
                for label, row in sorted(labels.items())
            }
            for split, labels in split_rows.items()
        }
        for contract, split_rows in coverage.items()
    }


def _coverage_row(row: dict[str, int]) -> dict[str, Any]:
    total = int(row.get("total", 0))
    covered = int(row.get("covered", 0))
    return {
        "total": total,
        "covered": covered,
        "missed": max(0, total - covered),
        "coverage": round(covered / total, 4) if total else 0.0,
    }


def _format_candidate_coverage(
    report: dict[str, Any],
    *,
    split_name: str = "val",
    labels: tuple[str, ...] = ("OBSERVABLE", "PROCEDURE", "FINDING"),
) -> list[str]:
    lines = []
    for contract in ("narrow", "balanced", "broad_1_24"):
        split = report.get(contract, {}).get(split_name, {})
        parts = []
        for label in labels:
            row = split.get(label, {})
            parts.append(
                f"{label}={row.get('covered', 0)}/{row.get('total', 0)}"
            )
        lines.append(f"{contract}: " + ", ".join(parts))
    return lines


def _record_to_spacy_doc(
    nlp,
    text: str,
    entities: list[dict[str, Any]],
    *,
    alignment_report: list[dict[str, Any]] | None = None,
    label_id: str = "",
):
    """Convert a single training record to a spaCy Doc with entity spans.

    Entities passed here must already be assertion-filtered and span-realigned.
    Overlapping and co-located spans with different labels are all written to
    doc.spans["sc"] to support multi-label spancat training. The seen_tokens
    dedup guard used by the legacy NER pipeline is intentionally absent.

    When ``alignment_report`` is provided, any span whose char offsets are
    silently expanded by ``alignment_mode="expand"`` to token boundaries has
    its before/after surface forms recorded (Wave 2 / F24).
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

        if alignment_report is not None and (
            span.start_char != start_char or span.end_char != end_char
        ):
            alignment_report.append(
                {
                    "label_id": label_id,
                    "label": label,
                    "requested_start": start_char,
                    "requested_end": end_char,
                    "resolved_start": span.start_char,
                    "resolved_end": span.end_char,
                    "requested_surface": text[start_char:end_char],
                    "resolved_surface": span.text,
                }
            )

        spans.append(span)

    doc.spans["sc"] = spans
    return doc


def export_labels(
    output_dir: Path,
    *,
    train_ratio: float | None = None,
    seed: int = 42,
    split_ratios: SplitRatios | None = None,
    log_fn=None,
) -> dict[str, Any]:
    """Fetch all exportable GoldLabel nodes and write train/val/dev/test DocBins.

    Wave 2 (F6, F20) replaces the previous random 80/20 split with a multi-
    label iterative stratified split producing four named partitions:

      * ``train`` (default 0.7) — optimiser training corpus
      * ``val``   (default 0.1) — drives early stopping during training
      * ``dev``   (default 0.1) — drives threshold calibration
      * ``test``  (default 0.1) — reported once after promotion

    Args:
        output_dir: Directory to write *.spacy and meta.json.
        train_ratio: Back-compat shorthand — if set, interpreted as the train
            fraction with the remainder split equally between val/dev/test.
            Prefer ``split_ratios`` for explicit control.
        seed: Random seed for reproducible split.
        split_ratios: Named ratios; must sum to 1.0.  Defaults to
            ``SplitRatios(0.7, 0.1, 0.1, 0.1)``.
        log_fn: Optional callable(str) for progress logging.

    Returns:
        dict with keys: total, per-split counts (``train_count``, ``val_count``,
        ``dev_count``, ``test_count``), per-split paths, labels_found,
        stratification warnings.

    Raises:
        ValueError: If fewer records than TRAINING_MIN_LABEL_COUNT.
    """
    import spacy
    from spacy.tokens import DocBin

    from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient
    from libs.cypher.gold_label_queries import GET_TRAINING_GOLD_LABELS_FOR_EXPORT
    from libs.cypher.golden_set_queries import GET_GOLDEN_SET_LABELS
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
    holdback_label_ids: list[str] = []
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
            rows = session.run(GET_TRAINING_GOLD_LABELS_FOR_EXPORT)
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
                        "label_id": label_id,
                        "text": text,
                        "entities": entities,
                        "source": source,
                    }
                )
            holdback_rows = session.run(GET_GOLDEN_SET_LABELS)
            holdback_label_ids = sorted(
                {
                    str(r.get("label_id") or "")
                    for r in holdback_rows
                    if str(r.get("label_id") or "").strip()
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

    # Corpus rebalancing -- collapse exact-duplicate text, cap per-source
    # surface dupes, cap any single source's share, and abort if tier-1
    # safety-critical labels are starved.  Without this guard a single bulk
    # seeder (historically: lab_coder_v1) can dominate the corpus and produce
    # a model that only fires on lab-test surfaces.
    balance_cfg = BalanceConfig.from_env()
    _log(
        "Corpus rebalancer config: "
        f"max_source_share={balance_cfg.max_source_share} "
        f"max_surface_dupes_per_source={balance_cfg.max_surface_dupes_per_source} "
        f"max_records_per_text={balance_cfg.max_records_per_text} "
        f"min_per_label={balance_cfg.min_per_label} "
        f"tier1={sorted(balance_cfg.tier1_labels)}"
    )
    try:
        records, balance_report = balance_corpus(records, balance_cfg)
    except TierOneLabelStarvationError as exc:
        # Re-raise as ValueError so existing job runner failure handling
        # surfaces the message verbatim to the user.
        raise ValueError(str(exc)) from exc

    for warning in balance_report.warnings:
        _log(f"Corpus balancer warning: {warning}")
    if balance_report.text_dedupe_dropped:
        _log(
            "Corpus balancer: dropped "
            f"{balance_report.text_dedupe_dropped} duplicate-text records."
        )
    if balance_report.surface_dedupe_dropped:
        _log(
            "Corpus balancer: dropped "
            f"{balance_report.surface_dedupe_dropped} repeated entity spans "
            "(per-source surface cap)."
        )
    if balance_report.source_cap_dropped:
        for action in balance_report.source_cap_actions:
            _log(
                "Corpus balancer: capped source "
                f"{action['source']!r} {action['before']} -> {action['after']} "
                f"(share {action['share_before']:.3f} -> "
                f"<= {action['share_target']:.3f})."
            )
    if balance_report.other_under_min:
        _log(
            "Corpus balancer: non-tier1 labels under minimum "
            f"({balance_cfg.min_per_label}): "
            + "; ".join(balance_report.other_under_min)
        )
    _log(
        f"Corpus balancer: {balance_report.pre_record_count} -> "
        f"{balance_report.post_record_count} records after rebalancing."
    )

    if len(records) < min_count:
        raise ValueError(
            f"Only {len(records)} GoldLabel records after rebalancing -- "
            f"minimum is {min_count}. Add more verified gold labels (or relax "
            "TRAINING_CORPUS_* limits) before training."
        )

    ratios = _resolve_split_ratios(train_ratio, split_ratios)
    label_sets: list[set[str]] = []
    for rec in records:
        label_sets.append(
            {
                _normalise_label(str(ent.get("label", "")))
                for ent in rec["entities"]
                if _normalise_label(str(ent.get("label", "")))
            }
        )

    split = iterative_multilabel_split(label_sets, ratios=ratios, seed=seed)
    for warning in split.warnings:
        _log(f"Stratified split warning: {warning}")

    split_records: dict[str, list[dict[str, Any]]] = {
        name: [records[i] for i in indices]
        for name, indices in split.indices.items()
    }
    _log(
        "Split: "
        + " / ".join(f"{len(v)} {k}" for k, v in split_records.items())
        + f" (seed={seed})"
    )

    nlp = spacy.blank("en")
    output_dir.mkdir(parents=True, exist_ok=True)

    per_split_bins: dict[str, DocBin] = {name: DocBin() for name in split_records}
    per_split_label_counts: dict[str, dict[str, int]] = {
        name: {} for name in split_records
    }
    per_split_label_ids: dict[str, list[str]] = {name: [] for name in split_records}
    all_labels: set[str] = set()
    skipped = 0
    alignment_report: list[dict[str, Any]] = []
    candidate_coverage = _new_candidate_coverage(list(split_records))

    for split_name, recs in split_records.items():
        for rec in recs:
            label_id_value = str(rec.get("label_id") or "")
            if label_id_value.strip():
                per_split_label_ids[split_name].append(label_id_value)
            counts = per_split_label_counts[split_name]
            for ent in rec["entities"]:
                label = _normalise_label(str(ent.get("label", "")))
                all_labels.add(label)
                if label:
                    counts[label] = counts.get(label, 0) + 1
            try:
                doc = _record_to_spacy_doc(
                    nlp,
                    rec["text"],
                    rec["entities"],
                    alignment_report=alignment_report,
                    label_id=label_id_value,
                )
                _add_doc_candidate_coverage(candidate_coverage, split_name, doc)
                per_split_bins[split_name].add(doc)
            except Exception:
                skipped += 1

    split_paths: dict[str, Path] = {}
    for split_name, bin_ in per_split_bins.items():
        path = output_dir / f"{split_name}.spacy"
        bin_.to_disk(path)
        split_paths[split_name] = path

    # Stable aliases for legacy callers (trainer and older tests).
    train_path = split_paths["train"]
    dev_path = split_paths["dev"]

    # Copy the clinical orth-variants table next to the corpora so the spaCy
    # trainer can resolve ${paths.orth_variants}.
    orth_variants_path = output_dir / "orth_variants.json"
    try:
        shutil.copyfile(_ORTH_VARIANTS_SOURCE, orth_variants_path)
    except OSError as exc:
        _log(
            "Warning: failed to copy orth_variants table "
            f"({_ORTH_VARIANTS_SOURCE} -> {orth_variants_path}): {exc}"
        )
        orth_variants_path.write_text(
            json.dumps({"single": [], "paired": []}),
            encoding="utf-8",
        )

    if skipped:
        _log(f"Warning: {skipped} records skipped during DocBin conversion.")
    if alignment_report:
        _log(
            f"Span alignment report: {len(alignment_report)} entities had "
            "char offsets silently expanded to token boundaries."
        )

    all_label_keys = sorted(all_labels)
    _log("Per-label entity counts (" + " / ".join(split_records.keys()) + "):")
    for label in all_label_keys:
        parts = [f"{per_split_label_counts[n].get(label, 0)} {n}" for n in split_records]
        warn = (
            " <-- LOW"
            if per_split_label_counts.get("dev", {}).get(label, 0) < 5
            else ""
        )
        _log(f"  {label}: " + " / ".join(parts) + warn)

    exported_at = datetime.datetime.utcnow().isoformat()
    per_split_hashes = {
        name: hashlib.sha256("\n".join(sorted(ids)).encode("utf-8")).hexdigest()
        for name, ids in per_split_label_ids.items()
    }
    holdback_split_hash = hashlib.sha256(
        "\n".join(holdback_label_ids).encode("utf-8")
    ).hexdigest()
    per_label_counts_meta = {
        label: {
            name: per_split_label_counts[name].get(label, 0)
            for name in split_records
        }
        for label in all_label_keys
    }
    candidate_coverage_meta = _candidate_coverage_report(candidate_coverage)
    for line in _format_candidate_coverage(candidate_coverage_meta, split_name="val"):
        _log("Candidate coverage (val) " + line)
    for line in _format_candidate_coverage(candidate_coverage_meta, split_name="dev"):
        _log("Candidate coverage (dev) " + line)
    training_quality = summarise_export_support(per_label_counts_meta)

    balance_report_dict = balance_report.to_dict()
    (output_dir / "corpus_balance_report.json").write_text(
        json.dumps(balance_report_dict, indent=2),
        encoding="utf-8",
    )
    (output_dir / "candidate_coverage_report.json").write_text(
        json.dumps(candidate_coverage_meta, indent=2),
        encoding="utf-8",
    )

    meta = {
        "exported_at": exported_at,
        "total_records": len(records),
        "split_ratios": ratios.as_mapping(),
        "split_counts": {name: len(recs) for name, recs in split_records.items()},
        "split_paths": {name: str(p) for name, p in split_paths.items()},
        "split_label_ids": {
            name: sorted(ids) for name, ids in per_split_label_ids.items()
        },
        "split_hashes": per_split_hashes,
        "stratification_warnings": split.warnings,
        "corpus_balance": {
            "pre_record_count": balance_report.pre_record_count,
            "post_record_count": balance_report.post_record_count,
            "text_dedupe_dropped": balance_report.text_dedupe_dropped,
            "surface_dedupe_dropped": balance_report.surface_dedupe_dropped,
            "source_cap_dropped": balance_report.source_cap_dropped,
            "tier1_under_min": list(balance_report.tier1_under_min),
            "other_under_min": list(balance_report.other_under_min),
            "warnings": list(balance_report.warnings),
        },
        # --- Legacy fields kept for back-compat with existing consumers --------
        "train_records": len(split_records["train"]),
        "dev_records": len(split_records["dev"]),
        "train_label_ids": sorted(per_split_label_ids["train"]),
        "dev_label_ids": sorted(per_split_label_ids["dev"]),
        "holdback_label_ids": holdback_label_ids,
        "train_split_hash": per_split_hashes["train"],
        "dev_split_hash": per_split_hashes["dev"],
        "holdback_split_hash": holdback_split_hash,
        "skipped": skipped,
        "assertion_filtered": total_assertion_filtered,
        "span_misaligned": total_span_misaligned,
        "span_alignment_expanded": len(alignment_report),
        "excluded_assertions": sorted(excluded_assertions),
        "label_set": sorted(all_labels),
        "per_label_counts": per_label_counts_meta,
        "candidate_coverage": candidate_coverage_meta,
        "training_quality": training_quality,
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
            "span_alignment_expanded_count": len(alignment_report),
        },
        "assertion_filtered": [
            d for d in diagnostics if d["reason"] == "assertion_filtered"
        ],
        "span_misaligned": [d for d in diagnostics if d["reason"] == "span_misaligned"],
        "span_alignment_expanded": alignment_report,
        "candidate_coverage": candidate_coverage_meta,
    }
    (output_dir / "export_diagnostics.json").write_text(
        json.dumps(diag_payload, indent=2)
    )

    # Dedicated span_alignment_report.json — Wave 5 artifact bundle consumes
    # this as-is.
    (output_dir / "span_alignment_report.json").write_text(
        json.dumps(
            {
                "summary": {"expanded_count": len(alignment_report)},
                "entries": alignment_report,
            },
            indent=2,
        )
    )

    _log(f"DocBins written to {output_dir}")

    return {
        "total": len(records),
        "split_counts": {name: len(recs) for name, recs in split_records.items()},
        "split_paths": {name: str(p) for name, p in split_paths.items()},
        "stratification_warnings": split.warnings,
        # --- Back-compat keys consumed by job_runner and tests -----------------
        "train_count": len(split_records["train"]),
        "val_count": len(split_records.get("val", [])),
        "dev_count": len(split_records["dev"]),
        "test_count": len(split_records.get("test", [])),
        "skipped": skipped,
        "assertion_filtered": total_assertion_filtered,
        "span_misaligned": total_span_misaligned,
        "span_alignment_expanded": len(alignment_report),
        "labels_found": sorted(all_labels),
        "label_set": sorted(all_labels),
        "per_label_counts": per_label_counts_meta,
        "candidate_coverage": candidate_coverage_meta,
        "training_quality": training_quality,
        "exported_at": exported_at,
        "train_path": str(train_path),
        "dev_path": str(dev_path),
        "val_path": str(split_paths.get("val", dev_path)),
        "test_path": str(split_paths.get("test", dev_path)),
        "orth_variants_path": str(orth_variants_path),
    }


def _resolve_split_ratios(
    train_ratio: float | None,
    split_ratios: SplitRatios | None,
) -> SplitRatios:
    """Resolve Wave 2 ratios with a back-compat shim for the old kwarg."""
    if split_ratios is not None:
        return split_ratios
    if train_ratio is None:
        return SplitRatios()
    if not 0.0 < train_ratio < 1.0:
        raise ValueError(
            f"train_ratio must be strictly between 0 and 1, got {train_ratio!r}"
        )
    remainder = 1.0 - train_ratio
    third = remainder / 3.0
    return SplitRatios(train=train_ratio, val=third, dev=third, test=remainder - 2 * third)
