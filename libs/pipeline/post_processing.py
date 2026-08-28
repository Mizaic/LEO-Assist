"""Canonical post-processing stack applied identically to training and runtime.

Atlas trace:
  UN: UN-89E2AE36
  DI: DI-B5C78811
  DO: DO-728930A1, DO-416BA91D
  VT: VT-88920DAA, VT-29AF2163, VT-2A7C5322, VT-4231B0A0,
      VT-E425D17E, VT-CC118874, VT-7AC15E8B, VT-29880CC8,
      VT-E6BD0CA9
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-B5C78811")

All layers execute in a fixed order on plain entity dicts (including 2b Referral Routing Guard).  Both the
training verification pipeline (label_verifier) and the runtime coding
pipeline (pipeline_service) call ``run_post_processing()`` so that gold
training data and production inference share exactly the same
post-processing logic, eliminating train/serve skew.

Layer order
-----------
1. Post-Processor Rules   -- DB-driven text/label rewrites
2. Lab-Value Guard        -- suppress disorders inferred from lab results
2b. Referral Routing Guard -- drop informational 2WW/pathway routing prose
3. Scope Guard            -- reclassify assertions in safety-netting /
                             recommendation / hedged-diagnosis text
3b. Lab Triple Recovery   -- add missing procedure / observable / finding
                             spans on lab-shaped lines the model missed
3c. Request Reason Recovery -- add clinically meaningful findings embedded in
                             lab request reason text.
3c2. Breast Screening Outcome Recovery -- NHS breast programme + abnormal
                             (68621) as a finding (SNOMED 171176006).
3d. Cross-Line Lab Finding Merge -- DI-B5C78811 / DO-728930A1. Extend an
                             observable_entity span forward across at most
                             one blank line when the next non-blank line
                             starts with a recognised result-interpretation
                             phrase ("Outside reference range", "High", ...).
4. Observable Norm.       -- clean observable spans, attach value/unit/ref
4b. Observable Surface Cleanup -- DI-B5C78811. Strip trailing value+unit (and
                             optional ref range) tokens from
                             observable_entity.text so downstream
                             stringification (validation scoring, training
                             label exports, audit) sees a single canonical
                             surface form across both pipelines.
4c. Measurement Observable Recovery -- DI-B5C78811. Retag weight/height/BMI
                             names that were split from their number
                             (often as procedure + qualifier_value) and
                             attach value/unit before SNOMED lookup.
5. Value-Unit Linking     -- attach numeric values to nearby observables
6. Entity-Type Norm.      -- deterministic label corrections (runs after
                             linking so observables with structured value/unit
                             are not mis-tagged as qualifier_value)
7. ConText Assertion Det. -- MedSpaCy negation/historical/family detection
7b. Referral Proc Guard   -- keep referral procedures as present
7c. Observable Trend Split -- split current vs historical result values
8. Situation Lookup Norm. -- normalise situation text for terminology
8b. Suspected Cancer Lookup -- enrich lookup_term for suspected referrals
9. Disorder Gate          -- LLM dual-model disorder classification (optional)
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from libs.llm_client.disorder_verifier import DisorderVerdict, verify_disorder
from libs.nlp.sentence_splitter import is_referral_procedure_phrase
from libs.ner.context_detector import normalize_situation_lookup

# Imported directly, never behind a fallback. ConText is the negation
# guard: without it "No chest pain" is recorded as chest pain present. A
# no-op stub standing in for a safety layer is prohibited by
# .cursor/rules/fail-closed-boundary.mdc rule 1, so a failed import must
# stop the run rather than quietly switch negation detection off.
from libs.ner.context_engine import apply_context_detection_to_dicts
from libs.ner.lab_triple_recovery import recover_lab_triples
from libs.ner.lab_value_guard import should_suppress_disorder
from libs.ner.referral_routing_guard import should_suppress_referral_routing_entity
from libs.ner.body_structure_guard import should_keep_body_structure
from libs.ner.observable_post_processor import normalize_observable_entities
from libs.ner.post_processor_rules import PostProcessorRule, apply_rules_to_entities
from libs.pipeline.extraction_term_normaliser import (
    clean_observable_surface_text,
    is_bare_numeric,
)
from libs.ner.breast_screening_outcome_recovery import (
    recover_breast_screening_outcome_finding,
)
from libs.ner.request_reason_recovery import recover_request_reason_entities
from libs.ner.local_concept_recovery import (
    LocalConceptPattern,
    recover_local_concept_entities,
)
from libs.ner.measurement_observable_recovery import recover_measurement_observables
from libs.ner.scope_guard import SUPPRESSED, reclassify_assertion

logger = logging.getLogger(__name__)

_SENTENCE_BOUNDARY_RE = re.compile(r"(?:\.(?:\s|$)|\n)")
_TREND_SPLIT_RE = re.compile(
    r"\b(?:trending\s+(?:down|up)|down\s+from|up\s+from|from\s+peak(?:\s+of)?|from\s+previous(?:ly)?|from\s+prior)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Concept-specific suppression guard (runs before all other layers)
# ---------------------------------------------------------------------------

# 395100000 | No evidence of cancer found (situation)
# This concept is only valid as a post-pathway cancer discharge confirmation.
# Routine population screening negatives (cervical smear, FIT, FOBT, HPV
# screening) must NEVER be coded with this concept.
_NO_CANCER_EVIDENCE_CONCEPT = "395100000"
_SCREENING_NEGATIVE_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"cervical\s+smear",
        r"cervical\s+cytology",
        r"hpv\s+(?:test|screen|not\s+detected)",
        r"high\s+risk\s+hpv\s+not\s+detected",
        r"normal\s+recall",
        r"no\s+cytology\s+result",
        r"\bfobt\b",
        r"\bfit\b(?:\s+result|\s+test|\s+negative|\s+-|\s+normal|$)",
        r"faecal\s+immunochemical",
        r"faecal\s+occult\s+blood",
        r"bowel\s+cancer\s+screening\s+programme",
        r"overall\s+negative\s+result",
        r"sent\s+following\s+(?:an\s+)?overall\s+negative",
        r"no\s+detectable\s+blood.*risk\s+of\s+(?:crc|bowel|colorectal)",
    ]
]


def _suppress_screening_false_positives(
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Remove any entity whose snomed_code is 395100000 but whose evidence
    text matches a routine screening negative pattern.

    This is a deterministic guard that catches LLM over-application of the
    'No evidence of cancer found' concept to cervical smear, FIT, FOBT, or
    HPV screening results.
    """
    kept = []
    for ent in entities:
        code = str(ent.get("snomed_concept_id") or ent.get("code") or "")
        if code != _NO_CANCER_EVIDENCE_CONCEPT:
            kept.append(ent)
            continue
        evidence = ent.get("text") or ent.get("entity_text") or ent.get("evidence", "")
        if any(p.search(str(evidence)) for p in _SCREENING_NEGATIVE_PATTERNS):
            logger.debug("Suppressed 395100000 screening false positive: %r", evidence)
        else:
            kept.append(ent)
    return kept


def _extract_sentence_window(
    encounter_text: str,
    start: int,
    end: int,
    margin: int = 300,
) -> str:
    """Return the sentence-level window around an entity span.

    Expands *margin* chars either side of [start, end] then trims to the
    nearest sentence boundary (period-space or newline) so the guard sees
    only the entity's local context, not the entire encounter.
    """
    win_start = max(0, start - margin)
    win_end = min(len(encounter_text), end + margin)

    left = encounter_text[win_start:start]
    boundary = _SENTENCE_BOUNDARY_RE.search(left[::-1])
    if boundary:
        win_start = start - boundary.start()

    right = encounter_text[end:win_end]
    boundary = _SENTENCE_BOUNDARY_RE.search(right)
    if boundary:
        win_end = end + boundary.end()

    return encounter_text[win_start:win_end]


def _extract_sentence_bounds(
    encounter_text: str,
    start: int,
    end: int,
    margin: int = 300,
) -> tuple[int, int]:
    """Return sentence-level (start, end) bounds around an entity span."""
    win_start = max(0, start - margin)
    win_end = min(len(encounter_text), end + margin)

    left = encounter_text[win_start:start]
    boundary = _SENTENCE_BOUNDARY_RE.search(left[::-1])
    if boundary:
        win_start = start - boundary.start()

    right = encounter_text[end:win_end]
    boundary = _SENTENCE_BOUNDARY_RE.search(right)
    if boundary:
        win_end = end + boundary.end()

    return win_start, win_end


