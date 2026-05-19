"""Gold-label granularity helpers for NER training data repair.

These helpers keep whole-note or partial annotations out of the spaCy
training export. A spancat example is treated as exhaustive, so any
unlabelled candidate span in a long note becomes negative training signal.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from libs.nlp.sentence_splitter import SentenceChunk, SentenceSplitter

MAX_SAFE_TRAINING_CHARS = 500
MAX_DERIVED_WINDOW_CHARS = 500

_SECTION_MARKER_RE = re.compile(
    r"\b(?:History|Plan|Diagnosis|Examination|Clinical Information|Problem):",
    re.IGNORECASE,
)
_POSITIVE_LOOKING_RE = re.compile(
    r"\b(?:psa|egfr|acr|tsh|b12|referral|2ww|xray|mri|ct|ultrasound|uss|"
    r"booster|testing|blood test|urine dip|stool sample|weight loss|"
    r"nipple|discharge|pain|infection|braf|biopsy)\b",
    re.IGNORECASE,
)
_ADMIN_NOISE_RE = re.compile(
    r"\b(?:New Patient Registration|Consent to SMS|Consent to Email|"
    r"Summary Care Record|Enhanced review indicated|PDSPreviously unset|"
    r"short message service text message sent to patient)\b",
    re.IGNORECASE,
)
_LAB_INTERPRETATION_RE = re.compile(
    r"^(?:outside reference range|within reference range|normal|abnormal|"
    r"borderline|satisfactory|no further action)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GoldGranularity:
    classification: str
    reason: str
    safe_for_training: bool


def parse_entities_json(raw: str | None) -> list[dict[str, Any]]:
    """Parse an entities_json payload, returning an empty list on bad input."""
    try:
        parsed = json.loads(raw or "[]")
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def classify_gold_record(
    text: str,
    entities: list[dict[str, Any]] | str | None,
    *,
    training_quarantined: bool = False,
    annotation_completeness: str | None = None,
) -> GoldGranularity:
    """Classify whether a GoldLabel is safe as a complete training example."""
    completeness = str(annotation_completeness or "").strip().lower()
    if training_quarantined:
        return GoldGranularity("quarantined", "training_quarantined", False)
    if completeness in {"complete", "derived_sentence", "sentence_ok"}:
        return GoldGranularity(completeness, "explicitly_complete", True)
    if completeness in {"partial", "partial_long_context", "needs_review"}:
        return GoldGranularity(completeness, "annotation_marked_partial", False)

    entity_list = parse_entities_json(entities) if isinstance(entities, str) else (entities or [])
    stripped = (text or "").strip()
    if not entity_list:
        if _POSITIVE_LOOKING_RE.search(stripped):
            return GoldGranularity("needs_review", "empty_positive_looking", False)
        return GoldGranularity("true_negative_candidate", "empty_no_target_signal", False)

    if _is_unsafe_long_context(stripped):
        return GoldGranularity("needs_split", "long_or_multi_section_context", False)
    return GoldGranularity("sentence_ok", "short_context_with_entities", True)


def safe_for_training_export(
    text: str,
    entities: list[dict[str, Any]],
    *,
    training_quarantined: bool = False,
    annotation_completeness: str | None = None,
) -> bool:
    """Return True when a record can be exported as an exhaustive example."""
    return classify_gold_record(
        text,
        entities,
        training_quarantined=training_quarantined,
        annotation_completeness=annotation_completeness,
    ).safe_for_training


def split_training_windows(text: str) -> list[SentenceChunk]:
    """Split clinical text into training-sized windows.

    Uses the canonical splitter first, then breaks oversized chunks on physical
    lines while preserving lab interpretation continuations.
    """
    splitter = SentenceSplitter()
    chunks = splitter.split(text)
    windows: list[SentenceChunk] = []
    for chunk in chunks:
        if not _is_unsafe_long_context(chunk.text):
            windows.append(chunk)
            continue
        windows.extend(_split_chunk_on_lines(text, chunk))
    return windows


def derive_sentence_records(
    *,
    parent_label_id: str,
    parent_candidate_id: str,
    text: str,
    entities: list[dict[str, Any]],
    repair_run_id: str,
) -> list[dict[str, Any]]:
    """Derive sentence/window-level records that contain existing entities."""
    windows = split_training_windows(text)
    derived: list[dict[str, Any]] = []
    for idx, window in enumerate(windows):
        remapped = [
            _remap_entity(ent, window.start, window.end)
            for ent in entities
            if _entity_inside(ent, window.start, window.end)
        ]
        remapped = [ent for ent in remapped if ent is not None]
        if not remapped:
            continue
        derived.append(
            {
                "parent_label_id": parent_label_id,
                "parent_candidate_id": parent_candidate_id,
                "repair_run_id": repair_run_id,
                "window_index": idx,
                "text": window.text,
                "entities": remapped,
            }
        )
    return derived


def _is_unsafe_long_context(text: str) -> bool:
    if len(text) >= MAX_SAFE_TRAINING_CHARS:
        return True
    if "\n" in text and _SECTION_MARKER_RE.search(text):
        return True
    return False


def _split_chunk_on_lines(full_text: str, chunk: SentenceChunk) -> list[SentenceChunk]:
    windows: list[SentenceChunk] = []
    current_start: int | None = None
    current_end: int | None = None
    for match in re.finditer(r"[^\n]+", full_text[chunk.start : chunk.end]):
        line_start = chunk.start + match.start()
        line_end = chunk.start + match.end()
        line = full_text[line_start:line_end].strip()
        if not line:
            continue
        should_join = (
            current_start is not None
            and _LAB_INTERPRETATION_RE.search(line) is not None
            and (line_end - current_start) <= MAX_DERIVED_WINDOW_CHARS
        )
        if should_join:
            current_end = line_end
            continue
        if current_start is not None and current_end is not None:
            windows.append(_make_chunk(full_text, current_start, current_end, len(windows)))
        current_start = line_start
        current_end = line_end
    if current_start is not None and current_end is not None:
        windows.append(_make_chunk(full_text, current_start, current_end, len(windows)))
    return windows


def _make_chunk(text: str, start: int, end: int, idx: int) -> SentenceChunk:
    return SentenceChunk(
        sentence_id=f"training_window_{idx}",
        text=text[start:end].strip(),
        start=start,
        end=end,
    )


def _entity_inside(ent: dict[str, Any], start: int, end: int) -> bool:
    try:
        ent_start = int(ent.get("start", 0))
        ent_end = int(ent.get("end", 0))
    except (TypeError, ValueError):
        return False
    return start <= ent_start and ent_end <= end and ent_end > ent_start


def _remap_entity(ent: dict[str, Any], start: int, end: int) -> dict[str, Any] | None:
    if not _entity_inside(ent, start, end):
        return None
    remapped = dict(ent)
    remapped["start"] = int(remapped.get("start", 0)) - start
    remapped["end"] = int(remapped.get("end", 0)) - start
    return remapped
