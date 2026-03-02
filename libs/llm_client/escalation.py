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
        "You are a UK primary care SNOMED CT coding specialist. "
        "Given a clinical entity extracted from a GP record, suggest the "
        "best matching SNOMED CT concept.\n\n"
        "Respond ONLY with a JSON object:\n"
        '{"concept_term": "...", "confidence": 0.0-1.0, "reason": "..."}\n\n'
        "If you cannot confidently identify the SNOMED concept, set "
        "confidence below 0.5 and explain why."
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
