"""Prompt builder for synthetic NER sentence generation."""

from __future__ import annotations

import json
import re

_SNOMED_QUALIFIER_RE = re.compile(r"\s*\([^)]+\)\s*$")


def _strip_snomed_qualifier(fsn: str) -> str:
    """Remove trailing SNOMED semantic qualifier from an FSN.

    e.g. 'Abdominal aortic aneurysm (disorder)' -> 'Abdominal aortic aneurysm'
    """
    return _SNOMED_QUALIFIER_RE.sub("", (fsn or "")).strip()


_REFERRAL_LIKE_RE = re.compile(
    r"\b(?:referral|referred|2ww|two\s*week|fast\s*track|urgent\s*suspected|"
    r"cancer\s*pathway|suspected\s*cancer|suspected\s*cancer\s*clinic)\b",
    re.IGNORECASE,
)


def _is_referral_like(surface_form: str, preferred_term: str) -> bool:
    blob = f"{surface_form} {preferred_term}"
    return bool(_REFERRAL_LIKE_RE.search(blob))


_TAG_GUIDANCE: dict[str, str] = {
    "procedure": (
        'Write a sentence where "{surface_form}" names a clinical action '
        "that has been performed, is being planned, was declined, or was requested. "
        'Use active verbs: "performed", "underwent", "arranged", "declined", "referred for". '
        'Example: "ECG was performed on admission."'
    ),
    "observable_entity": (
        'Write a sentence where "{surface_form}" names a measurable test or observation '
        "that has a recorded numeric result. "
        "State the result value and unit directly in the sentence. "
        'Use assertion "present" for any measured result. '
        'Example: "Serum albumin returned at 28 g/L on admission bloods."'
    ),
    "finding": (
        'Write a sentence where "{surface_form}" is a documented clinical finding, '
        "symptom, or sign that is currently present, was previously present, "
        "was absent, or is suspected. "
        'Example: "Peripheral oedema noted on examination."'
    ),
    "disorder": (
        'Write a sentence where "{surface_form}" is a documented diagnosis or condition '
        "that is active, historical, or excluded. "
        'Example: "Background of atrial fibrillation, currently rate-controlled."'
    ),
}

_DEFAULT_TAG_GUIDANCE = (
    'Write a sentence where "{surface_form}" is documented in a clinical note '
    "using language appropriate to its clinical meaning."
)

SYSTEM_PROMPT = """\
You are a UK clinical documentation specialist. Write short, realistic clinical
note sentences for NER training data.

Every sentence must:
1. Contain exactly one mention of the target term.
2. State a definite, documented clinical fact -- something that HAS happened or
   IS recorded. Not a prediction, plan-note, or piece of advice.
3. Read like a GP or hospital note: concise, factual, past or present tense.
4. Name only the target term as a clinical entity -- no other diagnoses, drugs,
   tests, or procedures by name.
5. Be 8 to 20 words long.
6. Use factual language: past tense ("was found", "recorded", "confirmed", "noted")
   or present tense ("remains", "is documented", "shows").
7. Match the semantic type instruction in the user message.
8. Cancer pathway language: if the sentence describes a referral, 2WW, fast-track
   wait, or a suspected cancer clinic visit, you MUST name the clinical speciality
   or tumour site in the same sentence (e.g. urological, breast, lung, colorectal,
   skin, gynaecological, upper GI, head and neck, haematology). Do not write a
   vague referral with no site or stream.

Before writing each sentence, silently check:
  a) Does this sentence state a documented fact? (yes required)
  b) Does it match the requested semantic type? (yes required)
  c) Is the target term mentioned exactly once? (yes required)
  d) Are there any other named clinical entities? (no required)

Return ONLY a JSON array. No prose, no markdown, no commentary.

Output schema:
[
  {{
    "sentence": "<clinical sentence>",
    "assertion": "present|absent|historical|possible|planned|hypothetical"
  }}
]

Generate exactly {n_sentences} sentence objects.
"""

