"""Compact facts/codes preview for Validation Lab pipeline spans.

Atlas trace:
  DO: DO-158BE606
  DI: DI-257D6883
  VT: VT-825F42CC
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
"""

from __future__ import annotations

from typing import Any

_MAX_ITEMS = 8
_MAX_COMPACT_ENTITIES = 40
_MAX_COMPACT_STRING = 1500
_SBAR_KEYS = ("situation", "background", "assessment", "recommendation")
_TEXT_KEYS = (
    "text",
    "surface",
    "mention",
    "term",
    "entity_text",
    "preferred_term",
    "lookup_term",
)
_CODE_KEYS = ("concept_id", "snomed_concept_id", "code", "conceptId")
_SENTENCE_KEYS = ("evidence_sentence", "sentence", "sentence_text")


def stage_work_preview(
    output: Any,
    input_data: Any | None = None,
) -> dict[str, Any]:
    """Return a short headline plus fact/code chips from stage JSON."""
    payload = output if isinstance(output, dict) else {}
    source = input_data if isinstance(input_data, dict) else {}
    sentences = _sentence_rows(payload) or _sentence_rows(source)
    items = _entity_items(payload, sentences) or _entity_items(source, sentences)
    sbar_items = _sbar_items(payload)
    chosen = items or sbar_items
    return {
        "headline": _headline(payload, items, sbar_items),
        "items": chosen[:_MAX_ITEMS],
    }


def compact_inspector_payload(payload: Any) -> dict[str, Any]:
    """Keep facts/codes when stage JSON is too large for the inspector."""
    if not isinstance(payload, dict):
        return {}
    compact: dict[str, Any] = {}
    for key, value in payload.items():
        compact[key] = _compact_value(key, value)
    return compact


def _compact_value(key: str, value: Any) -> Any:
    if key == "entities" and isinstance(value, list):
        rows = [_compact_entity(row) for row in value]
        return [item for item in rows if item][:_MAX_COMPACT_ENTITIES]
    if key in ("sbar_report", "sbar_sections") and isinstance(value, dict):
        return {name: _clip(str(text or ""), 400) for name, text in value.items()}
    if isinstance(value, str) and len(value) > _MAX_COMPACT_STRING:
        return _clip(value, _MAX_COMPACT_STRING)
    return value


def _compact_entity(row: Any) -> dict[str, str]:
    if not isinstance(row, dict):
        return {}
    text = _first_str(row, _TEXT_KEYS)
    code = _entity_code(row)
    item: dict[str, str] = {}
    if text:
        item["text"] = text
    if code:
        item["concept_id"] = code
    _copy_evidence_fields(row, item, text)
    return item


def _copy_evidence_fields(row: dict[str, Any], item: dict[str, str], text: str) -> None:
    evidence = _first_str(row, ("evidence",)) or text
    if evidence:
        item["evidence"] = evidence
    sentence = _first_str(row, _SENTENCE_KEYS)
    if sentence:
        item["evidence_sentence"] = sentence
    sid = str(row.get("__sentence_id") or "").strip()
    if sid:
        item["__sentence_id"] = sid


def _sentence_rows(payload: dict[str, Any]) -> list[Any]:
    raw = payload.get("sentences")
    return raw if isinstance(raw, list) else []


def _entity_items(
    payload: dict[str, Any], sentences: list[Any] | None = None
) -> list[dict[str, str]]:
    raw = payload.get("entities")
    if not isinstance(raw, list):
        return []
    sentence_rows = sentences if sentences is not None else _sentence_rows(payload)
    items: list[dict[str, str]] = []
    for ent in raw:
        if not isinstance(ent, dict):
            continue
        text = _first_str(ent, _TEXT_KEYS)
        if not text:
            continue
        items.append(_work_item(ent, text, sentence_rows))
    return items


def _work_item(ent: dict[str, Any], text: str, sentences: list[Any]) -> dict[str, str]:
    code = _entity_code(ent)
    item = {"kind": "code" if code else "fact", "text": text}
    if code:
        item["code"] = code
    evidence = _first_str(ent, ("evidence",)) or text
    if evidence:
        item["evidence"] = evidence
    sentence = _first_str(ent, _SENTENCE_KEYS) or _sentence_for(ent, sentences)
    if sentence:
        item["evidenceSentence"] = sentence
    return item


def _sentence_for(ent: dict[str, Any], sentences: list[Any]) -> str:
    sid = str(ent.get("__sentence_id") or ent.get("sentence_id") or "").strip()
    if not sid:
        return ""
    for row in sentences:
        if not isinstance(row, dict):
            continue
        row_id = str(row.get("sentence_id") or row.get("id") or "").strip()
        if row_id == sid:
            return str(row.get("text") or "").strip()
    return ""


def _entity_code(row: dict[str, Any]) -> str:
    code = _first_str(row, _CODE_KEYS)
    if code:
        return code
    coding = row.get("coding")
    if isinstance(coding, dict):
        return _first_str(coding, _CODE_KEYS)
    return ""


def _sbar_items(payload: dict[str, Any]) -> list[dict[str, str]]:
    report = payload.get("sbar_report")
    sections = report if isinstance(report, dict) else payload.get("sbar_sections")
    if not isinstance(sections, dict):
        return []
    items: list[dict[str, str]] = []
    for key in _SBAR_KEYS:
        text = str(sections.get(key) or "").strip()
        if not text:
            continue
        items.append({"kind": "sbar", "text": f"{key}: {_clip(text, 80)}"})
    return items


def _headline(
    payload: dict[str, Any],
    entities: list[dict[str, str]],
    sbar_items: list[dict[str, str]],
) -> str:
    if entities:
        coded = sum(1 for item in entities if item.get("kind") == "code")
        noun = "fact" if len(entities) == 1 else "facts"
        if coded:
            return f"Coded {coded} of {len(entities)} {noun}"
        return f"Found {len(entities)} {noun}"
    if isinstance(payload.get("entities"), list):
        return "Found 0 facts"
    if sbar_items:
        return f"Drafted {len(sbar_items)} of 4 sections"
    status = str(payload.get("sbar_status") or "").strip()
    if status == "error":
        return "Draft assessment failed"
    return ""


def _first_str(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _clip(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return f"{text[: max_len - 3]}..."