# ── regex / constants for entity-type normalisation (Layer 5) ──

_VALUE_UNIT_RE = re.compile(
    r"(?P<value>[<>]?\s*\d+(?:\.\d+)?)\s*(?P<unit>(?:10\^\d+\/[A-Za-z]+|[A-Za-z/%]+(?:\/[A-Za-z]+)*))",
    re.IGNORECASE,
)

_LAB_UNIT_INDICATORS = re.compile(
    r"(?:mmol|umol|nmol|pmol|mg|ug|ng|pg|g|iu|mL|miu|L|mol|fl|10\^9|%|ratio|kg|kpa|mmhg|bpm|ug/g|cigs)",
    re.IGNORECASE,
)

_RESULT_DESCRIPTOR_TEXTS = frozenset(
    {
        "abnormal",
        "abnormal but expected",
        "normal",
        "satisfactory",
        "outside reference range",
        "within normal limits",
        "within reference range",
        "normal - no action",
        "borderline",
        "high",
        "low",
        "raised",
        "elevated",
        "nad",
        "no abnormality detected",
        "fobt non-response",
        "non-response",
        "no problems or concerns",
        "no problemds or concerns",
        "negative",
        "positive",
        "reactive",
        "non-reactive",
        "but expected",
        "weight stable",
    }
)

_BUILTIN_EPISODE_MARKER_TEXTS: frozenset[str] = frozenset(
    {
        "new episode",
        "ongoing episode",
        "first episode",
    }
)
_EPISODE_MARKER_TEXTS: frozenset[str] = _BUILTIN_EPISODE_MARKER_TEXTS

_LIFESTYLE_FACTOR_TEXTS = frozenset(
    {
        "diet",
        "alcohol",
        "exercise",
        "weight",
        "bmi",
        "smoking",
        "drives",
        "sleep",
        "caffeine",
    }
)

_LIFESTYLE_SEP_RE = re.compile(r"[\s/&,]+")

_UNCERTAINTY_MARKER_RE = re.compile(r"^\?{1,4}$")

_SEVERITY_MODIFIER_TEXTS = frozenset(
    {
        "severe",
        "mild",
        "moderate",
        "minor",
        "major",
        "urgent",
        "worsened",
        "worsening",
        "improving",
        "stable",
        "unchanged",
        "pale",
        "slight",
        "significant",
        "marked",
    }
)

_MDT_OUTCOME_RE = re.compile(
    r"(?:mdt|multidisciplinary)\s+(?:meet(?:ing)?|discussion|team)?\s*(?:outcome|result|decision)",
    re.IGNORECASE,
)

_SMOKING_CONSUMPTION_RE = re.compile(
    r"\d+[\s-]*(?:\d+)?\s*(?:cigs?|cigarettes?|roll[\s-]?ups?)\s*/\s*(?:day|week|wk)",
    re.IGNORECASE,
)

_REF_RANGE_ONLY_RE = re.compile(
    r"^\s*\[?\s*\d+(?:\.\d+)?\s*-\s*\d+(?:\.\d+)?\s*\]?\s*$",
)

_ANALYTE_NAMES = frozenset(
    {
        "creatinine",
        "albumin",
        "phosphate",
        "inorganic phosphate",
        "sodium",
        "potassium",
        "calcium",
        "bilirubin",
        "cholesterol",
        "glucose",
        "urea",
        "ferritin",
        "haemoglobin",
        "globulin",
        "triglyceride",
        "triglycerides",
        "folate",
        "iron",
        "zinc",
        "magnesium",
        "copper",
        "lithium",
        "testosterone",
        "oestradiol",
        "cortisol",
        "thyroxine",
        "chloride",
        "bicarbonate",
        "protein",
        "alkaline phosphatase",
    }
)

_BARE_NUMERIC_RE = re.compile(r"^[<>]?\s*\d+(?:\.\d+)?\s*$")

# ── helper predicates ──


def _is_lifestyle_topic_list(text: str) -> bool:
    tokens = [t for t in _LIFESTYLE_SEP_RE.split(text.lower()) if t and t != "and"]
    return bool(tokens) and all(t in _LIFESTYLE_FACTOR_TEXTS for t in tokens)


def _is_smoking_status_text(text: str) -> bool:
    lowered = text.strip().lower()
    return "smoking status" in lowered or lowered in {
        "smoker",
        "non-smoker",
        "ex-smoker",
        "never smoker",
        "current smoker",
        "ex smoker",
        "non smoker",
    }