USER_PROMPT_TEMPLATE = """\
Generate synthetic NER training examples.

Target term   : {surface_form}
Full term     : {preferred_term}
SNOMED concept: {concept_id}
Semantic type : {semantic_tag}

Term usage rule: each sentence must contain EXACTLY ONE of the two forms below.
Pick one per sentence — never write both in the same sentence.
Never write "{surface_form} - {preferred_term}" or "{preferred_term} ({surface_form})".
Vary across your output so that some sentences use "{surface_form}" and some use "{preferred_term}".

How to write each sentence for this semantic type:
{tag_guidance}

Positive examples (write sentences like these):
[
  {{
    "sentence": "Type 2 diabetes remains well controlled.",
    "assertion": "present"
  }},
  {{
    "sentence": "No evidence of type 2 diabetes recorded.",
    "assertion": "absent"
  }},
  {{
    "sentence": "History of type 2 diabetes, diagnosed in 2018.",
    "assertion": "historical"
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
    gold_output_examples: list[dict[str, str]] | None = None,
    valueset_scope_titles: list[str] | None = None,
    domain_preferred_terms: list[str] | None = None,
) -> tuple[str, str, str]:
    """Return (system_prompt, user_prompt, clean_preferred_term).

    ``clean_preferred_term`` is the preferred term with any trailing SNOMED
    semantic qualifier stripped, e.g. 'Abdominal aortic aneurysm (disorder)'
    becomes 'Abdominal aortic aneurysm'.  The router should pass this to
    ``find_span`` as a fallback so sentences written with the full term
    (rather than the stored abbreviation) still produce a valid training span.
    """
    clean_preferred_term = _strip_snomed_qualifier(preferred_term)
    system_prompt = SYSTEM_PROMPT.format(n_sentences=n_sentences)
    raw_guidance = _TAG_GUIDANCE.get(semantic_tag, _DEFAULT_TAG_GUIDANCE)
    tag_guidance = raw_guidance.format(surface_form=surface_form)
    if semantic_tag == "procedure" and _is_referral_like(surface_form, preferred_term):
        tag_guidance += (
            " For referral or 2WW / fast-track wording, always pair the referral term "
            "with an explicit speciality or cancer site (UK notes style), e.g. "
            '"Urgent urological 2WW referral was raised."'
        )
    display_preferred = clean_preferred_term if clean_preferred_term else preferred_term
    user_prompt = USER_PROMPT_TEMPLATE.format(
        surface_form=surface_form,
        preferred_term=display_preferred,
        concept_id=concept_id,
        semantic_tag=semantic_tag,
        tag_guidance=tag_guidance,
    )
    examples = [str(x).strip() for x in (context_examples or []) if str(x).strip()]
    if examples:
        snippet_lines = "\n".join(f"- {snippet}" for snippet in examples[:10])
        user_prompt = (
            f"{user_prompt}\n\n"
            "Real de-identified note extracts (match this writing style):\n"
            f"{snippet_lines}\n"
        )
    style_examples = [
        {
            "sentence": str(item.get("sentence") or "").strip(),
            "assertion": str(item.get("assertion") or "").strip().lower(),
        }
        for item in (gold_output_examples or [])
        if isinstance(item, dict)
        and str(item.get("sentence") or "").strip()
        and str(item.get("assertion") or "").strip()
    ]
    if style_examples:
        style_json = json.dumps(style_examples[:5], ensure_ascii=False, indent=2)
        user_prompt = (
            f"{user_prompt}\n\n"
            "Verified gold output examples (match this output format exactly):\n"
            f"{style_json}\n"
        )

    vtitles = [str(t).strip() for t in (valueset_scope_titles or []) if str(t).strip()]
    vterms = [str(t).strip() for t in (domain_preferred_terms or []) if str(t).strip()][
        :50
    ]
    if vtitles or vterms:
        domain_lines: list[str] = []
        if vtitles:
            domain_lines.append(
                "Selected clinical domain(s): " + "; ".join(sorted(set(vtitles)))
            )
        if vterms:
            domain_lines.append(
                "Domain vocabulary (preferred-term names of other concepts in these "
                "domains; use ONLY as a short tumour site, stream, or speciality "
                "modifier in the same phrase as the target term — not as a second "
                "named diagnosis or procedure):\n" + "; ".join(vterms)
            )
        user_prompt = f"{user_prompt}\n\n" + "\n\n".join(domain_lines) + "\n"

    return system_prompt, user_prompt, clean_preferred_term
