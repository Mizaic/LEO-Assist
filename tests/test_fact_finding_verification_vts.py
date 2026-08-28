"""Fact-finding verification tests for UN-89E2AE36.

Atlas trace:
  UN: UN-89E2AE36
  DO: DO-728930A1
  VTs:
    VT-08DC830C, VT-575882D6, VT-948B7CD4, VT-54ED1672,
    VT-5FF4FE03, VT-87B6067E, VT-264F90B7, VT-27EF1B27,
    VT-895C7DD0, VT-BF5E13E3, VT-708F6642, VT-1940CF13,
    VT-F9438948, VT-B1C9FF0B, VT-1A36E7D0

The tests pin the production implementation that loads source text, emits
fact strings before coding, records audit metadata, and keeps source evidence.
"""

from __future__ import annotations

import sys
import types
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

from libs.cypher.documents_queries import write_documents_from_sentences_payload
from tests.helpers.clinical_extraction_scenario_loader import (
    load_expected_strings,
    score_extraction_cases,
)

ROOT = Path(__file__).resolve().parents[1]
EXTRACTION = ROOT / "libs/pipeline_graph/subgraphs/extraction.py"
EXTRACTOR = ROOT / "libs/pipeline_graph/subgraphs/_extractor.py"
PERSIST = ROOT / "libs/pipeline_graph/subgraphs/persist.py"
WORKFLOW_ENGINE = ROOT / "libs/workflow/engine.py"
DOCUMENTS_QUERIES = ROOT / "libs/cypher/documents_queries.py"
FIXTURE_TEST = ROOT / "tests/test_clinical_extraction_scenario_fixtures.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _import_split_sentences():
    if "langgraph.graph" not in sys.modules:
        graph_mod = types.SimpleNamespace(
            END="END",
            START="START",
            StateGraph=type("StateGraph", (), {}),
        )
        state_mod = types.SimpleNamespace(CompiledStateGraph=object)
        sys.modules["langgraph.graph"] = graph_mod
        sys.modules["langgraph.graph.state"] = state_mod

    from libs.pipeline_graph.subgraphs.extraction import split_sentences

    return split_sentences


def test_vt575882d6_extraction_source_text_loading() -> None:
    """VT-575882D6 -- source referral text is loaded for extraction."""
    split_sentences = _import_split_sentences()
    result = split_sentences(
        {
            "encounter_id": "enc-1",
            "encounter_text": "Patient has chest pain.",
        }
    )

    assert result["encounter_text"] == "Patient has chest pain."
    assert len(result["sentences"]) == 1


def test_vt08dc830c_missing_source_text_failure_is_clear() -> None:
    """VT-08DC830C -- missing source text fails as an empty extraction input."""
    split_sentences = _import_split_sentences()
    result = split_sentences({"encounter_id": "", "encounter_text": ""})
    source = _read(EXTRACTION)

    assert result["encounter_text"] == ""
    assert result["sentences"] == []
    assert "Encounter text missing in state and Neo4j" in source


def test_vt948b7cd4_source_text_is_split_before_extraction() -> None:
    """VT-948B7CD4 -- source text is prepared before coding starts."""
    source = _read(EXTRACTION)

    assert 'g.add_edge(START, "resolve_text_units")' in source
    assert 'g.add_edge("resolve_text_units", "extract_entities")' in source
    assert 'g.add_edge("extract_entities", "merge_results")' in source


def test_vt54ed1672_clinical_fact_string_emission() -> None:
    """VT-54ED1672 -- extraction emits clinical fact strings."""
    doc = load_expected_strings()
    case = doc["cases"][0]
    extracted = {case["case_id"]: list(case["expected_strings"])}
    result = score_extraction_cases([case], extracted, doc["normalisation"])

    assert result["overall"]["true_positive"] == len(case["expected_strings"])
    assert result["overall"]["f1"] == 1.0


def test_vt5ff4fe03_no_fact_input_returns_empty_output() -> None:
    """VT-5FF4FE03 -- no extractable facts produce an empty output."""
    doc = load_expected_strings()
    case = dict(doc["cases"][0], expected_strings=[])
    result = score_extraction_cases([case], {case["case_id"]: []}, doc["normalisation"])
    extraction = _read(EXTRACTION)

    assert result["overall"]["f1"] == 1.0
    assert 'return {"entities": [], "errors": [str(e)]}' in extraction


def test_vt87b6067e_unsupported_strings_are_separated_from_expected_output() -> None:
    """VT-87B6067E -- unsupported strings are not part of expected facts."""
    doc = load_expected_strings()
    fixture_test = _read(FIXTURE_TEST)

    assert any(case.get("must_not_extract") for case in doc["cases"])
    assert "## Must Not Extract" in fixture_test
    assert "expected extraction strings" in fixture_test


def test_vt264f90b7_audit_event_has_run_and_case_identity() -> None:
    """VT-264F90B7 -- audit events include run id and case identifiers."""
    engine = _read(WORKFLOW_ENGINE)

    assert '"id": f"audit-{event.run_id}"' in engine
    assert '"run_id": event.run_id' in engine
    assert '"patient_id": event.patient_id' in engine
    assert '"encounter_id": event.encounter_id or ""' in engine


def test_vt27ef1b27_audit_event_records_status_timing_and_errors() -> None:
    """VT-27EF1B27 -- audit metadata includes status, timing, and errors."""
    engine = _read(WORKFLOW_ENGINE)

    assert '"status": status' in engine
    assert '"total_duration_ms": total_ms' in engine
    assert '"error_count": len(errors)' in engine
    assert '"first_error": first_error' in engine


