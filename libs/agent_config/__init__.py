"""Agent configuration store.

Provides read-only access to FHIR Device-based agent configuration
(prompts, thresholds, extensions). Loaded at startup from the FHIR API
and cached in-memory for fast access by downstream services.

Ported from VRB clinical-ai/app/core/agent_config_store.py and
clinical-ai/app/core/fhir_config_client.py.
"""

from libs.agent_config.store import (
    get_agent_extension,
    get_agent_prompt,
    get_agent_property,
    get_quality_target,
    is_loaded,
    set_config,
)
from libs.agent_config.models import AgentConfig, FHIRConfig
from libs.agent_config.loader import FHIRConfigLoader

__all__ = [
    "AgentConfig",
    "FHIRConfig",
    "FHIRConfigLoader",
    "get_agent_extension",
    "get_agent_prompt",
    "get_agent_property",
    "get_quality_target",
    "is_loaded",
    "set_config",
]
