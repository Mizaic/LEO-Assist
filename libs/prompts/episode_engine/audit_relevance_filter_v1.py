"""Audit Relevance Filter prompt (DI-LEO-AI-524).

Cheap Haiku batched relevance triage for the encounters that the
always-keep guards have NOT already kept. The model receives up to 20
short encounter snippets at a time, plus the suspected cancer site, and
returns a per-encounter ``keep`` decision with a one-sentence
plain-English reason.

Reading age 9-11 throughout the prompt and in the model response.
"""

from __future__ import annotations

from libs.llm_client.prompt_safety import INJECTION_GUARD

VERSION = "v1"
TOOL_NAME = "submit_relevance"

SYSTEM = INJECTION_GUARD + (
    "You are a UK primary care cancer pathway focus assistant.\n"
    "You will look at a batch of short encounter notes and decide which\n"
    "ones to KEEP for a deeper cancer pathway audit.\n\n"
    "KEEP an encounter when it is about ANY of these:\n"
    "  - the suspected cancer or the work-up that looks for it\n"
    "    (symptoms, examinations, blood tests, scans, biopsies)\n"
    "  - the suspected body site or another name for the same site\n"
    "    (for example 'breast lump' and 'mass in breast' are the same)\n"
    "  - cancer treatment (surgery, hormone tablets, chemotherapy,\n"
    "    radiotherapy, immunotherapy)\n"
    "  - safety-netting advice about the cancer pathway\n"
    "    (for example 'come back if it gets worse', 'go to A and E if')\n"
    "  - pathway problems and delays\n"
    "    (missed referrals, lost letters, cancelled hospital visits,\n"
    "    did-not-attend events, results not back yet)\n\n"
    "DROP an encounter when it is about ANY of these:\n"
    "  - routine non-cancer care\n"
    "    (blood pressure check, flu jab, dentist, ear-wax referral,\n"
    "    repeat prescription review for an unrelated drug, podiatry)\n"
    "  - admin echoes with no clinical content\n"
    "    (failed encounter task, scheduling text message, booking\n"
    "    confirmation, prescription pickup record)\n\n"
    "When you are not sure, KEEP the encounter. Missing a real cancer\n"
    "pathway encounter is worse than keeping a few extra ones.\n\n"
    "For every encounter in the batch you MUST return one row with:\n"
    "  - encounter_id (copy it back exactly)\n"
    "  - keep (true or false)\n"
    "  - reason (one short sentence in plain English, no medical\n"
    "    jargon, no abbreviations on first use)\n\n"
    "Respond by calling the submit_relevance tool ONCE.\n"
)


USER_TEMPLATE = (
    "Patient: {patient_id}\n"
    "Window: {window_id}\n"
    "Suspected cancer site: {suspected_site}\n"
    "Batch: {batch_index} of {batch_total}\n"
    "\n"
    "Encounters to review (one per row):\n"
    "<encounters>\n"
    "{encounters_block}\n"
    "</encounters>\n"
    "\n"
    "For EVERY encounter above return a row with encounter_id, keep,\n"
    "and a one-sentence reason. Do not add or remove rows."
)


SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["decisions"],
    "properties": {
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["encounter_id", "keep", "reason"],
                "properties": {
                    "encounter_id": {"type": "string"},
                    "keep": {"type": "boolean"},
                    "reason": {
                        "type": "string",
                        "description": (
                            "One short plain-English sentence. "
                            "Reading age 9 to 11. No clinical jargon."
                        ),
                    },
                },
            },
        }
    },
}
