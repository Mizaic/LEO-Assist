"""JSON-specific LLM invocation wrapper.

Atlas trace:
  DO: DO-FA8FCECF
  DI: DI-7B978C0C
  VT: VT-06157CF6

Provides invoke_llm_json() which routes through ``create_llm`` using
``PIPELINE_MODEL_PROVIDER`` (default Azure OpenAI) and parses the response
as JSON with bounded retry and optional JSON Schema validation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

from jsonschema import ValidationError, validate
from libs.llm_client.factory import create_llm, default_llm_provider

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)


@dataclass(frozen=True)
class JSONInvocationOptions:
    """Provider-neutral controls for one structured invocation."""

    max_tokens: int = 1024
    temperature: float = 0.0
    max_retries: int = 3
    tier: str = "big"
    schema: dict[str, Any] | None = None
    verbosity: str = "low"


def _extract_json(text: str) -> dict[str, Any]:
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


def _parse_and_validate(raw_text: str, schema: dict[str, Any] | None) -> dict[str, Any]:
    result = _extract_json(raw_text)
    if schema is not None:
        validate(instance=result, schema=schema)
    return result


def _retry_prompts(
    system_prompt: str, user_message: str, schema: dict[str, Any] | None
) -> tuple[str, str]:
    contract = "Return one JSON object that matches the supplied schema exactly."
    if schema is None:
        contract = "Return one valid JSON object."
    return (
        f"{system_prompt}\n\nOUTPUT CORRECTION: {contract} No prose or markdown.",
        f"{user_message}\n\n{contract}",
    )


async def _invoke_once(
    client: Any,
    *,
    system: str,
    user: str,
    options: JSONInvocationOptions,
    agent_task: str,
    patient_id: str,
) -> str:
    response = await asyncio.to_thread(
        client.converse,
        system=system,
        messages=[{"role": "user", "content": user}],
        max_tokens=options.max_tokens,
        temperature=options.temperature,
        json_mode=True,
        structured_schema=options.schema,
        verbosity=options.verbosity,
        agent_task=agent_task,
        patient_id=patient_id,
    )
    return (response.text or "").strip()


async def invoke_llm_json(
    system_prompt: str,
    user_message: str,
    *,
    options: JSONInvocationOptions | None = None,
    agent_task: str = "unknown",
    patient_id: str = "",
) -> dict[str, Any]:
    """Invoke the configured LLM and return a validated JSON object."""
    config = options or JSONInvocationOptions()
    provider = default_llm_provider()
    client = await asyncio.to_thread(create_llm, provider=provider, tier=config.tier)
    system = system_prompt
    user = user_message
    last_error = ""
    for attempt in range(config.max_retries):
        started = time.perf_counter()
        try:
            raw_text = await _invoke_once(
                client,
                system=system,
                user=user,
                options=config,
                agent_task=agent_task,
                patient_id=patient_id,
            )
            return _parse_and_validate(raw_text, config.schema)
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = str(exc)
            logger.warning(
                "JSON parse failed (attempt %d/%d) for %s: %s",
                attempt + 1,
                config.max_retries,
                agent_task,
                last_error,
            )
            if attempt < config.max_retries - 1:
                system, user = _retry_prompts(
                    system_prompt, user_message, config.schema
                )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.error(
                "LLM invocation failed for %s after %dms: %s",
                agent_task,
                latency_ms,
                exc,
            )
            return {"error": str(exc)}

    return {
        "error": (
            f"JSON validation failed after {config.max_retries} attempts: {last_error}"
        )
    }
