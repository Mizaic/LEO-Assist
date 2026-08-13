"""Regression coverage for the "Unexplained DVT" checklist-label bug.

Real-world case: patient 9728344007 / referral 000049823847 (2WW breast).
The BR7 referral form's "Symptoms pathway (mandatory field)" checklist has a
row reading bare "Unexplained DVT" with NO checkbox glyph attached at all
(the docx checkbox content control for that specific row did not convert to
a "[ ]"/"[X]" text glyph, unlike its sibling rows). The extraction pipeline
coded this as a present "Deep venous thrombosis" finding, which then fired
NG12 1.13.4 ("DVT NSS triad") and surfaced an "Unexplained DVT" bullet in the
SBAR Background as if the patient actually had a DVT.

Two things had to both hold for this to reach the model uncorrected:
1. `normalize_form_checkbox_text` had to still mark the bare row as
   NON_EXTRACTABLE via its in-appendix/in-checklist fallback (it does --
   see `test_bare_checklist_row_with_no_checkbox_glyph_is_marked` below).
2. The extraction prompts had to actually explain what the
   "[NON_EXTRACTABLE]" marker means (they did not -- the marker was
   injected into the LLM's input text but never mentioned in
   EXTRACTION_SYSTEM_V1 / REFERRAL_EXTRACTION_SYSTEM_V1, so the model had
   no reason to treat it as anything other than stray text).

This file locks in the fix for (2) and the exact (1) scenario from the real
document, so this class of bug (a clinical-sounding checklist criterion or
appendix label with a lost/missing checkbox glyph) cannot silently regress.
"""

from __future__ import annotations

from libs.ner.form_checkbox_normalizer import (
    NON_EXTRACTABLE_MARKER,
    extractable_clinical_lines,
)
from libs.prompts.extraction_examples import EXTRACTION_EXAMPLES
from libs.prompts.extraction_v1 import EXTRACTION_SYSTEM_V1
from libs.prompts.referral_extraction_v1 import REFERRAL_EXTRACTION_SYSTEM_V1

# Verbatim (whitespace-normalised) reproduction of the BR7 form's
# "Symptoms pathway" table, ordinal 8 -- the "Unexplained DVT" row has no
# checkbox glyph at all, unlike every other row in the same checklist.
_BR7_SYMPTOMS_PATHWAY_TABLE = (
    "| Symptoms pathway (mandatory field): Please place x in relevant boxes |\n"
    "| --- |\n"
    "| [ ] New unexplained and unintentional weight loss (either documented "
    ">5% in three months or strong clinical suspicion) |\n"
    "| [ ] New unexplained vague abdominal pain for four weeks or more "
    "(less if very significant concern) with no associated change in bowel "
    "habit |\n"
    "| [ ] New unexplained, unexpected or progressive pain, including bone "
    "pain, of four weeks or more |\n"
    "| [ ] New unexplained constitutional symptoms for four weeks or more "
    "(less if very significant concern) Symptoms include loss of appetite, "
    "fatigue, nausea, bloating or malaise. |\n"
    "| Unexplained DVT |\n"
    "| [X] GP intuition or gut feeling (please state reasons you are "
    "concerned the patient has cancer in the section above) |"
)


def test_bare_checklist_row_with_no_checkbox_glyph_is_marked() -> None:
    """"Unexplained DVT" with zero checkbox glyph still gets excluded.

    Confirms the normaliser's in-checklist fallback catches a row that has
    neither "[ ]" nor "[X]" attached -- the exact BR7 failure mode, not the
    already-covered "[ ] Unexplained DVT" case.
    """
    lines = extractable_clinical_lines(_BR7_SYMPTOMS_PATHWAY_TABLE)
    joined = " ".join(lines).lower()
    assert "dvt" not in joined
    assert "thrombosis" not in joined
    # The ticked criterion in the same table is still extractable.
    assert "gut feeling" in joined


def test_extraction_prompts_document_the_non_extractable_marker() -> None:
    """The marker must be explained, or the model has no reason to obey it.

    This is the actual root cause of the DVT bug: the normaliser correctly
    tagged the row, but nothing in the system prompt told the model what
    "[NON_EXTRACTABLE]" means, so it kept reading "Unexplained DVT" as
    ordinary clinical text.
    """
    for prompt in (EXTRACTION_SYSTEM_V1, REFERRAL_EXTRACTION_SYSTEM_V1):
        assert NON_EXTRACTABLE_MARKER in prompt
        assert "Unexplained DVT" in prompt


def test_extraction_prompts_still_require_real_dvt_mentions() -> None:
    """The fix must not blanket-exclude DVT -- only marker-tagged spans.

    Guards against a lazy fix that just deletes "DVT" from extractable
    vocabulary. A genuinely documented, unmarked DVT mention must remain
    extractable per prompt instructions.
    """
    for prompt in (EXTRACTION_SYSTEM_V1, REFERRAL_EXTRACTION_SYSTEM_V1):
        lower = prompt.lower()
        assert "real" in lower or "genuine" in lower
        assert "must still be extracted" in lower or "extracted normally" in lower


def test_marker_few_shot_example_present_and_consistent() -> None:
    """The dedicated [NON_EXTRACTABLE]-marker few-shot example is well-formed.

    Teaches the model the marker excludes a span even with no checkbox
    glyph attached, while an adjacent unmarked ticked criterion is still
    extracted -- mirrors the real BR7 row pair.
    """
    marker_examples = [
        ex
        for ex in EXTRACTION_EXAMPLES
        if ex.get("category") == "form:checkbox"
        and NON_EXTRACTABLE_MARKER in ex.get("input", "")
    ]
    assert marker_examples, "expected a form:checkbox example demonstrating the marker"
    example = marker_examples[0]
    assert "Unexplained DVT" in example["input"]
    assert example["core"] is True
    assert '"terms": []' not in example["output"]
    assert "Unexplained DVT" not in example["output"]
    assert "gut feeling" in example["output"].lower()
