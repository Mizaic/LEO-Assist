"""VT-5BDFE5F7 -- Centralised Test Patient library, Phase A.

Verifies the data-model invariants and clone-from-real flow that
mitigate R-8C0CC94B (a test patient mistaken for a real patient).

These tests are intentionally hermetic: they assert on the static
shape of the Cypher queries and on the Python clone service against
a hand-rolled in-memory CodingGraphClient stub. They do not need a
running Neo4j instance.
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
from libs.cypher.test_patient_queries import (
    BACKFILL_LEGACY_TEST_PATIENTS,
    CLONE_PATIENT_DOCUMENTS,
    CLONE_PATIENT_ENCOUNTERS,
    COUNT_TEST_PATIENTS_BY_ASPECT,
    CREATE_TEST_PATIENT,
    CREATE_TEST_PATIENT_FOR_ASPECT,
    LIST_REAL_PATIENTS_FOR_CLONE_PICKER,
    LIST_TEST_PATIENTS,
    TEST_PATIENT_ASPECTS,
    TEST_PATIENT_CONSTRAINTS,
)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


@dataclass
class FakeRow(dict):
    """dict-with-attribute-access -- mimics a Neo4j result row."""


@dataclass
class FakeGraphClient:
    """Hand-rolled stand-in for CodingGraphClient.

    Records every Cypher statement and returns canned rows from
    `responses`, keyed by (search_term, fallback_index).
    """

    responses: list[list[dict]] = field(default_factory=list)
    calls: list[tuple[str, dict]] = field(default_factory=list)

    def run(self, cypher: str, **params: Any) -> list[dict]:
        self.calls.append((cypher, dict(params)))
        if self.responses:
            return self.responses.pop(0)
        return []

    def close(self) -> None:
        pass


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
# TC-002 -- Production isolation (label-level + relationship-level)
# ---------------------------------------------------------------------------


class TestTC002ProductionIsolation:
    """Production queries (`MATCH (p:Patient) ...`) cannot return
    :TestPatient nodes because the label is separate, AND the
    source-patient picker explicitly excludes test patients."""

    def test_picker_excludes_test_patients(self) -> None:
        assert "MATCH (p:Patient)" in LIST_REAL_PATIENTS_FOR_CLONE_PICKER
        assert "coalesce(p.is_test, false) = false" in (
            LIST_REAL_PATIENTS_FOR_CLONE_PICKER
        )

    def test_clone_query_creates_only_test_patient_label(self) -> None:
        # The new TestPatient root never carries a :Patient label, so
        # any production MATCH (p:Patient) cannot return it.
        assert ":TestPatient" in CREATE_TEST_PATIENT_FOR_ASPECT
        assert "(tp:Patient" not in CREATE_TEST_PATIENT_FOR_ASPECT

    def test_cloned_encounters_carry_is_test_flag(self) -> None:
        assert "te.is_test = true" in CLONE_PATIENT_ENCOUNTERS

    def test_cloned_documents_carry_is_test_flag(self) -> None:
        assert "td.is_test = true" in CLONE_PATIENT_DOCUMENTS


# ---------------------------------------------------------------------------
# TC-003 -- Clone-from-real strips PII and tags the new record
# ---------------------------------------------------------------------------


class TestTC003CloneFromReal:
    """Cloning a real patient produces a de-identified test patient
    with the test_ prefix, an aspect tag, and the source link."""

    def _client_with_source(self) -> FakeGraphClient:
        # _load_source -> CREATE_TEST_PATIENT_FOR_ASPECT ->
        # encounters -> documents -> concept rels (5 calls)
        return FakeGraphClient(
            responses=[
                # _load_source response: source patient row
                [
                    {
                        "id": "patient-real-1",
                        "display_name": "Jane Doe",
                        "age": 62,
                        "sex": "female",
                        "encounter_count": 4,
                        "document_count": 2,
                    }
                ],
                # CREATE_TEST_PATIENT_FOR_ASPECT response
                [{"id": "test_abc"}],
                # encounters response
                [{"encounters_cloned": 4}],
                # documents response
                [{"documents_cloned": 2}],
                # concept rels response
                [{"rel_count": 5}],
            ]
        )

    def test_clone_rejects_unknown_aspect(self) -> None:
        client = FakeGraphClient()
        with pytest.raises(CloneError):
            clone_patient_as_test_patient(
                client,
                source_patient_id="patient-real-1",
                aspect="not-a-real-aspect",
                created_by="qa@example.com",
            )

    def test_clone_rejects_missing_source(self) -> None:
        client = FakeGraphClient(responses=[[]])
        with pytest.raises(CloneError):
            clone_patient_as_test_patient(
                client,
                source_patient_id="missing",
                aspect="nlp",
                created_by="qa@example.com",
            )

    def test_clone_returns_new_test_patient_summary(self) -> None:
        client = self._client_with_source()
        result = clone_patient_as_test_patient(
            client,
            source_patient_id="patient-real-1",
            aspect="nlp",
            created_by="qa@example.com",
        )
        assert result["aspect"] == "nlp"
        assert result["source_patient_id"] == "patient-real-1"
        assert result["id"].startswith("test_")
        assert result["name"].startswith("test_")
        assert result["encounters_cloned"] == 4
        assert result["documents_cloned"] == 2
        assert result["concept_rels_cloned"] == 5

    def test_clone_writes_age_and_sex_only_to_new_root(self) -> None:
        client = self._client_with_source()
        clone_patient_as_test_patient(
            client,
            source_patient_id="patient-real-1",
            aspect="episodes",
            created_by="qa@example.com",
        )
        create_call = next(
            (
                params
                for cypher, params in client.calls
                if cypher == CREATE_TEST_PATIENT_FOR_ASPECT
            ),
            None,
        )
        assert create_call is not None
        # `name` is the only PII-shaped key we deliberately set on the
        # new root, and it must always carry the audit prefix and never
        # the source's display name.
        assert create_call["name"].startswith("test_")
        assert "Jane" not in create_call["name"]
        # Every other PII key is absent from the create parameters --
        # nothing identifiable from the source can reach the test patient.
        for pii in PII_KEYS_TO_STRIP:
            if pii == "name":
                continue
            assert pii not in create_call, f"PII key {pii!r} leaked to create"
        # Age + sex are carried over (they drive coding/guideline rules).
        assert create_call["age"] == 62
        assert create_call["sex"] == "female"
        # Source link is preserved for re-clone-after-source-changes.
        assert create_call["source_patient_id"] == "patient-real-1"

    def test_clone_uses_unique_id_prefix_for_subgraph(self) -> None:
        client = self._client_with_source()
        clone_patient_as_test_patient(
            client,
            source_patient_id="patient-real-1",
            aspect="summarisation",
            created_by="qa@example.com",
        )
        encounter_call = next(
            (
                params
                for cypher, params in client.calls
                if cypher == CLONE_PATIENT_ENCOUNTERS
            ),
            None,
        )
        assert encounter_call is not None
        assert encounter_call["id_prefix"].startswith("test_")
        assert encounter_call["id_prefix"].endswith("_")


# ---------------------------------------------------------------------------
# TC-004 -- Aspect counts service hand-off (router-level invariants)
# ---------------------------------------------------------------------------


class TestTC004AspectCounts:
    """The service always returns one entry per known aspect plus an
    `all` total, so the UI can render four stable count tiles."""

    def test_count_by_aspect_pads_zero_rows(self) -> None:
        from app.services import test_patient_service

        client = FakeGraphClient(
            responses=[
                [
                    {"aspect": "guidelines", "total": 3},
                    {"aspect": "nlp", "total": 1},
                ]
            ]
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

        client = FakeGraphClient(responses=[[]])
        test_patient_service.list_patients(client, aspect="bogus")
        cypher, params = client.calls[0]
        assert cypher == LIST_TEST_PATIENTS
        assert params["aspect"] is None

    def test_list_patients_passes_known_aspect_through(self) -> None:
        from app.services import test_patient_service

        client = FakeGraphClient(responses=[[]])
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
        # Every identifier called out in the DI acceptance criterion
        # is in the strip list, so the verification helper can prove
        # they are absent on the cloned root.
        for key in (
            "nhs_number",
            "name",
            "displayName",
            "date_of_birth",
            "dateOfBirth",
            "address",
            "phone",
            "phone_number",
        ):
            assert key in PII_KEYS_TO_STRIP


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
