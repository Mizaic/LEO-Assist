"""
Two-tier entity linker: local TF-IDF index (Tier 1) + Neo4j fallback (Tier 2).

Tier 1 uses the ``CandidateGenerator`` for sub-millisecond approximate string
matching against the terminology knowledge base. Tier 2 falls back to a Neo4j
fulltext query for entities that Tier 1 cannot resolve above threshold.

Sets ``Span._.kb_ents``, ``Span._.cui``, ``Span._.snomed_code``,
``Span._.snomed_term``, ``Span._.icd10_codes``, ``Span._.read_code``,
``Span._.linker_score``, and ``Span._.source``.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from spacy.language import Language
from spacy.tokens import Doc, Span

from ..kb.candidate_generation import CandidateGenerator
from ..kb.knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)

NEO4J_FALLBACK_QUERY = """
CALL db.index.fulltext.queryNodes('termFulltext', $term, {limit: 5})
YIELD node, score
MATCH (c:Concept)<-[:DESCRIBES]-(node)
OPTIONAL MATCH (c)-[:SAME_AS]-(u:UmlsConcept)
OPTIONAL MATCH (u)-[:MAPS_TO_ICD10]->(i:Icd10Code)
OPTIONAL MATCH (u)-[:MAPS_TO_READ]->(r:ReadCode)
RETURN c.id AS concept_id,
       node.term AS matched_term,
       score,
       u.cui AS cui,
       collect(DISTINCT i.code) AS icd10_codes,
       collect(DISTINCT r.code) AS read_codes
ORDER BY score DESC
LIMIT 5
"""


@Language.factory(
    "clinical_entity_linker",
    default_config={
        "kb_path": None,
        "index_path": None,
        "threshold": 0.7,
        "no_definition_threshold": 0.95,
        "max_entities_per_mention": 5,
        "k": 30,
        "resolve_abbreviations": True,
    },
)
class EntityLinker:
    """Two-tier entity linker: TF-IDF local index + Neo4j fallback."""

    def __init__(
        self,
        nlp: Language,
        name: str = "clinical_entity_linker",
        kb_path: str | None = None,
        index_path: str | None = None,
        threshold: float = 0.7,
        no_definition_threshold: float = 0.95,
        max_entities_per_mention: int = 5,
        k: int = 30,
        resolve_abbreviations: bool = True,
    ):
        self.nlp = nlp
        self.name = name
        self.threshold = threshold
        self.no_definition_threshold = no_definition_threshold
        self.max_entities = max_entities_per_mention
        self.k = k
        self.resolve_abbreviations = resolve_abbreviations

        self._kb: KnowledgeBase | None = None
        self._candidate_generator: CandidateGenerator | None = None
        self._neo4j_driver = None

        if kb_path and index_path:
            self._kb = KnowledgeBase.from_jsonl(kb_path)
            self._candidate_generator = CandidateGenerator.from_artifacts(
                self._kb, index_path
            )

    def set_neo4j_driver(self, driver) -> None:
        self._neo4j_driver = driver

    def _get_mention_text(self, span: Span) -> str:
        if self.resolve_abbreviations and span._.long_form is not None:
            return span._.long_form.text
        if hasattr(span[0]._, "expanded_form") and span[0]._.expanded_form:
            return span[0]._.expanded_form
        return span.text

    def __call__(self, doc: Doc) -> Doc:
        if not doc.ents:
            return doc

        mention_texts = [self._get_mention_text(ent) for ent in doc.ents]

        # --- Tier 1: Local TF-IDF index ---
        tier1_results: list[list[tuple[str, float]]] = [[] for _ in doc.ents]
        unresolved_indices: list[int] = []

        if self._candidate_generator is not None:
            batch_candidates = self._candidate_generator(mention_texts, k=self.k)
            for i, candidates in enumerate(batch_candidates):
                filtered = []
                for cand in candidates:
                    best_score = max(cand.similarities) if cand.similarities else 0.0
                    entity = self._kb.cui_to_entity.get(cand.concept_id)
                    effective_threshold = self.threshold
                    if entity and entity.definition is None:
                        effective_threshold = self.no_definition_threshold
                    if best_score >= effective_threshold:
                        filtered.append((cand.concept_id, best_score))
                filtered.sort(key=lambda x: x[1], reverse=True)
                tier1_results[i] = filtered[: self.max_entities]
                if not filtered:
                    unresolved_indices.append(i)
        else:
            unresolved_indices = list(range(len(doc.ents)))

        # --- Tier 2: Neo4j fallback ---
        tier2_results: dict[int, list[tuple[str, float]]] = {}
        if unresolved_indices and self._neo4j_driver is not None:
            tier2_results = self._neo4j_fallback(
                [mention_texts[i] for i in unresolved_indices],
                unresolved_indices,
            )

        # --- Enrich entities ---
        ents = list(doc.ents)
        for i, ent in enumerate(ents):
            kb_ents = tier1_results[i]
            source = "local_kb"

            if not kb_ents and i in tier2_results:
                kb_ents = tier2_results[i]
                source = "neo4j_fallback"

            if ent._.source == "read_code":
                source = "read_code"

            ent._.kb_ents = kb_ents
            ent._.source = source

            if kb_ents:
                top_id, top_score = kb_ents[0]
                ent._.linker_score = top_score

                if self._kb and top_id in self._kb.cui_to_entity:
                    entity = self._kb.cui_to_entity[top_id]
                    ent._.snomed_code = entity.concept_id
                    ent._.snomed_term = entity.canonical_name
                    ent._.cui = entity.cui
                    if entity.icd10_codes:
                        ent._.icd10_codes = entity.icd10_codes
                    if entity.read_codes:
                        ent._.read_code = entity.read_codes[0]

        return doc

    def _neo4j_fallback(
        self,
        mention_texts: list[str],
        indices: list[int],
    ) -> dict[int, list[tuple[str, float]]]:
        """Synchronous wrapper around async Neo4j queries."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self._neo4j_fallback_async(mention_texts, indices),
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self._neo4j_fallback_async(mention_texts, indices)
                )
        except RuntimeError:
            return asyncio.run(
                self._neo4j_fallback_async(mention_texts, indices)
            )

    async def _neo4j_fallback_async(
        self,
        mention_texts: list[str],
        indices: list[int],
    ) -> dict[int, list[tuple[str, float]]]:
        results: dict[int, list[tuple[str, float]]] = {}
        async with self._neo4j_driver.session() as session:
            for text, idx in zip(mention_texts, indices):
                try:
                    result = await session.run(NEO4J_FALLBACK_QUERY, term=text)
                    records = await result.data()
                    candidates = []
                    for rec in records:
                        score = rec.get("score", 0.0)
                        concept_id = rec.get("concept_id", "")
                        if concept_id:
                            candidates.append((concept_id, score))
                    if candidates:
                        results[idx] = candidates[: self.max_entities]
                except Exception:
                    logger.debug("Neo4j fallback failed for '%s'", text, exc_info=True)
        return results
