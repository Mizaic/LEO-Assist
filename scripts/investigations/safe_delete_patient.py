"""Safe patient deletion utility.

Removes a patient and ALL their associated data from Neo4j:
  - EpisodeOfCare nodes (and HAS_EPISODE_OF_CARE relationships)
  - Encounter nodes (and HAS_ENCOUNTER relationships)
  - DOCUMENTS relationships on those encounters
  - The Patient node itself

Shared concept nodes (Disease, Situation, Clinical_finding, etc.) are
intentionally left intact -- they are referenced by many patients.

Usage (dry-run first, always):
    python safe_delete_patient.py --patient-id 9990002013
    python safe_delete_patient.py --patient-id 9990002013 --apply
"""

from __future__ import annotations

import argparse
import os
import sys

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

# -- path resolution ---------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from neo4j import GraphDatabase  # noqa: E402

# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------
_KV_URL = os.getenv("AZURE_KEYVAULT_URL", "")


def _load_secrets() -> dict[str, str]:
    uri = os.getenv("NEO4J_URI", "")
    user = os.getenv("NEO4J_USER", "")
    pw = os.getenv("NEO4J_PASSWORD", "")
    if uri and user and pw:
        return {"uri": uri, "user": user, "password": pw}
    if not _KV_URL:
        raise EnvironmentError(
            "Set AZURE_KEYVAULT_URL or NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD"
        )
    cred = DefaultAzureCredential()
    client = SecretClient(vault_url=_KV_URL, credential=cred)
    return {
        "uri": client.get_secret("NEO4J-URI").value,
        "user": client.get_secret("NEO4J-USER").value,
        "password": client.get_secret("NEO4J-PASSWORD").value,
    }


# ---------------------------------------------------------------------------
# Cypher
# ---------------------------------------------------------------------------

_Q_AUDIT = """
MATCH (p:Patient)
WHERE toString(p.id) = $pid
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter)
OPTIONAL MATCH (e)-[r:DOCUMENTS]->()
OPTIONAL MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
RETURN
    count(DISTINCT e)  AS encounter_count,
    count(DISTINCT r)  AS documents_count,
    count(DISTINCT ep) AS episode_count,
    count(DISTINCT p)  AS patient_exists
"""

_Q_DELETE_DOCUMENTS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->()
WHERE toString(p.id) = $pid
DELETE r
"""

_Q_DELETE_EPISODES = """
MATCH (p:Patient)-[rel:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
WHERE toString(p.id) = $pid
DELETE rel, ep
"""

_Q_DELETE_ENCOUNTERS = """
MATCH (p:Patient)-[rel:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $pid
DELETE rel, e
"""

_Q_DELETE_PATIENT = """
MATCH (p:Patient)
WHERE toString(p.id) = $pid
DETACH DELETE p
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _audit(session, pid: str) -> dict:
    row = session.run(_Q_AUDIT, pid=pid).single()
    if row is None:
        return {
            "patient_exists": 0,
            "encounter_count": 0,
            "documents_count": 0,
            "episode_count": 0,
        }
    return dict(row)


def _delete(session, pid: str) -> None:
    """Delete in dependency order inside a single transaction."""
    with session.begin_transaction() as tx:
        tx.run(_Q_DELETE_DOCUMENTS, pid=pid)
        tx.run(_Q_DELETE_EPISODES, pid=pid)
        tx.run(_Q_DELETE_ENCOUNTERS, pid=pid)
        tx.run(_Q_DELETE_PATIENT, pid=pid)
        tx.commit()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    ap.add_argument("--patient-id", required=True, help="Patient ID to delete")
    ap.add_argument(
        "--apply", action="store_true", help="Actually delete (omit for dry-run)"
    )
    args = ap.parse_args()

    pid = str(args.patient_id)
    secrets = _load_secrets()
    driver = GraphDatabase.driver(
        secrets["uri"],
        auth=(secrets["user"], secrets["password"]),
    )

    with driver.session() as session:
        counts = _audit(session, pid)

        print(f"\nPatient {pid} -- deletion audit")
        print(f"  Patient node exists : {bool(counts['patient_exists'])}")
        print(f"  Encounters          : {counts['encounter_count']}")
        print(f"  DOCUMENTS rels      : {counts['documents_count']}")
        print(f"  EpisodeOfCare nodes : {counts['episode_count']}")

        if not counts["patient_exists"]:
            print("\nPatient not found -- nothing to delete.")
            driver.close()
            return

        if not args.apply:
            print(
                "\nDRY-RUN complete.  Re-run with --apply to delete."
                "\nShared concept nodes (Disease, Situation, etc.) are "
                "preserved -- only patient-specific data is removed."
            )
            driver.close()
            return

        print("\nDeleting patient data...")
        _delete(session, pid)
        counts_after = _audit(session, pid)
        if not counts_after["patient_exists"]:
            print(f"Patient {pid} and all associated data deleted successfully.")
        else:
            print(
                "WARNING: patient node still exists after deletion -- "
                "check for unexpected relationships."
            )

    driver.close()


if __name__ == "__main__":
    main()
