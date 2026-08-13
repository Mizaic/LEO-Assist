"""VT-CD5FB5E3 -- Validation Lab test-patient graph, real run polling, gold.

Atlas:
  DI: DI-724CD8A5, DI-2289D095, DI-9138BAC9
  DO: DO-3A70C3DD
  VT: VT-CD5FB5E3
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from libs.validation_lab.gold import (
    GoldContract,
    RunOutputs,
    promote_blocked_reason,
    score_against_gold,
)
from libs.validation_lab.models import (
    EncounterSpec,
    PersistMode,
    PmhItem,
    ValidationCaseSpec,
)
from libs.validation_lab import service as lab_service
from libs.validation_lab.ruleset_version import resolve_ruleset_version


class FakeClient:
    """Minimal Neo4j stand-in storing ValidationCase / run rows."""

    def __init__(self) -> None:
        self.cases: dict[str, dict[str, Any]] = {}
        self.runs: dict[str, dict[str, Any]] = {}
        self.pipeline_runs: dict[str, dict[str, Any]] = {}
        self.pipeline_stages: dict[str, list[dict[str, Any]]] = {}
        self.assessments: dict[str, dict[str, Any]] = {}
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        q = " ".join(query.split())
        if "MERGE (c:ValidationCase" in q:
            return self._upsert_case(params)
        if "MERGE (r:ValidationLabRun" in q:
            return self._upsert_run(params)
        if "ValidationLabRun {id: $run_id}" in q:
            return self._get_run(params)
        if "DETACH DELETE c" in q and "ValidationCase {id: $case_id}" in q:
            return self._delete_case(params)
        if "MATCH (c:ValidationCase {id: $case_id})" in q and "HAS_LAB_RUN" in q:
            return self._get_case_with_runs(params)
        if "MATCH (c:ValidationCase)" in q and "LIMIT" in q:
            return [{"case": c} for c in self.cases.values()]
        if "SET c.gold_json" in q and "coalesce($title" not in q:
            self.cases[params["case_id"]]["gold_json"] = params["gold_json"]
            return [{"id": params["case_id"]}]
        if "coalesce($title, c.title)" in q:
            return self._patch_case(params)
        if "HAS_STAGE" in q and "PipelineStageRun" in q and "s.step_id" in q:
            return list(self.pipeline_stages.get(params["run_id"]) or [])
        if "MATCH (r:PipelineRun {id: $run_id})" in q:
            row = self.pipeline_runs.get(params["run_id"])
            return [row] if row else []
        if "MATCH (ae:AuditEvent)" in q:
            return []
        if "GET_ASSESSMENT" in q or "MATCH (a:Assessment {id: $assessment_id})" in q:
            return self._get_assessment(params)
        return []

    def _upsert_case(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        cid = params["case_id"]
        self.cases[cid] = {
            "id": cid,
            "title": params["title"],
            "referral_text": params["referral_text"],
            "pmh_json": params["pmh_json"],
            "encounters_json": params["encounters_json"],
            "patient_id": params["patient_id"],
            "encounter_id": params["encounter_id"],
            "referral_id": params["referral_id"],
            "document_reference_id": params["document_reference_id"],
            "chunk_ids": params["chunk_ids"],
            "plan_id": params["plan_id"],
            "gold_json": params["gold_json"],
            "created_by": params["created_by"],
        }
        return [{"c": self.cases[cid]}]

    def _upsert_run(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        rid = params["run_id"]
        prior = self.runs.get(rid) or {}
        version = params.get("ruleset_version")
        if version is None:
            version = prior.get("ruleset_version")
        self.runs[rid] = {
            "id": rid,
            "_case_id": params["case_id"],
            "persist_mode": params["persist_mode"],
            "plan_id": params["plan_id"],
            "phase_ids": params["phase_ids"],
            "status": params["status"],
            "outputs_json": params["outputs_json"],
            "error_message": params["error_message"],
            "ruleset_version": version,
            "llm_cost_usd": params.get("llm_cost_usd") or 0.0,
            "llm_total_tokens": params.get("llm_total_tokens") or 0,
            "llm_calls": params.get("llm_calls") or 0,
            "created_at": prior.get("created_at") or "2026-08-05T08:00:00+00:00",
        }
        return [{"r": self.runs[rid]}]

    def _get_run(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        run = self.runs.get(params["run_id"])
        case = self.cases.get(params["case_id"])
        if not run or not case:
            return []
        return [{"run": run, "case": case}]

    def _get_case_with_runs(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        case = self.cases.get(params["case_id"])
        if not case:
            return []
        runs = [r for r in self.runs.values() if r.get("_case_id") == params["case_id"]]
        return [{"case": case, "runs": runs}]

    def _patch_case(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        case = self.cases[params["case_id"]]
        if params.get("title") is not None:
            case["title"] = params["title"]
        if params.get("referral_text") is not None:
            case["referral_text"] = params["referral_text"]
        if params.get("plan_id") is not None:
            case["plan_id"] = params["plan_id"]
        if params.get("gold_json") is not None:
            case["gold_json"] = params["gold_json"]
        return [{"c": case}]

    def _delete_case(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        cid = params["case_id"]
        case = self.cases.pop(cid, None)
        self.runs = {
            rid: run for rid, run in self.runs.items() if run.get("_case_id") != cid
        }
        return [{"patient_id": (case or {}).get("patient_id")}]

    def _get_assessment(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        row = self.assessments.get(params["assessment_id"])
        return [row] if row else []


def test_promote_blocked_for_dry_run():
    assert promote_blocked_reason(PersistMode.dry_run) is not None
    assert promote_blocked_reason(PersistMode.production) is None


def test_score_against_gold_codes():
    gold = GoldContract(snomed_codes=["123", "456"])
    out = RunOutputs(snomed_codes=["456", "123"])
    score = score_against_gold(gold, out)
    assert score["pass"] is True
    assert score["groups"]["snomed_codes"]["pass"] is True


def test_score_fails_when_codes_differ():
    gold = GoldContract(snomed_codes=["123"])
    out = RunOutputs(snomed_codes=["999"])
    score = score_against_gold(gold, out)
    assert score["pass"] is False


def _fake_materialise(patient_id: str) -> Any:
    def fake(_client: Any, spec: ValidationCaseSpec) -> dict[str, Any]:
        assert spec.referral_text
        return {
            "patient_id": patient_id,
            "encounter_id": f"{patient_id}:encounter",
            "referral_id": f"{patient_id}:referral",
            "document_reference_id": f"{patient_id}:document",
            "chunk_ids": ["chunk-a"],
            "background_encounter_ids": [],
        }

    return fake


def test_create_case_with_pmh_and_encounters(monkeypatch: pytest.MonkeyPatch):
    client = FakeClient()
    monkeypatch.setattr(lab_service, "materialise_case", _fake_materialise("p1"))
    spec = ValidationCaseSpec(
        case_id="case1",
        title="Jaundice referral",
        referral_text="## Reason for referral\n\nProgressive jaundice.",
        pmh=[PmhItem(category="condition", concept_id="197.1", term="Gallstones")],
        encounters=[EncounterSpec(label="GP note", text="Seen last week.")],
    )
    case = lab_service.create_case(client, spec)
    assert case["id"] == "case1"
    assert case["patient_id"] == "p1"
    assert case["referral_id"] == "p1:referral"
    assert case["pmh"][0]["term"] == "Gallstones"
    assert case["encounters"][0]["label"] == "GP note"


def test_delete_case_removes_case_and_cleans_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient()
    monkeypatch.setattr(lab_service, "materialise_case", _fake_materialise("p-del"))
    cleaned: list[str] = []
    monkeypatch.setattr(
        "libs.validation_lab.scaffold.cleanup_case_graph",
        lambda patient_id: cleaned.append(patient_id),
    )
    lab_service.create_case(
        client,
        ValidationCaseSpec(
            case_id="case-del",
            title="To delete",
            referral_text="Delete me.",
        ),
    )
    out = lab_service.delete_case(client, "case-del")
    assert out["deleted"] is True
    assert out["case_id"] == "case-del"
    assert cleaned == ["p-del"]
    with pytest.raises(KeyError):
        lab_service.get_case(client, "case-del")


def test_get_case_serialises_neo4j_datetime_like_values() -> None:
    class FakeNeoDateTime:
        def iso_format(self) -> str:
            return "2026-07-20T14:00:00.000000000+00:00"

    client = FakeClient()
    client.cases["case-dt"] = {
        "id": "case-dt",
        "title": "t",
        "created_at": FakeNeoDateTime(),
        "gold_json": "{}",
        "pmh_json": "[]",
        "encounters_json": "[]",
        "ag_thread_json": "[]",
        "gp_encounter_json": "{}",
    }
    case = lab_service.get_case(client, "case-dt")
    assert case["created_at"] == "2026-07-20T14:00:00.000000000+00:00"
    assert lab_service._json_safe({"nested": FakeNeoDateTime()}) == {
        "nested": "2026-07-20T14:00:00.000000000+00:00"
    }


def test_get_run_serialises_neo4j_datetime_like_values() -> None:
    class FakeNeoDateTime:
        def iso_format(self) -> str:
            return "2026-07-20T15:00:00.000000000+00:00"

    client = FakeClient()
    client.cases["case-run-dt"] = {
        "id": "case-run-dt",
        "title": "t",
        "created_at": FakeNeoDateTime(),
        "gold_json": "{}",
    }
    client.runs["run-dt"] = {
        "id": "run-dt",
        "_case_id": "case-run-dt",
        "status": "queued",
        "created_at": FakeNeoDateTime(),
        "outputs_json": "{}",
    }
    packed = lab_service.get_run(client, "case-run-dt", "run-dt")
    assert packed["run"]["created_at"] == "2026-07-20T15:00:00.000000000+00:00"
    assert packed["case"]["created_at"] == "2026-07-20T15:00:00.000000000+00:00"


def test_start_run_production_only_enqueues_never_fabricates(
    monkeypatch: pytest.MonkeyPatch,
):
    client = FakeClient()
    monkeypatch.setattr(lab_service, "materialise_case", _fake_materialise("p2"))
    monkeypatch.setattr(
        lab_service, "resolve_ruleset_version", lambda explicit=None: None
    )
    lab_service.create_case(
        client,
        ValidationCaseSpec(
            case_id="case2", title="t", referral_text="Referral body text."
        ),
    )
    published: list[dict[str, Any]] = []
    packed = lab_service.start_run(
        client,
        case_id="case2",
        plan_id="pd-referral-assessment",
        phase_ids=["extraction", "sbar"],
        persist_mode=PersistMode.production,
        publish=lambda body, run_id: published.append(body),
    )
    assert packed["run"]["status"] == "queued"
    assert packed["run"]["outputs"]["sbar_assessment_id"] == ""
    assert packed["run"]["outputs"]["snomed_codes"] == []
    assert published and published[0]["dry_run"] is False


def test_start_run_persists_explicit_ruleset_version(
    monkeypatch: pytest.MonkeyPatch,
):
    client = FakeClient()
    monkeypatch.setattr(lab_service, "materialise_case", _fake_materialise("p-ver"))
    lab_service.create_case(
        client,
        ValidationCaseSpec(
            case_id="case-ver", title="t", referral_text="Referral body text."
        ),
    )
    packed = lab_service.start_run(
        client,
        case_id="case-ver",
        plan_id="pd-referral-assessment",
        phase_ids=["extraction"],
        persist_mode=PersistMode.production,
        publish=lambda body, run_id: None,
        ruleset_version="v20260729-081307",
    )
    assert packed["run"]["ruleset_version"] == "v20260729-081307"


def test_start_run_resolves_live_ruleset_version_when_unset(
    monkeypatch: pytest.MonkeyPatch,
):
    client = FakeClient()
    monkeypatch.setattr(lab_service, "materialise_case", _fake_materialise("p-live"))
    monkeypatch.setattr(
        lab_service,
        "resolve_ruleset_version",
        lambda explicit=None: "v20260527-122320",
    )
    lab_service.create_case(
        client,
        ValidationCaseSpec(
            case_id="case-live", title="t", referral_text="Referral body text."
        ),
    )
    packed = lab_service.start_run(
        client,
        case_id="case-live",
        plan_id="pd-referral-assessment",
        phase_ids=["extraction"],
        persist_mode=PersistMode.production,
        publish=lambda body, run_id: None,
    )
    assert packed["run"]["ruleset_version"] == "v20260527-122320"


def test_resolve_ruleset_version_prefers_explicit():
    assert resolve_ruleset_version("vCandidate") == "vCandidate"


def test_start_run_dry_run_never_enqueues(monkeypatch: pytest.MonkeyPatch):
    client = FakeClient()
    monkeypatch.setattr(lab_service, "materialise_case", _fake_materialise("p3"))
    lab_service.create_case(
        client,
        ValidationCaseSpec(case_id="case3", title="t", referral_text="body"),
    )
    published: list[dict[str, Any]] = []
    packed = lab_service.start_run(
        client,
        case_id="case3",
        plan_id="pd-referral-assessment",
        phase_ids=["extraction"],
        persist_mode=PersistMode.dry_run,
        publish=lambda body, run_id: published.append(body),
    )
    assert packed["run"]["status"] == "completed"
    assert published == []


def test_start_run_marks_failed_when_publish_raises(
    monkeypatch: pytest.MonkeyPatch,
):
    client = FakeClient()
    monkeypatch.setattr(lab_service, "materialise_case", _fake_materialise("p-fail"))
    lab_service.create_case(
        client,
        ValidationCaseSpec(case_id="case-fail", title="t", referral_text="body"),
    )

    def _boom(_body: dict[str, Any], _run_id: str) -> None:
        raise RuntimeError("Service Bus auth error")

    packed = lab_service.start_run(
        client,
        case_id="case-fail",
        plan_id="pd-referral-assessment",
        phase_ids=["extraction", "sbar"],
        persist_mode=PersistMode.production,
        publish=_boom,
    )
    assert packed["run"]["status"] == "failed"
    assert "Service Bus auth error" in (packed["run"].get("error_message") or "")


def test_dry_run_cannot_promote_gold(monkeypatch: pytest.MonkeyPatch):
    client = FakeClient()
    monkeypatch.setattr(lab_service, "materialise_case", _fake_materialise("p4"))
    lab_service.create_case(
        client,
        ValidationCaseSpec(case_id="c-dry", title="t", referral_text="note"),
    )
    packed = lab_service.start_run(
        client,
        case_id="c-dry",
        plan_id="pd-referral-assessment",
        phase_ids=["extraction"],
        persist_mode=PersistMode.dry_run,
    )
    run_id = packed["run"]["id"]
    with pytest.raises(PermissionError, match="Dry-run"):
        lab_service.promote_gold(client, "c-dry", run_id)


def test_refresh_run_reads_real_assessment_once_completed(
    monkeypatch: pytest.MonkeyPatch,
):
    client = FakeClient()
    monkeypatch.setattr(lab_service, "materialise_case", _fake_materialise("p5"))
    lab_service.create_case(
        client,
        ValidationCaseSpec(case_id="c-real", title="t", referral_text="note"),
    )
    packed = lab_service.start_run(
        client,
        case_id="c-real",
        plan_id="pd-referral-assessment",
        phase_ids=["extraction", "sbar"],
        persist_mode=PersistMode.production,
        publish=lambda body, run_id: None,
    )
    run_id = packed["run"]["id"]
    assert packed["run"]["status"] == "queued"

    # Simulate the real pipeline finishing and writing a real Assessment.
    client.pipeline_runs[run_id] = {"status": "completed", "assessment_id": "ass-1"}
    client.assessments["ass-1"] = {
        "assessment_codes": ["123456"],
        "assessment_rules": ["rule-a"],
        "content": "# SBAR\n",
        "completeness_result_json": "{}",
        "llm_cost_usd": 0.0123,
        "llm_input_tokens": 1000,
        "llm_output_tokens": 200,
        "llm_cached_tokens": 50,
        "llm_total_tokens": 1250,
        "llm_calls": 4,
        "llm_latency_ms": 900,
        "llm_model_id": "test-model",
        "llm_model_provider": "test",
    }
    refreshed = lab_service.refresh_run(client, "c-real", run_id)
    assert refreshed["run"]["status"] == "completed"
    assert refreshed["run"]["outputs"]["snomed_codes"] == ["123456"]
    assert refreshed["run"]["outputs"]["sbar_assessment_id"] == "ass-1"
    assert refreshed["run"]["outputs"]["llm_usage"]["cost_usd"] == 0.0123
    assert refreshed["run"]["outputs"]["llm_usage"]["total_tokens"] == 1250
    assert refreshed["run"]["llm_cost_usd"] == 0.0123

    promoted = lab_service.promote_gold(client, "c-real", run_id)
    assert promoted["gold"]["snomed_codes"] == ["123456"]
    score = lab_service.score_case_run(client, "c-real", run_id)
    assert score["pass"] is True


def test_read_real_outputs_llm_usage_omitted_when_absent():
    from libs.validation_lab.pipeline import read_real_outputs

    client = FakeClient()
    client.assessments["ass-empty"] = {
        "assessment_codes": [],
        "assessment_rules": [],
        "content": "",
        "completeness_result_json": "{}",
    }
    out = read_real_outputs(client, "ass-empty")
    assert out.llm_usage == {}


def test_read_real_outputs_llm_usage_from_assessment():
    from libs.validation_lab.pipeline import read_real_outputs

    client = FakeClient()
    client.assessments["ass-cost"] = {
        "assessment_codes": ["1"],
        "assessment_rules": [],
        "content": "x",
        "completeness_result_json": "{}",
        "llm_cost_usd": 0.004,
        "llm_input_tokens": 10,
        "llm_output_tokens": 5,
        "llm_cached_tokens": 0,
        "llm_total_tokens": 15,
        "llm_calls": 1,
    }
    out = read_real_outputs(client, "ass-cost")
    assert out.llm_usage["cost_usd"] == 0.004
    assert out.llm_usage["llm_calls"] == 1


def test_read_real_outputs_parses_assessment_rules_json_string():
    """sbar_orchestrator.py persists assessment_rules via json.dumps(narrative.rules)
    -- a single JSON string encoding a list of full rule objects, not a Neo4j
    string list. Confirmed against a real replayed referral (BR7, 9728344007):
    the un-parsed string produced a matching_rules list of individual
    characters instead of rule ids."""
    from libs.validation_lab.pipeline import read_real_outputs

    client = FakeClient()
    client.assessments["ass-rules"] = {
        "assessment_codes": ["162164007"],
        "assessment_rules": json.dumps(
            [
                {
                    "rule_id": "rule:NG12:v1:CH002:SEC003:R000:12c9def5",
                    "name": "Rule: 1.4.1",
                    "strength": "refer",
                    "guideline_id": "NG12",
                }
            ]
        ),
        "content": "# SBAR\n",
        "completeness_result_json": "{}",
    }
    out = read_real_outputs(client, "ass-rules")
    assert out.matching_rules == ["rule:NG12:v1:CH002:SEC003:R000:12c9def5"]


def test_refresh_run_is_noop_while_still_queued():
    client = FakeClient()
    client.cases["c-pending"] = {
        "id": "c-pending",
        "patient_id": "p6",
        "gold_json": "{}",
    }
    client.runs["run-pending"] = {
        "id": "run-pending",
        "_case_id": "c-pending",
        "persist_mode": "production",
        "plan_id": "pd-referral-assessment",
        "phase_ids": ["extraction"],
        "status": "queued",
        "outputs_json": "{}",
        "error_message": "",
    }
    result = lab_service.refresh_run(client, "c-pending", "run-pending")
    assert result["run"]["status"] == "queued"
    assert result["run"]["stage_progress"] == []


def test_refresh_run_returns_live_stage_progress_while_running():
    client = FakeClient()
    client.cases["c-stages"] = {
        "id": "c-stages",
        "patient_id": "p-stages",
        "gold_json": "{}",
    }
    client.runs["run-stages"] = {
        "id": "run-stages",
        "_case_id": "c-stages",
        "persist_mode": "production",
        "plan_id": "pd-referral-assessment",
        "phase_ids": ["extraction", "sbar"],
        "status": "queued",
        "outputs_json": "{}",
        "error_message": "",
    }
    client.pipeline_runs["run-stages"] = {
        "status": "running",
        "assessment_id": "",
    }
    client.pipeline_stages["run-stages"] = [
        {
            "step_id": "act-ref-extract",
            "event_type": "extraction_requested",
            "status": "completed",
            "worker_id": "replica-a:msg-1",
            "started_at": "t1",
            "completed_at": "t2",
        },
        {
            "step_id": "act-ref-sbar",
            "event_type": "sbar_requested",
            "status": "running",
            "worker_id": "replica-b:msg-2",
            "started_at": "t3",
            "completed_at": "",
        },
    ]
    result = lab_service.refresh_run(client, "c-stages", "run-stages")
    assert result["run"]["status"] == "running"
    stages = result["run"]["stage_progress"]
    assert [s["step_id"] for s in stages] == [
        "act-ref-extract",
        "act-ref-sbar",
    ]
    assert stages[0]["status"] == "completed"
    assert stages[0]["worker_id"] == "replica-a:msg-1"
    assert stages[1]["status"] == "running"
    assert stages[1]["worker_id"] == "replica-b:msg-2"


def test_refresh_run_marks_orphan_queued_run_failed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(lab_service, "LAB_ORPHAN_QUEUED_SECONDS", 0)
    client = FakeClient()
    client.cases["c-orphan"] = {
        "id": "c-orphan",
        "patient_id": "p-orphan",
        "plan_id": "pd-referral-assessment",
        "encounter_id": "enc-1",
        "referral_id": "ref-1",
        "document_reference_id": "doc-1",
        "chunk_ids": ["chunk-1"],
        "gold_json": "{}",
    }
    client.runs["run-orphan"] = {
        "id": "run-orphan",
        "_case_id": "c-orphan",
        "persist_mode": "production",
        "plan_id": "pd-referral-assessment",
        "phase_ids": ["extraction"],
        "status": "queued",
        "outputs_json": '{"phase_outputs":[{"phase_id":"extraction","status":"queued","pipeline_enqueued":true}]}',
        "error_message": "",
        "created_at": "2020-01-01T00:00:00+00:00",
    }
    result = lab_service.refresh_run(client, "c-orphan", "run-orphan")
    assert result["run"]["status"] == "failed"
    assert "never admitted" in (result["run"].get("error_message") or "").lower()


def test_update_case_referral_text(monkeypatch: pytest.MonkeyPatch):
    client = FakeClient()
    monkeypatch.setattr(lab_service, "materialise_case", _fake_materialise("p7"))
    lab_service.create_case(
        client,
        ValidationCaseSpec(case_id="c-edit", title="Old", referral_text="note"),
    )
    updated = lab_service.update_case(
        client,
        "c-edit",
        title="New title",
        gold={"snomed_codes": ["123"]},
    )
    assert updated["title"] == "New title"
    assert updated["gold"]["snomed_codes"] == ["123"]
