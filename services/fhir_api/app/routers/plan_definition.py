"""FHIR PlanDefinition CRUD, version history, and $apply endpoints."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from libs.neo4j_client.client import KnowledgeGraphClient

router = APIRouter()


def _normalize_plan_resource(resource: Dict[str, Any], source: str) -> Dict[str, Any]:
    normalized = dict(resource)
    meta = normalized.get("meta")
    if not isinstance(meta, dict):
        meta = {}
    else:
        meta = dict(meta)
    if source == "seed":
        meta["seeded"] = True
    normalized["meta"] = meta
    normalized["source"] = source
    return normalized


def _load_plan_record(client: KnowledgeGraphClient, plan_id: str) -> Optional[Dict[str, Any]]:
    rows = client.run(
        "MATCH (pd:PlanDefinition {id: $pid}) "
        "RETURN pd.rawJson AS rawJson, coalesce(pd.source, 'user') AS source LIMIT 1",
        pid=plan_id,
    )
    if not rows or not rows[0].get("rawJson"):
        return None
    return _normalize_plan_resource(
        json.loads(rows[0]["rawJson"]),
        rows[0].get("source") or "user",
    )


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
            "RETURN pd.rawJson AS rawJson, coalesce(pd.source, 'user') AS source "
            "ORDER BY pd.name "
            "SKIP $offset LIMIT $limit",
            status=status, offset=_offset, limit=_count,
        )
        items = [
            _normalize_plan_resource(json.loads(r["rawJson"]), r.get("source") or "user")
            for r in rows
            if r.get("rawJson")
        ]
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
        resource = _load_plan_record(client, plan_id)
        if not resource:
            raise HTTPException(404, f"PlanDefinition/{plan_id} not found")
        return resource
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
    resource = dict(resource)
    resource.pop("source", None)
    resource["id"] = plan_id
    resource.setdefault("resourceType", "PlanDefinition")
    meta = resource.get("meta")
    if not isinstance(meta, dict):
        meta = {}
    else:
        meta = dict(meta)
    resource["meta"] = meta

    # Pull version notes out before they pollute rawJson.
    version_notes: str = resource.pop("versionNotes", "") or ""
    if not version_notes:
        version_notes = meta.pop("versionNotes", "") or ""

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
        source_rows = client.run(
            "MATCH (pd:PlanDefinition {id: $pid}) "
            "RETURN coalesce(pd.source, 'user') AS source LIMIT 1",
            pid=plan_id,
        )
        existing_source = source_rows[0].get("source") if source_rows else None
        source = "seed" if existing_source == "seed" else "user"
        if source == "seed":
            meta["seeded"] = True
        else:
            meta.pop("seeded", None)
            meta.pop("seededBy", None)
            if not meta:
                resource.pop("meta", None)

        # 1. Upsert the live node (MERGE ensures the node exists before we link versions).
        #    Preserve source='seed' for built-in pathways so UI delete protections remain intact.
        client.run(
            "MERGE (pd:PlanDefinition {id: $pid}) "
            "SET pd.rawJson = $raw, pd.status = $status, "
            "    pd.name = $name, pd.isGlobal = true, pd.source = $source",
            pid=plan_id,
            raw=json.dumps(resource),
            status=resource.get("status"),
            name=resource.get("name"),
            source=source,
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

        return _normalize_plan_resource(resource, source)
    finally:
        client.close()


# ── Delete ─────────────────────────────────────────────────────────────────────

@router.delete("/PlanDefinition/{plan_id}", status_code=204)
def delete_plan_definition(plan_id: str):
    client = KnowledgeGraphClient()
    try:
        resource = _load_plan_record(client, plan_id)
        if not resource:
            raise HTTPException(404, f"PlanDefinition/{plan_id} not found")
        if resource.get("source") == "seed" or bool((resource.get("meta") or {}).get("seeded")):
            raise HTTPException(403, "Seeded pathways cannot be deleted from the UI.")
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
            "WHERE a.trigger_name = $evt "
            "  AND coalesce(a.trigger_type, 'data-changed') IN ['data-changed', 'admin-action'] "
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
    # canvas_id is the user-defined node ID (e.g. "step_extract").  It is only
    # unique *within* a plan; across plans it can collide.  We therefore store
    # Action nodes in Neo4j with a plan-scoped composite id
    # ("{plan_id}__{canvas_id}") so the global uniqueness constraint is never
    # violated, while keeping canvas_id as a queryable property so the
    # WorkflowEngine can look actions up by their original ID.
    canvas_id = action.get("id", "")
    scoped_id = f"{plan_id}__{canvas_id}"

    trigger = (action.get("trigger") or [{}])[0]
    trigger_type = trigger.get("type", "")
    trigger_name = trigger.get("name", "")
    if isinstance(trigger_name, list):
        trigger_name = trigger_name[0] if trigger_name else ""
    elif not isinstance(trigger_name, str):
        trigger_name = str(trigger_name) if trigger_name else ""

    definition_ref = action.get("definitionCanonical") or action.get("definitionUri", "")
    related_defs = action.get("relatedAction") or []
    related_ids = [r.get("actionId", "") for r in related_defs]
    # Store the original canvas-level actionId values in relatedActionEdges so
    # the engine can resolve them against canvas_id at runtime.
    related_edges = [
        {
            "actionId": rel.get("actionId", ""),
            "relationship": rel.get("relationship", "after-end"),
            "sourceHandle": rel.get("sourceHandle"),
            "targetHandle": rel.get("targetHandle"),
        }
        for rel in related_defs
    ]

    condition_expr = None
    if action.get("condition"):
        cond_list = action["condition"]
        if isinstance(cond_list, list) and cond_list:
            condition_expr = (
                cond_list[0].get("expression", {}).get("expression")
                if isinstance(cond_list[0], dict)
                else None
            )

    # MERGE on the scoped id — safe to re-run on every save without
    # violating the uniqueness constraint, and isolated from other plans.
    client.run(
        "MATCH (pd:PlanDefinition {id: $pid}) "
        "MERGE (a:Action {id: $scoped_id}) "
        "SET a.canvas_id = $canvas_id, "
        "    a.trigger_type = $tt, a.trigger_name = $tn, "
        "    a.condition = $cond, a.sequence = $seq, a.subgraphId = $sgid, "
        "    a.nodeType = $ntype, a.relatedActions = $related, "
        "    a.relatedActionEdges = $related_edges "
        "MERGE (pd)-[:HAS_ACTION]->(a)",
        pid=plan_id,
        scoped_id=scoped_id,
        canvas_id=canvas_id,
        tt=trigger_type,
        tn=trigger_name,
        cond=condition_expr,
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
        # Link via scoped id so the correct Action node is matched.
        client.run(
            "MATCH (a:Action {id: $scoped_id}) "
            "MATCH (ad:ActivityDefinition {id: $adid}) "
            "MERGE (a)-[:USES_DEFINITION]->(ad)",
            scoped_id=scoped_id, adid=activity_id,
        )
