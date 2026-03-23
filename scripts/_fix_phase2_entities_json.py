"""Fix Phase 2 entities_json: update observable_entity -> procedure on TrainingLabels.

The main remediation script already resolved the CodingReview items but the
entities_json write ran after the reviews were resolved, so it found nothing.
This script queries the resolved reviews and updates TrainingLabel.entities_json
directly.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env")
load_dotenv(ROOT / "secrets" / ".env.secrets", override=True)

from neo4j import GraphDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def get_driver():
    uri = os.getenv("NEO4J_URI", "")
    user = os.getenv("NEO4J_USER", "neo4j")
    pwd = os.getenv("NEO4J_PASSWORD", "")
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    driver.verify_connectivity()
    return driver


# Query resolved Phase 2 reviews — these were observable_entity->procedure lab tests
GET_RESOLVED_LAB_TESTS = """
MATCH (cr:CodingReview)-[:REVIEWS_CODING]->(t:TrainingLabel)
WHERE t.include = true
  AND cr.resolved = true
  AND cr.resolved_method IN ['batch_resolve']
  AND cr.entity_label = 'observable_entity'
  AND cr.suggested_label = 'procedure'
RETURN DISTINCT cr.entity_text AS entity_text,
                t.label_id AS label_id,
                t.entities_json AS entities_json
ORDER BY cr.entity_text
"""

UPDATE_ENTITIES_JSON = """
MATCH (t:TrainingLabel {label_id: $label_id})
SET t.entities_json = $entities_json,
    t.updated_at    = datetime()
RETURN t.label_id AS label_id
"""


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", default=False)
    args = parser.parse_args()
    execute = args.execute
    mode = "EXECUTE" if execute else "DRY-RUN"
    logger.info("=== Phase 2 entities_json fix — %s ===", mode)

    driver = get_driver()
    updated = 0
    skipped = 0
    errors = 0

    with driver.session() as session:
        rows = list(session.run(GET_RESOLVED_LAB_TESTS))
        logger.info("Found %d (label_id, entity_text) pairs from resolved lab test reviews", len(rows))

        for row in rows:
            entity_text = row["entity_text"]
            label_id = row["label_id"]
            entities = json.loads(row["entities_json"] or "[]")

            changed = False
            for ent in entities:
                if ent.get("text") == entity_text and ent.get("label") == "observable_entity":
                    ent["label"] = "procedure"
                    changed = True

            if not changed:
                skipped += 1
                continue

            new_json = json.dumps(entities)
            if execute:
                try:
                    session.run(UPDATE_ENTITIES_JSON, label_id=label_id, entities_json=new_json)
                    updated += 1
                    logger.debug("  Updated %s: %r -> procedure", label_id, entity_text)
                except Exception as exc:
                    logger.warning("  ERROR %s: %s", label_id, exc)
                    errors += 1
            else:
                updated += 1
                logger.debug("  [DRY] Would update %s: %r -> procedure", label_id, entity_text)

    driver.close()
    logger.info("=== Done (%s) === updated=%d | skipped=%d | errors=%d", mode, updated, skipped, errors)


if __name__ == "__main__":
    main()
