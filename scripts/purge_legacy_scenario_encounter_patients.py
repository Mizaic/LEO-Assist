"""Purge legacy Encounter-only AI summarisation scenario patients.

Usage:
  python -m scripts.purge_legacy_scenario_encounter_patients
"""

from __future__ import annotations

from libs.keyvault.loader import load_keyvault_secrets
from libs.referral_simulator.cleanup import purge_legacy_scenario_encounter_patients


def main() -> None:
    load_keyvault_secrets()
    deleted = purge_legacy_scenario_encounter_patients(
        patient_id_prefix="scenario-sbar-"
    )
    print(f"Purged {deleted} legacy scenario patient graph(s).")


if __name__ == "__main__":
    main()
