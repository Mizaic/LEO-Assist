"""VT-35051473 -- Rule edit draft save and resume.

Atlas: DI-D52E923B / DO-BED08F09 / VT-35051473 / R-762335B1
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.guidance_rules import router
from app.services.guidance_rule_draft import (
    RuleEditDraftPayload,
    clear_rule_edit_drafts,
    delete_rule_edit_draft,
    get_rule_edit_draft,
    upsert_rule_edit_draft,
)


def _make_app() -> FastAPI:
    app = FastAPI()
    from app import deps

    app.dependency_overrides[deps.require_admin] = lambda: type(
        "Scope",
        (),
        {"email": "admin@example.com", "is_admin": True},
    )()
    app.include_router(router)
    return app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(_make_app())


def _payload(**overrides: object) -> RuleEditDraftPayload:
    base = {
        "name": "Draft rule",
        "reason": "still working",
        "logic_tree": {"kind": "AND", "children": []},
        "actions": None,
        "priority": "routine",
        "due_days": None,
        "is_default": False,
        "wizard_state": {
            "currentStepId": "who",
            "wizardPhase": "pathway-conditions",
            "situationCount": 2,
            "reachedCheck": False,
        },
    }
    base.update(overrides)
    return RuleEditDraftPayload.model_validate(base)


class TestUpsertRuleEditDraft:
    def test_upsert_returns_unchanged_live_status(self) -> None:
        neo = MagicMock()
        neo.run.return_value = [
            {
                "draft_id": "d1",
                "rule_id": "rule-1",
                "rule_status": "pending_review",
                "updated_at": "2026-07-31T12:00:00Z",
            }
        ]
        result = upsert_rule_edit_draft(
            neo,
            rule_id="rule-1",
            reviewer="admin",
            payload=_payload(),
        )
        assert result["rule_status"] == "pending_review"
        assert result["rule_id"] == "rule-1"
        cypher = neo.run.call_args[0][0]
        assert "RuleEditDraft" in cypher
        assert "SUPERSEDES" not in cypher
        assert "status" not in cypher.lower() or "rule.status" in cypher

    def test_upsert_missing_rule_raises(self) -> None:
        neo = MagicMock()
        neo.run.return_value = []
        with pytest.raises(LookupError, match="not found"):
            upsert_rule_edit_draft(
                neo,
                rule_id="missing",
                reviewer="admin",
                payload=_payload(),
            )


class TestGetAndDeleteDraft:
    def test_get_parses_json_fields(self) -> None:
        neo = MagicMock()
        neo.run.return_value = [
            {
                "draft_id": "d1",
                "name": "Draft rule",
                "reason": "wip",
                "logic_json": '{"kind":"AND","children":[]}',
                "action_json": None,
                "priority": "urgent",
                "due_days": 14,
                "is_default": False,
                "wizard_state_json": '{"wizardPhase":"review"}',
                "updated_at": "2026-07-31T12:00:00Z",
                "rule_status": "active",
            }
        ]
        draft = get_rule_edit_draft(neo, rule_id="rule-1", reviewer="admin")
        assert draft is not None
        assert draft["logic_tree"]["kind"] == "AND"
        assert draft["wizard_state"]["wizardPhase"] == "review"
        assert draft["priority"] == "urgent"

    def test_get_returns_none_when_absent(self) -> None:
        neo = MagicMock()
        neo.run.return_value = []
        assert get_rule_edit_draft(neo, rule_id="r", reviewer="a") is None

    def test_delete_returns_count(self) -> None:
        neo = MagicMock()
        neo.run.return_value = [{"deleted": 1}]
        assert delete_rule_edit_draft(neo, rule_id="r", reviewer="a") == 1

    def test_clear_all_for_rule(self) -> None:
        neo = MagicMock()
        neo.run.return_value = [{"deleted": 2}]
        assert clear_rule_edit_drafts(neo, rule_id="r") == 2


class TestDraftRouter:
    def test_put_and_get_round_trip(self, client: TestClient) -> None:
        with pytest.MonkeyPatch.context() as mp:

            def fake_upsert(neo, *, rule_id, reviewer, payload):
                assert rule_id == "rule-9"
                assert reviewer == "admin"
                assert payload.wizard_state["wizardPhase"] == "prerequisites"
                return {
                    "draft_id": "d9",
                    "rule_id": rule_id,
                    "rule_status": "active",
                    "updated_at": "t",
                }

            def fake_get(neo, *, rule_id, reviewer):
                return {
                    "draft_id": "d9",
                    "rule_id": rule_id,
                    "rule_status": "active",
                    "name": "n",
                    "reason": "r",
                    "logic_tree": {"kind": "AND", "children": []},
                    "actions": None,
                    "priority": "routine",
                    "due_days": None,
                    "is_default": False,
                    "wizard_state": {"wizardPhase": "prerequisites"},
                    "updated_at": "t",
                }

            mp.setattr(
                "app.routers.guidance_rules.upsert_rule_edit_draft",
                fake_upsert,
            )
            mp.setattr(
                "app.routers.guidance_rules.get_rule_edit_draft",
                fake_get,
            )
            mp.setattr(
                "app.routers.guidance_rules._kg_client",
                lambda: MagicMock(close=MagicMock()),
            )

            put_resp = client.put(
                "/guidance/rules/review/rule-9/draft",
                json={
                    "reviewer": "admin",
                    "name": "n",
                    "reason": "r",
                    "logic_tree": {"kind": "AND", "children": []},
                    "wizard_state": {"wizardPhase": "prerequisites"},
                },
            )
            assert put_resp.status_code == 200
            assert put_resp.json()["rule_status"] == "active"

            get_resp = client.get("/guidance/rules/review/rule-9/draft?reviewer=admin")
            assert get_resp.status_code == 200
            assert get_resp.json()["draft"]["wizard_state"]["wizardPhase"] == (
                "prerequisites"
            )

    def test_delete_draft(self, client: TestClient) -> None:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "app.routers.guidance_rules.delete_rule_edit_draft",
                lambda neo, *, rule_id, reviewer: 1,
            )
            mp.setattr(
                "app.routers.guidance_rules._kg_client",
                lambda: MagicMock(close=MagicMock()),
            )
            resp = client.delete("/guidance/rules/review/rule-9/draft?reviewer=admin")
            assert resp.status_code == 200
            assert resp.json()["deleted"] == 1

    def test_picker_query_ignores_draft_label(self) -> None:
        from libs.cypher.guidance_rule_picker_queries import (
            LIST_RULES_FOR_PICKER,
        )

        assert "AppropriatenessRule" in LIST_RULES_FOR_PICKER
        assert "RuleEditDraft" not in LIST_RULES_FOR_PICKER
        assert "pending_review" in LIST_RULES_FOR_PICKER
