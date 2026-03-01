"""Shared post-processor rule engine for extracted/training entities."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


@dataclass(frozen=True)
class PostProcessorRule:
    rule_id: str
    priority: int
    action: str
    match_text: str | None
    match_label: str | None
    context_regex: str | None
    window_chars: int
    rewrite_text: str | None
    rewrite_label: str | None


def parse_rules(rows: list[dict[str, Any]]) -> list[PostProcessorRule]:
    parsed: list[PostProcessorRule] = []
    for row in rows:
        parsed.append(
            PostProcessorRule(
                rule_id=str(row.get("rule_id", "")),
                priority=int(row.get("priority", 100) or 100),
                action=str(row.get("action", "suppress") or "suppress"),
                match_text=(str(row.get("match_text")).strip() if row.get("match_text") else None),
                match_label=(str(row.get("match_label")).strip() if row.get("match_label") else None),
                context_regex=(str(row.get("context_regex")).strip() if row.get("context_regex") else None),
                window_chars=int(row.get("window_chars", 40) or 40),
                rewrite_text=(str(row.get("rewrite_text")).strip() if row.get("rewrite_text") else None),
                rewrite_label=(str(row.get("rewrite_label")).strip() if row.get("rewrite_label") else None),
            )
        )
    return sorted(parsed, key=lambda r: r.priority)


def _find_nearest_occurrence(haystack: str, needle: str, old_start: int) -> int | None:
    positions: list[int] = []
    p = haystack.find(needle)
    while p != -1:
        positions.append(p)
        p = haystack.find(needle, p + 1)
    if not positions:
        return None
    return min(positions, key=lambda v: abs(v - old_start))


def _matches_rule(
    encounter_text: str,
    entity: dict[str, Any],
    rule: PostProcessorRule,
) -> bool:
    ent_text = str(entity.get("text", "") or "")
    ent_label = str(entity.get("label", "") or "")

    if rule.match_text and ent_text.lower() != rule.match_text.lower():
        return False
    if rule.match_label and ent_label != rule.match_label:
        return False
    if rule.context_regex:
        try:
            start = int(entity.get("start", 0) or 0)
            end = int(entity.get("end", start) or start)
            lo = max(0, start - rule.window_chars)
            hi = min(len(encounter_text), end + rule.window_chars)
            context = encounter_text[lo:hi]
            if not re.search(rule.context_regex, context):
                return False
        except re.error:
            # Invalid regex in rule should fail closed for safety.
            return False
    return True


def apply_rules_to_entities(
    encounter_text: str,
    entities: list[dict[str, Any]],
    rules: list[PostProcessorRule],
) -> list[dict[str, Any]]:
    """Apply rules in priority order and return transformed entity list."""
    if not rules:
        return [dict(e) for e in entities]

    out: list[dict[str, Any]] = []
    for source_ent in entities:
        ent = dict(source_ent)
        drop = False

        for rule in rules:
            if not _matches_rule(encounter_text, ent, rule):
                continue

            if rule.action == "suppress":
                drop = True
                break

            if rule.action == "relabel":
                if rule.rewrite_label:
                    ent["label"] = rule.rewrite_label
                continue

            if rule.action == "rewrite":
                new_text = rule.rewrite_text or str(ent.get("text", ""))
                old_start = int(ent.get("start", 0) or 0)
                new_start = _find_nearest_occurrence(encounter_text, new_text, old_start)
                if new_start is not None:
                    ent["text"] = new_text
                    ent["start"] = new_start
                    ent["end"] = new_start + len(new_text)
                if rule.rewrite_label:
                    ent["label"] = rule.rewrite_label
                continue

        if not drop:
            out.append(ent)
    return out
