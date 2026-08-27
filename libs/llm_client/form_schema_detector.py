"""LLM-powered form structure detection for referral form schema teaching.

Sends the raw form text to the big-tier LLM once and returns proposed
FormSchema sections -- including clinical entity text for each checkbox item.

The clinician reviews and corrects the proposals in the UI before saving.

Atlas trace: DI-5C9CA57B, DO-D0C19842
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from libs.llm_client.factory import create_llm
from libs.llm_client.prompt_safety import (
    INJECTION_GUARD,
    cap_llm_response,
    sanitise_for_prompt,
)
from libs.pipeline.form_section_splitter import (
    is_incomplete_schema,
    split_form_sections,
)

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = INJECTION_GUARD + """
You are a clinical form structure analyser for NHS referral forms.
Given raw referral form text, identify every distinct section and classify it.

SECTION TYPES -- choose exactly one per section:
- checkbox_single  : Options where ONE is checked (e.g. cancer type tick-boxes)
- checkbox_yesno   : Each criterion has a Yes/No pair (e.g. B1 Yes [X] No [ ])
- scale            : Numbered/labelled scale, one item selected (Frailty, ECOG)
- free_text        : Narrative clinical prose -- ALWAYS PRESERVE for the LLM
- ordered_tests    : Mandatory tests and blood-result stubs -- KEEP
- observable       : Measured values such as BMI, BP, HR -- KEEP
- template_noise   : Repeat-print footer only -- skip
- admin            : Patient demographics, practice details, hospital number -- skip
Keep PMB pathway, patient awareness, ECOG, and Minimum Dataset vitals as
their own sections. Do not hide clinical blocks.

SECTION ARCHETYPE TAXONOMY (derived from NHS 2WW referral forms):
Map every section to the closest archetype below using the heading examples
as a guide. Unknown forms use the same structural vocabulary.

  1. admin_skip
     What it is: Administrative fields that add no clinical value for coding.
     Always classify as: admin (skip)
     default_semantic_tag: none
     Heading examples: "Patient Details", "GP Details", "Practice Address",
       "Trust Use Only", "For Hospital Use"

  2. cancer_type_select
     What it is: Tick-boxes where the referrer picks ONE suspected cancer site.
     Always classify as: checkbox_single
     default_semantic_tag: situation
     Heading examples: "Suspected Cancer Site", "Type of Cancer Suspected",
       "Please tick the most appropriate cancer type"

  3. referral_criteria
     What it is: Numbered NICE or local criteria, each with a Yes/No response.
     Always classify as: checkbox_yesno
     default_semantic_tag: finding
     Heading examples: "Referral Criteria", "B1", "B2", "Criterion A",
       "Does the patient have...", "Please check the relevant box"

  4. primary_care_pathway
     What it is: Conditional pathway flags; all criteria must be met.
     Always classify as: checkbox_yesno
     default_semantic_tag: finding
     Heading examples: "Primary Care Management Based (PMB) Pathway",
       "Before referring, confirm ALL of the following", "Primary Pathway"

  5. patient_awareness_consent
     What it is: Consent, availability, and awareness checks.
     Always classify as: checkbox_yesno
     default_semantic_tag: situation
     Heading examples: "Patient Awareness", "Patient Information",
       "Is your patient aware", "Date(s) patient unable to attend",
       "Is patient fit for day case investigation?"

  6. clinical_narrative
     What it is: Free-text clinical history and examination findings.
     Always classify as: free_text
     default_semantic_tag: finding
     Heading examples: "Reasons for Referral", "Clinical History",
       "Clinical Summary", "Presenting Symptoms", "Examination Findings",
       "Significant past and current medical history"

  7. medications_allergies
     What it is: Current medications list and allergy record.
     Always classify as: free_text
     default_semantic_tag: substance
     Heading examples: "Current Medication", "Medications", "Allergies",
       "Is patient on any of the following medications?"

  8. investigations_ordered
     What it is: Tests the GP must order or has already ordered.
     Always classify as: ordered_tests
     default_semantic_tag: procedure
     Heading examples: "Blood Tests", "Investigations", "FBC, U&Es",
       "FIT Value", "Pathology & Radiology Reports", "Recent blood results"

  9. performance_frailty_scale
     What it is: A scored scale with one selection (ECOG or CFS).
     Always classify as: scale
     default_semantic_tag: observable
     Heading examples: "Performance Status", "ECOG Performance Status",
       "Clinical Frailty Scale", "Please tick as appropriate"

  10. minimum_dataset_vitals
      What it is: Measured clinical values entered by the referrer.
      Always classify as: observable
      default_semantic_tag: observable
      Heading examples: "Minimum Dataset", "Vitals", "BMI", "Blood Pressure",
        "Height", "Weight", "Heart Rate"

  11. blood_results_table
      What it is: Blank result stubs for the GP to fill in (not orders).
      Always classify as: ordered_tests
      default_semantic_tag: procedure
      Heading examples: "Blood Results", "Lab Results", "FBC result",
        "eGFR", "Hb", "MCV", "Ferritin"

