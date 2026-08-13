"""Batch LLM coding verifier: semantic gate for proposed SNOMED codes.

Atlas trace:
  UN: UN-BF51F752
  DI: DI-0EC8620E
  Risk: R-EB42EB45

After SNOMED terminology resolution, each proposed code is verified by an LLM
to detect lexical accidents (BM25 matched a wrong concept), non-codeable
descriptors, and domain mismatches.

Entities are verified in sub-batches so JSON responses stay within parse caps.

Verdicts
--------
  accept       -- code is clinically appropriate for the entity in context
  not_codeable -- entity is a descriptor with no standalone SNOMED code
  retry        -- code is wrong; better_term is supplied for re-resolution
  gate_failed  -- LLM call or parse failed; entity is flagged for human review

Fail-closed behaviour
---------------------
On consensus failure the entity verdict is ``gate_failed``.  The caller
(coding_verifier subgraph) treats gate_failed as tier=1 mandatory review;
the entity is NOT silently accepted or silently dropped.

Surface-form exact matches (had_exact_match=True) bypass this gate entirely
because they are curated by a human knowledge administrator.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

from libs.llm_client.consensus import (
    ConsensusOptions,
    _consensus_verifier_tier,
    run_consensus,
)
from libs.llm_client.prompt_safety import (
    INJECTION_GUARD,
    cap_llm_response,
    sanitise_for_prompt,
)

logger = logging.getLogger(__name__)

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)

# Keep each LLM call small enough that JSON + short reasons fit under the
# response-stuffing cap after prompt_safety truncation.
_SUB_BATCH_SIZE = 20
_CHARS_PER_ENTITY = 200
_BASE_RESPONSE_CHARS = 4_000
_MAX_RESPONSE_CHARS = 32_000
_TOKENS_PER_ENTITY = 120
_BASE_TOKENS = 600
_MAX_TOKENS = 8_000

_SYSTEM_PROMPT = INJECTION_GUARD + """
You are a UK clinical coding specialist.

OBJECTIVE
Decide whether each proposed SNOMED CT code is clinically correct for its
extracted entity in the supplied document context.

PRIORITY ORDER
1. Reject clinically wrong or cross-domain matches.
2. Do not accept descriptors that are not standalone codeable concepts.
3. Prefer retry over accept when the match is uncertain.
4. Preserve input order and follow the JSON contract exactly.

VERDICTS
  accept      -- the proposed SNOMED code is clinically appropriate
  not_codeable -- the entity is a clinical descriptor or modifier that has no standalone SNOMED code (e.g. marked internal vascularity is a descriptor, not independently codeable)
  retry       -- the code is wrong; set better_term to a short, clean SNOMED-friendly lookup term (1-3 words) so the resolver can try again

HARD REQUIREMENTS
1. If the proposed SNOMED term is from a completely different clinical domain (e.g. an ophthalmology code for an abdominal ultrasound entity), verdict=retry with a better lookup term.
2. If the entity describes a quality, degree, or context of another finding rather than a standalone clinical concept, verdict=not_codeable.
3. If the code is an acceptable SNOMED representation of the entity (even if not exact), verdict=accept.
4. When uncertain between accept and retry, prefer retry with a cleaner lookup term.
5. better_term is required when verdict=retry; set it to null otherwise.
6. Keep each reason to at most 12 words.

OUTPUT CONTRACT
Return only a JSON object with verdicts in the same order:
  {"verdicts": [{"index": <int>, "verdict": "<verdict>", "better_term": "<string or null>", "reason": "<short phrase>"}]}
