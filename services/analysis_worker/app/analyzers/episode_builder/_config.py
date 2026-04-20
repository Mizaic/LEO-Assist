"""Episode builder configuration with environment-variable overrides.

Atlas trace:
  DO: DO-694875ED
  Also implements: DO-6C398363
  DI: DI-080A2454
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-694875ED")
"""

from __future__ import annotations

import os
import sys
from datetime import date


def _parse_int_set(raw: str, default: frozenset[int]) -> frozenset[int]:
    values: set[int] = set()
    for token in (part.strip() for part in raw.split(",")):
        if not token:
            continue
        try:
            values.add(int(token))
        except ValueError:
            continue
    return frozenset(values) if values else default


# -- Episode time windows --------------------------------------------------
SAME_EPISODE_DAYS = int(os.getenv("EPISODE_SAME_EPISODE_DAYS", "180"))
DIAG_LOOKBACK_DAYS = int(os.getenv("EPISODE_DIAG_LOOKBACK_DAYS", "180"))

# DI-LEO-AI-124: minimum days between a referral anchor and a diagnosis
# anchor for the referral to be considered the trigger for that diagnosis.
# DI-LEO-AI-145: reduced to 0 to allow same-day PRISM-pathway referrals
# (one-stop breast/dermatology clinics where the GP completes the PRISM
# questionnaire and the suspected-cancer SNOMED code is entered in the
# same calendar day as the diagnosis letter is filed).
MIN_REFERRAL_TO_DIAG_DAYS = int(os.getenv("EPISODE_MIN_REFERRAL_TO_DIAG_DAYS", "0"))

# Auto-close thresholds (days)
STALE_HARD_DAYS = int(os.getenv("EPISODE_STALE_HARD_DAYS", "365"))
STALE_POST_SPECIALIST_DAYS = int(os.getenv("EPISODE_STALE_POST_SPECIALIST_DAYS", "90"))
PHANTOM_COMPLETED_WINDOW = int(os.getenv("EPISODE_PHANTOM_COMPLETED_WINDOW", "180"))

# Specialist outcome letter -- inferred benign completion (VT-087 / DI-087)
LETTER_WITHIN_DAYS_AFTER_VISIT = int(os.getenv("EPISODE_LETTER_WITHIN_DAYS", "60"))
NO_TREATMENT_WINDOW_AFTER_LETTER_DAYS = int(
    os.getenv("EPISODE_NO_TREATMENT_WINDOW", "120")
)

# Post-specialist outcome inference window
INFERENCE_POST_WINDOW_DAYS = int(os.getenv("EPISODE_INFERENCE_POST_WINDOW_DAYS", "180"))

# First presentation lookback / window parameters
FIRST_PRESENTATION_LOOKBACK_DAYS = int(os.getenv("EPISODE_FP_LOOKBACK_DAYS", "90"))
MAX_DAYS_PRESENTATION_TO_REFERRAL = int(
    os.getenv("EPISODE_MAX_DAYS_PRESENTATION_TO_REFERRAL", "14")
)
FALLBACK_REASON_WINDOW_DAYS_BEFORE = 21
FALLBACK_REASON_WINDOW_DAYS_AFTER = 3

MAX_BENIGN_CLOSURE_DAYS = 365
NO_CANCER_CONCEPT_ID = 395100000
BENIGN_QUALIFIER_WINDOW_DAYS = int(os.getenv("EPISODE_BENIGN_QUALIFIER_DAYS", "90"))
_DEFAULT_BENIGN_QUALIFIER_CONCEPT_IDS = frozenset(
    {30807003, 17621005, 263654008, 280413001, 2667000}
)
BENIGN_QUALIFIER_CONCEPT_IDS = _parse_int_set(
    os.getenv("EPISODE_BENIGN_QUALIFIER_CONCEPT_IDS", ""),
    _DEFAULT_BENIGN_QUALIFIER_CONCEPT_IDS,
)


def _today_for_episode_rules() -> date:
    """Return today's date, or a test-injected override.

    Tests set ``_TODAY_OVERRIDE`` on the *package* module
    (``episode_builder._TODAY_OVERRIDE = date(...)``).  This function
    reads that attribute through ``sys.modules`` so that sub-modules
    do not need a circular import back to ``__init__``.
    """
    pkg = sys.modules.get("services.analysis_worker.app.analyzers.episode_builder")
    override = getattr(pkg, "_TODAY_OVERRIDE", None) if pkg else None
    if override is not None:
        return override
    return date.today()
