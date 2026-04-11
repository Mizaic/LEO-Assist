"""Prompt builder for synthetic NER sentence generation."""

from __future__ import annotations

SYSTEM_PROMPT = """You are a UK clinical documentation specialist generating synthetic
clinical note sentences for NER training.

Requirements:
- Return ONLY valid JSON. No markdown, comments, or prose.
- Generate exactly {n_sentences} sentence objects.
- Each sentence MUST include this exact mention text: "{surface_form}".
- Use the mention exactly once per sentence.
- Keep each sentence focused on ONE coded mention only.
- Do NOT include additional diagnoses, procedures, findings, test names, drug names,
  or any other coded clinical entities in the same sentence.
- Keep sentences clinically plausible and varied in context (history, findings,
  plan, medication, investigations, discharge note).
- Avoid any real-world identifiers (names, addresses, NHS numbers, dates of
  birth, phone numbers, postcodes).
- Keep style concise and realistic for GP / hospital notes.
- Choose the most clinically valid assertion per sentence.
- Keep sentence length between 8 and 20 words.
- Avoid conjunction chains ("and", "with", "plus") that introduce extra entities.
- If unsure, produce a simpler sentence with only the target mention.

Assertion must be one of:
present, absent, historical, possible, planned, hypothetical

Output schema:
[
  {{
    "sentence": "<clinical sentence>",
    "assertion": "present|absent|historical|possible|planned|hypothetical"
  }}
]
"""

USER_PROMPT_TEMPLATE = """Generate synthetic NER training examples.

Surface form: {surface_form}
Preferred term: {preferred_term}
SNOMED concept ID: {concept_id}
Semantic tag: {semantic_tag}

Tag guidance:
- If semantic tag is "procedure": describe an action/intervention being performed, planned, or declined.
- If semantic tag is "observable_entity": describe a measurable observation/test concept only.
  Include either (a) a numeric result value, or (b) explicit reference-range status
  wording such as "out of reference range", "above reference range", or "below reference range".
- If semantic tag is "finding" or "disorder": describe a clinical state/diagnosis/symptom, not a procedure.

One-shot style example:
[
  {{
    "sentence": "Type 2 diabetes remains well controlled on metformin.",
    "assertion": "present"
  }},
  {{
    "sentence": "No evidence of type 2 diabetes at this review.",
    "assertion": "absent"
  }}
]
"""


def build_synthetic_sentence_prompts(
    *,
    surface_form: str,
    preferred_term: str,
    concept_id: str,
    semantic_tag: str,
    n_sentences: int,
    context_examples: list[str] | None = None,
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for the synthetic sentence request."""
    system_prompt = SYSTEM_PROMPT.format(
        n_sentences=n_sentences,
        surface_form=surface_form,
    )
    user_prompt = USER_PROMPT_TEMPLATE.format(
        surface_form=surface_form,
        preferred_term=preferred_term,
        concept_id=concept_id,
        semantic_tag=semantic_tag,
    )
    examples = [str(x).strip() for x in (context_examples or []) if str(x).strip()]
    if examples:
        snippet_lines = "\n".join(
            f"- Example {idx + 1}: {snippet}"
            for idx, snippet in enumerate(examples[:10])
        )
        user_prompt = (
            f"{user_prompt}\n\n"
            "De-identified real-note style examples:\n"
            f"{snippet_lines}\n"
        )
    return system_prompt, user_prompt
