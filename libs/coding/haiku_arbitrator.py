"""Haiku SNOMED arbitrator for lab entity validation.

Atlas trace:
  DI: DI-LEO-AI-LABCODER-001

Called ONLY when ``libs.training.gold_label_snomed_check.validate_proposals_batch``
returns ``accepted=False`` for one or more entities in a lab triple.  Haiku
receives the raw lab line, parsed measurement fields, the failing entity, and
the top-10 SNOMED candidates from the resolver.

For each failing entity it returns one of:
    accept      -- use the top candidate as-is
    fix_snomed  -- swap concept_id for a better candidate from the list
    fix_span    -- span text violates annotation rules; returns corrected text
    drop        -- entity is uncorrectable; exclude from GoldLabel

The system prompt is embedded verbatim in source code and is never supplied
by untrusted callers (LLM security rule: user-controllable prompts are
rejected; see .cursor/rules/llm-security.mdc).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt -- verbatim, never modified at runtime
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a clinical coding assistant for UK primary-care lab results.
Your task: validate a proposed SNOMED annotation for a single entity in a \
blood test result line and decide whether to accept, fix, or drop it.

ANNOTATION RULES (apply strictly):

1. PROCEDURE -- the test name span ONLY.
   - Excludes the bracketed Read/CTV3 code, any numeric value, unit, or range.
   - Required SNOMED semantic_tag: "procedure".
   - Example: "Haemoglobin" from "Haemoglobin (Xa96v) 135 g/L [130-170]"

2. OBSERVABLE_ENTITY -- test name + value + unit.
   - Excludes the bracketed reference range and any interpretation suffix.
   - Required SNOMED semantic_tag: "observable entity".
   - Example: "Haemoglobin 135 g/L" from "Haemoglobin (Xa96v) 135 g/L [130-170]"

3. FINDING -- present ONLY when an interpretation phrase follows (after " - ").
   - Span = test name + value + unit + reference range + interpretation.
   - Required SNOMED semantic_tag: "finding".
   - Interpretation -> SNOMED direction mapping (apply in order):
       "high" | "elevated" | "raised" | "above reference range"
           -> above-reference-range finding concept
       "low" | "reduced" | "below reference range"
           -> below-reference-range finding concept
       "normal" | "within reference range" | "in range"
           -> within-reference-range / normal finding concept
       "outside reference range" (direction not stated in text)
           -> compute from numeric value vs reference range:
              if value > upper_bound -> above-reference-range
              if value < lower_bound -> below-reference-range
       "borderline"
           -> borderline finding concept

DECISION OPTIONS for the entity:
  "accept"     -- the proposed span text and SNOMED concept are correct.
  "fix_snomed" -- span text is correct; select a better concept_id from
                  the candidates list.  Set "concept_id" to the chosen id
                  and "snomed_term" to the chosen fsn.
  "fix_span"   -- span boundaries violate the rules above; provide corrected
                  "text" (must be a substring of the lab line).
  "drop"       -- entity is uncorrectable (wrong label, no suitable concept).
                  Dropped entities are excluded from the gold label entirely.

Return ONLY valid JSON -- no prose, no markdown fences:
{
  "decision": "accept|fix_snomed|fix_span|drop",
  "concept_id": "...",
  "snomed_term": "...",
  "text": "...",
  "reason": "one sentence"
}
Fields not applicable to the decision may be omitted.\
"""

# ---------------------------------------------------------------------------
# Structured result
# ---------------------------------------------------------------------------

_VALID_DECISIONS = frozenset({"accept", "fix_snomed", "fix_span", "drop"})


@dataclass(frozen=True)
class ArbitrationResult:
    """Outcome of one Haiku arbitration call."""

    decision: str
    concept_id: str = ""
    snomed_term: str = ""
    text: str = ""
    reason: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_drop(self) -> bool:
        return self.decision == "drop"

    @property
    def is_accepted(self) -> bool:
        return self.decision in ("accept", "fix_snomed", "fix_span")


# ---------------------------------------------------------------------------
# Candidate formatter
# ---------------------------------------------------------------------------

