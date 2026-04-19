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
