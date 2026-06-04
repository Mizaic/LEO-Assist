"""SBAR canvas subgraph was removed in favour of the durable pub/sub orchestrator.

The legacy module ``libs.pipeline_graph/subgraphs/sbar.py`` is intentionally
gone. Production SBAR work runs through
``services.pipeline_worker.app.services.sbar_orchestrator`` and the referral
durable workflow registry (see ``tests/test_durable_referral_workflow.py``).
"""

from __future__ import annotations

from pathlib import Path


def test_legacy_sbar_subgraph_module_removed():
    assert not Path("libs/pipeline_graph/subgraphs/sbar.py").exists()


def test_referral_plan_documents_sbar_deprecation():
    from scripts.seed_plan_definitions import PLAN_DEFINITIONS

    plan = next(p for p in PLAN_DEFINITIONS if p.get("id") == "pd-referral-assessment")
    assert "sbar" in plan.get("_deprecatedSubgraphs", [])
    assert all(action.get("_subgraphId") != "sbar" for action in plan.get("action", []))
