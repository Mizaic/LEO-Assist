"""Span closure: complete partial lab/vitals nested triples and deduplicate.

When the LLM emits only 1 or 2 of the expected 3 spans for a lab/vitals
line, this module deterministically supplies the missing span using
libs.training.lab_span_detector. It also deduplicates across deterministic
and LLM-emitted entities.

Deduplication key: (sentence_id, labels_frozenset, quote_lower).
"""

from __future__ import annotations

from typing import Any

from libs.training.lab_span_detector import detect_lab_pattern


def _entity_key(e: dict[str, Any]) -> tuple:
    labels = frozenset(l.upper() for l in (e.get("labels") or []))
    quote = (e.get("quote") or "").strip().lower()
    return (e.get("sentence_id"), labels, quote)


def _find_sentence_text(
    sentences: list[dict[str, Any]],
    sentence_id: int,
) -> str:
    for s in sentences:
        if s.get("sentence_id") == sentence_id:
            return s.get("text") or ""
    return ""


def _has_label(entities: list[dict[str, Any]], sid: int, label: str) -> bool:
    label_up = label.upper()
    for e in entities:
        if e.get("sentence_id") != sid:
            continue
        if label_up in {l.upper() for l in (e.get("labels") or [])}:
            return True
    return False


def close_lab_triples(
    entities: list[dict[str, Any]],
    sentences: list[dict[str, Any]],
    id_prefix: str = "c",
) -> list[dict[str, Any]]:
    """Add any missing PROCEDURE/OBSERVABLE_ENTITY/FINDING spans per R1.

    Only adds spans for sentences that already have at least one of the
    three lab labels (indicating the sentence was identified as a lab line).
    """
    added: list[dict[str, Any]] = []
    idx = 1

    # Group entities by sentence_id
    sids_with_lab: set[int] = set()
    for e in entities:
        labels_up = {l.upper() for l in (e.get("labels") or [])}
        if labels_up & {"PROCEDURE", "OBSERVABLE_ENTITY", "FINDING"}:
            if e.get("source") == "deterministic" or True:
                sids_with_lab.add(e.get("sentence_id", -1))

    for sid in sorted(sids_with_lab):
        text = _find_sentence_text(sentences, sid)
        if not text:
            continue
        pattern = detect_lab_pattern(text)
        if not pattern.matched or pattern.test_name_span is None:
            continue

        if not _has_label(entities, sid, "PROCEDURE"):
            ts = pattern.test_name_span
            quote = text[ts.start:ts.end].strip() or ts.text
            added.append({
                "id":          f"{id_prefix}{idx}",
                "sentence_id": sid,
                "quote":       quote,
                "labels":      ["PROCEDURE"],
                "assertion":   "present",
                "rationale":   "span_closure R1 procedure",
                "source":      "span_closure",
            })
            idx += 1

        if pattern.observable_span and not _has_label(entities, sid, "OBSERVABLE_ENTITY"):
            obs = pattern.observable_span
            obs_text = text[obs.start:obs.end].strip() or obs.text
            added.append({
                "id":          f"{id_prefix}{idx}",
                "sentence_id": sid,
                "quote":       obs_text,
                "labels":      ["OBSERVABLE_ENTITY"],
                "assertion":   "present",
                "rationale":   "span_closure R1 observable",
                "source":      "span_closure",
            })
            idx += 1

        if pattern.finding_span and not _has_label(entities, sid, "FINDING"):
            fnd = pattern.finding_span
            fnd_text = text[fnd.start:fnd.end].strip() or fnd.text
            added.append({
                "id":          f"{id_prefix}{idx}",
                "sentence_id": sid,
                "quote":       fnd_text,
                "labels":      ["FINDING"],
                "assertion":   "present",
                "rationale":   "span_closure R1 finding",
                "source":      "span_closure",
            })
            idx += 1

    return added


def deduplicate(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove exact duplicates keeping the first seen. Renumber ids."""
    seen: set[tuple] = set()
    out: list[dict[str, Any]] = []
    for e in entities:
        key = _entity_key(e)
        if key in seen:
            continue
        seen.add(key)
        out.append(e)

    # Renumber ids e1, e2, ...
    for i, e in enumerate(out, start=1):
        e["id"] = f"e{i}"
    return out


def merge_and_close(
    structured_entities: list[dict[str, Any]],
    structured_missing: list[dict[str, Any]],
    narrative_entities: list[dict[str, Any]],
    sentences: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge deterministic + LLM-verified structured + narrative, then close."""
    combined = structured_entities + structured_missing + narrative_entities
    closure = close_lab_triples(combined, sentences)
    combined = combined + closure
    return deduplicate(combined)
