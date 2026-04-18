"""Stage 4 prompt: extract canonical milestones from one cancer or
multi-site window.

Inputs (USER_TEMPLATE):
    patient_id      : str
    window_id       : str
    suspected_site  : str
    window_start    : str
    window_end      : str
    window_full_text: full per-encounter snippets within the window
                      (one block per encounter_id)

Output: MilestoneExtractorResult.
"""

from __future__ import annotations

from libs.llm_client.prompt_safety import INJECTION_GUARD
from libs.prompts.episode_engine._shared import (
    MILESTONE_TYPE_LIST,
    PATIENT_4802892365_REFERENCE,
    RULES_OF_THE_ROAD,
    TREATMENT_TYPE_LIST,
)

VERSION = "v1"
TOOL_NAME = "submit_milestones"

SYSTEM = INJECTION_GUARD + (
    "You are a UK primary care cancer pathway analyst. You are given the\n"
    "full text of every encounter within ONE candidate episode window.\n"
    "Extract the canonical milestones from the window:\n"
    f"  {MILESTONE_TYPE_LIST}\n\n"
    "Rules for milestones:\n"
    "  - referral             : the source 2WW / fast-track / urgent\n"
    "                            cancer referral. Pick ONE -- the highest\n"
    "                            fidelity (PRISM / structured form) over\n"
    "                            free-text restatements on the same day.\n"
    "  - first_seen            : first specialist contact after referral\n"
    "                            (clinic visit, telephone consult).\n"
    "  - diagnosis_confirmed   : when the cancer diagnosis is confirmed,\n"
    "                            usually by histology or hospital letter.\n"
    "                            'PMHx of...' is NOT this.\n"
    "  - treatment_started     : the START of a definitive treatment\n"
    "                            modality. tag treatment_type from:\n"
    f"                            {TREATMENT_TYPE_LIST}.\n"
    "                            Neoadjuvant endocrine therapy and the\n"
    "                            subsequent surgery are SEPARATE\n"
    "                            treatment_started milestones.\n"
    "  - treatment_completed   : completion of the definitive course.\n"
    "  - benign_closure        : ONLY for benign windows; the date the\n"
    "                            benign outcome was confirmed.\n\n"
    "For every milestone:\n"
    "  - encounter_id MUST be the id of the SOURCE encounter, not an\n"
    "    admin echo. Reject 'Failed encounter', receptionist booking,\n"
    "    text-message confirmation, prescription pickup as the source.\n"
    "  - evidence_quote MUST be a literal substring of that encounter's\n"
    "    text (do not paraphrase).\n"
    "  - confidence < 0.6 -> set needs_human_review=true.\n"
    "  - If a milestone type genuinely does not occur in the window,\n"
    "    OMIT it. Do not fabricate.\n\n"
    + RULES_OF_THE_ROAD
    + "\n\n"
    + PATIENT_4802892365_REFERENCE
    + "\n\nRespond by calling the submit_milestones tool.\n"
)


USER_TEMPLATE = (
    "Patient: {patient_id}\n"
    "Window: {window_id}\n"
    "Suspected site: {suspected_site}\n"
    "Window start: {window_start}\n"
    "Window end: {window_end}\n"
    "\n"
    "Encounters within this window (full per-encounter snippets):\n"
    "<encounters>\n"
    "{window_full_text}\n"
    "</encounters>\n"
    "\n"
    "Extract milestones now. Cite encounter_id and evidence_quote for each."
)


SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["window_id", "milestones", "needs_human_review", "reasoning"],
    "properties": {
        "window_id": {"type": "string"},
        "milestones": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "type",
                    "date",
                    "encounter_id",
                    "evidence_quote",
                    "confidence",
                    "reasoning",
                ],
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "referral",
                            "first_seen",
                            "diagnosis_confirmed",
                            "treatment_started",
                            "treatment_completed",
                            "benign_closure",
                        ],
                    },
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "encounter_id": {"type": "string"},
                    "evidence_quote": {
                        "type": "string",
                        "description": (
                            "Literal substring of the source encounter text."
                        ),
                    },
                    "treatment_type": {
                        "type": ["string", "null"],
                        "enum": [
                            "surgery",
                            "endocrine",
                            "chemotherapy",
                            "radiotherapy",
                            "immunotherapy",
                            "other",
                            None,
                        ],
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                    },
                    "reasoning": {"type": "string"},
                },
            },
        },
        "needs_human_review": {"type": "boolean"},
        "reasoning": {"type": "string"},
    },
}
