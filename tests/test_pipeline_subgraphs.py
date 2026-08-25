from __future__ import annotations

from types import SimpleNamespace

import pytest

from libs.pipeline_graph.registry import get_registry


async def _fake_build_episodes(**_kwargs):
    return SimpleNamespace(episode_ids=["ep-1"], errors=[])


async def _fake_sbar_run(_self, _payload):
    return SimpleNamespace(
        status="completed",
        assessment_id="assess-1",
        situation="Patient context.",
        background="Recent finding.",
        assessment="Review indicated.",
        recommendation="Refer urgently.",
        actions=[],
        rules=[],
        errors=[],
        notices=[],
    )


def test_anchor_episode_and_safety_net_subgraphs_produce_structured_outputs(
    monkeypatch,
):
    registry = get_registry()
    monkeypatch.setattr(
        "libs.pipeline_graph.subgraphs.episode.resolve_flag",
        lambda name, tenant_id=None: "v1",
    )
    monkeypatch.setattr(
        "libs.pipeline_graph.subgraphs.safety_net.detect_safety_net_signals",
        lambda *_args, **_kwargs: [{"type": "missing_safety_netting"}],
    )
    monkeypatch.setattr(
        "libs.pipeline_graph.subgraphs.safety_net.persist_safety_net_alerts",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "libs.pipeline_graph.subgraphs.anchor._load_registry",
        lambda domain_id="": object(),
    )
    monkeypatch.setattr(
        "libs.pipeline_graph.subgraphs.anchor.detect_patient_anchors",
        lambda **_kwargs: SimpleNamespace(
            referral_anchors=[
                {
                    "encounter_id": "enc-1",
                    "encounter_date": "2024-01-10",
                    "concept_id": "276281000000104",
                }
            ],
            diagnosis_anchors=[],
            treatment_anchors=[],
            specialist_visit_anchors=[],
            benign_closure_anchors=[],
            specialist_outcome_letter_anchors=[],
            first_presentation_anchors=[],
            detection_method="test",
            expanded_start="",
            expanded_end="",
            errors=[],
        ),
    )
    monkeypatch.setattr(
        "libs.pipeline_graph.subgraphs.episode.build_patient_episodes",
        _fake_build_episodes,
    )
    monkeypatch.setattr(
        "services.analysis_worker.app.episode_detector_v2.runner.build_episodes",
        _fake_build_episodes,
    )

    anchor_graph = registry.build("anchor_detect")
    anchor_result = anchor_graph.invoke(
        {
            "patient_id": "p-1",
            "entities": [
                {
                    "encounter_id": "enc-1",
                    "encounter_date": "2024-01-10",
                    "concept_id": 276281000000104,
                    "concept_name": "Fast track referral for suspected breast cancer",
                }
            ],
        }
    )
    assert anchor_result["anchors"]
    assert anchor_result["anchor_result"]["referral_anchors"]

    episode_graph = registry.build("episode_build")
    episode_result = episode_graph.invoke(
        {
            "patient_id": "p-1",
            "anchor_result": anchor_result["anchor_result"],
        }
    )
    assert episode_result["episode_ids"]
    assert episode_result["episodes"]

    safety_graph = registry.build("safety_net")
    safety_result = safety_graph.invoke(
        {
            "patient_id": "p-1",
            "encounter_text": "Critical potassium level",
            "episodes": episode_result["episodes"],
        }
    )
    assert safety_result["safety_net_alerts"]


def test_quality_compliance_nba_and_sbar_subgraphs_produce_stateful_outputs(
    monkeypatch,
):
    registry = get_registry()
    monkeypatch.setattr(
        "libs.pipeline_graph.subgraphs.episode.resolve_flag",
        lambda name, tenant_id=None: "v1",
    )

    monkeypatch.setattr(
        "libs.pipeline_graph.subgraphs.quality_check.run_global_quality_checks",
        lambda: type(
            "Report",
            (),
            {
                "to_dict": lambda self: {
                    "total_checked": 0,
                    "compliant_count": 0,
                    "issues": [],
                }
            },
        )(),
    )

    quality_graph = registry.build("quality_check")
    quality_result = quality_graph.invoke(
        {
            "patient_id": "p-1",
            "entities": [
                {"text": "Rectal bleeding"},
                {"text": "Rectal bleeding"},
            ],
            "episodes": [{"episode_id": "ep-1"}],
        }
    )
    assert quality_result["quality_issues"]

    compliance_graph = registry.build("compliance")
    compliance_result = compliance_graph.invoke(
        {
            "patient_id": "p-1",
            "entities": [{"text": "red flag symptoms"}],
            "checklist": {
                "items": [
                    {"label": "Red flag symptoms", "required_text": "red flag"},
                    {"label": "Urgent referral", "required_text": "urgent referral"},
                ]
            },
        }
    )
    compliance = compliance_result["compliance_result"]
    assert "is_compliant" in compliance
    if "matched_rules" in compliance:
        assert "primary" in compliance
    else:
        assert "items" in compliance
        assert "passed_count" in compliance

    nba_graph = registry.build("next_best_action")
    nba_result = nba_graph.invoke(
        {
            "patient_id": "p-1",
            "safety_net_alerts": [{"type": "missing_safety_netting"}],
            "compliance_result": compliance_result["compliance_result"],
            "quality_issues": quality_result["quality_issues"],
        }
    )
    assert nba_result["recommendations"]

    monkeypatch.setattr(
        "services.pipeline_worker.app.services.sbar_orchestrator.SBAROrchestrator.run",
        _fake_sbar_run,
    )
    sbar_graph = registry.build("sbar")
    sbar_result = sbar_graph.invoke(
        {
            "patient_id": "p-1",
            "encounter_id": "enc-1",
            "run_id": "run-1",
            "entities": [{"text": "Rectal bleeding"}],
            "safety_net_alerts": [{"type": "missing_safety_netting"}],
            "recommendations": nba_result["recommendations"],
        }
    )
    assert sbar_result["sbar_report"]["recommendation"]


def test_registered_subgraphs_build():
    registry = get_registry()
    registered_ids = {item["id"] for item in registry.list_subgraphs()}
    expected = {
        "anchor_detect",
        "episode_build",
        "safety_net",
        "quality_check",
        "compliance",
        "next_best_action",
        "sbar",
        "snomed_enrichment",
        "surface_form_validation",
        "rest_connector",
        "queue_publish",
        "guidance_rule_extraction",
    }
    assert expected.issubset(registered_ids)
    for subgraph_id in expected:
        registry.build(subgraph_id)


@pytest.mark.asyncio
async def test_episode_subgraph_invokes_inside_running_loop(monkeypatch):
    monkeypatch.setattr(
        "libs.pipeline_graph.subgraphs.episode.resolve_flag",
        lambda name, tenant_id=None: "v1",
    )
    monkeypatch.setattr(
        "libs.pipeline_graph.subgraphs.episode.build_patient_episodes",
        _fake_build_episodes,
    )
    monkeypatch.setattr(
        "services.analysis_worker.app.episode_detector_v2.runner.build_episodes",
        _fake_build_episodes,
    )
    registry = get_registry()
    episode_graph = registry.build("episode_build")
    result = episode_graph.invoke(
        {
            "patient_id": "p-async-1",
            "anchor_result": {
                "referral_anchors": [],
                "diagnosis_anchors": [],
                "treatment_anchors": [],
                "specialist_visit_anchors": [],
                "benign_closure_anchors": [],
                "specialist_outcome_letter_anchors": [],
                "first_presentation_anchors": [],
            },
        }
    )
    assert "errors" in result
