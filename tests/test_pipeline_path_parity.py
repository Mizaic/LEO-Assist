"""One pipeline: BAU, Validation Lab, and reprocess must reach extract alike.

Requirement under audit (product owner): "There should only be 1 pipeline.
The Validation Lab and patient reprocess should be exactly the same as the
BAU production run."

Each test loads durable step state through the single shared loader
``libs.workflow.step_state_loader.load_step_state`` for all three entry
points and compares the keys that decide what gets extracted:

  - text_segmentation_mode
  - source_node_type
  - the (organization_id, service_id) pair used for taught-schema lookup
  - whether chunk loading happened at all

Neo4j is faked in the stub-client style used by
``tests/test_form_schema_resolve.py`` and
``tests/test_healthcare_service_resolver.py``.
"""

from __future__ import annotations

from typing import Any

import pytest

from libs.patient_document_runs.service import DEFAULT_PLAN_ID
from libs.referral_simulator.message import build_referral_received_message
from libs.validation_lab.pipeline import build_pipeline_message
from libs.workflow.durable_steps import StepRequest
from libs.workflow.step_state_loader import load_step_state

BAU_TENANT_ID = "RK5"
PATIENT_ID = "patient-sfh-1"
REFERRAL_ID = "000049823847"
DOCUMENT_REFERENCE_ID = "dr-000049823847"
ENCOUNTER_ID = "000049823847:referral-assessment"
CHUNK_IDS = ["chunk-1", "chunk-2"]
ORG_ID = "RK5"
SERVICE_ID = "7980224"

CHUNK_ROWS = [
    {
        "chunk_id": "chunk-1",
        "text": "Section A: cancer type suspected\nCervix [X]",
        "ordinal": 0,
        "char_start": 0,
        "char_end": 42,
    },
    {
        "chunk_id": "chunk-2",
        "text": "Section B: 14-day rule criteria\nB1 PMB [X]",
        "ordinal": 1,
        "char_start": 44,
        "char_end": 85,
    },
]

SERVICE_ROW = {
    "id": SERVICE_ID,
    "name": "Sherwood - Gynaecology Urgent Suspected Cancer Pathway",
    "specialty": "2WW",
    "guideline_ids_prop": "NG12",
    "guidance_ids": ["NG12"],
    "completeness_domain": None,
    "completeness_subdomain": None,
    "spoa_id": None,
    "organization_id": ORG_ID,
    "organization_name": "Sherwood Forest Hospitals NHS Foundation Trust",
}


class _FakeSession:
    """Minimal context manager standing in for a Neo4j session."""

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False


class _FakeGraphClient:
    """Stub PatientGraphClient that answers the loader's Cypher by shape."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        self.queries.append(query)
        if "MATCH (c:Chunk {id: cid})" in query:
            return list(CHUNK_ROWS)
        if "HAS_GENERAL_PRACTITIONER" in query:
            return [{"org_id": ORG_ID}]
        if "MATCH (p:Patient {id: $pid})" in query:
            return [{"birth_date": "1975-04-02", "gender": "female", "source": ""}]
        if "FOR_SERVICE" in query:
            return [dict(SERVICE_ROW)]
        return []

    def session(self) -> _FakeSession:
        return _FakeSession()

    def close(self) -> None:
        return None


class _FakeStageStore:
    def load_accumulated_state(self, run_id: str) -> dict[str, Any]:
        return {}


def _bau_body() -> dict[str, Any]:
    """BAU production referral, per docs/REFERRAL-PIPELINE-INTEGRATION.md."""
    body = build_referral_received_message(
        patient_id=PATIENT_ID,
        encounter_id=ENCOUNTER_ID,
        referral_id=REFERRAL_ID,
        document_reference_id=DOCUMENT_REFERENCE_ID,
        chunk_ids=list(CHUNK_IDS),
        run_id="run-bau",
        plan_definition_id=DEFAULT_PLAN_ID,
        context={"source": "hccp_referral_prep"},
    )
    body["tenant_id"] = BAU_TENANT_ID
    return body


def _lab_body() -> dict[str, Any]:
    """Validation Lab run, via libs/validation_lab/pipeline.py."""
    return build_pipeline_message(
        {
            "id": "case-1",
            "patient_id": PATIENT_ID,
            "encounter_id": ENCOUNTER_ID,
            "referral_id": REFERRAL_ID,
            "document_reference_id": DOCUMENT_REFERENCE_ID,
            "chunk_ids": list(CHUNK_IDS),
        },
        run_id="run-lab",
        plan_id=DEFAULT_PLAN_ID,
        dry_run=False,
    )


def _reprocess_body() -> dict[str, Any]:
    """Patient reprocess, per libs/patient_document_runs/service.py."""
    body = build_referral_received_message(
        patient_id=PATIENT_ID,
        encounter_id=ENCOUNTER_ID,
        referral_id=REFERRAL_ID,
        document_reference_id=DOCUMENT_REFERENCE_ID,
        chunk_ids=list(CHUNK_IDS),
        run_id="run-reprocess",
        plan_definition_id=DEFAULT_PLAN_ID,
        context={
            "source": "patient-viewer",
            "referral_id": REFERRAL_ID,
            "document_reference_id": DOCUMENT_REFERENCE_ID,
        },
    )
    body["tenant_id"] = BAU_TENANT_ID
    body["capture_validation_output"] = True
    return body


@pytest.fixture
def schema_lookups(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str]]:
    """Record the org/service scope every taught-schema lookup runs with."""
    from libs.pipeline import document_chunk_loader
    from libs.pipeline.form_schema_store import form_schema_state_fields

    recorded: list[tuple[str, str, str]] = []

    def _fake_resolve(
        raw_texts: list[str],
        organization_id: str = "",
        service_id: str = "",
        ers_service_id: str = "",
    ) -> tuple[Any, dict[str, str]]:
        recorded.append((organization_id, service_id, ers_service_id))
        return None, form_schema_state_fields("none")

    monkeypatch.setattr(document_chunk_loader, "_resolve_chunk_schema", _fake_resolve)
    return recorded


@pytest.fixture(autouse=True)
def _stub_side_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep prompt config, manifest, and scope validation off the network."""
    from libs.prompts import registry
    from libs.sbar import policy_runtime, trigger_chunk_scope

    monkeypatch.setattr(registry, "get_prompt_config", lambda *a, **k: {"stub": True})
    monkeypatch.setattr(policy_runtime, "load_execution_manifest", lambda *a: {})
    monkeypatch.setattr(
        trigger_chunk_scope,
        "validate_trigger_chunk_scope",
        lambda session, request: trigger_chunk_scope.TriggerChunkScopeResult(
            ok=True, ordered_chunk_ids=list(request.chunk_ids)
        ),
    )


