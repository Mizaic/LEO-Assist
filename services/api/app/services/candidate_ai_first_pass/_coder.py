"""Per-entity smart coder: validator + Haiku alt-query loop.

Atlas trace:
  DO: DO-D7005C41
  DI: DI-0FFA05BB
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-D7005C41")

DI-LEO-AI-208 / DO-LEO-AI-205.

Mirrors the behaviour of the Ask-LEO smart endpoint
(services/api/app/routers/_training_askleo.py::ask_leo_smart):

  1. Run the SNOMED resolver + validate_proposal.
  2. If accepted -> CodingOutcome(accepted=True, retries_used=0).
  3. If rejected -> ask Haiku to either pick from the candidates,
     declare not codeable, or rephrase the search query
     (escalate_coding_from_candidates).
  4. If Haiku asks to rephrase -> re-run the resolver with the new
     query and re-validate. Repeat up to ``max_retries`` times.
  5. On exhaustion -> CodingOutcome(accepted=False,
     retries_used=max_retries, rejection_reason='retry_cap_exhausted:<last>').
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Sequence

from libs.terminology.client import TerminologyClient
from libs.training.gold_label_snomed_check import (
    ValidationResult,
    validate_proposal,
)

from ._types import CodingOutcome, ExtractedEntity

logger = logging.getLogger(__name__)


_RESOLVER_TOP_N = 10
_DEFAULT_MAX_RETRIES = 2


def _validation_to_outcome(
    *,
    text: str,
    label: str,
    res: ValidationResult,
    alt_query: str | None,
    retries_used: int,
) -> CodingOutcome:
    return CodingOutcome(
        text=text,
        label=label,
        accepted=bool(res.accepted),
        snomed_concept_id=res.concept_id,
        snomed_term=res.snomed_term,
        score=float(res.resolver_score or 0.0),
        surface_match=float(res.surface_match or 0.0),
        rejection_reason=("" if res.accepted else (res.reason or "rejected")),
        alt_query_used=alt_query,
        retries_used=retries_used,
    )


def _terminology_search(
    terminology: TerminologyClient,
    query: str,
    *,
    semantic_tag: str,
    limit: int = _RESOLVER_TOP_N,
) -> list[dict[str, Any]]:
    """Wrap TerminologyClient.search with a per-call try/except."""
    try:
        return terminology.search(
            query=query,
            limit=limit,
            semantic_tags=[semantic_tag] if semantic_tag else [],
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "TerminologyClient.search failed for %r tag=%r",
            query,
            semantic_tag,
            exc_info=True,
        )
        return []


def _candidates_payload(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reshape resolver rows for escalate_coding_from_candidates."""
    out: list[dict[str, Any]] = []
    for r in rows:
        snomed = r.get("snomed_concept_id") or r.get("concept_id") or ""
        term = r.get("term") or r.get("snomed_term") or ""
        if not snomed or not term:
            continue
        out.append({"term": str(term), "snomed_concept_id": str(snomed)})
    return out


def _ask_haiku_for_alt_query(
    *,
    text: str,
    encounter_text: str,
    candidates: list[dict[str, Any]],
    tier: str,
) -> tuple[str, str]:
    """Invoke escalate_coding_from_candidates; return (action, alt_query).

    Imported lazily so tests can stub the whole function out.
    """
    from libs.llm_client.escalation import escalate_coding_from_candidates

    result = escalate_coding_from_candidates(
        entity_text=text,
        encounter_text=encounter_text or text,
        candidates=candidates,
        tier=tier,
    )
    return result.action, (result.alternative_query or "").strip()


def ai_code_entity(
    entity: ExtractedEntity,
    terminology: TerminologyClient,
    *,
    encounter_text: str = "",
    validator_kwargs: dict[str, float] | None = None,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    haiku_tier: str = "small",
    ask_haiku: Callable[..., tuple[str, str]] = _ask_haiku_for_alt_query,
) -> CodingOutcome:
    """Code one entity through the validator + Haiku alt-query loop."""
    text = (entity.text or "").strip()
    label = (entity.label or "").strip()
    if not text or not label:
        return CodingOutcome(
            text=text,
            label=label,
            accepted=False,
            rejection_reason="empty_input",
        )

    kwargs = dict(validator_kwargs or {})

    try:
        first = validate_proposal(text, label, terminology, **kwargs)
    except Exception:  # noqa: BLE001
        logger.exception("validator failed for text=%r label=%r", text, label)
        return CodingOutcome(
            text=text,
            label=label,
            accepted=False,
            rejection_reason="resolver_error",
        )

    if first.accepted:
        return _validation_to_outcome(
            text=text, label=label, res=first, alt_query=None, retries_used=0
        )

    last_reason = first.reason or "rejected"
    last_query: str | None = None
    used_queries: set[str] = {text.lower()}

    for attempt in range(1, max_retries + 1):
        # Get fresh resolver candidates from the LAST validated query so
        # Haiku can see what the resolver returned.
        rows = _terminology_search(
            terminology,
            (last_query or text),
            semantic_tag=label,
        )
        ranked = _candidates_payload(rows)
        if not ranked:
            return CodingOutcome(
                text=text,
                label=label,
                accepted=False,
                rejection_reason=f"no_resolver_candidates:{last_reason}",
                alt_query_used=last_query,
                retries_used=attempt - 1,
            )

        try:
            action, alt_query = ask_haiku(
                text=text,
                encounter_text=encounter_text,
                candidates=ranked,
                tier=haiku_tier,
            )
        except Exception:  # noqa: BLE001
            logger.exception("escalate_coding_from_candidates failed for %r", text)
            return CodingOutcome(
                text=text,
                label=label,
                accepted=False,
                rejection_reason=f"haiku_error:{last_reason}",
                alt_query_used=last_query,
                retries_used=attempt - 1,
            )

        if action == "not_codeable":
            return CodingOutcome(
                text=text,
                label=label,
                accepted=False,
                rejection_reason="haiku_not_codeable",
                alt_query_used=last_query,
                retries_used=attempt,
            )

        # The 'pick' branch alone does not satisfy the validator -- we
        # still need the validator to confirm the surface match. Re-run
        # validate_proposal with the picked term as the alt query.
        if action != "search" or not alt_query or alt_query.lower() in used_queries:
            return CodingOutcome(
                text=text,
                label=label,
                accepted=False,
                rejection_reason=f"haiku_no_new_query:{last_reason}",
                alt_query_used=last_query,
                retries_used=attempt,
            )

        used_queries.add(alt_query.lower())
        last_query = alt_query

        try:
            res = validate_proposal(alt_query, label, terminology, **kwargs)
        except Exception:  # noqa: BLE001
            logger.exception(
                "validator failed on alt-query text=%r label=%r", alt_query, label
            )
            return CodingOutcome(
                text=text,
                label=label,
                accepted=False,
                rejection_reason=f"resolver_error_on_alt:{alt_query}",
                alt_query_used=alt_query,
                retries_used=attempt,
            )

        if res.accepted:
            return _validation_to_outcome(
                text=text,
                label=label,
                res=res,
                alt_query=alt_query,
                retries_used=attempt,
            )
        last_reason = res.reason or "rejected"

    return CodingOutcome(
        text=text,
        label=label,
        accepted=False,
        rejection_reason=f"retry_cap_exhausted:{last_reason}",
        alt_query_used=last_query,
        retries_used=max_retries,
    )
