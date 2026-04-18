"""VT-LEO-AI-180 -- Unit tests for the existing-entity audit pass.

These tests pin the offline self-consistency audit added to
scripts/lib/gold_label_snomed_check.py
(`audit_existing_entity` / `audit_gold_label_entities`).

The audit catches the regression class observed on 2026-04-17 where
the manual seed wrote entities with `label="finding"` and the attached
SNOMED concept was actually a `(qualifier value)` -- something the
proposal validator never inspected because it only looks at LLM
additions.

Each test pins one issue code from `ENTITY_AUDIT_ISSUE_CODES` and
asserts the severity ranking. Tests are pure -- no network, no DB.

Design Controls: DI-LEO-AI-186, DO-LEO-AI-185, R-LEO-AI-180.
"""

from __future__ import annotations

import json

from scripts.lib.gold_label_snomed_check import (
    ENTITY_AUDIT_ISSUE_CODES,
    EntityAuditResult,
    audit_existing_entity,
    audit_gold_label_entities,
)


def _entity(**overrides) -> dict:
    base = {
        "text": "normal",
        "label": "finding",
        "semantic_tag": "finding",
        "snomed_concept_id": "17621005",
        "snomed_term": "Normal (qualifier value)",
        "assertion": "present",
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# qualifier_value_on_clinical_label
# --------------------------------------------------------------------------


class TestQualifierValueOnClinicalLabel:
    """The exact regression observed in GL-d3ffb211468a5bcf and 4 others."""

    def test_normal_finding_with_qualifier_value_concept_is_critical(self):
        result = audit_existing_entity(_entity(), label_id="GL-x", entity_index=0)
        assert "qualifier_value_on_clinical_label" in result.issues
        assert result.severity == "critical"
        assert not result.is_clean

    def test_negative_finding_with_qualifier_value_concept_is_critical(self):
        result = audit_existing_entity(
            _entity(
                text="negative result",
                snomed_concept_id="260385009",
                snomed_term="Negative (qualifier value)",
            ),
            label_id="GL-x",
            entity_index=0,
        )
        assert "qualifier_value_on_clinical_label" in result.issues
        assert result.severity == "critical"

    def test_qualifier_value_on_disorder_label_is_critical(self):
        result = audit_existing_entity(
            _entity(label="disorder", semantic_tag="disorder"),
            label_id="GL-x",
            entity_index=0,
        )
        assert "qualifier_value_on_clinical_label" in result.issues

    def test_qualifier_value_on_procedure_label_is_critical(self):
        result = audit_existing_entity(
            _entity(label="procedure", semantic_tag="procedure"),
            label_id="GL-x",
            entity_index=0,
        )
        assert "qualifier_value_on_clinical_label" in result.issues

    def test_qualifier_value_on_observable_entity_label_is_critical(self):
        result = audit_existing_entity(
            _entity(label="observable_entity", semantic_tag="observable_entity"),
            label_id="GL-x",
            entity_index=0,
        )
        assert "qualifier_value_on_clinical_label" in result.issues

    def test_qualifier_value_on_qualifier_value_label_is_clean(self):
        # The legitimate case -- if the human curator set label
        # correctly to qualifier_value, the audit must NOT flag.
        result = audit_existing_entity(
            _entity(label="qualifier_value", semantic_tag="qualifier_value"),
            label_id="GL-x",
            entity_index=0,
        )
        assert "qualifier_value_on_clinical_label" not in result.issues
        assert "tag_label_mismatch" not in result.issues
        assert result.is_clean


# --------------------------------------------------------------------------
# tag_label_mismatch (clinical-vs-clinical, not covered by synonyms)
# --------------------------------------------------------------------------


class TestTagLabelMismatch:
    def test_finding_label_with_disorder_concept_is_synonym_clean(self):
        # finding<->disorder is in _TAG_SYNONYMS so this is tolerated.
        result = audit_existing_entity(
            _entity(
                text="prostate cancer",
                snomed_concept_id="399068003",
                snomed_term="Malignant tumor of prostate (disorder)",
                semantic_tag="disorder",
            ),
            label_id="GL-x",
            entity_index=0,
        )
        assert "tag_label_mismatch" not in result.issues

    def test_procedure_label_with_disorder_concept_is_critical(self):
        # procedure has no synonym for disorder.
        result = audit_existing_entity(
            _entity(
                text="cancer surgery",
                label="procedure",
                snomed_concept_id="399068003",
                snomed_term="Malignant tumor of prostate (disorder)",
                semantic_tag="procedure",
            ),
            label_id="GL-x",
            entity_index=0,
        )
        assert "tag_label_mismatch" in result.issues
        assert result.severity == "critical"

    def test_body_structure_label_with_morphologic_abnormality_is_synonym_clean(
        self,
    ):
        result = audit_existing_entity(
            _entity(
                text="diverticulae",
                label="body_structure",
                snomed_concept_id="125285008",
                snomed_term="Multiple diverticula (morphologic abnormality)",
                semantic_tag="body_structure",
            ),
            label_id="GL-x",
            entity_index=0,
        )
        assert "tag_label_mismatch" not in result.issues


# --------------------------------------------------------------------------
# stored_tag_drift (label OK, but stored semantic_tag drifts from term)
# --------------------------------------------------------------------------


class TestStoredTagDrift:
    def test_drift_is_flagged_when_no_other_issue_dominates(self):
        # label=finding + term=(finding) (clean on label/tag axis), but
        # the stored semantic_tag is "qualifier_value". Pure data-write
        # integrity issue.
        result = audit_existing_entity(
            _entity(
                text="lung mass",
                label="finding",
                snomed_concept_id="123",
                snomed_term="Mass of lung (finding)",
                semantic_tag="qualifier_value",
            ),
            label_id="GL-x",
            entity_index=0,
        )
        assert "stored_tag_drift" in result.issues
        # info-level only -- term suffix wins, so this is metadata noise
        # not a training-set blocker.
        assert result.severity == "info"

    def test_no_drift_when_stored_matches_term_suffix(self):
        result = audit_existing_entity(
            _entity(
                text="lung mass",
                label="finding",
                snomed_concept_id="123",
                snomed_term="Mass of lung (finding)",
                semantic_tag="finding",
            ),
            label_id="GL-x",
            entity_index=0,
        )
        assert result.is_clean


# --------------------------------------------------------------------------
# blocked_assertion_with_concept
# --------------------------------------------------------------------------


class TestBlockedAssertionWithConcept:
    def test_absent_assertion_with_concept_is_info(self):
        # Info-only: gold training intentionally captures e.g.
        # "no melanoma" as <melanoma, assertion=absent> so the NER
        # model learns the span; the assertion engine then decides not
        # to code at inference time.
        result = audit_existing_entity(
            _entity(
                text="lung cancer",
                label="disorder",
                snomed_concept_id="93880001",
                snomed_term="Primary malignant neoplasm of lung (disorder)",
                semantic_tag="disorder",
                assertion="absent",
            ),
            label_id="GL-x",
            entity_index=0,
        )
        assert "blocked_assertion_with_concept" in result.issues
        assert result.severity == "info"

    def test_planned_assertion_with_concept_is_info(self):
        result = audit_existing_entity(
            _entity(
                text="biopsy",
                label="procedure",
                snomed_concept_id="86273004",
                snomed_term="Biopsy (procedure)",
                semantic_tag="procedure",
                assertion="planned",
            ),
            label_id="GL-x",
            entity_index=0,
        )
        assert "blocked_assertion_with_concept" in result.issues
        assert result.severity == "info"

    def test_present_assertion_does_not_trigger(self):
        result = audit_existing_entity(
            _entity(
                text="biopsy",
                label="procedure",
                snomed_concept_id="86273004",
                snomed_term="Biopsy (procedure)",
                semantic_tag="procedure",
                assertion="present",
            ),
            label_id="GL-x",
            entity_index=0,
        )
        assert "blocked_assertion_with_concept" not in result.issues
        assert result.is_clean


# --------------------------------------------------------------------------
# missing fields
# --------------------------------------------------------------------------


class TestMissingFields:
    def test_label_without_concept_id_is_critical(self):
        result = audit_existing_entity(
            _entity(snomed_concept_id="", snomed_term=""),
            label_id="GL-x",
            entity_index=0,
        )
        assert "missing_concept_id" in result.issues
        assert result.severity == "critical"

    def test_concept_id_without_label_is_critical(self):
        result = audit_existing_entity(
            _entity(label="", semantic_tag=""),
            label_id="GL-x",
            entity_index=0,
        )
        assert "missing_label" in result.issues
        assert result.severity == "critical"

    def test_concept_id_without_term_is_warning(self):
        result = audit_existing_entity(
            _entity(snomed_term=""),
            label_id="GL-x",
            entity_index=0,
        )
        assert "missing_snomed_term" in result.issues
        # severity is warning UNLESS another critical issue stacks (here
        # the missing term means we cannot derive semantic_tag, so we
        # cannot assert qualifier_value mismatch -- only the warning
        # triggers).
        assert result.severity == "warning"


# --------------------------------------------------------------------------
# Severity ranking when multiple issues stack
# --------------------------------------------------------------------------


class TestSeverityRanking:
    def test_critical_dominates_warning_and_info(self):
        result = audit_existing_entity(
            _entity(
                # clinical label + qualifier_value concept (critical)
                # AND stored_semantic_tag drifts from suffix (info)
                # AND historical assertion (info)
                semantic_tag="finding",
                assertion="historical",
            ),
            label_id="GL-x",
            entity_index=0,
        )
        assert "qualifier_value_on_clinical_label" in result.issues
        assert "blocked_assertion_with_concept" in result.issues
        assert result.severity == "critical"


# --------------------------------------------------------------------------
# audit_gold_label_entities -- batch wrapper
# --------------------------------------------------------------------------


class TestAuditGoldLabelEntities:
    def test_replays_real_failing_record(self):
        # GL-d3ffb211468a5bcf payload from production on 2026-04-17.
        payload = json.dumps(
            [
                {
                    "text": "US scan of breast",
                    "label": "procedure",
                    "assertion": "present",
                    "snomed_concept_id": "47079000",
                    "semantic_tag": "procedure",
                    "snomed_term": "Ultrasonography of breast (procedure)",
                },
                {
                    "text": "normal",
                    "label": "finding",
                    "assertion": "present",
                    "snomed_concept_id": "17621005",
                    "semantic_tag": "finding",
                    "snomed_term": "Normal (qualifier value)",
                },
            ]
        )
        results = audit_gold_label_entities(
            label_id="GL-d3ffb211468a5bcf", entities_json=payload
        )
        assert len(results) == 2
        assert results[0].is_clean
        assert not results[1].is_clean
        assert "qualifier_value_on_clinical_label" in results[1].issues

    def test_handles_empty_payload(self):
        assert audit_gold_label_entities("GL-x", None) == []
        assert audit_gold_label_entities("GL-x", "") == []
        assert audit_gold_label_entities("GL-x", "[]") == []

    def test_handles_malformed_payload(self):
        assert audit_gold_label_entities("GL-x", "not json") == []
        assert audit_gold_label_entities("GL-x", "{}") == []
        # Mixed list with non-dict entries: skip non-dicts, keep dicts.
        results = audit_gold_label_entities(
            "GL-x", json.dumps(["string", 42, _entity()])
        )
        assert len(results) == 1
        assert isinstance(results[0], EntityAuditResult)


def test_issue_codes_are_documented():
    """Every code emitted by the audit must have a human description."""
    for code in [
        "missing_concept_id",
        "missing_snomed_term",
        "missing_label",
        "qualifier_value_on_clinical_label",
        "tag_label_mismatch",
        "stored_tag_drift",
        "blocked_assertion_with_concept",
    ]:
        assert code in ENTITY_AUDIT_ISSUE_CODES
        assert ENTITY_AUDIT_ISSUE_CODES[code]
