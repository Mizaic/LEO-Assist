"""JSON-specific LLM invocation wrapper.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design_output", dc_id="DO-AA3B7FCC")

Provides invoke_llm_json() which routes through ``create_llm`` using
``PIPELINE_MODEL_PROVIDER`` (default Azure OpenAI) and parses the response
as JSON with retry logic.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Dict, Optional

from libs.llm_client.factory import create_llm, default_llm_provider

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)


def _extract_json(text: str) -> Dict[str, Any]:
    """Extract JSON from an LLM response that may contain markdown fencing."""
    text = text.strip()
    if text.startswith("{"):
        return json.loads(text)
    m = _JSON_BLOCK_RE.search(text)
    if m:
        return json.loads(m.group(1).strip())
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise json.JSONDecodeError("No JSON object found in response", text, 0)


async def invoke_llm_json(
    system_prompt: str,
    user_message: str,
    *,
    max_tokens: int = 1024,
    temperature: float = 0.0,
    prefill_hint: Optional[str] = None,
    agent_task: str = "unknown",
    patient_id: str = "",
    max_retries: int = 3,
    tier: str = "big",
) -> Dict[str, Any]:
    """Invoke the LLM and parse the response as JSON.

    Uses ``PIPELINE_MODEL_PROVIDER`` (default ``azure``) via ``create_llm``.
    Telemetry is emitted by ``LLMClient.converse`` (DI-LEO-AI-515).

    Args:
        system_prompt: System prompt for the model.
        user_message: User message / task description.
        max_tokens: Maximum tokens in the response.
        temperature: Sampling temperature.
        prefill_hint: Optional assistant pre-fill (appended to parsed text only).
        agent_task: Task label for usage tracking.
        patient_id: Patient ID for usage tracking.
        max_retries: Number of retries on JSON parse failure.
        tier: Model tier (``small`` / ``big`` / ``max``).

    Returns:
        Parsed JSON dict, or a dict with an "error" key on failure.
    """
    provider = default_llm_provider()
    client = await asyncio.to_thread(create_llm, provider=provider, tier=tier)

    system = system_prompt
    user = user_message
    last_error = ""
    for attempt in range(max_retries):
        started = time.perf_counter()
        try:
            resp = await asyncio.to_thread(
                client.converse,
                system=system,
                messages=[{"role": "user", "content": user}],
                max_tokens=max_tokens,
                temperature=temperature,
                json_mode=True,
                agent_task=agent_task,
                patient_id=patient_id,
            )
            raw_text = (resp.text or "").strip()
            if prefill_hint:
                raw_text = prefill_hint + raw_text

            result = _extract_json(raw_text)
            return result
        except json.JSONDecodeError as exc:
            last_error = str(exc)
            logger.warning(
                "JSON parse failed (attempt %d/%d) for %s: %s",
                attempt + 1,
                max_retries,
                agent_task,
                last_error,
            )
            if attempt < max_retries - 1:
                system = (
                    f"{system_prompt}\n\n"
                    "Return ONLY valid JSON. No prose, no markdown."
                )
                user = f"{user_message}\n\nReturn a single JSON object only."
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.error(
                "LLM invocation failed for %s after %dms: %s",
                agent_task,
                latency_ms,
                exc,
            )
            return {"error": str(exc)}

    return {"error": f"JSON parse failed after {max_retries} attempts: {last_error}"}
