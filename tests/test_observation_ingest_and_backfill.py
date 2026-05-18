"""Phase 6c/6d -- tests for NICE ingest observation emission + backfill.

Atlas trace:
    UN: UN-26E57FA1
    DI: DI-4C8A09C3
    DO: DO-CB6324A3
    VT: VT-1A7862B9 (execution_status=passed)

Covers:
    - The ingest pipeline ``_normalise_observation_node`` accepts the
      LLM's flat observation shape and rejects partials (fail closed).
    - The ingest's ``_finalise_observations`` canonicalises threshold
      values when the observable is registered, and downgrades to
      CONCEPT when the registry does not recognise the SNOMED id.
    - The backfill scanner recognises the full set of NICE phrasing
      variants (prefix, postfix, between, abbreviations) and never
      emits a finding for unknown observables.
    - The backfill report builder correctly marks rules that already
      encode an observation vs. those that only presence-check the
      observable.
"""

from __future__ import annotations

import json

import pytest

from libs.pipeline_graph.subgraphs.guidance_rule_extraction_v2_impl import (
    _finalise_observations,
    _normalise_observation_node,
)
from libs.units.observation_backfill_scanner import (
    build_alias_index,
    iter_findings,
    match_observable,
)
from scripts.atlas.backfill_observation_leaves import scan_rules


# -- Phase 6c: ingest normalisation ---------------------------------


class TestNormaliseObservationNode:
    """LLM output -> normalised node structure."""

    def test_happy_path_platelet_threshold(self) -> None:
        node = {
            "kind": "observation",
            "term": {"text": "Platelet count"},
            "operator": ">=",
            "value": 400,
            "unit": "10*9/L",
            "within_days": 365,
        }
        out = _normalise_observation_node(node)
        assert out is not None
        assert out["kind"] == "observation"
        assert out["operator"] == ">="
        assert out["value"] == 400.0
        assert out["unit"] == "10*9/L"
        assert out["within_days"] == 365

    def test_between_operator_accepts_two_element_array(self) -> None:
        node = {
            "kind": "observation",
            "term": {"text": "Haemoglobin"},
            "operator": "between",
            "value": [100, 110],
            "unit": "g/L",
        }
        out = _normalise_observation_node(node)
        assert out is not None
        assert out["value"] == [100.0, 110.0]
        assert out["within_days"] == 365  # default

    def test_missing_term_rejected(self) -> None:
        node = {
            "kind": "observation",
            "term": {"text": ""},
            "operator": ">=",
            "value": 4.0,
            "unit": "ug/L",
        }
        assert _normalise_observation_node(node) is None

    def test_missing_unit_rejected(self) -> None:
        node = {
            "kind": "observation",
            "term": {"text": "PSA"},
            "operator": ">=",
            "value": 4.0,
            "unit": "",
        }
        assert _normalise_observation_node(node) is None

    def test_invalid_operator_rejected(self) -> None:
        node = {
            "kind": "observation",
            "term": {"text": "PSA"},
            "operator": "approximately",
            "value": 4.0,
            "unit": "ug/L",
        }
        assert _normalise_observation_node(node) is None

    def test_between_without_pair_rejected(self) -> None:
        node = {
            "kind": "observation",
            "term": {"text": "Haemoglobin"},
            "operator": "between",
            "value": 110,
            "unit": "g/L",
        }
        assert _normalise_observation_node(node) is None


# -- Phase 6c: finalise (canonicalise + downgrade) -------------------


class TestFinaliseObservations:
    """After terminology resolution, split OBSERVATION vs. CONCEPT."""

    def _node(self, snomed_id: str, unit: str = "10*9/L") -> dict:
        return {
            "kind": "observation",
            "operator": ">=",
            "value": 400.0,
            "unit": unit,
            "within_days": 365,
            "criterion": {
                "snomed_concept_id": snomed_id,
                "node_id": "obs_1",
                "term": "Platelet count",
            },
        }

    def test_known_observable_kept_and_canonicalised(self) -> None:
        node = self._node("365632008")
        out, downgrades = _finalise_observations(node)
        assert out is not None
        assert out["kind"] == "observation"
        assert out["unit"] == "10*9/L"
        assert out["value"] == pytest.approx(400.0)
        assert downgrades == []

    def test_unknown_observable_downgraded_to_concept(self) -> None:
        node = self._node("9999999999")
        out, downgrades = _finalise_observations(node)
        assert out is not None
        assert out["kind"] == "concept"
        assert "operator" not in out
        assert "value" not in out
        assert "unit" not in out
        assert downgrades == [("obs_1", "9999999999")]

    def test_unparseable_unit_downgraded_to_concept(self) -> None:
        node = self._node("365632008", unit="potatoes")
        out, downgrades = _finalise_observations(node)
        assert out is not None
        assert out["kind"] == "concept"
        assert downgrades and downgrades[0][1] == "365632008"

    def test_non_observation_nodes_passed_through(self) -> None:
        tree = {
            "kind": "AND",
            "children": [
                {
                    "kind": "concept",
                    "criterion": {"snomed_concept_id": "123", "node_id": "c1"},
                },
                self._node("365632008"),
            ],
        }
        out, downgrades = _finalise_observations(tree)
        assert out is not None
        assert out["kind"] == "AND"
        assert len(out["children"]) == 2
        assert out["children"][0]["kind"] == "concept"
        assert out["children"][1]["kind"] == "observation"
        assert downgrades == []


# -- Phase 6d: backfill scanner --------------------------------------


