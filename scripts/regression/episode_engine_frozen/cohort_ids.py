"""Frozen 20-patient regression cohort for the Haiku episode engine.

These ids are pinned. They span:

  - the original spike cohort (10 patients incl. 4802892365, the breast-cancer
    patient that motivated the rule -> LLM rewrite)
  - 10 more high-encounter patients chosen at baseline-generation time

Do NOT renumber. The frozen baseline JSON is keyed by patient_id and any
new id added here MUST be appended (not inserted) AND a new baseline must
be regenerated and committed in the same change.
"""

from __future__ import annotations

# Spike cohort -- includes the canonical 4802892365 case
SPIKE_COHORT: tuple[str, ...] = (
    "4802892365",
    "4926916703",
    "4563706582",
    "4563591157",
    "4921442355",
    "4245132175",
    "6309359401",
    "4926940965",
    "6040304227",
    "4587360686",
)

# Additional high-encounter patients picked from the live graph
EXTENDED_COHORT: tuple[str, ...] = (
    "7011988319",
    "6261656266",
    "4640519532",
    "6263830379",
    "6310920987",
    "4483039911",
    "4200797127",
    "6280880796",
    "7313758405",
    "4505618269",
)

FROZEN_COHORT: tuple[str, ...] = SPIKE_COHORT + EXTENDED_COHORT

assert len(set(FROZEN_COHORT)) == 20, "Frozen cohort must have 20 unique ids."
