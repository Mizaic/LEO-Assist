"""Tests for PlanDefinition seed immutability (M2.6)."""

from __future__ import annotations

import json
import uuid

from libs.workflow.plan_seed import (
    GET_MAX_VERSION_ID,
    GET_PLAN_REFRESH_STATE,
    GET_PLAN_SEED_STATE,
    PLAN_SEED_REVISION,
    PUBLISH_VERSION_SNAPSHOT,
    UPDATE_SEED_REVISION,
    bootstrap_initial_version,
    plan_content_hash,
    publish_plan_version_snapshot,
    resolve_plan_seed_revision,
    should_publish_version_snapshot,
    should_refresh_seeded_plan_on_startup,
    should_seed_plan,
    should_touch_activity,
    touch_seed_revision,
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


def test_should_refresh_when_repo_revision_is_newer() -> None:
    assert (
        should_refresh_seeded_plan_on_startup(
            existing_count=1,
            plan_source="seed",
            stored_revision="2026-01-01T00:00:00Z",
            repo_revision=PLAN_SEED_REVISION,
        )
        is True
    )


def test_should_not_refresh_user_owned_plans() -> None:
    assert (
        should_refresh_seeded_plan_on_startup(
            existing_count=1,
            plan_source="user",
            stored_revision="",
            repo_revision=PLAN_SEED_REVISION,
        )
        is False
    )


def test_should_not_refresh_when_revision_matches() -> None:
    assert (
        should_refresh_seeded_plan_on_startup(
            existing_count=1,
            plan_source="seed",
            stored_revision=PLAN_SEED_REVISION,
            repo_revision=PLAN_SEED_REVISION,
        )
        is False
    )


def test_should_publish_when_active_content_changed() -> None:
    assert (
        should_publish_version_snapshot(
            plan_status="active",
            version_count=2,
            repo_content_hash="abc",
            latest_version_hash="def",
        )
        is True
    )


def test_should_not_publish_when_hash_matches() -> None:
    assert (
        should_publish_version_snapshot(
            plan_status="active",
            version_count=2,
            repo_content_hash="same",
            latest_version_hash="same",
        )
        is False
    )


def test_resolve_plan_seed_revision_uses_override() -> None:
    assert resolve_plan_seed_revision({"_seedRevision": "2026-07-01T00:00:00Z"}) == (
        "2026-07-01T00:00:00Z"
    )


def test_activity_definitions_are_create_only() -> None:
    assert should_touch_activity(0) is True
    assert should_touch_activity(1) is False


class _SeedClient:
    def __init__(self) -> None:
        self.plans: dict[str, dict] = {}
        self.activities: set[str] = set()
        self.version_hashes: dict[str, str] = {}
        self.version_numbers: dict[str, int] = {}
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
        if query in (GET_PLAN_SEED_STATE, GET_PLAN_REFRESH_STATE):
            plan_id = params["id"]
            plan = self.plans.get(plan_id, {})
            versions = [vid for vid in self.version_hashes if vid.startswith(plan_id)]
            latest_hash = ""
            if versions:
                latest_hash = self.version_hashes[versions[-1]]
            return [
                {
                    "status": plan.get("status", "draft"),
                    "version_count": len(versions),
                    "referenced_version_count": plan.get("referenced_versions", 0),
                    "source": plan.get("source", "seed"),
                    "seed_revision": plan.get("seed_revision", ""),
                    "latest_version_hash": latest_hash,
                }
            ]
        if query == GET_MAX_VERSION_ID:
            plan_id = params["pid"]
            return [{"max_ver": self.version_numbers.get(plan_id, 0)}]
        if query == UPSERT_PLAN:
            self.plans[params["id"]] = {
                "status": params["status"],
                "raw": params["raw"],
                "source": "seed",
                "seed_revision": params["seed_revision"],
            }
            return []
        if query == UPDATE_SEED_REVISION:
            plan = self.plans.setdefault(params["id"], {})
            plan["seed_revision"] = params["seed_revision"]
            return []
        if query == CLEAR_ACTIONS:
            return []
        if query in (CREATE_ACTION, LINK_ACTIVITY, UPSERT_ACTIVITY):
            if query == UPSERT_ACTIVITY:
                self.activities.add(params["id"])
            return []
        if query == PUBLISH_VERSION_SNAPSHOT:
            plan_id = params["pid"]
            ver = int(params["ver"])
            self.version_numbers[plan_id] = ver
            self.version_hashes[f"{plan_id}-ver-{ver}"] = params["content_hash"]
            return [{"version_id": params["vid"]}]
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


def test_startup_refresh_publishes_new_version_for_active_seed_plan() -> None:
    client = _SeedClient()
    plan_id = "pd-referral-assessment"
    client.plans[plan_id] = {
        "status": "active",
        "source": "seed",
        "seed_revision": "2026-01-01T00:00:00Z",
    }
    client.version_numbers[plan_id] = 2
    client.version_hashes[f"{plan_id}-ver-2"] = "stale-hash"

    seed_with_client(client, startup_refresh=True)

    assert client.version_numbers[plan_id] == 3
    assert client.plans[plan_id]["seed_revision"] == PLAN_SEED_REVISION


def test_startup_refresh_skips_user_owned_plan() -> None:
    client = _SeedClient()
    plan_id = "pd-referral-assessment"
    before_raw = '{"status":"active"}'
    client.plans[plan_id] = {
        "status": "active",
        "source": "user",
        "seed_revision": "",
        "raw": before_raw,
    }

    seed_with_client(client, startup_refresh=True)

    assert client.plans[plan_id]["raw"] == before_raw


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


def test_touch_seed_revision_updates_plan_node() -> None:
    client = _SeedClient()
    client.plans["pd-test"] = {"seed_revision": ""}
    touch_seed_revision(client, plan_id="pd-test", seed_revision="2026-08-04T00:00:00Z")
    assert client.plans["pd-test"]["seed_revision"] == "2026-08-04T00:00:00Z"


def test_publish_plan_version_snapshot_increments_version() -> None:
    client = _SeedClient()
    client.plans["pd-test"] = {}
    client.version_numbers["pd-test"] = 1
    version_id = publish_plan_version_snapshot(
        client,
        plan_id="pd-test",
        raw_json='{"id":"pd-test","status":"active","action":[]}',
        content_hash="hash-2",
        validate=False,
    )
    assert version_id
    assert client.version_numbers["pd-test"] == 2


def test_canonical_hash_ignores_key_order() -> None:
    first = {"b": 2, "a": 1}
    second = {"a": 1, "b": 2}
    assert plan_content_hash(first) == plan_content_hash(second)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
