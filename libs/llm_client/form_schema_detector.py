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
from libs.pipeline.form_schema_section_types import (
    VALID_SECTION_TYPES,
    coerce_section_type,
)
from libs.pipeline.form_section_splitter import (
    is_incomplete_schema,
    split_form_sections,
)

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    INJECTION_GUARD
    + """
You are a clinical form structure analyser for NHS referral forms.
Given raw referral form text, identify every distinct section and classify it.

INPUT FORMAT -- markdown pipe tables:
The text is almost always a markdown table, not plain lines. Read it as
cells separated by "|", and apply these rules:
- Section headings sit INSIDE a table cell, for example
  "| Section A: Cancer type suspected |". Strip the leading and trailing
  "|" and any padding spaces before you read the heading.
- A separator row such as "| --- |" or "| --- | --- |" follows almost
  every heading. Separator rows are layout only. Never treat one as a
  heading, an item, or clinical content.
- A label and its answer are often in DIFFERENT cells of the same row,
  for example "| B1. Lesion on cervix | Yes [X] No [ ] |". The pattern is
  the label cell; the boxes are in a later cell.
- A question row may span three columns while its answer sits on the NEXT
  row with fewer cells, for example "| Question? | Yes | No |" followed by
  "| [X] | [ ] |". Treat the question and the row below it as one item.
- Blood battery rows use empty spacer cells, for example
  "| FBC |  | Hb , WCC , Plts |  |  |". The battery is the first non-empty
  cell; the analytes are a comma separated list in a later cell. An
  analyte may sit in a different column from its battery, for example
  "| CRP |  |  | ESR |  |".
- A line such as "--- Document: name.pdf ---" marks the start of a second
  document appended to the same bundle. Everything after it is an
  administrative wrapper. Classify it as admin.

start_pattern must be the heading text WITHOUT the surrounding pipes.

SECTION TYPES -- choose exactly one per section. Use one of these exact
strings. "checkbox" on its own is not a section type and will be rejected:
- checkbox_single  : Options where ONE is checked (e.g. cancer type tick-boxes)
- checkbox_multi   : Options where MORE THAN ONE may be checked
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
     default_semantic_tags: ["none"]
     Heading examples: "Patient Details", "GP Details", "Practice Address",
       "Trust Use Only", "For Hospital Use"

  2. cancer_type_select
     What it is: Tick-boxes where the referrer picks ONE suspected cancer site.
     Always classify as: checkbox_single
     default_semantic_tags: ["situation"]
     Heading examples: "Suspected Cancer Site", "Type of Cancer Suspected",
       "Please tick the most appropriate cancer type"

  3. referral_criteria
     What it is: Numbered NICE or local criteria, each with a Yes/No response.
     Always classify as: checkbox_yesno
     default_semantic_tags: ["finding"]
     Heading examples: "Referral Criteria", "B1", "B2", "Criterion A",
       "Does the patient have...", "Please check the relevant box"

  4. primary_care_pathway
     What it is: Conditional pathway flags; all criteria must be met.
     Always classify as: checkbox_yesno
     default_semantic_tags: ["finding"]
     Heading examples: "Primary Care Management Based (PMB) Pathway",
       "Before referring, confirm ALL of the following", "Primary Pathway"

  5. patient_awareness_consent
     What it is: Consent, availability, and awareness checks.
     Always classify as: checkbox_yesno
     default_semantic_tags: ["situation"]
     Heading examples: "Patient Awareness", "Patient Information",
       "Is your patient aware", "Date(s) patient unable to attend",
       "Is patient fit for day case investigation?"

  6. clinical_narrative
     What it is: Free-text clinical history and examination findings.
     Always classify as: free_text
     default_semantic_tags: ["finding"]
     Heading examples: "Reasons for Referral", "Clinical History",
       "Clinical Summary", "Presenting Symptoms", "Examination Findings",
       "Significant past and current medical history", "Additional clinical
       information"
     The heading is often on its own line; the narrative usually sits in a
     box or field on the lines below, not on the same line as the label.
     Treat every line from after the heading until the next section header
     as part of the same free_text section. Do not stop at the header line.

  7. medications_allergies
     What it is: Current medications list and allergy record.
     Always classify as: free_text
     default_semantic_tags: ["substance"]
     Heading examples: "Current Medication", "Medications", "Allergies",
       "Is patient on any of the following medications?"

  8. investigations_ordered
     What it is: Tests the GP must order or has already ordered.
     Always classify as: ordered_tests
     default_semantic_tags: ["procedure"]
     Heading examples: "Blood Tests", "Investigations", "FBC, U&Es",
       "FIT Value", "Pathology & Radiology Reports", "Recent blood results"

  9. performance_frailty_scale
     What it is: A scored scale with one selection (ECOG or CFS).
     Always classify as: scale
     default_semantic_tags: ["observable"]
     Heading examples: "Performance Status", "ECOG Performance Status",
       "Clinical Frailty Scale", "Please tick as appropriate"

  10. minimum_dataset_vitals
      What it is: Measured clinical values entered by the referrer.
      Always classify as: observable
      default_semantic_tags: ["observable"]
      Heading examples: "Minimum Dataset", "Vitals", "BMI", "Blood Pressure",
        "Height", "Weight", "Heart Rate"

  11. blood_results_table
      What it is: Blank result stubs for the GP to fill in (not orders).
      Always classify as: ordered_tests
      default_semantic_tags: ["procedure", "observable"]
      Heading examples: "Blood Results", "Lab Results", "FBC result",
        "eGFR", "Hb", "MCV", "Ferritin"

ITEMS (only for checkbox_single, checkbox_yesno, scale):
For each option provide:
  "pattern"     : the exact label text before the box, e.g. "Cervix"
  "entity_text" : CLINICAL meaning when checked, e.g. "Cervical cancer suspected"
  "semantic_tag": always "finding"
  "assertion"   : always "present"
  "procedure_snomed" : "" (leave blank -- filled by the teacher)
  "procedure_display": "" (leave blank)
  "analytes"    : [] (leave empty)
  "value_placeholder": ""

ITEMS (for ordered_tests sections -- blood results tables):
For each test battery row provide:
  "pattern"     : the battery label as it appears in the form, e.g. "FBC"
  "entity_text" : full display name, e.g. "Full blood count"
  "semantic_tag": "procedure"
  "assertion"   : "present"
  "procedure_snomed" : "" (leave blank -- filled by the teacher or SNOMED lookup)
  "procedure_display": the battery display name, e.g. "Full blood count"
  "analytes"    : list of individual result entries visible in the battery row.
                  Each analyte:
                    {"label": "<short name>", "snomed_code": "", "display": "<name>"}
                  Example for FBC: [
                    {"label": "Hb",   "snomed_code": "", "display": "Haemoglobin"},
                    {"label": "WCC",  "snomed_code": "", "display": "White cell count"},
                    {"label": "Plts", "snomed_code": "", "display": "Platelet count"}
                  ]
                  Leave snomed_code blank -- the teacher fills it in the UI.
  "value_placeholder": "{{NUMERIC_VALUE}} {{UNIT}}"

Use precise clinical language for entity_text. Examples:
  "Cervix"      in cancer referral  -> "Cervical cancer suspected"
  "Ovary"       in cancer referral  -> "Ovarian cancer suspected"
  "Endometrium" in cancer referral  -> "Endometrial cancer suspected"
  "1. Very Fit" in frailty scale    -> "Clinical Frailty Scale: 1 - Very Fit"
  B1 lesion suspicious...           -> "Suspicious lesion on cervix or vagina"

Return one JSON object matching the supplied schema. No prose.
"""
)

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
                    "default_semantic_tags",
                ],
                "properties": {
                    "section_id": {"type": "string"},
                    "label": {"type": "string"},
                    "section_type": {
                        "type": "string",
                        "enum": sorted(VALID_SECTION_TYPES),
                    },
                    "start_pattern": {"type": "string"},
                    "default_semantic_tags": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
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
                                "procedure_snomed",
                                "procedure_display",
                                "analytes",
                                "value_placeholder",
                            ],
                            "properties": {
                                "pattern": {"type": "string"},
                                "entity_text": {"type": "string"},
                                "semantic_tag": {"type": "string"},
                                "assertion": {"type": "string"},
                                "procedure_snomed": {"type": "string"},
                                "procedure_display": {"type": "string"},
                                "analytes": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "required": [
                                            "label",
                                            "snomed_code",
                                            "display",
                                        ],
                                        "properties": {
                                            "label": {"type": "string"},
                                            "snomed_code": {"type": "string"},
                                            "display": {"type": "string"},
                                        },
                                    },
                                },
                                "value_placeholder": {"type": "string"},
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
    """Normalise one proposed section.

    The section type is coerced rather than rejected: this is a proposal
    the clinician reviews and can change in the teach dialog, and one bad
    value must not throw away every other section the model found. The
    substitution is logged, and the API still refuses to save anything
    outside the vocabulary.
    """
    return {
        "section_id": str(raw.get("section_id", "?")),
        "label": str(raw.get("label", "")),
        "section_type": coerce_section_type(
            raw.get("section_type", "free_text"),
            source="llm form-schema detector",
        ),
        "start_pattern": str(raw.get("start_pattern", "")),
        "default_semantic_tags": _coerce_semantic_tags(raw),
        "items": [
            _validate_item(i) for i in raw.get("items", []) if isinstance(i, dict)
        ],
    }


