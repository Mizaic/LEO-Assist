r"""Ingest QA-clean training records into Neo4j TrainingLabel nodes.

Reads the merged JSONL from the NER pipeline and writes each record
as a TrainingLabel node via the existing bulk_upsert helper.  This is
the bridge between the offline mining pipeline and the UX-managed
training workflow.

Usage:
    .\.venv\Scripts\python.exe scripts\ingest_training_labels.py
    .\.venv\Scripts\python.exe scripts\ingest_training_labels.py --input exports\ner\all_domains\domain_entities_merged.jsonl
    .\.venv\Scripts\python.exe scripts\ingest_training_labels.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from libs.ner.training_label_writer import bulk_upsert_training_labels, make_label_id

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DEFAULT_INPUT = (
    ROOT / "exports" / "ner" / "all_domains" / "domain_entities_merged.jsonl"
)
BATCH_SIZE = 500

SOURCE_MAP = {
    "seed_exclusion_v1": "seed",
    "mined_raw": "anchor_mining",
}


def _map_source(metadata: dict[str, Any]) -> str:
    origin = metadata.get("source_origin", "")
    return SOURCE_MAP.get(origin, "anchor_mining")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate but don't write to Neo4j",
    )
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        logger.error("Input file not found: %s", input_path)
        sys.exit(1)

    records: list[dict[str, Any]] = []
    with input_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            metadata = rec.get("metadata", {})
            source = _map_source(metadata)
            run_id = metadata.get("run_id", "")

            records.append(
                {
                    "encounter_id": rec.get("document_id", ""),
                    "patient_id": rec.get("document_id", ""),
                    "text": rec.get("text", ""),
                    "entities": rec.get("entities", []),
                    "quality_score": 1.0,
                    "_source": source,
                    "_source_ref": run_id or "ner_pipeline_v1",
                }
            )

    logger.info("Parsed %d records from %s", len(records), input_path.name)

    if args.dry_run:
        seed = sum(1 for r in records if r["_source"] == "seed")
        mined = sum(1 for r in records if r["_source"] == "anchor_mining")
        logger.info(
            "Dry run — seed=%d  anchor_mining=%d  total=%d", seed, mined, len(records)
        )
        print(
            json.dumps(
                {
                    "total": len(records),
                    "seed": seed,
                    "anchor_mining": mined,
                    "dry_run": True,
                },
                indent=2,
            )
        )
        return

    from libs.neo4j_client.client import PatientGraphClient
    from libs.cypher.training_label_queries import CREATE_TRAINING_LABEL_INDEXES

    client = PatientGraphClient()
    try:
        with client.session() as session:
            for idx_q in CREATE_TRAINING_LABEL_INDEXES:
                session.run(idx_q)
        logger.info("TrainingLabel indexes ensured.")

        total_ingested = 0
        t0 = time.time()

        for i in range(0, len(records), args.batch_size):
            batch = records[i : i + args.batch_size]
            source = batch[0]["_source"]
            source_ref = batch[0]["_source_ref"]

            cleaned = []
            for r in batch:
                cleaned.append(
                    {
                        "encounter_id": r["encounter_id"],
                        "patient_id": r["patient_id"],
                        "text": r["text"],
                        "entities": r["entities"],
                        "quality_score": r["quality_score"],
                    }
                )

            bulk_upsert_training_labels(
                cleaned,
                source=source,
                source_ref=source_ref,
                client=client,
            )
            total_ingested += len(batch)
            elapsed = time.time() - t0
            rate = total_ingested / max(elapsed, 0.001)
            logger.info(
                "Ingested %d / %d  (%.1f rec/s)",
                total_ingested,
                len(records),
                rate,
            )

    finally:
        client.close()

    elapsed = time.time() - t0
    logger.info(
        "Done: %d TrainingLabel nodes upserted in %.1fs", total_ingested, elapsed
    )
    print(
        json.dumps(
            {
                "total_ingested": total_ingested,
                "elapsed_s": round(elapsed, 1),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
