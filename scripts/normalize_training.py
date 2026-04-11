"""Normalise per-milestone training JSONL files into a single merged file.

Reads the four files produced by generate_training_datasets.py and:

1. Applies a uniform canonical schema to every record (positive and negative).
2. Promotes cross-label records that are negative for one milestone but are
   evidently positive for another (e.g. "Seen in fast track suspected X clinic"
   is negative for diagnosis but positive for specialist_visit).

Output: exports/training/all_training_merged.jsonl

Canonical schema
----------------
Every output record has exactly these keys (null when not applicable):

    patient_id       str
    milestone_type   str   "referral" | "diagnosis" | "treatment_start" | "specialist_visit"
    label            int   1 = positive example, 0 = negative example
    encounter_id     str
    encounter_date   str   YYYY-MM-DD
    text             str   The clinical text span (evidence / snippet / phrase_matched)
    concept_id       str | null
    concept_name     str | null
    confidence       float | null
    detection_method str | null   "concept" | "hybrid" | "investigation+llm"
    assertion        str | null   "present" | "historical" | "negated" | null
    source_file      str          which input file this came from
    exclusion_reason str | null   why it was labelled 0 (null for positives)

Usage
-----
    python scripts/normalize_training.py \\
        --input-dir exports/training \\
        --output   exports/training/all_training_merged.jsonl
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s"
)
logger = logging.getLogger("normalize_training")

# ──────────────────────────────────────────────────────────────────────────────
# Cross-label promotion patterns
# ──────────────────────────────────────────────────────────────────────────────

_FAST_TRACK_CLINIC_RE = re.compile(
    r"Seen in fast track suspected .+ clinic",
    re.IGNORECASE,
)
_FAST_TRACK_REFERRAL_RE = re.compile(
    r"Fast track referral for suspected",
    re.IGNORECASE,
)
_2WW_REFERRAL_RE = re.compile(
    r"\b2ww\b|two.week.wait referral|\brefer\b.{0,30}\bsuspected cancer\b",
    re.IGNORECASE,
)

# Assertion heuristics
_HISTORICAL_RE = re.compile(
    r"\b(had|previous|past|former|prior|history of|PMH|PMHx|hx of)\b",
    re.IGNORECASE,
)
_NEGATED_RE = re.compile(
    r"\b(no evidence of|no fam|rule out|unlikely|excluded|not )\b",
    re.IGNORECASE,
)
_FAMILY_RE = re.compile(
    r"\b(family history|fam hx|fam hist|maternal|paternal)\b",
    re.IGNORECASE,
)


def _infer_assertion(text: str, record: dict) -> str | None:
    """Infer assertion type from record metadata and text."""
    if record.get("disambiguation") == "historical":
        return "historical"
    text_lower = text.lower()
    if _NEGATED_RE.search(text):
        return "negated"
    if _FAMILY_RE.search(text):
        return "family_history"
    if _HISTORICAL_RE.search(text):
        return "historical"
    return "present"


def _canonical(
    record: dict,
    milestone_type: str,
    source_file: str,
    label: int | None = None,
    exclusion_reason: str | None = None,
) -> dict[str, Any]:
    """Convert a raw training record into the canonical schema."""
    # Prefer evidence > phrase_matched > snippet as the canonical text
    text = (
        record.get("evidence")
        or record.get("phrase_matched")
        or record.get("snippet")
        or record.get("text")
        or ""
    )
    text = text[:400]  # cap length

    resolved_label = label if label is not None else record.get("label", 0)

    assertion = record.get("assertion")
    if not assertion and text:
        assertion = _infer_assertion(text, record)

    return {
        "patient_id": record.get("patient_id", ""),
        "milestone_type": milestone_type,
        "label": resolved_label,
        "encounter_id": str(record.get("encounter_id", "")),
        "encounter_date": str(record.get("encounter_date") or record.get("date") or ""),
        "text": text,
        "concept_id": str(record["concept_id"]) if record.get("concept_id") else None,
        "concept_name": record.get("concept_name") or None,
        "confidence": (
            float(record["confidence"])
            if record.get("confidence") is not None
            else None
        ),
        "detection_method": record.get("detection_method") or None,
        "assertion": assertion,
        "source_file": source_file,
        "exclusion_reason": exclusion_reason
        or record.get("exclusion_reason")
        or record.get("reason")
        or None,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Cross-label promotion
# ──────────────────────────────────────────────────────────────────────────────


def _cross_label_promotions(
    record: dict,
    source_milestone: str,
    source_file: str,
) -> list[dict[str, Any]]:
    """Return additional canonical records for other milestones where this
    record constitutes a positive example.

    Called only on records that are label=0 in their source file.
    """
    text = (
        record.get("evidence")
        or record.get("phrase_matched")
        or record.get("snippet")
        or ""
    )
    promoted = []

    # "Seen in fast track suspected X clinic" → positive for specialist_visit
    if source_milestone != "specialist_visit" and _FAST_TRACK_CLINIC_RE.search(text):
        promoted.append(_canonical(record, "specialist_visit", source_file, label=1))

    # "Fast track referral for suspected..." → positive for referral
    if source_milestone != "referral" and (
        _FAST_TRACK_REFERRAL_RE.search(text) or _2WW_REFERRAL_RE.search(text)
    ):
        # Don't promote if it already looks like a clinic attendance
        if not _FAST_TRACK_CLINIC_RE.search(text):
            promoted.append(_canonical(record, "referral", source_file, label=1))

    return promoted


# ──────────────────────────────────────────────────────────────────────────────
# File processing
# ──────────────────────────────────────────────────────────────────────────────

MILESTONE_FILES = {
    "referral": "referral_training.jsonl",
    "diagnosis": "diagnosis_training.jsonl",
    "treatment_start": "treatment_start_training.jsonl",
    "specialist_visit": "specialist_visit_training.jsonl",
}


def process_input_dir(input_dir: str, output_path: str) -> dict[str, Any]:
    input_dir_path = Path(input_dir)
    output_records: list[dict] = []

    stats: dict[str, Any] = {
        m: {"positives": 0, "negatives": 0, "promoted": 0} for m in MILESTONE_FILES
    }
    cross_promoted = 0

    for milestone, filename in MILESTONE_FILES.items():
        filepath = input_dir_path / filename
        if not filepath.exists():
            logger.warning("  %s not found — skipping", filepath)
            continue

        file_positives = 0
        file_negatives = 0
        file_promoted = 0

        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    continue

                label = raw.get("label", 1)
                source_file = filename

                # Emit canonical record for this milestone
                output_records.append(_canonical(raw, milestone, source_file))

                if label == 1:
                    file_positives += 1
                else:
                    file_negatives += 1
                    # Attempt cross-label promotion
                    promoted = _cross_label_promotions(raw, milestone, source_file)
                    for p in promoted:
                        output_records.append(p)
                        target_ms = p["milestone_type"]
                        stats[target_ms]["promoted"] += 1
                        file_promoted += 1
                        cross_promoted += 1

        stats[milestone]["positives"] = file_positives
        stats[milestone]["negatives"] = file_negatives
        logger.info(
            "  %-20s %4d pos  %4d neg  %4d cross-promoted",
            milestone,
            file_positives,
            file_negatives,
            file_promoted,
        )

    # Deduplicate: same encounter_id + milestone_type + label → keep first
    seen: set[tuple] = set()
    deduped: list[dict] = []
    for rec in output_records:
        key = (rec["encounter_id"], rec["milestone_type"], rec["label"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(rec)

    duplicates_removed = len(output_records) - len(deduped)

    with open(output_path, "w", encoding="utf-8") as f:
        for rec in deduped:
            f.write(json.dumps(rec, default=str) + "\n")

    logger.info("")
    logger.info("=" * 60)
    logger.info("NORMALISATION SUMMARY")
    logger.info("=" * 60)
    for m, s in stats.items():
        logger.info(
            "  %-20s pos=%d neg=%d promoted_in=%d",
            m,
            s["positives"],
            s["negatives"],
            s["promoted"],
        )
    logger.info("  Cross-label promotions total: %d", cross_promoted)
    logger.info("  Duplicates removed:           %d", duplicates_removed)
    logger.info("  Records written:              %d", len(deduped))
    logger.info("  Output: %s", output_path)
    logger.info("=" * 60)

    return {
        "per_milestone": stats,
        "cross_promoted": cross_promoted,
        "duplicates_removed": duplicates_removed,
        "total_records": len(deduped),
        "output_path": output_path,
    }


def main():
    parser = argparse.ArgumentParser(description="Normalise training JSONL files")
    parser.add_argument(
        "--input-dir",
        default="exports/training",
        help="Directory containing the four milestone training JSONL files",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSONL path (default: <input-dir>/all_training_merged.jsonl)",
    )
    args = parser.parse_args()

    output_path = args.output or str(Path(args.input_dir) / "all_training_merged.jsonl")
    logger.info("Normalising from %s → %s", args.input_dir, output_path)
    process_input_dir(args.input_dir, output_path)


if __name__ == "__main__":
    main()
