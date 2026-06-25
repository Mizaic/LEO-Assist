"""Tests for coding validation router corpus loading."""

from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from app.routers import coding_validation as router


class _FakeClient:
    def __init__(
        self,
        list_rows: list[dict] | None = None,
        detail_rows: list[dict] | None = None,
    ):
        self.list_rows = list_rows or []
        self.detail_rows = detail_rows or []
        self.calls: list[tuple[str, dict]] = []

    def run(self, query: str, **params):
        self.calls.append((query, params))
        if "{case_id: $case_id}" in query:
            return self.detail_rows
        if "MATCH (s:ExtractionScenario)" in query:
            return self.list_rows
        return []

    def close(self) -> None:
        return None


def test_load_cases_prefers_neo4j(monkeypatch):
    monkeypatch.setattr(
        router,
        "_coding_client",
        lambda: _FakeClient(
            list_rows=[
                {
                    "case_id": "lung_001",
                    "expected_strings": (
                        '[{"text": "cough", "semantic_tag": "finding"}]'
                    ),
                }
            ]
        ),
    )
    cases = router._load_cases()
    assert cases == [
        {
            "case_id": "lung_001",
            "expected_strings": [{"text": "cough", "semantic_tag": "finding"}],
        }
    ]


def test_load_cases_falls_back_to_fixture(monkeypatch, tmp_path):
    fixture_path = tmp_path / "expected_strings.json"
    fixture_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(router, "_load_cases_from_neo4j", lambda: [])
    monkeypatch.setattr(router, "_fixture_path", lambda: fixture_path)
    monkeypatch.setattr(
        router,
        "_load_cases_from_fixture",
        lambda: [{"case_id": "fixture_case", "expected_strings": []}],
    )
    cases = router._load_cases()
    assert cases[0]["case_id"] == "fixture_case"


def test_load_cases_raises_when_no_corpus(monkeypatch, tmp_path):
    monkeypatch.setattr(router, "_load_cases_from_neo4j", lambda: [])
    missing = tmp_path / "expected_strings.json"
    monkeypatch.setattr(router, "_fixture_path", lambda: missing)
    with pytest.raises(HTTPException) as exc:
        router._load_cases()
    assert exc.value.status_code == 404
    assert "Extraction scenario corpus not found" in exc.value.detail


def test_update_neo4j_ground_truth_remove(monkeypatch):
    fake = _FakeClient(
        detail_rows=[
            {
                "case_id": "lung_001",
                "expected_strings": (
                    '[{"text": "cough", "semantic_tag": "finding"}]'
                ),
            }
        ]
    )
    monkeypatch.setattr(router, "_coding_client", lambda: fake)
    updated = router._update_neo4j_ground_truth(
        router.UpdateGroundTruthRequest(
            case_id="lung_001",
            surface_form="cough",
            action="remove",
        )
    )
    assert updated is True
    patch_call = fake.calls[-1]
    assert json.loads(patch_call[1]["expected_strings"]) == []
