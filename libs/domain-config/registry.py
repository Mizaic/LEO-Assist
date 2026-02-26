"""Domain registry that loads definitions from FHIR ValueSets.

Each domain maps to a FHIR ValueSet stored in the Knowledge Graph.
The registry caches loaded definitions for the lifetime of the process.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("libs.domain_config")


@dataclass
class DomainDefinition:
    """A single clinical domain definition."""

    name: str
    valueset_url: str
    ancestor_concepts: List[str] = field(default_factory=list)
    semantic_tags: List[str] = field(default_factory=list)
    display: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class DomainRegistry:
    """Registry of clinical domains loaded from the Knowledge Graph.

    Usage::

        registry = DomainRegistry()
        await registry.load(knowledge_graph_client)
        symptoms = registry.get("symptoms")
    """

    def __init__(self) -> None:
        self._domains: Dict[str, DomainDefinition] = {}

    async def load(self, kg_client) -> None:
        """Load domain definitions from FHIR ValueSet nodes in Knowledge Graph."""
        query = """
        MATCH (vs:ValueSet)
        WHERE vs.status = 'active'
        OPTIONAL MATCH (vs)-[:INCLUDES]->(c:Concept)
        WITH vs, collect(c.sctid) AS concepts, collect(DISTINCT c.semanticTag) AS tags
        RETURN vs.url AS url, vs.name AS name, vs.title AS title,
               concepts, tags
        """
        records = kg_client.run(query)
        self._domains.clear()
        for rec in records:
            name = rec.get("name", "")
            if not name:
                continue
            defn = DomainDefinition(
                name=name,
                valueset_url=rec.get("url", ""),
                ancestor_concepts=rec.get("concepts", []),
                semantic_tags=rec.get("tags", []),
                display=rec.get("title", name),
            )
            self._domains[name] = defn
        logger.info("Loaded %d domain definitions from Knowledge Graph", len(self._domains))

    def get(self, name: str) -> Optional[DomainDefinition]:
        return self._domains.get(name)

    def all(self) -> Dict[str, DomainDefinition]:
        return dict(self._domains)

    @property
    def domain_names(self) -> List[str]:
        return list(self._domains.keys())
