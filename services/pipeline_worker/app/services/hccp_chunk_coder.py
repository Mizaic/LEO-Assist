"""Chunk-level coding helper for the HCCP bridge.

Atlas trace:
  DI: DI-6B52E28E
  DO: DO-4B8D8AEB
  VT: VT-66810B48
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from libs.cypher.documents_queries import write_documents_from_sentences_payload
from libs.pipeline_graph.subgraphs.extraction import build_extraction_subgraph
from libs.pipeline_graph.subgraphs.persist import (
    _canonical_entity_relations,
    _extract_body_site_fields,
)
from libs.pipeline_graph.subgraphs.post_processing import build_post_processing_subgraph
from libs.pipeline_graph.subgraphs.terminology import build_terminology_subgraph


@dataclass
class HCCPChunkCodingResult:
    chunk_id: str
    documents_written: int
    entities_count: int


class HCCPChunkCoder:
    """Run the standard Core AI coding path and persist Chunk DOCUMENTS links."""

    def __init__(
        self,
        *,
        extraction_graph: Any | None = None,
        post_processing_graph: Any | None = None,
        terminology_graph: Any | None = None,
        documents_writer: Callable[..., int] = write_documents_from_sentences_payload,
    ) -> None:
        self._extraction_graph = extraction_graph or build_extraction_subgraph()
        self._post_processing_graph = (
            post_processing_graph or build_post_processing_subgraph()
        )
        self._terminology_graph = terminology_graph or build_terminology_subgraph()
        self._documents_writer = documents_writer

    def code_chunk(
        self, chunk: dict[str, Any], *, session: Any, run_id: str
    ) -> HCCPChunkCodingResult:
        chunk_id = str(chunk.get("chunk_id") or "").strip()
        text = str(chunk.get("text") or "")
        if not chunk_id:
            raise ValueError("Resolved HCCP chunk is missing chunk_id")

        extraction_state = self._run_extraction(chunk_id, text)
        _raise_on_errors("extraction", extraction_state)
        post_state = self._run_post_processing(text, extraction_state)
        _raise_on_errors("post_processing", post_state)
        term_state = self._run_terminology(post_state)
        _raise_on_errors("terminology", term_state)
        entities = list(term_state.get("entities") or [])
        sentences = list(extraction_state.get("sentences") or [])
        payload = build_hccp_sentences_payload(text, sentences, entities)
        written = self._documents_writer(
            chunk_id,
            payload,
            session,
            source="hccp_bridge",
            run_id=run_id,
            source_label="Chunk",
        )
        return HCCPChunkCodingResult(
            chunk_id=chunk_id,
            documents_written=written,
            entities_count=len(entities),
        )

    def _run_extraction(self, chunk_id: str, text: str) -> dict[str, Any]:
        return dict(
            self._extraction_graph.invoke(
                {
                    "encounter_id": chunk_id,
                    "encounter_text": text,
                    "extraction_method": "llm",
                }
            )
        )

    def _run_post_processing(
        self, text: str, extraction_state: dict[str, Any]
    ) -> dict[str, Any]:
        return dict(
            self._post_processing_graph.invoke(
                {
                    "encounter_text": text,
                    "entities": extraction_state.get("entities") or [],
                    "coding_mode": "hitl",
                    "enable_disorder_gate": False,
                }
            )
        )

    def _run_terminology(self, post_state: dict[str, Any]) -> dict[str, Any]:
        return dict(
            self._terminology_graph.invoke(
                {
                    "entities": post_state.get("entities") or [],
                    "errors": post_state.get("errors") or [],
                }
            )
        )


def _raise_on_errors(stage: str, state: dict[str, Any]) -> None:
    errors = [str(error) for error in state.get("errors") or [] if error]
    if errors:
        raise RuntimeError(f"{stage}: {'; '.join(errors)}")


def build_hccp_sentences_payload(
    chunk_text: str,
    sentences: list[dict[str, Any]],
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    terms_by_sentence = _terms_by_sentence(entities)
    payload = _sentences_payload(sentences, terms_by_sentence)
    if payload:
        return payload
    return [{"sentence_id": "s-fallback", "text": chunk_text, "terms": []}]


def _terms_by_sentence(
    entities: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for idx, entity in enumerate(entities):
        term = _entity_to_term(entity, entities, idx)
        if term is None:
            continue
        sid = str(entity.get("__sentence_id") or "s-fallback")
        grouped.setdefault(sid, []).append(term)
    return grouped


def _entity_to_term(
    entity: dict[str, Any], entities: list[dict[str, Any]], index: int
) -> dict[str, Any] | None:
    concept_id = entity.get("concept_id")
    if not concept_id or entity.get("terminology_unresolved"):
        return None
    body_site, body_site_concept_id, body_site_term = _extract_body_site_fields(
        entity, entities
    )
    return {
        "text": entity.get("text", ""),
        "semantic_tag": entity.get("semantic_tag") or entity.get("label") or "other",
        "assertion": entity.get("assertion", "present"),
        "modifiers": entity.get("modifiers") or {},
        "body_site": body_site,
        "body_site_concept_id": body_site_concept_id,
        "body_site_term": body_site_term,
        "relations": _canonical_entity_relations(entity, entities),
        "numeric_value": entity.get("value"),
        "unit": entity.get("unit"),
        "reference_range": entity.get("reference_range"),
        "decision_tier": entity.get("decision_tier") or entity.get("tier"),
        "coding": _coding(entity, concept_id),
        "extraction_model_name": entity.get("__model_name", ""),
        "extraction_model_version": entity.get("__model_version", ""),
        "contract_version": entity.get("__contract_version", ""),
        "domain": entity.get("domain", "clinical"),
        "entity_index": index,
    }


def _coding(entity: dict[str, Any], concept_id: Any) -> dict[str, Any]:
    return {
        "snomed_concept_id": str(concept_id),
        "read_code": entity.get("read_code"),
        "snomed_term": entity.get("term") or entity.get("text", ""),
        "score": float(entity.get("score") or 0.0),
        "source": "hccp_bridge",
    }


def _sentences_payload(
    sentences: list[dict[str, Any]],
    terms_by_sentence: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for sentence in sentences:
        sid = str(sentence.get("sentence_id") or "")
        if not sid or sid in seen_ids:
            continue
        seen_ids.add(sid)
        payload.append(
            {
                "sentence_id": sid,
                "text": sentence.get("text", ""),
                "terms": terms_by_sentence.pop(sid, []),
            }
        )
    for sid, terms in terms_by_sentence.items():
        payload.append(
            {"sentence_id": sid, "text": terms[0].get("text", ""), "terms": terms}
        )
    return payload
