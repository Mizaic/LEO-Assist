"""Stage 2 prompt: segment a patient timeline into candidate episode windows.

Atlas trace:
  DO: DO-710D9EEB
  DI: DI-CBCA6E2D
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-710D9EEB")

Inputs (USER_TEMPLATE):
    patient_id    : str
    timeline_text : the trunk view from timeline_loader

Output: SegmenterResult (see schemas.py).
"""

from __future__ import annotations

from libs.llm_client.prompt_safety import INJECTION_GUARD
from libs.oncology.cancer_types import CANONICAL_CANCER_TYPES
from libs.prompts.episode_engine._shared import (
    BREAST_REFERENCE_CASE,
    CANCER_TYPE_PICKER,
    COLORECTAL_FOBT_BCSP_FIRST_REFERENCE,
    COLORECTAL_SCREENING_SAME_DAY_REFERENCE,
    MULTI_SITE_REFERENCE_CASE,
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
    "  - A&E / walk-in / out-of-hours first attendance for a\n"
    "    site-consistent symptom, OR a hospital-issued handoff to a cancer\n"
    "    / urgent-suspected pathway, opens a window even if no GP 2WW\n"
    "    has happened yet. Do not require a prior surgery referral.\n"
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
    "ADDITIONAL HEURISTICS FOR COMPLEX MULTI-SITE CASES:\n\n"
    "  GP-ONLY INVESTIGATION WINDOWS (no 2WW required):\n"
    "    A cluster of GP-ordered investigations (blood tests, plain X-ray,\n"
    "    spirometry, stool tests, lung function) targeting a specific\n"
    "    symptom opens a candidate window even WITHOUT a 2WW referral.\n"
    "    Set window_start to the first GP consultation for that symptom.\n"
    "    Set window_end to the date the result/outcome is recorded. If the\n"
    "    outcome is normal or benign and the patient is not referred onwards,\n"
    "    the window closes at that result date.\n"
    "    Example: cough + chest X-ray ordered by GP + 'X-ray clear' result\n"
    "    -> Lung window from first cough consultation to X-ray result date.\n\n"
    "  SHARED FIRST PRESENTATION, MULTIPLE PATHWAYS:\n"
    "    A single GP consultation that presents symptoms pointing to\n"
    "    MULTIPLE possible sites (e.g. 'cough + weight loss + abdominal\n"
    "    pain', or 'PR bleeding + shortness of breath') must produce ONE\n"
    "    window per suspected site, each sharing the SAME window_start.\n"
    "    One window may close early (benign result for that site) while\n"
    "    the others stay open. DO NOT collapse multi-symptom presentations\n"
    "    into a single window -- the reconciler cannot split a window but\n"
    "    CAN merge two windows.\n\n"
    "  SAME-DAY MULTI-SITE 2WW REFERRALS:\n"
    "    When two 2WW forms are submitted on the same day for different\n"
    "    body sites (e.g. breast 2WW and upper-GI 2WW both on 12 Aug),\n"
    "    emit one window per site with the same window_start. Do not\n"
    "    assume one is the 'real' referral and drop the other.\n\n"
    "  A&E / HOSPITAL-FIRST ENTRY (no preceding GP 2WW in the record):\n"
    "    If the first dated, site-relevant text is A&E, AMU, MAU, or a\n"
    "    same-day care centre with onward referral, open the window on\n"
    "    the date of that attendance. A patient may have bypassed the GP\n"
    "    entirely. Example: 'Attended A&E with visible haematuria,\n"
    "    accepted under urology' -> open the urology window at that\n"
    "    encounter date, not a later admin entry.\n\n"
    + RULES_OF_THE_ROAD
    + "\n\n"
    + CANCER_TYPE_PICKER
    + "\n\n"
    + BREAST_REFERENCE_CASE
    + "\n\n"
    + MULTI_SITE_REFERENCE_CASE
    + "\n\n"
    + COLORECTAL_SCREENING_SAME_DAY_REFERENCE
    + "\n\n"
    + COLORECTAL_FOBT_BCSP_FIRST_REFERENCE
    + "\nRespond by calling the submit_windows tool with the JSON below.\n"
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
                        "enum": list(CANONICAL_CANCER_TYPES),
                        "description": (
                            "MUST be one of the NCDA cancer types. Use "
                            "'Unknown Primary' when the site cannot be "
                            "determined from the encounter text. Use 'No "
                            "Information' if no clinical evidence at all. "
                            "Use 'Other' for cancers outside the standard "
                            "NCDA list (e.g. salivary gland, anal canal "
                            "without colorectal context)."
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
