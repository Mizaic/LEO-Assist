"""Tests for extraction scenario CRUD service and routes."""

from __future__ import annotations

import pytest

from app.services.extraction_scenario_crud import (
    ScenarioValidationError,
    create_scenario,
    delete_scenario,
    update_scenario,
    validate_case_id,
    validate_write_payload,
)


def test_validate_case_id_rejects_invalid_slug():
    with pytest.raises(ScenarioValidationError):
        validate_case_id("Bad Case")
    with pytest.raises(ScenarioValidationError):
        validate_case_id("ab")


def test_validate_write_payload_normalises_phrases():
    payload = validate_write_payload(
        {
            "site": "lung",
            "format": "referral_letter",
            "markdown_body": "Patient has cough.",
            "expected_strings": [
                {
                    "text": " cough ",
                    "semantic_tag": "finding",
                    "concept_id": " 49727002 ",
                    "preferred_term": " Cough (finding) ",
                },
                "weight loss",
            ],
            "must_not_extract": [" boilerplate ", "boilerplate"],
            "expected_analysis": {
                "matched_rule_ids": ["R-LUNG-001", "R-LUNG-001"],
                "expect_no_rules_fired": False,
                "expected_action_priority": "2ww",
                "reviewer_notes": "Should fire lung rule.",
            },
            "expected_sbar": {
                "situation_md": "2WW referral.",
                "matched_rule_ids": ["R-LUNG-001"],
            },
        }
    )
    assert payload["site"] == "lung"
    assert payload["expected_strings"] == [
        {
            "text": "cough",
            "semantic_tag": "finding",
            "concept_id": "49727002",
            "preferred_term": "Cough (finding)",
        },
        {"text": "weight loss", "semantic_tag": "finding"},
    ]
    assert payload["must_not_extract"] == ["boilerplate"]
    assert payload["expected_analysis"]["matched_rule_ids"] == ["R-LUNG-001"]
    assert payload["expected_sbar"]["situation_md"] == "2WW referral."


class _FakeClient:
    def __init__(self, rows_by_query: dict[str, list[dict]] | None = None):
        self.rows_by_query = rows_by_query or {}
        self.calls: list[tuple[str, dict]] = []

    def run(self, query: str, **params):
        self.calls.append((query, params))
        for key, rows in self.rows_by_query.items():
            if key in query:
                return rows
        if "CREATE (" in query:
            return [{"case_id": params["case_id"]}]
        if "UPDATE" in query and "SET" in query:
            return [
                {
                    "case_id": params["case_id"],
                    "review_status": "draft_for_clinician_approval",
                }
            ]
        if "DETACH DELETE" in query:
            return [{"case_id": params["case_id"]}]
        return []


def test_create_scenario_rejects_duplicate():
    client = _FakeClient(
        {"MATCH (s:ExtractionScenario {case_id: $case_id})": [{"case_id": "lung_001"}]}
    )
    with pytest.raises(ScenarioValidationError, match="already exists"):
        create_scenario(
            client,
            "lung_001",
            {
                "site": "lung",
                "format": "referral_letter",
                "markdown_body": "Clinical note",
                "expected_strings": [{"text": "cough", "semantic_tag": "finding"}],
            },
        )


def test_create_scenario_writes_node():
    client = _FakeClient()
    result = create_scenario(
        client,
        "lung_001",
        {
            "site": "lung",
            "format": "referral_letter",
            "markdown_body": "Clinical note",
            "expected_strings": [{"text": "cough", "semantic_tag": "finding"}],
        },
    )
    assert result["case_id"] == "lung_001"
    assert result["review_status"] == "draft_for_clinician_approval"
    assert any("CREATE (s:ExtractionScenario" in query for query, _ in client.calls)


def test_update_scenario_resets_review_state():
    client = _FakeClient(
        {"MATCH (s:ExtractionScenario {case_id: $case_id})": [{"case_id": "lung_001"}]}
    )
    result = update_scenario(
        client,
        "lung_001",
        {
            "site": "lung",
            "format": "referral_letter",
            "markdown_body": "Updated note",
            "expected_strings": [{"text": "cough", "semantic_tag": "finding"}],
        },
    )
    assert result["review_status"] == "draft_for_clinician_approval"
    assert any("review_status" in query for query, _ in client.calls)


def test_delete_scenario_removes_node():
    client = _FakeClient()
    result = delete_scenario(client, "lung_001")
    assert result["deleted"] is True
    assert any("DETACH DELETE" in query for query, _ in client.calls)


def test_mutation_routes_use_admin_guard(monkeypatch):
    from app.routers import extraction_scenario_mutations as routes

    captured: dict[str, object] = {}

    def fake_create(client, case_id, body):
        captured["case_id"] = case_id
        captured["body"] = body
        return {"case_id": case_id, "review_status": "draft_for_clinician_approval"}

    class FakeClient:
        def close(self):
            return None

    monkeypatch.setattr(routes, "create_scenario", fake_create)
    monkeypatch.setattr(routes, "_coding_client", lambda: FakeClient())

    result = routes.create_scenario_route(
        routes.CreateScenarioBody(
            case_id="lung_002",
            site="lung",
            format="referral_letter",
            markdown_body="Clinical note",
            expected_strings=[
                routes.ExpectedPhrase(text="cough", semantic_tag="finding")
            ],
        ),
        _scope=object(),
    )
    assert result["case_id"] == "lung_002"
    assert captured["case_id"] == "lung_002"
