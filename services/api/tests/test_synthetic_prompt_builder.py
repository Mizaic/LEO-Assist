from __future__ import annotations

from libs.prompts.synthetic_ner_sentences import build_synthetic_sentence_prompts


def test_prompt_builder_includes_context_and_gold_output_examples() -> None:
    _, user_prompt, clean_preferred = build_synthetic_sentence_prompts(
        surface_form="AST",
        preferred_term="Aspartate transaminase",
        concept_id="123",
        semantic_tag="observable_entity",
        n_sentences=3,
        context_examples=["AST was 32 U/L in admission bloods."],
        gold_output_examples=[
            {
                "sentence": "AST recorded at 27 U/L within reference range.",
                "assertion": "present",
            }
        ],
    )
    assert "Real de-identified note extracts" in user_prompt
    assert "Verified gold output examples" in user_prompt
    assert '"assertion": "present"' in user_prompt
    assert clean_preferred == "Aspartate transaminase"


def test_snomed_qualifier_stripped_from_preferred_term() -> None:
    _, user_prompt, clean = build_synthetic_sentence_prompts(
        surface_form="AAA",
        preferred_term="Abdominal aortic aneurysm (disorder)",
        concept_id="233985008",
        semantic_tag="disorder",
        n_sentences=3,
    )
    assert clean == "Abdominal aortic aneurysm"
    assert "Abdominal aortic aneurysm (disorder)" not in user_prompt
    assert "Abdominal aortic aneurysm" in user_prompt
