"""Contract tests for libs/cypher/remediation_queries.py.

These tests pin the shape of the Cypher queries used by
scripts/remediate_audit_findings.py so that the audit-driven
encounter remediation workflow stays safe (idempotent, scoped to
audit_remediation source, and never touches unrelated patients).

Atlas trace:
  VT: VT-19165B6F (Automated Encounter Remediation - LLM Gate and Audit Trail)
  DI: DI-09E26C1D
  DO: DO-C5890265
"""

from __future__ import annotations

import re

import libs.cypher.remediation_queries as q


def _params(text: str) -> set[str]:
    return set(re.findall(r"\$([a-zA-Z_][a-zA-Z0-9_]*)", text))


class TestGetEncounterForRemediation:
    def test_is_non_empty_string(self):
        assert isinstance(q.GET_ENCOUNTER_FOR_REMEDIATION, str)
        assert q.GET_ENCOUNTER_FOR_REMEDIATION.strip()

    def test_uses_encounter_id_parameter(self):
        assert "encounter_id" in _params(q.GET_ENCOUNTER_FOR_REMEDIATION)

    def test_returns_text_date_and_coded_collection(self):
        s = q.GET_ENCOUNTER_FOR_REMEDIATION
        assert "AS text" in s
        assert "AS date" in s
        assert "AS coded" in s

    def test_returns_per_concept_provenance_fields(self):
        s = q.GET_ENCOUNTER_FOR_REMEDIATION
        for field in ("concept_id", "name", "semantic_tag",
                      "context", "evidence", "source", "confidence"):
            assert field in s


class TestDeleteOvercodedDocuments:
    def test_uses_documented_parameters(self):
        assert _params(q.DELETE_OVERCODED_DOCUMENTS) == {
            "encounter_id", "concept_id"
        }

    def test_only_deletes_documents_relationships_not_concept_nodes(self):
        s = q.DELETE_OVERCODED_DOCUMENTS
        assert "DELETE rel" in s
        assert "DETACH DELETE" not in s

    def test_returns_remaining_encounter_doc_count(self):
        s = q.DELETE_OVERCODED_DOCUMENTS
        assert "AS deleted_count" in s
        assert "AS remaining_encounter_docs" in s


class TestCleanupPatientShortcut:
    def test_uses_patient_id_and_concept_id(self):
        assert _params(q.CLEANUP_PATIENT_SHORTCUT) == {
            "patient_id", "concept_id"
        }

    def test_only_removes_known_shortcut_relationship_types(self):
        s = q.CLEANUP_PATIENT_SHORTCUT
        for rel in (
            "HAS_FINDING",
            "HAS_DISORDER",
            "HAS_DISEASE",
            "HAS_CLINICAL_FINDING",
            "HAS_SITUATION",
            "HAS_OBSERVABLE",
            "HAS_OBSERVABLE_ENTITY",
            "HAS_PROCEDURE",
            "HAS_CONCEPT",
        ):
            assert rel in s

    def test_does_not_detach_delete_concept_nodes(self):
        assert "DETACH DELETE" not in q.CLEANUP_PATIENT_SHORTCUT


class TestGetPatientForEncounter:
    def test_uses_encounter_id(self):
        assert _params(q.GET_PATIENT_FOR_ENCOUNTER) == {"encounter_id"}

    def test_returns_patient_id_string(self):
        assert "AS patient_id" in q.GET_PATIENT_FOR_ENCOUNTER


class TestBuildAddDocumentsQuery:
    def test_returns_non_empty_string(self):
        s = q.build_add_documents_query("Finding", "HAS_FINDING")
        assert isinstance(s, str) and s.strip()

    def test_uses_runtime_parameters(self):
        s = q.build_add_documents_query("Finding", "HAS_FINDING")
        for p in ("encounter_id", "concept_id", "name", "semantic_tag",
                  "assertion", "evidence", "confidence", "context_json"):
            assert p in _params(s)

    def test_injects_label_and_rel_type(self):
        s = q.build_add_documents_query("Finding", "HAS_FINDING")
        assert "MERGE (s:Finding" in s
        assert ":HAS_FINDING]" in s

    def test_uses_merge_for_idempotency_on_concept_and_documents(self):
        s = q.build_add_documents_query("Disorder", "HAS_DISORDER")
        assert "MERGE (s:Disorder" in s
        assert "MERGE (e)-[r:DOCUMENTS" in s

    def test_stamps_audit_remediation_provenance(self):
        s = q.build_add_documents_query("Disorder", "HAS_DISORDER")
        assert "audit_remediation" in s
        assert "remediated_by" in s
        assert "remediated_at" in s

    def test_only_creates_patient_shortcut_for_present_or_historical(self):
        s = q.build_add_documents_query("Disorder", "HAS_DISORDER")
        assert "FOREACH" in s
        assert "['present', 'historical']" in s

    def test_does_not_detach_delete(self):
        s = q.build_add_documents_query("Disorder", "HAS_DISORDER")
        assert "DETACH DELETE" not in s


class TestSetDocumentsContext:
    def test_uses_encounter_concept_and_context(self):
        assert _params(q.SET_DOCUMENTS_CONTEXT) == {
            "encounter_id", "concept_id", "context_json"
        }

    def test_stamps_remediated_by_and_at(self):
        s = q.SET_DOCUMENTS_CONTEXT
        assert "remediated_by" in s
        assert "remediated_at" in s

    def test_get_context_uses_limit_one(self):
        assert "LIMIT 1" in q.GET_DOCUMENTS_CONTEXT
        assert _params(q.GET_DOCUMENTS_CONTEXT) == {
            "encounter_id", "concept_id"
        }


class TestNoDestructiveCypherInModule:
    def test_no_drop_or_database_wide_delete(self):
        for name, value in vars(q).items():
            if not isinstance(value, str):
                continue
            assert "DROP " not in value, f"{name} contains DROP"
            assert "MATCH (n)\nDETACH DELETE n" not in value, (
                f"{name} contains a wildcard DETACH DELETE"
            )