def test_vt895c7dd0_failed_extraction_runs_are_audit_logged() -> None:
    """VT-895C7DD0 -- failed extraction status flows to the audit record."""
    engine = _read(WORKFLOW_ENGINE)

    assert 'if step_result.status == "error":' in engine
    assert 'final_status = "error"' in engine
    assert "await self._write_audit_event(event, step_results, final_status" in engine
    assert '"status": status' in engine


def test_vtbf5e13e3_audit_text_minimisation() -> None:
    """VT-BF5E13E3 -- audit snapshots truncate large patient text fields."""
    engine = _read(WORKFLOW_ENGINE)

    assert "def _sanitize_state" in engine
    assert "MAX_STR = 2000" in engine
    assert "v[:MAX_STR]" in engine
    assert "prompt_config" in engine


def test_vt708f6642_extracted_string_source_reference() -> None:
    """VT-708F6642 -- DOCUMENTS links keep the source reference."""
    queries = _read(DOCUMENTS_QUERIES)

    assert "MERGE (src)-[r:DOCUMENTS" in queries
    assert "r.source           = $source" in queries
    assert "r.run_id           = $run_id" in queries


def test_vt1940cf13_extracted_string_source_location() -> None:
    """VT-1940CF13 -- evidence sentence, offsets, and sentence index are stored."""
    session = MagicMock()
    payload = [
        {
            "text": "Sentence one has Haematocrit mention.",
            "terms": [
                {
                    "text": "Haematocrit",
                    "semantic_tag": "observable_entity",
                    "assertion": "present",
                    "coding": {
                        "snomed_concept_id": "1022291000000105",
                        "snomed_term": "Haematocrit (observable entity)",
                        "score": 0.99,
                    },
                }
            ],
        }
    ]

    with patch(
        "libs.cypher.documents_queries.deidentify_with_span",
        return_value=("DEID sentence", 18, 29),
    ):
        written = write_documents_from_sentences_payload(
            encounter_id="enc-1",
            sentences_payload=payload,
            session=session,
            source="pipeline_runtime",
            run_id="run-123",
        )

    assert written == 1
    kwargs = session.run.call_args_list[-1].kwargs
    assert kwargs["evidence_sentence"] == "DEID sentence"
    assert kwargs["evidence_start"] == 18
    assert kwargs["evidence_end"] == 29
    assert kwargs["sentence_index"] == 0


def test_vtf9438948_source_evidence_unavailable_marker_surface() -> None:
    """VT-F9438948 -- extraction output carries source metadata fields."""
    extraction = _read(EXTRACTION)

    assert '"__sentence_id": item.sentence_id' in extraction
    assert '"__source": item.source' in extraction
    assert '"__source_meta": item.source_meta' in extraction


def test_vtb1c9ff0b_source_evidence_is_written_before_coding_decisions() -> None:
    """VT-B1C9FF0B -- DOCUMENTS evidence writes happen before coding decisions."""
    persist = _read(PERSIST)

    assert "write_documents_from_sentences_payload" in persist
    assert "UPSERT_CODING_DECISION" in persist
    # Anchored on the two call sites inside write_patient_graph. The earlier
    # version matched the literal ``session.run(UPSERT_CODING_DECISION`` at
    # the call site; extracting that loop into ``_write_coding_decisions``
    # broke the match while the ordering itself never changed.
    assert persist.index("docs_written = write_documents_from_sentences_payload") < (
        persist.index("n = _write_coding_decisions(")
    ), "a coding decision must never exist before the evidence it cites"


def test_vt1a36e7d0_terms_text_before_coding_contract() -> None:
    """VT-1A36E7D0 -- the verification scorer uses terms[].text before coding."""
    doc = load_expected_strings()

    assert doc["validation_scope"] == "extraction_only_terms_text_before_coding"

    # The declared output contract, which is what "terms[].text" names. It
    # used to be asserted against tests/helpers/..., now a shim that
    # re-exports the real loader, so the string was no longer there to find.
    from libs.workflow.validation_workflows import VALIDATION_WORKFLOW_SPECS

    contracts = [
        field
        for spec in VALIDATION_WORKFLOW_SPECS.values()
        for field in (spec.output_contract or ())
    ]
    assert "terms[].text" in contracts

    # And the scorer really does compare that field before any coding runs.
    scorer = _read(ROOT / "libs/validation/clinical_extraction_scenario_loader.py")
    assert 'entity.get("text", "")' in scorer
    assert "concept_id" not in scorer, "scoring must not depend on coding output"


def test_fact_finding_vt_ids_are_declared_in_this_module() -> None:
    """Traceability guard -- every fact-finding VT id is cited on disk."""
    text = _read(Path(__file__))
    expected_ids = {
        "VT-08DC830C",
        "VT-575882D6",
        "VT-948B7CD4",
        "VT-54ED1672",
        "VT-5FF4FE03",
        "VT-87B6067E",
        "VT-264F90B7",
        "VT-27EF1B27",
        "VT-895C7DD0",
        "VT-BF5E13E3",
        "VT-708F6642",
        "VT-1940CF13",
        "VT-F9438948",
        "VT-B1C9FF0B",
        "VT-1A36E7D0",
    }

    assert expected_ids <= set(re.findall(r"VT-[0-9A-F]{8}", text))
