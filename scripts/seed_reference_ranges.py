"""Deprecated: patient-graph reference ranges were retired.

Lab metadata now lives in the Knowledge Graph as LabResultConfig nodes.
Use scripts/seed_lab_result_config.py or the Results/Labs tab instead.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from libs.neo4j_client.client import KnowledgeGraphClient  # noqa: E402
from scripts.seed_lab_result_config import seed_if_missing  # noqa: E402

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.warning(
        "seed_reference_ranges.py is deprecated; seeding Knowledge Graph "
        "LabResultConfig via seed_lab_result_config.py instead."
    )
    client = KnowledgeGraphClient()
    try:
        seed_if_missing(client)
    finally:
        client.close()


if __name__ == "__main__":
    main()
