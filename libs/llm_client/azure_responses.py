"""Azure OpenAI v1 Responses transport.

Atlas trace:
  DI: DI-7B978C0C
  DO: DO-FA8FCECF
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

_RESPONSES = "responses"
_CHAT_COMPLETIONS = "chat_completions"
_VALID_TRANSPORTS = frozenset({_RESPONSES, _CHAT_COMPLETIONS})


@dataclass(frozen=True)
class AzureResponsesCapabilities:
    """Features enabled for one Azure model deployment."""

    reasoning: bool = True
    verbosity: bool = True
    strict_schema: bool = True
    tools: bool = True


@dataclass(frozen=True)
class AzureResponsesCall:
    """Provider-neutral inputs for one Azure Responses request."""

    model_id: str
    system: str
    messages: list[dict[str, Any]]
    max_output_tokens: int
    temperature: float = 0.0
    tool_config: dict[str, Any] | None = None
    structured_schema: dict[str, Any] | None = None
    response_items: list[Any] | None = None
    verbosity: str | None = None
    use_reasoning: bool = False
    reasoning_effort: str = "high"
    json_mode: bool = False
    capabilities: AzureResponsesCapabilities | None = None


def _responses_read_timeout_s() -> float:
    """Seconds to wait for one GPT-5 Responses body.

    Reasoning windows often need more than the Chat Completions default of 45s.
    """
    raw = (
        os.getenv("AZURE_OPENAI_RESPONSES_READ_TIMEOUT")
        or os.getenv("AZURE_OPENAI_READ_TIMEOUT")
        or "120.0"
    )
    return float(raw)


def reasoning_max_output_tokens(
    max_tokens: int,
    *,
    tier: str,
    use_reasoning: bool,
) -> int:
    """Expand the output budget so GPT-5 thinking does not cut off JSON.

    GPT-5 Responses still spends thinking tokens when reasoning is off.
    Always leave headroom. Expand further when reasoning is requested.
    """
    requested = max(1, int(max_tokens))
    if use_reasoning and str(tier).strip().lower() != "small":
        scale = 4
    else:
        scale = 2
    return min(max(requested * scale, 8000), 32768)


def azure_transport_name() -> str:
    """Return the configured Azure transport name."""
    value = (os.getenv("AZURE_OPENAI_TRANSPORT") or _RESPONSES).strip().lower()
    if value not in _VALID_TRANSPORTS:
        allowed = ", ".join(sorted(_VALID_TRANSPORTS))
        raise ValueError(f"AZURE_OPENAI_TRANSPORT must be one of: {allowed}")
    return value


def create_azure_responses_client() -> Any:
    """Create an OpenAI client for Azure's undated v1 endpoint."""
    import httpx
    from openai import OpenAI

    connect_timeout = float(os.getenv("AZURE_OPENAI_CONNECT_TIMEOUT", "10.0"))
    read_timeout = _responses_read_timeout_s()
    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
    return OpenAI(
        base_url=f"{endpoint}/openai/v1/",
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        timeout=httpx.Timeout(read_timeout, connect=connect_timeout),
        max_retries=0,
    )


