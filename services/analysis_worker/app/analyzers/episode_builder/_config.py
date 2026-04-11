"""Episode builder configuration with environment-variable overrides."""

from __future__ import annotations

import os
import sys
from datetime import date

# -- Episode time windows --------------------------------------------------
SAME_EPISODE_DAYS = int(os.getenv("EPISODE_SAME_EPISODE_DAYS", "180"))
DIAG_LOOKBACK_DAYS = int(os.getenv("EPISODE_DIAG_LOOKBACK_DAYS", "180"))

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