Do not add prose or Markdown fences.
""".strip()

_VALID_VERDICTS = frozenset({"accept", "not_codeable", "retry", "gate_failed"})
_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "minimum": 0},
                    "verdict": {
                        "type": "string",
                        "enum": ["accept", "not_codeable", "retry"],
                    },
                    "better_term": {"type": ["string", "null"]},
                    "reason": {"type": "string"},
                },
                "required": ["index", "verdict", "better_term", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["verdicts"],
    "additionalProperties": False,
}


def _response_cap(entity_count: int) -> int:
    return min(
        _BASE_RESPONSE_CHARS + entity_count * _CHARS_PER_ENTITY,
        _MAX_RESPONSE_CHARS,
    )


def _token_budget(entity_count: int) -> int:
    return min(_BASE_TOKENS + entity_count * _TOKENS_PER_ENTITY, _MAX_TOKENS)


def _parse_verdicts(text: str, *, max_chars: int) -> list[dict[str, Any]] | None:
    """Parse the LLM response into a list of per-entity verdict dicts."""
    text = cap_llm_response(text, max_chars=max_chars)
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            parsed = parsed.get("verdicts")
        if isinstance(parsed, list):
            return _validate_verdicts(parsed)
    except json.JSONDecodeError:
        pass
    match = _JSON_ARRAY_RE.search(text)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        if isinstance(parsed, dict):
            parsed = parsed.get("verdicts")
        if isinstance(parsed, list):
            return _validate_verdicts(parsed)
    except json.JSONDecodeError:
        return None
    return None


def _validate_verdicts(items: list) -> list[dict[str, Any]] | None:
    result = []
    for item in items:
        if not isinstance(item, dict):
            return None
        verdict = str(item.get("verdict") or "").strip().lower()
        if verdict not in _VALID_VERDICTS - {"gate_failed"}:
            return None
        result.append(
            {
                "index": int(item.get("index", 0)),
                "verdict": verdict,
                "better_term": str(item.get("better_term") or "").strip() or None,
                "reason": str(item.get("reason") or "").strip(),
            }
        )
    return result if result else None


def _build_user_message(
    entities: list[dict[str, Any]],
    clinical_text: str,
) -> str:
    items = []
    for i, entity in enumerate(entities):
        items.append(
            {
                "index": i,
                "entity_text": sanitise_for_prompt(
                    str(entity.get("text") or ""), max_chars=150
                ),
                "proposed_snomed_term": sanitise_for_prompt(
                    str(entity.get("term") or ""), max_chars=150
                ),
                "concept_id": str(entity.get("concept_id") or ""),
                "semantic_tag": str(entity.get("semantic_tag") or ""),
            }
        )
    return json.dumps(
        {
            "clinical_text": sanitise_for_prompt(clinical_text, max_chars=2_000),
            "proposed_codes": items,
        }
    )


def _gate_failed_verdicts(count: int) -> list[dict[str, Any]]:
    return [
        {
            "index": i,
            "verdict": "gate_failed",
            "better_term": None,
            "reason": "parse error",
        }
        for i in range(count)
    ]


def _verify_sub_batch(
    entities: list[dict[str, Any]],
    clinical_text: str,
) -> list[dict[str, Any]]:
    max_chars = _response_cap(len(entities))
    parse_fn: Callable[[str], list[dict[str, Any]] | None] = (
        lambda text: _parse_verdicts(text, max_chars=max_chars)
    )
    result = run_consensus(
        system_prompt=_SYSTEM_PROMPT,
        user_msg=_build_user_message(entities, clinical_text),
        parse_fn=parse_fn,
        fail_verdict=None,
        options=ConsensusOptions(
            max_tokens=_token_budget(len(entities)),
            json_mode=True,
            tier=_consensus_verifier_tier(),
            structured_schema=_OUTPUT_SCHEMA,
        ),
    )
    verdicts = result.verdict if isinstance(result.verdict, list) else None
    if not verdicts or len(verdicts) != len(entities):
        logger.warning(
            "CodingVerifier batch returned %s verdicts for %d entities -- gate_failed",
            len(verdicts) if verdicts else "None",
            len(entities),
        )
        return _gate_failed_verdicts(len(entities))
    return verdicts


def verify_coding_batch(
    entities: list[dict[str, Any]],
    clinical_text: str,
) -> list[dict[str, Any]]:
    """Verify proposed SNOMED codes using one or more LLM sub-batches.

    Returns a list of verdict dicts in the same order as ``entities``.
    Each dict has keys: index, verdict, better_term (or None), reason.

    On gate failure for a sub-batch, those entities receive verdict=gate_failed.
    Surface-form exact matches MUST be filtered out by the caller before
    calling this function.
    """
    if not entities:
        return []

    combined: list[dict[str, Any]] = []
    for start in range(0, len(entities), _SUB_BATCH_SIZE):
        batch = entities[start : start + _SUB_BATCH_SIZE]
        batch_verdicts = _verify_sub_batch(batch, clinical_text)
        for offset, verdict in enumerate(batch_verdicts):
            remapped = dict(verdict)
            remapped["index"] = start + offset
            combined.append(remapped)

    logger.info(
        "CodingVerifier batch: %d entities -- accept=%d not_codeable=%d "
        "retry=%d gate_failed=%d",
        len(combined),
        sum(1 for v in combined if v["verdict"] == "accept"),
        sum(1 for v in combined if v["verdict"] == "not_codeable"),
        sum(1 for v in combined if v["verdict"] == "retry"),
        sum(1 for v in combined if v["verdict"] == "gate_failed"),
    )
    return combined
