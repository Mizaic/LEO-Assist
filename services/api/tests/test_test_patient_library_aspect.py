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
    TEST_PATIENT_ASPECTS,
    TEST_PATIENT_CONSTRAINTS,
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
