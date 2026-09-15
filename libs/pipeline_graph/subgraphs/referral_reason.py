"""Referral reason extraction subgraph.

Atlas trace:
  UN: UN-AF530E8E
  DI: DI-41542A49
  DO: DO-4F133EE7
  VT: VT-95532C93

Searches referral document chunks for NHS eRS section header patterns,
then calls an LLM to extract a clean 1-2 sentence reason for referral.
The result is written to the ReferralRequest.reason property so the
SBAR Situation step can consume it.

Best-effort: sets referral_reason_skipped=True in state rather than
raising when inputs are missing or the LLM fails.

Runs in a thread via asyncio.to_thread(subgraph.invoke, state), so
async calls use asyncio.run() which is safe from a worker thread.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)

_REASON_PATTERNS = [
    "the reason i am concerned this patient has cancer is",
    "the reason for referral is",
    "reason for referral",
    "reason for request",
    "referral information",
    "referral criteria and clinical information",
    "further clinical details",
    "clinical information",
    "reasons for request",
    "i am referring this patient because",
    "reason i am referring",
]


class ReferralReasonState(TypedDict, total=False):
    referral_id: str
    chunk_ids: list[str]
    patient_id: str
    run_id: str
    dry_run: bool
    referral_reason: str
    referral_reason_skipped: bool
    errors: list[str]


def _extract_reason(state: ReferralReasonState) -> dict[str, Any]:
    referral_id = str(state.get("referral_id") or "").strip()
    chunk_ids = list(state.get("chunk_ids") or [])
    patient_id = str(state.get("patient_id") or "")
    run_id = str(state.get("run_id") or "")

    if not referral_id or not chunk_ids:
        logger.warning(
            "referral_reason: missing referral_id or chunk_ids run_id=%s, skipping",
            run_id,
        )
        return {"referral_reason_skipped": True}

    try:
        return asyncio.run(
            _async_extract_reason(
                referral_id,
                chunk_ids,
                patient_id,
                run_id,
                dry_run=bool(state.get("dry_run")),
            )
        )
    except Exception as exc:
        logger.warning("referral_reason extraction failed: %s", exc)
        return {
            "referral_reason_skipped": True,
            "errors": [f"referral_reason: {exc}"],
        }


def _load_reason_chunks(chunk_ids: list[str]) -> list[dict[str, Any]]:
    from libs.cypher.chunk_queries import GET_REASON_CHUNKS_BY_IDS
    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()
    try:
        return list(
            client.run(
                GET_REASON_CHUNKS_BY_IDS,
                chunk_ids=chunk_ids,
                patterns=_REASON_PATTERNS,
            )
            or []
        )
    finally:
        client.close()


def _ranked_reason_text(rows: list[dict[str, Any]], referral_id: str) -> str | None:
    from libs.pipeline_graph.referral_reason_chunks import select_reason_chunks

    if not rows:
        logger.info(
            "referral_reason: no header-matched chunks for referral %s", referral_id
        )
        return None
    ranked = select_reason_chunks(rows, limit=5)
    if not ranked:
        logger.info(
            "referral_reason: only scan-report chunks for referral %s", referral_id
        )
        return None
    return " ".join(str(row.get("text") or "") for row in ranked)


async def _llm_reason(candidate_text: str, patient_id: str) -> str:
    from libs.llm_client.json_helper import JSONInvocationOptions, invoke_llm_json
    from libs.llm_client.prompt_safety import INJECTION_GUARD, sanitise_for_prompt
    from libs.prompts.referral_reason_v1 import REFERRAL_REASON_SYSTEM_V1

    result = await invoke_llm_json(
        INJECTION_GUARD + REFERRAL_REASON_SYSTEM_V1,
        sanitise_for_prompt(candidate_text, max_chars=2000),
        options=JSONInvocationOptions(
            max_tokens=256,
            schema={
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "minLength": 1, "maxLength": 300}
                },
                "required": ["reason"],
                "additionalProperties": False,
            },
        ),
        agent_task="referral_reason_extraction",
        patient_id=patient_id,
    )
    if "error" in result:
        return ""
    return str(result.get("reason") or "").strip()


def _persist_reason(referral_id: str, reason: str) -> None:
    from libs.cypher.chunk_queries import SET_REFERRAL_REASON
    from libs.neo4j_client.client import PatientGraphClient

    write_client = PatientGraphClient()
    try:
        write_client.run(SET_REFERRAL_REASON, referral_id=referral_id, reason=reason)
    finally:
        write_client.close()


async def _async_extract_reason(
    referral_id: str,
    chunk_ids: list[str],
    patient_id: str,
    run_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    candidate_text = _ranked_reason_text(_load_reason_chunks(chunk_ids), referral_id)
    if not candidate_text:
        return {"referral_reason_skipped": True}

    reason = await _llm_reason(candidate_text, patient_id)
    if not reason:
        logger.warning(
            "referral_reason: LLM extraction failed or empty for referral %s",
            referral_id,
        )
        return {"referral_reason_skipped": True}

    if dry_run:
        logger.info("dry_run=True - skipping referral reason write")
        return {"referral_reason": reason}

    _persist_reason(referral_id, reason)
    logger.info("referral_reason: wrote reason to ReferralRequest %s", referral_id)
    return {"referral_reason": reason}


def build_referral_reason_subgraph() -> CompiledStateGraph:
    """Build and compile the referral reason extraction subgraph."""
    graph = StateGraph(ReferralReasonState)
    graph.add_node("extract_reason", _extract_reason)
    graph.add_edge(START, "extract_reason")
    graph.add_edge("extract_reason", END)
    return graph.compile()
