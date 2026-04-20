"""Load FHIR configuration from the knowledge graph.

Atlas trace:
  DO: DO-61EE87E0
  DI: DI-6A1CD328
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-61EE87E0")

Unlike the VRB which uses HTTP to talk to a separate fhir-api,
PCA reads Device/Measure/ValueSet nodes directly from the
KnowledgeGraphClient since all services share the same process.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from libs.agent_config.models import AgentConfig, FHIRConfig
from libs.neo4j_client.client import KnowledgeGraphClient

logger = logging.getLogger(__name__)


class FHIRConfigLoader:
    """Load agent config from the Knowledge Graph Neo4j instance."""

    def __init__(self, client: Optional[KnowledgeGraphClient] = None) -> None:
        self._client = client or KnowledgeGraphClient()

    def load(self) -> FHIRConfig:
        config = FHIRConfig()
        config.agents = self._load_devices()
        config.measures = self._load_resources("Measure")
        config.valuesets = self._load_resources("ValueSet")
        logger.info(
            "FHIR config loaded: %d agents, %d measures, %d valuesets",
            len(config.agents),
            len(config.measures),
            len(config.valuesets),
        )
        return config

    def _load_devices(self) -> Dict[str, AgentConfig]:
        rows = self._client.run(
            "MATCH (d:Device) WHERE d.status = 'active' " "RETURN d {.*} AS resource"
        )
        agents: Dict[str, AgentConfig] = {}
        for row in rows:
            resource = row.get("resource", {})
            ac = AgentConfig.from_device(resource)
            if ac.type_code:
                agents[ac.type_code] = ac
        return agents

    def _load_resources(self, label: str) -> Dict[str, Dict[str, Any]]:
        rows = self._client.run(f"MATCH (r:{label}) RETURN r {{.*}} AS resource")
        result: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            resource = row.get("resource", {})
            rid = resource.get("id", "")
            if rid:
                result[rid] = resource
        return result