def _coerce_semantic_tags(raw: dict[str, Any]) -> list[str]:
    """Return a list from default_semantic_tags, falling back to legacy singular."""
    if "default_semantic_tags" in raw:
        val = raw["default_semantic_tags"]
        if isinstance(val, list):
            return [str(t) for t in val] if val else ["finding"]
    if "default_semantic_tag" in raw:
        return [str(raw["default_semantic_tag"])]
    return ["finding"]


def _validate_item(raw: dict[str, Any]) -> dict[str, Any]:
    analytes = raw.get("analytes") or []
    if not isinstance(analytes, list):
        analytes = []
    safe_analytes = [
        {
            "label": str(a.get("label", "")),
            "snomed_code": str(a.get("snomed_code", "")),
            "display": str(a.get("display", "")),
        }
        for a in analytes
        if isinstance(a, dict)
    ]
    return {
        "pattern": str(raw.get("pattern", "")),
        "entity_text": str(raw.get("entity_text", "")),
        "semantic_tag": str(raw.get("semantic_tag", "finding")),
        "assertion": str(raw.get("assertion", "present")),
        "procedure_snomed": str(raw.get("procedure_snomed", "")),
        "procedure_display": str(raw.get("procedure_display", "")),
        "analytes": safe_analytes,
        "value_placeholder": str(raw.get("value_placeholder", "")),
    }
