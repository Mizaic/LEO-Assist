"""Admin -- Workflow Builder endpoints.

Exposes CRUD over Workflow nodes and their Step/HumanInTheLoop graphs stored
in Neo4j.  All endpoints require platform admin.

Neo4j schema:
  (Service)-[:HAS_WORKFLOW]->(Workflow)
  (Service)-[:PROVIDES_SERVICE_FOR]->(Organization)
  (Workflow)-[:STARTS_AT]->(Step|HumanInTheLoop)
  (Step)-[:CREATES_DATA_FOR]->(Workflow)
  (Step|HumanInTheLoop)-[:NEXT_STEP {condition}]->(Step|HumanInTheLoop)
  Ambient agents on this workflow (STARTS_AT path or CREATES_DATA_FOR).
  Scheduler on the canvas is derived (Service.interval + ambient
  intervals), not a Neo4j label.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.deps import require_admin
from app.services import workflow_graph_cypher as cy
from app.services.workflow_graph_map import (
    build_context_edges,
    build_context_nodes,
    is_context_kind,
    kind_from_labels,
    node_data_from_props,
    node_props,
    step_write_params,
)
from libs.auth.org_scope import CallerScope
from libs.neo4j_client.client import PatientGraphClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/workflows", tags=["admin-workflows"])

# -- Helpers ----------------------------------------------------------------


def _client() -> PatientGraphClient:
    return PatientGraphClient()


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Convert a Neo4j Record to a plain dict."""
    return dict(row)


def serialise_workflow_row(row: Any) -> dict[str, Any]:
    """Map a Neo4j list row to the camelCase contract the UI reads."""
    data = dict(row) if not isinstance(row, dict) else row
    wf_id = str(data.get("id") or "")
    raw_name = str(data.get("name") or "").strip()
    service_name = str(data.get("service_name") or "").strip()
    return {
        "id": wf_id,
        "name": raw_name or service_name or wf_id or "Untitled workflow",
        "serviceId": str(data.get("service_id") or ""),
        "serviceName": service_name,
        "createdAt": str(data.get("created_at") or ""),
        "stepCount": int(data.get("step_count") or 0),
        "humanCount": int(data.get("human_count") or 0),
    }


def _record_kind(item: Any) -> str:
    data = item.get("data") if isinstance(item, dict) else getattr(item, "data", None)
    if isinstance(data, dict):
        return str(data.get("kind") or "")
    return str(getattr(data, "kind", "") or "")


def _record_id(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("id") or "")
    return str(getattr(item, "id", "") or "")


def _record_end(item: Any, key: str) -> str:
    if isinstance(item, dict):
        return str(item.get(key) or "")
    return str(getattr(item, key, "") or "")


def filter_saveable_nodes(nodes: list[Any]) -> list[Any]:
    """Drop Start and read-only context nodes before a graph write."""
    kept: list[Any] = []
    for node in nodes:
        if _record_id(node) == "__start__":
            continue
        if is_context_kind(_record_kind(node)):
            continue
        kept.append(node)
    return kept


def filter_saveable_edges(edges: list[Any], saveable_ids: set[str]) -> list[Any]:
    """Keep only Start and step edges. Context links are display-only."""
    allowed = set(saveable_ids) | {"__start__"}
    kept: list[Any] = []
    for edge in edges:
        source = _record_end(edge, "source")
        target = _record_end(edge, "target")
        if source in allowed and target in allowed:
            kept.append(edge)
    return kept


def load_context_nodes(
    client: PatientGraphClient, workflow_id: str
) -> list[dict[str, Any]]:
    """Load Service, Organisation, and derived Scheduler canvas nodes."""
    rows = client.run(cy.GET_GRAPH_CONTEXT, id=workflow_id)
    if not rows:
        return []
    data = _row_to_dict(rows[0])
    service = node_props(data.get("s")) or None
    organisation = node_props(data.get("org")) or None
    ambients = [node_props(item) for item in (data.get("ambients") or []) if item]
    return build_context_nodes(service, organisation, ambients)


# -- Request / response models ----------------------------------------------


class CreateWorkflowBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    service_id: str = Field(default="", alias="serviceId")


class NodePosition(BaseModel):
    x: float
    y: float


