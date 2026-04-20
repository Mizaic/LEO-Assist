"""Module-level cache for FHIR agent configuration.

Atlas trace:
  DO: DO-61EE87E0
  DI: DI-6A1CD328
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-61EE87E0")

Call set_config() at startup to populate the cache, then use
get_agent_property / get_agent_prompt / get_agent_extension anywhere.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from libs.agent_config.models import FHIRConfig

logger = logging.getLogger(__name__)

_config: Optional[FHIRConfig] = None


def set_config(config: FHIRConfig) -> None:
    global _config
    _config = config
    logger.info(
        "Agent config store populated: %d agents",
        len(config.agents) if config else 0,
    )


def get_agent_property(agent_type: str, prop_name: str, default: Any = None) -> Any:
    if _config is None:
        return default
    agent = _config.agents.get(agent_type)
    if agent is None:
        return default
    return agent.get_property(prop_name, default)


def get_agent_prompt(agent_type: str, prompt_name: str, default: str = "") -> str:
    if _config is None:
        return default
    agent = _config.agents.get(agent_type)
    if agent is None:
        return default
    return agent.get_prompt(prompt_name, default)


def get_agent_extension(agent_type: str, ext_name: str, default: Any = None) -> Any:
    if _config is None:
        return default
    agent = _config.agents.get(agent_type)
    if agent is None:
        return default
    return agent.extensions.get(ext_name, default)


def get_quality_target(
    target_code: str, field: str = "target", default: Any = None
) -> Any:
    if _config is None:
        return default
    measure = _config.measures.get("nhs-cancer-quality-targets")
    if not measure:
        return default
    for group in measure.get("group") or []:
        code = (group.get("code") or {}).get("text", "")
        if code == target_code:
            for strat in group.get("stratifier") or []:
                for ext in strat.get("extension") or []:
                    url = ext.get("url", "")
                    if field == "target" and url.endswith("/target-value"):
                        qty = ext.get("valueQuantity") or {}
                        return qty.get("value", default)
                    elif field == "percentage" and url.endswith("/target-percentage"):
                        return ext.get("valueDecimal", default)
    return default


def is_loaded() -> bool:
    return _config is not None
