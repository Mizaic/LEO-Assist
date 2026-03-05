"""Canonical post-processing stack applied identically to training and runtime.

All 9 layers execute in a fixed order on plain entity dicts.  Both the
training verification pipeline (label_verifier) and the runtime coding
pipeline (pipeline_service) call ``run_post_processing()`` so that gold
training data and production inference share exactly the same
post-processing logic, eliminating train/serve skew.

Layer order
-----------
1. Post-Processor Rules   -- DB-driven text/label rewrites
2. Lab-Value Guard        -- suppress disorders inferred from lab results
3. Scope Guard            -- reclassify assertions in safety-netting /
                             recommendation / hedged-diagnosis text
4. Observable Norm.       -- clean observable spans, attach value/unit/ref
5. Entity-Type Norm.      -- deterministic label corrections
6. Value-Unit Linking     -- attach numeric values to nearby observables
7. ConText Assertion Det. -- MedSpaCy negation/historical/family detection
8. Situation Lookup Norm. -- normalise situation text for terminology
9. Disorder Gate          -- LLM dual-model disorder classification (optional)
"""
from __future__ import annotations

import logging
import re
from typing import Any

from libs.llm_client.disorder_verifier import DisorderVerdict, verify_disorder
from libs.ner.context_detector import normalize_situation_lookup
from libs.ner.context_engine import apply_context_detection_to_dicts
from libs.ner.lab_value_guard import should_suppress_disorder
from libs.ner.observable_post_processor import normalize_observable_entities
from libs.ner.post_processor_rules import PostProcessorRule, apply_rules_to_entities
from libs.ner.scope_guard import reclassify_assertion

logger = logging.getLogger(__name__)

_SENTENCE_BOUNDARY_RE = re.compile(r"(?:\.(?:\s|$)|\n)")