@pytest.fixture(scope="module")
def alias_index() -> dict[str, tuple[str, str]]:
    return build_alias_index()


class TestBackfillScanner:
    """Regex + alias index cover NICE phrasing we expect in the wild."""

    @pytest.mark.parametrize(
        "text,expected_operator,expected_unit",
        [
            (
                "Refer adults with a platelet count of 400 x10*9/L "
                "or more for a suspected cancer pathway.",
                ">=",
                "10*9/L",
            ),
            (
                "Consider urgent referral when serum PSA is at or "
                "above 4 ug/L in men over 50.",
                ">=",
                "ug/L",
            ),
            (
                "In patients with eGFR less than 60 mL/min/1.73m2, "
                "consider stage 3 CKD.",
                "<",
                "mL/min/{1.73_m2}",
            ),
            (
                "Systolic blood pressure at or above 140 mmHg, "
                "confirm with 24h monitor.",
                ">=",
                "mm[Hg]",
            ),
            (
                "Platelets 500 x10*9/L or higher warrant investigation.",
                ">=",
                "10*9/L",
            ),
            (
                "PSA above 4 ng/mL in patients over 50 warrants "
                "urologic review.",
                ">",
                "ug/L",
            ),
        ],
    )
    def test_prefix_and_postfix_thresholds(
        self,
        alias_index: dict,
        text: str,
        expected_operator: str,
        expected_unit: str,
    ) -> None:
        hits = list(iter_findings(text, alias_index))
        assert len(hits) == 1, f"expected one hit for: {text}"
        assert hits[0].operator == expected_operator
        assert hits[0].unit_canonical == expected_unit

    def test_between_range_extracted(
        self, alias_index: dict
    ) -> None:
        hits = list(
            iter_findings(
                "Haemoglobin between 100 and 110 g/L indicates mild "
                "anaemia.",
                alias_index,
            )
        )
        assert len(hits) == 1
        assert hits[0].operator == "between"
        assert hits[0].value_canonical == [100.0, 110.0]

    def test_plain_text_yields_no_findings(
        self, alias_index: dict
    ) -> None:
        hits = list(
            iter_findings(
                "Refer if symptoms are concerning or persistent.",
                alias_index,
            )
        )
        assert hits == []

    def test_unknown_observable_not_reported(
        self, alias_index: dict
    ) -> None:
        hits = list(
            iter_findings(
                "Wacky lab test above 99 widgets warrants review.",
                alias_index,
            )
        )
        assert hits == []

    def test_match_observable_resolves_rightmost_alias(
        self, alias_index: dict
    ) -> None:
        assert match_observable(
            "in patients with egfr", alias_index
        ) == (
            "1011481000000105",
            "Estimated GFR",
        )

    def test_match_observable_returns_none_for_unknown(
        self, alias_index: dict
    ) -> None:
        assert match_observable("random noise words", alias_index) is None


class TestBackfillReportBuilder:
    """End-to-end over a fake rule row."""

    def test_rule_without_observation_leaf_flagged_as_concept_only(
        self,
    ) -> None:
        rows = [
            {
                "rule_id": "RULE1",
                "rule_name": "NICE NG12 example",
                "rule_status": "active",
                "logic_json": json.dumps({"logic_tree": {"kind": "AND"}}),
                "recommendation_id": "REC1",
                "verbatim": "eGFR less than 60 mL/min/1.73m2.",
                "guideline_id": "G1",
            }
        ]
        report = scan_rules(rows)
        assert len(report) == 1
        row = report[0]
        assert row.observable_snomed_id == "1011481000000105"
        assert row.operator == "<"
        assert "CONCEPT" in row.current_leaf_kind
        assert "replace the CONCEPT leaf" in row.suggested_action

    def test_rule_already_encoding_observation_flagged_for_confirmation(
        self,
    ) -> None:
        logic = {
            "logic_tree": {
                "kind": "AND",
                "children": [
                    {
                        "kind": "observation",
                        "criterion": {
                            "snomed_concept_id": "1011481000000105",
                            "node_id": "obs_1",
                        },
                    }
                ],
            }
        }
        rows = [
            {
                "rule_id": "RULE2",
                "rule_name": "Already encoded",
                "rule_status": "active",
                "logic_json": json.dumps(logic),
                "recommendation_id": "REC2",
                "verbatim": "eGFR less than 60 mL/min/1.73m2.",
                "guideline_id": "G1",
            }
        ]
        report = scan_rules(rows)
        assert len(report) == 1
        row = report[0]
        assert "OBSERVATION (same observable already encoded)" == (
            row.current_leaf_kind
        )
        assert "confirm the existing OBSERVATION leaf" in row.suggested_action

    def test_empty_verbatim_produces_no_rows(self) -> None:
        report = scan_rules(
            [
                {
                    "rule_id": "RULE3",
                    "rule_name": "No text",
                    "rule_status": "active",
                    "logic_json": "{}",
                    "recommendation_id": "REC3",
                    "verbatim": "",
                    "guideline_id": "G1",
                }
            ]
        )
        assert report == []

    def test_malformed_logic_json_does_not_crash(self) -> None:
        report = scan_rules(
            [
                {
                    "rule_id": "RULE4",
                    "rule_name": "Bad JSON",
                    "rule_status": "active",
                    "logic_json": "{not valid json",
                    "recommendation_id": "REC4",
                    "verbatim": "eGFR less than 60 mL/min/1.73m2.",
                    "guideline_id": "G1",
                }
            ]
        )
        assert len(report) == 1  # still emitted, just treated as no existing leaf
