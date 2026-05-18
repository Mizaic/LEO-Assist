"""Tests for cross-line lab finding merger (Layer 3c).

Atlas trace:
  DI: DI-D3391745
  DO: DO-1DB93C8E
  VT: VT-835D4BBC

These tests cover the merge_cross_line_lab_findings helper directly and the
end-to-end run_post_processing path so both training (label_verifier) and
runtime (pipeline_service) inherit the fix.
"""

from __future__ import annotations

import copy

from libs.pipeline.post_processing import (
    merge_cross_line_lab_findings,
    run_post_processing,
)


PSA_OBSERVABLE_TEXT = "Prostate-specific antigen level (XE25C) 12 ng/ml [0 - 6.5]"


def _psa_encounter(gap: str = "\n\n") -> str:
    """Return an encounter with the PSA value and the trailing interpretation
    separated by *gap* (default: blank line)."""
    return f"{PSA_OBSERVABLE_TEXT}{gap}Outside reference range"


def _psa_observable_entity(encounter: str) -> dict:
    start = encounter.find(PSA_OBSERVABLE_TEXT)
    assert start >= 0
    return {
        "text": PSA_OBSERVABLE_TEXT,
        "label": "observable_entity",
        "start": start,
        "end": start + len(PSA_OBSERVABLE_TEXT),
    }


class TestMergeCrossLineLabFindingsDirect:
    """Unit tests for merge_cross_line_lab_findings called in isolation."""

    def test_extends_observable_across_blank_line(self):
        encounter = _psa_encounter(gap="\n\n")
        ent = _psa_observable_entity(encounter)
        result = merge_cross_line_lab_findings(encounter, [ent])
        assert len(result) == 1
        merged = result[0]
        assert merged.get("__cross_line_merged__") is True
        assert merged["text"].endswith("Outside reference range")
        assert merged["end"] == len(encounter)
        assert encounter[merged["start"] : merged["end"]] == merged["text"]

    def test_extends_observable_across_single_newline(self):
        encounter = _psa_encounter(gap="\n")
        ent = _psa_observable_entity(encounter)
        result = merge_cross_line_lab_findings(encounter, [ent])
        merged = result[0]
        assert merged.get("__cross_line_merged__") is True
        assert merged["text"].endswith("Outside reference range")

    def test_idempotent(self):
        encounter = _psa_encounter()
        ent = _psa_observable_entity(encounter)
        first = merge_cross_line_lab_findings(encounter, [ent])
        snapshot = copy.deepcopy(first)
        second = merge_cross_line_lab_findings(encounter, first)
        assert second == snapshot

    def test_does_not_merge_when_descriptor_missing(self):
        encounter = (
            f"{PSA_OBSERVABLE_TEXT}\n\nThe patient is otherwise well today."
        )
        ent = _psa_observable_entity(encounter)
        result = merge_cross_line_lab_findings(encounter, [ent])
        merged = result[0]
        assert merged.get("__cross_line_merged__") is not True
        assert merged["text"] == PSA_OBSERVABLE_TEXT
        assert merged["end"] == ent["end"]

    def test_does_not_merge_across_two_blank_lines(self):
        encounter = f"{PSA_OBSERVABLE_TEXT}\n\n\n\nOutside reference range"
        ent = _psa_observable_entity(encounter)
        result = merge_cross_line_lab_findings(encounter, [ent])
        merged = result[0]
        assert merged.get("__cross_line_merged__") is not True
        assert merged["text"] == PSA_OBSERVABLE_TEXT

    def test_does_not_merge_when_observable_has_no_value(self):
        encounter = "Prostate-specific antigen level\n\nOutside reference range"
        ent = {
            "text": "Prostate-specific antigen level",
            "label": "observable_entity",
            "start": 0,
            "end": len("Prostate-specific antigen level"),
        }
        result = merge_cross_line_lab_findings(encounter, [ent])
        merged = result[0]
        assert merged.get("__cross_line_merged__") is not True

    def test_does_not_extend_beyond_max_extension(self):
        gap = "\n" + " " * 90 + "\n"
        encounter = (
            f"{PSA_OBSERVABLE_TEXT}{gap}Outside reference range"
        )
        ent = _psa_observable_entity(encounter)
        result = merge_cross_line_lab_findings(encounter, [ent])
        merged = result[0]
        assert merged.get("__cross_line_merged__") is not True
        assert merged["text"] == PSA_OBSERVABLE_TEXT

    def test_handles_two_independent_lab_blocks(self):
        block_a = "Haemoglobin (XE2pb) 11.0 g/dL [12 - 15]"
        block_b = "Mean cell volume (42A..) 105 fL [80 - 100]"
        encounter = (
            f"{block_a}\n\nOutside reference range\n\n"
            f"{block_b}\n\nOutside reference range"
        )
        ent_a = {
            "text": block_a,
            "label": "observable_entity",
            "start": encounter.find(block_a),
            "end": encounter.find(block_a) + len(block_a),
        }
        ent_b = {
            "text": block_b,
            "label": "observable_entity",
            "start": encounter.find(block_b),
            "end": encounter.find(block_b) + len(block_b),
        }
        result = merge_cross_line_lab_findings(encounter, [ent_a, ent_b])
        assert all(e.get("__cross_line_merged__") for e in result)
        assert result[0]["text"].endswith("Outside reference range")
        assert result[1]["text"].endswith("Outside reference range")
        # No cross-talk: the first block's text must not overlap the second.
        assert result[0]["end"] <= result[1]["start"]

    def test_skips_already_merged_entities(self):
        encounter = _psa_encounter()
        ent = _psa_observable_entity(encounter)
        ent["__cross_line_merged__"] = True
        result = merge_cross_line_lab_findings(encounter, [ent])
        assert result[0]["text"] == PSA_OBSERVABLE_TEXT
        assert result[0]["end"] == ent["end"]

    def test_empty_inputs_are_safe(self):
        assert merge_cross_line_lab_findings("", []) == []
        assert merge_cross_line_lab_findings("text", []) == []
        assert merge_cross_line_lab_findings(
            "", [{"text": "x", "label": "observable_entity", "start": 0, "end": 1}]
        ) == [{"text": "x", "label": "observable_entity", "start": 0, "end": 1}]

    def test_ignores_non_observable_entities(self):
        encounter = _psa_encounter()
        ent = {
            "text": PSA_OBSERVABLE_TEXT,
            "label": "qualifier_value",
            "start": 0,
            "end": len(PSA_OBSERVABLE_TEXT),
        }
        result = merge_cross_line_lab_findings(encounter, [ent])
        assert result[0].get("__cross_line_merged__") is not True

    def test_does_not_merge_when_value_is_followed_by_narrative(self):
        encounter = (
            "PSA (XE25C) 12 ng/ml. The patient also reports headache today."
        )
        ent = {
            "text": "PSA (XE25C) 12 ng/ml",
            "label": "observable_entity",
            "start": 0,
            "end": len("PSA (XE25C) 12 ng/ml"),
        }
        result = merge_cross_line_lab_findings(encounter, [ent])
        merged = result[0]
        assert merged.get("__cross_line_merged__") is not True
        assert merged["text"] == "PSA (XE25C) 12 ng/ml"


