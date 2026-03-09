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
# Call reload_nlp() after creating/deactivating Neo4j ContextRule nodes so the
# pipeline picks up changes without a full service restart.
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


def _build_nlp(extra_rules: list[dict] | None = None) -> spacy.language.Language:
    """Create a blank spaCy pipeline with medspaCy ConText and UK rules.

    Args:
        extra_rules: Optional list of additional rule dicts (e.g. fetched from
            Neo4j) to append after the built-in JSON rules.  Each dict must
            contain at least ``literal``, ``category``, ``direction``, and
            ``max_scope`` keys — the same shape returned by ``GET_CONTEXT_RULES``.
    """
    from medspacy.context import ConTextRule

    _register_extensions()
    nlp = spacy.blank("en")
    nlp.add_pipe("sentencizer")
    context = nlp.add_pipe(
        "medspacy_context",
        config={"span_attrs": _SPAN_ATTRS, "max_scope": 10, "rules": "default"},
    )

    # ── Built-in rules from the shipped JSON file ────────────────────────────
    builtin_rules: list[ConTextRule] = []
    if _UK_RULES_PATH.exists():
        raw = json.loads(_UK_RULES_PATH.read_text(encoding="utf-8"))
        for entry in raw.get("context_rules", []):
            clean = {k: v for k, v in entry.items() if k in _CONTEXT_RULE_KEYS}
            builtin_rules.append(ConTextRule(**clean))
        logger.info("Loaded %d built-in UK ConText rules from %s", len(builtin_rules), _UK_RULES_PATH)
    else:
        logger.warning("Built-in UK ConText rules not found at %s", _UK_RULES_PATH)

    # ── Custom rules injected by the caller (e.g. from Neo4j) ───────────────
    custom_rules: list[ConTextRule] = []
    for entry in (extra_rules or []):
        try:
            clean = {k: v for k, v in entry.items() if k in _CONTEXT_RULE_KEYS}
            custom_rules.append(ConTextRule(**clean))
        except Exception:
            logger.warning("Skipping malformed custom ConText rule: %s", entry, exc_info=True)
    if custom_rules:
        logger.info("Loaded %d custom ConText rules from Neo4j", len(custom_rules))

    all_rules = builtin_rules + custom_rules
    if all_rules:
        context.add(all_rules)

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


def _fetch_neo4j_rules() -> list[dict]:
    """Fetch active custom ContextRule nodes from the Patient Graph.

    Returns an empty list (and logs a warning) if the DB is unreachable so that
    the engine can still run on built-in rules alone.
    """
    try:
        from libs.cypher.coding_review_queries import GET_CONTEXT_RULES
        from libs.neo4j_client.client import PatientGraphClient  # noqa: PLC0415

        client = PatientGraphClient()
        try:
            with client.session() as session:
                rows = list(session.run(GET_CONTEXT_RULES, active_only=True, org_id=None))
            return [dict(r) for r in rows]
        finally:
            client.close()
    except Exception:
        logger.warning(
            "Could not fetch custom ConText rules from Neo4j — running on built-in rules only",
            exc_info=True,
        )
        return []


def _get_nlp() -> spacy.language.Language:
    global _nlp
    if _nlp is None:
        custom = _fetch_neo4j_rules()
        _nlp = _build_nlp(extra_rules=custom)
    return _nlp


def reload_nlp() -> None:
    """Rebuild the ConText NLP singleton, re-fetching custom rules from Neo4j.

    Call this from the API after a ContextRule is created or deactivated so the
    pipeline picks up the change without a service restart.
    """
    global _nlp
    custom = _fetch_neo4j_rules()
    _nlp = _build_nlp(extra_rules=custom)
    logger.info("ConText NLP pipeline reloaded")


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
) -> list[list[tuple[int, Span]]]:
    """Split overlapping spans into non-overlapping groups (passes).

    Returns a list of groups where each group contains non-overlapping
    spans that can be set as ``doc.ents`` simultaneously.  Overlapping
    entities are moved to subsequent passes so ConText processes them all.
    """
    passes: list[list[tuple[int, Span]]] = []
    assigned: set[int] = set()

    remaining = list(pending)
    while remaining:
        current_pass: list[tuple[int, Span]] = []
        seen_tokens: set[int] = set()
        still_remaining: list[tuple[int, Span]] = []
        for idx, span in remaining:
            tokens = set(range(span.start, span.end))
            if tokens & seen_tokens:
                still_remaining.append((idx, span))
            else:
                seen_tokens.update(tokens)
                current_pass.append((idx, span))
                assigned.add(idx)
        passes.append(current_pass)
        remaining = still_remaining

    return passes


def apply_context_detection_to_dicts(
    encounter_text: str,
    entities: list[dict],
) -> None:
    """Apply ConText assertion detection to plain entity dicts, mutating in place.

    Each dict must have ``start`` and ``end`` character offsets.
    Only overwrites ``assertion`` when the current value is ``"present"`` or unset.

    Overlapping entities are processed in multiple passes so that ConText
    evaluates every entity, not just the first of each overlapping group.

    Raises:
        Any exception from the spaCy/medspaCy pipeline is re-raised so
        callers never silently persist incorrect assertion values.
    """
    if not entities:
        return
    needs = [i for i, e in enumerate(entities) if (e.get("assertion") or "present") == "present"]
    if not needs:
        return
    try:
        nlp = _get_nlp()
        doc = nlp.make_doc(encounter_text)
        if nlp.has_pipe("sentencizer"):
            doc = nlp.get_pipe("sentencizer")(doc)
        pending = []
        for idx in needs:
            ent = entities[idx]
            start = int(ent.get("start") or 0)
            end = int(ent.get("end") or start)
            span = doc.char_span(start, end, label="ENTITY", alignment_mode="expand")
            if span is not None:
                pending.append((idx, span))
        passes = _deduplicate_spans(pending)
        context_pipe = nlp.get_pipe("medspacy_context")
        for current_pass in passes:
            doc.ents = [span for _, span in current_pass]
            doc = context_pipe(doc)
            ent_assertion = {span.start: _span_to_assertion(span) for span in doc.ents}
            for item_idx, span in current_pass:
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

    Items that already carry a non-``"present"`` assertion are returned
    unchanged.  Overlapping entities are processed in multiple passes.

    Args:
        encounter_text: Full de-identified encounter text.
        items: ExtractionItems with span_start / span_end character offsets.

    Returns:
        Tuple of (assertions list, context_detection_failed bool).
        assertions has the same length and order as *items*.
        context_detection_failed is True if spaCy raised an exception.

    Raises:
        Any exception from the spaCy/medspaCy pipeline is re-raised so
        callers never silently persist incorrect assertion values.
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
        if nlp.has_pipe("sentencizer"):
            doc = nlp.get_pipe("sentencizer")(doc)
        pending = _make_pending_spans(doc, items, needs)
        passes = _deduplicate_spans(pending)

        context_pipe = nlp.get_pipe("medspacy_context")
        for current_pass in passes:
            doc.ents = [span for _, span in current_pass]
            doc = context_pipe(doc)
            ent_assertion = {span.start: _span_to_assertion(span) for span in doc.ents}
            for item_idx, span in current_pass:
                defaults[item_idx] = ent_assertion.get(span.start, "present")
        return defaults, False

    except Exception:
        logger.error(
            "ConText detection FAILED for encounter (%d entities) -- aborting",
            len(needs),
            exc_info=True,
        )
        raise