def _extract_sentence_window(
    encounter_text: str, start: int, end: int, margin: int = 300,
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


# ── regex / constants for entity-type normalisation (Layer 5) ──

_VALUE_UNIT_RE = re.compile(
    r"(?P<value>[<>]?\s*\d+(?:\.\d+)?)\s*(?P<unit>(?:10\^\d+\/[A-Za-z]+|[A-Za-z/%]+(?:\/[A-Za-z]+)*))",
    re.IGNORECASE,
)

_LAB_UNIT_INDICATORS = re.compile(
    r"(?:mmol|umol|nmol|pmol|mg|ug|ng|pg|g|iu|mL|miu|L|mol|fl|10\^9|%|ratio|kg|kpa|mmhg|bpm|ug/g|cigs)",
    re.IGNORECASE,
)

_RESULT_DESCRIPTOR_TEXTS = frozenset({
    "abnormal", "abnormal but expected", "normal", "satisfactory",
    "outside reference range", "within normal limits", "within reference range",
    "normal - no action", "borderline", "high", "low", "raised", "elevated",
    "nad", "no abnormality detected", "fobt non-response", "non-response",
    "no problems or concerns", "no problemds or concerns",
    "negative", "positive", "reactive", "non-reactive",
    "but expected", "weight stable",
})

_EPISODE_MARKER_TEXTS = frozenset({
    "new episode", "ongoing episode", "first episode",
})

_LIFESTYLE_FACTOR_TEXTS = frozenset({
    "diet", "alcohol", "exercise", "weight", "bmi", "smoking", "drives",
    "sleep", "caffeine",
})

_LIFESTYLE_SEP_RE = re.compile(r"[\s/&,]+")

_UNCERTAINTY_MARKER_RE = re.compile(r"^\?{1,4}$")

_SEVERITY_MODIFIER_TEXTS = frozenset({
    "severe", "mild", "moderate", "minor", "major", "urgent",
    "worsened", "worsening", "improving", "stable", "unchanged",
    "pale", "slight", "significant", "marked",
})

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

_ANALYTE_NAMES = frozenset({
    "creatinine", "albumin", "phosphate", "inorganic phosphate", "sodium",
    "potassium", "calcium", "bilirubin", "cholesterol", "glucose", "urea",
    "ferritin", "haemoglobin", "globulin", "triglyceride", "triglycerides",
    "folate", "iron", "zinc", "magnesium", "copper", "lithium",
    "testosterone", "oestradiol", "cortisol", "thyroxine",
    "chloride", "bicarbonate", "protein", "alkaline phosphatase",
})

_BARE_NUMERIC_RE = re.compile(r"^[<>]?\s*\d+(?:\.\d+)?\s*$")

# ── helper predicates ──


def _is_lifestyle_topic_list(text: str) -> bool:
    tokens = [t for t in _LIFESTYLE_SEP_RE.split(text.lower()) if t and t != "and"]
    return bool(tokens) and all(t in _LIFESTYLE_FACTOR_TEXTS for t in tokens)


def _is_smoking_status_text(text: str) -> bool:
    lowered = text.strip().lower()
    return "smoking status" in lowered or lowered in {
        "smoker", "non-smoker", "ex-smoker", "never smoker",
        "current smoker", "ex smoker", "non smoker",
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


def _has_nearby_observable(entities: list[dict[str, Any]], target_idx: int, max_dist: int = 80) -> bool:
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


# ── Layer 5: Entity-Type Normalisation ──


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

        if label == "observable_entity" and _is_numeric_measurement_text(text):
            ent["label"] = "qualifier_value"

        if label in {"finding", "situation"} and _is_result_descriptor(text):
            ent["label"] = "qualifier_value"

        if label in {"X_TEMPORAL", "X_PATHWAY_MILESTONE"} and lowered in _EPISODE_MARKER_TEXTS:
            ent["label"] = "qualifier_value"

        if label == "X_PATHWAY_MILESTONE" and ent.get("label") == "X_PATHWAY_MILESTONE":
            ent["label"] = "procedure"

        if label in {"attribute", "observable_entity"} and _is_lifestyle_topic_list(text):
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

        if label == "substance" and _is_bare_analyte(text) and _has_nearby_observable(entities, i):
            suppress_indices.add(i)

        if label == "X_NEGATION_CUE":
            suppress_indices.add(i)

        if _REF_RANGE_ONLY_RE.match(text):
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
                if a_start <= b_start and a_end >= b_end:
                    suppress_indices.add(j)
                elif b_start <= a_start and b_end >= a_end:
                    suppress_indices.add(i)

    if suppress_indices:
        entities[:] = [e for i, e in enumerate(entities) if i not in suppress_indices]


# ── Layer 6: Value-Unit Linking ──


def link_observable_value_units(entities: list[dict[str, Any]]) -> None:
    """Attach value/unit from nearby numeric spans onto observable entities.

    Mutates *entities* in place.
    """
    observable_indices = [
        i for i, e in enumerate(entities)
        if str(e.get("label", "")) == "observable_entity"
    ]
    if not observable_indices:
        return

    measurement_indices = [
        i for i, e in enumerate(entities)
        if _is_numeric_measurement_text(str(e.get("text", "")))
    ]
    if not measurement_indices:
        return

    for obs_i in observable_indices:
        obs = entities[obs_i]
        if obs.get("value") is not None and obs.get("unit"):
            continue
        obs_start = int(obs.get("start", 0) or 0)
        obs_end = int(obs.get("end", 0) or 0)
        closest_idx: int | None = None
        closest_dist: int | None = None

        for meas_i in measurement_indices:
            meas = entities[meas_i]
            meas_start = int(meas.get("start", 0) or 0)
            meas_end = int(meas.get("end", 0) or 0)
            dist = min(abs(meas_start - obs_end), abs(obs_start - meas_end))
            if closest_dist is None or dist < closest_dist:
                closest_dist = dist
                closest_idx = meas_i

        if closest_idx is None or (closest_dist is not None and closest_dist > 40):
            continue
        parsed = _extract_value_unit(str(entities[closest_idx].get("text", "")))
        if not parsed:
            continue
        value, unit = parsed
        obs["value"] = value
        obs["unit"] = unit


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
            str(ent.get("text", "")), encounter_text, coding_mode=coding_mode,
        )
        if verdict == DisorderVerdict.INFORMATIONAL:
            ent["__suppress__"] = True
        elif verdict == DisorderVerdict.HISTORICAL:
            ent["assertion"] = "historical"
        elif verdict == DisorderVerdict.REFUTED:
            ent["assertion"] = "refuted"
        elif verdict == DisorderVerdict.UNCERTAIN:
            ent["assertion"] = "possible"
            ent["__needs_review"] = True


# ── Layer 3: Scope Guard (dict-based helper) ──


def _apply_scope_guard_to_dicts(
    encounter_text: str,
    entities: list[dict[str, Any]],
) -> None:
    """Reclassify assertions using scope-guard rules.  Mutates *entities* in place.

    Uses ``_extract_sentence_window`` to scope the guard to the entity's
    local sentence rather than the full encounter.
    """
    for ent in entities:
        assertion = str(ent.get("assertion") or "present").strip().lower()
        if assertion not in ("present", ""):
            continue
        start = int(ent.get("start", 0) or 0)
        end = int(ent.get("end", 0) or 0)
        sentence_text = _extract_sentence_window(encounter_text, start, end)

        new_assertion = reclassify_assertion(
            entity_semantic_tag=str(ent.get("label", "")),
            entity_assertion=assertion,
            sentence_text=sentence_text,
            entity_text=str(ent.get("text") or ent.get("normalized") or ""),
        )
        if new_assertion is not None:
            ent["assertion"] = new_assertion


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


# ── Public API ──


def run_post_processing(
    encounter_text: str,
    entities: list[dict],
    *,
    rules: list[PostProcessorRule] | None = None,
    enable_disorder_gate: bool = False,
    coding_mode: str = "hitl",
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

    Returns:
        The (mutated) entity list after all layers have run.
    """
    working = [dict(e) for e in entities]

    # Layer 1: Post-Processor Rules
    if rules:
        working = apply_rules_to_entities(encounter_text, working, rules)

    # Layer 2: Lab-Value Guard
    for ent in working:
        ent_start = int(ent.get("start", 0) or 0)
        ent_end = int(ent.get("end", 0) or 0)
        sentence_window = _extract_sentence_window(encounter_text, ent_start, ent_end)
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
    working = [e for e in working if not e.get("__suppress__")]

    # Layer 3: Scope Guard
    _apply_scope_guard_to_dicts(encounter_text, working)

    # Layer 4: Observable Normalisation
    working = normalize_observable_entities(
        encounter_text,
        working,
        add_qualifier_value=True,
    )

    # Layer 5: Entity-Type Normalisation
    normalise_entity_types(working)

    # Layer 6: Value-Unit Linking
    link_observable_value_units(working)

    # Layer 7: ConText Assertion Detection
    apply_context_detection_to_dicts(encounter_text, working)

    # Layer 8: Situation Lookup Normalisation
    _apply_situation_lookup(working)

    # Layer 9: Disorder Gate (optional)
    if enable_disorder_gate:
        _apply_disorder_gate(encounter_text, working, coding_mode=coding_mode)
        working = [e for e in working if not e.get("__suppress__")]

    return working
