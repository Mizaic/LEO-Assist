"""JSON-specific LLM invocation wrapper.

Provides invoke_llm_json() which calls the existing Bedrock/Azure
LangChain models and parses the response as JSON with retry logic.

Equivalent to VRB's invoke_bedrock_json() but uses PCA's LangChain
provider infrastructure.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

from libs.llm_client.providers import get_bedrock_model, invoke_with_retry
from libs.llm_client.token_tracker import track_llm_usage

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
) -> Dict[str, Any]:
    """Invoke the LLM and parse the response as JSON.

    Args:
        system_prompt: System prompt for the model.
        user_message: User message / task description.
        max_tokens: Maximum tokens in the response.
        temperature: Sampling temperature.
        prefill_hint: Optional assistant pre-fill for Claude models
            (e.g. '{"status":"' to nudge JSON output).
        agent_task: Task label for usage tracking.
        patient_id: Patient ID for usage tracking.
        max_retries: Number of retries on JSON parse failure.

    Returns:
        Parsed JSON dict, or a dict with an "error" key on failure.
    """
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    model = await get_bedrock_model()

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_message)]
    if prefill_hint:
        messages.append(AIMessage(content=prefill_hint))

    last_error = ""
    for attempt in range(max_retries):
        try:
            response = await invoke_with_retry(
                model, messages, {"max_tokens": max_tokens, "temperature": temperature}
            )
            raw_text = response.content if hasattr(response, "content") else str(response)
            if prefill_hint:
                raw_text = prefill_hint + raw_text

            result = _extract_json(raw_text)
            import asyncio
            asyncio.ensure_future(track_llm_usage(agent_task=agent_task, patient_id=patient_id, model="bedrock"))
            return result
        except json.JSONDecodeError as exc:
            last_error = str(exc)
            logger.warning(
                "JSON parse failed (attempt %d/%d) for %s: %s",
                attempt + 1, max_retries, agent_task, last_error,
            )
            if attempt < max_retries - 1:
                messages_retry = [
                    SystemMessage(content=f"{system_prompt}\n\nReturn ONLY valid JSON. No prose, no markdown."),
                    HumanMessage(content=f"{user_message}\n\nReturn a single JSON object only."),
                ]
                if prefill_hint:
                    messages_retry.append(AIMessage(content=prefill_hint))
                messages = messages_retry
        except Exception as exc:
            logger.error("LLM invocation failed for %s: %s", agent_task, exc)
            return {"error": str(exc)}

    return {"error": f"JSON parse failed after {max_retries} attempts: {last_error}"}
