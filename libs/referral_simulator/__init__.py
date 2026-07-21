"""Shared referral simulator for production-shaped test scaffolds.

Materialises Patient + ReferralRequest + DocumentReference + Chunk graphs
and builds referral-received message bodies used by scenario runs and
extraction quick-run.

Atlas trace:
  VT: VT-C1B99249
  DI: DI-41D651DE
  Look up via: get_design_control(dc_type="verification-test", dc_id="VT-C1B99249")
"""

from libs.referral_simulator.cleanup import purge_legacy_scenario_encounter_patients
from libs.referral_simulator.ids import (
    document_reference_id,
    encounter_id_for_referral,
    referral_id_for_child_run,
    scenario_patient_id,
)
from libs.referral_simulator.message import (
    ReferralSimulatorError,
    build_referral_received_message,
)
from libs.referral_simulator.scaffold import (
    SOURCE_QUICK_TEST,
    SOURCE_SCENARIO,
    cleanup_referral_scaffold,
    scaffold_referral,
    split_into_chunks,
)

__all__ = [
    "SOURCE_QUICK_TEST",
    "SOURCE_SCENARIO",
    "ReferralSimulatorError",
    "build_referral_received_message",
    "cleanup_referral_scaffold",
    "document_reference_id",
    "encounter_id_for_referral",
    "purge_legacy_scenario_encounter_patients",
    "referral_id_for_child_run",
    "scaffold_referral",
    "scenario_patient_id",
    "split_into_chunks",
]
