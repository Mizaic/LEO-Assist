"""
Knowledge base data structures for entity linking.

Adapted from scispaCy's ``linking_utils.py``, extended with SNOMED, ICD-10,
and Read code fields so the linker returns all coding systems in one lookup.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)


class Entity(NamedTuple):
    concept_id: str
    canonical_name: str
    aliases: list[str]
    types: list[str] = []
    definition: str | None = None
    cui: str | None = None
    icd10_codes: list[str] = []
    read_codes: list[str] = []


class KnowledgeBase:
    """In-memory terminology knowledge base with alias-to-concept reverse index."""

    def __init__(self) -> None:
        self.cui_to_entity: dict[str, Entity] = {}
        self.alias_to_cuis: dict[str, set[str]] = defaultdict(set)

    def add_entity(self, entity: Entity) -> None:
        self.cui_to_entity[entity.concept_id] = entity
        canon = entity.canonical_name.lower()
        self.alias_to_cuis[canon].add(entity.concept_id)
        for alias in entity.aliases:
            self.alias_to_cuis[alias.lower()].add(entity.concept_id)

    def __len__(self) -> int:
        return len(self.cui_to_entity)

    @classmethod
    def from_jsonl(cls, filepath: str | Path) -> KnowledgeBase:
        kb = cls()
        filepath = Path(filepath)
        count = 0
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                entity = Entity(
                    concept_id=data["concept_id"],
                    canonical_name=data["canonical_name"],
                    aliases=data.get("aliases", []),
                    types=data.get("types", []),
                    definition=data.get("definition"),
                    cui=data.get("cui"),
                    icd10_codes=data.get("icd10_codes", []),
                    read_codes=data.get("read_codes", []),
                )
                kb.add_entity(entity)
                count += 1
                if count % 100_000 == 0:
                    logger.info("Loaded %d entities", count)

        logger.info(
            "Knowledge base loaded: %d entities, %d aliases",
            len(kb.cui_to_entity),
            len(kb.alias_to_cuis),
        )
        return kb