class NodeData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    agent_type: str = Field(alias="agentType")
    label: str
    kind: str  # "agent" | "human" | "ambient"
    interval: Optional[int] = None
    always_trigger: Optional[bool] = Field(default=False, alias="alwaysTrigger")
    status_on_ready: Optional[str] = Field(default="", alias="statusOnReady")
    default_on_hitl: Optional[bool] = Field(default=False, alias="defaultOnHitl")
    description: Optional[str] = ""
    enabled: Optional[bool] = True
    status: Optional[str] = ""
    enable_date: Optional[str] = Field(default="", alias="enableDate")


class GraphNode(BaseModel):
    id: str
    type: str
    position: NodePosition
    data: NodeData


class EdgeData(BaseModel):
    condition: Optional[str] = ""


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    data: Optional[EdgeData] = None


class SaveGraphBody(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


# -- Endpoints --------------------------------------------------------------


@router.get("")
def list_workflows(
    scope: CallerScope = Depends(require_admin),
) -> list[dict[str, Any]]:
    """Return all workflows with step counts and service info."""
    client = _client()
    try:
        rows = client.run(cy.LIST_WORKFLOWS)
        return [serialise_workflow_row(r) for r in rows]
    except Exception as exc:
        logger.exception("list_workflows failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("", status_code=201)
def create_workflow(
    body: CreateWorkflowBody,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Create a new Workflow node and optionally link it to a Service."""
    client = _client()
    wf_id = str(uuid.uuid4())
    try:
        rows = client.run(cy.CREATE_WORKFLOW, id=wf_id, name=body.name.strip())
        if not rows:
            raise HTTPException(status_code=500, detail="Workflow node not created")
        created = _row_to_dict(rows[0])
        created.setdefault("service_id", "")
        created.setdefault("service_name", "")
        created.setdefault("step_count", 0)
        created.setdefault("human_count", 0)
        if body.service_id:
            try:
                client.run(
                    cy.LINK_WORKFLOW_TO_SERVICE,
                    workflow_id=wf_id,
                    service_id=body.service_id,
                )
                created["service_id"] = body.service_id
            except Exception:
                logger.warning(
                    "Could not link workflow %s to service %s",
                    wf_id,
                    body.service_id,
                )
        return serialise_workflow_row(created)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("create_workflow failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/{workflow_id}", status_code=204)
def delete_workflow(
    workflow_id: str,
    scope: CallerScope = Depends(require_admin),
) -> None:
    """Delete a workflow and all its Step / HumanInTheLoop nodes."""
    client = _client()
    try:
        client.run(cy.DELETE_WORKFLOW, id=workflow_id)
    except Exception as exc:
        logger.exception("delete_workflow failed for %s", workflow_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{workflow_id}/graph")
def get_workflow_graph(
    workflow_id: str,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    """Return the React Flow graph (nodes + edges) for a workflow."""
    client = _client()
    try:
        meta_rows = client.run(cy.GET_WORKFLOW_META, id=workflow_id)
        if not meta_rows:
            raise HTTPException(status_code=404, detail="Workflow not found")
        meta = _row_to_dict(meta_rows[0])

        node_rows = client.run(cy.GET_GRAPH_NODES, id=workflow_id)
        edge_rows = client.run(cy.GET_GRAPH_EDGES, id=workflow_id)
        start_rows = client.run(cy.GET_START_EDGE, id=workflow_id)
        context_nodes = load_context_nodes(client, workflow_id)

        rf_nodes = context_nodes + build_rf_nodes(node_rows)
        rf_edges = build_context_edges(context_nodes) + build_rf_edges(
            start_rows=start_rows, edge_rows=edge_rows
        )

        return {
            "workflowId": workflow_id,
            "workflowName": meta["name"],
            "serviceId": meta["service_id"],
            "nodes": rf_nodes,
            "edges": rf_edges,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("get_workflow_graph failed for %s", workflow_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/{workflow_id}/graph", status_code=204)
def save_workflow_graph(
    workflow_id: str,
    body: SaveGraphBody,
    scope: CallerScope = Depends(require_admin),
) -> None:
    """Replace Step / HITL nodes. Context nodes are never written."""
    client = _client()
    try:
        step_nodes = filter_saveable_nodes(body.nodes)
        saveable_ids = {_record_id(node) for node in step_nodes}
        step_edges = filter_saveable_edges(body.edges, saveable_ids)
        client.run(cy.REPLACE_GRAPH, workflow_id=workflow_id)
        for node in step_nodes:
            _write_step_node(client, node)
        _write_step_edges(client, workflow_id, step_edges)
    except Exception as exc:
        logger.exception("save_workflow_graph failed for %s", workflow_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _write_step_node(client: PatientGraphClient, node: GraphNode) -> None:
    params = step_write_params(
        node_id=node.id,
        label=node.data.label,
        agent_type=node.data.agent_type,
        canvas_x=node.position.x,
        canvas_y=node.position.y,
        interval=node.data.interval,
        always_trigger=bool(node.data.always_trigger),
        status_on_ready=node.data.status_on_ready or "",
        default_on_hitl=bool(node.data.default_on_hitl),
        description=node.data.description or "",
        enabled=bool(node.data.enabled),
        status=node.data.status or "",
    )
    if node.data.kind == "human":
        client.run(cy.SAVE_HUMAN, **params)
        return
    client.run(cy.SAVE_STEP, **params)
    if node.data.kind == "ambient":
        client.run(cy.SET_AMBIENT_LABELS, id=node.id)
        return
    client.run(cy.SET_AGENT_LABELS, id=node.id)


def _edge_condition(edge: GraphEdge) -> str:
    return (edge.data.condition if edge.data else "") or ""


def _write_step_edges(
    client: PatientGraphClient,
    workflow_id: str,
    edges: list[GraphEdge],
) -> None:
    for edge in edges:
        if edge.source == "__start__":
            client.run(
                cy.LINK_STARTS_AT,
                workflow_id=workflow_id,
                node_id=edge.target,
                condition=_edge_condition(edge),
            )
            continue
        client.run(
            cy.LINK_NEXT_STEP,
            source_id=edge.source,
            target_id=edge.target,
            condition=_edge_condition(edge),
        )


# -- Graph builder helpers --------------------------------------------------


def _row_get(row: Any, key: str, default: Any = "") -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, TypeError):
        return default


def build_rf_edges(
    *,
    start_target: str | None = None,
    start_rows: list[Any] | None = None,
    edge_rows: list[Any],
) -> list[dict[str, Any]]:
    """Build React Flow edges with unique ids (same pair can appear twice)."""
    edges: list[dict[str, Any]] = []
    starts = list(start_rows or [])
    if start_target and not starts:
        starts = [{"target_id": start_target, "condition": ""}]
    for index, row in enumerate(starts):
        target = _row_get(row, "target_id")
        if not target:
            continue
        edges.append(
            {
                "id": f"e-start-{target}-{index}",
                "source": "__start__",
                "target": target,
                "data": {"condition": _row_get(row, "condition") or ""},
            }
        )
    seen: set[str] = {e["id"] for e in edges}
    for index, row in enumerate(edge_rows):
        source = _row_get(row, "source")
        target = _row_get(row, "target")
        if not source or not target:
            continue
        rel_id = str(_row_get(row, "rel_id") or "")
        edge_id = f"e-{rel_id}" if rel_id else f"e-{source}-{target}-{index}"
        if edge_id in seen:
            edge_id = f"{edge_id}-{index}"
        seen.add(edge_id)
        edges.append(
            {
                "id": edge_id,
                "source": source,
                "target": target,
                "data": {"condition": _row_get(row, "condition") or ""},
            }
        )
    return edges


def build_rf_nodes(node_rows: list[Any]) -> list[dict[str, Any]]:
    """Start sentinel plus one React Flow node per step id."""
    nodes = _build_start_node()
    seen = {"__start__"}
    for row in node_rows:
        if _row_get(row, "n") is None:
            continue
        node = _neo4j_node_to_rf(row)
        node_id = node["id"]
        if node_id in seen:
            continue
        seen.add(node_id)
        nodes.append(node)
    return nodes


def _build_start_node() -> list[dict[str, Any]]:
    return [
        {
            "id": "__start__",
            "type": "start",
            "position": {"x": 200, "y": 40},
            "data": {"agentType": "__start__", "label": "Start", "kind": "agent"},
            "deletable": False,
        }
    ]


def _neo4j_node_to_rf(row: Any) -> dict[str, Any]:
    raw = _row_get(row, "n")
    props = dict(raw) if raw is not None else {}
    labels = list(_row_get(row, "node_labels") or [])
    kind = kind_from_labels(labels) if labels else str(_row_get(row, "kind") or "agent")
    return {
        "id": props.get("id", str(uuid.uuid4())),
        "type": kind,
        "position": {
            "x": float(_row_get(row, "pos_x") or 200.0),
            "y": float(_row_get(row, "pos_y") or 200.0),
        },
        "data": node_data_from_props(props, kind=kind),
    }
