"""Shared helpers for episode-engine agents.

Atlas trace:
  DO: DO-2C1A2392
  DI: DI-7FF67ECE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C1A2392")

Wraps the common boilerplate of:
  - building Bedrock toolConfig from a JSON Schema
  - calling LLMClient.converse(...)
  - extracting the toolUse JSON
  - validating via a Pydantic model
  - capturing a StageTrace for provenance
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from libs.llm_client.factory import LLMClient
from libs.llm_usage import LLMCostConfig, LLMUsage
from services.analysis_worker.app.episode_engine.schemas import StageTrace

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class StageError(RuntimeError):
    """Raised when an agent stage cannot produce a valid response."""


def build_tool_config(tool_name: str, schema: dict[str, Any]) -> dict[str, Any]:
    """Wrap a JSON Schema in the Bedrock toolConfig structure that Claude
    needs to be FORCED to call the tool (and so emit valid JSON)."""

    return {
        "tools": [
            {
                "toolSpec": {
                    "name": tool_name,
                    "description": (
                        "Submit the structured episode-engine response. "
                        "Always call this tool exactly once."
                    ),
                    "inputSchema": {"json": schema},
                }
            }
        ],
        "toolChoice": {"tool": {"name": tool_name}},
    }


def _extract_tool_input(
    tool_uses: list[dict[str, Any]], tool_name: str
) -> dict[str, Any] | None:
    for tu in tool_uses:
        if not isinstance(tu, dict):
            continue
        if tu.get("name") != tool_name:
            continue
        payload = tu.get("input") or {}
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, str):
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                continue
    return None


# Claude occasionally leaks its internal tool-call XML envelope into a
# JSON key (instead of using the key as a key). Detect any key that
# contains the closing markers Claude bleeds in.
_ANTHROPIC_XML_LEAK_RX = re.compile(r"</?(parameter|invoke)>", re.IGNORECASE)


def _payload_has_xml_leak(payload: dict[str, Any]) -> bool:
    """Return True if any top-level key looks like an Anthropic XML leak."""

    if not isinstance(payload, dict):
        return False
    for key in payload:
        if isinstance(key, str) and _ANTHROPIC_XML_LEAK_RX.search(key):
            return True
    return False


def _repair_xml_leak(payload: dict[str, Any]) -> dict[str, Any]:
    """Best-effort repair of an XML-leaked toolUse payload.

    Strategy: drop any key matching the leak pattern. The legitimate fields
    that landed in their own keys (e.g. ``"windows"``) are kept intact.
    The retry path is responsible for producing a clean response next; this
    is just a salvage in case the rest of the payload is otherwise valid.
    """

    return {
        k: v
        for k, v in payload.items()
        if not (isinstance(k, str) and _ANTHROPIC_XML_LEAK_RX.search(k))
    }


def _repair_jsonish_strings(payload: dict[str, Any]) -> dict[str, Any]:
    """Repair Claude's habit of returning JSON-encoded arrays/objects as
    strings inside the toolUse payload.

    Failure mode (observed in real Haiku output):
        {"window_id": "w1", "milestones": "[{...}, {...}]"}
    The schema requires ``milestones`` to be an array, not a string. We
    try to ``json.loads`` any string value that looks like a JSON array
    or object and replace it in place. Non-stringy values are untouched.
    """

    if not isinstance(payload, dict):
        return payload
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith(("[", "{")):
                try:
                    out[key] = json.loads(stripped)
                    continue
                except (json.JSONDecodeError, ValueError):
                    pass
        out[key] = value
    return out


def call_stage(
    *,
    stage: str,
    llm: LLMClient,
    system: str,
    user: str,
    schema: dict[str, Any],
    tool_name: str,
    response_model: type[T],
    prompt_version: str,
    max_tokens: int = 4096,
) -> tuple[T, StageTrace]:
    """Run one stage end-to-end and return ``(parsed_response, trace)``.

    Raises ``StageError`` on irrecoverable failure (the chain decides
    whether to fail-fast or fail-soft per stage).
    """

    tier = getattr(llm, "tier", "") or ""
    started = time.perf_counter()
    trace = StageTrace(
        stage=stage,
        prompt_version=prompt_version,
        model_id=llm.model_id,
        tier=tier,
    )
    try:
        resp = llm.converse(
            system=system,
            messages=[{"role": "user", "content": user}],
            tool_config=build_tool_config(tool_name, schema),
            max_tokens=max_tokens,
        )
    except Exception as exc:
        trace.ok = False
        trace.error = f"{type(exc).__name__}: {exc}"
        trace.latency_ms = int((time.perf_counter() - started) * 1000)
        raise StageError(f"{stage}: LLM call failed: {exc}") from exc

    trace.input_tokens = int(resp.input_tokens or 0)
    trace.output_tokens = int(resp.output_tokens or 0)
    trace.cached_input_tokens = int(getattr(resp, "cached_input_tokens", 0) or 0)
    trace.latency_ms = int((time.perf_counter() - started) * 1000)
    trace.model_id = resp.model_id or llm.model_id

    # Cost is best-effort: if the env vars for this tier are not set,
    # cost_usd is 0 and we still record token counts.
    try:
        usage = LLMUsage(
            input_tokens=trace.input_tokens,
            output_tokens=trace.output_tokens,
            cached_input_tokens=trace.cached_input_tokens,
            llm_calls=1,
        )
        cfg = LLMCostConfig.for_tier(tier or "small")
        trace.cost_usd = round(usage.cost_usd(cfg), 6)
    except Exception:
        logger.debug(
            "Stage %s: cost calc failed; leaving cost_usd=0", stage, exc_info=True
        )
        trace.cost_usd = 0.0

    payload = _extract_tool_input(resp.tool_uses or [], tool_name)
    if payload is None:
        trace.ok = False
        trace.error = (
            f"no toolUse named {tool_name!r} in response "
            f"(stop_reason={resp.stop_reason!r}, text_len={len(resp.text)})"
        )
        raise StageError(trace.error)

    if _payload_has_xml_leak(payload):
        logger.warning(
            "Stage %s: detected Anthropic XML leak in toolUse keys; "
            "attempting repair + retry",
            stage,
        )
        payload = _repair_xml_leak(payload)
    payload = _repair_jsonish_strings(payload)

    try:
        parsed = response_model.model_validate(payload)
        return parsed, trace
    except ValidationError as exc:
        logger.warning(
            "Stage %s schema validation failed (attempt 1) for %s: %s\n"
            "Payload: %s",
            stage,
            response_model.__name__,
            exc,
            json.dumps(payload, default=str)[:1000],
        )

    # Single retry: re-prompt the model and explicitly call out the schema
    # error. Do NOT raise inside; if the retry also fails we surface a
    # StageError below.
    retry_started = time.perf_counter()
    _open_tag = "<" + "parameter" + ">"
    _close_tag = "<" + "/parameter" + ">"
    retry_user = (
        user
        + "\n\nIMPORTANT: your previous response failed schema validation. "
        "Respond by calling the tool ONCE with a valid JSON object that "
        "matches the schema exactly. Do NOT include any XML tags such as "
        + _open_tag
        + " or "
        + _close_tag
        + " in the JSON. Use only the property names defined in the "
        "schema. Array fields (for example 'milestones', 'disruptions', "
        "'episodes', 'windows') MUST be JSON arrays, not strings -- do "
        "NOT JSON-encode the array as a string."
    )
    try:
        retry_resp = llm.converse(
            system=system,
            messages=[{"role": "user", "content": retry_user}],
            tool_config=build_tool_config(tool_name, schema),
            max_tokens=max_tokens,
        )
    except Exception as exc:
        trace.ok = False
        trace.error = f"retry: LLM call failed: {exc}"
        trace.latency_ms += int((time.perf_counter() - retry_started) * 1000)
        raise StageError(f"{stage}: retry LLM call failed: {exc}") from exc

    trace.input_tokens += int(retry_resp.input_tokens or 0)
    trace.output_tokens += int(retry_resp.output_tokens or 0)
    trace.cached_input_tokens += int(
        getattr(retry_resp, "cached_input_tokens", 0) or 0
    )
    trace.latency_ms += int((time.perf_counter() - retry_started) * 1000)

    try:
        usage = LLMUsage(
            input_tokens=trace.input_tokens,
            output_tokens=trace.output_tokens,
            cached_input_tokens=trace.cached_input_tokens,
            llm_calls=2,
        )
        cfg = LLMCostConfig.for_tier(tier or "small")
        trace.cost_usd = round(usage.cost_usd(cfg), 6)
    except Exception:
        logger.debug(
            "Stage %s: retry cost calc failed; leaving prior cost_usd",
            stage,
            exc_info=True,
        )

    retry_payload = _extract_tool_input(retry_resp.tool_uses or [], tool_name)
    if retry_payload is None:
        trace.ok = False
        trace.error = "retry: no toolUse in response"
        raise StageError(trace.error)
    if _payload_has_xml_leak(retry_payload):
        retry_payload = _repair_xml_leak(retry_payload)
    retry_payload = _repair_jsonish_strings(retry_payload)

    try:
        parsed = response_model.model_validate(retry_payload)
    except ValidationError as exc:
        trace.ok = False
        trace.error = f"schema validation failed after retry: {exc.error_count()} errors"
        logger.warning(
            "Stage %s schema validation FAILED on retry for %s: %s\n"
            "Payload: %s",
            stage,
            response_model.__name__,
            exc,
            json.dumps(retry_payload, default=str)[:1000],
        )
        raise StageError(trace.error) from exc

    logger.info("Stage %s succeeded on retry after schema repair", stage)
    return parsed, trace
