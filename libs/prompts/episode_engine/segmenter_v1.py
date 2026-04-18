"""Stage 2 prompt: segment a patient timeline into candidate episode windows.

Inputs (USER_TEMPLATE):
    patient_id    : str
    timeline_text : the trunk view from timeline_loader

Output: SegmenterResult (see schemas.py).
"""

from __future__ import annotations

from libs.llm_client.prompt_safety import INJECTION_GUARD
from libs.prompts.episode_engine._shared import (
    BREAST_REFERENCE_CASE,
    RULES_OF_THE_ROAD,
)

VERSION = "v1"
TOOL_NAME = "submit_windows"

SYSTEM = INJECTION_GUARD + (
    "You are a UK primary care cancer pathway analyst. You are given a\n"
    "patient's full encounter timeline and must split it into CANDIDATE\n"
    "EPISODE WINDOWS for the next stages to classify and detail.\n\n"
    "A 'candidate episode window' is a contiguous date range that *might*\n"
    "represent one cancer pathway. You are NOT deciding whether the\n"
    "window is cancer -- the classifier does that. You are NOT extracting\n"
    "milestones -- the milestone extractor does that. Your only job is\n"
    "rough segmentation.\n\n"
    "Heuristics for window boundaries:\n"
    "  - A 2WW or fast-track referral typically opens a window.\n"
    "  - A confirmed diagnosis with no prior referral in scope opens a\n"
    "    window.\n"
    "  - A treatment-completed milestone or 12+ months of silence on the\n"
    "    pathway closes a window.\n"
    "  - DISTINCT cancers years apart get DISTINCT windows -- never merge.\n"
    "  - Multi-site referrals (e.g. breast + ovarian) on overlapping\n"
    "    dates: emit ONE window per site. The reconciler merges them\n"
    "    later if they prove to be the same primary.\n"
    "  - When in doubt, prefer MORE windows over fewer; reconciler will\n"
    "    merge.\n\n"
    + RULES_OF_THE_ROAD
    + "\n\n"
    + BREAST_REFERENCE_CASE
    + "\n\nRespond by calling the submit_windows tool with the JSON below.\n"
)


USER_TEMPLATE = (
    "Patient: {patient_id}\n"
    "\n"
    "Encounter timeline (compact, one section per date):\n"
    "<timeline>\n"
    "{timeline_text}\n"
    "</timeline>\n"
    "\n"
    "Identify candidate episode windows now."
)


SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["windows", "notes"],
    "properties": {
        "windows": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "window_id",
                    "suspected_site",
                    "window_start",
                    "rationale",
                ],
                "properties": {
                    "window_id": {
                        "type": "string",
                        "description": "Stable id within this call: w1, w2, ...",
                    },
                    "suspected_site": {
                        "type": "string",
                        "description": (
                            "Free-text body site (e.g. 'breast', 'colorectal', "
                            "'lung', 'unknown')."
                        ),
                    },
                    "window_start": {
                        "type": "string",
                        "description": "YYYY-MM-DD",
                    },
                    "window_end": {
                        "type": ["string", "null"],
                        "description": "YYYY-MM-DD or null if window is open.",
                    },
                    "rationale": {
                        "type": "string",
                        "description": "One sentence justifying this window.",
                    },
                },
            },
        },
        "notes": {
            "type": "string",
            "description": "Optional notes for the reviewer.",
        },
    },
}
