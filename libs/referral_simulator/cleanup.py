"""One-shot cleanup for legacy Encounter-only scenario patients.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")
"""

from __future__ import annotations

from libs.neo4j_client.client import PatientGraphClient
from libs.referral_simulator.message import ReferralSimulatorError
from libs.referral_simulator.scaffold import SOURCE_SCENARIO

# Deletes scenario patients (and their source-scoped encounters / docs / chunks /
# referrals). Used to clear Encounter-text scaffolds before re-running via the
# referral simulator. Always bound to source + id prefix -- never a bare MATCH.
PURGE_LEGACY_SCENARIO_ENCOUNTER_PATIENTS = """
MATCH (p:Patient)
WHERE p.source = $source
  AND p.id STARTS WITH $patient_id_prefix
WITH collect(p) AS patients
WITH patients, size(patients) AS deleted_count
UNWIND patients AS p
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter {source: $source})
OPTIONAL MATCH (p)-[:HAS_DOCUMENT_REFERENCE]->(dr:DocumentReference {source: $source})
OPTIONAL MATCH (dr)-[:HAS_CHUNK]->(c:Chunk)
OPTIONAL MATCH (rr:ReferralRequest {source: $source})-[:FOR_PATIENT]->(p)
DETACH DELETE e, c, dr, rr, p
RETURN deleted_count
"""


def purge_legacy_scenario_encounter_patients(
    *,
    patient_id_prefix: str = "scenario-sbar-",
) -> int:
    """Detach-delete legacy scenario patients matching id prefix + source."""
    if not str(patient_id_prefix or "").strip():
        raise ReferralSimulatorError("patient_id_prefix is required for purge")
    client = PatientGraphClient()
    try:
        rows = client.run(
            PURGE_LEGACY_SCENARIO_ENCOUNTER_PATIENTS,
            source=SOURCE_SCENARIO,
            patient_id_prefix=patient_id_prefix,
        )
    finally:
        client.close()
    if not rows:
        return 0
    return int(rows[0].get("deleted_count") or 0)
