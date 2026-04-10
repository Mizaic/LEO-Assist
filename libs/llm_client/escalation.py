"""Model escalation service: small -> big -> max.

When a small model cannot resolve a clinical disagreement with sufficient
confidence, this module escalates to progressively larger models.  Each
tier's rationale is preserved so the HITL operator (or an audit) can see
exactly which model resolved the issue and why.

Tier mapping (AWS Bedrock only -- Azure is not available):

  small  ->  Claude Haiku 4.5
  big    ->  Claude Sonnet 4.6
  max    ->  Claude Opus 4.6
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from libs.llm_client.factory import LLMResponse, create_llm
from libs.llm_client.prompt_safety import INJECTION_GUARD, cap_llm_response, sanitise_for_prompt

logger = logging.getLogger(__name__)

_TIERS = ("small", "big", "max")

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class CandidatesResult:
    """Outcome of asking LEO to pick from a real SNOMED candidate list."""

    action: str = "ambiguous"  # "pick" | "search" | "ambiguous" | "not_codeable"
    selected_index: int = 0
    alternative_query: str = ""
    reason: str = ""
    model_id: str = ""
    # Assertion override: "declined", "cancelled", or "refuted" when LEO detects
    # the patient declined/cancelled or an initial impression was overridden.
    # "present" in all other cases.
    assertion: str = "present"


@dataclass
class EscalationResult:
    """Outcome of an escalation attempt."""

    resolved: bool
    label: str | None = None
    concept_id: str | None = None
    concept_term: str | None = None
    confidence: float = 0.0
    model_tier: str = ""
    model_id: str = ""
    rationale: str = ""
    method: str = "escalation"
    all_attempts: list[dict[str, Any]] | None = None


def _parse_json(text: str) -> dict[str, Any]:
    text = cap_llm_response(text, max_chars=1000)
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass
    m = _JSON_OBJECT_RE.search(text)
    if not m:
        return {}
    try:
        parsed = json.loads(m.group(0))
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        val = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, val))


def escalate_label(
    *,
    entity_text: str,
    encounter_text: str,
    current_label: str,
    model_a_label: str,
    model_b_label: str,
    model_a_rationale: str = "",
    model_b_rationale: str = "",
    allowed_labels: list[str],
    system_prompt: str,
    confidence_threshold: float = 0.85,
    start_tier: str = "small",
) -> EscalationResult:
    """Escalate a label disagreement through model tiers until resolved.

    Returns as soon as any tier produces confidence >= threshold.
    If all tiers fail, returns the best attempt with resolved=False.
    """
    target_labels = {model_a_label, model_b_label}
    attempts: list[dict[str, Any]] = []
    best: EscalationResult | None = None

    start_idx = _TIERS.index(start_tier) if start_tier in _TIERS else 0

    for tier in _TIERS[start_idx:]:
        try:
            client = create_llm(provider="aws", tier=tier)
            response: LLMResponse = client.converse(
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "entity_text": sanitise_for_prompt(entity_text, max_chars=200),
                                "encounter_text": sanitise_for_prompt(encounter_text, max_chars=16_000),
                                "current_label": current_label,
                                "model_a_label": model_a_label,
                                "model_a_rationale": model_a_rationale,
                                "model_b_label": model_b_label,
                                "model_b_rationale": model_b_rationale,
                                "allowed_labels": allowed_labels,
                            }
                        ),
                    }
                ],
                temperature=0.0,
                max_tokens=400,
            )
            parsed = _parse_json(response.text)
        except Exception:
            logger.warning(
                "Escalation tier=%s failed for %r", tier, entity_text,
                exc_info=True,
            )
            attempts.append({"tier": tier, "error": True})
            continue

        resolved_label = str(parsed.get("resolved_label", "")).strip()
        confidence = _safe_float(parsed.get("confidence"))
        rationale = str(parsed.get("reason", ""))[:500]

        attempts.append({
            "tier": tier,
            "model_id": response.model_id,
            "resolved_label": resolved_label,
            "confidence": confidence,
            "rationale": rationale,
        })

        logger.info(
            "Escalation tier=%s entity=%r label=%r conf=%.2f threshold=%.2f",
            tier, entity_text, resolved_label, confidence, confidence_threshold,
        )

        result = EscalationResult(
            resolved=(
                resolved_label in target_labels
                and confidence >= confidence_threshold
            ),
            label=resolved_label if resolved_label in target_labels else None,
            confidence=confidence,
            model_tier=tier,
            model_id=response.model_id,
            rationale=rationale,
            all_attempts=attempts,
        )

        if result.resolved:
            return result

        if best is None or confidence > best.confidence:
            best = result

    if best is None:
        best = EscalationResult(
            resolved=False,
            all_attempts=attempts,
        )
    else:
        best.all_attempts = attempts
    return best


def escalate_coding(
    *,
    entity_text: str,
    entity_label: str,
    encounter_text: str,
    confidence_threshold: float = 0.85,
    start_tier: str = "small",
) -> EscalationResult:
    """Escalate a coding issue: ask increasingly capable models to suggest
    the correct SNOMED surface form / concept for an entity.

    Returns the model's best suggestion with concept_id, concept_term,
    and confidence.
    """
    system_prompt = INJECTION_GUARD + (
        "You are a UK primary care SNOMED CT coding specialist.\n\n"
        "Given a clinical entity extracted from a GP record, suggest the "
        "best matching SNOMED CT Fully Specified Name (FSN).\n\n"
        "CRITICAL RULES:\n"
        "1. DO NOT invent or guess SNOMED concept IDs. Never include a numeric "
        "SNOMED ID in your response. The concept_term field must be a plain "
        "text FSN only -- the system will look up the real ID separately.\n"
        "2. If the entity is genuinely ambiguous (e.g. 'weight loss' could be "
        "intentional, unintentional, unexplained, or weight decreased), set "
        "confidence below 0.6 and describe the ambiguity in reason. Do not "
        "guess a specific subtype without clear evidence from the encounter.\n"
        "3. Use the measurement unit in the encounter text to pick the most "
        "specific concept:\n"
        "   - g/L or g/dL in whole blood -> 'Mass concentration of X in blood'\n"
        "   - mmol/L -> 'Substance concentration of X in blood'\n"
        "   - /L or x10^9/L -> count-type observable\n"
        "   - % -> volume fraction or ratio observable\n"
        "4. Do NOT confuse whole-blood measurements with erythrocyte/cell "
        "indices (e.g. MCHC). 'Haemoglobin 129 g/L' is total Hb in blood, "
        "not haemoglobin within erythrocytes.\n"
        "5. UK primary care biochemistry results are serum-based by default. "
        "Use 'Serum X level' not 'Plasma X level' unless specimen type is "
        "explicitly stated as plasma.\n"
        "6. The concept_term MUST be consistent with your reason. Do not say "
        "'serum' in reason and output 'plasma' as concept_term.\n"
        "7. Prefer UK SNOMED CT edition concepts where they exist.\n"
        "8. Return the FSN including its semantic tag in parentheses, "
        "e.g. 'Serum urea level (observable entity)'.\n"
        "9. CRITICAL -- Do NOT infer diagnoses from lab values. A lab result "
        "(eGFR, HbA1c, creatinine, sodium, haemoglobin, etc.) is an observation, "
        "NOT a diagnosis. 'CKD-EPI' is a formula name, not CKD. If the entity "
        "text is a lab measurement, suggest an observable entity FSN, not a "
        "disorder. Set confidence below 0.3 and explain that a lab value alone "
        "does not constitute a diagnosis.\n"
        "10. Ambiguous abbreviation rules (UK primary care context):\n"
        "   a) Entity text is 'CA' alone (no organ/site stated in encounter): set "
        "confidence 0.0 and state in reason that organ site is required before "
        "coding. Do not suggest a generic cancer concept.\n"
        "   b) Entity text is 'MSK' alone as a specialty tag: set confidence 0.0 "
        "and state in reason that MSK is a body system category, not a codeable "
        "clinical entity. Suggest the specific symptom or diagnosis from the "
        "encounter context if one exists.\n"
        "   c) Entity text is 'NAD': set confidence 0.0 and do not suggest any "
        "concept. 'NAD' is ambiguous in UK primary care -- it can mean 'No "
        "abnormality detected' OR 'No apparent distress', and these cannot be "
        "distinguished from the abbreviation alone. Leave uncoded for manual review.\n\n"
        "Respond ONLY with a JSON object:\n"
        '{"concept_term": "<FSN>", "confidence": 0.0-1.0, "reason": "<brief>"}\n\n'
        "If you cannot confidently identify the concept, set confidence "
        "below 0.5 and explain why in reason."
    )

    attempts: list[dict[str, Any]] = []
    best: EscalationResult | None = None
    start_idx = _TIERS.index(start_tier) if start_tier in _TIERS else 0

    for tier in _TIERS[start_idx:]:
        try:
            client = create_llm(provider="aws", tier=tier)
            response: LLMResponse = client.converse(
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "entity_text": sanitise_for_prompt(entity_text, max_chars=200),
                                "entity_label": entity_label,
                                "encounter_text": sanitise_for_prompt(encounter_text, max_chars=16_000),
                            }
                        ),
                    }
                ],
                temperature=0.0,
                max_tokens=400,
            )
            parsed = _parse_json(response.text)
        except Exception:
            logger.warning(
                "Coding escalation tier=%s failed for %r",
                tier, entity_text, exc_info=True,
            )
            attempts.append({"tier": tier, "error": True})
            continue

        concept_term = str(parsed.get("concept_term", "")).strip()
        confidence = _safe_float(parsed.get("confidence"))
        rationale = str(parsed.get("reason", ""))[:500]

        attempts.append({
            "tier": tier,
            "model_id": response.model_id,
            "concept_term": concept_term,
            "confidence": confidence,
            "rationale": rationale,
        })

        logger.info(
            "Coding escalation tier=%s entity=%r concept=%r conf=%.2f",
            tier, entity_text, concept_term, confidence,
        )

        result = EscalationResult(
            resolved=bool(concept_term and confidence >= confidence_threshold),
            concept_term=concept_term or None,
            confidence=confidence,
            model_tier=tier,
            model_id=response.model_id,
            rationale=rationale,
            all_attempts=attempts,
        )

        if result.resolved:
            return result

        if best is None or confidence > best.confidence:
            best = result

    if best is None:
        best = EscalationResult(resolved=False, all_attempts=attempts)
    else:
        best.all_attempts = attempts
    return best


_CANDIDATES_SYSTEM = INJECTION_GUARD + (
    "You are a UK primary care SNOMED CT coding specialist.\n\n"
    "You are given real SNOMED CT concepts retrieved from the terminology index. "
    "Choose one of four actions:\n"
    "  pick          - select the best concept from the list by its index\n"
    "  search        - none fit; suggest a better plain-English search query\n"
    "  ambiguous     - the correct code cannot be determined from the evidence\n"
    "  not_codeable  - the encounter text shows this specific entity should NOT "
    "be coded at all (procedure not yet performed, ruled out, no evidence of, "
    "negated existence)\n\n"
    "RULES:\n"
    "1. Never invent or guess SNOMED concept IDs. Only reference the indexed "
    "concepts by number.\n"
    "2. Prefer UK SNOMED CT edition concepts where available.\n"
    "3. Use measurement units (g/L vs mmol/L) to disambiguate lab results.\n"
    "4. If candidates differ only by clinical qualifier (intentional / "
    "unintentional / unexplained) and the encounter does not indicate which, "
    "use action 'ambiguous' and explain why.\n"
    "5. UK convention: biochemistry is serum-based unless specimen type is "
    "explicitly stated otherwise.\n"
    "6. For action 'search', the query must be plain English with no SNOMED IDs "
    "-- the system will search the terminology index with it.\n"
    "7. When a patient DECLINED, REFUSED, or CANCELLED a procedure, referral, "
    "appointment, or investigation: code the UNDERLYING clinical procedure or "
    "referral using its normal SNOMED concept -- do NOT search for "
    "'patient declined X'. Add \"assertion\":\"declined\" (or \"cancelled\") to "
    "your JSON response. The system stores the code with a declined/cancelled "
    "assertion on the relationship so the clinical record shows it was offered "
    "but not accepted. Example: 'patient declined lymph node biopsy' -> pick or "
    "search for 'Biopsy of lymph node' with assertion 'declined'.\n"
    "7b. When a clinical impression was OVERRIDDEN by subsequent investigation "
    "(e.g. 'initially suggested Barrett's oesophagus, but biopsy confirmed "
    "cancer'), the overridden entity is 'refuted'. Add \"assertion\":\"refuted\" "
    "for the initial impression that was superseded. The CONFIRMED finding "
    "should remain 'present'. Example: 'thought to be eczema but biopsy "
    "confirmed psoriasis' -> eczema gets assertion 'refuted'.\n"
    "8. Use 'not_codeable' ONLY when the entity truly did not occur and there is "
    "no clinical event to record: condition explicitly ruled out, or finding "
    "explicitly negated (e.g. 'no evidence of X'). "
    "NEVER use 'not_codeable' for declined/refused/cancelled procedures — those "
    "are coded with assertion='declined' or 'cancelled' per Rule 7. "
    "NEVER use 'not_codeable' for pending/awaiting items -- those are coded with "
    "assertion='planned' (confirmed booking/referral) or 'hypothetical' (conditional "
    "future). State the reason clearly.\n"
    "9. CRITICAL -- Lab values vs diagnoses:\n"
    "   a) When the CANDIDATES are observable-entity concepts (e.g. 'Neutrophil "
    "count', 'Red blood cell count', 'Serum sodium level') and the entity text "
    "is a lab result with a numeric value, this IS codeable -- pick the best "
    "observable-entity concept. Lab results are valid clinical observations.\n"
    "   b) Do NOT infer a DISORDER from a lab value. If the candidates are "
    "disorder concepts (e.g. 'Chronic kidney disease stage 1', 'Anaemia') "
    "but the encounter text only shows a numeric result without an explicit "
    "diagnosis, use 'not_codeable' -- a lab value is an observation, not a "
    "diagnosis. 'CKD-EPI' is a formula name, NOT a diagnosis of CKD.\n"
    "   c) Similarly, do NOT infer diabetes from HbA1c, hyponatraemia from "
    "sodium, anaemia from haemoglobin, etc. Only code a disorder if the "
    "encounter text explicitly states a diagnosis.\n"
    "10. This system is a CODING tool. You code what is written. You do NOT make "
    "diagnoses, recommend treatment, or interpret clinical results.\n"
    "11. Ambiguous abbreviation rules (UK primary care context):\n"
    "   a) CA without an explicit organ/body site in the same sentence: use "
    "'not_codeable'. Reason must state that organ site is required before coding. "
    "When CA appears WITH a site (e.g. 'prostate CA', 'CA breast'), pick or search "
    "for the site-specific cancer concept.\n"
    "   b) MSK alone as a specialty or system tag (e.g. 'MSK clinic', 'referred to "
    "MSK', 'MSK pathway'): use 'not_codeable'. Reason must state it is a specialty "
    "tag, not a codeable clinical entity. When MSK appears with a specific symptom "
    "(e.g. 'MSK back pain'), pick the symptom concept, not MSK itself.\n"
    "   c) Entity text is 'NAD': use 'not_codeable'. 'NAD' is ambiguous in UK "
    "primary care -- it can mean 'No abnormality detected' (281900007) OR 'No "
    "apparent distress' (no SNOMED code). These cannot be distinguished from the "
    "abbreviation alone. Do not attempt to code NAD; leave for manual review.\n\n"
    "Respond ONLY with JSON. Include 'assertion' only when it differs from "
    "'present' (i.e. set it to 'declined', 'cancelled', or 'refuted' per rules 7/7b):\n"
    '  {"action":"pick","selected_index":<int>,"reason":"<one sentence>"}\n'
    '  {"action":"pick","selected_index":<int>,"reason":"<one sentence>","assertion":"declined"}\n'
    '  {"action":"pick","selected_index":<int>,"reason":"<one sentence>","assertion":"refuted"}\n'
    '  {"action":"search","query":"<plain English>","reason":"<one sentence>"}\n'
    '  {"action":"search","query":"<plain English>","reason":"<one sentence>","assertion":"declined"}\n'
    '  {"action":"ambiguous","reason":"<one sentence explaining ambiguity>"}\n'
    '  {"action":"not_codeable","reason":"<one sentence: why no clinical event to record>"}'
)


def _format_candidates(candidates: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"{i}. {c.get('term', '')} (SNOMED: {c.get('snomed_concept_id', '')})"
        for i, c in enumerate(candidates)
    )


def escalate_coding_from_candidates(
    *,
    entity_text: str,
    encounter_text: str,
    candidates: list[dict[str, Any]],
    tier: str = "small",
) -> CandidatesResult:
    """Ask an LLM to pick from real SNOMED candidates or request an alternative
    search query when none fit.  Never invents concept IDs.
    """
    if not candidates:
        return CandidatesResult(action="ambiguous", reason="No candidates provided.")

    numbered = _format_candidates(candidates)
    user_msg = json.dumps({
        "entity_text": sanitise_for_prompt(entity_text, max_chars=200),
        "encounter_text": sanitise_for_prompt(encounter_text, max_chars=16_000),
        "candidates": numbered,
    })

    resolved_tier = tier if tier in _TIERS else "small"
    try:
        client = create_llm(provider="aws", tier=resolved_tier)
        response = client.converse(
            system=_CANDIDATES_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
            temperature=0.0,
            max_tokens=200,
        )
    except Exception:
        logger.warning(
            "escalate_coding_from_candidates failed for %r", entity_text, exc_info=True,
        )
        return CandidatesResult(action="ambiguous", reason="LLM call failed.")

    parsed = _parse_json(response.text)
    action = str(parsed.get("action", "ambiguous")).strip()
    reason = str(parsed.get("reason", ""))[:400]

    raw_assertion = str(parsed.get("assertion", "present")).strip().lower()
    assertion = raw_assertion if raw_assertion in {"declined", "cancelled", "refuted"} else "present"

    if action == "pick":
        try:
            idx = int(parsed.get("selected_index", -1))
        except (TypeError, ValueError):
            idx = -1
        if not (0 <= idx < len(candidates)):
            logger.warning(
                "escalate_coding_from_candidates: selected_index=%r out of "
                "range [0, %d) for %r -- falling back to ambiguous",
                parsed.get("selected_index"),
                len(candidates),
                entity_text,
            )
            return CandidatesResult(
                action="ambiguous",
                reason=f"Invalid selected_index ({parsed.get('selected_index')}); {reason}",
                model_id=response.model_id,
            )
        return CandidatesResult(
            action="pick",
            selected_index=idx,
            reason=reason,
            model_id=response.model_id,
            assertion=assertion,
        )
    if action == "search":
        query = str(parsed.get("query", "")).strip()
        return CandidatesResult(
            action="search",
            alternative_query=query,
            reason=reason,
            model_id=response.model_id,
            assertion=assertion,
        )
    if action == "not_codeable":
        return CandidatesResult(
            action="not_codeable",
            reason=reason,
            model_id=response.model_id,
            assertion=assertion,
        )
    return CandidatesResult(action="ambiguous", reason=reason, model_id=response.model_id)


# -- Dual-model consensus verification for autonomous coding ----------------

_VERIFY_SYSTEM = INJECTION_GUARD + (
    "You are a UK primary care SNOMED CT coding specialist.\n\n"
    "A terminology index matched an entity from a GP encounter to a SNOMED "
    "concept. Your task: decide whether the match is CORRECT.\n\n"
    "Return exactly one verdict:\n"
    "  correct   -- the SNOMED concept accurately represents the entity in "
    "this clinical context\n"
    "  incorrect -- the concept does not match; explain briefly\n"
    "  uncertain -- insufficient context to decide\n\n"
    "Respond ONLY with JSON:\n"
    '{"verdict": "<correct|incorrect|uncertain>", "reason": "<one sentence>"}'
)


def _parse_verify_verdict(text: str) -> str:
    parsed = _parse_json(text)
    v = str(parsed.get("verdict", "")).strip().lower()
    return v if v in {"correct", "incorrect", "uncertain"} else ""


def verify_coding_consensus(
    *,
    entity_text: str,
    encounter_text: str,
    snomed_term: str,
    snomed_concept_id: str,
    coding_mode: str = "hitl",
) -> str:
    """Verify a terminology match using dual-model consensus.

    Returns 'correct', 'incorrect', or 'uncertain'.
    In autonomous mode, failure defaults to 'uncertain' (do not auto-code).
    In HITL mode, failure defaults to 'correct' (let human review).
    """
    from libs.llm_client.consensus import run_consensus

    fail_v = "uncertain" if coding_mode == "autonomous" else "correct"
    user_msg = json.dumps({
        "entity_text": sanitise_for_prompt(entity_text, max_chars=200),
        "encounter_text": sanitise_for_prompt(encounter_text, max_chars=1500),
        "matched_concept": f"{snomed_term} (SNOMED: {snomed_concept_id})",
    })

    result = run_consensus(
        system_prompt=_VERIFY_SYSTEM,
        user_msg=user_msg,
        parse_fn=_parse_verify_verdict,
        fail_verdict=fail_v,
        max_tokens=150,
    )
    logger.info(
        "verify_coding_consensus entity=%r verdict=%s agreed=%s",
        entity_text, result.verdict, result.agreed,
    )
    return result.verdict
