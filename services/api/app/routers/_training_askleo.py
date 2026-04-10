"""Ask LEO endpoints -- extracted from training.py for file size compliance.

Contains: ask_leo_coding, ask_leo_rank_candidates, ask_leo_smart
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel

from libs.auth.org_scope import CallerScope, get_caller_scope

logger = logging.getLogger(__name__)

_TERMINOLOGY_URL = os.getenv(
    "TERMINOLOGY_API_URL", "http://localhost:8001"
).rstrip("/")


class AskLeoRequest(BaseModel):
    entity_text: str
    entity_label: str = ""
    tier: str = "small"
    encounter_text: str = ""


class AskLeoRankRequest(BaseModel):
    entity_text: str
    encounter_text: str = ""
    candidates: list[dict[str, Any]]
    tier: str = "small"


class AskLeoSmartRequest(BaseModel):
    entity_text: str
    encounter_text: str = ""
    initial_candidates: list[dict[str, Any]]
    semantic_tags: list[str] = []
    tier: str = "small"
    assertion: str = "present"


_ASSERTION_NOTES: dict[str, str] = {
    "absent": "The entity was explicitly negated in this record. Coding is likely inappropriate.",
    "declined": (
        "The patient declined or refused this. Code the underlying procedure or referral "
        "using its normal SNOMED concept -- do NOT search for 'patient declined [entity]'. "
        "The system will store the code with assertion='declined' on the relationship so "
        "the timeline shows it was offered but not accepted."
    ),
    "cancelled": (
        "The appointment or procedure was cancelled (by patient or practice). Code the "
        "underlying procedure using its normal SNOMED concept. The system will store the "
        "code with assertion='cancelled' on the relationship."
    ),
    "refuted": (
        "Initial impression overridden by subsequent investigation. "
        "Code the entity that WAS confirmed using its normal SNOMED concept. "
        "The refuted entity should NOT be coded."
    ),
    "historical": "This may be a past event, not a current active condition.",
    "planned": "This procedure was booked or referred -- it is confirmed but has not happened yet.",
    "hypothetical": "This is a conditional or speculative future event -- it has not been arranged.",
    "possible": "This was uncertain or suspected in the original record.",
    "family": "This applies to a family member, not the patient directly.",
}


def _terminology_search(
    query: str,
    limit: int,
    semantic_tags: list[str],
) -> list[dict[str, Any]]:
    """Call the Terminology API search endpoint and return candidates."""
    import httpx

    params: dict[str, Any] = {"q": query, "limit": limit}
    if semantic_tags:
        params["semantic_tag"] = semantic_tags
    try:
        with httpx.Client(timeout=10) as http:
            resp = http.get(
                f"{_TERMINOLOGY_URL}/terminology/search",
                params=params,
            )
            resp.raise_for_status()
            return resp.json() or []
    except Exception:
        logger.warning("_terminology_search failed for %r", query, exc_info=True)
        return []


def _pick_candidate(
    candidates: list[dict[str, Any]],
    index: int,
) -> dict[str, Any] | None:
    if not candidates or not (0 <= index < len(candidates)):
        return None
    return candidates[index]


def register_askleo_routes(router) -> None:
    """Register Ask LEO route handlers on the given router."""

    @router.post("/coding-review/ask-leo")
    def ask_leo_coding(
        body: AskLeoRequest,
        scope: CallerScope = Depends(get_caller_scope),
    ) -> dict[str, Any]:
        """Ask LEO to suggest the best SNOMED concept for a clinical entity."""
        from libs.llm_client.escalation import escalate_coding
        from libs.llm_client.prompt_safety import sanitise_for_prompt

        result = escalate_coding(
            entity_text=sanitise_for_prompt(body.entity_text, max_chars=200),
            entity_label=body.entity_label or "clinical finding",
            encounter_text=sanitise_for_prompt(body.encounter_text, max_chars=16_000),
            start_tier=body.tier if body.tier in ("small", "big", "max") else "small",
            confidence_threshold=0.70,
        )
        return {
            "concept_term": result.concept_term,
            "confidence": round(result.confidence, 2),
            "rationale": result.rationale,
            "model_tier": result.model_tier,
            "resolved": result.resolved,
        }

    @router.post("/coding-review/ask-leo-rank")
    def ask_leo_rank_candidates(
        body: AskLeoRankRequest,
        scope: CallerScope = Depends(get_caller_scope),
    ) -> dict[str, Any]:
        """Given real SNOMED candidates, ask LEO to pick the best one."""
        if not body.candidates:
            return {"selected_index": 0, "reason": ""}

        from libs.llm_client.escalation import _parse_json
        from libs.llm_client.factory import create_llm
        from libs.llm_client.prompt_safety import INJECTION_GUARD, sanitise_for_prompt
        from libs.ner.lab_value_guard import (
            is_lab_result_sentence,
            should_suppress_disorder,
        )

        if is_lab_result_sentence(body.encounter_text or ""):
            if should_suppress_disorder(
                entity_text=body.entity_text,
                entity_semantic_tag="disorder",
                entity_normalized=body.entity_text,
                sentence_text=body.encounter_text or "",
            ):
                return {
                    "selected_index": 0,
                    "reason": (
                        "Lab-value guard: a lab result does not constitute a diagnosis. "
                        "'CKD-EPI' is a formula name, not a diagnosis of CKD."
                    ),
                }

        numbered = "\n".join(
            f"{i}. {c.get('term', '')} (SNOMED: {c.get('snomed_concept_id', '')})"
            for i, c in enumerate(body.candidates)
        )
        system = INJECTION_GUARD + (
            "You are a UK primary care SNOMED CT coding specialist.\n"
            "Pick the best concept from the numbered list for the clinical entity "
            "and encounter context.\n\n"
            "CRITICAL RULES:\n"
            "1. Only pick from the numbered list provided. Do not invent or "
            "reference any SNOMED concept IDs -- the list already contains the "
            "verified real codes.\n"
            "2. Clinical subtype matters. For example:\n"
            "   - 'weight loss' without a qualifier should map to the generic term, "
            "not a specific subtype (intentional/unintentional/unexplained) unless "
            "the encounter text clearly indicates which.\n"
            "   - 'no weight loss' or 'weight loss absent' suggests negation; pick "
            "the plain concept (the negation flag is handled separately).\n"
            "3. Use measurement units to disambiguate lab results: g/L -> mass "
            "concentration; mmol/L -> substance concentration.\n"
            "4. UK convention: blood tests are serum-based unless stated otherwise.\n"
            "5. If no candidate clearly fits, pick the closest and set a lower "
            "confidence in your reason.\n"
            "6. Do NOT infer diagnoses from lab values. A lab result (eGFR, HbA1c, "
            "creatinine, sodium, etc.) is an observation, NOT a diagnosis. 'CKD-EPI' "
            "is a formula name, not CKD. If the encounter text is a lab result, pick "
            "the observable entity concept, not a disorder concept.\n"
            "7. This system is a CODING tool. You code what is written, not what is "
            "inferred or recommended.\n\n"
            "Reply ONLY with JSON: "
            '{"selected_index": <int>, "reason": "<one sentence>"}'
        )
        user_msg = json.dumps({
            "entity_text": sanitise_for_prompt(body.entity_text, max_chars=200),
            "encounter_text": sanitise_for_prompt(
                body.encounter_text, max_chars=16_000
            ),
            "candidates": numbered,
        })
        tier = body.tier if body.tier in ("small", "big", "max") else "small"
        try:
            client = create_llm(provider="aws", tier=tier)
            response = client.converse(
                system=system,
                messages=[{"role": "user", "content": user_msg}],
                temperature=0.0,
                max_tokens=150,
            )
            parsed = _parse_json(response.text)
            idx = int(parsed.get("selected_index", 0))
            reason = str(parsed.get("reason", ""))[:300]
            if not (0 <= idx < len(body.candidates)):
                idx = 0
            return {"selected_index": idx, "reason": reason}
        except Exception:
            logger.warning(
                "ask-leo-rank failed for %r", body.entity_text, exc_info=True
            )
            return {"selected_index": 0, "reason": ""}

    @router.post("/coding-review/ask-leo-smart")
    def ask_leo_smart(
        body: AskLeoSmartRequest,
        scope: CallerScope = Depends(get_caller_scope),
    ) -> dict[str, Any]:
        """Agentic two-pass SNOMED coding.

        Pass 1: LEO sees the real candidate list and either picks one, requests
        an alternative search query, or declares ambiguous.
        Pass 2 (only if "search"): backend fetches a new candidate list using
        LEO's query, then LEO picks or declares ambiguous.
        """
        from libs.llm_client.escalation import escalate_coding_from_candidates
        from libs.llm_client.prompt_safety import sanitise_for_prompt
        from libs.ner.lab_value_guard import (
            is_lab_result_sentence,
            should_suppress_disorder,
        )

        safe_entity = sanitise_for_prompt(body.entity_text, max_chars=200)
        safe_encounter = sanitise_for_prompt(body.encounter_text, max_chars=16_000)

        if is_lab_result_sentence(safe_encounter or ""):
            if should_suppress_disorder(
                entity_text=safe_entity,
                entity_semantic_tag="disorder",
                entity_normalized=safe_entity,
                sentence_text=safe_encounter or "",
            ):
                return {
                    "matched_candidate": None,
                    "reason": (
                        "This encounter text is a lab result line. A lab value "
                        "(e.g. eGFR, HbA1c, creatinine) is an observation, not a "
                        "diagnosis. 'CKD-EPI' is a formula name, not a diagnosis "
                        "of chronic kidney disease. This entity should not be coded "
                        "as a disorder."
                    ),
                    "is_ambiguous": False,
                    "alternative_query_used": None,
                    "assertion_warning": (
                        "Lab-value guard: a lab result does not constitute a "
                        "diagnosis. This entity should not be coded as a disorder."
                    ),
                    "assertion": "present",
                }

        tier = body.tier if body.tier in ("small", "big", "max") else "small"
        assertion_note = _ASSERTION_NOTES.get(body.assertion, "")
        encounter_ctx = (
            f"{safe_encounter}\n\nContext note: {assertion_note}"
            if assertion_note and safe_encounter
            else safe_encounter
        )

        def _smart_response(
            candidate: dict[str, Any] | None,
            reason: str,
            is_ambiguous: bool,
            alternative_query: str | None = None,
            assertion_warning: str | None = None,
            assertion: str = "present",
        ) -> dict[str, Any]:
            return {
                "matched_candidate": candidate,
                "reason": reason,
                "is_ambiguous": is_ambiguous,
                "alternative_query_used": alternative_query,
                "assertion_warning": assertion_warning,
                "assertion": assertion,
            }

        result1 = escalate_coding_from_candidates(
            entity_text=safe_entity,
            encounter_text=encounter_ctx,
            candidates=body.initial_candidates,
            tier=tier,
        )

        if result1.action == "not_codeable":
            return _smart_response(
                None,
                result1.reason,
                is_ambiguous=False,
                assertion_warning=result1.reason,
            )

        if result1.action == "pick":
            candidate = _pick_candidate(
                body.initial_candidates, result1.selected_index
            )
            return _smart_response(
                candidate,
                result1.reason,
                is_ambiguous=False,
                assertion=result1.assertion,
            )

        if result1.action == "ambiguous":
            return _smart_response(None, result1.reason, is_ambiguous=True)

        # -- Pass 2: LEO requested an alternative search ----------------------
        alt_query = result1.alternative_query
        pass2_ctx = encounter_ctx
        if result1.assertion in {"declined", "cancelled", "refuted"}:
            note = _ASSERTION_NOTES.get(result1.assertion, "")
            if note:
                pass2_ctx = f"{encounter_ctx}\n\nContext note: {note}"

        new_candidates = _terminology_search(
            alt_query, 10, body.semantic_tags
        )
        if not new_candidates:
            return _smart_response(
                None,
                result1.reason,
                is_ambiguous=True,
                alternative_query=alt_query,
                assertion=result1.assertion,
            )

        result2 = escalate_coding_from_candidates(
            entity_text=safe_entity,
            encounter_text=pass2_ctx,
            candidates=new_candidates,
            tier=tier,
        )

        if result2.action == "not_codeable":
            return _smart_response(
                None,
                result2.reason,
                is_ambiguous=False,
                alternative_query=alt_query,
                assertion_warning=result2.reason,
            )

        if result2.action == "pick":
            candidate = _pick_candidate(
                new_candidates, result2.selected_index
            )
            assertion = (
                result2.assertion
                if result2.assertion != "present"
                else result1.assertion
            )
            return _smart_response(
                candidate,
                result2.reason,
                is_ambiguous=False,
                alternative_query=alt_query,
                assertion=assertion,
            )

        assertion = (
            result2.assertion
            if result2.assertion != "present"
            else result1.assertion
        )
        return _smart_response(
            None,
            result2.reason,
            is_ambiguous=True,
            alternative_query=alt_query,
            assertion=assertion,
        )
