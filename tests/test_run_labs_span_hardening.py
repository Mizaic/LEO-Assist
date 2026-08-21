from __future__ import annotations

from libs.terminology.client import ResolvedTerm
from scripts.coding_loop.run_labs import _align_entity_for_gold, process_sentence


class _FakeTerminologyClient:
    def __init__(self, *, reject_value_bearing_terms: bool = False) -> None:
        self.terms: list[str] = []
        self.reject_value_bearing_terms = reject_value_bearing_terms

    def resolve(
        self,
        terms: list[str],
        expected_tags: dict[str, str] | None = None,
    ) -> dict[str, list[ResolvedTerm]]:
        self.terms.extend(terms)
        out: dict[str, list[ResolvedTerm]] = {}
        for term in terms:
            if self.reject_value_bearing_terms and "42K.." in term:
                out[term] = []
                continue
            out[term] = [
                ResolvedTerm(
                    text=term,
                    concept_id="1022561000000101",
                    term="Eosinophil count",
                    semantic_tag="observable_entity",
                    score=1.0,
                    had_exact_match=True,
                    lexical_raw=1.2,
                )
            ]
        return out


def test_align_entity_for_gold_recomputes_changed_haiku_text() -> None:
    sentence = "Serum potassium level (XE2pz) 4.1 mmol/L [3.5 - 5.3]"
    entity = {
        "text": "Serum potassium level 4.1 mmol/L",
        "label": "observable_entity",
        "start": 0,
        "end": 10,
    }

    aligned = _align_entity_for_gold(sentence, entity)

    assert aligned is not None
    assert aligned["text"] == "Serum potassium level (XE2pz) 4.1 mmol/L"
    assert sentence[aligned["start"] : aligned["end"]] == aligned["text"]


def test_align_entity_for_gold_drops_unfindable_text() -> None:
    aligned = _align_entity_for_gold(
        "Serum potassium level (XE2pz) 4.1 mmol/L",
        {"text": "Serum sodium level 140 mmol/L", "label": "observable_entity"},
    )

    assert aligned is None


def test_process_sentence_falls_back_to_stripped_observable_lookup() -> None:
    sentence = (
        "Eosinophil count - observation (42K..) "
        "0.23 10^9/L [0.04 - 0.4]"
    )
    client = _FakeTerminologyClient(reject_value_bearing_terms=True)

    result = process_sentence(
        sentence,
        terminology_client=client,
        with_haiku=False,
        arbitrator=None,
        dry_run=True,
    )

    assert result is not None
    assert "Eosinophil count - observation" in client.terms
    assert any(
        term.startswith("Eosinophil count - observation (42K..)")
        for term in client.terms
    )
    assert len(result["entities"]) == 1
    entity = result["entities"][0]
    assert entity["text"] in sentence
    assert sentence[entity["start"] : entity["end"]] == entity["text"]
    assert entity["label"] == "observable_entity"
    assert entity["semantic_tag"] == "observable_entity"
    assert entity["snomed_concept_id"] == "1022561000000101"
    assert entity["snomed_term"] == "Eosinophil count"
    assert entity["start"] == 0
    assert entity["end"] == len(sentence)
    assert entity["numeric_value"] == "0.23"
    assert entity["unit"] == "10^9/L"
    assert entity["reference_range"] == "0.04 - 0.4"
