"""Local concept recovery -- happy and non-happy paths."""

from __future__ import annotations

from libs.ner.local_concept_recovery import (
    LocalConceptPattern,
    patterns_from_rows,
    recover_local_concept_entities,
)

_PATTERNS = [
    LocalConceptPattern(
        normalized="acne fulminans",
        form="acne fulminans",
        concept_id="LEO-LOCAL-ACNE-FULMINANS",
        fsn="Acne fulminans (LEO local)",
        semantic_tag="finding",
    )
]


class TestRecoveryHappy:
    def test_recovers_missing_local_entity(self):
        text = "Urgently refer acne fulminans to dermatology today."
        out = recover_local_concept_entities(text, [], _PATTERNS)
        assert len(out) == 1
        assert out[0]["snomed_concept_id"] == "LEO-LOCAL-ACNE-FULMINANS"
        assert out[0]["code_system"] == "leo_local"
        assert out[0]["_recovered_local_concept"] is True

    def test_patterns_from_rows_filters_non_leo(self):
        rows = [
            {
                "normalized": "x",
                "form": "x",
                "concept_id": "LEO-LOCAL-X",
                "fsn": "X",
                "semantic_tag": "finding",
            },
            {
                "normalized": "dm",
                "form": "dm",
                "concept_id": "73211009",
                "fsn": "Diabetes",
                "semantic_tag": "disorder",
            },
        ]
        pats = patterns_from_rows(rows)
        assert len(pats) == 1
        assert pats[0].concept_id == "LEO-LOCAL-X"


class TestRecoveryUnhappy:
    def test_blank_text_noop(self):
        assert recover_local_concept_entities("", [], _PATTERNS) == []
        assert recover_local_concept_entities("  ", [{"text": "a"}], _PATTERNS) == [
            {"text": "a"}
        ]

    def test_skips_when_already_present(self):
        entities = [
            {
                "text": "acne fulminans",
                "snomed_concept_id": "LEO-LOCAL-ACNE-FULMINANS",
            }
        ]
        out = recover_local_concept_entities(
            "patient has acne fulminans", entities, _PATTERNS
        )
        assert len(out) == 1

    def test_no_patterns_noop(self):
        text = "acne fulminans present"
        assert recover_local_concept_entities(text, [], []) == []
