"""Map Neo4j workflow node/edge properties to the canvas contract.

Onboarding writes camelCase (statusOnReady, alwaysTrigger). Early builder
writes used snake_case. Read both. Write camelCase so agents still see
the keys they already query.
"""

from __future__ import annotations

from typing import Any

CONTEXT_KINDS = frozenset({"service", "organisation", "scheduler"})
SERVICE_ATTR_KEYS = (
    "id",
    "name",
    "ers_service_id",
    "clinicalType",
    "interval",
    "enableDate",
    "directlyBookable",
    "enabled",
    "status",
)
ORG_ATTR_KEYS = ("id", "name", "odsCode")


def is_context_kind(kind: str | None) -> bool:
    return (kind or "") in CONTEXT_KINDS


def kind_from_labels(labels: list[str] | None) -> str:
    names = set(labels or [])
    if "HumanInTheLoop" in names:
        return "human"
    if "AmbientAgent" in names:
        return "ambient"
    return "agent"


def _pick(props: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in props and props[key] is not None:
            return props[key]
    return default


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def node_data_from_props(props: dict[str, Any], *, kind: str) -> dict[str, Any]:
    """Flatten a Step / HumanInTheLoop property map for React Flow."""
    return {
        "agentType": _as_text(_pick(props, "type")),
        "label": _as_text(_pick(props, "name")),
        "kind": kind,
        "interval": _as_int(_pick(props, "interval")),
        "alwaysTrigger": bool(
            _pick(props, "alwaysTrigger", "always_trigger", default=False)
        ),
        "statusOnReady": _as_text(
            _pick(props, "statusOnReady", "status_on_ready", default="")
        ),
        "defaultOnHitl": bool(
            _pick(props, "defaultOnHitl", "default_on_hitl", default=False)
        ),
        "description": _as_text(_pick(props, "description")),
        "enabled": bool(_pick(props, "enabled", default=True)),
        "status": _as_text(_pick(props, "status")),
        "enableDate": _as_text(_pick(props, "enableDate")),
    }


def step_write_params(
    *,
    node_id: str,
    label: str,
    agent_type: str,
    canvas_x: float,
    canvas_y: float,
    interval: int | None,
    always_trigger: bool,
    status_on_ready: str,
    default_on_hitl: bool,
    description: str,
    enabled: bool,
    status: str,
) -> dict[str, Any]:
    """Params for MERGE/SET using the onboarding property names."""
    return {
        "id": node_id,
        "type": agent_type,
        "name": label,
        "interval": interval if interval is not None else 9999,
        "alwaysTrigger": bool(always_trigger),
        "statusOnReady": status_on_ready or "",
        "defaultOnHitl": bool(default_on_hitl),
        "description": description or "",
        "enabled": bool(enabled),
        "status": status or "",
        "canvas_x": canvas_x,
        "canvas_y": canvas_y,
    }


def _attr(name: str, value: Any) -> dict[str, str] | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return {"name": name, "value": "true" if value else "false"}
    return {"name": name, "value": str(value)}


def _attrs_from(props: dict[str, Any], keys: tuple[str, ...]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for key in keys:
        item = _attr(key, props.get(key))
        if item:
            rows.append(item)
    return rows


def _context_node(
    *,
    node_id: str,
    kind: str,
    label: str,
    attributes: list[dict[str, str]],
    derived: bool,
    position: tuple[float, float],
) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": kind,
        "position": {"x": position[0], "y": position[1]},
        "deletable": False,
        "connectable": False,
        "data": {
            "agentType": kind,
            "label": label,
            "kind": kind,
            "attributes": attributes,
            "readOnly": True,
            "derived": derived,
        },
    }


def _attr_row(name: str, value: str, step_id: str) -> dict[str, str]:
    item = {"name": name, "value": value}
    if step_id:
        item["id"] = step_id
    return item


def _ambient_attributes(agent: dict[str, Any]) -> list[dict[str, str]]:
    step_id = _as_text(agent.get("id") or "")
    name = _as_text(_pick(agent, "name", "id", default="ambient"))
    rows = [_attr_row("ambient", name, step_id)]
    interval = _pick(agent, "interval")
    if interval is not None:
        rows.append(_attr_row("interval", f"{name}: {interval} min", step_id))
    last_ran = _pick(agent, "lastRanTime", "last_ran_time")
    if last_ran:
        rows.append(_attr_row("lastRanTime", str(last_ran), step_id))
    status = _pick(agent, "status")
    if status:
        rows.append(_attr_row("status", str(status), step_id))
    return rows


def _unique_ambients(agents: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for agent in agents or []:
        key = _as_text(agent.get("id") or "")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        unique.append(agent)
    return unique


def _scheduler_attributes(
    service: dict[str, Any] | None,
    ambient_agents: list[dict[str, Any]] | None,
) -> list[dict[str, str]]:
    rows = [
        {"name": "source", "value": "derived"},
        {"name": "note", "value": "Not a Neo4j Scheduler node"},
    ]
    interval = None if not service else service.get("interval")
    if interval is not None:
        rows.append({"name": "serviceInterval", "value": str(interval)})
    for agent in _unique_ambients(ambient_agents):
        rows.extend(_ambient_attributes(agent))
    return rows


def build_context_nodes(
    service: dict[str, Any] | None,
    organisation: dict[str, Any] | None,
    ambient_agents: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Read-only Organisation, Service, and derived Scheduler canvas nodes."""
    nodes: list[dict[str, Any]] = []
    if organisation:
        org_id = _as_text(organisation.get("id") or "__organisation__")
        nodes.append(
            _context_node(
                node_id=org_id,
                kind="organisation",
                label=_as_text(organisation.get("name") or org_id or "Organisation"),
                attributes=_attrs_from(organisation, ORG_ATTR_KEYS),
                derived=False,
                position=(50.0, 40.0),
            )
        )
    if service:
        svc_id = _as_text(service.get("id") or "__service__")
        nodes.append(
            _context_node(
                node_id=svc_id,
                kind="service",
                label=_as_text(service.get("name") or svc_id or "Service"),
                attributes=_attrs_from(service, SERVICE_ATTR_KEYS),
                derived=False,
                position=(200.0, 40.0),
            )
        )
    if service or ambient_agents:
        nodes.append(
            _context_node(
                node_id="__scheduler__",
                kind="scheduler",
                label="Scheduler",
                attributes=_scheduler_attributes(service, ambient_agents),
                derived=True,
                position=(450.0, 40.0),
            )
        )
    return nodes


def build_context_edges(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Organisation -> Service -> Scheduler -> Start."""
    by_kind = {n["data"]["kind"]: n["id"] for n in nodes}
    org_id = by_kind.get("organisation")
    svc_id = by_kind.get("service")
    sch_id = by_kind.get("scheduler")
    edges: list[dict[str, Any]] = []
    if org_id and svc_id:
        edges.append(_context_edge("e-context-org-service", org_id, svc_id))
    if svc_id and sch_id:
        edges.append(_context_edge("e-context-service-scheduler", svc_id, sch_id))
    elif svc_id:
        edges.append(_context_edge("e-context-service-start", svc_id, "__start__"))
    if sch_id:
        edges.append(_context_edge("e-context-scheduler-start", sch_id, "__start__"))
    return edges


def _context_edge(edge_id: str, source: str, target: str) -> dict[str, Any]:
    return {
        "id": edge_id,
        "source": source,
        "target": target,
        "data": {"condition": ""},
    }


def node_props(raw: Any) -> dict[str, Any]:
    """Coerce a Neo4j node or mapping into a plain dict."""
    if raw is None:
        return {}
    return dict(raw)