def _is_lab_value_text(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    starts_with_number = bool(re.match(r"^[<>]?\s*\d", stripped))
    has_lab_unit = bool(_LAB_UNIT_INDICATORS.search(stripped))
    return starts_with_number and has_lab_unit


def _is_numeric_measurement_text(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    starts_with_number = bool(re.match(r"^[<>]?\s*\d", stripped))
    has_unit = bool(_VALUE_UNIT_RE.search(stripped))
    return starts_with_number and has_unit


def _is_result_descriptor(text: str) -> bool:
    return text.strip().lower() in _RESULT_DESCRIPTOR_TEXTS


def _is_string_result_text(text: str) -> bool:
    return text.strip().lower() in _RESULT_DESCRIPTOR_TEXTS


def _is_bare_analyte(text: str) -> bool:
    return text.strip().lower() in _ANALYTE_NAMES


def _extract_value_unit(text: str) -> tuple[str, str] | None:
    m = _VALUE_UNIT_RE.search(text or "")
    if not m:
        return None
    value = (m.group("value") or "").strip()
    unit = (m.group("unit") or "").strip()
    if not value or not unit:
        return None
    return value, unit


def _has_nearby_observable(
    entities: list[dict[str, Any]], target_idx: int, max_dist: int = 80
) -> bool:
    target = entities[target_idx]
    t_start = int(target.get("start", 0) or 0)
    t_end = int(target.get("end", 0) or 0)
    for i, ent in enumerate(entities):
        if i == target_idx:
            continue
        if str(ent.get("label", "")) != "observable_entity":
            continue
        o_start = int(ent.get("start", 0) or 0)
        o_end = int(ent.get("end", 0) or 0)
        dist = min(abs(t_start - o_end), abs(o_start - t_end))
        if dist <= max_dist:
            return True
    return False


# -- Layer 3c: Cross-Line Lab Finding Merge --
# DI-B5C78811, DO-728930A1, VT-29880CC8.
# EHR exports often place a lab observable's value/units on one line and the
# trailing result-interpretation phrase ("Outside reference range", "High",
# "Within normal limits", ...) on the next physical line, sometimes after a
# blank line. The sentence splitter's blank-line break leaves the
# interpretation phrase orphaned in a separate sentence, which prevents Layer
# 4 (observable normalisation) from emitting the matching `finding` sub-entity
# and prevents the SNOMED resolver from picking the compound concept (e.g.
# 166160000 "Prostate specific antigen outside reference range").
#
# This layer extends the observable_entity span forward across at most one
# blank line when the next non-blank line starts with a recognised result
# descriptor. Bounded, deterministic, idempotent.

# Maximum number of characters of trailing whitespace + blank line + leading
# whitespace allowed between the observable end and the candidate descriptor.
_CROSS_LINE_GAP_CHARS = 80
# Maximum forward extension applied to an observable span in a single pass.
_CROSS_LINE_MAX_EXTENSION = 120
# Maximum number of newlines tolerated in the gap (i.e. allow one blank line
# = two newlines, but not two blank lines).
_CROSS_LINE_MAX_NEWLINES = 2
_CROSS_LINE_GAP_RE = re.compile(r"^[ \t]*(?:\r?\n[ \t]*){1,2}$")
_CROSS_LINE_OBS_VALUE_RE = re.compile(
    r"\d+(?:\.\d+)?\s*[A-Za-z%/^0-9]*|\[[^\]]*\]",
)
# Sort descriptors by length descending so the longest match wins (e.g.
# "outside reference range" before "outside").
_CROSS_LINE_DESCRIPTORS: tuple[str, ...] = tuple(
    sorted(_RESULT_DESCRIPTOR_TEXTS, key=len, reverse=True)
)


def _observable_carries_value(text: str) -> bool:
    """Return True when an observable's surface text already includes a
    numeric value or a [reference range] token."""
    if not text:
        return False
    return _CROSS_LINE_OBS_VALUE_RE.search(text) is not None


def _next_line_descriptor(
    encounter_text: str, search_start: int
) -> tuple[int, int, str] | None:
    """Find the first recognised result descriptor that starts the next
    non-blank line after *search_start*.

    Returns (descriptor_start, descriptor_end, descriptor_text) using
    encounter-absolute offsets, or None if no acceptable descriptor follows.
    """
    if search_start >= len(encounter_text):
        return None
    window = encounter_text[search_start : search_start + 200]
    # Find the first non-whitespace character; everything between
    # search_start and that index is the gap.
    line_start_offset = 0
    for ch in window:
        if not ch.isspace():
            break
        line_start_offset += 1
    if line_start_offset == 0:
        # No leading whitespace -- the descriptor would have to start
        # immediately at search_start, which means there was no line break
        # at all. We require at least one newline in the gap to count this
        # as a cross-line merge (intra-line continuations are handled by
        # observable normalisation already).
        return None
    gap = window[:line_start_offset]
    if _CROSS_LINE_GAP_RE.fullmatch(gap) is None:
        return None
    if gap.count("\n") > _CROSS_LINE_MAX_NEWLINES:
        return None
    if line_start_offset > _CROSS_LINE_GAP_CHARS:
        return None
    # Read the rest of the next line (until newline or end of window).
    rest = window[line_start_offset:]
    line_end = rest.find("\n")
    line_text = rest if line_end < 0 else rest[:line_end]
    lowered = line_text.strip().lower()
    if not lowered:
        return None
    matched: str | None = None
    for descriptor in _CROSS_LINE_DESCRIPTORS:
        if lowered.startswith(descriptor):
            matched = descriptor
            break
    if matched is None:
        return None
    descriptor_start = search_start + line_start_offset
    # Match descriptor case-insensitively against the actual surface text so
    # that the extended span uses the original casing.
    descriptor_end = descriptor_start + len(matched)
    if descriptor_end - search_start > _CROSS_LINE_MAX_EXTENSION:
        return None
    return (
        descriptor_start,
        descriptor_end,
        encounter_text[descriptor_start:descriptor_end],
    )


def merge_cross_line_lab_findings(
    encounter_text: str,
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extend an observable_entity span forward across at most one blank line
    when the next non-blank line begins with a recognised result-interpretation
    phrase.

    Deterministic and idempotent: marks merged entities with
    ``__cross_line_merged__`` so a second invocation is a no-op for spans
    that have already been extended this run.
    """

    if not encounter_text or not entities:
        return entities

    for ent in entities:
        if str(ent.get("label", "")) != "observable_entity":
            continue
        if ent.get("__cross_line_merged__"):
            continue
        text = str(ent.get("text", ""))
        if not _observable_carries_value(text):
            continue
        try:
            ent_start = int(ent.get("start", 0) or 0)
            ent_end = int(ent.get("end", 0) or 0)
        except (TypeError, ValueError):
            continue
        if ent_end <= ent_start or ent_end > len(encounter_text):
            continue
        descriptor = _next_line_descriptor(encounter_text, ent_end)
        if descriptor is None:
            continue
        _desc_start, desc_end, _desc_text = descriptor
        ent["start"] = ent_start
        ent["end"] = desc_end
        ent["text"] = encounter_text[ent_start:desc_end]
        ent["__cross_line_merged__"] = True

    return entities


# ── Layer 4b: Observable Surface Cleanup ──
# DI-B5C78811, DO-728930A1.
# Strip trailing value/unit (and optional reference-range) tokens from
# observable_entity surface forms once Layer 4 has parsed them out into
# dedicated fields. Production stringification (terminology lookup, audit
# events) and validation scoring then see the same canonical name (e.g.
# "Haemoglobin" instead of "Haemoglobin 124 g/L (115-160)"), which avoids
# train/validate skew on phrase-level F1.


def clean_observable_surface_forms(
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Apply the shared surface-form cleanup to every observable_entity.

    Idempotent. Records the original surface form under ``__raw_text`` for
    audit. Entities that collapse to a bare numeric token are dropped --
    they carry no clinical meaning once their value/unit has been linked.
    """
    kept: list[dict[str, Any]] = []
    for ent in entities:
        if str(ent.get("label", "")) != "observable_entity":
            kept.append(ent)
            continue
        raw = str(ent.get("text", "") or "")
        cleaned = clean_observable_surface_text(raw)
        if not cleaned:
            logger.debug(
                "Layer 4b: dropping observable with no name after cleanup: %r",
                raw,
            )
            continue
        if cleaned != raw and "__raw_text" not in ent:
            ent["__raw_text"] = raw
        ent["text"] = cleaned
        for alias_key in ("normalized", "lookup_term"):
            value = ent.get(alias_key)
            if isinstance(value, str) and value.strip():
                normalised_alias = clean_observable_surface_text(value)
                if normalised_alias and not is_bare_numeric(normalised_alias):
                    ent[alias_key] = normalised_alias
        kept.append(ent)
    return kept


# ── Layer 5: Entity-Type Normalisation ──


def _normalized_value(ent: dict[str, Any]) -> str:
    """Return the lowercased normalized lookup term for an entity.

    Falls back to the lowercased surface text when no normalized field is
    present so that the nesting suppression guard can still operate.
    """
    raw = ent.get("normalized") or ent.get("lookup_term") or ent.get("text") or ""
    return str(raw).strip().lower()


def _observable_has_structured_measurement(ent: dict[str, Any]) -> bool:
    """True when Layer 4/6 already attached a measurement to this observable."""
    if str(ent.get("label", "")) != "observable_entity":
        return False
    value = str(ent.get("value") or "").strip()
    if not value:
        return False
    unit = str(ent.get("unit") or "").strip()
    if unit:
        return True
    return _is_string_result_text(value)


def _fetch_neo4j_entity_norm_rules(family: str) -> list[dict]:
    """Fetch :NerGuardRule nodes for entity-type normalisation from Neo4j.

    Returns [] when Neo4j is unreachable.
    """
    try:
        from libs.pipeline.config_loader import _fetch_neo4j_rules

        return _fetch_neo4j_rules(family)
    except Exception:
        logger.warning(
            "Could not fetch entity-type norm rules from Neo4j -- using builtins",
            exc_info=True,
        )
        return []


def reload_entity_type_norm() -> None:
    """Rebuild entity-type normalisation lookup sets from Neo4j custom rules.

    Call this after creating or deactivating an :NerGuardRule node with
    family='entity_type_norm'.
    """
    global _EPISODE_MARKER_TEXTS
    import json

    rows = _fetch_neo4j_entity_norm_rules("entity_type_norm")
    custom_markers: set[str] = set()
    for row in rows:
        if not row.get("active", True):
            continue
        try:
            payload = json.loads(row.get("payload") or "{}")
        except (ValueError, TypeError):
            payload = {}
        rule_type = payload.get("rule_type") or row.get("rule_type", "episode_marker")
        text = (payload.get("text") or row.get("text", "")).strip().lower()
        if text and rule_type == "episode_marker":
            custom_markers.add(text)
    _EPISODE_MARKER_TEXTS = _BUILTIN_EPISODE_MARKER_TEXTS | frozenset(custom_markers)
    logger.info(
        "Entity-type norm reloaded: %d built-in + %d custom episode markers",
        len(_BUILTIN_EPISODE_MARKER_TEXTS),
        len(custom_markers),
    )


def normalise_entity_types(entities: list[dict[str, Any]]) -> None:
    """Deterministic label correction rules.  Mutates *entities* in place."""

    for ent in entities:
        label = str(ent.get("label", ""))
        text = str(ent.get("text", ""))
        lowered = text.strip().lower()

        if label in {"attribute", "situation"} and _is_smoking_status_text(text):
            ent["label"] = "finding"

        if label == "X_DOSAGE" and _is_lab_value_text(text):
            ent["label"] = "qualifier_value"

        if (
            label == "observable_entity"
            and _is_numeric_measurement_text(text)
            and not _observable_has_structured_measurement(ent)
        ):
            ent["label"] = "qualifier_value"

        if label in {"finding", "situation"} and _is_result_descriptor(text):
            ent["label"] = "qualifier_value"

        if (
            label in {"X_TEMPORAL", "X_PATHWAY_MILESTONE"}
            and lowered in _EPISODE_MARKER_TEXTS
        ):
            ent["label"] = "qualifier_value"

        if label == "X_PATHWAY_MILESTONE" and ent.get("label") == "X_PATHWAY_MILESTONE":
            ent["label"] = "procedure"

        if label in {"attribute", "observable_entity"} and _is_lifestyle_topic_list(
            text
        ):
            ent["label"] = "finding"

        if label == "X_DOSAGE" and _SMOKING_CONSUMPTION_RE.search(text):
            ent["label"] = "qualifier_value"

        if _UNCERTAINTY_MARKER_RE.match(text.strip()):
            ent["label"] = "qualifier_value"

        if label in {"attribute", "finding"} and lowered in _SEVERITY_MODIFIER_TEXTS:
            ent["label"] = "qualifier_value"

        if _MDT_OUTCOME_RE.search(text):
            ent["label"] = "record_artifact"
        elif lowered == "mdt" and label in {"event", "record_artifact"}:
            ent["label"] = "procedure"

    # ── Suppression passes ──

    suppress_indices: set[int] = set()
    for i, ent in enumerate(entities):
        label = str(ent.get("label", ""))
        text = str(ent.get("text", ""))

        if (
            label == "substance"
            and _is_bare_analyte(text)
            and _has_nearby_observable(entities, i)
        ):
            suppress_indices.add(i)

        if label == "X_NEGATION_CUE":
            suppress_indices.add(i)

        if _REF_RANGE_ONLY_RE.match(text):
            suppress_indices.add(i)

        if label in {
            "body_structure",
            "body structure",
        } and not should_keep_body_structure(ent):
            suppress_indices.add(i)

    for i, ent_a in enumerate(entities):
        if i in suppress_indices:
            continue
        a_label = str(ent_a.get("label", ""))
        a_start = int(ent_a.get("start", 0) or 0)
        a_end = int(ent_a.get("end", 0) or 0)
        a_text = str(ent_a.get("text", "")).strip().lower()
        for j, ent_b in enumerate(entities):
            if j <= i or j in suppress_indices:
                continue
            b_label = str(ent_b.get("label", ""))
            b_start = int(ent_b.get("start", 0) or 0)
            b_end = int(ent_b.get("end", 0) or 0)
            b_text = str(ent_b.get("text", "")).strip().lower()

            if a_text == b_text and a_label == b_label:
                suppress_indices.add(j)
                continue

            if a_label == b_label:
                # Only suppress a nested span when its normalized lookup term
                # is identical to the containing span's term. Different lookup
                # terms indicate genuinely distinct clinical concepts (e.g.
                # "breast lesion" vs "malignant neoplasm of breast with mets")
                # that must both be preserved for multi-label NER output.
                a_norm = _normalized_value(ent_a)
                b_norm = _normalized_value(ent_b)
                if a_norm != b_norm:
                    continue
                if a_start <= b_start and a_end >= b_end:
                    suppress_indices.add(j)
                elif b_start <= a_start and b_end >= a_end:
                    suppress_indices.add(i)

    if suppress_indices:
        entities[:] = [e for i, e in enumerate(entities) if i not in suppress_indices]


# ── Layer 6: Value-Unit Linking ──


def _nearest_entity_within(
    obs_start: int,
    obs_end: int,
    candidate_indices: list[int],
    entities: list[dict[str, Any]],
    max_dist: int,
) -> int | None:
    """Return the index of the closest candidate entity within max_dist chars."""
    closest_idx: int | None = None
    closest_dist: int | None = None
    for idx in candidate_indices:
        e = entities[idx]
        e_start = int(e.get("start", 0) or 0)
        e_end = int(e.get("end", 0) or 0)
        dist = min(abs(e_start - obs_end), abs(obs_start - e_end))
        if closest_dist is None or dist < closest_dist:
            closest_dist = dist
            closest_idx = idx
    if closest_idx is None or (closest_dist is not None and closest_dist > max_dist):
        return None
    return closest_idx


def _raw_text_value_before(
    encounter_text: str, obs_start: int, window: int = 60
) -> tuple[str, str] | None:
    """Scan up to *window* characters before obs_start for a value or result."""
    if not encounter_text or obs_start <= 0:
        return None
    snippet = encounter_text[max(0, obs_start - window) : obs_start]
    parsed = _extract_value_unit(snippet)
    if parsed:
        return parsed
    for token in reversed(snippet.split()):
        if token.lower() in _RESULT_DESCRIPTOR_TEXTS:
            return token.lower(), ""
    return None


def link_observable_value_units(
    entities: list[dict[str, Any]],
    encounter_text: str = "",
) -> None:
    """Attach value/unit from nearby spans or raw text onto observable entities.

    Three passes, each only runs on observables that still have no value:

    Pass 1 - numeric entity: nearest qualifier_value whose text starts with
             a digit and contains a recognised unit, within 40 characters.
    Pass 2 - string entity: nearest entity whose text is in
             _RESULT_DESCRIPTOR_TEXTS, within 40 characters.
    Pass 3 - raw-text fallback: scan up to 60 characters before the
             observable start in encounter_text for a numeric or string match.

    Mutates *entities* in place.
    """
    obs_indices = [
        i
        for i, e in enumerate(entities)
        if str(e.get("label", "")) == "observable_entity"
    ]
    if not obs_indices:
        return

    numeric_indices = [
        i
        for i, e in enumerate(entities)
        if _is_numeric_measurement_text(str(e.get("text", "")))
    ]
    string_indices = [
        i
        for i, e in enumerate(entities)
        if _is_string_result_text(str(e.get("text", "")))
    ]

    for obs_i in obs_indices:
        obs = entities[obs_i]
        if obs.get("value") is not None:
            continue
        obs_start = int(obs.get("start", 0) or 0)
        obs_end = int(obs.get("end", 0) or 0)

        # Pass 1: numeric entity
        closest = _nearest_entity_within(
            obs_start, obs_end, numeric_indices, entities, max_dist=40
        )
        if closest is not None:
            parsed = _extract_value_unit(str(entities[closest].get("text", "")))
            if parsed:
                obs["value"], obs["unit"] = parsed
                continue

        # Pass 2: string result entity
        closest = _nearest_entity_within(
            obs_start, obs_end, string_indices, entities, max_dist=40
        )
        if closest is not None:
            obs["value"] = str(entities[closest].get("text", "")).strip().lower()
            obs["unit"] = ""
            continue

        # Pass 3: raw-text fallback
        result = _raw_text_value_before(encounter_text, obs_start)
        if result is not None:
            obs["value"], obs["unit"] = result


# ── Layer 9: Disorder Gate ──


def _apply_disorder_gate(
    encounter_text: str,
    entities: list[dict[str, Any]],
    coding_mode: str = "hitl",
) -> None:
    """LLM dual-model disorder classification.  Mutates *entities* in place."""
    for ent in entities:
        if str(ent.get("label", "")) != "disorder":
            continue
        assertion = str(ent.get("assertion") or "present").strip().lower()
        if assertion != "present":
            continue
        verdict = verify_disorder(
            str(ent.get("text", "")),
            encounter_text,
            coding_mode=coding_mode,
        )
        # Record verdict on the entity so the tier classifier can gate on
        # informational / uncertain / gate_failed directly.
        ent["disorder_verdict"] = verdict.value
        if verdict == DisorderVerdict.INFORMATIONAL:
            ent["__suppress__"] = True
        elif verdict == DisorderVerdict.HISTORICAL:
            ent["assertion"] = "historical"
        elif verdict == DisorderVerdict.REFUTED:
            ent["assertion"] = "refuted"
        elif verdict == DisorderVerdict.UNCERTAIN:
            ent["assertion"] = "possible"
            ent["__needs_review"] = True
        elif verdict == DisorderVerdict.GATE_FAILED:
            # Fail-closed: keep the entity but force review. Tier classifier
            # treats gate_failed the same as uncertain (tier 3 / review).
            ent["__needs_review"] = True
            ent["__gate_failed__"] = True


# ── Layer 3: Scope Guard (dict-based helper) ──


def _apply_scope_guard_to_dicts(
    encounter_text: str,
    entities: list[dict[str, Any]],
) -> None:
    """Reclassify or suppress entities using scope-guard rules.

    Mutates *entities* in place:
    - Safety-netting entities are REMOVED from the list (they are patient
      instructions, not clinical events, and must not reach the coding queue).
    - Recommendation-language entities are reclassified to 'hypothetical'.
    - Hedged-diagnosis disorder entities are reclassified to 'possible'.

    Uses ``_extract_sentence_window`` to scope the guard to the entity's
    local sentence rather than the full encounter.
    """
    to_remove: list[int] = []

    for i, ent in enumerate(entities):
        assertion = str(ent.get("assertion") or "present").strip().lower()
        start = int(ent.get("start", 0) or 0)
        end = int(ent.get("end", 0) or 0)
        sentence_text = _extract_sentence_window(encounter_text, start, end)

        new_assertion = reclassify_assertion(
            entity_semantic_tag=str(ent.get("label", "")),
            entity_assertion=assertion,
            sentence_text=sentence_text,
            entity_text=str(ent.get("text") or ent.get("normalized") or ""),
        )
        if new_assertion == SUPPRESSED:
            to_remove.append(i)
        elif new_assertion is not None and assertion in ("present", ""):
            ent["assertion"] = new_assertion

    for i in reversed(to_remove):
        entities.pop(i)


# ── Layer 7d: Double-Negation Guard ──

_PT_NEGATED_PREFIX_RE = re.compile(
    r"^(No |Absence of |Unable to |Not |Never )", re.IGNORECASE
)


def fix_double_negated_situations(entities: list[dict[str, Any]]) -> None:
    """Correct double negation on pre-negated SNOMED situation concepts.

    ConText fires before SNOMED lookup and may set assertion=absent when it
    sees a negation cue (e.g. "No") preceding the span.  For situation
    concepts whose preferred term already encodes the negative -- such as
    134420004 "No suicidal thoughts (situation)" -- absent+absent is a
    clinical inversion.  This guard restores assertion=present and records
    the correction reason for audit.

    Safe to call when term is absent: the PT check short-circuits and the
    entity is left unchanged.  Idempotent -- can be applied more than once.
    Only fires on situation semantic tag with assertion=absent.
    """
    for ent in entities:
        if ent.get("assertion") != "absent":
            continue
        tag = str(ent.get("semantic_tag") or ent.get("label", "")).lower()
        if tag != "situation":
            continue
        term = str(ent.get("term") or "")
        if not term or not _PT_NEGATED_PREFIX_RE.match(term):
            continue
        ent["assertion"] = "present"
        ent["_assertion_guard"] = "double_negated_situation"
        logger.info(
            "double_neg_guard: assertion restored to present | term=%r concept=%s",
            term,
            ent.get("concept_id"),
        )


# ── Layer 7d (b): Polarity-Encoded Finding Guard ──

_POLARITY_SUFFIX_RE = re.compile(
    r"\b(absent|not detected|not found|not present|negative)\s*\([^)]+\)\s*$",
    re.IGNORECASE,
)

_POLARITY_FINDING_TAGS = frozenset({"finding", "observable entity"})


def fix_polarity_encoded_findings(entities: list[dict[str, Any]]) -> None:
    """Correct assertion inversion on polarity-encoding SNOMED finding concepts.

    When a resolved SNOMED preferred term ends with a polarity word such as
    "absent", "not detected", or "negative" before the semantic tag parenthesis
    -- e.g. 370051000 "Perineural invasion by tumor absent (finding)" -- the
    concept already encodes the clinical absence. If ConText has additionally
    set assertion=absent (or any non-present value), the double negation inverts
    the clinical meaning.

    The concept choice is the authoritative statement of polarity. Entity
    assertion must always be "present" to mean "this concept applies to this
    patient".

    Fires only on finding and observable entity tags; situation prefix-negated
    concepts are handled by fix_double_negated_situations. Idempotent.
    """
    for ent in entities:
        if ent.get("assertion") == "present":
            continue
        tag = str(ent.get("semantic_tag") or ent.get("label", "")).lower().strip()
        if tag not in _POLARITY_FINDING_TAGS:
            continue
        term = str(ent.get("term") or "")
        if not term or not _POLARITY_SUFFIX_RE.search(term):
            continue
        ent["assertion"] = "present"
        ent["_assertion_guard"] = "polarity_encoded_finding"
        logger.info(
            "polarity_guard: assertion corrected to present | term=%r concept=%s",
            term,
            ent.get("concept_id"),
        )


# -- Layer 7d (c): Lifestyle status + PMH false-absent guards (DI-0F9542BF) --

_BUILTIN_LIFESTYLE_CONCEPT_IDS: frozenset[str] = frozenset(
    {
        "8517006",  # Ex-smoker (finding)
        "266919005",  # Never smoked tobacco (finding)
        "8392000",  # Non-smoker (finding)
    }
)
_custom_lifestyle_concept_ids: set[str] = set()
_LIFESTYLE_STATUS_CONCEPT_IDS: frozenset[str] = _BUILTIN_LIFESTYLE_CONCEPT_IDS


def _fetch_neo4j_assertion_rules(family: str) -> list[dict]:
    """Fetch :NerGuardRule nodes for the assertion guard from Neo4j.

    Returns [] when Neo4j is unreachable.
    """
    try:
        from libs.pipeline.config_loader import _fetch_neo4j_rules

        return _fetch_neo4j_rules(family)
    except Exception:
        logger.warning(
            "Could not fetch assertion guard rules from Neo4j -- using builtins",
            exc_info=True,
        )
        return []


def reload_lifestyle_status_guard() -> None:
    """Rebuild the lifestyle concept ID set from Neo4j custom rules.

    Call this after creating or deactivating an :NerGuardRule node with
    family='assertion_guard' and rule_type='lifestyle_concept'.
    """
    global _LIFESTYLE_STATUS_CONCEPT_IDS
    import json

    rows = _fetch_neo4j_assertion_rules("assertion_guard")
    custom: set[str] = set()
    for row in rows:
        if not row.get("active", True):
            continue
        try:
            payload = json.loads(row.get("payload") or "{}")
        except (ValueError, TypeError):
            payload = {}
        cid = payload.get("concept_id") or row.get("concept_id", "")
        if cid:
            custom.add(str(cid))
    _LIFESTYLE_STATUS_CONCEPT_IDS = _BUILTIN_LIFESTYLE_CONCEPT_IDS | frozenset(custom)
    logger.info(
        "Lifestyle status guard reloaded: %d built-in + %d custom concept IDs",
        len(_BUILTIN_LIFESTYLE_CONCEPT_IDS),
        len(custom),
    )


# Only status phrases that already encode polarity. Do not match bare "smoker"
# (true "not a smoker" / "denies smoking" must stay absent).
_LIFESTYLE_STATUS_TEXT_RE = re.compile(
    r"\b(ex[-\s]?smoker|former\s+smoker|never\s+smoked|non[-\s]?smoker)\b",
    re.IGNORECASE,
)

_PMH_POSITIVE_RE = re.compile(
    r"\b(?:background|history|hx|h/?o)\s+of\b",
    re.IGNORECASE,
)

_PMH_NEGATED_RE = re.compile(
    r"\b(?:no|denies|without|nil)\s+(?:known\s+)?"
    r"(?:background|history|hx|h/?o)\s+of\b",
    re.IGNORECASE,
)

_BUILTIN_PMH_CUES: tuple[str, ...] = (
    "background of",
    "history of",
    "hx of",
    "h/o",
)
_CUSTOM_PMH_CUES: tuple[str, ...] = ()


def reload_pmh_list_guard() -> None:
    """Load extra past-history cues from assertion_guard / pmh_list rules."""
    global _CUSTOM_PMH_CUES
    import json

    rows = _fetch_neo4j_assertion_rules("assertion_guard")
    cues: list[str] = []
    for row in rows:
        if not row.get("active", True):
            continue
        try:
            payload = json.loads(row.get("payload") or "{}")
        except (ValueError, TypeError):
            payload = {}
        if str(payload.get("rule_type") or "") != "pmh_list":
            continue
        pattern = str(payload.get("pattern") or "").strip()
        if pattern:
            cues.append(pattern)
    _CUSTOM_PMH_CUES = tuple(cues)
    logger.info("PMH list guard reloaded: %d custom cues", len(_CUSTOM_PMH_CUES))


def _pmh_positive_match(sentence: str) -> bool:
    if _PMH_POSITIVE_RE.search(sentence):
        return True
    lower = sentence.lower()
    for cue in _CUSTOM_PMH_CUES:
        if cue and cue.lower() in lower:
            return True
    return False


def _lifestyle_status_blob(ent: dict[str, Any]) -> str:
    parts = [
        ent.get("term"),
        ent.get("preferred_term"),
        ent.get("text"),
        ent.get("evidence"),
        ent.get("lookup_term"),
    ]
    return " ".join(str(p) for p in parts if p)


def fix_lifestyle_status_assertions(entities: list[dict[str, Any]]) -> None:
    """Restore present for lifestyle status concepts wrongly marked absent.

    Status concepts such as Ex-smoker already encode cessation. Marking them
    absent inverts meaning (as if the patient were not an ex-smoker). Idempotent.
    Atlas: DI-0F9542BF / DO-15449C6E / VT-A1919820.
    """
    for ent in entities:
        if ent.get("assertion") == "present":
            continue
        concept_id = str(ent.get("concept_id") or ent.get("conceptId") or "").strip()
        blob = _lifestyle_status_blob(ent)
        if concept_id not in _LIFESTYLE_STATUS_CONCEPT_IDS and not (
            blob and _LIFESTYLE_STATUS_TEXT_RE.search(blob)
        ):
            continue
        ent["assertion"] = "present"
        ent["_assertion_guard"] = "lifestyle_status"
        logger.info(
            "lifestyle_status_guard: restored present | text=%r concept=%s",
            blob[:80],
            concept_id or None,
        )


def fix_pmh_list_false_absent(entities: list[dict[str, Any]]) -> None:
    """Restore present when LLM absents a condition inside a positive PMH list.

    Covers 'background of X and Y' / 'history of X' when ConText cannot overwrite
    a sticky LLM absent. Leaves true 'no history of X' untouched. Idempotent.
    Atlas: DI-0F9542BF / DO-15449C6E / VT-A1919820.
    """
    for ent in entities:
        if ent.get("assertion") != "absent":
            continue
        sentence = str(
            ent.get("evidence_sentence") or ent.get("sentence") or ent.get("text") or ""
        )
        if not sentence:
            continue
        if _PMH_NEGATED_RE.search(sentence):
            continue
        if not _pmh_positive_match(sentence):
            continue
        ent["assertion"] = "present"
        ent["_assertion_guard"] = "pmh_list_false_absent"
        logger.info(
            "pmh_list_guard: assertion restored to present | evidence=%r",
            (ent.get("evidence") or ent.get("text") or "")[:80],
        )


_SITUATION_SUSPECTED_CANCER_RE = re.compile(
    r"(?:"
    r"\bsuspected\b.+\bcancer\b|"
    r"\bcancer\b.+\bsuspected\b|"
    r"malignant\s+neoplasm\s+of\s+.+\s+suspected|"
    r"\b(?:gastric|stomach|oesophageal|esophageal|colorectal|pancreatic|"
    r"breast|lung|skin|prostate)\s+malignancy\b|"
    r"cancer\s+pathway\s+for\s+.+\bcancer\b"
    r")",
    re.IGNORECASE,
)

_SITUATION_FAMILY_HISTORY_RE = re.compile(
    r"(?:"
    r"\bfamily\s+history\s+of\b|"
    r"\bfamily\s+history\s*:|"
    r"\bfh(?:x)?\s+of\b|"
    r"\b(?:mother|father|mum|mom|dad|sibling|sister|brother|"
    r"parent|grandmother|grandfather)\s+had\b"
    r")",
    re.IGNORECASE,
)


def _is_situation_entity(ent: dict[str, Any]) -> bool:
    tag = str(ent.get("semantic_tag") or ent.get("label") or "").lower().strip()
    if tag == "situation":
        return True
    term = str(ent.get("term") or "")
    return bool(re.search(r"\(situation\)\s*$", term, re.IGNORECASE))


def _situation_guard_blob(ent: dict[str, Any]) -> str:
    parts = [
        ent.get("text"),
        ent.get("evidence"),
        ent.get("term"),
        ent.get("normalized"),
        ent.get("normalized_lookup"),
        ent.get("lookup_term"),
    ]
    return " ".join(str(p) for p in parts if p)


def fix_situation_present_assertions(entities: list[dict[str, Any]]) -> None:
    """Restore present for suspected-cancer and FH situation concepts.

    ConText maps 'suspected' -> possible and 'mum'/'fhx' -> family. For SNOMED
    situation concepts those cues are already encoded in the concept; assertion
    must stay present. Idempotent.
    Atlas: DI-95CB940F / DO-847F1ED5 / VT-BA44A8B3.
    """
    for ent in entities:
        if ent.get("assertion") == "present":
            continue
        if not _is_situation_entity(ent):
            continue
        blob = _situation_guard_blob(ent)
        if not blob:
            continue
        if _SITUATION_SUSPECTED_CANCER_RE.search(blob):
            ent["assertion"] = "present"
            ent["_assertion_guard"] = "situation_suspected_cancer"
            logger.info(
                "situation_present_guard: restored present (suspected) | text=%r",
                blob[:80],
            )
            continue
        if _SITUATION_FAMILY_HISTORY_RE.search(blob):
            ent["assertion"] = "present"
            ent["_assertion_guard"] = "situation_family_history"
            logger.info(
                "situation_present_guard: restored present (family history) | text=%r",
                blob[:80],
            )


def apply_false_absent_assertion_guards(entities: list[dict[str, Any]]) -> None:
    """Run lifestyle-status, PMH, situation-present, and contrast guards."""
    from libs.ner.contrast_negation_guard import fix_contrast_positive_false_absent

    fix_lifestyle_status_assertions(entities)
    fix_pmh_list_false_absent(entities)
    fix_situation_present_assertions(entities)
    fix_contrast_positive_false_absent(entities)


# ── Layer 8: Situation Lookup Normalisation ──


def _apply_situation_lookup(entities: list[dict[str, Any]]) -> None:
    """Normalise situation entity text for terminology resolution.

    Mutates *entities* in place — adds ``normalized_lookup`` key.
    """
    for ent in entities:
        if str(ent.get("label", "")) != "situation":
            continue
        canonical = normalize_situation_lookup(str(ent.get("text", "")))
        if canonical:
            ent["normalized_lookup"] = canonical


def _apply_referral_procedure_assertion_guard(
    entities: list[dict[str, Any]],
) -> None:
    """Keep referral procedures from being marked as uncertain disease mentions."""
    for ent in entities:
        label = str(ent.get("label", "")).strip().lower().replace(" ", "_")
        assertion = str(ent.get("assertion") or "").strip().lower()
        if label != "procedure" or assertion != "possible":
            continue
        text = str(
            ent.get("text")
            or ent.get("normalized")
            or ent.get("normalized_lookup")
            or ""
        )
        if is_referral_procedure_phrase(text):
            ent["assertion"] = "present"
            ent["_assertion_guard"] = "referral_procedure"


def _split_observable_trend_results(
    encounter_text: str,
    entities: list[dict[str, Any]],
) -> None:
    """Split dual-value trend sentences into present + historical observables."""
    additions: list[dict[str, Any]] = []
    for ent in entities:
        if str(ent.get("label", "")) != "observable_entity":
            continue
        if ent.get("_trend_split_role") == "historical":
            continue

        start = int(ent.get("start", 0) or 0)
        end = int(ent.get("end", 0) or 0)
        s_start, s_end = _extract_sentence_bounds(encounter_text, start, end)
        sentence = encounter_text[s_start:s_end]
        if not _TREND_SPLIT_RE.search(sentence):
            continue

        matches = list(_VALUE_UNIT_RE.finditer(sentence))
        if len(matches) < 2:
            continue

        marker = re.search(
            r"\bfrom\s+(?:peak(?:\s+of)?|previous(?:ly)?|prior)\b",
            sentence,
            re.IGNORECASE,
        )
        current_m = matches[0]
        historical_m = matches[-1]
        if marker:
            after_marker = [m for m in matches if m.start() >= marker.end()]
            before_marker = [m for m in matches if m.end() <= marker.start()]
            if after_marker:
                historical_m = after_marker[0]
            if before_marker:
                current_m = before_marker[-1]
            elif len(matches) >= 2:
                current_m = matches[0]
                historical_m = matches[-1]

        current_value = (current_m.group("value") or "").strip()
        current_unit = (current_m.group("unit") or "").strip()
        historical_value = (historical_m.group("value") or "").strip()
        historical_unit = (historical_m.group("unit") or "").strip()
        if (
            not current_value
            or not current_unit
            or not historical_value
            or not historical_unit
            or (
                current_value == historical_value
                and current_unit.lower() == historical_unit.lower()
            )
        ):
            continue

        ent["value"] = current_value
        ent["unit"] = current_unit
        ent["assertion"] = "present"
        ent["_trend_split_role"] = "current"

        hist_ent = dict(ent)
        hist_ent["value"] = historical_value
        hist_ent["unit"] = historical_unit
        hist_ent["assertion"] = "historical"
        hist_ent["_trend_split_role"] = "historical"
        additions.append(hist_ent)

    if additions:
        entities.extend(additions)


# ── Public API ──


def _entity_anchor(entity: dict[str, Any]) -> str:
    """Stable per-entity anchor for before/after layer comparisons."""
    return "|".join(
        [
            str(entity.get("start", "")),
            str(entity.get("end", "")),
            str(entity.get("text", "")),
        ]
    )


def _entity_preview(entity: dict[str, Any]) -> str:
    """Compact preview used in layer telemetry."""
    text = str(entity.get("text", "")).strip()
    label = str(entity.get("label", "")).strip()
    assertion = str(entity.get("assertion", "")).strip()
    parts = [p for p in (text, label, assertion) if p]
    return " | ".join(parts[:3])


def _summarise_layer_delta(
    before_entities: list[dict[str, Any]],
    after_entities: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return add/remove/update counts and short samples for one layer."""
    before_map = {_entity_anchor(e): e for e in before_entities}
    after_map = {_entity_anchor(e): e for e in after_entities}

    added_anchors = [a for a in after_map if a not in before_map]
    removed_anchors = [a for a in before_map if a not in after_map]
    shared = [a for a in before_map if a in after_map]
    updated_anchors = [a for a in shared if before_map[a] != after_map[a]]

    return {
        "added_count": len(added_anchors),
        "removed_count": len(removed_anchors),
        "updated_count": len(updated_anchors),
        "sample_added": [_entity_preview(after_map[a]) for a in added_anchors[:3]],
        "sample_removed": [_entity_preview(before_map[a]) for a in removed_anchors[:3]],
        "sample_updated": [
            {
                "before": _entity_preview(before_map[a]),
                "after": _entity_preview(after_map[a]),
            }
            for a in updated_anchors[:3]
        ],
    }


def _snapshot_extractor_assertions(entities: list[dict[str, Any]]) -> None:
    """Record the extractor-provided assertion before post-processing mutates it.

    The tier classifier reads ``assertion_parity_failed`` to know when the
    LLM and the deterministic post-processing stack (ConText + scope guard)
    disagreed about an entity's assertion. When they disagree we hold the
    entity at tier 2 rather than auto-coding, since exactly one of the two
    signals is wrong.
    """
    for ent in entities:
        if "_extractor_assertion" in ent:
            continue
        ent["_extractor_assertion"] = str(ent.get("assertion") or "present")


def _apply_assertion_parity_check(entities: list[dict[str, Any]]) -> None:
    """Flag entities where extractor and post-processing disagreed."""
    for ent in entities:
        before = str(ent.pop("_extractor_assertion", "") or "").strip().lower()
        after = str(ent.get("assertion") or "").strip().lower()
        if not before or not after:
            continue
        ent["assertion_parity_failed"] = before != after


def run_post_processing_with_trace(
    encounter_text: str,
    entities: list[dict],
    *,
    rules: list[PostProcessorRule] | None = None,
    enable_disorder_gate: bool = False,
    coding_mode: str = "hitl",
    local_concept_patterns: list[LocalConceptPattern] | None = None,
) -> tuple[list[dict], list[dict[str, Any]]]:
    """Run post-processing and return (entities, per-layer trace)."""
    working = [dict(e) for e in entities]
    _snapshot_extractor_assertions(working)
    layer_trace: list[dict[str, Any]] = []
    _local_patterns = local_concept_patterns or []

    def _run_layer(
        layer_id: str,
        name: str,
        fn,
        *,
        skip_when: bool = False,
        skip_reason: str | None = None,
    ) -> None:
        nonlocal working
        if skip_when:
            layer_trace.append(
                {
                    "layer_id": layer_id,
                    "name": name,
                    "status": "skipped",
                    "reason": skip_reason or "disabled",
                    "before_count": len(working),
                    "after_count": len(working),
                    "added_count": 0,
                    "removed_count": 0,
                    "updated_count": 0,
                    "duration_ms": 0,
                }
            )
            return

        before = [dict(e) for e in working]
        started = time.perf_counter()
        try:
            result = fn(working)
            if result is not None:
                working = result
            after = [dict(e) for e in working]
            delta = _summarise_layer_delta(before, after)
            layer_trace.append(
                {
                    "layer_id": layer_id,
                    "name": name,
                    "status": "completed",
                    "before_count": len(before),
                    "after_count": len(after),
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                    **delta,
                }
            )
        except Exception as exc:
            layer_trace.append(
                {
                    "layer_id": layer_id,
                    "name": name,
                    "status": "error",
                    "error": str(exc),
                    "before_count": len(before),
                    "after_count": len(working),
                    "added_count": 0,
                    "removed_count": 0,
                    "updated_count": 0,
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                }
            )
            raise

    # Layer 0: Concept-Specific Suppression Guard
    # Deterministic block for known LLM over-application patterns, e.g.
    # 395100000 (No evidence of cancer found) being applied to routine screening.
    _run_layer(
        "layer_0",
        "Concept Suppression Guard",
        _suppress_screening_false_positives,
    )

    # Layer 1: Post-Processor Rules
    _run_layer(
        "layer_1",
        "Post-Processor Rules",
        lambda current: (
            apply_rules_to_entities(encounter_text, current, rules)
            if rules
            else current
        ),
        skip_when=rules is None,
        skip_reason="no rules configured",
    )

    # Layer 2: Lab-Value Guard
    def _layer_2(current: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for ent in current:
            ent_start = int(ent.get("start", 0) or 0)
            ent_end = int(ent.get("end", 0) or 0)
            sentence_window = _extract_sentence_window(
                encounter_text, ent_start, ent_end
            )
            normalized = str(
                ent.get("normalized")
                or ent.get("normalized_lookup")
                or ent.get("lookup_term")
                or ent.get("text", "")
            )
            if should_suppress_disorder(
                entity_text=str(ent.get("text", "")),
                entity_semantic_tag=str(ent.get("label", "")),
                entity_normalized=normalized,
                sentence_text=sentence_window,
                entity_numeric_value=str(ent.get("value", "") or ""),
                entity_unit=str(ent.get("unit", "") or ""),
            ):
                ent["__suppress__"] = True
        return [e for e in current if not e.get("__suppress__")]

    _run_layer("layer_2", "Lab-Value Guard", _layer_2)

    # Layer 2b: Referral Routing Guard (DI-B5C78811 / UN-89E2AE36)
    def _layer_2b(current: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for ent in current:
            if should_suppress_referral_routing_entity(ent):
                ent["__suppress__"] = True
                ent["_routing_guard"] = "informational_referral"
        return [e for e in current if not e.get("__suppress__")]

    _run_layer("layer_2b", "Referral Routing Guard", _layer_2b)

    # Layer 3: Scope Guard
    _run_layer(
        "layer_3",
        "Scope Guard",
        lambda current: (_apply_scope_guard_to_dicts(encounter_text, current), current)[
            1
        ],
    )

    # Layer 3b: Lab Triple Recovery
    # Deterministically add missing procedure / observable_entity / finding
    # spans on UK primary-care lab-result lines (e.g. "Reticulocyte count
    # (42X..) 96 10^9/L [20 - 80] - Outside reference range"). The spancat
    # suggester is capped at 10 tokens which is shorter than the typical
    # observable span, and the LLM extractor by design emits the parameter
    # name only -- so without this layer the long observable / finding
    # entities never reach Layer 4 to be enriched. Idempotent: never
    # duplicates an existing span with the same (label, start, end).
    _run_layer(
        "layer_3b",
        "Lab Triple Recovery",
        lambda current: recover_lab_triples(encounter_text, current),
    )

    # Layer 3c: Request Reason Recovery
    # Some lab request records carry clinically meaningful reasons after
    # "Reasons for Request:" which are not part of the lab result itself.
    _run_layer(
        "layer_3c",
        "Request Reason Recovery",
        lambda current: recover_request_reason_entities(encounter_text, current),
    )

    # Layer 3c2: Breast screening programme abnormal (Read 68621 / SNOMED 171176006)
    _run_layer(
        "layer_3c2",
        "Breast Screening Outcome Recovery",
        lambda current: recover_breast_screening_outcome_finding(
            encounter_text, current
        ),
    )

    # Layer 3c3: LEO-local concept exact-match recovery (approved aliases)
    _run_layer(
        "layer_3c3",
        "Local Concept Recovery",
        lambda current: recover_local_concept_entities(
            encounter_text, current, _local_patterns
        ),
        skip_when=not _local_patterns,
        skip_reason="no local concept patterns",
    )

    # Layer 3d: Cross-Line Lab Finding Merge (DI-B5C78811, DO-728930A1,
    # VT-29880CC8). Extend an observable_entity span forward across at
    # most one blank line when the next non-blank line begins with a
    # recognised result-interpretation phrase. This lets Layer 4 emit the
    # matching `finding` sub-entity from one merged span instead of leaving
    # the interpretation phrase orphaned in a separate sentence (e.g. PSA
    # value line followed by a blank line and "Outside reference range").
    _run_layer(
        "layer_3d",
        "Cross-Line Lab Finding Merge",
        lambda current: merge_cross_line_lab_findings(encounter_text, current),
    )

    # Layer 4: Observable Normalisation
    _run_layer(
        "layer_4",
        "Observable Normalisation",
        lambda current: normalize_observable_entities(
            encounter_text,
            current,
            add_qualifier_value=True,
        ),
    )

    # Layer 4b: Observable Surface Cleanup (DI-B5C78811 / DO-728930A1)
    _run_layer(
        "layer_4b",
        "Observable Surface Cleanup",
        clean_observable_surface_forms,
    )

    # Layer 4c: Measurement Observable Recovery (DI-B5C78811 / DO-728930A1).
    # Retag anthropometry names split from their value so Layer 5 / terminology
    # see an observable_entity with structured value and unit.
    _run_layer(
        "layer_4c",
        "Measurement Observable Recovery",
        lambda current: recover_measurement_observables(encounter_text, current),
    )

    # Layer 5: Value-Unit Linking (before entity-type norm -- see module docstring)
    _run_layer(
        "layer_5",
        "Value-Unit Linking",
        lambda current: (
            link_observable_value_units(current, encounter_text),
            current,
        )[1],
    )

    # Layer 6: Entity-Type Normalisation
    _run_layer(
        "layer_6",
        "Entity-Type Normalisation",
        lambda current: (normalise_entity_types(current), current)[1],
    )

    # Layer 6b: Taught analyte SNOMED override (FormSchema ordered_tests)
    def _apply_taught_analyte_codes(
        current: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        from libs.pipeline.document_quality import form_fingerprint
        from libs.pipeline.form_schema_normalizer import apply_schema_analyte_codes
        from libs.pipeline.form_schema_store import get_cached_schema

        schema = get_cached_schema(form_fingerprint(encounter_text))
        if schema is None:
            return current
        return apply_schema_analyte_codes(
            current, schema, schema.chunk_section_map or []
        )

    _run_layer(
        "layer_6b", "Taught Analyte SNOMED Override", _apply_taught_analyte_codes
    )

    # Layer 7: ConText Assertion Detection
    _run_layer(
        "layer_7",
        "ConText Assertion Detection",
        lambda current: (
            apply_context_detection_to_dicts(encounter_text, current),
            current,
        )[1],
    )

    # Layer 7b: Referral Procedure Assertion Guard
    _run_layer(
        "layer_7b",
        "Referral Procedure Assertion Guard",
        lambda current: (_apply_referral_procedure_assertion_guard(current), current)[
            1
        ],
    )

    # Layer 7c: Observable Trend Split
    _run_layer(
        "layer_7c",
        "Observable Trend Split",
        lambda current: (
            _split_observable_trend_results(encounter_text, current),
            current,
        )[1],
    )

    # Layer 7d: Double-Negation + false-absent guards
    # Polarity / double-neg need a resolved SNOMED preferred term (training
    # path). Lifestyle + PMH guards also use evidence text and run here for
    # both paths; terminology._resolve_terms re-runs them after SNOMED resolve.
    def _run_double_neg_guards(current: list) -> list:
        fix_double_negated_situations(current)
        fix_polarity_encoded_findings(current)
        apply_false_absent_assertion_guards(current)
        return current

    _run_layer("layer_7d", "Double-Negation Guards", _run_double_neg_guards)

    # Layer 8: Situation Lookup Normalisation
    _run_layer(
        "layer_8",
        "Situation Lookup Normalisation",
        lambda current: (_apply_situation_lookup(current), current)[1],
    )

    # Layer 8b: Suspected cancer lookup enrichment (pre-terminology)
    def _run_suspected_cancer_lookup(
        current: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        from libs.ner.suspected_cancer_guard import enrich_suspected_cancer_lookups

        enrich_suspected_cancer_lookups(encounter_text, current)
        return current

    _run_layer(
        "layer_8b",
        "Suspected Cancer Lookup Enrichment",
        _run_suspected_cancer_lookup,
    )

    # Layer 8c: Unresulted-test guard.
    # Runs after value-unit linking and after ConText, because it needs the
    # value and the assertion to decide. A battery label sitting on a blank
    # row of a taught blood panel is not evidence the test was done.
    def _run_unresulted_test_guard(
        current: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        from libs.pipeline.unresulted_test_guard import (
            suppress_unresulted_test_mentions,
        )

        kept, dropped = suppress_unresulted_test_mentions(current, encounter_text)
        for ent in dropped:
            logger.info(
                "Unresulted-test guard dropped %r: %s",
                ent.get("text"),
                ent.get("suppressed_reason"),
            )
        return kept

    _run_layer(
        "layer_8c",
        "Unresulted-Test Guard",
        _run_unresulted_test_guard,
    )

    # Layer 9: Disorder Gate (optional)
    def _layer_9(current: list[dict[str, Any]]) -> list[dict[str, Any]]:
        _apply_disorder_gate(encounter_text, current, coding_mode=coding_mode)
        return [e for e in current if not e.get("__suppress__")]

    _run_layer(
        "layer_9",
        "Disorder Gate",
        _layer_9,
        skip_when=not enable_disorder_gate,
        skip_reason="disabled",
    )

    _apply_assertion_parity_check(working)

    return working, layer_trace


def run_post_processing(
    encounter_text: str,
    entities: list[dict],
    *,
    rules: list[PostProcessorRule] | None = None,
    enable_disorder_gate: bool = False,
    coding_mode: str = "hitl",
    local_concept_patterns: list[LocalConceptPattern] | None = None,
) -> list[dict]:
    """Canonical post-processing stack applied identically to training and runtime.

    Args:
        encounter_text: Full de-identified encounter text.
        entities: Mutable list of entity dicts (``text``, ``label``,
            ``start``, ``end``, ``assertion``, …).
        rules: Optional DB-driven PostProcessorRules for Layer 1.
        enable_disorder_gate: When True, run the LLM disorder gate (Layer 9).
            Defaults to True in training, False at runtime.
        coding_mode: Coding mode forwarded to the disorder gate.
        local_concept_patterns: Optional approved LEO-local alias patterns
            for Layer 3c3 exact-match recovery.

    Returns:
        The (mutated) entity list after all layers have run.
    """
    processed, _trace = run_post_processing_with_trace(
        encounter_text,
        entities,
        rules=rules,
        enable_disorder_gate=enable_disorder_gate,
        coding_mode=coding_mode,
        local_concept_patterns=local_concept_patterns,
    )
    return processed