def _format_candidates(candidates: list[dict[str, Any]], *, top_n: int = 10) -> str:
    """Render top-N SNOMED candidates as a numbered list for the prompt."""
    lines: list[str] = []
    for i, c in enumerate(candidates[:top_n], start=1):
        concept_id = c.get("concept_id") or ""
        fsn = c.get("snomed_term") or c.get("term") or ""
        tag = c.get("semantic_tag") or ""
        score = c.get("score") or c.get("resolver_score") or 0.0
        lines.append(
            f"  {i}. concept_id={concept_id}  tag={tag}  score={score:.3f}\n"
            f"     fsn: {fsn}"
        )
    return "\n".join(lines) if lines else "  (no candidates)"


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_response(text: str) -> dict[str, Any]:
    """Extract the first JSON object from the response text."""
    text = text.strip()
    m = _JSON_BLOCK_RE.search(text)
    if not m:
        raise ValueError(f"no JSON object found in response: {text[:200]!r}")
    return json.loads(m.group(0))


# ---------------------------------------------------------------------------
# HaikuArbitrator
# ---------------------------------------------------------------------------

class HaikuArbitrator:
    """Validates a single lab entity via Haiku when SNOMED validation fails.

    One instance per script run; the underlying LLMClient is process-cached
    via ``create_llm``'s ``lru_cache`` so repeated calls reuse the same
    Bedrock/Azure connection pool.
    """

    def __init__(self) -> None:
        from libs.llm_client.factory import create_llm
        self._llm = create_llm(tier="small")

    def arbitrate(
        self,
        *,
        lab_line: str,
        numeric_value: str,
        unit: str,
        reference_range: str,
        interpretation: str,
        entity_label: str,
        entity_text: str,
        candidates: list[dict[str, Any]],
    ) -> ArbitrationResult:
        """Call Haiku to validate/fix one failing lab entity.

        Args:
            lab_line:         Full raw lab line (e.g. "Haemoglobin (Xa96v) 135 g/L [130-170] - Normal").
            numeric_value:    Parsed numeric value string (e.g. "135").
            unit:             Parsed unit string (e.g. "g/L").
            reference_range:  Parsed reference range string (e.g. "[130-170]").
            interpretation:   Interpretation phrase if present (e.g. "Normal", "Outside reference range").
            entity_label:     One of "procedure", "observable_entity", "finding".
            entity_text:      The proposed span text.
            candidates:       Top-N ResolvedTerm-like dicts from the terminology resolver.

        Returns:
            ArbitrationResult with decision, optionally corrected concept_id/text.
        """
        user_msg = self._build_user_message(
            lab_line=lab_line,
            numeric_value=numeric_value,
            unit=unit,
            reference_range=reference_range,
            interpretation=interpretation,
            entity_label=entity_label,
            entity_text=entity_text,
            candidates=candidates,
        )

        try:
            response = self._llm.converse(
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
                max_tokens=256,
                temperature=0.0,
                agent_task="lab_snomed_arbitration",
            )
            raw = _parse_response(response.text)
        except Exception:
            logger.warning(
                "HaikuArbitrator: failed for entity %r in line %r",
                entity_text,
                lab_line[:80],
                exc_info=True,
            )
            return ArbitrationResult(decision="drop", reason="arbitrator_error")

        decision = str(raw.get("decision") or "drop").strip().lower()
        if decision not in _VALID_DECISIONS:
            logger.warning(
                "HaikuArbitrator: invalid decision %r for entity %r -- dropping",
                decision,
                entity_text,
            )
            return ArbitrationResult(decision="drop", reason="invalid_decision", raw=raw)

        return ArbitrationResult(
            decision=decision,
            concept_id=str(raw.get("concept_id") or ""),
            snomed_term=str(raw.get("snomed_term") or ""),
            text=str(raw.get("text") or entity_text),
            reason=str(raw.get("reason") or ""),
            raw=raw,
        )

    @staticmethod
    def _build_user_message(
        *,
        lab_line: str,
        numeric_value: str,
        unit: str,
        reference_range: str,
        interpretation: str,
        entity_label: str,
        entity_text: str,
        candidates: list[dict[str, Any]],
    ) -> str:
        parts = [
            f'Lab line: "{lab_line}"',
            f"Parsed: value={numeric_value or '?'}, unit={unit or '?'}, "
            f"reference_range={reference_range or 'none'}, "
            f"interpretation={interpretation!r}",
            "",
            f"Entity to validate:",
            f"  label:        {entity_label}",
            f"  proposed_text: {entity_text!r}",
            "",
            f"Top SNOMED candidates:",
            _format_candidates(candidates),
        ]
        return "\n".join(parts)
