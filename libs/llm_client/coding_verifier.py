"""Batch LLM coding verifier: semantic gate for proposed SNOMED codes.

Atlas trace:
  UN: UN-BF51F752
  DI: DI-0EC8620E
  Risk: R-EB42EB45

After SNOMED terminology resolution, each proposed code is verified by an LLM
to detect lexical accidents (BM25 matched a wrong concept), non-codeable
descriptors, and domain mismatches.

All entities for one document are batched into a single LLM call to keep
latency and token cost low.

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
from typing import Any

from libs.llm_client.consensus import _consensus_verifier_tier, run_consensus
from libs.llm_client.prompt_safety import (
    INJECTION_GUARD,
    cap_llm_response,
    sanitise_for_prompt,
)

logger = logging.getLogger(__name__)

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)

_SYSTEM_PROMPT = INJECTION_GUARD + (
    "You are a UK clinical coding specialist.\n\n"
    "You are given a list of extracted clinical entities from a document, "
    "each paired with a proposed SNOMED CT code.\n\n"
    "For each entity, decide whether the proposed code is clinically correct "
    "in the context of this document.\n\n"
    "Return a JSON array with one object per entity in the same order:\n"
    '  {"index": <int>, "verdict": "<verdict>", '
    '"better_term": "<optional string>", "reason": "<one sentence>"}\n\n'
    "Verdicts:\n"
    "  accept      -- the proposed SNOMED code is clinically appropriate\n"
    "  not_codeable -- the entity is a clinical descriptor or modifier that "
    "has no standalone SNOMED code (e.g. 'marked internal vascularity' is a "
    "descriptor, not independently codeable)\n"
    "  retry       -- the code is wrong; set better_term to a short, clean "
    "SNOMED-friendly lookup term (1-3 words) so the resolver can try again\n\n"
    "Rules:\n"
    "1. If the proposed SNOMED term is from a completely different clinical "
    "domain (e.g. an ophthalmology code for an abdominal ultrasound entity), "
    "verdict=retry with a better lookup term.\n"
    "2. If the entity describes a quality, degree, or context of another "
    "finding rather than a standalone clinical concept, verdict=not_codeable.\n"
    "3. If the code is an acceptable SNOMED representation of the entity "
    "(even if not exact), verdict=accept.\n"
    "4. When uncertain between accept and retry, prefer retry with a cleaner "
    "lookup term.\n"
    "5. better_term is required when verdict=retry, omit otherwise.\n"
    "6. Only output the JSON array -- no prose before or after it."
)

_VALID_VERDICTS = frozenset({"accept", "not_codeable", "retry", "gate_failed"})


def _parse_verdicts(text: str) -> list[dict[str, Any]] | None:
    """Parse the LLM response into a list of per-entity verdict dicts."""
    text = cap_llm_response(text, max_chars=4_000)
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return _validate_verdicts(parsed)
    except json.JSONDecodeError:
        pass
    m = _JSON_ARRAY_RE.search(text)
    if not m:
        return None
    try:
        parsed = json.loads(m.group(0))
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
        result.append({
            "index": int(item.get("index", 0)),
            "verdict": verdict,
            "better_term": str(item.get("better_term") or "").strip() or None,
            "reason": str(item.get("reason") or "").strip(),
        })
    return result if result else None


def _build_user_message(
    entities: list[dict[str, Any]],
    clinical_text: str,
) -> str:
    items = []
    for i, e in enumerate(entities):
        items.append({
            "index": i,
            "entity_text": sanitise_for_prompt(str(e.get("text") or ""), max_chars=150),
            "proposed_snomed_term": sanitise_for_prompt(
                str(e.get("term") or ""), max_chars=150
            ),
            "concept_id": str(e.get("concept_id") or ""),
            "semantic_tag": str(e.get("semantic_tag") or ""),
        })
    return json.dumps({
        "clinical_text": sanitise_for_prompt(clinical_text, max_chars=2_000),
        "proposed_codes": items,
    })


def verify_coding_batch(
    entities: list[dict[str, Any]],
    clinical_text: str,
) -> list[dict[str, Any]]:
    """Verify a batch of proposed SNOMED codes using a single LLM call.

    Returns a list of verdict dicts in the same order as ``entities``.
    Each dict has keys: index, verdict, better_term (or None), reason.

    On gate failure, all entities receive verdict=gate_failed.
    Surface-form exact matches MUST be filtered out by the caller before
    calling this function.

    Parameters
    ----------
    entities:
        Resolved entities with at least text, term, concept_id, semantic_tag.
    clinical_text:
        The source document text (used as context for the LLM judge).
    """
    if not entities:
        return []

    user_msg = _build_user_message(entities, clinical_text)

    result = run_consensus(
        system_prompt=_SYSTEM_PROMPT,
        user_msg=user_msg,
        parse_fn=_parse_verdicts,
        fail_verdict=None,
        max_tokens=min(400 + len(entities) * 80, 2_000),
        tier=_consensus_verifier_tier(),
    )

    verdicts = result.verdict if isinstance(result.verdict, list) else None

    if not verdicts or len(verdicts) != len(entities):
        logger.warning(
            "CodingVerifier batch returned %s verdicts for %d entities -- gate_failed",
            len(verdicts) if verdicts else "None",
            len(entities),
        )
        return [
            {"index": i, "verdict": "gate_failed", "better_term": None, "reason": "parse error"}
            for i in range(len(entities))
        ]

    logger.info(
        "CodingVerifier batch: %d entities -- accept=%d not_codeable=%d retry=%d gate_failed=%d",
        len(verdicts),
        sum(1 for v in verdicts if v["verdict"] == "accept"),
        sum(1 for v in verdicts if v["verdict"] == "not_codeable"),
        sum(1 for v in verdicts if v["verdict"] == "retry"),
        sum(1 for v in verdicts if v["verdict"] == "gate_failed"),
    )
    return verdicts