class TestMergeCrossLineLabFindingsViaPipeline:
    """Integration: ensure the merger runs as Layer 3c inside
    run_post_processing and that Layer 4 (observable normalisation) emits the
    matching finding sub-entity from the merged span."""

    def test_run_post_processing_emits_finding_from_merged_span(self):
        encounter = _psa_encounter(gap="\n\n")
        observable = _psa_observable_entity(encounter)
        result = run_post_processing(encounter, [observable])

        observables = [e for e in result if str(e.get("label")) == "observable_entity"]
        # Layer 4 emits the interpretation as a sub-entity carrying the
        # interpretation_qualifier metadata. Layer 5's deterministic relabel
        # rule then re-labels result-descriptor surface text to
        # qualifier_value; the qualifier metadata still flows through to the
        # SNOMED resolver via parent_observable_text + interpretation_qualifier.
        interpretation_entities = [
            e
            for e in result
            if str(e.get("interpretation_qualifier", ""))
            == "outside_reference_range"
        ]

        assert len(observables) == 1, observables
        assert interpretation_entities, result
        # The interpretation entity's surface text must come from the original
        # encounter (i.e. encounter offsets are preserved across the merge).
        for e in interpretation_entities:
            start = int(e.get("start", -1))
            end = int(e.get("end", -1))
            assert start >= 0 and end > start
            assert encounter[start:end] == e["text"]
            assert (
                str(e.get("parent_observable_text", "")).lower()
                .startswith("prostate-specific antigen")
            )

    def test_run_post_processing_is_idempotent(self):
        encounter = _psa_encounter(gap="\n\n")
        observable = _psa_observable_entity(encounter)
        first = run_post_processing(encounter, [copy.deepcopy(observable)])
        second = run_post_processing(encounter, copy.deepcopy(first))

        def _shape(entities):
            return sorted(
                (
                    str(e.get("label")),
                    str(e.get("text")),
                    int(e.get("start", -1) or -1),
                    int(e.get("end", -1) or -1),
                )
                for e in entities
            )

        assert _shape(first) == _shape(second)

    def test_run_post_processing_no_false_merge_in_narrative(self):
        encounter = (
            "The patient reports fatigue and weight loss over six months.\n\n"
            "On examination there is mild tenderness over the right flank."
        )
        result = run_post_processing(encounter, [])
        assert result == []
