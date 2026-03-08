"""FHIR PlanDefinition CRUD and $apply endpoints."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from libs.neo4j_client.client import KnowledgeGraphClient

router = APIRouter()


@router.get("/PlanDefinition")
def search_plan_definitions(
    name: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    _count: int = Query(default=100, alias="_count"),
    _offset: int = Query(default=0, alias="_offset"),
):
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            "MATCH (pd:PlanDefinition) "
            "WHERE ($status IS NULL OR pd.status = $status) "
            "RETURN pd.rawJson AS rawJson "
            "ORDER BY pd.name "
            "SKIP $offset LIMIT $limit",
            status=status, offset=_offset, limit=_count,
        )
        items = [json.loads(r["rawJson"]) for r in rows if r.get("rawJson")]
        if name:
            items = [p for p in items if name.lower() in (p.get("name") or "").lower()]
        total_rows = client.run(
            "MATCH (pd:PlanDefinition) "
            "WHERE ($status IS NULL OR pd.status = $status) "
            "RETURN count(pd) AS total",
            status=status,
        )
        total = total_rows[0]["total"] if total_rows else len(items)
        return {
            "resourceType": "Bundle",
            "type": "searchset",
            "total": total,
            "entry": [{"resource": p} for p in items],
        }
    finally:
        client.close()


@router.get("/PlanDefinition/{plan_id}")
def get_plan_definition(plan_id: str):
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            "MATCH (pd:PlanDefinition {id: $pid}) RETURN pd.rawJson AS rawJson LIMIT 1",
            pid=plan_id,
        )
        if not rows or not rows[0].get("rawJson"):
            raise HTTPException(404, f"PlanDefinition/{plan_id} not found")
        return json.loads(rows[0]["rawJson"])
    finally:
        client.close()


@router.put("/PlanDefinition/{plan_id}")
def upsert_plan_definition(plan_id: str, resource: Dict[str, Any]):
    resource["id"] = plan_id
    resource.setdefault("resourceType", "PlanDefinition")

    ui_actions = resource.get("actions")
    fhir_actions: List[Dict[str, Any]] = resource.get("action", [])

    if ui_actions is not None and not fhir_actions:
        fhir_actions = _ui_actions_to_fhir(
            ui_actions,
            resource.get("edges", []),
            resource.get("trigger"),
        )

    client = KnowledgeGraphClient()
    try:
        client.run(
            "MERGE (pd:PlanDefinition {id: $pid}) "
            "SET pd.rawJson = $raw, pd.status = $status, "
            "    pd.name = $name, pd.isGlobal = true",
            pid=plan_id,
            raw=json.dumps(resource),
            status=resource.get("status"),
            name=resource.get("name"),
        )
        client.run(
            "MATCH (pd:PlanDefinition {id: $pid})-[r:HAS_ACTION]->(a:Action) "
            "DETACH DELETE a",
            pid=plan_id,
        )
        for action in fhir_actions:
            _upsert_action(client, plan_id, action)
        return resource
    finally:
        client.close()


def _ui_actions_to_fhir(
    ui_actions: List[Dict[str, Any]],
    ui_edges: List[Dict[str, Any]],
    plan_trigger: Dict[str, Any] | None,
) -> List[Dict[str, Any]]:
    """Convert UI pathway-builder actions/edges to FHIR action array for graph storage."""
    edge_lookup: Dict[str, Dict[str, Any]] = {}
    for e in ui_edges:
        target_id = e.get("target")
        if not target_id:
            continue
        edge_lookup[target_id] = {
            "source": e.get("source", ""),
            "sourceHandle": e.get("sourceHandle"),
            "targetHandle": e.get("targetHandle"),
        }

    fhir_actions = []
    for i, ua in enumerate(ui_actions):
        action_id = ua["id"]
        config = ua.get("config") or {}
        definition_id = f"{action_id}-config"
        act: Dict[str, Any] = {
            "id": action_id,
            "title": ua.get("label", ua.get("subgraphId", "")),
            "_sequence": i,
            "_subgraphId": ua.get("subgraphId", ""),
            "_nodeType": ua.get("nodeType", "action"),
            "definitionCanonical": f"ActivityDefinition/{definition_id}",
            "_dynamicValues": config,
        }
        source_edge = edge_lookup.get(action_id)
        if source_edge and source_edge.get("source"):
            rel: Dict[str, Any] = {
                "actionId": source_edge["source"],
                "relationship": "after-end",
            }
            if source_edge.get("sourceHandle"):
                rel["sourceHandle"] = source_edge["sourceHandle"]
            if source_edge.get("targetHandle"):
                rel["targetHandle"] = source_edge["targetHandle"]
            act["relatedAction"] = [rel]
        if i == 0 and plan_trigger:
            trigger_name = plan_trigger.get("event", "")
            trigger_type = plan_trigger.get("type", "data-changed")
            if trigger_name:
                act["trigger"] = [{"type": trigger_type, "name": trigger_name}]
        fhir_actions.append(act)
    return fhir_actions


@router.delete("/PlanDefinition/{plan_id}", status_code=204)
def delete_plan_definition(plan_id: str):
    client = KnowledgeGraphClient()
    try:
        client.run(
            "MATCH (pd:PlanDefinition {id: $pid}) "
            "OPTIONAL MATCH (pd)-[:HAS_ACTION]->(a:Action) "
            "DETACH DELETE a, pd",
            pid=plan_id,
        )
    finally:
        client.close()


@router.post("/PlanDefinition/{plan_id}/$apply")
def apply_plan_definition(
    plan_id: str,
    body: Dict[str, Any],
):
    """Evaluate which actions should trigger for a patient given the current event."""
    event_type = body.get("event_type", "")
    patient_id = body.get("patient_id", "")
    if not event_type or not patient_id:
        raise HTTPException(400, "event_type and patient_id are required")

    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            "MATCH (pd:PlanDefinition {id: $pid}) RETURN pd.status AS status LIMIT 1",
            pid=plan_id,
        )
        if not rows:
            raise HTTPException(404, f"PlanDefinition/{plan_id} not found")
        if rows[0].get("status") != "active":
            raise HTTPException(409, "PlanDefinition is not active")

        action_rows = client.run(
            "MATCH (pd:PlanDefinition {id: $pid})-[:HAS_ACTION]->(a:Action) "
            "WHERE a.trigger_type = 'data-changed' AND a.trigger_name = $evt "
            "OPTIONAL MATCH (a)-[:USES_DEFINITION]->(ad:ActivityDefinition) "
            "RETURN a.id AS actionId, a.trigger_type AS triggerType, "
            "       a.trigger_name AS triggerName, a.condition AS condition, "
            "       ad.subgraphId AS subgraphId, ad.id AS activityId "
            "ORDER BY a.sequence",
            pid=plan_id, evt=event_type,
        )
        matched = [
            {
                "actionId": r["actionId"],
                "triggerType": r["triggerType"],
                "triggerName": r["triggerName"],
                "condition": r.get("condition"),
                "subgraphId": r.get("subgraphId"),
                "activityDefinitionId": r.get("activityId"),
            }
            for r in action_rows
        ]
        return {
            "resourceType": "Parameters",
            "parameter": [
                {"name": "planDefinitionId", "valueString": plan_id},
                {"name": "patientId", "valueString": patient_id},
                {"name": "matchedActions", "valueInteger": len(matched)},
                {"name": "actions", "resource": matched},
            ],
        }
    finally:
        client.close()


def _upsert_action(client: KnowledgeGraphClient, plan_id: str, action: Dict[str, Any]) -> None:
    action_id = action.get("id", "")
    trigger = (action.get("trigger") or [{}])[0]
    trigger_type = trigger.get("type", "")
    trigger_name = (trigger.get("name") or trigger.get("event", [None])
                    if isinstance(trigger.get("name"), str)
                    else trigger.get("name", ""))
    if isinstance(trigger_name, list):
        trigger_name = trigger_name[0] if trigger_name else ""

    definition_ref = action.get("definitionCanonical") or action.get("definitionUri", "")
    related_defs = action.get("relatedAction") or []
    related_ids = [r.get("actionId", "") for r in related_defs]
    related_edges = []
    for rel in related_defs:
        related_edges.append(
            {
                "actionId": rel.get("actionId", ""),
                "relationship": rel.get("relationship", "after-end"),
                "sourceHandle": rel.get("sourceHandle"),
                "targetHandle": rel.get("targetHandle"),
            }
        )

    client.run(
        "MATCH (pd:PlanDefinition {id: $pid}) "
        "CREATE (pd)-[:HAS_ACTION]->(a:Action {"
        "  id: $aid, trigger_type: $tt, trigger_name: $tn, "
        "  condition: $cond, sequence: $seq, subgraphId: $sgid, "
        "  nodeType: $ntype, relatedActions: $related, relatedActionEdges: $related_edges"
        "}) ",
        pid=plan_id,
        aid=action_id,
        tt=trigger_type,
        tn=trigger_name,
        cond=action.get("condition", [{}])[0].get("expression", {}).get("expression") if action.get("condition") else None,
        seq=action.get("_sequence", 0),
        sgid=action.get("_subgraphId", ""),
        ntype=action.get("_nodeType", "action"),
        related=related_ids,
        related_edges=json.dumps(related_edges),
    )

    if definition_ref:
        activity_id = definition_ref.split("/")[-1]
        dynamic_values = action.get("_dynamicValues") or {}
        client.run(
            "MERGE (ad:ActivityDefinition {id: $adid}) "
            "SET ad.subgraphId = $sgid, ad.dynamicValues = $dvals, ad.rawJson = $raw, "
            "    ad.name = coalesce(ad.name, $adid), ad.status = coalesce(ad.status, 'active')",
            adid=activity_id,
            sgid=action.get("_subgraphId", ""),
            dvals=json.dumps(dynamic_values),
            raw=json.dumps(
                {
                    "resourceType": "ActivityDefinition",
                    "id": activity_id,
                    "status": "active",
                    "subgraphId": action.get("_subgraphId", ""),
                    "dynamicValues": dynamic_values,
                }
            ),
        )

    if definition_ref:
        activity_id = definition_ref.split("/")[-1]
        client.run(
            "MATCH (a:Action {id: $aid}) "
            "MATCH (ad:ActivityDefinition {id: $adid}) "
            "MERGE (a)-[:USES_DEFINITION]->(ad)",
            aid=action_id, adid=activity_id,
        )
