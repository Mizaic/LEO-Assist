"""Map onboarding camelCase Neo4j props onto the workflow canvas."""

from __future__ import annotations

import sys
from pathlib import Path

_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.services.workflow_graph_cypher import GET_GRAPH_CONTEXT  # noqa: E402
from app.services.workflow_graph_map import (  # noqa: E402
    build_context_edges,
    build_context_nodes,
    is_context_kind,
    kind_from_labels,
    node_data_from_props,
    step_write_params,
)


def test_kind_from_labels_prefers_human_then_ambient():
    assert kind_from_labels(["Step", "Agent", "AmbientAgent"]) == "ambient"
    assert kind_from_labels(["HumanInTheLoop"]) == "human"
    assert kind_from_labels(["Step", "Agent", "ManualAgent"]) == "agent"


def test_node_data_from_props_reads_onboarding_camel_case():
    data = node_data_from_props(
        {
            "id": "review_6711368",
            "type": "clinical_triage",
            "name": "Clinical triage",
            "statusOnReady": "AWAITING_CLINICIAN_REVIEW",
            "defaultOnHitl": True,
            "alwaysTrigger": False,
            "description": "Clinician reviews the referral",
            "enabled": True,
            "interval": 5,
            "status": "ready",
        },
        kind="human",
    )

    assert data["agentType"] == "clinical_triage"
    assert data["statusOnReady"] == "AWAITING_CLINICIAN_REVIEW"
    assert data["defaultOnHitl"] is True
    assert data["description"] == "Clinician reviews the referral"
    assert data["enabled"] is True
    assert data["interval"] == 5
    assert data["status"] == "ready"


def test_node_data_from_props_reads_snake_case_builder_writes():
    data = node_data_from_props(
        {
            "type": "referral_prep_agent",
            "name": "Prep",
            "always_trigger": True,
            "status_on_ready": "READY",
            "default_on_hitl": False,
        },
        kind="agent",
    )

    assert data["alwaysTrigger"] is True
    assert data["statusOnReady"] == "READY"
    assert data["defaultOnHitl"] is False


def test_step_write_params_use_onboarding_camel_case():
    params = step_write_params(
        node_id="leo_prep_1",
        label="Prep",
        agent_type="referral_prep_agent",
        canvas_x=10,
        canvas_y=20,
        interval=5,
        always_trigger=True,
        status_on_ready="",
        default_on_hitl=False,
        description="Prepares documents",
        enabled=True,
        status="ready",
    )

    assert params["type"] == "referral_prep_agent"
    assert params["name"] == "Prep"
    assert params["alwaysTrigger"] is True
    assert params["statusOnReady"] == ""
    assert params["defaultOnHitl"] is False
    assert params["description"] == "Prepares documents"
    assert params["canvas_x"] == 10


def test_is_context_kind_covers_service_org_and_scheduler():
    assert is_context_kind("service") is True
    assert is_context_kind("organisation") is True
    assert is_context_kind("scheduler") is True
    assert is_context_kind("agent") is False
    assert is_context_kind("human") is False


def test_context_nodes_include_service_organisation_and_derived_scheduler():
    nodes = build_context_nodes(
        service={
            "id": "6711368",
            "name": "Fast track cancer referral",
            "interval": 720,
            "clinicalType": "2WW",
            "ers_service_id": "6711368",
            "directlyBookable": False,
            "classificationPrompt": "DO NOT SHOW THIS PROMPT",
        },
        organisation={
            "id": "M0L1I",
            "name": "TD008541 TRUST SITE 012 (E8K17)",
            "onboarderEmail": "secret@example.com",
        },
        ambient_agents=[
            {
                "id": "worklist_6711368",
                "name": "Worklist Processing",
                "interval": 720,
                "lastRanTime": "2026-06-05T01:00:23Z",
                "status": "ready",
            }
        ],
    )

    by_kind = {n["data"]["kind"]: n for n in nodes}
    assert set(by_kind) == {"service", "organisation", "scheduler"}
    assert by_kind["service"]["id"] == "6711368"
    assert by_kind["organisation"]["id"] == "M0L1I"
    assert by_kind["scheduler"]["id"] == "__scheduler__"
    assert by_kind["scheduler"]["data"]["derived"] is True
    assert by_kind["service"]["data"]["readOnly"] is True

    service_names = {a["name"] for a in by_kind["service"]["data"]["attributes"]}
    assert "classificationPrompt" not in service_names
    assert "id" in service_names
    assert "interval" in service_names
    assert "clinicalType" in service_names

    org_names = {a["name"] for a in by_kind["organisation"]["data"]["attributes"]}
    assert "onboarderEmail" not in org_names
    assert "name" in org_names

    sched_values = " ".join(
        a["value"] for a in by_kind["scheduler"]["data"]["attributes"]
    )
    assert "720" in sched_values
    assert "Worklist Processing" in sched_values
    assert "derived" in sched_values.lower() or any(
        a["name"] == "source" and a["value"] == "derived"
        for a in by_kind["scheduler"]["data"]["attributes"]
    )