ITEMS (only for checkbox_single, checkbox_yesno, scale):
For each option provide:
  "pattern"     : the exact label text before the box, e.g. "Cervix"
  "entity_text" : CLINICAL meaning when checked, e.g. "Cervical cancer suspected"
  "semantic_tag": always "finding"
  "assertion"   : always "present"

Use precise clinical language for entity_text. Examples:
  "Cervix"      in cancer referral  -> "Cervical cancer suspected"
  "Ovary"       in cancer referral  -> "Ovarian cancer suspected"
  "Endometrium" in cancer referral  -> "Endometrial cancer suspected"
  "1. Very Fit" in frailty scale    -> "Clinical Frailty Scale: 1 - Very Fit"
  B1 lesion suspicious...           -> "Suspicious lesion on cervix or vagina"

Return one JSON object matching the supplied schema. No prose.
"""

_MAX_FORM_CHARS = 6000
_MAX_RESPONSE_CHARS = 16000
_MAX_TOKENS = 2048

_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["sections"],
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "section_id",
                    "label",
                    "section_type",
                    "start_pattern",
                    "items",
                    "default_semantic_tag",
                ],
                "properties": {
                    "section_id": {"type": "string"},
                    "label": {"type": "string"},
                    "section_type": {"type": "string"},
                    "start_pattern": {"type": "string"},
                    "default_semantic_tag": {"type": "string"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": [
                                "pattern",
                                "entity_text",
                                "semantic_tag",
                                "assertion",
                            ],
                            "properties": {
                                "pattern": {"type": "string"},
                                "entity_text": {"type": "string"},
                                "semantic_tag": {"type": "string"},
                                "assertion": {"type": "string"},
                            },
                        },
                    },
                },
            },
        }
    },
}


def detect_form_sections(text: str) -> list[dict[str, Any]]:
    """Call the big-tier LLM once to detect form sections.

    If the model is missing, the parse is empty, or the result is only
    admin / skip sections, fall back to the deterministic splitter so
    Section A / B on a table-wrapped form still appear.
    """
    cleaned = sanitise_for_prompt(text, max_chars=_MAX_FORM_CHARS)
    sections: list[dict[str, Any]] = []
    try:
        response = _call_detector(cleaned)
        sections = _parse_response(response.text or "") or []
    except Exception:
        log.warning("form-detect: LLM call failed", exc_info=True)
    if is_incomplete_schema(sections):
        fallback = split_form_sections(text)
        if not is_incomplete_schema(fallback):
            log.info("form-detect: splitter fallback found %d sections", len(fallback))
            return fallback
    log.info("form-detect: %d sections detected by LLM", len(sections))
    return sections


def _call_detector(form_text: str) -> Any:
    client = create_llm(tier="big")
    return client.converse(
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": form_text}],
        temperature=0.0,
        max_tokens=_MAX_TOKENS,
        json_mode=True,
        structured_schema=_OUTPUT_SCHEMA,
        agent_task="form_schema_detect",
    )


def _parse_response(text: str) -> list[dict[str, Any]] | None:
    """Extract and validate the sections list from the LLM response."""
    cleaned = cap_llm_response(text, max_chars=_MAX_RESPONSE_CHARS)
    cleaned = re.sub(r"```(?:json)?|```", "", cleaned).strip()
    parsed = _load_json(cleaned)
    if parsed is None:
        return None
    sections = parsed.get("sections") if isinstance(parsed, dict) else parsed
    if not isinstance(sections, list) or not sections:
        return None
    return [_validate_section(s) for s in sections if isinstance(s, dict)]


def _load_json(cleaned: str) -> Any | None:
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}|\[.*\]", cleaned, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None


def _validate_section(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "section_id": str(raw.get("section_id", "?")),
        "label": str(raw.get("label", "")),
        "section_type": str(raw.get("section_type", "free_text")),
        "start_pattern": str(raw.get("start_pattern", "")),
        "default_semantic_tag": str(raw.get("default_semantic_tag", "finding")),
        "items": [
            _validate_item(i) for i in raw.get("items", []) if isinstance(i, dict)
        ],
    }


def _validate_item(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "pattern": str(raw.get("pattern", "")),
        "entity_text": str(raw.get("entity_text", "")),
        "semantic_tag": str(raw.get("semantic_tag", "finding")),
        "assertion": str(raw.get("assertion", "present")),
    }
