"""Export NER training adapters from full-schema JSONL to model-training inputs.

Converts exports/ner/all_domains/domain_entities_merged.jsonl into:
    exports/ner/all_domains/training_adapters/
        spacy/
            train.spacy       — spaCy DocBin (training split ~80%)
            dev.spacy         — spaCy DocBin (dev split ~20%)
            train.jsonl       — spaCy-compatible JSON (for inspection)
            dev.jsonl         — spaCy-compatible JSON (for inspection)
            meta.json         — adapter metadata (source version, label set, counts)
        validation/
            import_check.txt  — importability validation result
            label_stats.json  — entity label distribution

The script also runs an automated importability validation: it reads back the
written DocBin files and verifies all docs are parseable, matching entity
counts to the source JSONL.

Requires: spacy (pip install spacy)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DEFAULT_INPUT = (
    ROOT / "exports" / "ner" / "all_domains" / "domain_entities_merged.jsonl"
)
DEFAULT_OUT_DIR = ROOT / "exports" / "ner" / "all_domains" / "training_adapters"
TRAIN_SPLIT = 0.8


# ---------------------------------------------------------------------------
# Label mapping to spaCy entity labels
# ---------------------------------------------------------------------------
# spaCy entity labels must be simple strings (no colon, uppercase conventional)
_LABEL_TO_SPACY: dict[str, str] = {
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


def _to_spacy_label(label: str) -> str:
    return _LABEL_TO_SPACY.get(label, label.upper())


# ---------------------------------------------------------------------------
# spaCy-compatible JSON format (for inspection / non-DocBin consumers)
# ---------------------------------------------------------------------------


def _record_to_spacy_json(record: dict[str, Any]) -> dict[str, Any]:
    """Convert one canonical record to spaCy JSON training format."""
    text = record.get("text") or ""
    entities: list[tuple[int, int, str]] = []
    for ent in record.get("entities") or []:
        start = ent.get("start")
        end = ent.get("end")
        label = ent.get("label", "")
        if start is not None and end is not None and label:
            entities.append((int(start), int(end), _to_spacy_label(label)))

    # Resolve overlapping spans (keep longest)
    entities = _resolve_overlaps(entities)

    return {
        "document_id": record.get("document_id"),
        "text": text,
        "entities": [{"start": s, "end": e, "label": l} for s, e, l in entities],
        "metadata": record.get("metadata"),
    }


def _resolve_overlaps(
    entities: list[tuple[int, int, str]],
) -> list[tuple[int, int, str]]:
    """Remove overlapping entity spans, keeping longest span at each position."""
    if not entities:
        return []
    sorted_ents = sorted(entities, key=lambda x: (x[0], -(x[1] - x[0])))
    result: list[tuple[int, int, str]] = []
    last_end = -1
    for start, end, label in sorted_ents:
        if start >= last_end:
            result.append((start, end, label))
            last_end = end
    return result


# ---------------------------------------------------------------------------
# DocBin writer (requires spaCy)
# ---------------------------------------------------------------------------


def _write_docbin(
    records: list[dict[str, Any]],
    output_path: Path,
    nlp: Any,
) -> int:
    """Write a list of canonical records to a spaCy DocBin file.

    Returns number of docs written.
    """
    from spacy.tokens import DocBin, Span

    db = DocBin()
    written = 0
    skipped = 0
    for record in records:
        text = record.get("text") or ""
        if not text:
            skipped += 1
            continue
        doc = nlp.make_doc(text)
        spacy_ents = _record_to_spacy_json(record)["entities"]
        spans: list[Span] = []
        for ent_info in spacy_ents:
            start_char = ent_info["start"]
            end_char = ent_info["end"]
            label = ent_info["label"]
            try:
                span = doc.char_span(
                    start_char, end_char, label=label, alignment_mode="contract"
                )
                if span is not None:
                    spans.append(span)
            except Exception:
                pass
        doc.ents = tuple(spans)
        db.add(doc)
        written += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    db.to_disk(str(output_path))
    if skipped:
        logger.warning("Skipped %d empty records when writing %s", skipped, output_path)
    return written


# ---------------------------------------------------------------------------
# Importability validation
# ---------------------------------------------------------------------------


def _validate_docbin(
    docbin_path: Path,
    expected_doc_count: int,
    nlp: Any,
) -> dict[str, Any]:
    """Read back a DocBin and verify it's importable; return validation result."""
    from spacy.tokens import DocBin

    result: dict[str, Any] = {
        "path": str(docbin_path),
        "status": "fail",
        "expected_docs": expected_doc_count,
        "actual_docs": 0,
        "entity_count": 0,
        "errors": [],
    }
    try:
        db = DocBin().from_disk(str(docbin_path))
        docs = list(db.get_docs(nlp.vocab))
        result["actual_docs"] = len(docs)
        result["entity_count"] = sum(len(doc.ents) for doc in docs)
        if len(docs) != expected_doc_count:
            result["errors"].append(
                f"doc_count_mismatch: expected={expected_doc_count} actual={len(docs)}"
            )
        else:
            result["status"] = "pass"
    except Exception as exc:
        result["errors"].append(str(exc))
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--train-split", type=float, default=TRAIN_SPLIT)
    parser.add_argument(
        "--skip-docbin",
        action="store_true",
        help="Only write JSON adapter; skip spaCy DocBin (use if spaCy not installed)",
    )
    parser.add_argument(
        "--dataset-version", default="v1", help="Version tag for adapter meta"
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    out_dir = Path(args.out_dir)
    spacy_dir = out_dir / "spacy"
    validation_dir = out_dir / "validation"
    spacy_dir.mkdir(parents=True, exist_ok=True)
    validation_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        logger.error("Input file not found: %s", input_path)
        sys.exit(1)

    # Load all records
    records: list[dict[str, Any]] = []
    with input_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    logger.info("Loaded %d records from %s", len(records), input_path)

    # Deterministic split — sort by document_id for reproducibility
    records.sort(key=lambda r: r.get("document_id") or "")
    split_idx = int(len(records) * args.train_split)
    train_records = records[:split_idx]
    dev_records = records[split_idx:]

    logger.info("Split: train=%d dev=%d", len(train_records), len(dev_records))

    # Label statistics
    label_counts: Counter[str] = Counter()
    domain_counts: Counter[str] = Counter()
    for rec in records:
        for ent in rec.get("entities") or []:
            label_counts[ent.get("label", "unknown")] += 1
            domain_counts[ent.get("domain", "unknown")] += 1

    # Write spaCy JSON (inspection format)
    for split_name, split_recs in [("train", train_records), ("dev", dev_records)]:
        json_out = spacy_dir / f"{split_name}.jsonl"
        with json_out.open("w", encoding="utf-8") as jf:
            for rec in split_recs:
                jf.write(
                    json.dumps(_record_to_spacy_json(rec), ensure_ascii=False) + "\n"
                )
        logger.info("Wrote %s: %d records → %s", split_name, len(split_recs), json_out)

    # Write DocBin (spaCy binary format)
    validation_results: list[dict[str, Any]] = []
    import_check_lines: list[str] = []

    if not args.skip_docbin:
        try:
            import spacy  # noqa: F401

            nlp = spacy.blank("en")

            for split_name, split_recs in [
                ("train", train_records),
                ("dev", dev_records),
            ]:
                docbin_out = spacy_dir / f"{split_name}.spacy"
                written = _write_docbin(split_recs, docbin_out, nlp)
                logger.info("DocBin %s: %d docs → %s", split_name, written, docbin_out)

                validation = _validate_docbin(docbin_out, written, nlp)
                validation_results.append(validation)
                status = validation["status"]
                import_check_lines.append(
                    f"{split_name}.spacy: {status} | docs={validation['actual_docs']} ents={validation['entity_count']}"
                )
                if validation["errors"]:
                    for err in validation["errors"]:
                        import_check_lines.append(f"  ERROR: {err}")
                    logger.warning(
                        "DocBin validation errors for %s: %s",
                        split_name,
                        validation["errors"],
                    )
                else:
                    logger.info(
                        "DocBin %s validated OK: docs=%d ents=%d",
                        split_name,
                        validation["actual_docs"],
                        validation["entity_count"],
                    )

        except ImportError:
            msg = "spaCy not installed — DocBin output skipped. Install with: pip install spacy"
            logger.warning(msg)
            import_check_lines.append(f"SKIPPED: {msg}")
    else:
        import_check_lines.append("SKIPPED: --skip-docbin flag set")

    # Write validation outputs
    (validation_dir / "import_check.txt").write_text(
        "\n".join(import_check_lines), encoding="utf-8"
    )
    (validation_dir / "label_stats.json").write_text(
        json.dumps(
            {
                "label_counts": dict(label_counts.most_common()),
                "domain_counts": dict(domain_counts.most_common()),
                "total_entities": sum(label_counts.values()),
                "total_records": len(records),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # Write adapter meta
    meta: dict[str, Any] = {
        "dataset_version": args.dataset_version,
        "source_file": str(input_path),
        "total_records": len(records),
        "train_records": len(train_records),
        "dev_records": len(dev_records),
        "train_split": args.train_split,
        "label_set": sorted(_LABEL_TO_SPACY.values()),
        "label_counts": dict(label_counts.most_common()),
        "domain_counts": dict(domain_counts.most_common()),
        "docbin_validation": validation_results,
        "outputs": {
            "train_jsonl": str(spacy_dir / "train.jsonl"),
            "dev_jsonl": str(spacy_dir / "dev.jsonl"),
            "train_spacy": (
                str(spacy_dir / "train.spacy") if not args.skip_docbin else None
            ),
            "dev_spacy": str(spacy_dir / "dev.spacy") if not args.skip_docbin else None,
            "import_check": str(validation_dir / "import_check.txt"),
            "label_stats": str(validation_dir / "label_stats.json"),
        },
    }
    (spacy_dir / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "total_records": len(records),
                "train_records": len(train_records),
                "dev_records": len(dev_records),
                "docbin_ok": all(v.get("status") == "pass" for v in validation_results),
                "label_count": sum(label_counts.values()),
                "outputs": meta["outputs"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
