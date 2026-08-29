"""List-item serialisation for the admin workflow builder."""

from __future__ import annotations

import sys
from pathlib import Path

_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.routers.admin_workflows import (  # noqa: E402
    build_rf_edges,
    build_rf_nodes,
    filter_saveable_edges,
    filter_saveable_nodes,
    serialise_workflow_row,
)


def test_serialise_workflow_row_uses_camel_case_and_fills_blank_name():
    row = {
        "id": "demo-wf-080",
        "name": None,
        "service_id": "11122233",
        "service_name": "Lower GI Urgent Suspected Cancer Referral",
        "created_at": "2026-06-27T14:06:48.927Z",
        "step_count": 2,
        "human_count": 1,
    }

    item = serialise_workflow_row(row)

    assert item["id"] == "demo-wf-080"
    assert item["name"] == "Lower GI Urgent Suspected Cancer Referral"
    assert item["serviceId"] == "11122233"
    assert item["serviceName"] == "Lower GI Urgent Suspected Cancer Referral"
    assert item["createdAt"] == "2026-06-27T14:06:48.927Z"
    assert item["stepCount"] == 2
    assert item["humanCount"] == 1


def test_serialise_workflow_row_falls_back_to_id_when_name_and_service_missing():
    item = serialise_workflow_row({"id": "demo-wf-001", "name": None})

    assert item["name"] == "demo-wf-001"
    assert item["serviceId"] == ""
    assert item["serviceName"] == ""
    assert item["stepCount"] == 0
    assert item["humanCount"] == 0


def test_build_rf_edges_gives_unique_ids_for_same_source_and_target():
    rows = [
        {
            "source": "review_6711368",
            "target": "appointment_booking_6711368",
            "condition": "",
        },
        {
            "source": "review_6711368",
            "target": "appointment_booking_6711368",
            "condition": "",
        },
        {
            "source": "review_6711368",
            "target": "appointment_booking_6711368",
            "condition": "$.ok == true",
        },
    ]

    edges = build_rf_edges(start_target="review_6711368", edge_rows=rows)
    ids = [e["id"] for e in edges]

    assert len(ids) == len(set(ids))
    assert ids[0] == "e-start-review_6711368-0"
    assert edges[1]["source"] == "review_6711368"
    assert edges[1]["target"] == "appointment_booking_6711368"


def _graph_node_row(node_id: str) -> dict:
    return {
        "n": {"id": node_id, "type": "review", "name": node_id},
        "kind": "human",
        "pos_x": 200.0,
        "pos_y": 200.0,
    }


def test_build_rf_nodes_keeps_one_copy_of_each_step_id():
    rows = [
        _graph_node_row("review_6711368"),
        _graph_node_row("review_6711368"),
        _graph_node_row("appointment_booking_6711368"),
        _graph_node_row("appointment_booking_6711368"),
    ]

    nodes = build_rf_nodes(rows)
    ids = [n["id"] for n in nodes]

    assert ids[0] == "__start__"
    assert ids.count("review_6711368") == 1
    assert ids.count("appointment_booking_6711368") == 1
    assert len(ids) == len(set(ids))


def test_filter_saveable_nodes_drops_start_and_context():
    nodes = [
        {"id": "__start__", "data": {"kind": "agent"}},
        {"id": "6711368", "data": {"kind": "service"}},
        {"id": "M0L1I", "data": {"kind": "organisation"}},
        {"id": "__scheduler__", "data": {"kind": "scheduler"}},
        {"id": "review_6711368", "data": {"kind": "human"}},
        {"id": "extract_6711368", "data": {"kind": "agent"}},
    ]

    kept = filter_saveable_nodes(nodes)

    assert [n["id"] for n in kept] == ["review_6711368", "extract_6711368"]


def test_filter_saveable_edges_drops_context_links():
    edges = [
        {"id": "e-org", "source": "M0L1I", "target": "6711368"},
        {"id": "e-svc", "source": "6711368", "target": "__start__"},
        {"id": "e-sch", "source": "__scheduler__", "target": "6711368"},
        {"id": "e-start", "source": "__start__", "target": "review_6711368"},
        {"id": "e-next", "source": "review_6711368", "target": "book_6711368"},
    ]
    saveable = {"review_6711368", "book_6711368"}

    kept = filter_saveable_edges(edges, saveable_ids=saveable)

    assert [e["id"] for e in kept] == ["e-start", "e-next"]
