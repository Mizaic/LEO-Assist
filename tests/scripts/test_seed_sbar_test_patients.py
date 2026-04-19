"""VT-5BDFE5F7 unit tests for scripts/seed_sbar_test_patients.py.

Covers the SBAR fixture importer:
- TC-001  All 10 manifest fixtures load and produce TestPatient ids
- TC-002  Concept pre-flight loud failure raises before any write
- TC-003  Idempotent re-run upserts the same TestPatient id without
          churning the node identity
- TC-004  PII-style or numeric edge cases are handled (empty
          smoking_status, missing age_band, evaluator outage with no
          matched rules)
- TC-005  Required- and banned-phrase nested lists are flattened with
          ' | ' alternative-separator semantics
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.seed_sbar_test_patients import (  # noqa: E402
    AGE_BAND_MIDPOINTS,
    SBAR_DIR,
    _build_encounter_payload,
    _build_expected_sbar_payload,
    _build_root_props,
    _collect_concept_ids,
    _flatten_phrase_list,
    _load_fixture,
    _load_manifest,
    _seed_fixture,
    _test_patient_id,
    seed,
)


class FakeKnowledgeGraphClient:
    """Captures every Cypher call so tests can assert call shape."""

    def __init__(self, present_concepts: set[str] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._present = present_concepts

    def run(self, cypher: str, **params: Any) -> list[dict[str, Any]]:
        self.calls.append((cypher, params))
        if "missing" in cypher and "WHERE c IS NULL" in cypher:
            requested = set(params.get("concept_ids") or [])
            if self._present is None:
                missing: list[str] = []
            else:
                missing = sorted(requested - self._present)
            return [{"missing": missing}]
        if "RETURN tp.id AS id" in cypher:
            return [{"id": params.get("id")}]
        if "RETURN s.id AS id" in cypher:
            return [{"id": params.get("sbar_id")}]
        if "RETURN count(DISTINCT c) AS codes_linked" in cypher:
            return [{"codes_linked": len(params.get("codes") or [])}]
        return [{}]

    def close(self) -> None:
        return None


def _all_fixture_concepts() -> set[str]:
    """Collect every SNOMED id referenced by any manifest fixture."""
    manifest = _load_manifest()
    fixtures = [_load_fixture(entry["file"]) for entry in manifest]
    return set(_collect_concept_ids(fixtures))


# ---------------------------------------------------------------------
# TC-001 -- every manifest fixture seeds successfully end-to-end
# ---------------------------------------------------------------------
def test_tc001_seeds_every_manifest_fixture():
    fake = FakeKnowledgeGraphClient(present_concepts=_all_fixture_concepts())
    seeded = seed(client=fake)
    manifest = _load_manifest()
    assert len(seeded) == len(manifest), (
        f"expected {len(manifest)} seeded, got {len(seeded)}"
    )
    for tp_id in seeded:
        assert tp_id.startswith("test_sbar_gs_"), tp_id
    cyphers = [c[0] for c in fake.calls]
    assert any(
        "RETURN collect(cid) AS missing" in c for c in cyphers
    ), "concept pre-flight must run before writes"
    assert any(
        "MERGE (tp:TestPatient { id: $id })" in c for c in cyphers
    ), "test patient root upsert must run"
    assert any(
        "MERGE (tp)-[r:HAS_EXPECTED_SBAR]->(s)" in c for c in cyphers
    ), "expected SBAR edge must be merged"


# ---------------------------------------------------------------------
# TC-002 -- loud failure when a SNOMED concept is missing
# ---------------------------------------------------------------------
def test_tc002_loud_failure_when_concept_missing(tmp_path):
    all_concepts = _all_fixture_concepts()
    one_missing = next(iter(all_concepts))
    fake = FakeKnowledgeGraphClient(
        present_concepts=all_concepts - {one_missing}
    )
    with pytest.raises(SystemExit) as excinfo:
        seed(client=fake)
    assert one_missing in str(excinfo.value)
    assert "Refusing to seed" in str(excinfo.value)
    seed_writes = [
        c for c in fake.calls
        if "MERGE (tp:TestPatient { id: $id })" in c[0]
    ]
    assert seed_writes == [], (
        "no test-patient writes must happen when concepts are missing"
    )


# ---------------------------------------------------------------------
# TC-003 -- idempotent re-run preserves test patient ids
# ---------------------------------------------------------------------
def test_tc003_seed_id_is_stable_across_runs():
    fake = FakeKnowledgeGraphClient(present_concepts=_all_fixture_concepts())
    first = seed(client=fake)
    second = seed(client=FakeKnowledgeGraphClient(
        present_concepts=_all_fixture_concepts()
    ))
    assert first == second
    assert _test_patient_id("SBAR-GS-01") == "test_sbar_gs_01"


# ---------------------------------------------------------------------
# TC-004 -- evaluator outage / missing optional fields are tolerated
# ---------------------------------------------------------------------
def test_tc004_root_props_handle_missing_optional_fields():
    fixture = {
        "id": "SBAR-GS-99",
        "title": "Synthetic edge-case fixture",
        "clinical_scenario": "",
        "input": {"guideline_ids": []},
        "resolved_situation": {"patient_summary": {}},
        "resolved_background": [],
        "llm_transcript": {},
        "reviewer_expectations": {},
        "evaluator_response": {"outage": True, "matched_rules": []},
    }
    props = _build_root_props(fixture, "SBAR-GS-99", "fixture-99.yaml")
    assert props["id"] == "test_sbar_gs_99"
    assert props["age"] is None
    assert props["age_band"] is None
    assert props["sex"] is None
    assert props["smoking_status"] is None
    assert props["guideline_ids"] == []
    assert props["name"].startswith("test_sbar-gs-99_")

    sbar = _build_expected_sbar_payload(fixture, "SBAR-GS-99", props["id"])
    assert sbar["evaluator_outage"] is True
    assert sbar["matched_rule_ids"] == []
    assert sbar["situation_md"] == ""
    assert sbar["banned_phrases"] == []


# ---------------------------------------------------------------------
# TC-005 -- nested phrase lists flatten with alternative semantics
# ---------------------------------------------------------------------
def test_tc005_nested_phrase_lists_flatten_with_alt_separator():
    flattened = _flatten_phrase_list(
        [
            "R-LUNG-001",
            ["2WW", "two-week wait", "two week wait"],
            ["Insufficient documented evidence", "clinical judgement"],
        ]
    )
    assert flattened == [
        "R-LUNG-001",
        "2WW | two-week wait | two week wait",
        "Insufficient documented evidence | clinical judgement",
    ]
    assert _flatten_phrase_list(None) == []
    assert _flatten_phrase_list("solo") == ["solo"]


# ---------------------------------------------------------------------
# TC-006 -- age band midpoint mapping is honoured for known bands
# ---------------------------------------------------------------------
def test_tc006_age_band_midpoint_is_used_when_band_known():
    fixture = {
        "id": "SBAR-GS-AGE",
        "title": "age band test",
        "input": {"guideline_ids": []},
        "resolved_situation": {
            "patient_summary": {"age_band": "60-69", "sex": "F"}
        },
        "resolved_background": [],
        "llm_transcript": {},
        "reviewer_expectations": {},
        "evaluator_response": {},
    }
    props = _build_root_props(fixture, "SBAR-GS-AGE", "fixture-age.yaml")
    assert props["age_band"] == "60-69"
    assert props["age"] == AGE_BAND_MIDPOINTS["60-69"] == 65


# ---------------------------------------------------------------------
# TC-007 -- encounter payload carries every code with assertion default
# ---------------------------------------------------------------------
def test_tc007_encounter_payload_defaults_assertion_to_present():
    enc = {
        "source_label": "Encounter",
        "source_id": "enc-gs-99",
        "text": "  GP review.  ",
        "codes": [
            {"concept_id": "12345", "term": "Made up"},
            {"concept_id": "67890", "term": "Other", "assertion": "absent"},
        ],
    }
    payload = _build_encounter_payload(enc, "SBAR-GS-99", "test_sbar_gs_99", 1)
    assert payload["text"] == "GP review."
    assert payload["fixture_id"] == "SBAR-GS-99"
    assert payload["encounter_id"].startswith("test_sbar_gs_99_enc_01_")
    assert payload["codes"] == [
        {"concept_id": "12345", "term": "Made up", "assertion": "present"},
        {"concept_id": "67890", "term": "Other", "assertion": "absent"},
    ]


# ---------------------------------------------------------------------
# TC-008 -- the 10 declared fixture YAMLs all exist on disk
# ---------------------------------------------------------------------
def test_tc008_manifest_files_exist():
    manifest = _load_manifest()
    assert len(manifest) == 10
    for entry in manifest:
        path = SBAR_DIR / entry["file"]
        assert path.is_file(), f"missing fixture file: {path}"


# ---------------------------------------------------------------------
# TC-009 -- _seed_fixture writes the right shape of cypher per fixture
# ---------------------------------------------------------------------
def test_tc009_seed_fixture_writes_root_reset_and_sbar():
    fixture = _load_fixture("fixture-01.yaml")
    fake = FakeKnowledgeGraphClient(present_concepts=_all_fixture_concepts())
    tp_id, n_enc = _seed_fixture(fake, fixture, "fixture-01.yaml")
    assert tp_id == "test_sbar_gs_01"
    assert n_enc == 1
    cyphers = [c[0] for c in fake.calls]
    assert any("MERGE (tp:TestPatient { id: $id })" in c for c in cyphers)
    assert any("DETACH DELETE e" in c for c in cyphers), (
        "RESET_SBAR_FIXTURE_CHILDREN must run before encounters are seeded"
    )
    assert any("MATCH (tp:TestPatient { id: $tp_id })\nCREATE (e:Encounter" in c for c in cyphers)
    assert any("MERGE (s:ExpectedSBAR { id: $sbar_id })" in c for c in cyphers)


# ---------------------------------------------------------------------
# TC-010 -- --allow-missing-concepts skips per-code instead of aborting
# ---------------------------------------------------------------------
def test_tc010_allow_missing_concepts_drops_only_unknown_codes():
    all_concepts = _all_fixture_concepts()
    one_missing = next(iter(all_concepts))
    fake = FakeKnowledgeGraphClient(
        present_concepts=all_concepts - {one_missing}
    )
    seeded = seed(client=fake, allow_missing_concepts=True)
    assert len(seeded) == 10, "must still seed every fixture"
    encounter_writes = [
        params for cypher, params in fake.calls
        if "CREATE (e:Encounter" in cypher
    ]
    for params in encounter_writes:
        for code in params.get("codes") or []:
            assert code["concept_id"] != one_missing, (
                "skipped concept must not appear in any encounter payload"
            )
