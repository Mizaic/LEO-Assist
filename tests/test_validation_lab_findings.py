"""VT-5E51F5D9 -- Validation findings persist and clinical run open.

Atlas:
  DI: DI-562F2C9E
  DO: DO-4FD76836
  VT: VT-5E51F5D9
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from libs.cypher.validation_lab_finding_queries import (
    FIND_PIPELINE_RUNS_BY_IDENTIFIER,
    FIND_PIPELINE_RUNS_BY_LETTER,
)
from libs.validation_lab.clinical_runs import (
    compact_lookup,
    find_pipeline_runs,
    letter_snippet,
    list_clinical_patients,
    list_recent_pipeline_runs,
    require_pipeline_run,
)
from libs.validation_lab.findings import (
    FindingError,
    create_finding,
    list_findings_for_run,
    list_open_findings,
)
from libs.validation_lab import inspector as lab_inspector


class FakeFindingClient:
    def __init__(self) -> None:
        self.findings: dict[str, dict[str, Any]] = {}
        self.pipeline_runs: dict[str, dict[str, Any]] = {
            "pipe-1": {"run_id": "pipe-1", "status": "completed"},
        }
        self.lookup_rows: list[dict[str, Any]] = [
            {
                "run_id": "pipe-1",
                "status": "completed",
                "created_at": "2026-08-13",
                "plan_id": "pd-referral-assessment",
                "patient_id": "p1",
                "patient_name": "Test",
                "nhs_number": "943 476 5919",
                "ubrn": "000000000001",
            }
        ]
        self.enqueued = False
        self.queries: list[str] = []

    def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        q = " ".join(query.split())
        self.queries.append(q)
        if "MERGE (f:ValidationFinding" in q:
            row = {
                "id": params["finding_id"],
                "run_id": params["run_id"],
                "stage_id": params["stage_id"],
                "category": params["category"],
                "target": params["target"],
                "note": params["note"],
                "status": params["status"],
            }
            self.findings[row["id"]] = row
            return [{"finding": row}]
        if "MATCH (f:ValidationFinding {run_id: $run_id})" in q:
            return [
                {"finding": row}
                for row in self.findings.values()
                if row["run_id"] == params["run_id"]
            ]
        if "MATCH (f:ValidationFinding)" in q and "statuses" in params:
            wanted = set(params["statuses"])
            return [
                {"finding": row}
                for row in self.findings.values()
                if row["status"] in wanted
            ]
        if "AS run_count" in q:
            return [
                {
                    **self.lookup_rows[0],
                    "run_count": 2,
                }
            ]
        if params.get("needle"):
            return [{**self.lookup_rows[0], "hit_text": "Patient has chest pain today"}]
        if params.get("compact"):
            compact = str(params["compact"])
            lookup = str(params.get("lookup") or "").upper()
            return [
                row
                for row in self.lookup_rows
                if compact
                in compact_lookup(row.get("nhs_number") or "")
                + compact_lookup(row.get("ubrn") or "")
                or lookup in str(row.get("patient_name") or "").upper()
            ]
        if "MATCH (r:PipelineRun)" in q and "LIMIT $limit" in q:
            return [
                {
                    "run_id": "pipe-1",
                    "status": "completed",
                    "created_at": "2026-08-13",
                    "plan_id": "pd-referral-assessment",
                    "patient_id": "p1",
                    "patient_name": "Test",
                }
            ]
        if "MATCH (r:PipelineRun {id: $run_id})" in q and "RETURN r.id AS run_id" in q:
            row = self.pipeline_runs.get(params["run_id"])
            return [row] if row else []
        if "referral-received" in q or "ENQUEUE" in q:
            self.enqueued = True
        if "plan_raw_json" in q and "PipelineRun {id: $run_id}" in q:
            return [
                {
                    "pipeline_run_id": params["run_id"],
                    "pipeline_status": "completed",
                    "plan_id": "pd-referral-assessment",
                    "plan_version_id": "",
                    "execution_manifest_json": "",
                    "plan_raw_json": '{"action": []}',
                    "plan_version_number": 1,
                }
            ]
        if "HAS_STAGE" in q:
            return []
        return []


def test_create_finding_stores_required_fields() -> None:
    client = FakeFindingClient()
    row = create_finding(
        client,
        run_id="run-1",
        stage_id="extract",
        category="extraction",
        target="chest pain",
        note="This fact was missed.",
    )
    assert row["run_id"] == "run-1"
    assert row["stage_id"] == "extract"
    assert row["category"] == "extraction"
    assert row["target"] == "chest pain"
    assert row["note"] == "This fact was missed."
    assert row["status"] == "open"
    listed = list_findings_for_run(client, "run-1")
    assert len(listed) == 1
    open_rows = list_open_findings(client)
    assert open_rows[0]["id"] == row["id"]


class _Neo4jDateTime:
    def __init__(self, text: str) -> None:
        self._text = text

    def iso_format(self) -> str:
        return self._text


def test_saving_a_finding_returns_json_safe_timestamps() -> None:
    client = FakeFindingClient()
    inner = client.run

    def with_datetimes(query: str, **params: Any) -> list[dict[str, Any]]:
        rows = inner(query, **params)
        for row in rows:
            finding = row.get("finding")
            if finding is not None:
                finding["created_at"] = _Neo4jDateTime("2026-08-14T08:00:00Z")
                finding["updated_at"] = _Neo4jDateTime("2026-08-14T08:00:00Z")
        return rows

    client.run = with_datetimes  # type: ignore[method-assign]
    row = create_finding(
        client,
        run_id="run-1",
        stage_id="terminology",
        category="phrase_mapping",
        target="bilirubin",
        note="did not code",
    )
    payload = json.dumps(row)
    assert "bilirubin" in payload
    assert row["created_at"] == "2026-08-14T08:00:00Z"
    assert row["updated_at"] == "2026-08-14T08:00:00Z"


def test_create_finding_rejects_unknown_category() -> None:
    client = FakeFindingClient()
    with pytest.raises(FindingError):
        create_finding(
            client,
            run_id="run-1",
            stage_id="extract",
            category="hallucination",
            target="x",
            note="n",
        )


def test_list_recent_pipeline_runs_does_not_enqueue() -> None:
    client = FakeFindingClient()
    rows = list_recent_pipeline_runs(client, limit=10)
    assert rows[0]["run_id"] == "pipe-1"
    assert client.enqueued is False


def test_find_pipeline_runs_by_nhs_number_does_not_enqueue() -> None:
    client = FakeFindingClient()
    rows = find_pipeline_runs(client, query="943 476 5919", limit=10)
    assert rows[0]["run_id"] == "pipe-1"
    assert rows[0]["nhs_number"] == "943 476 5919"
    assert rows[0]["matched_on"] == "nhs"
    assert client.enqueued is False


def test_find_pipeline_runs_by_ubrn_does_not_enqueue() -> None:
    client = FakeFindingClient()
    rows = find_pipeline_runs(client, query="000000000001", limit=10)
    assert rows[0]["ubrn"] == "000000000001"
    assert rows[0]["matched_on"] == "ubrn"
    assert client.enqueued is False


def test_find_pipeline_runs_by_name_does_not_enqueue() -> None:
    client = FakeFindingClient()
    rows = find_pipeline_runs(client, query="Test", limit=10)
    assert rows[0]["patient_name"] == "Test"
    assert rows[0]["matched_on"] == "name"
    assert client.enqueued is False


def test_find_pipeline_runs_by_letter_does_not_enqueue() -> None:
    client = FakeFindingClient()
    rows = find_pipeline_runs(client, query="chest pain", mode="letters")
    assert rows[0]["run_id"] == "pipe-1"
    assert rows[0]["matched_on"] == "letter"
    assert "chest pain" in rows[0]["snippet"]
    assert client.enqueued is False


def test_letter_search_ignores_short_queries() -> None:
    client = FakeFindingClient()
    assert find_pipeline_runs(client, query="ab", mode="letters") == []
    assert client.queries == []


def test_letter_snippet_keeps_nearby_words() -> None:
    text = "The GP notes unexplained chest pain and weight loss."
    assert "chest pain" in letter_snippet(text, "chest pain")


def test_find_query_orders_by_alias_after_distinct() -> None:
    tail = FIND_PIPELINE_RUNS_BY_IDENTIFIER.split("RETURN")[-1]
    assert "ORDER BY run." not in tail
    assert "ORDER BY created_raw DESC" in FIND_PIPELINE_RUNS_BY_IDENTIFIER
    letter_tail = FIND_PIPELINE_RUNS_BY_LETTER.split("RETURN")[-1]
    assert "ORDER BY run." not in letter_tail


def test_compact_lookup_strips_spaces() -> None:
    assert compact_lookup("943 476 5919") == "9434765919"


def test_list_clinical_patients_does_not_enqueue() -> None:
    client = FakeFindingClient()
    rows = list_clinical_patients(client, limit=10)
    assert rows[0]["patient_id"] == "p1"
    assert rows[0]["run_count"] == 2
    assert client.enqueued is False


def test_pipeline_inspector_opens_without_enqueue() -> None:
    client = FakeFindingClient()
    snap = lab_inspector.get_pipeline_inspector(client, "pipe-1")
    assert snap["pipeline_run_id"] == "pipe-1"
    assert client.enqueued is False
    require_pipeline_run(client, "pipe-1")
    with pytest.raises(KeyError):
        require_pipeline_run(client, "missing")