def test_context_scheduler_dedupes_the_same_ambient_agent():
    nodes = build_context_nodes(
        service={"id": "svc-1", "name": "Colorectal", "interval": 720},
        organisation=None,
        ambient_agents=[
            {"id": "worklist_1", "name": "Worklist", "interval": 720},
            {"id": "worklist_1", "name": "Worklist", "interval": 720},
        ],
    )
    sched = next(n for n in nodes if n["data"]["kind"] == "scheduler")
    ambient_rows = [a for a in sched["data"]["attributes"] if a["name"] == "ambient"]
    assert len(ambient_rows) == 1


SHARED_AMBIENT_NAME = "LEO - DB UAT - Worklist Processing"


def _scheduler_attrs(ambient_agents):
    nodes = build_context_nodes(
        service={"id": "6710023", "name": "LEO - DB UAT", "interval": 720},
        organisation=None,
        ambient_agents=ambient_agents,
    )
    sched = next(n for n in nodes if n["data"]["kind"] == "scheduler")
    return sched["data"]["attributes"]


def test_scheduler_rows_keep_unique_ids_when_ambient_labels_match():
    attrs = _scheduler_attrs(
        [
            {
                "id": "worklist_aaa",
                "name": SHARED_AMBIENT_NAME,
                "interval": 720,
            },
            {
                "id": "worklist_bbb",
                "name": SHARED_AMBIENT_NAME,
                "interval": 720,
            },
        ]
    )
    ambient_rows = [a for a in attrs if a["name"] == "ambient"]
    assert len(ambient_rows) == 2
    assert {a["id"] for a in ambient_rows} == {"worklist_aaa", "worklist_bbb"}
    keys = [f"{a.get('id', '')}-{a['name']}-{i}" for i, a in enumerate(attrs)]
    assert len(keys) == len(set(keys))


def test_scheduler_does_not_list_another_workflow_ambient():
    attrs = _scheduler_attrs(
        [
            {
                "id": "worklist_6710023",
                "name": SHARED_AMBIENT_NAME,
                "interval": 720,
            }
        ]
    )
    values = [a["value"] for a in attrs]
    assert values.count(SHARED_AMBIENT_NAME) == 1
    assert "LEO - VG - Cancer - Worklist Processing" not in values
    assert "worklist_6711368" not in {a.get("id") for a in attrs}


def test_graph_context_cypher_scopes_ambients_to_this_workflow():
    collapsed = " ".join(GET_GRAPH_CONTEXT.split())
    assert ":AmbientAgent)-[:FOR_SERVICE]" not in collapsed
    assert "(a2:AmbientAgent)-[:CREATES_DATA_FOR]->(w)" in collapsed
    assert "STARTS_AT|NEXT_STEP" in collapsed
    assert "a:AmbientAgent" in collapsed


def test_context_edges_link_org_service_scheduler_start():
    nodes = build_context_nodes(
        service={"id": "svc-1", "name": "Colorectal"},
        organisation={"id": "org-1", "name": "Trust"},
        ambient_agents=[],
    )
    edges = build_context_edges(nodes)
    pairs = {(e["source"], e["target"]) for e in edges}

    assert pairs == {
        ("org-1", "svc-1"),
        ("svc-1", "__scheduler__"),
        ("__scheduler__", "__start__"),
    }
