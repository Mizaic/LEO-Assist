"""Non-production patient id constants for tests and redacted documentation.

These are 10-digit strings in the 99900xxxxx range. They are **not** real NHS
numbers and must never be used as live clinical identifiers. Use them only in
unit tests, fixtures, and doc examples.

For optional integration tests that require a pre-seeded graph (e.g. multi-
pathway gold cases), set ``EPISODE_GOLD_SEED_PATIENT_ID`` in the environment
to a **local** seed id; do not commit real practice patient ids.
"""

from __future__ import annotations

# --- Episode-engine / rulebook gold VT fixtures (replaces former embedded ids) ---
GOLD_COLORECTAL_CLOSED_BENIGN = "9990001001"
GOLD_BREAST_CLOSED_BENIGN = "9990001002"
GOLD_COLORECTAL_SCREEN_FIT = "9990001003"
GOLD_MULTI_PATHWAY = "9990001004"  # concurrent sites in unit tests
GOLD_PROSTATE_COMPLETED = "9990001005"

# --- UI / API test doubles ---
MISSION_CONTROL_FIXTURE = "9990001006"

# --- Example / dry-run script defaults (not linked to a real person) ---
EXAMPLE_READ_CODED_PROBLEM_LIST = "9990002001"

# --- Pattern-guard / local inspection exemplars (tests + one-off scripts) ---
# Use env overrides when pointed at a real seed graph; never commit practice ids.
PATTERN_GUARD_CARE_OBSTRUCTION_EXEMPLAR = "9990003001"

# Ordered list for VT / cohort scripts (same as individual constants)
GOLD_PATIENT_ORDER: tuple[str, ...] = (
    GOLD_COLORECTAL_CLOSED_BENIGN,
    GOLD_BREAST_CLOSED_BENIGN,
    GOLD_COLORECTAL_SCREEN_FIT,
    GOLD_MULTI_PATHWAY,
    GOLD_PROSTATE_COMPLETED,
)

GOLD_PATIENT_SET: frozenset[str] = frozenset(GOLD_PATIENT_ORDER)
