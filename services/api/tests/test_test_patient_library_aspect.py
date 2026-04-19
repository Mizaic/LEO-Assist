"""VT-5BDFE5F7 -- Centralised Test Patient library, Phase A.

Verifies the data-model invariants and clone-from-real flow that
mitigate R-8C0CC94B (a test patient mistaken for a real patient) and
the new R-PHI-XGRAPH risk (PHI leaking from the patient graph to the
knowledge graph during a clone).

These tests are intentionally hermetic: they assert on the static
shape of the Cypher queries and on the Python clone service against a
hand-rolled in-memory graph client stub. They do not need a running
Neo4j instance.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from app.services import test_patient_clone
from app.services.test_patient_clone import (
    PII_KEYS_TO_STRIP,
    CloneError,
    clone_patient_as_test_patient,
)
from app.services.test_patient_redactor import NoopRedactor
from libs.cypher.test_patient_queries import (
    ALLOWED_CONCEPT_EDGE_TYPES,
    ASSERT_CONCEPTS_PRESENT,
    BACKFILL_LEGACY_TEST_PATIENTS,
    COUNT_TEST_PATIENTS_BY_ASPECT,
    CREATE_TEST_PATIENT,
    CREATE_TEST_PATIENT_FOR_ASPECT,
    LIST_REAL_PATIENTS_FOR_CLONE_PICKER,
    LIST_TEST_PATIENTS,
    READ_SOURCE_CONCEPT_EDGES,
    READ_SOURCE_DOCUMENTS,
    READ_SOURCE_ENCOUNTERS,
    READ_SOURCE_PATIENT_FOR_CLONE,
    READ_TEST_PATIENT_FULL,
    RESET_TEST_PATIENT_CHILDREN,
    SEED_EXPECTED_SBAR,
    TEST_PATIENT_ASPECTS,
    TEST_PATIENT_CONSTRAINTS,
    UPDATE_TEST_PATIENT_PROFILE,
    WRITE_EDITOR_ENCOUNTER,
    WRITE_TEST_CONCEPT_EDGE,
    WRITE_TEST_DOCUMENT,
    WRITE_TEST_ENCOUNTER,
)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


@dataclass
class FakeRow(dict):
    """dict-with-attribute-access -- mimics a Neo4j result row."""


@dataclass
class FakeGraphClient:
    """Hand-rolled stand-in for a Neo4j client.

    Records every Cypher statement and returns canned rows from the
    `responses` dict, keyed by a substring matched against the cypher.
    Falls back to ``[]`` when no key matches.
    """

    responses: dict[str, list[dict]] = field(default_factory=dict)
    calls: list[tuple[str, dict]] = field(default_factory=list)

    def run(self, cypher: str, **params: Any) -> list[dict]:
        self.calls.append((cypher, dict(params)))
        for key, rows in self.responses.items():
            if key in cypher:
                return list(rows)
        return []

    def close(self) -> None:
        pass


def _patient_graph_with_one_source() -> FakeGraphClient:
    """Patient graph stub with a real Jane Doe and a tiny subgraph."""
    return FakeGraphClient(
        responses={
            # READ_SOURCE_PATIENT_FOR_CLONE
            "MATCH (p:Patient { id: $source_patient_id })\nWHERE coalesce(p.is_test, false) = false\nOPTIONAL MATCH (p)-[:HAS_ENCOUNTER]": [
                {
                    "id": "patient-real-1",
                    "display_name": "Jane Doe",
                    "age": 62,
                    "sex": "female",
                    "nhs_number": "1234567890",
                    "date_of_birth": "1962-01-01",
                    "address": "10 High Street",
                    "phone": "07700 900900",
                    "email": "jane@example.com",
                    "encounter_count": 2,
                    "document_count": 1,
                }
            ],
            # READ_SOURCE_ENCOUNTERS
            "MATCH (p:Patient { id: $source_patient_id })-[:HAS_ENCOUNTER]->(e:Encounter)": [
                {
                    "id": "enc-1",
                    "date": "2024-09-01",
                    "text": "Mrs Jane Doe seen with cough.",
                    "flags": None,
                    "all_properties": {
                        "id": "enc-1",
                        "date": "2024-09-01",
                        "text": "Mrs Jane Doe seen with cough.",
                        "name": "Jane Doe encounter",
                    },
                    "documents": [
                        {
                            "rel_type": "DOCUMENTS",
                            "properties": {"assertion": "present"},
                            "concept_id": "12345001",
                        }
                    ],
                },
                {
                    "id": "enc-2",
                    "date": "2024-09-08",
                    "text": "Follow-up review.",
                    "flags": None,
                    "all_properties": {"id": "enc-2"},
                    "documents": [],
                },
            ],
            # READ_SOURCE_DOCUMENTS
            "MATCH (p:Patient { id: $source_patient_id })-[:HAS_DOCUMENT]->(d:Document)": [
                {
                    "id": "doc-1",
                    "title": "Referral letter",
                    "text": "Patient Jane Doe, NHS 1234567890.",
                    "all_properties": {"id": "doc-1", "title": "Referral letter"},
                },
            ],
            # READ_SOURCE_CONCEPT_EDGES
            "MATCH (p:Patient { id: $source_patient_id })-[r]->(c)": [
                {
                    "rel_type": "HAS_FINDING",
                    "properties": {"created": "2024-09-01"},
                    "concept_id": "33334",
                }
            ],
        }
    )


def _knowledge_graph_with_concepts(present: set[str]) -> FakeGraphClient:
    """Knowledge graph stub: pretends every id in `present` exists."""
    fake = FakeGraphClient()

    original_run = fake.run

    def run(cypher: str, **params: Any) -> list[dict]:
        original_run(cypher, **params)
        if "WHERE c IS NULL" in cypher and "RETURN collect(cid) AS missing" in cypher:
            requested = set(params.get("concept_ids") or [])
            missing = sorted(requested - present)
            return [{"missing": missing}]
        if "RETURN tp.id AS id" in cypher:
            return [{"id": params.get("id")}]
        if "RETURN td.id AS id" in cypher:
            return [{"id": params.get("document_id")}]
        if "RETURN count(DISTINCT te) AS encounters_written" in cypher:
            return [{"encounters_written": 1}]
        return []

    fake.run = run  # type: ignore[assignment]
    return fake


# ---------------------------------------------------------------------------
# TC-001 -- Data model + label invariants
# ---------------------------------------------------------------------------


class TestTC001DataModelInvariants:
    """Every TestPatient row carries the test marker and an aspect tag,
    and the production label is never shared."""

    def test_aspect_vocabulary_is_stable(self) -> None:
        assert TEST_PATIENT_ASPECTS == (
            "nlp",
            "episodes",
            "guidelines",
            "summarisation",
        )

    def test_constraints_index_aspect_and_is_test(self) -> None:
        joined = "\n".join(TEST_PATIENT_CONSTRAINTS)
        assert "test_patient_aspect" in joined
        assert "test_patient_is_test" in joined
        assert "test_patient_source" in joined

    def test_create_query_stamps_is_test_and_aspect(self) -> None:
        assert "is_test:           true" in CREATE_TEST_PATIENT
        assert "aspect:            'guidelines'" in CREATE_TEST_PATIENT

    def test_aspect_create_query_carries_marker(self) -> None:
        assert "is_test:            true" in CREATE_TEST_PATIENT_FOR_ASPECT
        assert "aspect:             $aspect" in CREATE_TEST_PATIENT_FOR_ASPECT

    def test_aspect_create_query_does_not_match_patient_label(self) -> None:
        # The new TestPatient root never carries a :Patient label, AND the
        # query no longer reaches across to (:Patient) -- crucial because
        # :Patient nodes do not exist in the knowledge graph.
        assert ":TestPatient" in CREATE_TEST_PATIENT_FOR_ASPECT
        assert "(src:Patient" not in CREATE_TEST_PATIENT_FOR_ASPECT
        assert "MATCH (src:Patient" not in CREATE_TEST_PATIENT_FOR_ASPECT

    def test_list_query_filters_on_test_marker(self) -> None:
        assert "coalesce(tp.is_test, false) = true" in LIST_TEST_PATIENTS

    def test_list_query_rule_id_filter_unions_sbar_matched_rules(self) -> None:
        # SBAR / referral-triage test patients link to rules via
        # ExpectedSBAR.matched_rule_ids rather than EXPECTED_RESULT
        # rels. The rule editor's "Try it on real patients" panel
        # filters by rule_id so it MUST also match the SBAR path,
        # otherwise patients created in the central library are
        # invisible (chip reads "0 saved").
        assert (
            "any(e IN expectations WHERE e.rule_id = $rule_id)"
            in LIST_TEST_PATIENTS
        )
        assert (
            "$rule_id IN coalesce(s.matched_rule_ids, [])"
            in LIST_TEST_PATIENTS
        )

    def test_count_query_groups_by_aspect(self) -> None:
        assert "coalesce(tp.aspect, 'guidelines') AS aspect" in (
            COUNT_TEST_PATIENTS_BY_ASPECT
        )
        assert "coalesce(tp.is_test, false) = true" in (
            COUNT_TEST_PATIENTS_BY_ASPECT
        )

    def test_backfill_query_idempotent_shape(self) -> None:
        assert "tp.is_test IS NULL OR tp.aspect IS NULL" in (
            BACKFILL_LEGACY_TEST_PATIENTS
        )
        assert "RETURN count(tp) AS updated" in BACKFILL_LEGACY_TEST_PATIENTS


# ---------------------------------------------------------------------------
# TC-002 -- Cross-graph isolation
# ---------------------------------------------------------------------------


class TestTC002CrossGraphIsolation:
    """READ_SOURCE_* runs on the patient graph; WRITE_TEST_* runs on the
    knowledge graph. No single Cypher statement spans both graphs, and
    the source-picker explicitly excludes test patients."""

    def test_picker_excludes_test_patients(self) -> None:
        assert "MATCH (p:Patient)" in LIST_REAL_PATIENTS_FOR_CLONE_PICKER
        assert "coalesce(p.is_test, false) = false" in (
            LIST_REAL_PATIENTS_FOR_CLONE_PICKER
        )

    def test_read_source_queries_target_patient_label(self) -> None:
        for query in (
            READ_SOURCE_PATIENT_FOR_CLONE,
            READ_SOURCE_ENCOUNTERS,
            READ_SOURCE_DOCUMENTS,
            READ_SOURCE_CONCEPT_EDGES,
        ):
            assert "MATCH (p:Patient" in query, query[:80]
            # Read-side queries must not reference :TestPatient
            assert ":TestPatient" not in query, query[:80]

    def test_write_queries_target_test_patient_only(self) -> None:
        for query in (
            WRITE_TEST_ENCOUNTER,
            WRITE_TEST_DOCUMENT,
            WRITE_TEST_CONCEPT_EDGE,
        ):
            assert ":TestPatient" in query, query[:80]
            # Write-side queries must not reference :Patient (PHI label)
            assert "(p:Patient" not in query, query[:80]
            assert "MATCH (p:Patient" not in query, query[:80]

    def test_write_queries_carry_is_test_flag(self) -> None:
        assert "te.is_test" not in WRITE_TEST_ENCOUNTER  # set as literal
        assert "is_test:          true" in WRITE_TEST_ENCOUNTER
        assert "is_test:          true" in WRITE_TEST_DOCUMENT
        assert "r.is_test = true" in WRITE_TEST_CONCEPT_EDGE

    def test_concept_check_returns_missing_ids(self) -> None:
        assert "WHERE c IS NULL" in ASSERT_CONCEPTS_PRESENT
        assert "RETURN collect(cid) AS missing" in ASSERT_CONCEPTS_PRESENT

    def test_allowed_concept_edge_types_includes_documents_only_extension(
        self,
    ) -> None:
        # DOCUMENTS is the encounter->concept edge; the rest are direct
        # patient->concept relationships. Adding a new label should be
        # an explicit code change, not a config knob.
        assert set(ALLOWED_CONCEPT_EDGE_TYPES) == {
            "HAS_FINDING",
            "HAS_DISORDER",
            "HAS_OBSERVABLE",
            "HAS_PROCEDURE",
            "HAS_SITUATION",
            "HAS_CONCEPT",
            "DOCUMENTS",
        }


# ---------------------------------------------------------------------------
# TC-003 -- Cross-graph clone end to end (dual driver)
# ---------------------------------------------------------------------------


class TestTC003CrossGraphClone:
    """Cloning a real patient produces a de-identified test patient
    written to the knowledge graph, with the test_ prefix, the chosen
    aspect, the source link as a property (not an edge), and PII
    stripped from every level (root, encounters, documents, edges)."""

    def test_clone_rejects_unknown_aspect(self) -> None:
        with pytest.raises(CloneError):
            clone_patient_as_test_patient(
                FakeGraphClient(),
                FakeGraphClient(),
                source_patient_id="patient-real-1",
                aspect="not-a-real-aspect",
                created_by="qa@example.com",
                redactor=NoopRedactor(),
            )

    def test_clone_rejects_missing_source(self) -> None:
        patient_graph = FakeGraphClient()  # returns [] for everything
        knowledge_graph = FakeGraphClient()
        with pytest.raises(CloneError):
            clone_patient_as_test_patient(
                patient_graph,
                knowledge_graph,
                source_patient_id="missing",
                aspect="nlp",
                created_by="qa@example.com",
                redactor=NoopRedactor(),
            )

    def test_clone_rejects_missing_concept_in_knowledge_graph(self) -> None:
        patient_graph = _patient_graph_with_one_source()
        # Knowledge graph knows about NEITHER concept the source uses
        knowledge_graph = _knowledge_graph_with_concepts(present=set())
        with pytest.raises(CloneError) as excinfo:
            clone_patient_as_test_patient(
                patient_graph,
                knowledge_graph,
                source_patient_id="patient-real-1",
                aspect="nlp",
                created_by="qa@example.com",
                redactor=NoopRedactor(),
            )
        msg = str(excinfo.value)
        assert "missing" in msg
        assert ("12345001" in msg) or ("33334" in msg)

    def test_clone_returns_summary_when_concepts_present(self) -> None:
        patient_graph = _patient_graph_with_one_source()
        knowledge_graph = _knowledge_graph_with_concepts(
            present={"12345001", "33334"}
        )
        result = clone_patient_as_test_patient(
            patient_graph,
            knowledge_graph,
            source_patient_id="patient-real-1",
            aspect="nlp",
            created_by="qa@example.com",
            redactor=NoopRedactor(),
        )
        assert result["aspect"] == "nlp"
        assert result["source_patient_id"] == "patient-real-1"
        assert result["id"].startswith("test_")
        assert result["name"].startswith("test_")
        assert result["encounters_cloned"] == 2
        assert result["documents_cloned"] == 1
        assert result["concept_rels_cloned"] == 1

    def test_clone_writes_age_and_sex_only_to_new_root(self) -> None:
        patient_graph = _patient_graph_with_one_source()
        knowledge_graph = _knowledge_graph_with_concepts(
            present={"12345001", "33334"}
        )
        clone_patient_as_test_patient(
            patient_graph,
            knowledge_graph,
            source_patient_id="patient-real-1",
            aspect="episodes",
            created_by="qa@example.com",
            redactor=NoopRedactor(),
        )
        create_call = next(
            (
                params
                for cypher, params in knowledge_graph.calls
                if cypher == CREATE_TEST_PATIENT_FOR_ASPECT
            ),
            None,
        )
        assert create_call is not None
        # `name` is the only PII-shaped key we deliberately set; it
        # must always carry the audit prefix and never the source's
        # display name.
        assert create_call["name"].startswith("test_")
        assert "Jane" not in create_call["name"]
        # Every other PII key is absent from the create parameters.
        for pii in PII_KEYS_TO_STRIP:
            if pii == "name":
                continue
            assert pii not in create_call, f"PII key {pii!r} leaked to create"
        assert create_call["age"] == 62
        assert create_call["sex"] == "female"
        assert create_call["source_patient_id"] == "patient-real-1"

    def test_clone_runs_redactor_on_encounter_text(self) -> None:
        patient_graph = _patient_graph_with_one_source()
        knowledge_graph = _knowledge_graph_with_concepts(
            present={"12345001", "33334"}
        )

        class CapturingRedactor(NoopRedactor):
            def __init__(self) -> None:
                self.seen: list[str] = []

            def redact(self, text: str) -> str:
                self.seen.append(text)
                return text.replace("Jane Doe", "[PERSON]")

        redactor = CapturingRedactor()
        clone_patient_as_test_patient(
            patient_graph,
            knowledge_graph,
            source_patient_id="patient-real-1",
            aspect="nlp",
            created_by="qa@example.com",
            redactor=redactor,
        )
        # Both encounter texts and the document text must be redacted.
        assert any("Jane Doe" in t for t in redactor.seen)
        encounter_writes = [
            params
            for cypher, params in knowledge_graph.calls
            if cypher == WRITE_TEST_ENCOUNTER
        ]
        assert encounter_writes, "encounter writes expected"
        for params in encounter_writes:
            assert "Jane Doe" not in (params.get("text") or "")
        document_writes = [
            params
            for cypher, params in knowledge_graph.calls
            if cypher == WRITE_TEST_DOCUMENT
        ]
        assert document_writes, "document writes expected"
        for params in document_writes:
            assert "Jane Doe" not in (params.get("text") or "")

    def test_clone_refuses_when_redactor_omitted(self) -> None:
        patient_graph = _patient_graph_with_one_source()
        knowledge_graph = _knowledge_graph_with_concepts(
            present={"12345001", "33334"}
        )
        with pytest.raises(CloneError):
            clone_patient_as_test_patient(
                patient_graph,
                knowledge_graph,
                source_patient_id="patient-real-1",
                aspect="nlp",
                created_by="qa@example.com",
                redactor=None,
            )


# ---------------------------------------------------------------------------
# TC-004 -- Aspect counts service hand-off (router-level invariants)
# ---------------------------------------------------------------------------


class TestTC004AspectCounts:
    """The service always returns one entry per known aspect plus an
    `all` total, so the UI can render four stable count tiles."""

    def test_count_by_aspect_pads_zero_rows(self) -> None:
        from app.services import test_patient_service

        client = FakeGraphClient(
            responses={
                "MATCH (tp:TestPatient)\nWHERE coalesce(tp.is_test": [
                    {"aspect": "guidelines", "total": 3},
                    {"aspect": "nlp", "total": 1},
                ]
            }
        )
        counts = test_patient_service.count_by_aspect(client)
        assert counts == {
            "nlp": 1,
            "episodes": 0,
            "guidelines": 3,
            "summarisation": 0,
            "all": 4,
        }

    def test_list_patients_normalises_unknown_aspect_to_none(self) -> None:
        from app.services import test_patient_service

        client = FakeGraphClient()
        test_patient_service.list_patients(client, aspect="bogus")
        cypher, params = client.calls[0]
        assert cypher == LIST_TEST_PATIENTS
        assert params["aspect"] is None

    def test_list_patients_passes_known_aspect_through(self) -> None:
        from app.services import test_patient_service

        client = FakeGraphClient()
        test_patient_service.list_patients(client, aspect="nlp")
        _, params = client.calls[0]
        assert params["aspect"] == "nlp"


# ---------------------------------------------------------------------------
# TC-005 -- PII allow-list completeness
# ---------------------------------------------------------------------------


class TestTC005PIIStripping:
    """The clone allow-list keeps only age + sex on the root, so any
    future PII key added to :Patient is dropped automatically."""

    def test_strip_pii_keeps_only_age_and_sex(self) -> None:
        result = test_patient_clone._strip_pii(
            {
                "id": "patient-real-1",
                "display_name": "Jane Doe",
                "nhs_number": "1234567890",
                "dateOfBirth": "1962-01-01",
                "address": "10 High Street",
                "phone_number": "07700 900900",
                "age": 62,
                "sex": "female",
                "tenantId": "tenant-1",
            }
        )
        assert set(result.keys()) == {"age", "sex"}
        assert result["age"] == 62
        assert result["sex"] == "female"

    def test_pii_keys_to_strip_lists_documented_identifiers(self) -> None:
        for key in (
            "nhs_number",
            "name",
            "displayName",
            "date_of_birth",
            "dateOfBirth",
            "address",
            "phone",
            "phone_number",
            "email",
        ):
            assert key in PII_KEYS_TO_STRIP


# ---------------------------------------------------------------------------
# TC-007 -- Build-blank service for non-Guidelines aspects
# ---------------------------------------------------------------------------


class TestTC007BuildBlankPatientForAspect:
    """Build a patient dialog (NLP / Episodes / SBAR) writes a single
    :TestPatient row with the test_ prefix, the chosen aspect, and the
    is_test flag. Guidelines aspect is rejected at this entry point
    because it goes through confirm_and_save instead.
    """

    def _client_returning(self, patient_id: str) -> FakeGraphClient:
        return FakeGraphClient(
            responses={"CREATE (tp:TestPatient": [{"id": patient_id}]}
        )

    def test_build_blank_writes_aspect_and_is_test_flag(self) -> None:
        from app.services import test_patient_service

        client = self._client_returning("test_abc123def456")
        result = test_patient_service.build_blank_patient_for_aspect(
            client,
            aspect="nlp",
            name="older man with cough",
            description="checking the AI reads cough correctly",
            age=72,
            sex="male",
            created_by="qa@example.com",
        )
        assert result["id"] == "test_abc123def456"
        assert result["aspect"] == "nlp"
        assert result["age"] == 72
        assert result["sex"] == "male"
        # Single Cypher round-trip against CREATE_TEST_PATIENT_FOR_ASPECT.
        assert len(client.calls) == 1
        cypher, params = client.calls[0]
        assert cypher == CREATE_TEST_PATIENT_FOR_ASPECT
        assert params["aspect"] == "nlp"
        # PII guardrail: name always carries the test_ prefix.
        assert params["name"].startswith("test_")
        # Reuses an existing prefix rather than double-prefixing.
        result2 = test_patient_service.build_blank_patient_for_aspect(
            client,
            aspect="episodes",
            name="test_already_prefixed",
            created_by="qa@example.com",
        )
        assert result2["aspect"] == "episodes"
        _, params2 = client.calls[-1]
        assert params2["name"] == "test_already_prefixed"

    def test_build_blank_rejects_guidelines_aspect(self) -> None:
        from app.services import test_patient_service

        client = FakeGraphClient()
        with pytest.raises(ValueError, match="guidelines"):
            test_patient_service.build_blank_patient_for_aspect(
                client,
                aspect="guidelines",
                name="should not be saved",
                created_by="qa@example.com",
            )
        assert client.calls == []

    def test_build_blank_rejects_unknown_aspect(self) -> None:
        from app.services import test_patient_service

        client = FakeGraphClient()
        with pytest.raises(ValueError):
            test_patient_service.build_blank_patient_for_aspect(
                client,
                aspect="bogus",
                name="anything",
                created_by="qa@example.com",
            )
        assert client.calls == []

    def test_build_blank_rejects_blank_name(self) -> None:
        from app.services import test_patient_service

        client = FakeGraphClient()
        with pytest.raises(ValueError, match="name"):
            test_patient_service.build_blank_patient_for_aspect(
                client,
                aspect="nlp",
                name="   ",
                created_by="qa@example.com",
            )
        assert client.calls == []


# ---------------------------------------------------------------------------
# TC-008 -- Per-aspect editor (GET /full + PATCH /full)
# ---------------------------------------------------------------------------


class TestTC008PerAspectEditor:
    """The Edit drawer reads the editable subgraph in one shot and
    rewrites it atomically. Concept ids are pre-flighted before any
    write so a missing SNOMED id fails loudly. Guidelines aspect is
    rejected at /full to preserve the rule-fire snapshot path."""

    def test_read_full_returns_encounters_and_expected_sbar(self) -> None:
        # Verify the query shape exposes everything the editor needs.
        for token in (
            "MATCH (tp:TestPatient { id: $id })",
            "OPTIONAL MATCH (tp)-[:HAS_ENCOUNTER]->(e:Encounter)",
            "OPTIONAL MATCH (e)-[d:DOCUMENTS]->(c:Concept)",
            "OPTIONAL MATCH (tp)-[:HAS_EXPECTED_SBAR]->(s:ExpectedSBAR)",
            "AS encounters",
            "AS expected_sbar",
        ):
            assert token in READ_TEST_PATIENT_FULL, token

    def test_reset_only_touches_test_marked_children(self) -> None:
        # The reset must not delete legacy non-test children attached
        # by accident (e.g. a hand-seeded concept node), so each
        # OPTIONAL MATCH has the is_test guard.
        guard = "WHERE coalesce(e.is_test, false) = true"
        assert guard in RESET_TEST_PATIENT_CHILDREN
        assert "DETACH DELETE e" in RESET_TEST_PATIENT_CHILDREN
        assert "DETACH DELETE s" in RESET_TEST_PATIENT_CHILDREN
        assert "DETACH DELETE d" in RESET_TEST_PATIENT_CHILDREN

    def test_editor_encounter_query_merges_concept_by_id(self) -> None:
        # Loud failure on missing concept is enforced by MATCH (not
        # MERGE) on the :Concept lookup -- if a concept is not in the
        # knowledge graph the UNWIND row drops to zero.
        assert "MATCH (c:Concept { id: code.concept_id })" in (
            WRITE_EDITOR_ENCOUNTER
        )
        assert "is_test:      true" in WRITE_EDITOR_ENCOUNTER
        assert "MERGE (e)-[d:DOCUMENTS]->(c)" in WRITE_EDITOR_ENCOUNTER
        assert "d.is_test    = true" in WRITE_EDITOR_ENCOUNTER

    def test_profile_update_preserves_guideline_snapshot(self) -> None:
        # The editor profile update touches name / desc / age / sex
        # only -- never EXPECTED_RESULT or codes. Guidelines aspect
        # therefore continues to flow through UPDATE_TEST_PATIENT.
        assert "EXPECTED_RESULT" not in UPDATE_TEST_PATIENT_PROFILE
        assert "tp.codes" not in UPDATE_TEST_PATIENT_PROFILE
        assert "tp.name        = $name" in UPDATE_TEST_PATIENT_PROFILE
        assert "tp.age         = $age" in UPDATE_TEST_PATIENT_PROFILE

    def test_get_full_returns_none_when_missing(self) -> None:
        from app.services import test_patient_service

        client = FakeGraphClient()
        result = test_patient_service.get_full_patient(
            client, patient_id="missing"
        )
        assert result is None

    def test_get_full_returns_row(self) -> None:
        from app.services import test_patient_service

        client = FakeGraphClient(
            responses={
                "MATCH (tp:TestPatient { id: $id })": [
                    {
                        "id": "test_abc",
                        "name": "test_one",
                        "description": "demo",
                        "aspect": "summarisation",
                        "is_test": True,
                        "encounters": [
                            {
                                "id": "enc1",
                                "text": "cough",
                                "date": None,
                                "codes": [
                                    {
                                        "concept_id": "12345",
                                        "term": "Cough",
                                        "assertion": "present",
                                    }
                                ],
                            }
                        ],
                        "expected_sbar": {
                            "id": "expsbar1",
                            "situation_md": "S",
                            "background_md": "B",
                            "recommendation_md": "R",
                        },
                    }
                ]
            }
        )
        row = test_patient_service.get_full_patient(client, patient_id="test_abc")
        assert row is not None
        assert row["aspect"] == "summarisation"
        assert len(row["encounters"]) == 1
        assert row["expected_sbar"]["situation_md"] == "S"

    def test_update_full_rejects_guidelines(self) -> None:
        from app.services import test_patient_service
        from app.services.test_patient_service import EditorError

        client = FakeGraphClient()
        with pytest.raises(EditorError, match="Guidelines"):
            test_patient_service.update_full_patient(
                client,
                patient_id="test_abc",
                aspect="guidelines",
                name="test_one",
            )
        assert client.calls == []

    def test_update_full_rejects_blank_name(self) -> None:
        from app.services import test_patient_service
        from app.services.test_patient_service import EditorError

        client = FakeGraphClient()
        with pytest.raises(EditorError, match="name"):
            test_patient_service.update_full_patient(
                client,
                patient_id="test_abc",
                aspect="nlp",
                name="   ",
            )
        assert client.calls == []

    def test_update_full_fails_loudly_on_missing_concept(self) -> None:
        from app.services import test_patient_service
        from app.services.test_patient_service import EditorError

        client = _knowledge_graph_with_concepts(present={"33334"})
        with pytest.raises(EditorError, match="missing"):
            test_patient_service.update_full_patient(
                client,
                patient_id="test_abc",
                aspect="nlp",
                name="cough patient",
                encounters=[
                    {
                        "id": "enc1",
                        "text": "patient with cough",
                        "codes": [
                            {"concept_id": "99999", "term": "Unknown"},
                            {"concept_id": "33334", "term": "Known"},
                        ],
                    }
                ],
            )
        # The pre-flight runs before the profile update, so no write
        # should have been attempted against the encounter.
        cyphers_called = [c for c, _ in client.calls]
        assert UPDATE_TEST_PATIENT_PROFILE not in cyphers_called

    def test_update_full_returns_404_marker_when_root_missing(self) -> None:
        from app.services import test_patient_service

        # Knowledge graph that has every concept but the profile
        # update returns no rows (patient does not exist).
        client = _knowledge_graph_with_concepts(present={"12345"})

        original_run = client.run

        def run(cypher: str, **params: Any) -> list[dict]:
            if cypher == UPDATE_TEST_PATIENT_PROFILE:
                client.calls.append((cypher, dict(params)))
                return []
            return original_run(cypher, **params)

        client.run = run  # type: ignore[assignment]
        result = test_patient_service.update_full_patient(
            client,
            patient_id="test_missing",
            aspect="nlp",
            name="cough patient",
            encounters=[
                {
                    "text": "demo",
                    "codes": [{"concept_id": "12345", "term": "Cough"}],
                }
            ],
        )
        assert result == {
            "id": "test_missing",
            "updated": False,
            "encounters_written": 0,
            "expected_sbar_written": False,
        }

    def test_update_full_writes_encounters_and_expected_sbar(self) -> None:
        from app.services import test_patient_service

        client = _knowledge_graph_with_concepts(present={"12345"})
        # Make UPDATE_TEST_PATIENT_PROFILE return one row so the
        # service treats the patient as existing.
        original_run = client.run

        def run(cypher: str, **params: Any) -> list[dict]:
            if cypher == UPDATE_TEST_PATIENT_PROFILE:
                client.calls.append((cypher, dict(params)))
                return [{"id": params["id"]}]
            return original_run(cypher, **params)

        client.run = run  # type: ignore[assignment]

        result = test_patient_service.update_full_patient(
            client,
            patient_id="test_abc",
            aspect="summarisation",
            name="cough handover",
            description="patient with persistent cough",
            age=72,
            sex="male",
            encounters=[
                {
                    "id": "enc1",
                    "text": "GP review: cough 4w",
                    "date": "2026-04-01",
                    "source_label": "Encounter",
                    "codes": [
                        {
                            "concept_id": "12345",
                            "term": "Cough",
                            "assertion": "present",
                        }
                    ],
                }
            ],
            expected_sbar={
                "situation_md": "older man with cough",
                "background_md": "smoker, 4w cough",
                "recommendation_md": "refer 2WW lung",
                "matched_rule_ids": ["R-LUNG-001"],
                "required_phrases": ["2WW"],
                "banned_phrases": ["as an AI"],
                "reviewer_focus": "must keep 2WW",
            },
            updated_by="qa@example.com",
        )
        assert result["updated"] is True
        assert result["aspect"] == "summarisation"
        assert result["encounters_written"] == 1
        assert result["expected_sbar_written"] is True
        cyphers = [c for c, _ in client.calls]
        # The order matters: pre-flight, profile, reset, encounters,
        # expected sbar. Profile must come BEFORE reset so a missing
        # patient short-circuits without dropping its children.
        assert ASSERT_CONCEPTS_PRESENT in cyphers
        assert (
            cyphers.index(ASSERT_CONCEPTS_PRESENT)
            < cyphers.index(UPDATE_TEST_PATIENT_PROFILE)
        )
        assert (
            cyphers.index(UPDATE_TEST_PATIENT_PROFILE)
            < cyphers.index(RESET_TEST_PATIENT_CHILDREN)
        )
        assert WRITE_EDITOR_ENCOUNTER in cyphers
        assert SEED_EXPECTED_SBAR in cyphers
        # Profile name carries the test_ prefix even though the
        # caller did not include it.
        profile_call = next(
            params for cypher, params in client.calls
            if cypher == UPDATE_TEST_PATIENT_PROFILE
        )
        assert profile_call["name"].startswith("test_")

    def test_update_full_skips_expected_sbar_for_non_summarisation(
        self,
    ) -> None:
        from app.services import test_patient_service

        client = _knowledge_graph_with_concepts(present={"12345"})
        original_run = client.run

        def run(cypher: str, **params: Any) -> list[dict]:
            if cypher == UPDATE_TEST_PATIENT_PROFILE:
                client.calls.append((cypher, dict(params)))
                return [{"id": params["id"]}]
            return original_run(cypher, **params)

        client.run = run  # type: ignore[assignment]

        result = test_patient_service.update_full_patient(
            client,
            patient_id="test_abc",
            aspect="nlp",
            name="cough patient",
            encounters=[
                {
                    "text": "GP review: cough",
                    "codes": [{"concept_id": "12345", "term": "Cough"}],
                }
            ],
            expected_sbar={"situation_md": "ignored"},
        )
        assert result["expected_sbar_written"] is False
        cyphers = [c for c, _ in client.calls]
        assert SEED_EXPECTED_SBAR not in cyphers


# ---------------------------------------------------------------------------
# TC-009 -- Guidance rule lookup powers the SBAR Matched rule IDs picker
# ---------------------------------------------------------------------------


class TestTC009GuidanceRuleLookup:
    """The SBAR editor's Matched rule IDs field is a tree-dialog picker
    over the live appropriateness rule library. The /test-patients/rules
    endpoint returns a plain-English payload (display label, chapter,
    action priority, SNOMED triggers) so the dialog can render readable
    rows and group them by guideline -- not by raw rule id."""

    def test_rules_endpoint_returns_plain_english_payload(self) -> None:
        # Verify the router payload -- nothing the picker needs is left
        # to the rule_id alone (which is opaque to a nurse). Internal
        # columns (e.g. logic_json) must NOT leak.
        from app.routers import test_patients as router

        client = FakeGraphClient(
            responses={
                "MATCH (rule:AppropriatenessRule)": [
                    {
                        "rule_id": "rule:NG12:v1:CH002:R001:abc",
                        "name": "Rule 1.1.1",
                        "status": "active",
                        "recommendation_text": (
                            "Refer adults with unexplained haematuria for an "
                            "X-ray within 2 weeks."
                        ),
                        "chapter_title": "1.1 -- Suspected cancer",
                        "action_priority": "2ww",
                        "trigger_terms": ["haematuria", "abdominal mass"],
                        "guideline_id": "NG12",
                        "guideline_title": "Suspected cancer",
                        "logic_json": "{should-not-leak}",
                    },
                ]
            }
        )

        original_client = router._client
        router._client = lambda: client  # type: ignore[assignment]
        try:
            rows = router.list_rules(
                guideline_id=None,
                q=None,
                limit=100,
                scope=None,  # type: ignore[arg-type]
            )
        finally:
            router._client = original_client  # type: ignore[assignment]

        assert isinstance(rows, list)
        assert len(rows) == 1
        first = rows[0]
        assert set(first.keys()) == {
            "rule_id",
            "status",
            "name",
            "display_label",
            "recommendation_text",
            "chapter_title",
            "action_priority",
            "trigger_terms",
            "guideline_id",
            "guideline_title",
        }
        # display_label leads with the verbatim NICE recommendation so a
        # nurse-grade reader knows what the rule is for at a glance.
        assert first["display_label"].startswith(
            "Refer adults with unexplained haematuria"
        )
        assert first["action_priority"] == "2ww"
        assert first["trigger_terms"] == ["haematuria", "abdominal mass"]
        assert "logic_json" not in first

    def test_rules_endpoint_falls_back_to_chapter_when_no_recommendation(
        self,
    ) -> None:
        # When the recommendation text is missing the picker still needs
        # something readable -- the chapter title plus the first SNOMED
        # trigger is the documented fallback.
        from app.routers import test_patients as router

        client = FakeGraphClient(
            responses={
                "MATCH (rule:AppropriatenessRule)": [
                    {
                        "rule_id": "rule:NG12:v1:CH002:R002:xyz",
                        "name": "Rule 1.1.2",
                        "status": "active",
                        "recommendation_text": None,
                        "chapter_title": "1.1 -- Suspected cancer",
                        "action_priority": None,
                        "trigger_terms": ["weight loss"],
                        "guideline_id": "NG12",
                        "guideline_title": "Suspected cancer",
                    },
                ]
            }
        )
        original_client = router._client
        router._client = lambda: client  # type: ignore[assignment]
        try:
            rows = router.list_rules(
                guideline_id=None, q=None, limit=10, scope=None  # type: ignore[arg-type]
            )
        finally:
            router._client = original_client  # type: ignore[assignment]

        assert rows[0]["display_label"] == "1.1 -- Suspected cancer -- weight loss"

    def test_rules_endpoint_filters_by_q_substring(self) -> None:
        # The tree dialog drives a single substring search across rule,
        # chapter, recommendation, guideline and triggers -- so a nurse
        # can type a symptom (e.g. "haematuria") or a section (e.g.
        # "1.1.5") instead of a rule id.
        from app.routers import test_patients as router

        client = FakeGraphClient(
            responses={
                "MATCH (rule:AppropriatenessRule)": [
                    {
                        "rule_id": "rule:NG12:R001",
                        "name": "Rule 1.1.1",
                        "status": "active",
                        "recommendation_text": (
                            "Refer adults with haematuria for an X-ray."
                        ),
                        "chapter_title": "1.1 Cancer",
                        "trigger_terms": ["haematuria"],
                        "guideline_id": "NG12",
                        "guideline_title": "Suspected cancer",
                    },
                    {
                        "rule_id": "rule:NG28:R002",
                        "name": "HbA1c review",
                        "status": "active",
                        "recommendation_text": "Recheck HbA1c in 3 months.",
                        "chapter_title": "Monitoring",
                        "trigger_terms": ["raised HbA1c"],
                        "guideline_id": "NG28",
                        "guideline_title": "Type 2 diabetes",
                    },
                ]
            }
        )
        original_client = router._client
        router._client = lambda: client  # type: ignore[assignment]
        try:
            # Searching by symptom matches the recommendation text.
            rows = router.list_rules(
                guideline_id=None, q="haematuria", limit=10, scope=None,  # type: ignore[arg-type]
            )
            assert [r["rule_id"] for r in rows] == ["rule:NG12:R001"]
            # Searching by guideline title matches the parent label.
            rows = router.list_rules(
                guideline_id=None, q="diabetes", limit=10, scope=None,  # type: ignore[arg-type]
            )
            assert [r["rule_id"] for r in rows] == ["rule:NG28:R002"]
        finally:
            router._client = original_client  # type: ignore[assignment]

    def test_rules_endpoint_passes_guideline_filter_to_cypher(self) -> None:
        from app.routers import test_patients as router

        client = FakeGraphClient(
            responses={"MATCH (rule:AppropriatenessRule)": []}
        )
        original_client = router._client
        router._client = lambda: client  # type: ignore[assignment]
        try:
            router.list_rules(
                guideline_id="NG28",
                q=None,
                limit=100,
                scope=None,  # type: ignore[arg-type]
            )
        finally:
            router._client = original_client  # type: ignore[assignment]

        assert client.calls, "Cypher query should have been issued."
        _, params = client.calls[-1]
        assert params.get("guideline_id") == "NG28"


# ---------------------------------------------------------------------------
# TC-006 -- Legacy route removal sweep
# ---------------------------------------------------------------------------


class TestTC006LegacyRouteRemoval:
    """The /admin/guidance/test-patients route file no longer exists
    on disk -- only the supporting modules (api, dialogs, types)
    remain and they are now imported by the new Knowledge tab."""

    def test_legacy_page_route_is_deleted(self) -> None:
        import pathlib

        repo_root = pathlib.Path(__file__).resolve().parents[3]
        legacy_page = (
            repo_root
            / "services"
            / "ui"
            / "src"
            / "app"
            / "admin"
            / "guidance"
            / "test-patients"
            / "page.tsx"
        )
        assert not legacy_page.exists(), (
            "Legacy /admin/guidance/test-patients route should be removed; "
            f"page.tsx still exists at {legacy_page}"
        )

    def test_new_knowledge_tab_route_exists(self) -> None:
        import pathlib

        repo_root = pathlib.Path(__file__).resolve().parents[3]
        new_page = (
            repo_root
            / "services"
            / "ui"
            / "src"
            / "app"
            / "admin"
            / "knowledge"
            / "test-patients"
            / "page.tsx"
        )
        assert new_page.exists()


# ---------------------------------------------------------------------------
# TC-010 -- AI scaffold-from-rule (flow 1 of AI-assisted authoring)
# ---------------------------------------------------------------------------


class _ScaffoldFakeClient(FakeGraphClient):
    """Knowledge-graph stub for the scaffolder tests.

    Routes each Cypher fragment to a canned row set so we can exercise
    the whole load-rule -> build-blank -> stamp-ai -> patch-full
    pipeline without hitting Neo4j.
    """

    def __init__(
        self,
        *,
        rule_row: dict | None,
        present_concepts: set[str],
        new_patient_id: str = "test_ai_scaffold_001",
    ) -> None:
        super().__init__()
        self._rule_row = rule_row
        self._present_concepts = present_concepts
        self._new_patient_id = new_patient_id

    def run(self, cypher: str, **params: Any) -> list[dict]:  # type: ignore[override]
        self.calls.append((cypher, dict(params)))
        # READ_RULE_FOR_SCAFFOLD -- the unique signature is the
        # {id: $rule_id} binding (the picker query has no id binding).
        if "MATCH (rule:AppropriatenessRule {id: $rule_id})" in cypher:
            return [self._rule_row] if self._rule_row else []
        # CREATE_TEST_PATIENT_FOR_ASPECT
        if "CREATE (tp:TestPatient" in cypher and "$aspect" in cypher:
            return [{"id": self._new_patient_id}]
        # ASSERT_CONCEPTS_PRESENT
        if "missing" in cypher and "concept_ids" in cypher:
            asked = set(params.get("concept_ids") or [])
            return [{"missing": sorted(asked - self._present_concepts)}]
        # UPDATE_TEST_PATIENT_PROFILE -- "SET tp.name = $name" is the
        # signature line; the AI provenance stamp uses tp.aiAssisted
        # so we route the two writes apart.
        if "SET tp.name" in cypher and "tp.aiAssisted" not in cypher:
            return [{"id": params.get("id")}]
        # WRITE_EDITOR_ENCOUNTER returns the count, but the service
        # ignores the return value.
        return []


_GOOD_RULE_ROW = {
    "rule_id": "rule:NG12:R001",
    "rule_name": "2WW for visible haematuria >= 60",
    "recommendation_text": (
        "Refer adults aged >= 60 with unexplained visible haematuria using a "
        "suspected cancer pathway."
    ),
    "chapter_title": "Urological cancers",
    "guideline_id": "NG12",
    "guideline_title": "Suspected cancer: recognition and referral",
    "action_priority": "2WW",
    "triggers": [
        {
            "concept_id": "34436003",
            "preferred_term": "haematuria",
            "predicate": "EQ",
        }
    ],
    "demographic_constraints": [
        {"field": "age", "operator": ">=", "value": 60, "unit": "years"}
    ],
}


def _good_haiku_draft() -> dict:
    """Mimic a well-formed Haiku response for _GOOD_RULE_ROW."""
    return {
        "demographics": {
            "age": 67,
            "sex": "female",
            "display_hint": "Retired teacher with HTN",
        },
        "encounters": [
            {
                "source_label": "GP consultation",
                "date_offset_days": -5,
                "text": (
                    "67yo female. C/O 2 weeks of painless visible haematuria. "
                    "No dysuria. PMHx HTN. OE abdo soft. Urine dip blood +++. "
                    "Plan: 2WW urology referral."
                ),
            }
        ],
        "reviewer_focus": "Confirm 2WW urology rule fires on the haematuria mention.",
    }


class TestTC010ScaffoldFromRule:
    """AI scaffold-from-rule (flow 1 of AI-assisted test patient
    authoring). Verifies the rule reader, the LLM-response validator,
    the deterministic SBAR fill, the aiAssisted provenance stamp, and
    the loud-failure error paths.
    """

    _UNSET = object()

    def _scaffold(
        self,
        *,
        rule_row=_UNSET,
        draft: dict | None = None,
        present_concepts: set[str] | None = None,
        aspect: str = "summarisation",
    ):
        from app.services import test_patient_scaffolder

        if rule_row is self._UNSET:
            rule_row = _GOOD_RULE_ROW
        present_concepts = (
            present_concepts
            if present_concepts is not None
            else {"34436003"}
        )
        client = _ScaffoldFakeClient(
            rule_row=rule_row,
            present_concepts=present_concepts,
        )

        async def fake_generator(_system: str, _user: str) -> dict:
            return draft if draft is not None else _good_haiku_draft()

        result = test_patient_scaffolder.scaffold_patient_from_rule_sync(
            client,
            rule_id=(rule_row or {}).get("rule_id", "rule:none"),
            aspect=aspect,
            created_by="qa@example.com",
            generator=fake_generator,
        )
        return client, result

    def test_happy_path_writes_patient_and_stamps_provenance(self) -> None:
        from app.services.test_patient_scaffolder import ScaffoldResult

        client, result = self._scaffold()

        assert isinstance(result, ScaffoldResult)
        assert result.patient_id == "test_ai_scaffold_001"
        assert result.aspect == "summarisation"
        assert result.rule_id == "rule:NG12:R001"
        assert result.encounters_written == 1
        assert result.expected_sbar_written is True

        cyphers = [c for c, _ in client.calls]
        # 1. Rule read happens first.
        assert any("AppropriatenessRule {id: $rule_id}" in c for c in cyphers)
        # 2. Blank patient creation.
        assert any("CREATE (tp:TestPatient" in c for c in cyphers)
        # 3. AI provenance stamp.
        provenance_calls = [
            (c, p)
            for c, p in client.calls
            if "tp.aiAssisted" in c and "tp.aiSourceId" in c
        ]
        assert len(provenance_calls) == 1
        _, params = provenance_calls[0]
        assert params == {
            "id": "test_ai_scaffold_001",
            "rule_id": "rule:NG12:R001",
        }
        # 4. Concept pre-flight is enforced.
        assert any("missing" in c and "concept_ids" in c for c in cyphers)
        # 5. Encounter write happened.
        assert any("MERGE (tp)-[:HAS_ENCOUNTER]" in c or "HAS_ENCOUNTER" in c for c in cyphers)
        # 6. Expected SBAR write happened (summarisation aspect).
        assert any("MERGE (s:ExpectedSBAR" in c for c in cyphers)

    def test_expected_sbar_uses_rule_text_not_llm_words(self) -> None:
        """The deterministic SBAR fill: Recommendation must be the
        rule's verbatim recommendation, NOT anything the LLM wrote.
        Critical -- otherwise the test would check the AI against
        itself.
        """
        client, _ = self._scaffold()

        # SEED_EXPECTED_SBAR is the only write that carries
        # `recommendation_md`; the RESET cypher mentions ExpectedSBAR
        # too but as a delete, so we filter on the write parameter.
        sbar_calls = [
            (c, p)
            for c, p in client.calls
            if "MERGE (s:ExpectedSBAR" in c
        ]
        assert sbar_calls, "Expected SBAR write should have happened."
        _, params = sbar_calls[0]
        assert params["recommendation_md"].startswith(
            "Refer adults aged >= 60 with unexplained visible haematuria"
        )
        assert params["matched_rule_ids"] == ["rule:NG12:R001"]
        assert params["expected_action_priority"] == "2WW"

    def test_non_summarisation_aspect_skips_expected_sbar(self) -> None:
        client, result = self._scaffold(aspect="nlp")
        assert result.aspect == "nlp"
        assert result.expected_sbar_written is False
        assert not any(
            "MERGE (s:ExpectedSBAR" in c for c, _ in client.calls
        )

    def test_rejects_guidelines_aspect(self) -> None:
        from app.services.test_patient_scaffolder import ScaffoldError

        with pytest.raises(ScaffoldError, match="not supported"):
            self._scaffold(aspect="guidelines")

    def test_missing_rule_raises_scaffold_error(self) -> None:
        from app.services.test_patient_scaffolder import ScaffoldError

        with pytest.raises(ScaffoldError, match="not found"):
            self._scaffold(rule_row=None)

    def test_rule_with_no_triggers_is_rejected(self) -> None:
        from app.services.test_patient_scaffolder import ScaffoldError

        broken = dict(_GOOD_RULE_ROW, triggers=[])
        with pytest.raises(ScaffoldError, match="no SNOMED criteria"):
            self._scaffold(rule_row=broken)

    def test_llm_missing_keys_is_rejected(self) -> None:
        from app.services.test_patient_scaffolder import ScaffoldError

        bad = {"demographics": {"age": 67, "sex": "female"}}  # missing keys
        with pytest.raises(ScaffoldError, match="missing required keys"):
            self._scaffold(draft=bad)

    def test_llm_breaking_demographic_constraint_is_rejected(self) -> None:
        from app.services.test_patient_scaffolder import ScaffoldError

        too_young = _good_haiku_draft()
        too_young["demographics"]["age"] = 45  # rule needs age >= 60
        with pytest.raises(ScaffoldError, match="APPLIES_TO age"):
            self._scaffold(draft=too_young)

    def test_llm_skipping_a_trigger_term_is_rejected(self) -> None:
        from app.services.test_patient_scaffolder import ScaffoldError

        no_trigger = _good_haiku_draft()
        no_trigger["encounters"][0]["text"] = (
            "67yo female. Routine check. BP 130/80. Plan: continue current "
            "antihypertensives."
        )
        with pytest.raises(ScaffoldError, match="did not mention every trigger"):
            self._scaffold(draft=no_trigger)

    def test_llm_returning_error_dict_is_rejected(self) -> None:
        from app.services.test_patient_scaffolder import ScaffoldError

        with pytest.raises(ScaffoldError, match="did not return JSON"):
            self._scaffold(draft={"error": "bedrock timeout"})

    def test_router_endpoint_returns_scaffold_result(self) -> None:
        """Router smoke test: the endpoint translates the service
        result into the documented JSON shape."""
        from app.routers import test_patients as router
        from app.services import test_patient_scaffolder
        from app.services.test_patient_scaffolder import ScaffoldResult

        canned = ScaffoldResult(
            patient_id="test_ai_scaffold_002",
            aspect="summarisation",
            rule_id="rule:NG12:R001",
            encounters_written=1,
            expected_sbar_written=True,
            notes="Scaffolded a summarisation test patient against rule:NG12:R001.",
        )

        original = test_patient_scaffolder.scaffold_patient_from_rule_sync
        test_patient_scaffolder.scaffold_patient_from_rule_sync = (  # type: ignore[assignment]
            lambda *_a, **_kw: canned
        )
        try:
            body = router.ScaffoldFromRuleRequest(
                rule_id="rule:NG12:R001", aspect="summarisation"
            )
            payload = router.scaffold_from_rule(
                body, scope=None  # type: ignore[arg-type]
            )
        finally:
            test_patient_scaffolder.scaffold_patient_from_rule_sync = original  # type: ignore[assignment]

        assert payload == {
            "patient_id": "test_ai_scaffold_002",
            "aspect": "summarisation",
            "rule_id": "rule:NG12:R001",
            "encounters_written": 1,
            "expected_sbar_written": True,
            "notes": canned.notes,
        }

    def test_router_translates_scaffold_error_to_422(self) -> None:
        from fastapi import HTTPException
        from app.routers import test_patients as router
        from app.services import test_patient_scaffolder
        from app.services.test_patient_scaffolder import ScaffoldError

        def _raise(*_a, **_kw):
            raise ScaffoldError("rule not found")

        original = test_patient_scaffolder.scaffold_patient_from_rule_sync
        test_patient_scaffolder.scaffold_patient_from_rule_sync = _raise  # type: ignore[assignment]
        try:
            body = router.ScaffoldFromRuleRequest(
                rule_id="rule:missing", aspect="summarisation"
            )
            with pytest.raises(HTTPException) as exc_info:
                router.scaffold_from_rule(
                    body, scope=None  # type: ignore[arg-type]
                )
        finally:
            test_patient_scaffolder.scaffold_patient_from_rule_sync = original  # type: ignore[assignment]

        assert exc_info.value.status_code == 422
        assert "rule not found" in str(exc_info.value.detail)


# ---------------------------------------------------------------------------
# TC-011 -- AI scaffold-from-scenario (flow 2 of AI-assisted authoring)
# ---------------------------------------------------------------------------


class _ScenarioFakeClient(FakeGraphClient):
    """Knowledge-graph stub for the scenario-scaffolder tests.

    Routes Cypher fragments to canned rows so we can exercise the
    whole validate -> draft -> resolve -> evaluate -> persist pipeline
    without hitting Neo4j or the terminology API.
    """

    def __init__(
        self,
        *,
        present_concepts: set[str],
        new_patient_id: str = "test_ai_scenario_001",
    ) -> None:
        super().__init__()
        self._present_concepts = present_concepts
        self._new_patient_id = new_patient_id

    def run(self, cypher: str, **params: Any) -> list[dict]:  # type: ignore[override]
        self.calls.append((cypher, dict(params)))
        # CREATE_TEST_PATIENT_FOR_ASPECT
        if "CREATE (tp:TestPatient" in cypher and "$aspect" in cypher:
            return [{"id": self._new_patient_id}]
        # ASSERT_CONCEPTS_PRESENT
        if "missing" in cypher and "concept_ids" in cypher:
            asked = set(params.get("concept_ids") or [])
            return [{"missing": sorted(asked - self._present_concepts)}]
        # UPDATE_TEST_PATIENT_PROFILE -- "SET tp.name" is the
        # signature line; the AI provenance stamp uses tp.aiAssisted
        # so we route the two writes apart.
        if "SET tp.name" in cypher and "tp.aiAssisted" not in cypher:
            return [{"id": params.get("id")}]
        return []


def _good_scenario_draft() -> dict:
    """Mimic a well-formed Haiku response for a haematuria scenario."""
    return {
        "demographics": {
            "age": 67,
            "sex": "female",
            "display_hint": "Retired teacher with HTN",
        },
        "encounters": [
            {
                "source_label": "GP consultation",
                "date_offset_days": -5,
                "text": (
                    "67yo female. C/O 2/52 painless visible haematuria. "
                    "No dysuria. PMHx HTN. OE abdo soft. Urine dip "
                    "blood +++. Plan: 2WW urology referral."
                ),
                "terms": [
                    {
                        "surface_form": "visible haematuria",
                        "lookup_term": "haematuria",
                        "semantic_tag": "finding",
                        "assertion": "present",
                    },
                    {
                        "surface_form": "no dysuria",
                        "lookup_term": "dysuria",
                        "semantic_tag": "finding",
                        "assertion": "absent",
                    },
                    {
                        "surface_form": "PMHx HTN",
                        "lookup_term": "hypertension",
                        "semantic_tag": "disorder",
                        "assertion": "history_of",
                    },
                ],
            }
        ],
        "reviewer_focus": (
            "Confirm 2WW urology rule fires on the haematuria mention."
        ),
    }


def _scenario_resolver(known: dict[str, tuple[str, str, float]]):
    """Build a fake terminology resolver from a {term: (cid, pt, score)} map."""

    def _resolve(terms: list[str]) -> dict[str, list[Any]]:
        out: dict[str, list[Any]] = {}
        for term in terms:
            hit = known.get(term.lower())
            if hit is None:
                out[term] = []
                continue
            cid, preferred, score = hit
            out[term] = [
                {
                    "concept_id": cid,
                    "term": preferred,
                    "score": score,
                }
            ]
        return out

    return _resolve


_GOOD_RESOLVER_HITS: dict[str, tuple[str, str, float]] = {
    "haematuria": ("34436003", "Haematuria", 0.96),
    "dysuria": ("49650001", "Dysuria", 0.94),
    "hypertension": ("38341003", "Hypertensive disorder", 0.92),
}


def _good_evaluator_result() -> dict:
    return {
        "matched_rules": [
            {
                "rule_id": "rule:NG12:R001",
                "name": "2WW for visible haematuria >= 60",
                "recommendation_verbatim": (
                    "Refer adults aged >= 60 with unexplained visible "
                    "haematuria using a suspected cancer pathway."
                ),
                "action": "2ww",
                "guideline_title": "Suspected cancer: recognition and referral",
                "chapter_title": "Urological cancers",
            },
            {
                "rule_id": "rule:NG12:R777",
                "name": "Routine BP review",
                "recommendation_verbatim": "Annual BP review for hypertension.",
                "action": "routine",
                "guideline_title": "Hypertension in adults",
                "chapter_title": "Monitoring",
            },
        ]
    }


class TestTC011ScaffoldFromScenario:
    """AI scaffold-from-scenario (flow 2 of AI-assisted authoring).

    Verifies the scenario validator, the LLM-response shape check,
    the terminology resolver pass (resolved + unresolved), the rule
    engine wiring, the deterministic SBAR fill, the aiAssisted
    provenance stamp, and the loud-failure error paths.
    """

    _UNSET = object()

    def _scaffold(
        self,
        *,
        scenario: str = (
            "67yo woman with 2-week painless visible haematuria, "
            "BP 140/85, PMHx HTN."
        ),
        draft=_UNSET,
        resolver_hits: dict[str, tuple[str, str, float]] | None = _UNSET,  # type: ignore[assignment]
        eval_result: dict | None | object = _UNSET,
        present_concepts: set[str] | None = None,
        aspect: str = "summarisation",
    ):
        from app.services import test_patient_scenario_scaffolder

        if draft is self._UNSET:
            draft = _good_scenario_draft()
        if resolver_hits is self._UNSET:
            resolver_hits = _GOOD_RESOLVER_HITS
        if eval_result is self._UNSET:
            eval_result = _good_evaluator_result()
        present_concepts = (
            present_concepts
            if present_concepts is not None
            else {"34436003", "49650001", "38341003"}
        )
        client = _ScenarioFakeClient(present_concepts=present_concepts)

        async def fake_generator(_system: str, _user: str) -> dict:
            return draft if isinstance(draft, dict) else {"error": str(draft)}

        def fake_evaluator(_payload):
            return eval_result if isinstance(eval_result, dict) else {}

        result = (
            test_patient_scenario_scaffolder.scaffold_patient_from_scenario_sync(
                client,
                scenario=scenario,
                aspect=aspect,
                created_by="qa@example.com",
                generator=fake_generator,
                resolver=_scenario_resolver(resolver_hits or {}),
                evaluator=fake_evaluator,
            )
        )
        return client, result

    # -- happy paths -------------------------------------------------

    def test_happy_path_writes_patient_resolves_terms_and_predicts_rules(self) -> None:
        from app.services.test_patient_scenario_scaffolder import (
            ScenarioScaffoldResult,
        )

        client, result = self._scaffold()

        assert isinstance(result, ScenarioScaffoldResult)
        assert result.patient_id == "test_ai_scenario_001"
        assert result.aspect == "summarisation"
        assert result.encounters_written == 1
        assert result.expected_sbar_written is True
        # All three terms resolved.
        assert sorted(r.concept_id for r in result.resolved_terms) == sorted(
            ["34436003", "38341003", "49650001"]
        )
        assert result.unresolved_terms == []
        # Top matched rule is the 2WW rule (urgency wins over routine).
        assert result.matched_rules[0].rule_id == "rule:NG12:R001"
        assert result.matched_rules[0].action_priority == "2ww"

        cyphers = [c for c, _ in client.calls]
        # Blank patient creation happens.
        assert any("CREATE (tp:TestPatient" in c for c in cyphers)
        # AI provenance stamp uses scenario kind, not rule.
        provenance_calls = [
            (c, p)
            for c, p in client.calls
            if "tp.aiAssisted" in c and "tp.aiSourceText" in c
        ]
        assert len(provenance_calls) == 1
        _, params = provenance_calls[0]
        assert params["id"] == "test_ai_scenario_001"
        assert "haematuria" in params["scenario"]
        # Concept pre-flight is enforced before the encounter write.
        assert any("missing" in c and "concept_ids" in c for c in cyphers)
        # Expected SBAR write happened (summarisation aspect).
        assert any("MERGE (s:ExpectedSBAR" in c for c in cyphers)

    def test_expected_sbar_uses_top_priority_rule_not_llm_words(self) -> None:
        """Deterministic SBAR fill: Recommendation must be the top
        matched rule's verbatim recommendation, NOT anything the LLM
        wrote. Action priority must be the rule engine's verdict.
        """
        client, _ = self._scaffold()

        sbar_calls = [
            (c, p) for c, p in client.calls if "MERGE (s:ExpectedSBAR" in c
        ]
        assert sbar_calls, "Expected SBAR write should have happened."
        _, params = sbar_calls[0]
        assert params["recommendation_md"].startswith(
            "Refer adults aged >= 60 with unexplained visible haematuria"
        )
        assert params["matched_rule_ids"] == [
            "rule:NG12:R001",
            "rule:NG12:R777",
        ]
        assert params["expected_action_priority"] == "2ww"

    def test_no_rules_fired_seeds_no_referral_skeleton(self) -> None:
        """When the rule engine returns no matches the SBAR is still
        seeded with a 'no referral' skeleton so the reviewer has a
        starting point.
        """
        client, result = self._scaffold(eval_result={"matched_rules": []})

        assert result.matched_rules == []
        sbar_calls = [
            (c, p) for c, p in client.calls if "MERGE (s:ExpectedSBAR" in c
        ]
        assert sbar_calls
        _, params = sbar_calls[0]
        assert "No rule fires" in params["recommendation_md"]
        assert params["matched_rule_ids"] == []
        assert params["expected_action_priority"] is None

    def test_unresolved_terms_are_returned_for_reviewer_to_fix(self) -> None:
        """Terms the resolver does not return are surfaced as
        unresolved so the reviewer can fix them in the editor. The
        scaffold still succeeds as long as at least some terms
        resolved.
        """
        partial = {
            "haematuria": ("34436003", "Haematuria", 0.96),
            # dysuria and hypertension intentionally missing
        }
        client, result = self._scaffold(resolver_hits=partial)

        resolved_lookups = {r.lookup_term for r in result.resolved_terms}
        unresolved_lookups = {r.lookup_term for r in result.unresolved_terms}
        assert resolved_lookups == {"haematuria"}
        assert unresolved_lookups == {"dysuria", "hypertension"}
        # Per-encounter codes should only carry the resolved one.
        # The fake client's WRITE_EDITOR_ENCOUNTER call carries the
        # codes via $codes; we look it up from the recorded calls.
        encounter_writes = [
            (c, p)
            for c, p in client.calls
            if ":HAS_ENCOUNTER" in c or "(enc:Encounter" in c
        ]
        assert encounter_writes, "Encounter write should have happened."

    def test_low_score_term_is_treated_as_unresolved(self) -> None:
        """Terms whose top-1 candidate scored below the floor are
        treated as unresolved so we never write a bad SNOMED code.
        """
        weak = {
            "haematuria": ("34436003", "Haematuria", 0.96),
            "dysuria": ("49650001", "Dysuria", 0.94),
            # Hypertension scores below the 0.45 floor.
            "hypertension": ("38341003", "Hypertensive disorder", 0.10),
        }
        _, result = self._scaffold(resolver_hits=weak)

        unresolved = {r.lookup_term for r in result.unresolved_terms}
        assert "hypertension" in unresolved

    def test_non_summarisation_aspect_skips_expected_sbar_and_evaluator(self) -> None:
        eval_called = {"hit": False}

        def _evaluator(_payload):
            eval_called["hit"] = True
            return {}

        from app.services import test_patient_scenario_scaffolder

        client = _ScenarioFakeClient(
            present_concepts={"34436003", "49650001", "38341003"}
        )

        async def gen(_s, _u):
            return _good_scenario_draft()

        result = (
            test_patient_scenario_scaffolder.scaffold_patient_from_scenario_sync(
                client,
                scenario="67yo woman with haematuria.",
                aspect="nlp",
                created_by="qa@example.com",
                generator=gen,
                resolver=_scenario_resolver(_GOOD_RESOLVER_HITS),
                evaluator=_evaluator,
            )
        )

        assert result.aspect == "nlp"
        assert result.expected_sbar_written is False
        assert result.matched_rules == []
        assert eval_called["hit"] is False
        assert not any(
            "MERGE (s:ExpectedSBAR" in c for c, _ in client.calls
        )

    # -- loud-failure paths -----------------------------------------

    def test_rejects_guidelines_aspect(self) -> None:
        from app.services.test_patient_scenario_scaffolder import (
            ScenarioScaffoldError,
        )

        with pytest.raises(ScenarioScaffoldError, match="not supported"):
            self._scaffold(aspect="guidelines")

    def test_too_short_scenario_is_rejected_before_llm_call(self) -> None:
        from app.services.test_patient_scenario_scaffolder import (
            ScenarioScaffoldError,
        )

        with pytest.raises(ScenarioScaffoldError, match="too short"):
            self._scaffold(scenario="hi")

    def test_too_long_scenario_is_rejected(self) -> None:
        from app.services.test_patient_scenario_scaffolder import (
            ScenarioScaffoldError,
        )

        long_text = "x" * 3000
        with pytest.raises(ScenarioScaffoldError, match="too long"):
            self._scaffold(scenario=long_text)

    def test_llm_missing_keys_is_rejected(self) -> None:
        from app.services.test_patient_scenario_scaffolder import (
            ScenarioScaffoldError,
        )

        bad = {"demographics": {"age": 67, "sex": "female"}}
        with pytest.raises(ScenarioScaffoldError, match="missing required keys"):
            self._scaffold(draft=bad)

    def test_llm_returning_error_dict_is_rejected(self) -> None:
        from app.services.test_patient_scenario_scaffolder import (
            ScenarioScaffoldError,
        )

        with pytest.raises(ScenarioScaffoldError, match="did not return JSON"):
            self._scaffold(draft={"error": "bedrock timeout"})

    def test_no_terms_extracted_is_rejected(self) -> None:
        """A scenario with no clinical terms is unusable -- we surface
        the error rather than save an empty patient."""
        from app.services.test_patient_scenario_scaffolder import (
            ScenarioScaffoldError,
        )

        empty_terms = _good_scenario_draft()
        empty_terms["encounters"][0]["terms"] = []
        with pytest.raises(
            ScenarioScaffoldError, match="did not pick out any clinical terms"
        ):
            self._scaffold(draft=empty_terms)

    def test_resolver_outage_raises_loud_failure(self) -> None:
        from app.services import test_patient_scenario_scaffolder
        from app.services.test_patient_scenario_scaffolder import (
            ScenarioScaffoldError,
        )

        client = _ScenarioFakeClient(present_concepts=set())

        async def gen(_s, _u):
            return _good_scenario_draft()

        def broken_resolver(_terms: list[str]):
            raise RuntimeError("terminology API timeout")

        with pytest.raises(
            ScenarioScaffoldError, match="terminology service"
        ):
            test_patient_scenario_scaffolder.scaffold_patient_from_scenario_sync(
                client,
                scenario="67yo woman with haematuria.",
                aspect="summarisation",
                created_by="qa@example.com",
                generator=gen,
                resolver=broken_resolver,
                evaluator=lambda _p: _good_evaluator_result(),
            )

    def test_evaluator_outage_raises_loud_failure_for_summarisation(self) -> None:
        from app.services import test_patient_scenario_scaffolder
        from app.services.test_patient_scenario_scaffolder import (
            ScenarioScaffoldError,
        )

        client = _ScenarioFakeClient(
            present_concepts={"34436003", "49650001", "38341003"}
        )

        async def gen(_s, _u):
            return _good_scenario_draft()

        def broken_evaluator(_payload):
            raise RuntimeError("rule engine 502")

        with pytest.raises(
            ScenarioScaffoldError, match="rule engine"
        ):
            test_patient_scenario_scaffolder.scaffold_patient_from_scenario_sync(
                client,
                scenario="67yo woman with haematuria.",
                aspect="summarisation",
                created_by="qa@example.com",
                generator=gen,
                resolver=_scenario_resolver(_GOOD_RESOLVER_HITS),
                evaluator=broken_evaluator,
            )

    # -- router smoke tests -----------------------------------------

    def test_router_endpoint_returns_scaffold_result(self) -> None:
        from app.routers import test_patients as router
        from app.services import test_patient_scenario_scaffolder
        from app.services.test_patient_scenario_scaffolder import (
            MatchedRuleRow,
            ResolvedTermRow,
            ScenarioScaffoldResult,
        )

        canned = ScenarioScaffoldResult(
            patient_id="test_ai_scenario_002",
            aspect="summarisation",
            scenario="67yo woman with haematuria.",
            encounters_written=1,
            expected_sbar_written=True,
            resolved_terms=[
                ResolvedTermRow(
                    surface_form="visible haematuria",
                    lookup_term="haematuria",
                    semantic_tag="finding",
                    assertion="present",
                    concept_id="34436003",
                    preferred_term="Haematuria",
                    score=0.96,
                )
            ],
            unresolved_terms=[],
            matched_rules=[
                MatchedRuleRow(
                    rule_id="rule:NG12:R001",
                    name="2WW haematuria",
                    recommendation_verbatim="Refer using 2WW pathway.",
                    action_priority="2ww",
                    guideline_title="Suspected cancer",
                    chapter_title="Urological",
                )
            ],
            notes="Scaffolded a summarisation test patient.",
        )

        original = (
            test_patient_scenario_scaffolder.scaffold_patient_from_scenario_sync
        )
        test_patient_scenario_scaffolder.scaffold_patient_from_scenario_sync = (  # type: ignore[assignment]
            lambda *_a, **_kw: canned
        )
        try:
            body = router.ScaffoldFromScenarioRequest(
                scenario="67yo woman with haematuria.",
                aspect="summarisation",
            )
            payload = router.scaffold_from_scenario(
                body, scope=None  # type: ignore[arg-type]
            )
        finally:
            test_patient_scenario_scaffolder.scaffold_patient_from_scenario_sync = (  # type: ignore[assignment]
                original
            )

        assert payload["patient_id"] == "test_ai_scenario_002"
        assert payload["aspect"] == "summarisation"
        assert payload["scenario"] == "67yo woman with haematuria."
        assert payload["encounters_written"] == 1
        assert payload["expected_sbar_written"] is True
        assert payload["resolved_terms"][0]["concept_id"] == "34436003"
        assert payload["unresolved_terms"] == []
        assert payload["matched_rules"][0]["rule_id"] == "rule:NG12:R001"
        assert payload["matched_rules"][0]["action_priority"] == "2ww"

    def test_router_translates_scaffold_error_to_422(self) -> None:
        from fastapi import HTTPException
        from app.routers import test_patients as router
        from app.services import test_patient_scenario_scaffolder
        from app.services.test_patient_scenario_scaffolder import (
            ScenarioScaffoldError,
        )

        def _raise(*_a, **_kw):
            raise ScenarioScaffoldError("scenario too short")

        original = (
            test_patient_scenario_scaffolder.scaffold_patient_from_scenario_sync
        )
        test_patient_scenario_scaffolder.scaffold_patient_from_scenario_sync = (  # type: ignore[assignment]
            _raise
        )
        try:
            body = router.ScaffoldFromScenarioRequest(
                scenario="hi there friend",
                aspect="summarisation",
            )
            with pytest.raises(HTTPException) as exc_info:
                router.scaffold_from_scenario(
                    body, scope=None  # type: ignore[arg-type]
                )
        finally:
            test_patient_scenario_scaffolder.scaffold_patient_from_scenario_sync = (  # type: ignore[assignment]
                original
            )

        assert exc_info.value.status_code == 422
        assert "scenario too short" in str(exc_info.value.detail)


# ---------------------------------------------------------------------------
# TC-012 -- Triage outcome filter + counts (NG12 / referral-triage pass)
# ---------------------------------------------------------------------------


class TestTC012TriageOutcomeFilter:
    """The SBAR aspect IS the referral-triage aspect. The list query
    surfaces a derived `triage_outcome` (2ww / urgent / routine /
    no_rule_fired / evaluator_outage / unset) so the Knowledge tab
    can offer a chip-group filter inside the SBAR aspect, and a
    counts endpoint backs the chip badges. The derivation lives in
    Cypher so it is consistent across the list + count paths.
    """

    def test_list_cypher_derives_triage_outcome_from_expected_sbar(self) -> None:
        # The same CASE expression appears in both the list query and
        # the count query so the chip badge count and the filtered
        # row count agree.
        from libs.cypher.test_patient_queries import (
            COUNT_TEST_PATIENTS_BY_TRIAGE_OUTCOME,
            LIST_TEST_PATIENTS,
        )

        for cypher in (LIST_TEST_PATIENTS, COUNT_TEST_PATIENTS_BY_TRIAGE_OUTCOME):
            assert "OPTIONAL MATCH (tp)-[:HAS_EXPECTED_SBAR]->(s:ExpectedSBAR)" in cypher
            assert "coalesce(s.evaluator_outage, false)" in cypher
            assert "s.expected_action_priority IS NOT NULL" in cypher
            assert "size(coalesce(s.matched_rule_ids, [])) = 0" in cypher
            assert "'no_rule_fired'" in cypher
            assert "'evaluator_outage'" in cypher

    def test_list_cypher_filters_on_triage_outcome_param(self) -> None:
        # The filter respects 'all' (no filter), exact match, and the
        # special 'unset' value used for non-summarisation patients
        # that have no ExpectedSBAR node.
        from libs.cypher.test_patient_queries import LIST_TEST_PATIENTS

        assert "$triage_outcome IS NULL" in LIST_TEST_PATIENTS
        assert "$triage_outcome = 'all'" in LIST_TEST_PATIENTS
        assert "triage_outcome = $triage_outcome" in LIST_TEST_PATIENTS
        assert (
            "$triage_outcome = 'unset' AND triage_outcome IS NULL"
            in LIST_TEST_PATIENTS
        )
        assert "triage_outcome     AS triage_outcome" in LIST_TEST_PATIENTS

    def test_count_query_only_sees_summarisation_patients(self) -> None:
        # The chip group only makes sense for the SBAR / referral-
        # triage aspect -- the other three aspects do not have an
        # ExpectedSBAR node and so do not have a triage outcome. The
        # WHERE clause guarantees the chip badges never count NLP
        # or Episodes patients.
        from libs.cypher.test_patient_queries import (
            COUNT_TEST_PATIENTS_BY_TRIAGE_OUTCOME,
        )

        assert (
            "coalesce(tp.aspect, 'guidelines') = 'summarisation'"
            in COUNT_TEST_PATIENTS_BY_TRIAGE_OUTCOME
        )
        assert "RETURN triage_outcome" in COUNT_TEST_PATIENTS_BY_TRIAGE_OUTCOME

    def test_list_patients_passes_triage_outcome_through(self) -> None:
        from app.services import test_patient_service

        client = FakeGraphClient()
        test_patient_service.list_patients(
            client,
            aspect="summarisation",
            triage_outcome="2ww",
        )
        _, params = client.calls[0]
        assert params["aspect"] == "summarisation"
        assert params["triage_outcome"] == "2ww"

    def test_list_patients_normalises_unknown_triage_outcome_to_none(self) -> None:
        # Same defensive behaviour as the aspect filter: a typo in a
        # query string should never 500 the API, it should just stop
        # filtering by outcome.
        from app.services import test_patient_service

        client = FakeGraphClient()
        test_patient_service.list_patients(
            client,
            aspect="summarisation",
            triage_outcome="bogus",
        )
        _, params = client.calls[0]
        assert params["triage_outcome"] is None

    def test_list_patients_normalises_all_triage_outcome_to_none(self) -> None:
        from app.services import test_patient_service

        client = FakeGraphClient()
        test_patient_service.list_patients(
            client,
            triage_outcome="all",
        )
        _, params = client.calls[0]
        assert params["triage_outcome"] is None

    def test_count_by_triage_outcome_pads_zero_rows(self) -> None:
        # The counts endpoint always returns one entry per known
        # outcome (zero when none) so the UI can render a stable
        # chip group without conditional logic.
        from app.services import test_patient_service

        client = FakeGraphClient(
            responses={
                "COUNT_TEST_PATIENTS_BY_TRIAGE_OUTCOME_KEY": [],
                "coalesce(tp.aspect, 'guidelines') = 'summarisation'": [
                    {"triage_outcome": "2ww", "total": 4},
                    {"triage_outcome": "routine", "total": 1},
                    {"triage_outcome": "no_rule_fired", "total": 1},
                ],
            }
        )
        counts = test_patient_service.count_by_triage_outcome(client)
        assert counts == {
            "2ww": 4,
            "urgent": 0,
            "routine": 1,
            "no_rule_fired": 1,
            "evaluator_outage": 0,
            "unset": 0,
        }

    def test_count_by_triage_outcome_drops_unknown_outcome_rows(self) -> None:
        # Defensive: if the graph ever contains a value outside the
        # canonical vocabulary (e.g. an old fixture) we drop it
        # rather than letting the chip group grow unexpected entries.
        from app.services import test_patient_service

        client = FakeGraphClient(
            responses={
                "coalesce(tp.aspect, 'guidelines') = 'summarisation'": [
                    {"triage_outcome": "2ww", "total": 2},
                    {"triage_outcome": "stop", "total": 9},
                ],
            }
        )
        counts = test_patient_service.count_by_triage_outcome(client)
        assert counts["2ww"] == 2
        assert "stop" not in counts

    def test_router_endpoint_passes_triage_outcome_through(self) -> None:
        # The router converts the FastAPI Query into a service call
        # so the chip-driven URL ?triage_outcome=2ww filters server-
        # side, not client-side.
        from app.routers import test_patients as router
        from app.services import test_patient_service

        captured: dict[str, Any] = {}

        def _fake_list(_client, **kw):
            captured.update(kw)
            return []

        original = test_patient_service.list_patients
        test_patient_service.list_patients = _fake_list  # type: ignore[assignment]
        try:
            router.list_patients(
                aspect="summarisation",
                guideline_id=None,
                rule_id=None,
                node_id=None,
                triage_outcome="2ww",
                limit=200,
                scope=None,  # type: ignore[arg-type]
            )
        finally:
            test_patient_service.list_patients = original  # type: ignore[assignment]
        assert captured.get("triage_outcome") == "2ww"
        assert captured.get("aspect") == "summarisation"

    def test_router_endpoint_returns_triage_outcome_counts(self) -> None:
        from app.routers import test_patients as router
        from app.services import test_patient_service

        called: dict[str, bool] = {"hit": False}

        def _fake_count(_client):
            called["hit"] = True
            return {
                "2ww": 4,
                "urgent": 1,
                "routine": 1,
                "no_rule_fired": 1,
                "evaluator_outage": 0,
                "unset": 0,
            }

        original = test_patient_service.count_by_triage_outcome
        test_patient_service.count_by_triage_outcome = _fake_count  # type: ignore[assignment]
        try:
            result = router.get_triage_outcome_counts(scope=None)  # type: ignore[arg-type]
        finally:
            test_patient_service.count_by_triage_outcome = original  # type: ignore[assignment]
        assert called["hit"] is True
        assert result["2ww"] == 4
        assert set(result.keys()) == {
            "2ww",
            "urgent",
            "routine",
            "no_rule_fired",
            "evaluator_outage",
            "unset",
        }


# ---------------------------------------------------------------------------
# TC-014 -- Rule logic_json walker (criteria + demographic constraints)
# ---------------------------------------------------------------------------


# A real-shaped logic tree pulled from
# rule:NG12:v1:CH002:SEC000:R004 (NICE NG12 mesothelioma 2WW). Trimmed
# down to keep the fixture readable but preserves the production
# structure: a top-level AND with a demographic leaf, an OR of three
# sibling AT_LEAST groups, and concept leaves nested inside AT_LEAST.
# Some concepts deliberately repeat across branches so we can pin the
# de-dup behaviour. See _logic_tree.parse_logic_json for the wire shape.
_REAL_LOGIC_TREE = {
    "kind": "AND",
    "children": [
        {
            "kind": "demographic",
            "field": "age",
            "operator": ">=",
            "value": 40,
            "unit": "years",
        },
        {
            "kind": "OR",
            "children": [
                {
                    "kind": "AT_LEAST",
                    "min": 2,
                    "children": [
                        {
                            "kind": "concept",
                            "criterion": {
                                "snomed_concept_id": "49727002",
                                "preferred_term": "Cough (finding)",
                                "term": "cough",
                            },
                        },
                        {
                            "kind": "concept",
                            "criterion": {
                                "snomed_concept_id": "267036007",
                                "preferred_term": "Dyspnea (finding)",
                                "term": "dyspnoea",
                            },
                        },
                    ],
                },
                {
                    "kind": "concept",
                    "criterion": {
                        "snomed_concept_id": "49727002",
                        "preferred_term": "Cough (finding)",
                        "term": "cough",
                    },
                },
                {
                    "kind": "concept",
                    "criterion": {
                        "snomed_concept_id": "161635002",
                        "preferred_term": "History of asbestos exposure (situation)",
                    },
                },
            ],
        },
    ],
}


class TestTC014LogicTreeWalker:
    """Pin the shared logic-tree walker that the scaffolder + picker
    both consume. The walker replaces the broken
    ``:HAS_CRITERIA_GROUP`` / ``:APPLIES_TO`` cypher walks -- production
    rules persist criteria inside ``rule.logicJson`` only.
    """

    def test_extract_concept_triggers_walks_nested_groups_and_dedupes(self) -> None:
        from app.services._logic_tree import extract_concept_triggers

        triggers = extract_concept_triggers(_REAL_LOGIC_TREE)
        ids = [t["concept_id"] for t in triggers]
        # Cough appears 3 times in the tree -- once in AT_LEAST, once
        # in the parent OR, and not in the asbestos branch -- and must
        # collapse to a single trigger.
        assert ids.count("49727002") == 1
        assert set(ids) == {"49727002", "267036007", "161635002"}
        # Every trigger keeps the field shape the LLM prompt + the
        # validator expect.
        first = triggers[0]
        assert set(first.keys()) == {
            "concept_id",
            "preferred_term",
            "predicate",
        }
        assert first["predicate"] == "LOGIC"

    def test_extract_concept_triggers_falls_back_to_term_then_id(self) -> None:
        from app.services._logic_tree import extract_concept_triggers

        tree = {
            "kind": "OR",
            "children": [
                {
                    "kind": "concept",
                    "criterion": {
                        "snomed_concept_id": "111",
                        "term": "short label only",
                    },
                },
                {
                    "kind": "concept",
                    "criterion": {"snomed_concept_id": "222"},  # nothing else
                },
            ],
        }
        triggers = extract_concept_triggers(tree)
        labels = {t["concept_id"]: t["preferred_term"] for t in triggers}
        assert labels["111"] == "short label only"
        assert labels["222"] == "222"

    def test_extract_demographic_constraints_returns_field_op_value(self) -> None:
        from app.services._logic_tree import extract_demographic_constraints

        constraints = extract_demographic_constraints(_REAL_LOGIC_TREE)
        assert constraints == [
            {"field": "age", "operator": ">=", "value": 40, "unit": "years"}
        ]

    def test_parse_logic_json_accepts_string_dict_or_garbage(self) -> None:
        from app.services._logic_tree import parse_logic_json

        # Real production payload: a JSON-encoded string.
        encoded = (
            '{"kind": "concept", '
            '"criterion": {"snomed_concept_id": "49727002"}}'
        )
        assert parse_logic_json(encoded) == {
            "kind": "concept",
            "criterion": {"snomed_concept_id": "49727002"},
        }
        # Already-decoded dicts pass through.
        decoded = {"kind": "AND", "children": []}
        assert parse_logic_json(decoded) is decoded
        # Garbage is tolerated -- callers branch on None.
        assert parse_logic_json("not-json") is None
        assert parse_logic_json("") is None
        assert parse_logic_json(None) is None
        assert parse_logic_json(["a", "b"]) is None

    def test_trigger_terms_preview_returns_first_three_in_order(self) -> None:
        from app.services._logic_tree import trigger_terms_preview

        preview = trigger_terms_preview(_REAL_LOGIC_TREE, limit=3)
        # Document-order is Cough, Dyspnea, then the asbestos history
        # (Cough's repeat is dropped by extract_concept_triggers).
        assert preview == [
            "Cough (finding)",
            "Dyspnea (finding)",
            "History of asbestos exposure (situation)",
        ]
        assert trigger_terms_preview(_REAL_LOGIC_TREE, limit=2) == [
            "Cough (finding)",
            "Dyspnea (finding)",
        ]
        assert trigger_terms_preview(None, limit=3) == []


# ---------------------------------------------------------------------------
# TC-015 -- Rule lookup queries pin the logicJson contract
# ---------------------------------------------------------------------------


class TestTC015RuleLookupQueriesUseLogicJson:
    """Regression invariants for the two cypher queries that read a rule
    for the test-patient library. Both used to walk
    ``:HAS_CRITERIA_GROUP -> :CriteriaGroup -> :HAS_CRITERIA`` and
    ``:APPLIES_TO``, but those labels / relationships do not exist in
    the production knowledge graph (the v2 writer persists the criteria
    inside ``rule.logicJson``). Without these tests the silent regression
    came back as "Rule X has no SNOMED criteria attached" for every
    real NG12 / NG78 / TA rule the reviewer tried to scaffold.
    """

    def test_read_rule_for_scaffold_returns_logic_json(self) -> None:
        from libs.cypher.test_patient_queries import READ_RULE_FOR_SCAFFOLD

        assert "rule.logicJson" in READ_RULE_FOR_SCAFFOLD
        assert "AS logic_json" in READ_RULE_FOR_SCAFFOLD

    def test_read_rule_for_scaffold_drops_broken_graph_walks(self) -> None:
        from libs.cypher.test_patient_queries import READ_RULE_FOR_SCAFFOLD

        assert ":HAS_CRITERIA_GROUP" not in READ_RULE_FOR_SCAFFOLD
        assert ":CriteriaGroup" not in READ_RULE_FOR_SCAFFOLD
        assert ":APPLIES_TO" not in READ_RULE_FOR_SCAFFOLD

    def test_list_rules_for_picker_returns_logic_json(self) -> None:
        from libs.cypher.test_patient_queries import LIST_RULES_FOR_PICKER

        assert "rule.logicJson" in LIST_RULES_FOR_PICKER
        assert "AS logic_json" in LIST_RULES_FOR_PICKER

    def test_list_rules_for_picker_drops_broken_graph_walks(self) -> None:
        from libs.cypher.test_patient_queries import LIST_RULES_FOR_PICKER

        assert ":HAS_CRITERIA_GROUP" not in LIST_RULES_FOR_PICKER
        assert ":CriteriaGroup" not in LIST_RULES_FOR_PICKER


# ---------------------------------------------------------------------------
# TC-016 -- load_rule_for_scaffold derives triggers from logic_json
# ---------------------------------------------------------------------------


class TestTC016LoadRuleForScaffold:
    """End-to-end pin: the scaffolder's rule reader walks ``logic_json``
    to derive the trigger list and demographic constraints, so the
    "no SNOMED criteria attached" error no longer fires for production
    rules.
    """

    def _row(self, **overrides: Any) -> dict:
        base = {
            "rule_id": "rule:NG12:v1:CH002:SEC000:R004:53e182a2",
            "rule_name": "Rule: 1.1.5",
            "recommendation_text": (
                "Offer an urgent chest X-ray (within 2 weeks) to assess "
                "for mesothelioma in people aged 40 and over."
            ),
            "chapter_title": "Recommendations organised by site of cancer",
            "guideline_id": "NG12",
            "guideline_title": "Suspected cancer: recognition and referral",
            "action_priority": "2ww",
            "logic_json": json.dumps(_REAL_LOGIC_TREE),
        }
        base.update(overrides)
        return base

    def test_derives_triggers_and_constraints_from_logic_json(self) -> None:
        from app.services.test_patient_scaffolder import load_rule_for_scaffold

        client = _ScaffoldFakeClient(
            rule_row=self._row(),
            present_concepts={"49727002", "267036007", "161635002"},
        )
        loaded = load_rule_for_scaffold(
            client, rule_id="rule:NG12:v1:CH002:SEC000:R004:53e182a2"
        )
        # ``triggers`` is the satisfying-path subset the LLM must
        # mention. The trimmed mesothelioma tree's OR has three
        # children: AT_LEAST 2 of [Cough, Dyspnea] (size 2), Cough
        # alone (size 1), and Asbestos alone (size 1). The walker
        # picks the smallest non-empty branch in document order ->
        # just Cough fires the rule.
        ids = [t["concept_id"] for t in loaded["triggers"]]
        assert ids == ["49727002"]
        # ``all_triggers`` keeps the full union for any UI surface
        # that wants to show the complete trigger space alongside the
        # briefing list.
        all_ids = {t["concept_id"] for t in loaded["all_triggers"]}
        assert all_ids == {"49727002", "267036007", "161635002"}
        assert loaded["demographic_constraints"] == [
            {
                "field": "age",
                "operator": ">=",
                "value": 40,
                "unit": "years",
            }
        ]
        # Other fields the prompt formatter needs are passed through.
        assert loaded["action_priority"] == "2ww"
        assert loaded["rule_id"] == "rule:NG12:v1:CH002:SEC000:R004:53e182a2"

    def test_logic_json_with_no_concept_leaves_raises_scaffold_error(
        self,
    ) -> None:
        from app.services.test_patient_scaffolder import (
            ScaffoldError,
            load_rule_for_scaffold,
        )

        # Demographic-only tree: no concept leaves -> the scaffolder
        # cannot brief Haiku on what symptoms to draft, so it must
        # fail loud rather than write a half-baked patient.
        empty_tree = json.dumps(
            {
                "kind": "AND",
                "children": [
                    {
                        "kind": "demographic",
                        "field": "age",
                        "operator": ">=",
                        "value": 40,
                    }
                ],
            }
        )
        client = _ScaffoldFakeClient(
            rule_row=self._row(logic_json=empty_tree),
            present_concepts=set(),
        )
        with pytest.raises(ScaffoldError, match="no SNOMED criteria"):
            load_rule_for_scaffold(client, rule_id="rule:demo:001")

    def test_falls_back_to_legacy_triggers_when_logic_json_missing(
        self,
    ) -> None:
        # Backwards-compat shim: stub rows that pre-date the logic_json
        # column (older fixtures, 3rd-party callers) keep working as
        # long as they pre-populate `triggers`. Production rows always
        # carry `logic_json`.
        from app.services.test_patient_scaffolder import load_rule_for_scaffold

        legacy_row = self._row(logic_json=None)
        legacy_row["triggers"] = [
            {
                "concept_id": "34436003",
                "preferred_term": "haematuria",
                "predicate": "EQ",
            }
        ]
        legacy_row["demographic_constraints"] = []
        client = _ScaffoldFakeClient(
            rule_row=legacy_row,
            present_concepts={"34436003"},
        )
        loaded = load_rule_for_scaffold(client, rule_id="rule:legacy:001")
        assert [t["concept_id"] for t in loaded["triggers"]] == ["34436003"]
        assert loaded["demographic_constraints"] == []


# ---------------------------------------------------------------------------
# TC-017 -- list_rules_for_picker derives trigger_terms from logic_json
# ---------------------------------------------------------------------------


class TestTC017PickerTriggerTermsFromLogicJson:
    """The rule picker preview must derive its 3-term trigger preview
    from the same ``logic_json`` the scaffolder reads, otherwise the
    picker shows blank cues for every production rule.
    """

    def test_picker_derives_trigger_terms_from_real_logic_json(self) -> None:
        from app.services import test_patient_service

        client = FakeGraphClient(
            responses={
                "MATCH (rule:AppropriatenessRule)": [
                    {
                        "rule_id": "rule:NG12:v1:CH002:SEC000:R004",
                        "name": "Rule: 1.1.5",
                        "status": "pending_review",
                        "recommendation_text": "Offer an urgent chest X-ray",
                        "chapter_title": "Site-specific recommendations",
                        "action_priority": "2ww",
                        "guideline_id": "NG12",
                        "guideline_title": "Suspected cancer",
                        "logic_json": json.dumps(_REAL_LOGIC_TREE),
                    }
                ]
            }
        )
        rows = test_patient_service.list_rules_for_picker(
            client, guideline_id=None
        )
        assert len(rows) == 1
        first = rows[0]
        # logic_json is consumed by the service and never leaks to the
        # router (which exposes the picker payload).
        assert "logic_json" not in first
        assert first["trigger_terms"] == [
            "Cough (finding)",
            "Dyspnea (finding)",
            "History of asbestos exposure (situation)",
        ]

    def test_picker_uses_legacy_trigger_terms_when_logic_json_missing(
        self,
    ) -> None:
        # Pre-existing fixtures (and the unit tests in TC-009) stub the
        # picker rows directly with `trigger_terms`. Keep that contract
        # working so the migration is non-breaking.
        from app.services import test_patient_service

        client = FakeGraphClient(
            responses={
                "MATCH (rule:AppropriatenessRule)": [
                    {
                        "rule_id": "rule:legacy:001",
                        "name": "Legacy",
                        "status": "active",
                        "recommendation_text": "Refer adults with haematuria",
                        "chapter_title": "1.1 Cancer",
                        "action_priority": "2ww",
                        "guideline_id": "NG12",
                        "guideline_title": "Suspected cancer",
                        "trigger_terms": ["haematuria"],
                        # logic_json deliberately absent
                    }
                ]
            }
        )
        rows = test_patient_service.list_rules_for_picker(
            client, guideline_id=None
        )
        assert rows[0]["trigger_terms"] == ["haematuria"]