def _capability_overrides() -> dict[str, Any]:
    raw = os.getenv("AZURE_OPENAI_CAPABILITIES", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("AZURE_OPENAI_CAPABILITIES must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("AZURE_OPENAI_CAPABILITIES must be a JSON object")
    return parsed


def capabilities_for_model(model_id: str) -> AzureResponsesCapabilities:
    """Return explicit per-deployment capabilities with GPT-5 defaults."""
    values = _capability_overrides().get(model_id, {})
    if values and not isinstance(values, dict):
        raise ValueError(f"Capabilities for {model_id} must be an object")
    defaults = AzureResponsesCapabilities()
    return AzureResponsesCapabilities(
        reasoning=bool(values.get("reasoning", defaults.reasoning)),
        verbosity=bool(values.get("verbosity", defaults.verbosity)),
        strict_schema=bool(values.get("strict_schema", defaults.strict_schema)),
        tools=bool(values.get("tools", defaults.tools)),
    )


def _get_value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content or "")
    parts: list[str] = []
    for item in content:
        text = str(_get_value(item, "text") or "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts)


def _response_output_text(response: Any) -> str:
    direct = str(_get_value(response, "output_text", "") or "").strip()
    if direct:
        return direct
    parts: list[str] = []
    for item in list(_get_value(response, "output", []) or []):
        item_type = str(_get_value(item, "type") or "")
        if item_type in {"reasoning", "function_call"}:
            continue
        text = _message_text(_get_value(item, "content"))
        if not text:
            text = str(_get_value(item, "text") or "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _build_input(call: AzureResponsesCall) -> list[Any]:
    items: list[Any] = [{"role": "developer", "content": call.system}]
    for message in call.messages:
        items.append(
            {
                "role": str(message.get("role") or "user"),
                "content": _message_text(message.get("content")),
            }
        )
    items.extend(call.response_items or [])
    return items


def _translate_tool(tool: Any) -> dict[str, Any] | None:
    if not isinstance(tool, dict):
        return None
    spec = tool.get("toolSpec")
    if not isinstance(spec, dict) or not spec.get("name"):
        return None
    input_schema = spec.get("inputSchema") or {}
    schema = input_schema.get("json", {}) if isinstance(input_schema, dict) else {}
    return {
        "type": "function",
        "name": str(spec["name"]),
        "description": str(spec.get("description") or ""),
        "parameters": schema,
        "strict": _is_strict_schema(schema),
    }


def _is_strict_schema(schema: Any) -> bool:
    """Return True when a schema satisfies OpenAI strict-tool rules."""
    if not isinstance(schema, dict):
        return False
    if schema.get("type") == "object":
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            return False
        if schema.get("additionalProperties") is not False:
            return False
        if set(schema.get("required") or []) != set(properties):
            return False
        return all(_is_strict_schema(value) for value in properties.values())
    if schema.get("type") == "array":
        return _is_strict_schema(schema.get("items"))
    return bool(schema.get("type") or schema.get("anyOf") or schema.get("enum"))


def _translate_tools(tool_config: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not tool_config:
        return []
    translated = [_translate_tool(tool) for tool in tool_config.get("tools", [])]
    return [tool for tool in translated if tool is not None]


def _translate_tool_choice(tool_config: dict[str, Any] | None) -> Any:
    choice = (tool_config or {}).get("toolChoice")
    if not isinstance(choice, dict):
        return None
    forced = choice.get("tool")
    if isinstance(forced, dict) and forced.get("name"):
        return {"type": "function", "name": str(forced["name"])}
    if "any" in choice:
        return "required"
    if "auto" in choice:
        return "auto"
    return None


def _text_config(call: AzureResponsesCall) -> dict[str, Any] | None:
    text: dict[str, Any] = {}
    if call.structured_schema is not None:
        if call.structured_schema.get("type") != "object":
            raise ValueError("Azure strict structured output requires an object root")
        text["format"] = {
            "type": "json_schema",
            "name": "response",
            "schema": call.structured_schema,
            "strict": True,
        }
    elif call.json_mode:
        text["format"] = {"type": "json_object"}
    if call.verbosity:
        text["verbosity"] = call.verbosity
    return text or None


def _validate_capabilities(
    call: AzureResponsesCall, capabilities: AzureResponsesCapabilities
) -> None:
    requested_tools = bool(_translate_tools(call.tool_config))
    checks = (
        (call.use_reasoning, capabilities.reasoning, "reasoning"),
        (bool(call.verbosity), capabilities.verbosity, "verbosity"),
        (
            call.structured_schema is not None,
            capabilities.strict_schema,
            "strict_schema",
        ),
        (requested_tools, capabilities.tools, "tools"),
    )
    unsupported = [
        name for requested, supported, name in checks if requested and not supported
    ]
    if unsupported:
        names = ", ".join(unsupported)
        raise ValueError(f"Azure deployment {call.model_id} lacks: {names}")


def build_azure_responses_request(call: AzureResponsesCall) -> dict[str, Any]:
    """Build one stateless Responses API request."""
    capabilities = call.capabilities or capabilities_for_model(call.model_id)
    _validate_capabilities(call, capabilities)
    request: dict[str, Any] = {
        "model": call.model_id,
        "input": _build_input(call),
        "max_output_tokens": call.max_output_tokens,
        "store": False,
    }
    text = _text_config(call)
    tools = _translate_tools(call.tool_config)
    tool_choice = _translate_tool_choice(call.tool_config)
    if text is not None:
        request["text"] = text
    if tools:
        request["tools"] = tools
    if tool_choice is not None:
        request["tool_choice"] = tool_choice
    if call.use_reasoning:
        request["reasoning"] = {"effort": call.reasoning_effort}
    elif call.temperature != 0.0:
        request["temperature"] = call.temperature
    return request


def _parse_arguments(arguments: Any) -> dict[str, Any]:
    if isinstance(arguments, dict):
        return arguments
    if not isinstance(arguments, str) or not arguments:
        return {}
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_tool_uses(output_items: list[Any]) -> list[dict[str, Any]]:
    tool_uses: list[dict[str, Any]] = []
    for item in output_items:
        if _get_value(item, "type") != "function_call":
            continue
        tool_uses.append(
            {
                "toolUseId": str(
                    _get_value(item, "call_id") or _get_value(item, "id") or ""
                ),
                "name": str(_get_value(item, "name") or ""),
                "input": _parse_arguments(_get_value(item, "arguments")),
            }
        )
    return tool_uses


def _usage_counts(response: Any) -> tuple[int, int, int, int]:
    usage = _get_value(response, "usage")
    input_details = _get_value(usage, "input_tokens_details")
    output_details = _get_value(usage, "output_tokens_details")
    return (
        int(_get_value(usage, "input_tokens", 0) or 0),
        int(_get_value(usage, "output_tokens", 0) or 0),
        int(_get_value(input_details, "cached_tokens", 0) or 0),
        int(_get_value(output_details, "reasoning_tokens", 0) or 0),
    )


def parse_azure_responses_response(response: Any, model_id: str) -> Any:
    """Convert an SDK Responses object to the provider-neutral response."""
    from libs.llm_client.factory import LLMResponse

    output_items = list(_get_value(response, "output", []) or [])
    input_tokens, output_tokens, cached_tokens, reasoning_tokens = _usage_counts(
        response
    )
    incomplete = _get_value(response, "incomplete_details")
    stop_reason = _get_value(incomplete, "reason") or _get_value(response, "status", "")
    return LLMResponse(
        text=_response_output_text(response),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached_tokens,
        reasoning_tokens=reasoning_tokens,
        stop_reason=str(stop_reason or ""),
        model_id=model_id,
        tool_uses=_parse_tool_uses(output_items),
        response_id=str(_get_value(response, "id", "") or ""),
        raw_output_items=output_items,
    )


def send_azure_responses(client: Any, call: AzureResponsesCall) -> Any:
    """Send one Responses request and retry short Azure outages."""
    from libs.llm_client.azure_retry import call_azure_with_retry

    payload = build_azure_responses_request(call)
    response = call_azure_with_retry(
        lambda: client.responses.create(**payload),
        model_id=call.model_id,
    )
    return parse_azure_responses_response(response, call.model_id)
