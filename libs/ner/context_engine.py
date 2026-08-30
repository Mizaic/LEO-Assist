"""MedSpaCy ConText engine for clinical assertion detection.

Atlas trace:
  DO: DO-15449C6E
  DI: DI-0F9542BF
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-15449C6E")

Atlas: DO-15449C6E / DI-0F9542BF / VT-A1919820
Custom categories: DECLINED, CANCELLED, REFUTED, PLANNED.
PLANNED is a confirmed booking; HYPOTHETICAL is speculative.
Raises on spaCy errors so callers never persist a silent wrong assertion.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import spacy
from spacy.tokens import Span

from libs.ner.context_span_resolution import resolve_context_spans

if TYPE_CHECKING:
    from libs.ner.extractor_contract import ExtractionItem

logger = logging.getLogger(__name__)

# Span attribute mapping -- includes the custom DECLINED category.
# Span.set_extension("is_declined") must be called before ConText is added.
_SPAN_ATTRS: dict = {
    "NEGATED_EXISTENCE": {"is_negated": True},
    "POSSIBLE_EXISTENCE": {"is_uncertain": True},
    "HISTORICAL": {"is_historical": True},
    "HYPOTHETICAL": {"is_hypothetical": True},
    "FAMILY": {"is_family": True},
    "DECLINED": {"is_declined": True},
    "CANCELLED": {"is_cancelled": True},
    "REFUTED": {"is_refuted": True},
    "PLANNED": {"is_planned": True},
}

_CATEGORY_ASSERTION = {
    "NEGATED_EXISTENCE": "absent",
    "POSSIBLE_EXISTENCE": "possible",
    "HISTORICAL": "historical",
    "HYPOTHETICAL": "hypothetical",
    "FAMILY": "family",
    "DECLINED": "declined",
    "CANCELLED": "cancelled",
    "REFUTED": "refuted",
    "PLANNED": "planned",
}
_ASSERTION_RANK = (
    "family",
    "absent",
    "refuted",
    "declined",
    "cancelled",
    "planned",
    "historical",
    "hypothetical",
    "possible",
)

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
    if not Span.has_extension("is_planned"):
        Span.set_extension("is_planned", default=False)


from spacy.symbols import ORTH

_CONTEXT_RULE_KEYS = frozenset(
    {
        "pattern",
        "category",
        "max_scope",
        "metadata",
        "max_targets",
        "literal",
        "excluded_types",
        "allowed_types",
        "direction",
    }
)


def _build_nlp(
    extra_rules: list[dict] | None = None,
    suppressed: set[str] | None = None,
) -> spacy.language.Language:
    """Create a blank spaCy pipeline with packaged ConText plus custom rules."""
    from medspacy.context import ConTextRule

    _register_extensions()
    nlp = spacy.blank("en")

    # Fix for "#s." tokenization where "s." is treated as an abbreviation
    # Also handle common laterality abbreviations at end of sentence (#l., #r.)
    for abbrev in ["s.", "l.", "r.", "n."]:
        nlp.tokenizer.add_special_case(abbrev, [{ORTH: abbrev[0]}, {ORTH: "."}])

    nlp.add_pipe("sentencizer")
    context = nlp.add_pipe(
        "medspacy_context",
        config={"span_attrs": _SPAN_ATTRS, "max_scope": 10, "rules": None},
    )

    from libs.ner.context_rule_catalog import packaged_nlp_entries

    builtin_rules: list[ConTextRule] = []
    for entry in packaged_nlp_entries(set(suppressed or ())):
        clean = {k: v for k, v in entry.items() if k in _CONTEXT_RULE_KEYS}
        builtin_rules.append(ConTextRule(**clean))
    logger.info("Loaded %d packaged ConText rules", len(builtin_rules))

    custom_rules: list[ConTextRule] = []
    for entry in extra_rules or []:
        try:
            clean = {k: v for k, v in entry.items() if k in _CONTEXT_RULE_KEYS}
            custom_rules.append(ConTextRule(**clean))
        except Exception:
            logger.warning(
                "Skipping malformed custom ConText rule: %s", entry, exc_info=True
            )
    if custom_rules:
        logger.info("Loaded %d custom ConText rules from Neo4j", len(custom_rules))

    all_rules = builtin_rules + custom_rules
    if all_rules:
        context.add(all_rules)

    return nlp


def get_builtin_rules() -> list[dict[str, Any]]:
    """Return shipped medspaCy plus UK ConText rules as plain dicts."""
    from libs.ner.context_rule_catalog import list_packaged_context_rules

    return list_packaged_context_rules()


def _fetch_neo4j_context_state() -> tuple[list[dict], set[str]]:
    """Active custom rules plus literals that authors have turned off."""
    from libs.ner.context_rule_catalog import (
        is_packaged_rule_id,
        suppressed_literals,
    )

    try:
        from libs.cypher.coding_review_queries import GET_CONTEXT_RULES
        from libs.neo4j_client.client import PatientGraphClient  # noqa: PLC0415

        client = PatientGraphClient()
        try:
            with client.session() as session:
                rows = [
                    dict(r)
                    for r in session.run(
                        GET_CONTEXT_RULES, active_only=False, org_id=None
                    )
                ]
        finally:
            client.close()
    except Exception:
        logger.warning(
            "Could not fetch custom ConText rules from Neo4j -- "
            "running on built-in rules only",
            exc_info=True,
        )
        return [], set()

    off = suppressed_literals(rows)
    custom = [
        row
        for row in rows
        if row.get("active", True) and not is_packaged_rule_id(row.get("rule_id"))
    ]
    return custom, off


def _fetch_neo4j_rules() -> list[dict]:
    """Fetch active custom ContextRule nodes from the Patient Graph."""
    custom, _off = _fetch_neo4j_context_state()
    return custom


def _get_nlp() -> spacy.language.Language:
    global _nlp
    if _nlp is None:
        custom, off = _fetch_neo4j_context_state()
        _nlp = _build_nlp(extra_rules=custom, suppressed=off)
    return _nlp


def reload_nlp() -> None:
    """Rebuild the ConText NLP singleton, re-fetching custom rules from Neo4j."""
    global _nlp
    custom, off = _fetch_neo4j_context_state()
    _nlp = _build_nlp(extra_rules=custom, suppressed=off)
    logger.info("ConText NLP pipeline reloaded")


def _modifier_token_span(modifier: Any) -> tuple[int, int] | None:
    raw = getattr(modifier, "modifier_span", None)
    if isinstance(raw, tuple) and len(raw) == 2:
        return int(raw[0]), int(raw[1])
    other = getattr(modifier, "span", None)
    if other is None:
        return None
    start = getattr(other, "start", None)
    end = getattr(other, "end", None)
    if start is None or end is None:
        return None
    return int(start), int(end)


def _same_sentence_modifiers(span: Span) -> list[Any]:
    """Keep ConText cues that sit in the same sentence as the entity.

    medspaCy max_scope uses a token window and can cross a full stop.
    """
    kept: list[Any] = []
    doc = span.doc
    sent_start = span.sent.start
    for modifier in getattr(span._, "modifiers", None) or []:
        tokens = _modifier_token_span(modifier)
        if tokens is None:
            continue
        start = tokens[0]
        if start < 0 or start >= len(doc):
            continue
        if doc[start].sent.start != sent_start:
            continue
        if _contrast_cuts_modifier(span, start, tokens[1]):
            continue
        kept.append(modifier)
    return kept


def _contrast_cuts_modifier(span: Span, mod_start: int, mod_end: int) -> bool:
    """Drop a cue when 'but does have' sits between that cue and the entity."""
    from libs.ner.contrast_negation_guard import contrast_terminates_modifier

    if mod_start < 0 or mod_end > len(span.doc) or mod_start >= mod_end:
        return False
    piece = span.doc[mod_start:mod_end]
    return contrast_terminates_modifier(
        span.doc.text, int(piece.end_char), int(span.start_char)
    )


def _span_to_assertion(span: Span) -> str:
    """Map same-sentence ConText cues to a priority-ordered assertion."""
    found: set[str] = set()
    for modifier in _same_sentence_modifiers(span):
        mapped = _CATEGORY_ASSERTION.get(
            str(getattr(modifier, "category", "") or "").upper()
        )
        if mapped:
            found.add(mapped)
    for key in _ASSERTION_RANK:
        if key in found:
            return key
    return "present"


def _trigger_window_from_span(span: Span) -> dict[str, Any] | None:
    """First same-sentence cue text and offsets. Supports DI-23822663."""
    for modifier in _same_sentence_modifiers(span):
        tokens = _modifier_token_span(modifier)
        if tokens is None:
            continue
        start, end = tokens
        if start < 0 or end > len(span.doc) or start >= end:
            continue
        piece = span.doc[start:end]
        return {
            "assertion_trigger_text": piece.text,
            "assertion_trigger_start": int(piece.start_char),
            "assertion_trigger_end": int(piece.end_char),
            "assertion_trigger_category": str(getattr(modifier, "category", "") or ""),
        }
    return None


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
    needs = [
        i
        for i, e in enumerate(entities)
        if (e.get("assertion") or "present") == "present"
    ]
    if not needs:
        return
    try:
        nlp = _get_nlp()
        doc = nlp.make_doc(encounter_text)
        if nlp.has_pipe("sentencizer"):
            doc = nlp.get_pipe("sentencizer")(doc)
        # Locate each fact by its own words first. Offsets arriving here can
        # be a SpanResolver fallback pointing at character 0 -- the document
        # banner -- and a banner carries no negation cue, so ConText would
        # come back "present" for a denied finding. A fact whose text is
        # nowhere in the letter is marked and skipped rather than judged
        # against someone else's words.
        pending = []
        for idx, start, end in resolve_context_spans(encounter_text, entities, needs):
            span = doc.char_span(start, end, label="ENTITY", alignment_mode="expand")
            if span is not None:
                pending.append((idx, span))
        passes = _deduplicate_spans(pending)
        context_pipe = nlp.get_pipe("medspacy_context")
        for current_pass in passes:
            doc.ents = [span for _, span in current_pass]
            doc = context_pipe(doc)
            ent_assertion = {span.start: _span_to_assertion(span) for span in doc.ents}
            ent_trigger = {
                span.start: _trigger_window_from_span(span) for span in doc.ents
            }
            for item_idx, span in current_pass:
                assertion = ent_assertion.get(span.start, "present")
                if assertion != "present":
                    entities[item_idx]["assertion"] = assertion
                    entities[item_idx]["_assertion_source"] = "context"
                    trigger = ent_trigger.get(span.start)
                    if trigger is not None:
                        entities[item_idx].update(trigger)
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

    needs = [
        i for i, it in enumerate(items) if (it.assertion or "present") == "present"
    ]
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
