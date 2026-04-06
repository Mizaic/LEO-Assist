"""Anchor detection subgraph."""

from __future__ import annotations

import copy
import json
import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from services.analysis_worker.app.analyzers.anchor_detector import (
    detect_anchors as detect_patient_anchors,
)

logger = logging.getLogger(__name__)


class AnchorState(TypedDict, total=False):
    patient_id: str
    org_id: str
    domain_id: str
    entities: list[dict[str, Any]]
    encounter_id: str
    encounter_date: str
    anchors: list[dict[str, Any]]
    anchor_result: dict[str, Any]
    errors: list[str]


_DOMAIN_VALUESET_QUERY = (
    "MATCH (d:AuditDomain {id: $domain_id})-[:HAS_SUBDOMAIN]->(v:ValueSet) "
    "RETURN v.id AS id, v.rawJson AS raw_json"
)

_FALLBACK_VALUESET_QUERY = (
    "MATCH (d:AuditDomain)-[:HAS_SUBDOMAIN]->(v:ValueSet) "
    "WHERE coalesce(d.episodeDetector, false) = true "
    "RETURN v.id AS id, v.rawJson AS raw_json, d.id AS domain_id"
)

_LEGACY_VALUESET_QUERY = (
    "MATCH (v:ValueSet) WHERE v.id STARTS WITH 'ncda-' "
    "RETURN v.id AS id, v.rawJson AS raw_json"
)


_ISA_DESCENDANTS_QUERY = (
    "MATCH (ancestor:Concept)<-[:IS_A*1..5]-(d:Concept) "
    "WHERE ancestor.id IN $ids AND d.active = true "
    "RETURN ancestor.id AS parent_id, d.id AS child_id, "
    "       coalesce(d.preferredTerm, d.id) AS display"
)


def _expand_valuesets_with_isa(kg, valuesets: dict) -> dict:
    """Expand each stored concept with its IS_A descendants from the KG.

    The UI stores only parent concepts (e.g. 'Malignant neoplastic disease').
    This materialises the full descendant set so the anchor detector's exact
    concept-ID match correctly captures all child variants.
    """
    parent_ids = [
        concept.get("code", "")
        for vs in valuesets.values()
        for include in (vs.get("compose") or {}).get("include") or []
        for concept in include.get("concept") or []
        if concept.get("code")
    ]
    if not parent_ids:
        return valuesets

    try:
        rows = kg.run(_ISA_DESCENDANTS_QUERY, ids=list(set(parent_ids)))
    except Exception:
        logger.warning("IS_A expansion query failed; using parent concepts only")
        return valuesets

    by_parent: dict[str, list[dict]] = {}
    for row in rows or []:
        pid = row.get("parent_id") or ""
        if pid:
            by_parent.setdefault(pid, []).append(
                {"code": row["child_id"], "display": row.get("display") or row["child_id"]}
            )

    total = sum(len(v) for v in by_parent.values())
    logger.info(
        "IS_A expansion: %d parent concept(s) -> %d descendant(s) added to buckets",
        len(by_parent),
        total,
    )

    enriched = copy.deepcopy(valuesets)
    for vs in enriched.values():
        for include in (vs.get("compose") or {}).get("include") or []:
            existing = include.get("concept") or []
            extras = [
                entry
                for concept in existing
                for entry in by_parent.get(concept.get("code", ""), [])
            ]
            include["concept"] = existing + extras
    return enriched


def _load_registry(domain_id: str = ""):
    """Load DomainRegistry from KG, scoped to a specific domain when provided.

    Resolution order:
    1. If domain_id given -- load only that domain's ValueSet subdomains.
    2. Else -- load all AuditDomain nodes flagged episodeDetector=true.
    3. Else (legacy) -- load all ncda-* ValueSet nodes.
    Raises RuntimeError when no ValueSets are found.

    IS_A expansion: for each concept in a ValueSet, all SNOMED descendants are
    fetched from the KG and injected before the registry is built, so the
    anchor detector's exact-match lookup covers the full hierarchy.
    """
    from libs.domain_config.registry import DomainRegistry
    from libs.neo4j_client.client import KnowledgeGraphClient

    kg = KnowledgeGraphClient()
    try:
        if domain_id:
            rows = kg.run(_DOMAIN_VALUESET_QUERY, domain_id=domain_id)
            source = f"domain '{domain_id}'"
        else:
            rows = kg.run(_FALLBACK_VALUESET_QUERY)
            if not rows:
                rows = kg.run(_LEGACY_VALUESET_QUERY)
                source = "all ncda-* ValueSets (legacy)"
            else:
                source = "all episode-detector AuditDomains"

        valuesets: dict = {}
        for r in rows or []:
            raw = r.get("raw_json")
            if not raw:
                continue
            try:
                valuesets[r["id"]] = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                pass

        if not valuesets:
            hint = f" for domain '{domain_id}'" if domain_id else ""
            raise RuntimeError(
                f"anchor_detect subgraph: no ValueSet nodes found{hint} in the knowledge "
                "graph. Seed the KG or mark an AuditDomain as episode detector before "
                "running episode detection."
            )

        valuesets = _expand_valuesets_with_isa(kg, valuesets)
    finally:
        kg.close()

    logger.info("Loaded %d ValueSets from %s", len(valuesets), source)
    return DomainRegistry.from_fhir(valuesets)