def _load(body: dict[str, Any]) -> tuple[dict[str, Any], _FakeGraphClient]:
    client = _FakeGraphClient()
    request = StepRequest.from_message({**body, "step_id": "extraction"})
    state = load_step_state(client, _FakeStageStore(), request, body=body)
    return state, client


def _all_states() -> dict[str, dict[str, Any]]:
    return {
        "bau": _load(_bau_body())[0],
        "validation_lab": _load(_lab_body())[0],
        "reprocess": _load(_reprocess_body())[0],
    }


def test_text_segmentation_mode_matches_across_paths(schema_lookups) -> None:
    """All three paths must segment the referral the same way."""
    states = _all_states()
    modes = {name: s.get("text_segmentation_mode") for name, s in states.items()}
    assert len(set(modes.values())) == 1, modes


def test_source_node_type_matches_across_paths(schema_lookups) -> None:
    """All three paths must present the same source node type to extract."""
    states = _all_states()
    types = {name: s.get("source_node_type") for name, s in states.items()}
    assert len(set(types.values())) == 1, types


def test_receiving_service_scope_survives_chunk_source_type(schema_lookups) -> None:
    """Taught-schema binding must not depend on the source node label.

    A referral bundle is read from :Chunk rows, so ``default_source_fields``
    reports source_node_type "Chunk" and source_node_id the
    DocumentReference id. "ReferralRequest" is not a key in the extraction
    subgraph's _SOURCE_NODE_CONFIG, so state must keep "Chunk" here. The
    receiving trust and service therefore have to be resolved from the
    referral id on state, on every path.
    """
    states = _all_states()
    types = {name: s.get("source_node_type") for name, s in states.items()}
    assert set(types.values()) == {"Chunk"}, types
    orgs = {name: s.get("healthcare_service_org_id") for name, s in states.items()}
    services = {name: s.get("healthcare_service_id") for name, s in states.items()}
    assert set(orgs.values()) == {ORG_ID}, orgs
    assert set(services.values()) == {SERVICE_ID}, services


def test_schema_lookup_scope_matches_across_paths(schema_lookups) -> None:
    """The taught-schema lookup must use the same org and service everywhere."""
    _all_states()
    assert len(schema_lookups) == 3, schema_lookups
    assert len(set(schema_lookups)) == 1, schema_lookups


def test_schema_lookup_scope_is_populated(schema_lookups) -> None:
    """A referral bundle must look the schema up with a real org and service."""
    _all_states()
    empty = [scope for scope in schema_lookups if not scope[0] or not scope[1]]
    assert not empty, schema_lookups


def test_chunks_load_on_every_path(schema_lookups) -> None:
    """Every path must actually read the referral chunks."""
    states = _all_states()
    loaded = {name: len(s.get("sentences") or []) for name, s in states.items()}
    assert all(count > 0 for count in loaded.values()), loaded


def test_chunk_scope_failure_behaves_the_same_on_every_path(
    monkeypatch: pytest.MonkeyPatch,
    schema_lookups,
) -> None:
    """A failing chunk scope check must stop, or not stop, all paths alike."""
    from libs.sbar import trigger_chunk_scope

    monkeypatch.setattr(
        trigger_chunk_scope,
        "validate_trigger_chunk_scope",
        lambda session, request: trigger_chunk_scope.TriggerChunkScopeResult(
            ok=False,
            errors=[
                trigger_chunk_scope.TriggerChunkScopeError(
                    code="out_of_scope", message="chunk out of scope"
                )
            ],
        ),
    )
    states = _all_states()
    failed = {name: bool(s.get("chunk_scope_failed")) for name, s in states.items()}
    assert len(set(failed.values())) == 1, failed


def test_capture_validation_output_matches_across_paths(schema_lookups) -> None:
    """Diagnostics capture must not depend on who started the run."""
    states = _all_states()
    capture = {
        name: bool(s.get("capture_validation_output")) for name, s in states.items()
    }
    assert len(set(capture.values())) == 1, capture


def test_single_model_defaults_apply_to_every_path(schema_lookups) -> None:
    """Model mode and tier must not depend on who started the run."""
    from libs.workflow.model_defaults import apply_single_model_defaults

    states = _all_states()
    for state in states.values():
        apply_single_model_defaults(state)
    modes = {name: s.get("model_mode") for name, s in states.items()}
    tiers = {name: s.get("model_tier") for name, s in states.items()}
    assert len(set(modes.values())) == 1, modes
    assert len(set(tiers.values())) == 1, tiers
