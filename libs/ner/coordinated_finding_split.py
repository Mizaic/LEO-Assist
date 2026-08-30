"""Split coordinated findings so each span is one clinical fact.

Atlas trace:
  DI: DI-B5C78811
  DO: DO-728930A1
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-B5C78811")

A span such as "no adnexal mass or free fluid" cannot be coded as one
SNOMED concept. This layer cuts those spans before terminology lookup.
It does not split measurements, brand products, or PMB.
"""

from __future__ import annotations

import re
from typing import Any

_KEEP_WHOLE = re.compile(
    r"post[- ]?menopausal bleeding|\bpmb\b|"
    r"\d|"
    r"\bltd\b|ointment|dressing|inhaler|patches|"
    r"albuminuria|gfr category",
    re.IGNORECASE,
)

_OF_THE_OR = re.compile(
    r"^(?P<pre>no abnormalities of the )"
    r"(?P<a>[a-z][a-z \-]+?)"
    r" or "
    r"(?P<b>[a-z][a-z \-]+)$",
    re.IGNORECASE,
)

_NO_OR = re.compile(
    r"^(?P<pre>no |nil )"
    r"(?P<a>[a-z][a-z \-]{2,}(?: [a-z][a-z \-]{1,})+)"
    r" or "
    r"(?P<b>[a-z][a-z \-]{2,}(?: [a-z][a-z \-]{1,})+)$",
    re.IGNORECASE,
)

_SLASH_PAIR = re.compile(
    r"^(?P<pre>[a-z]+ )"
    r"(?P<a>itch|pain|dryness|soreness|bleeding)"
    r"/"
    r"(?P<b>itch|pain|dryness|soreness|bleeding)$",
    re.IGNORECASE,
)

_SHORT_AND = re.compile(
    r"^(?P<a>[A-Za-z]{2,8})"
    r" and "
    r"(?P<b>[A-Za-z]{3,20})$",
)

_WORD_COUNT = re.compile(r"[A-Za-z]{2,}")


def _word_count(text: str) -> int:
    return len(_WORD_COUNT.findall(text))


def _keep_whole(text: str, label: str) -> bool:
    if _KEEP_WHOLE.search(text):
        return True
    return label.lower() in {"product", "clinical_drug", "substance"}


def _parts_for(text: str, label: str) -> list[str] | None:
    if _keep_whole(text, label):
        return None
    match = _OF_THE_OR.match(text.strip())
    if match:
        pre = match.group("pre")
        return [pre + match.group("a").strip(), pre + match.group("b").strip()]
    match = _NO_OR.match(text.strip())
    if match:
        pre = match.group("pre")
        left = match.group("a").strip()
        right = match.group("b").strip()
        if _word_count(left) >= 2 and _word_count(right) >= 2:
            return [pre + left, pre + right]
        return None
    match = _SLASH_PAIR.match(text.strip())
    if match:
        pre = match.group("pre")
        return [pre + match.group("a"), pre + match.group("b")]
    match = _SHORT_AND.match(text.strip())
    if match:
        return [match.group("a"), match.group("b")]
    return None


def _child(entity: dict[str, Any], text: str) -> dict[str, Any]:
    child = dict(entity)
    child["text"] = text
    child["end"] = int(entity.get("start") or 0) + len(text)
    child["normalized"] = text.lower()
    child["lookup_term"] = text
    child["normalized_lookup"] = text.lower()
    child["_coordinated_split"] = True
    return child


def split_coordinated_findings(
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Cut coordinated finding spans into one fact each."""
    out: list[dict[str, Any]] = []
    for entity in entities:
        text = str(entity.get("text") or "")
        label = str(entity.get("label") or entity.get("semantic_tag") or "")
        parts = _parts_for(text, label)
        if not parts:
            out.append(entity)
            continue
        out.extend(_child(entity, part) for part in parts)
    return out
