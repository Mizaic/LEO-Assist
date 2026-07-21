"""Purge all Validation Lab synthetic data so the Lab starts empty.

Deletes, across both graphs:
  - :TestPatient + :RulesetReplay (knowledge graph) -- the retired
    Fixtures library.
  - :ValidationCase + its scaffolded Patient graph (source=validation-lab).
  - AI Summarisation scenario patients (source=ai_summarisation_scenario).
  - Quick Test patients (source=quick-test).

Real patient data (no synthetic `source` marker, no :TestPatient /
:ValidationCase label) is never touched.

Usage:
  python -m scripts.reset_validation_lab --yes
"""

from __future__ import annotations

import argparse

from libs.keyvault.loader import load_keyvault_secrets
from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient
from libs.validation_lab.reset import reset_validation_lab


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually delete. Without this flag the script is a no-op dry run.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    load_keyvault_secrets()
    if not args.yes:
        print(
            "Dry run (no --yes passed). Nothing deleted. Sources that would be purged:"
        )
        print("  knowledge graph: TestPatient, RulesetReplay")
        print(
            "  patient graph:   ValidationCase, validation-lab, "
            "ai_summarisation_scenario, quick-test"
        )
        return

    knowledge_client = KnowledgeGraphClient()
    patient_client = PatientGraphClient()
    try:
        report = reset_validation_lab(knowledge_client, patient_client)
    finally:
        knowledge_client.close()
        patient_client.close()

    print(f"Purged TestPatient nodes: {report.test_patients}")
    print(f"Purged RulesetReplay snapshots: {report.ruleset_replays}")
    print(f"Purged ValidationCase nodes: {report.validation_cases}")
    for source, count in report.patient_graph_by_source.items():
        print(f"Purged patient graph (source={source}): {count}")


if __name__ == "__main__":
    main()
