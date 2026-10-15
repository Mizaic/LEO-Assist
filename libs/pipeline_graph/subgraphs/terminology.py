"""Terminology resolution subgraph wrapping libs.terminology.client.

Atlas trace:
  DO: DO-572A5C05
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-572A5C05")
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from libs.pipeline.form_checkbox_seed import is_taught_checkbox
from libs.pipeline.form_schema_seeding import carries_taught_test_row_code
from libs.ner.suspected_cancer_guard import (
    dedupe_suspected_malignancy_conflicts,
    enrich_suspected_cancer_lookups,
    guard_suspected_cancer_resolutions,
)
from libs.pipeline.post_processing import (
    apply_false_absent_assertion_guards,
    fix_double_negated_situations,
    fix_polarity_encoded_findings,
)
from libs.pipeline.coding_candidate_gate import (
    apply_draft_from_shortlist,
    filter_coding_candidates,
)
from libs.pipeline_graph.subgraphs._terminology_letter_codes import (
    dedup_by_concept_id,
    with_lab_findings,
)
from libs.terminology.client import TerminologyClient, TerminologyUnavailable

logger = logging.getLogger(__name__)


# Minimum calibrated absolute confidence to accept a SNOMED mapping.
# Calibrated ~ P(correct mapping). 0.55 admits:
#   - Exact-branch hits (lex_signal=1.0 -> calibrated=1.0)
#   - Strong fulltext (BM25>=2) with tag match (~0.67+0.10=0.77)
#   - High-cosine vector hits (>=0.85)
# Rejects:
#   - Weak partial Lucene matches whose only candidate was a one-token
#     hit (calibrated <= 0.5).
# Was 0.70 under the old per-term-normalised scoring; lowered to 0.55
# now that the score reflects absolute strength rather than relative
# rank within the per-term candidate pool.
_DEFAULT_MIN_SCORE = 0.55
_BLOCKLIST_SEED_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "libs"
    / "ner"
    / "resources"
    / "term_concept_blocklist.json"
)
_FAMILY_BLOCKLIST = "term_concept_blocklist"


def _normalise_text_key(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


# Singleton: surface_form_key -> frozenset of blocked concept IDs.
# Rebuilt at module import and on _reload_blocklist_singleton().
_blocklist_singleton: dict[str, frozenset[str]] = {}


def _fetch_neo4j_blocklist(family: str) -> list[dict]:
    """Fetch :NerGuardRule nodes for the blocklist family from Neo4j.

    Returns [] if Neo4j is unreachable.
    """
    try:
        from libs.pipeline.config_loader import _fetch_neo4j_rules

        return _fetch_neo4j_rules(family)
    except Exception:
        logger.warning(
            "Could not fetch Neo4j blocklist rules -- using builtins only",
            exc_info=True,
        )
        return []


def _build_blocklist() -> dict[str, frozenset[str]]:
    """Build the blocklist dict from seed JSON and Neo4j rows."""
    result: dict[str, set[str]] = {}

    if _BLOCKLIST_SEED_PATH.exists():
        try:
            data = json.loads(_BLOCKLIST_SEED_PATH.read_text(encoding="utf-8"))
            for r in data.get("rules", []):
                if not r.get("active", True):
                    continue
                key = _normalise_text_key(r.get("surface_form", ""))
                ids = r.get("blocked_concept_ids", [])
                if key and ids:
                    result.setdefault(key, set()).update(str(i) for i in ids)
        except Exception:
            logger.error("Failed to parse blocklist seed file", exc_info=True)

    for row in _fetch_neo4j_blocklist(_FAMILY_BLOCKLIST):
        if not row.get("active", True):
            continue
        key = _normalise_text_key(row.get("surface_form", ""))
        ids = row.get("blocked_concept_ids", [])
        if key and ids:
            result.setdefault(key, set()).update(str(i) for i in ids)

    return {k: frozenset(v) for k, v in result.items()}


def _reload_blocklist_singleton() -> None:
    """Rebuild the blocklist singleton, re-fetching custom rules from Neo4j."""
    global _blocklist_singleton
    _blocklist_singleton = _build_blocklist()
    logger.info(
        "Term concept blocklist reloaded (%d entries)", len(_blocklist_singleton)
    )


_reload_blocklist_singleton()


def _is_blocked_mapping(text: str, concept_id: str | None) -> bool:
    if not concept_id:
        return False
    blocked = _blocklist_singleton.get(_normalise_text_key(text))
    return bool(blocked and str(concept_id) in blocked)


class TerminologyState(TypedDict, total=False):
    encounter_text: str
    entities: list[dict[str, Any]]
    expected_tags: dict[str, str]
    resolved_entities: list[dict[str, Any]]
    confidence_threshold: float
    patient_age: float
    patient_sex: str
    org_id: str
    errors: list[str]
    warnings: list[str]
    degraded: bool


# Leading tokens that are never useful as the core SNOMED lookup term.
# Stripping them increases the chance of an exact-branch hit.
_LOOKUP_STRIP_PREFIXES = frozenset(
    {
        "moderate",
        "mild",
        "severe",
        "marked",
        "significant",
        "bilateral",
        "left",
        "right",
        "small",
        "large",
        "central",
        "peripheral",
        "anterior",
        "posterior",
        "medial",
        "lateral",
        "proximal",
        "distal",
        "diffuse",
        "focal",
        "generalised",
        "generalized",
        "extensive",
        "complex",
        "simple",
        "high-risk",
        "high risk",
        "low-risk",
        "low risk",
    }
)


def _strip_leading_modifiers(text: str) -> str:
    """Remove leading qualifier words that hurt SNOMED lexical matching.

    Drops one leading token at a time (case-insensitive) while the first
    word is a known non-clinical modifier.  Stops as soon as the first
    word is clinical so we never strip the concept itself.
    """
    words = text.split()
    while words:
        first = words[0].lower().rstrip("-,;")
        if first in _LOOKUP_STRIP_PREFIXES or not words[0].strip("-*.|"):
            words = words[1:]
            continue
        break
    return " ".join(words) if words else text


_LOOKUP_STRIP_SUFFIXES = (
    " both solids and liquids",
    " solids and liquids",
    " to solids and liquids",
    " of uncertain cause",
    " of unknown cause",
    " of unclear cause",
)


def _strip_trailing_modifiers(text: str) -> str:
    """Remove trailing meal or certainty words that block SNOMED lookup."""
    lowered = text.lower()
    for suffix in _LOOKUP_STRIP_SUFFIXES:
        if lowered.endswith(suffix):
            return text[: len(text) - len(suffix)].strip()
    return text


_GENERIC_VULVA_FINDING_ID = "248858001"
_VULVAL_ULCER_ID = "68640004"
_VULVAL_ULCER_TERM = "Ulceration of vulva (disorder)"
_ULCERATION_WORD = re.compile(r"\bulceration\b", re.IGNORECASE)
_VULVA_STEM = re.compile(r"\bvulv", re.IGNORECASE)


def _upgrade_generic_vulva_ulcer(entity: dict[str, Any]) -> dict[str, Any]:
    """Replace generic or missing vulva code when the span says ulceration.

    Soreness or pain alone must not become an ulcer code.
    """
    current = str(entity.get("concept_id") or "")
    if current not in {"", _GENERIC_VULVA_FINDING_ID}:
        return entity
    blob = " ".join(
        (
            str(entity.get("text") or ""),
            str(entity.get("lookup_term") or ""),
        )
    )
    if not (_ULCERATION_WORD.search(blob) and _VULVA_STEM.search(blob)):
        return entity
    upgraded = dict(entity)
    upgraded["concept_id"] = _VULVAL_ULCER_ID
    upgraded["term"] = _VULVAL_ULCER_TERM
    upgraded["semantic_tag"] = "disorder"
    upgraded["terminology_unresolved"] = False
    upgraded["_vulval_ulcer_remapped"] = True
    return upgraded


def _reports_a_measured_value(entity: dict[str, Any]) -> bool:
    """Say whether this span reports a number with a unit.

    A value plus a unit is what separates "the CA 125 was 6 ku/L" from
    "suspected ovarian cancer". Only the former is a measurement, and a
    measurement's identity is its analyte, never a suspicion.
    """
    value = str(entity.get("value") or "").strip()
    unit = str(entity.get("unit") or "").strip()
    return bool(value) and bool(unit)


def _resolve_lookup_term(entity: dict[str, Any]) -> str:
    text = str(entity.get("text") or "").strip()
    normalized_lookup = str(entity.get("normalized_lookup") or "").strip()
    normalized = str(entity.get("normalized") or "").strip()
    lookup = str(entity.get("lookup_term") or "").strip()

    # A reported result keeps the analyte's name. Blood tables put the
    # requesting clinic in the last cell ("| CA 125 | 6 ku/L | 2ww Gynae |"),
    # the model pulls it into the lookup term, and without this guard a
    # normal CA 125 codes as a suspected gynaecological malignancy.
    measured = _reports_a_measured_value(entity)
    if measured:
        if text:
            return text
    else:
        for candidate in (normalized_lookup, normalized, lookup):
            if candidate and "suspected" in candidate.lower():
                return candidate

    if lookup and lookup.lower() != text.lower():
        return lookup

    if normalized_lookup:
        return normalized_lookup

    if normalized and normalized.lower() != text.lower():
        return normalized

    # When lookup mirrors surface text, strip leading qualifiers so the SNOMED
    # resolver sees "ovary enlarged" instead of "left ovary enlarged".
    if not lookup or lookup.lower() == text.lower():
        stripped = _strip_trailing_modifiers(_strip_leading_modifiers(text))
        if stripped and stripped != text:
            return stripped
        if lookup:
            return lookup

    if lookup:
        return lookup

    relations = list(entity.get("__relations") or [])
    for rel in relations:
        if not isinstance(rel, dict):
            continue
        if str(rel.get("type") or "").strip().lower() != "finding_site":
            continue
        tail = str(rel.get("target_text") or "").strip()
        if tail and text:
            return f"{tail} {text}".strip()
    return text


def _stamp_rejected_guess(merged: dict[str, Any], candidate: Any) -> dict[str, Any]:
    merged["score"] = round(float(getattr(candidate, "score", 0.0) or 0.0), 4)
    merged["terminology_unresolved"] = True
    merged["rejected_term"] = getattr(candidate, "term", None)
    merged["rejected_concept_id"] = getattr(candidate, "concept_id", None)
    merged["rejected_tag"] = getattr(candidate, "semantic_tag", None)
    merged["coding_candidates"] = []
    for field in ("concept_id", "term", "read_code"):
        merged[field] = None
    return merged


def _merge_resolution(
    e: dict[str, Any],
    candidates: list,
    min_score: float = _DEFAULT_MIN_SCORE,
) -> dict[str, Any]:
    merged = dict(e)
    if not candidates:
        merged["score"] = 0.0
        merged["terminology_unresolved"] = True
        merged["coding_candidates"] = []
        return merged
    shortlist = filter_coding_candidates(
        e,
        candidates,
        is_blocked=_is_blocked_mapping,
        min_score=min_score,
    )
    if not shortlist:
        first = candidates[0]
        logger.info(
            "Terminology: no safe candidate for %r (top was %r score %.4f)",
            e.get("text"),
            getattr(first, "term", None),
            float(getattr(first, "score", 0.0) or 0.0),
        )
        return _stamp_rejected_guess(merged, first)
    drafted = apply_draft_from_shortlist(merged, shortlist)
    best = candidates[0]
    raw = getattr(best, "raw", None) or {}
    if "surface_form_status" in raw and drafted.get("concept_id") == best.concept_id:
        drafted["surface_form_status"] = raw.get("surface_form_status", "")
    return drafted


def _keep_taught_form_code(entity: dict[str, Any]) -> bool:
    """Taught FormSchema ticks and test rows already carry their concept id."""
    if carries_taught_test_row_code(entity):
        return True
    if not is_taught_checkbox(entity):
        return False
    return bool(str(entity.get("concept_id") or "").strip())


def _resolve_terms(state: TerminologyState) -> dict[str, Any]:
    entities = state.get("entities") or []
    expected_tags = state.get("expected_tags") or {}
    errors: list[str] = list(state.get("errors") or [])
    warnings: list[str] = list(state.get("warnings") or [])
    min_score = float(state.get("confidence_threshold") or _DEFAULT_MIN_SCORE)
    if not entities:
        return {
            "entities": [],
            "resolved_entities": [],
            "errors": errors,
            "warnings": warnings,
        }
    try:
        encounter_text = str(state.get("encounter_text") or "")
        enrich_suspected_cancer_lookups(encounter_text, entities)
        terms = []
        tag_map: dict[str, str] = dict(expected_tags)
        lookup_by_index: dict[int, str] = {}
        for e in entities:
            idx = len(lookup_by_index)
            lookup = _resolve_lookup_term(e)
            lookup_by_index[idx] = lookup
            if lookup:
                terms.append(lookup)
                if lookup not in tag_map and (
                    label := e.get("semantic_tag") or e.get("label")
                ):
                    tag_map[lookup] = str(label)
        org_id = str(state.get("org_id") or "").strip() or None
        results = TerminologyClient().resolve(
            terms, expected_tags=tag_map or None, org_id=org_id
        )
        resolved = []
        for idx, entity in enumerate(entities):
            lookup = lookup_by_index.get(idx) or ""
            if _keep_taught_form_code(entity):
                resolved.append(dict(entity))
                continue
            merged = _merge_resolution(entity, results.get(lookup, []), min_score)
            if lookup:
                merged["lookup_term"] = lookup
            resolved.append(_upgrade_generic_vulva_ulcer(merged))
        unresolved = [r for r in resolved if r.get("terminology_unresolved")]
        if unresolved:
            warnings.append(
                f"terminology_low_confidence: {len(unresolved)} entity/entities below "
                f"score threshold {min_score:.2f} -- "
                + ", ".join(
                    f'"{u.get("text")}" (score {u.get("score", 0):.2f})'
                    for u in unresolved
                )
            )
        guard_suspected_cancer_resolutions(encounter_text, resolved)
        fix_double_negated_situations(resolved)
        fix_polarity_encoded_findings(resolved)
        apply_false_absent_assertion_guards(resolved, respect_context=True)
        resolved, lab_degraded = with_lab_findings(resolved, state, warnings)
        resolved = dedupe_suspected_malignancy_conflicts(resolved)
        resolved = dedup_by_concept_id(resolved)
        out: dict[str, Any] = {
            "entities": resolved,
            "resolved_entities": resolved,
            "errors": errors,
            "warnings": warnings,
        }
        if lab_degraded:
            out["degraded"] = True
        return out
    except TerminologyUnavailable as exc:
        # Rule 2 of .cursor/rules/fail-closed-boundary.mdc. We could not ask,
        # so these spans must not be handed on looking like spans we asked
        # about and found no safe code for. The run degrades to a person.
        logger.error("Terminology lookup failed: %s", exc)
        unlooked = [dict(e, terminology_lookup_failed=True) for e in entities]
        warnings.append(
            "terminology_lookup_failed: we could not reach the terminology "
            f"service, so no clinical term was looked up for {len(unlooked)} "
            "phrase(s). Someone needs to check this referral."
        )
        return {
            "entities": unlooked,
            "resolved_entities": unlooked,
            "errors": errors,
            "warnings": warnings,
            "degraded": True,
        }
    except Exception as exc:
        logger.exception("Terminology resolution failed")
        errors.append(f"terminology: {exc}")
        return {
            "entities": entities,
            "resolved_entities": entities,
            "errors": errors,
            "warnings": warnings,
        }


def build_terminology_subgraph() -> CompiledStateGraph:
    graph = StateGraph(TerminologyState)
    graph.add_node("resolve_terms", _resolve_terms)
    graph.add_edge(START, "resolve_terms")
    graph.add_edge("resolve_terms", END)
    return graph.compile()
