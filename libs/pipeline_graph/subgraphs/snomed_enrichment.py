"""SNOMED-grounded relation candidates and inferred body sites.

Atlas trace:
  UN: UN-19FDDE7E
  DI: DI-209F4326
  DO: DO-604CE96E
  VT: VT-E3682B7B
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-604CE96E")
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from libs.relations.policy import is_relation_allowed

logger = logging.getLogger(__name__)

RelatedFetcher = Callable[[list[str]], dict[str, dict[str, Any]]]

_RELATED_KEYS = (
    "interpreted_by_findings",
    "component_of_procedures",
    "interprets_observables",
    "has_components",
    "associated_findings",
    "finding_sites",
    "procedure_sites",
)

_REL_TO_TYPE = {
    "HAS_FINDING_SITE": "finding_site",
    "HAS_PROCEDURE_SITE": "finding_site",
    "FINDING_SITE": "finding_site",
    "PROCEDURE_SITE": "finding_site",
    "INTERPRETS": "interprets",
    "INTERPRETED_BY": "interprets",
    "HAS_COMPONENT": "component_of",
    "COMPONENT_OF": "component_of",
    "HAS_ASSOCIATED_FINDING": "associated_finding",
}

_SITE_RELS = frozenset(
    {"HAS_FINDING_SITE", "HAS_PROCEDURE_SITE", "FINDING_SITE", "PROCEDURE_SITE"}
)
# Neighbour is the relation head; current entity is the tail.
_REVERSE_RELS = frozenset({"INTERPRETED_BY", "HAS_COMPONENT"})


class SnomedEnrichState(TypedDict, total=False):
    entities: list[dict[str, Any]]
    snomed_candidates: list[dict[str, Any]]
    errors: list[str]


def _concept_id(entity: dict[str, Any]) -> str:
    if entity.get("terminology_unresolved"):
        return ""
    return str(entity.get("concept_id") or "").strip()


def _strip_fsn(fsn: str) -> str:
    text = (fsn or "").strip()
    if text.endswith(")") and "(" in text:
        return text[: text.rfind("(")].strip() or text
    return text


def _flatten_related(related: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for key in _RELATED_KEYS:
        for item in related.get(key) or []:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            rows.append(
                {
                    "id": str(item["id"]),
                    "fsn": str(item.get("fsn") or ""),
                    "semantic_tag": str(item.get("semantic_tag") or ""),
                    "rel": str(item.get("rel") or key).upper(),
                }
            )
    return rows


def _head_tail(src_idx: int, tgt_idx: int, snomed_rel: str) -> tuple[int, int]:
    if snomed_rel in _REVERSE_RELS:
        return tgt_idx, src_idx
    return src_idx, tgt_idx


def _append_candidate(
    entities: list[dict[str, Any]],
    head_idx: int,
    tail_idx: int,
    rel_type: str,
    snomed_rel: str,
) -> dict[str, Any] | None:
    if head_idx == tail_idx:
        return None
    head = entities[head_idx]
    tail = entities[tail_idx]
    allowed, _ = is_relation_allowed(
        source_label=str(head.get("label") or head.get("semantic_tag") or ""),
        target_label=str(tail.get("label") or tail.get("semantic_tag") or ""),
        relation_type=rel_type,
    )
    if not allowed:
        return None
    row = {
        "type": rel_type,
        "target_idx": tail_idx,
        "target_text": str(tail.get("text") or ""),
        "target_concept_id": _concept_id(tail),
        "confidence": 0.9,
        "source": "snomed",
        "snomed_rel": snomed_rel,
    }
    existing = list(head.get("__snomed_relations") or [])
    key = (rel_type, tail_idx)
    if any((r.get("type"), r.get("target_idx")) == key for r in existing):
        return None
    existing.append(row)
    head["__snomed_relations"] = existing
    return {
        "head_idx": head_idx,
        "tail_idx": tail_idx,
        "type": rel_type,
        "confidence": 0.9,
        "extraction_method": "snomed",
    }


def _add_inferred_site(
    entities: list[dict[str, Any]],
    by_concept: dict[str, int],
    neighbour: dict[str, str],
) -> int:
    cid = neighbour["id"]
    if cid in by_concept:
        return by_concept[cid]
    entity = {
        "text": _strip_fsn(neighbour["fsn"]),
        "label": "body_structure",
        "semantic_tag": "body_structure",
        "concept_id": cid,
        "term": neighbour["fsn"],
        "inferred": True,
        "inferred_from": "snomed",
        "assertion": "present",
    }
    entities.append(entity)
    idx = len(entities) - 1
    by_concept[cid] = idx
    return idx


def _fetch_related(concept_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not concept_ids:
        return {}
    from libs.terminology.client import TerminologyClient

    return TerminologyClient().batch_get_related(concept_ids)


def snomed_enrichment(
    state: SnomedEnrichState,
    fetch_related: RelatedFetcher | None = None,
) -> dict[str, Any]:
    """Add SNOMED candidate relations and inferred finding-site entities."""
    entities = deepcopy(list(state.get("entities") or []))
    errors = list(state.get("errors") or [])
    if not entities:
        return {"entities": [], "snomed_candidates": [], "errors": errors}

    by_concept: dict[str, int] = {}
    for idx, ent in enumerate(entities):
        cid = _concept_id(ent)
        if cid and cid not in by_concept:
            by_concept[cid] = idx
    if not by_concept:
        return {"entities": entities, "snomed_candidates": [], "errors": errors}

    fetcher = fetch_related or _fetch_related
    try:
        related_map = fetcher(list(by_concept.keys()))
    except Exception as exc:
        logger.warning("snomed_enrichment related fetch failed: %s", exc)
        errors.append(f"snomed_enrichment: {exc}")
        return {"entities": entities, "snomed_candidates": [], "errors": errors}

    candidates: list[dict[str, Any]] = []
    coded_indexes = list(by_concept.values())
    for src_idx in coded_indexes:
        cid = _concept_id(entities[src_idx])
        for neighbour in _flatten_related(related_map.get(cid) or {}):
            snomed_rel = neighbour["rel"]
            rel_type = _REL_TO_TYPE.get(snomed_rel)
            if not rel_type:
                continue
            tgt_idx = by_concept.get(neighbour["id"])
            if tgt_idx is None and snomed_rel in _SITE_RELS:
                tgt_idx = _add_inferred_site(entities, by_concept, neighbour)
            if tgt_idx is None:
                continue
            head_idx, tail_idx = _head_tail(src_idx, tgt_idx, snomed_rel)
            row = _append_candidate(entities, head_idx, tail_idx, rel_type, snomed_rel)
            if row:
                candidates.append(row)
    return {
        "entities": entities,
        "snomed_candidates": candidates,
        "errors": errors,
    }


def build_snomed_enrichment_subgraph() -> CompiledStateGraph:
    g = StateGraph(SnomedEnrichState)
    g.add_node("snomed_enrichment", snomed_enrichment)
    g.add_edge(START, "snomed_enrichment")
    g.add_edge("snomed_enrichment", END)
    return g.compile()
