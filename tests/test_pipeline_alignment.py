"""Pipeline alignment audit: validation plans must trace through the same
core stages as the production GP encounter coding plan up to the extraction
boundary.

Atlas trace:
  UN: UN-89E2AE36
  DI: DI-B5C78811
  VT: VT-29880CC8

This audit fires when a contributor changes the validation plans, the
production GP coding plan, or the activity registry. It catches accidental
drift like:

* Validation extraction stops at post_processing while production has added
  relation_linking + extraction_check.
* A new clinical guard added to production never reaches validation, so the
  metrics no longer reflect production behaviour.

The audit is intentionally tight on the early stages (extraction through
extraction_check) and silent on later stages (terminology / coding) because
validation plans branch on user-need-specific outcomes after the extraction
boundary.
"""

from __future__ import annotations

import pytest

from scripts.seed_plan_definitions import PLAN_DEFINITIONS


# Subgraphs that must appear in this exact order at the front of every
# validation plan. They mirror the early stages of pd-gp-encounter-coding so
# validation F1 reflects the production extraction stack.
EXTRACTION_STAGES: tuple[str, ...] = (
    "extraction",
    "post_processing",
    "relation_linking",
    "extraction_check",
)


# Plans that share the production extraction front-end.
ALIGNED_VALIDATION_PLAN_IDS: tuple[str, ...] = (
    "pd-referral-assessment",
    "pd-val-key-fact-extraction",
    "pd-val-pathway-criteria",
    "pd-val-triage-completeness",
    "pd-val-terminology-mapping",
    "pd-val-sbar-summary",
    "pd-referral-triage-e2e",
)


def _plan_by_id(plan_id: str) -> dict:
    for plan in PLAN_DEFINITIONS:
        if plan.get("id") == plan_id:
            return plan
    raise KeyError(plan_id)


def _action_subgraphs(plan: dict) -> list[str]:
    return [action["_subgraphId"] for action in plan["action"]]


def test_gp_encounter_coding_uses_canonical_extraction_front_end():
    """Anchor: the production plan defines the canonical front-end order."""
    plan = _plan_by_id("pd-gp-encounter-coding")
    stages = _action_subgraphs(plan)
    # encounter_loader runs first; the rest of the extraction stages follow
    # immediately, in the canonical order.
    assert stages[0] == "encounter_loader"
    assert stages[1 : 1 + len(EXTRACTION_STAGES)] == list(EXTRACTION_STAGES)


@pytest.mark.parametrize("plan_id", ALIGNED_VALIDATION_PLAN_IDS)
def test_validation_plan_front_end_matches_production(plan_id):
    """Every aligned validation plan must run the same first four stages."""
    plan = _plan_by_id(plan_id)
    # Durable plans may start with a trigger node; compare clinical stages only.
    stages = [s for s in _action_subgraphs(plan) if s != "trigger"]
    assert stages[: len(EXTRACTION_STAGES)] == list(EXTRACTION_STAGES), (
        f"{plan_id} front-end {stages[: len(EXTRACTION_STAGES)]} does not "
        f"match production canonical front-end {list(EXTRACTION_STAGES)}"
    )


def test_validation_plan_extraction_uses_llm_referral_activity():
    """Referral extraction must use LLM-only referral prompt (no NER auto-route)."""
    expected = "ActivityDefinition/ad-extraction-referral"
    for plan_id in ALIGNED_VALIDATION_PLAN_IDS:
        plan = _plan_by_id(plan_id)
        extract_actions = [
            a for a in plan["action"] if a["_subgraphId"] == "extraction"
        ]
        assert extract_actions, f"{plan_id} has no extraction action"
        assert extract_actions[0]["definitionCanonical"] == expected, (
            f"{plan_id} extraction action uses "
            f"{extract_actions[0]['definitionCanonical']} but the audit "
            f"expects {expected}"
        )


def test_production_referral_assessment_uses_full_clinical_chain():
    """Production referral runs the full graph-backed triage chain."""
    plan = _plan_by_id("pd-referral-assessment")

    assert _action_subgraphs(plan) == [
        "trigger",
        "extraction",
        "post_processing",
        "relation_linking",
        "extraction_check",
        "terminology",
        "coding_verifier",
        "snomed_enrichment",
        "relation_linking",
        "persist",
        "referral_reason",
        "compliance",
        "quality_check",
        "sbar",
    ]
    assert plan["action"][0]["trigger"] == [
        {"type": "data-changed", "name": "referral-received"}
    ]
    assert plan["_workflowMode"] == "durable_pubsub"
    assert all(a.get("_durableEventType") for a in plan["action"])