def _entity_rows(state: AnchorState) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entity in state.get("entities") or []:
        concept_id = (
            entity.get("concept_id")
            or entity.get("resolved_code")
            or entity.get("code")
            or (entity.get("coding") or {}).get("code")
        )
        rows.append(
            {
                "encounter_id": entity.get("encounter_id") or state.get("encounter_id") or "",
                "encounter_date": entity.get("encounter_date") or state.get("encounter_date") or "",
                "concept_id": concept_id,
                "concept_name": entity.get("concept_name") or entity.get("text") or entity.get("label") or "",
                "source": entity.get("source") or "pipeline",
                "confidence": entity.get("confidence", 1.0),
                "evidence": entity.get("evidence") or "",
                "assertion": entity.get("assertion") or "present",
            }
        )
    return rows


def _flatten_anchor_result(anchor_result) -> list[dict[str, Any]]:
    anchors: list[dict[str, Any]] = []
    for milestone_type, rows in (
        ("referral", anchor_result.referral_anchors),
        ("diagnosis", anchor_result.diagnosis_anchors),
        ("treatment_start", anchor_result.treatment_anchors),
        ("specialist_visit", anchor_result.specialist_visit_anchors),
        ("benign_closure", anchor_result.benign_closure_anchors),
    ):
        for row in rows:
            anchor = dict(row)
            anchor["milestone_type"] = milestone_type
            anchors.append(anchor)
    return anchors


def detect_anchors(state: AnchorState) -> dict[str, Any]:
    patient_id = state.get("patient_id") or ""
    domain_id = state.get("domain_id") or ""
    logger.info("Detecting anchors for patient %s (domain: %s)", patient_id, domain_id or "any")
    errors = list(state.get("errors") or [])

    try:
        registry = _load_registry(domain_id=domain_id)
    except RuntimeError as exc:
        logger.error("Cannot load DomainRegistry: %s", exc)
        return {"anchors": [], "anchor_result": {}, "errors": errors + [str(exc)]}

    try:
        entity_rows = _entity_rows(state)
        if entity_rows:
            class _Client:
                def run(self, *_args, **_kwargs):
                    return entity_rows

            anchor_result = detect_patient_anchors(
                patient_id=patient_id,
                start_date=str(state.get("window_start") or ""),
                end_date=str(state.get("window_end") or ""),
                patient_client=_Client(),
                registry=registry,
            )
        else:
            from libs.neo4j_client.client import PatientGraphClient

            client = PatientGraphClient()
            try:
                anchor_result = detect_patient_anchors(
                    patient_id=patient_id,
                    start_date=str(state.get("window_start") or ""),
                    end_date=str(state.get("window_end") or ""),
                    patient_client=client,
                    registry=registry,
                )
            finally:
                client.close()
        anchors = _flatten_anchor_result(anchor_result)
        return {
            "anchors": anchors,
            "anchor_result": {
                "referral_anchors": anchor_result.referral_anchors,
                "diagnosis_anchors": anchor_result.diagnosis_anchors,
                "treatment_anchors": anchor_result.treatment_anchors,
                "specialist_visit_anchors": anchor_result.specialist_visit_anchors,
                "benign_closure_anchors": anchor_result.benign_closure_anchors,
                "detection_method": anchor_result.detection_method,
                "expanded_start": anchor_result.expanded_start,
                "expanded_end": anchor_result.expanded_end,
            },
            "errors": errors + list(anchor_result.errors),
        }
    except Exception as exc:
        logger.exception("Anchor detection failed for patient %s", patient_id)
        return {"anchors": [], "anchor_result": {}, "errors": errors + [str(exc)]}


def build_anchor_subgraph() -> CompiledStateGraph:
    g = StateGraph(AnchorState)
    g.add_node("detect_anchors", detect_anchors)
    g.add_edge(START, "detect_anchors")
    g.add_edge("detect_anchors", END)
    return g.compile()
