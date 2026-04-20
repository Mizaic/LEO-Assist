"""Stage 3 prompt: classify a single candidate episode window.

Atlas trace:
  DO: DO-710D9EEB
  DI: DI-CBCA6E2D
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-710D9EEB")

Inputs (USER_TEMPLATE):
    patient_id      : str
    window_id       : str
    suspected_site  : str
    window_start    : str (YYYY-MM-DD)
    window_end      : str ("" or YYYY-MM-DD)
    window_text     : compact slice of the timeline within this window

Output: ClassifierResult (see schemas.py).
"""

from __future__ import annotations

from libs.llm_client.prompt_safety import INJECTION_GUARD
from libs.prompts.episode_engine._shared import EPISODE_TYPE_LIST, RULES_OF_THE_ROAD

VERSION = "v1"
TOOL_NAME = "submit_classification"

SYSTEM = INJECTION_GUARD + (
    "You are a UK primary care cancer pathway analyst. You will look at\n"
    "ONE candidate episode window and classify it as one of:\n"
    f"  {EPISODE_TYPE_LIST}\n\n"
    "Definitions:\n"
    "  cancer       : a confirmed cancer diagnosis exists, or referral +\n"
    "                 strong cancer-suspicion signal with the pathway\n"
    "                 progressing.\n"
    "  multi_site   : referrals to two or more body sites at overlapping\n"
    "                 dates and it is not yet clear if they are one\n"
    "                 primary or two -- reconciler will decide.\n"
    "  benign       : referral pathway concluded with a benign outcome\n"
    "                 (e.g. breast lump benign, polyp benign).\n"
    "  non_cancer   : the window does not represent a cancer pathway at\n"
    "                 all. Pick this rather than 'uncertain' when the\n"
    "                 segmenter clearly mis-flagged.\n"
    "  uncertain    : signal is ambiguous and the model cannot decide --\n"
    "                 the writer will set needs_human_review.\n\n"
    "Confidence: 0.95+ when there is structured-code evidence and a clear\n"
    "outcome; 0.7-0.9 when narrative is consistent but lacks codes; <0.7\n"
    "when key milestones are missing or contradictory.\n\n"
    + RULES_OF_THE_ROAD
    + "\n\nRespond by calling the submit_classification tool.\n"
)


USER_TEMPLATE = (
    "Patient: {patient_id}\n"
    "Window: {window_id}\n"
    "Suspected site: {suspected_site}\n"
    "Window start: {window_start}\n"
    "Window end: {window_end}\n"
    "\n"
    "Encounters in this window:\n"
    "<window>\n"
    "{window_text}\n"
    "</window>\n"
    "\n"
    "Classify this window now."
)


SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["window_id", "episode_type", "confidence", "reasoning"],
    "properties": {
        "window_id": {"type": "string"},
        "episode_type": {
            "type": "string",
            "enum": ["cancer", "multi_site", "benign", "non_cancer", "uncertain"],
        },
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "reasoning": {
            "type": "string",
            "description": "1-2 sentences citing the strongest evidence.",
        },
    },
}
