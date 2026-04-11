"""Upload a trained spaCy NER model to Azure Blob Storage.

Usage
-----
    python scripts/upload_model.py \\
        --version 1.3 \\
        --model-dir models/medspacy_clinical_ner \\
        --schema-version 1.0 \\
        --deid-version 1.0 \\
        --label-version 1.0 \\
        --dataset-version 20260301 \\
        --notes "Trained on 2026-03-01 gold set"

This script:
1. Uploads the model directory to Azure Blob Storage via ModelStore.
2. Registers the version in ModelRegistry if not already present.
3. Runs the CompatibilityGate against the training manifest.
4. If all checks pass: starts offline validation using any stored eval metrics.

The inference service is NOT reloaded here — only ModelRegistry.promote()
triggers a hot-swap.  Promote separately after reviewing offline eval results.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Allow running from the repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Upload trained NER model to blob store"
    )
    parser.add_argument(
        "--version", required=True, help="Model version string e.g. 1.3"
    )
    parser.add_argument(
        "--model-dir",
        required=True,
        help="Local path to trained spaCy model directory",
    )
    parser.add_argument("--schema-version", default="1.0")
    parser.add_argument("--deid-version", default="1.0")
    parser.add_argument("--label-version", default="1.0")
    parser.add_argument("--dataset-version", default="")
    parser.add_argument("--notes", default="")
    parser.add_argument(
        "--manifest",
        default="",
        help="Path to training manifest.json for compatibility gate check",
    )
    parser.add_argument(
        "--offline-precision",
        type=float,
        default=None,
        help="Offline eval precision (0-1). If provided, runs offline validation.",
    )
    parser.add_argument(
        "--offline-recall",
        type=float,
        default=None,
        help="Offline eval recall (0-1). If provided, runs offline validation.",
    )
    args = parser.parse_args()

    from libs.model_store import ModelStore
    from libs.model_registry.registry import ModelRecord, ModelRegistry
    from libs.model_registry.manifest_reader import CompatibilityGate

    # 1. Compatibility gate (if manifest supplied)
    if args.manifest:
        gate = CompatibilityGate(
            required_schema_version=os.getenv("MODEL_REQUIRED_SCHEMA_VERSION", "1.0"),
            required_deid_version=os.getenv("MODEL_REQUIRED_DEID_VERSION", "1.0"),
            required_label_version=os.getenv("MODEL_REQUIRED_LABEL_VERSION", "1.0"),
        )
        result = gate.check(
            manifest_path=args.manifest,
            model_schema_version=args.schema_version,
            model_deid_version=args.deid_version,
            model_label_mapping_version=args.label_version,
            model_dataset_version=args.dataset_version,
        )
        if result.warnings:
            for w in result.warnings:
                logger.warning("Compatibility warning: %s", w)
        if not result.passed:
            for f in result.failures:
                logger.error("Compatibility FAIL: %s", f)
            logger.error("Upload aborted: compatibility gate failed.")
            return 1
        logger.info("Compatibility gate: PASSED")

    # 2. Upload to blob
    store = ModelStore()
    blob_uri = store.upload(
        model_dir=args.model_dir,
        version=args.version,
        schema_version=args.schema_version,
        deid_version=args.deid_version,
        label_mapping_version=args.label_version,
        dataset_version=args.dataset_version,
        notes=args.notes,
    )
    logger.info("Uploaded: %s", blob_uri)

    # 3. Register in ModelRegistry
    reg = ModelRegistry()
    if reg.get(args.version) is None:
        rec = ModelRecord(
            model_name=os.getenv("CODING_MODEL_NAME", "medspacy_clinical_ner"),
            model_version=args.version,
            model_path=args.model_dir,
            training_dataset_version=args.dataset_version,
            schema_version=args.schema_version,
            deid_version=args.deid_version,
            artifact_uri=blob_uri,
            notes=args.notes,
        )
        reg.register(rec)
    else:
        # Update the artifact URI on the existing record
        existing = reg.get(args.version)
        existing.artifact_uri = blob_uri
        reg._save()

    logger.info("Registered v%s in model registry", args.version)

    # 4. Offline validation (if metrics provided)
    if args.offline_precision is not None and args.offline_recall is not None:
        rec = reg.validate_offline(
            args.version,
            precision=args.offline_precision,
            recall=args.offline_recall,
            notes=args.notes,
        )
        logger.info(
            "Offline validation: status=%s (P=%.3f R=%.3f)",
            rec.status,
            args.offline_precision,
            args.offline_recall,
        )
        if rec.status != "offline_validated":
            logger.warning(
                "Model did NOT pass offline validation thresholds — not eligible for canary."
            )
            return 2

    logger.info(
        "Upload complete. Next step: run ModelRegistry.start_canary('%s') "
        "and then ModelRegistry.promote('%s') after canary KPIs pass.",
        args.version,
        args.version,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
