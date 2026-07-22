"""Tests for PlanDefinition seed immutability (M2.6)."""

from __future__ import annotations

import json
import uuid

from libs.workflow.plan_seed import (
    GET_PLAN_SEED_STATE,
    GET_VERSION_CONTENT_HASHES,
    bootstrap_initial_version,
    plan_content_hash,
    should_seed_plan,
    should_touch_activity,
)
from scripts.seed_plan_definitions import (
    CLEAR_ACTIONS,
    COUNT_ACTIVITY_BY_ID,
    COUNT_PLAN_BY_ID,
    CREATE_ACTION,
    LINK_ACTIVITY,
    PLAN_DEFINITIONS,
    UPSERT_ACTIVITY,
    UPSERT_PLAN,
    _to_ui_format,
    seed_with_client,
)


def test_plan_content_hash_stable_for_identical_resource() -> None:
    resource = {"id": "pd-test", "name": "Test", "action": []}
    assert plan_content_hash(resource) == plan_content_hash(dict(resource))


def test_should_seed_plan_creates_missing_only_by_default() -> None:
    assert should_seed_plan(0, force=False) is True
    assert should_seed_plan(1, force=False) is False


def test_force_seed_skips_active_plans() -> None:
    assert should_seed_plan(1, force=True, plan_status="active") is False


def test_force_seed_skips_when_versions_referenced_by_runs() -> None:
    assert (
        should_seed_plan(
            1,
            force=True,
            plan_status="draft",
            referenced_version_count=2,
        )
        is False
    )


def test_force_seed_allows_draft_without_run_pins() -> None:
    assert (
        should_seed_plan(
            1,
            force=True,
            plan_status="draft",
            referenced_version_count=0,
        )
        is True
    )


def test_activity_definitions_are_create_only() -> None:
    assert should_touch_activity(0) is True
    assert should_touch_activity(1) is False


class _SeedClient:
    def __init__(self) -> None:
        self.plans: dict[str, dict] = {}
        self.activities: set[str] = set()
        self.version_hashes: dict[str, str] = {}
        self.queries: list[str] = []

    def run(self, query: str, **params):  # noqa: ANN001
        self.queries.append(query.strip().split("\n")[0])
        if "CREATE CONSTRAINT" in query:
            return []
        if "PromptConfig" in query:
            return []
        if query == COUNT_PLAN_BY_ID:
            plan_id = params["id"]
            return [{"cnt": 1 if plan_id in self.plans else 0}]
        if query == COUNT_ACTIVITY_BY_ID:
            return [{"cnt": 1 if params["id"] in self.activities else 0}]
        if query == GET_PLAN_SEED_STATE:
            plan_id = params["id"]
            plan = self.plans.get(plan_id, {})
            versions = [
                vid for vid, _ in self.version_hashes.items() if vid.startswith(plan_id)
            ]
            return [
                {
                    "status": plan.get("status", "draft"),
                    "version_count": len(versions),
                    "referenced_version_count": plan.get("referenced_versions", 0),
                }
            ]
        if query == GET_VERSION_CONTENT_HASHES:
            return [
                {
                    "version_id": vid,
                    "content_hash": h,
                    "version_id_num": idx,
                }
                for idx, (vid, h) in enumerate(self.version_hashes.items(), start=1)
            ]
        if query == UPSERT_PLAN:
            self.plans[params["id"]] = {
                "status": params["status"],
                "raw": params["raw"],
            }
            return []
        if query == CLEAR_ACTIONS:
            return []
        if query in (CREATE_ACTION, LINK_ACTIVITY, UPSERT_ACTIVITY):
            if query == UPSERT_ACTIVITY:
                self.activities.add(params["id"])
            return []
        if "PlanDefinitionVersion" in query and "CREATE" in query:
            self.version_hashes[params["vid"]] = params["content_hash"]
            return [{"version_id": params["vid"]}]
        return []


def test_seed_rerun_leaves_version_hashes_unchanged() -> None:
    client = _SeedClient()
    pd = next(p for p in PLAN_DEFINITIONS if p["id"] == "pd-gold-training-audit")
    ui_pd = _to_ui_format(pd)
    ui_pd["status"] = "draft"
    before_hash = plan_content_hash(ui_pd)
    client.plans[pd["id"]] = {"status": "active", "referenced_versions": 1}
    client.version_hashes[f"{pd['id']}-ver-1"] = before_hash

    seed_with_client(client, force=True)

    assert client.version_hashes[f"{pd['id']}-ver-1"] == before_hash
    assert all(
        "PlanDefinitionVersion" not in q or "CREATE" not in q for q in client.queries
    )


def test_seed_creates_initial_version_for_missing_plan() -> None:
    client = _SeedClient()
    pd = next(p for p in PLAN_DEFINITIONS if p["id"] == "pd-gold-training-audit")
    ui_pd = _to_ui_format(pd)
    raw_json = json.dumps(ui_pd)
    content_hash = plan_content_hash(ui_pd)
    version_id = bootstrap_initial_version(
        client,
        plan_id=pd["id"],
        raw_json=raw_json,
        content_hash=content_hash,
        version_node_id=str(uuid.uuid4()),
    )
    assert version_id
    assert client.version_hashes


def test_canonical_hash_ignores_key_order() -> None:
    first = {"b": 2, "a": 1}
    second = {"a": 1, "b": 2}
    assert plan_content_hash(first) == plan_content_hash(second)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
