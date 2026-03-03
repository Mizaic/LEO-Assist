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

logger = logging.getLogger(__name__)

_TIERS = ("small", "big", "max")

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class CandidatesResult:
    """Outcome of asking LEO to pick from a real SNOMED candidate list."""

    action: str = "ambiguous"  # "pick" | "search" | "ambiguous"
    selected_index: int = 0
    alternative_query: str = ""
    reason: str = ""
    model_id: str = ""


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
                                "entity_text": entity_text,
                                "encounter_text": encounter_text,
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
    system_prompt = (
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
        "e.g. 'Serum urea level (observable entity)'.\n\n"
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
                                "entity_text": entity_text,
                                "entity_label": entity_label,
                                "encounter_text": encounter_text[:2000],
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


_CANDIDATES_SYSTEM = (
    "You are a UK primary care SNOMED CT coding specialist.\n\n"
    "You are given real SNOMED CT concepts retrieved from the terminology index. "
    "Choose one of three actions:\n"
    "  pick      - select the best concept from the list by its index\n"
    "  search    - none fit; suggest a better plain-English search query\n"
    "  ambiguous - the correct code cannot be determined from the evidence\n\n"
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
    "-- the system will search the terminology index with it.\n\n"
    "Respond ONLY with JSON, one of:\n"
    '  {"action":"pick","selected_index":<int>,"reason":"<one sentence>"}\n'
    '  {"action":"search","query":"<plain English>","reason":"<one sentence>"}\n'
    '  {"action":"ambiguous","reason":"<one sentence explaining ambiguity>"}'
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
        "entity_text": entity_text,
        "encounter_text": encounter_text[:1500],
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

    if action == "pick":
        idx = int(parsed.get("selected_index", 0))
        if not (0 <= idx < len(candidates)):
            idx = 0
        return CandidatesResult(
            action="pick",
            selected_index=idx,
            reason=reason,
            model_id=response.model_id,
        )
    if action == "search":
        query = str(parsed.get("query", "")).strip()
        return CandidatesResult(
            action="search",
            alternative_query=query,
            reason=reason,
            model_id=response.model_id,
        )
    return CandidatesResult(action="ambiguous", reason=reason, model_id=response.model_id)
