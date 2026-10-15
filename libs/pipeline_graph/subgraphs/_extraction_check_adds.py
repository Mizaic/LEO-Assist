"""Facts the extraction check adds: verbatim, and never from a hidden line.

The extraction check reads the raw letter, so it can see lines the form
normaliser marked non-extractable. An added fact must appear in the text
the main extraction was shown (``llm_facing_text`` of each sentence), or a
sealed guidance line such as "please arrange FBC, U&Es & eGFR" comes back
as a planned test.

Atlas trace:
  DO: DO-8620A68B, DO-E2F2B277
  DI: DI-5C9CA57B
  VT: VT-1B2063CC
"""

from __future__ import annotations

import re
from typing import Any

from libs.ner.form_layout_rules import llm_facing_text
from libs.nlp.sentence_splitter import is_referral_procedure_phrase

_SPACE_RE = re.compile(r"\s+")


def _label_is_procedure(label: str) -> bool:
    return label.strip().lower().replace(" ", "_") == "procedure"


def normalise_referral_procedure_assertion(
    *,
    label: str,
    text: str,
    assertion: str,
) -> str:
    cleaned_assertion = assertion.strip().lower()
    if (
        cleaned_assertion == "possible"
        and _label_is_procedure(label)
        and is_referral_procedure_phrase(text)
    ):
        return "present"
    return cleaned_assertion


def _squash(text: str) -> str:
    return _SPACE_RE.sub(" ", text).strip().lower()


def usable_text(sentences: list[dict[str, Any]] | None) -> str | None:
    """Return the text the extraction model was shown, or None if unknown."""
    if not sentences:
        return None
    shown = (llm_facing_text(str(s.get("text") or "")) for s in sentences)
    return _squash("\n".join(shown))


def _resolve_span(encounter_text: str, needle: str) -> tuple[int, int]:
    cleaned = needle.strip()
    if not cleaned:
        return 0, 1
    idx = encounter_text.lower().find(cleaned.lower())
    if idx >= 0:
        return idx, idx + len(cleaned)
    return 0, len(cleaned)


def _rejection(text: str, encounter_text: str, usable: str | None) -> str | None:
    if text.lower() not in encounter_text.lower():
        return "not_verbatim_in_text"
    if usable is not None and _squash(text) not in usable:
        return "only_on_non_extractable_line"
    return None


def _new_entity(row: dict[str, Any], text: str, encounter_text: str) -> dict:
    label = str(row.get("label") or "").strip()
    start, end = _resolve_span(encounter_text, text)
    assertion = str(row.get("assertion") or "present")
    final_assertion = normalise_referral_procedure_assertion(
        label=label, text=text, assertion=assertion
    )
    entity = {
        "text": text,
        "label": label,
        "semantic_tag": label,
        "start": start,
        "end": end,
        "assertion": final_assertion,
        "confidence": float(row.get("confidence") or 0.6),
        "normalized": str(row.get("lookup_term") or text),
        "lookup_term": str(row.get("lookup_term") or text),
        "_llm_check_source": "llm_added",
    }
    if final_assertion != assertion.strip().lower():
        entity["_assertion_guard"] = "referral_procedure"
    return entity


def apply_added_entities(
    rows: Any,
    encounter_text: str,
    sentences: list[dict[str, Any]] | None,
    entities: list[dict[str, Any]],
    changes: list[dict[str, Any]],
) -> None:
    """Append each valid added fact to *entities*; record every decision."""
    usable = usable_text(sentences)
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        text = str(row.get("text") or "").strip()
        label = str(row.get("label") or "").strip()
        if not text or not label:
            continue
        reason = _rejection(text, encounter_text, usable)
        if reason:
            changes.append({"type": "drop_add", "text": text, "reason": reason})
            continue
        entities.append(_new_entity(row, text, encounter_text))
        changes.append({"type": "added", "text": text, "label": label})
