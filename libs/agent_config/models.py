"""Data models for FHIR-based agent configuration.

AgentConfig wraps a single FHIR Device resource.
FHIRConfig aggregates all agents, valuesets, and measures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AgentConfig:
    """Configuration parsed from a single FHIR Device resource."""

    device_id: str
    type_code: str
    type_display: str
    description: str
    status: str
    version: str
    properties: Dict[str, Any] = field(default_factory=dict)
    prompts: Dict[str, str] = field(default_factory=dict)
    extensions: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_device(cls, resource: Dict[str, Any]) -> AgentConfig:
        device_type = resource.get("type") or {}
        codings = device_type.get("coding") or []
        type_code = codings[0].get("code", "") if codings else ""
        type_display = codings[0].get("display", "") if codings else ""

        versions = resource.get("version") or []
        version = versions[0].get("value", "0.0.0") if versions else "0.0.0"

        properties = _parse_device_properties(resource)
        prompts, extensions, description = _parse_device_extensions(resource)

        return cls(
            device_id=resource.get("id", ""),
            type_code=type_code,
            type_display=type_display,
            description=description,
            status=resource.get("status", "active"),
            version=version,
            properties=properties,
            prompts=prompts,
            extensions=extensions,
        )

    def get_property(self, name: str, default: Any = None) -> Any:
        return self.properties.get(name, default)

    def get_prompt(self, name: str, default: str = "") -> str:
        return self.prompts.get(name, default)


@dataclass
class FHIRConfig:
    """Complete FHIR-based configuration loaded at startup."""

    agents: Dict[str, AgentConfig] = field(default_factory=dict)
    valuesets: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    conceptmaps: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    pipeline: Optional[Dict[str, Any]] = None
    measures: Dict[str, Dict[str, Any]] = field(default_factory=dict)


def _parse_device_properties(resource: Dict[str, Any]) -> Dict[str, Any]:
    properties: Dict[str, Any] = {}
    for prop in resource.get("property") or []:
        name = (prop.get("type") or {}).get("text", "")
        if not name:
            continue
        qty_list = prop.get("valueQuantity") or []
        if qty_list:
            val = (
                qty_list[0].get("value")
                if isinstance(qty_list, list)
                else qty_list.get("value")
            )
            properties[name] = val
            continue
        code_list = prop.get("valueCode") or []
        if code_list:
            val = (
                code_list[0].get("text")
                if isinstance(code_list, list)
                else code_list.get("text")
            )
            properties[name] = val
    return properties


def _parse_device_extensions(
    resource: Dict[str, Any],
) -> tuple[Dict[str, str], Dict[str, Any], str]:
    prompts: Dict[str, str] = {}
    extensions: Dict[str, Any] = {}
    description = ""
    for ext in resource.get("extension") or []:
        url = ext.get("url", "")
        short_name = url.rsplit("/", 1)[-1] if "/" in url else url
        if ext.get("valueString") is not None:
            if short_name in ("agent-description", "description"):
                description = ext["valueString"]
                continue
            if "prompt" in short_name.lower() or "template" in short_name.lower():
                prompts[short_name] = ext["valueString"]
            else:
                extensions[short_name] = ext["valueString"]
        elif ext.get("valueInteger") is not None:
            extensions[short_name] = ext["valueInteger"]
        elif ext.get("valueDecimal") is not None:
            extensions[short_name] = ext["valueDecimal"]
        elif ext.get("valueBoolean") is not None:
            extensions[short_name] = ext["valueBoolean"]
    return prompts, extensions, description
