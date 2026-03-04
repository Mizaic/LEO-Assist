"""MedSpaCy ConText engine for clinical assertion detection.

Replaces the custom character-window regex detector with the ConText
graph algorithm, extended with UK primary care rules and two custom
categories:

  DECLINED    -- patient declined or refused (custom)
  CANCELLED   -- patient cancelled / did not attend / DNA (custom)
  REFUTED     -- initial impression overridden by investigation (custom)
  HYPOTHETICAL -- planned / awaiting, not yet completed (medspaCy built-in)

The spaCy pipeline is initialised once at module level and reused across
all encounters.

Safety: on any spaCy exception the pipeline raises immediately so that
callers never silently persist incorrect assertion values.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import spacy
from spacy.tokens import Span

if TYPE_CHECKING:
    from libs.ner.extractor_contract import ExtractionItem

logger = logging.getLogger(__name__)

_UK_RULES_PATH = Path(__file__).parent / "resources" / "uk_primary_care_context_rules.json"

# Span attribute mapping -- includes the custom DECLINED category.
# Span.set_extension("is_declined") must be called before ConText is added.
_SPAN_ATTRS: dict = {
    "NEGATED_EXISTENCE": {"is_negated": True},
    "POSSIBLE_EXISTENCE": {"is_uncertain": True},
    "HISTORICAL":         {"is_historical": True},
    "HYPOTHETICAL":       {"is_hypothetical": True},
    "FAMILY":             {"is_family": True},
    "DECLINED":           {"is_declined": True},
    "CANCELLED":          {"is_cancelled": True},
    "REFUTED":            {"is_refuted": True},
}

# Module-level singleton -- lazy-initialised on first call.
_nlp: spacy.language.Language | None = None


def _register_extensions() -> None:
    if not Span.has_extension("is_declined"):
        Span.set_extension("is_declined", default=False)
    if not Span.has_extension("is_cancelled"):
        Span.set_extension("is_cancelled", default=False)
    if not Span.has_extension("is_refuted"):
        Span.set_extension("is_refuted", default=False)


_CONTEXT_RULE_KEYS = frozenset(
    {"pattern", "category", "max_scope", "metadata", "max_targets",
     "literal", "excluded_types", "allowed_types", "direction"}
)


def _build_nlp() -> spacy.language.Language:
    """Create a blank spaCy pipeline with medspaCy ConText and UK rules."""
    from medspacy.context import ConTextRule

    _register_extensions()
    nlp = spacy.blank("en")
    context = nlp.add_pipe(
        "medspacy_context",
        config={"span_attrs": _SPAN_ATTRS, "max_scope": 10, "rules": "default"},
    )
    if _UK_RULES_PATH.exists():
        raw = json.loads(_UK_RULES_PATH.read_text(encoding="utf-8"))
        rules = []
        for entry in raw.get("context_rules", []):
            clean = {k: v for k, v in entry.items() if k in _CONTEXT_RULE_KEYS}
            rules.append(ConTextRule(**clean))
        context.add(rules)
        logger.info("Loaded %d UK ConText rules from %s", len(rules), _UK_RULES_PATH)
    else:
        logger.warning("UK ConText rules not found at %s", _UK_RULES_PATH)
    return nlp


def get_builtin_rules() -> list[dict[str, Any]]:
    """Return the shipped UK primary-care ConText rules as plain dicts.

    Each entry carries ``source="builtin"`` so callers can distinguish them
    from user-defined rules stored in Neo4j.
    """
    if not _UK_RULES_PATH.exists():
        logger.warning("Built-in context rules not found at %s", _UK_RULES_PATH)
        return []
    try:
        raw = json.loads(_UK_RULES_PATH.read_text(encoding="utf-8"))
        return [
            {
                "rule_id": None,
                "literal": r["literal"],
                "category": r["category"],
                "direction": r["direction"],
                "max_scope": r["max_scope"],
                "description": r.get("description", ""),
                "example": r.get("example", ""),
                "created_by": "system",
                "active": True,
                "created_at": None,
                "updated_at": None,
                "source": "builtin",
                "org_id": None,
            }
            for r in raw.get("context_rules", [])
        ]
    except Exception:
        logger.error("Failed to load built-in context rules", exc_info=True)
        return []


def _get_nlp() -> spacy.language.Language:
    global _nlp
    if _nlp is None:
        _nlp = _build_nlp()
    return _nlp


def _span_to_assertion(span: Span) -> str:
    """Map ConText span boolean flags to a priority-ordered assertion string.

    Priority: family > absent > refuted > declined > cancelled > historical > hypothetical > possible.
    """
    if span._.is_family:
        return "family"
    if span._.is_negated:
        return "absent"
    if span._.is_refuted:
        return "refuted"
    if span._.is_declined:
        return "declined"
    if span._.is_cancelled:
        return "cancelled"
    if span._.is_historical:
        return "historical"
    if span._.is_hypothetical:
        return "hypothetical"
    if span._.is_uncertain:
        return "possible"
    return "present"


def _make_pending_spans(
    doc: spacy.tokens.Doc,
    items: list[ExtractionItem],
    indices: list[int],
) -> list[tuple[int, Span]]:
    """Build (item_idx, Span) pairs for items that need context detection."""
    pending = []
    for idx in indices:
        item = items[idx]
        span = doc.char_span(
            item.span_start,
            item.span_end,
            label="ENTITY",
            alignment_mode="expand",
        )
        if span is not None:
            pending.append((idx, span))
    return pending


def _deduplicate_spans(
    pending: list[tuple[int, Span]],
) -> list[tuple[int, Span]]:
    """Remove overlapping spans, keeping the first occurrence per token."""
    seen: set[int] = set()
    result = []
    for idx, span in pending:
        tokens = set(range(span.start, span.end))
        if tokens & seen:
            continue
        seen.update(tokens)
        result.append((idx, span))
    return result


def apply_context_detection_to_dicts(
    encounter_text: str,
    entities: list[dict],
) -> None:
    """Apply ConText assertion detection to plain entity dicts, mutating in place.

    Each dict must have 'start' and 'end' character offsets.
    Only overwrites 'assertion' when the current value is 'present' or unset.
    Used by the label verifier which works with plain dicts, not ExtractionItems.
    Falls back silently on any spaCy error.
    """
    if not entities:
        return
    needs = [i for i, e in enumerate(entities) if (e.get("assertion") or "present") == "present"]
    if not needs:
        return
    try:
        nlp = _get_nlp()
        doc = nlp.make_doc(encounter_text)
        pending = []
        for idx in needs:
            ent = entities[idx]
            start = int(ent.get("start") or 0)
            end = int(ent.get("end") or start)
            span = doc.char_span(start, end, label="ENTITY", alignment_mode="expand")
            if span is not None:
                pending.append((idx, span))
        filtered = _deduplicate_spans(pending)
        doc.ents = [span for _, span in filtered]
        doc = nlp.get_pipe("medspacy_context")(doc)
        ent_assertion = {span.start: _span_to_assertion(span) for span in doc.ents}
        for item_idx, span in filtered:
            assertion = ent_assertion.get(span.start, "present")
            if assertion != "present":
                entities[item_idx]["assertion"] = assertion
    except Exception:
        logger.error(
            "ConText dict detection FAILED for %d entities -- aborting",
            len(needs),
            exc_info=True,
        )
        raise


def detect_assertions_for_encounter(
    encounter_text: str,
    items: list[ExtractionItem],
) -> tuple[list[str], bool]:
    """Return assertion strings for each ExtractionItem plus a failure flag.

    Items that already carry a non-'present' assertion are returned unchanged.
    On any spaCy exception, affected entities are marked 'possible' (uncertain)
    so they enter the assertion review queue rather than being silently coded.

    Args:
        encounter_text: Full de-identified encounter text.
        items: ExtractionItems with span_start / span_end character offsets.

    Returns:
        Tuple of (assertions list, context_detection_failed bool).
        assertions has the same length and order as items.
        context_detection_failed is True if spaCy raised an exception.
    """
    if not items:
        return [], False

    needs = [i for i, it in enumerate(items) if (it.assertion or "present") == "present"]
    defaults = [it.assertion or "present" for it in items]
    if not needs:
        return defaults, False

    try:
        nlp = _get_nlp()
        doc = nlp.make_doc(encounter_text)
        pending = _make_pending_spans(doc, items, needs)
        filtered = _deduplicate_spans(pending)

        doc.ents = [span for _, span in filtered]
        doc = nlp.get_pipe("medspacy_context")(doc)

        ent_assertion = {span.start: _span_to_assertion(span) for span in doc.ents}
        for item_idx, span in filtered:
            defaults[item_idx] = ent_assertion.get(span.start, "present")
        return defaults, False

    except Exception:
        logger.error(
            "ConText detection FAILED for encounter (%d entities) -- aborting",
            len(needs),
            exc_info=True,
        )
        raise
