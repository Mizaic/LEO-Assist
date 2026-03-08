"""FHIR PlanDefinition CRUD, version history, and $apply endpoints."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from libs.neo4j_client.client import KnowledgeGraphClient

router = APIRouter()


# ── Search ─────────────────────────────────────────────────────────────────────

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


# ── Single fetch ───────────────────────────────────────────────────────────────

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


# ── Version history ────────────────────────────────────────────────────────────

@router.get("/PlanDefinition/{plan_id}/_history")
def get_plan_definition_history(plan_id: str):
    """Return all published version snapshots for this pathway as a FHIR history Bundle."""
    client = KnowledgeGraphClient()
    try:
        plan_rows = client.run(
            "MATCH (pd:PlanDefinition {id: $pid}) RETURN pd.id AS id LIMIT 1",
            pid=plan_id,
        )
        if not plan_rows:
            raise HTTPException(404, f"PlanDefinition/{plan_id} not found")

        rows = client.run(
            "MATCH (pd:PlanDefinition {id: $pid})-[:HAS_VERSION]->(v:PlanDefinitionVersion) "
            "RETURN v.versionId AS versionId, v.rawJson AS rawJson, "
            "       v.publishedAt AS publishedAt, v.versionNotes AS versionNotes, "
            "       v.status AS status "
            "ORDER BY v.versionId DESC",
            pid=plan_id,
        )

        entries = []
        for r in rows:
            try:
                resource = json.loads(r["rawJson"])
            except Exception:
                resource = {"id": plan_id, "resourceType": "PlanDefinition"}

            resource["meta"] = {
                "versionId": str(r["versionId"]),
                "lastUpdated": r.get("publishedAt") or "",
                "versionNotes": r.get("versionNotes") or "",
            }
            entries.append({
                "fullUrl": f"PlanDefinition/{plan_id}/_history/{r['versionId']}",
                "resource": resource,
            })

        return {
            "resourceType": "Bundle",
            "type": "history",
            "total": len(entries),
            "entry": entries,
        }
    finally:
        client.close()


# ── Restore a previous version ─────────────────────────────────────────────────

@router.post("/PlanDefinition/{plan_id}/_restore/{version_id}")
def restore_plan_definition_version(plan_id: str, version_id: int):
    """Restore a previous published snapshot to live. Creates a new version entry."""
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            "MATCH (:PlanDefinition {id: $pid})-[:HAS_VERSION]->(v:PlanDefinitionVersion {versionId: $vid}) "
            "RETURN v.rawJson AS rawJson LIMIT 1",
            pid=plan_id, vid=version_id,
        )
        if not rows or not rows[0].get("rawJson"):
            raise HTTPException(404, f"Version {version_id} not found for PlanDefinition/{plan_id}")
        raw: Dict[str, Any] = json.loads(rows[0]["rawJson"])
    finally:
        client.close()

    # Publish the restored snapshot; this will create a new version entry in the history.
    raw["status"] = "active"
    raw["versionNotes"] = f"Rolled back to v{version_id}"
    return _save_plan_definition(plan_id, raw)


# ── Create (new pathway) ───────────────────────────────────────────────────────

@router.post("/PlanDefinition", status_code=201)
def create_plan_definition(resource: Dict[str, Any]):
    """Create a new PlanDefinition with a server-generated ID and return it."""
    new_id = str(uuid.uuid4())
    resource.setdefault("status", "draft")
    result = _save_plan_definition(new_id, resource)
    return {"id": new_id, **result}


# ── Upsert (create / update) ───────────────────────────────────────────────────

@router.put("/PlanDefinition/{plan_id}")
def upsert_plan_definition(plan_id: str, resource: Dict[str, Any]):
    return _save_plan_definition(plan_id, resource)


def _save_plan_definition(plan_id: str, resource: Dict[str, Any]) -> Dict[str, Any]:
    resource["id"] = plan_id
    resource.setdefault("resourceType", "PlanDefinition")

    # Pull version notes out before they pollute rawJson.
    version_notes: str = resource.pop("versionNotes", "") or ""
    if not version_notes and isinstance(resource.get("meta"), dict):
        version_notes = resource["meta"].pop("versionNotes", "") or ""

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
        # 1. Upsert the live node (MERGE ensures the node exists before we link versions).
        #    source='user' marks this as user-authored so the seed script won't overwrite it.
        client.run(
            "MERGE (pd:PlanDefinition {id: $pid}) "
            "SET pd.rawJson = $raw, pd.status = $status, "
            "    pd.name = $name, pd.isGlobal = true, pd.source = 'user'",
            pid=plan_id,
            raw=json.dumps(resource),
            status=resource.get("status"),
            name=resource.get("name"),
        )

        # 2. When publishing to active, snapshot the current state as an immutable version.
        if resource.get("status") == "active":
            ver_rows = client.run(
                "MATCH (pd:PlanDefinition {id: $pid})-[:HAS_VERSION]->(v:PlanDefinitionVersion) "
                "RETURN coalesce(max(v.versionId), 0) AS max_ver",
                pid=plan_id,
            )
            next_ver = (ver_rows[0]["max_ver"] or 0) + 1 if ver_rows else 1
            now = datetime.now(timezone.utc).isoformat()
            client.run(
                "MATCH (pd:PlanDefinition {id: $pid}) "
                "CREATE (pd)-[:HAS_VERSION]->(v:PlanDefinitionVersion {"
                "  id: $vid, planId: $pid, versionId: $ver, "
                "  status: 'active', rawJson: $raw, "
                "  publishedAt: $now, versionNotes: $notes "
                "})",
                pid=plan_id,
                vid=str(uuid.uuid4()),
                ver=next_ver,
                raw=json.dumps(resource),
                now=now,
                notes=version_notes,
            )

        # 3. Rebuild the action graph.
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


# ── Delete ─────────────────────────────────────────────────────────────────────

@router.delete("/PlanDefinition/{plan_id}", status_code=204)
def delete_plan_definition(plan_id: str):
    client = KnowledgeGraphClient()
    try:
        client.run(
            "MATCH (pd:PlanDefinition {id: $pid}) "
            "OPTIONAL MATCH (pd)-[:HAS_ACTION]->(a:Action) "
            "OPTIONAL MATCH (pd)-[:HAS_VERSION]->(v:PlanDefinitionVersion) "
            "DETACH DELETE a, v, pd",
            pid=plan_id,
        )
    finally:
        client.close()


# ── $apply ─────────────────────────────────────────────────────────────────────

@router.post("/PlanDefinition/{plan_id}/$apply")
def apply_plan_definition(plan_id: str, body: Dict[str, Any]):
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


# ── Internal helpers ───────────────────────────────────────────────────────────

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
    related_edges = [
        {
            "actionId": rel.get("actionId", ""),
            "relationship": rel.get("relationship", "after-end"),
            "sourceHandle": rel.get("sourceHandle"),
            "targetHandle": rel.get("targetHandle"),
        }
        for rel in related_defs
    ]

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
        client.run(
            "MATCH (a:Action {id: $aid}) "
            "MATCH (ad:ActivityDefinition {id: $adid}) "
            "MERGE (a)-[:USES_DEFINITION]->(ad)",
            aid=action_id, adid=activity_id,
        )
