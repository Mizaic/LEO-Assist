"""Recover mis-tagged anthropometry names as observables with value and unit.

Atlas trace:
  DI: DI-B5C78811
  DO: DO-728930A1
  VT: VT-E6BD0CA9
  Look up via: get_design_control(dc_type="verification-test", dc_id="VT-E6BD0CA9")

The extractor sometimes splits "- Current weight: 67 kg" into a procedure
name and a stray qualifier_value. This layer retags the name as
observable_entity, stores value/unit on that entity, and drops the orphan
number so terminology can resolve the observable SNOMED code.
"""

from __future__ import annotations

import re
from typing import Any

_MIS_TAGS = frozenset(
    {"procedure", "finding", "qualifier_value", "situation", "observable_entity"}
)

_NAME_TO_LOOKUP = {
    "weight": "body weight",
    "current weight": "current body weight",
    "body weight": "body weight",
    "measured weight": "body weight",
    "height": "body height",
    "current height": "body height",
    "body height": "body height",
    "bmi": "body mass index",
    "body mass index": "body mass index",
}

_BULLET_PREFIX = re.compile(r"^[\-\*\|\u2022]+\s*")
_VALUE_UNIT_RE = re.compile(
    r"(?P<value>[<>]?\s*\d+(?:\.\d+)?)\s*" r"(?P<unit>kg\/m(?:2|\^2)?|cm|mm|kg|g|m)\b",
    re.IGNORECASE,
)
_NEAR_CHARS = 80


def _clean_name(text: str) -> str:
    stripped = _BULLET_PREFIX.sub("", (text or "").strip())
    return stripped.strip(" :").lower()


def _ascii_unit(unit: str) -> str:
    cleaned = (unit or "").replace("\u00b2", "2").replace("\u00b3", "3")
    return cleaned.strip()


def _parse_value_unit(text: str) -> tuple[str, str] | None:
    hay = _ascii_unit(text or "")
    match = _VALUE_UNIT_RE.search(hay)
    if not match:
        return None
    value = (match.group("value") or "").strip()
    unit = _ascii_unit(match.group("unit") or "")
    if not value or not unit:
        return None
    return value, unit


def _normalise_unit(name: str, unit: str) -> str:
    lowered = unit.lower()
    if name == "bmi" or name == "body mass index":
        if lowered in {"kg/m", "kg/m2", "kg/m^2"}:
            return "kg/m2"
    return unit


def _value_from_line(encounter_text: str, name: str) -> tuple[str, str] | None:
    if not encounter_text or not name:
        return None
    needle = name.lower()
    for raw_line in encounter_text.splitlines():
        lower = raw_line.lower()
        idx = lower.find(needle)
        if idx < 0:
            continue
        parsed = _parse_value_unit(raw_line[idx + len(name) :])
        if parsed:
            return parsed
    return None


def _offset_ok(ent: dict[str, Any]) -> bool:
    start = int(ent.get("start", 0) or 0)
    end = int(ent.get("end", 0) or 0)
    return end > start


def _char_dist(left: dict[str, Any], right: dict[str, Any]) -> int:
    l_start = int(left.get("start", 0) or 0)
    l_end = int(left.get("end", 0) or 0)
    r_start = int(right.get("start", 0) or 0)
    r_end = int(right.get("end", 0) or 0)
    return min(abs(l_start - r_end), abs(r_start - l_end))


def _value_from_nearby(
    name_ent: dict[str, Any], entities: list[dict[str, Any]]
) -> tuple[str, str, int] | None:
    if not _offset_ok(name_ent):
        return None
    best: tuple[int, str, str, int] | None = None
    for idx, ent in enumerate(entities):
        if ent is name_ent or ent.get("__suppress__"):
            continue
        if not _offset_ok(ent):
            continue
        parsed = _parse_value_unit(str(ent.get("text") or ""))
        if not parsed:
            continue
        dist = _char_dist(name_ent, ent)
        if dist > _NEAR_CHARS:
            continue
        if best is None or dist < best[0]:
            best = (dist, parsed[0], parsed[1], idx)
    if best is None:
        return None
    return best[1], best[2], best[3]


def _suppress_orphan(
    entities: list[dict[str, Any]],
    value: str,
    unit: str,
    keep: dict[str, Any],
    used_idx: int | None,
) -> None:
    want = f"{value}{_normalise_unit('bmi', unit)}".lower().replace(" ", "")
    for idx, ent in enumerate(entities):
        if ent is keep or idx == used_idx:
            continue
        parsed = _parse_value_unit(str(ent.get("text") or ""))
        if not parsed:
            continue
        got = f"{parsed[0]}{_normalise_unit('bmi', parsed[1])}".lower().replace(" ", "")
        if got != want:
            continue
        label = str(ent.get("label") or "")
        if label in {"qualifier_value", "observable_entity"}:
            ent["__suppress__"] = True


def _apply_observable(
    ent: dict[str, Any],
    *,
    name: str,
    lookup: str,
    value: str,
    unit: str,
) -> None:
    ent["label"] = "observable_entity"
    ent["semantic_tag"] = "observable entity"
    ent["text"] = name
    ent["lookup_term"] = lookup
    ent["normalized"] = lookup
    ent["value"] = value
    ent["unit"] = _normalise_unit(name, unit)


def recover_measurement_observables(
    encounter_text: str,
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Retag measurement names and attach nearby value/unit. Returns survivors."""
    for ent in entities:
        if ent.get("__suppress__"):
            continue
        label = str(ent.get("label") or "").replace(" ", "_")
        if label not in _MIS_TAGS:
            continue
        name = _clean_name(str(ent.get("text") or ""))
        lookup = _NAME_TO_LOOKUP.get(name)
        if not lookup:
            continue
        if label == "observable_entity" and ent.get("value") and ent.get("unit"):
            if name != str(ent.get("text") or "").strip().lower():
                ent["text"] = name
                ent["lookup_term"] = lookup
            continue
        nearby = _value_from_nearby(ent, entities)
        parsed = _value_from_line(encounter_text, name)
        used_idx: int | None = None
        if parsed is None and nearby:
            parsed = (nearby[0], nearby[1])
            used_idx = nearby[2]
        if parsed is None:
            continue
        value, unit = parsed
        _apply_observable(ent, name=name, lookup=lookup, value=value, unit=unit)
        if used_idx is not None:
            entities[used_idx]["__suppress__"] = True
        _suppress_orphan(entities, value, unit, ent, used_idx)
    return [e for e in entities if not e.get("__suppress__")]
