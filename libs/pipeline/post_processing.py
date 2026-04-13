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
7b. Referral Proc Guard   -- keep referral procedures as present
7c. Observable Trend Split -- split current vs historical result values
8. Situation Lookup Norm. -- normalise situation text for terminology
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
from libs.ner.lab_value_guard import should_suppress_disorder
from libs.ner.observable_post_processor import normalize_observable_entities
from libs.ner.post_processor_rules import PostProcessorRule, apply_rules_to_entities
from libs.ner.scope_guard import SUPPRESSED, reclassify_assertion

logger = logging.getLogger(__name__)

try:
    from libs.ner.context_engine import apply_context_detection_to_dicts
except Exception:
    logger.warning(
        "ConText engine unavailable; assertion context detection is disabled in this runtime",
        exc_info=True,
    )

    def apply_context_detection_to_dicts(
        _encounter_text: str, _entities: list[dict[str, Any]]
    ) -> None:
        return


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

_EPISODE_MARKER_TEXTS = frozenset(
    {
        "new episode",
        "ongoing episode",
        "first episode",
    }
)

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
        i
        for i, e in enumerate(entities)
        if str(e.get("label", "")) == "observable_entity"
    ]
    if not observable_indices:
        return

    measurement_indices = [
        i
        for i, e in enumerate(entities)
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
            str(ent.get("text", "")),
            encounter_text,
            coding_mode=coding_mode,
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


def run_post_processing_with_trace(
    encounter_text: str,
    entities: list[dict],
    *,
    rules: list[PostProcessorRule] | None = None,
    enable_disorder_gate: bool = False,
    coding_mode: str = "hitl",
) -> tuple[list[dict], list[dict[str, Any]]]:
    """Run post-processing and return (entities, per-layer trace)."""
    working = [dict(e) for e in entities]
    layer_trace: list[dict[str, Any]] = []

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

    # Layer 3: Scope Guard
    _run_layer(
        "layer_3",
        "Scope Guard",
        lambda current: (_apply_scope_guard_to_dicts(encounter_text, current), current)[
            1
        ],
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

    # Layer 5: Entity-Type Normalisation
    _run_layer(
        "layer_5",
        "Entity-Type Normalisation",
        lambda current: (normalise_entity_types(current), current)[1],
    )

    # Layer 6: Value-Unit Linking
    _run_layer(
        "layer_6",
        "Value-Unit Linking",
        lambda current: (link_observable_value_units(current), current)[1],
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

    # Layer 7d: Double-Negation Situation Guard
    # Fires only for entities that already carry a resolved SNOMED preferred
    # term (training path).  Runtime entities have no term yet at this point;
    # they are handled by terminology._resolve_terms after SNOMED resolution.
    _run_layer(
        "layer_7d",
        "Double-Negation Situation Guard",
        lambda current: (fix_double_negated_situations(current), current)[1],
    )

    # Layer 8: Situation Lookup Normalisation
    _run_layer(
        "layer_8",
        "Situation Lookup Normalisation",
        lambda current: (_apply_situation_lookup(current), current)[1],
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

    return working, layer_trace


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
    processed, _trace = run_post_processing_with_trace(
        encounter_text,
        entities,
        rules=rules,
        enable_disorder_gate=enable_disorder_gate,
        coding_mode=coding_mode,
    )
    return processed
