#!/usr/bin/env python3
"""Download cancer-related text datasets from Hugging Face.

Searches for datasets matching 'cancer' with text modality and downloads them
to a local directory. Requires: pip install huggingface_hub datasets

Usage:
    python scripts/download_hf_cancer_datasets.py [--output-dir DIR] [--limit N] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download cancer-related text datasets from Hugging Face"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/hf_cancer_datasets"),
        help="Directory to save datasets (default: data/hf_cancer_datasets)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of datasets to download (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only list datasets, do not download",
    )
    parser.add_argument(
        "--trust-remote-code",
        action="store_true",
        help="Allow loading datasets with custom code",
    )
    args = parser.parse_args()

    try:
        from huggingface_hub import HfApi
    except ImportError:
        logger.error(
            "huggingface_hub not installed. Run: pip install huggingface_hub datasets"
        )
        return 1

    api = HfApi()
    logger.info("Searching for cancer text datasets on Hugging Face...")

    # Search: cancer, filter by text modality (matches HF datasets page),
    # sort by downloads (trending).
    datasets_iter = api.list_datasets(
        search="cancer",
        filter=["modality:text"],
        sort="downloads",
    )

    dataset_ids: list[str] = []
    for info in datasets_iter:
        dataset_ids.append(info.id)
        if args.limit and len(dataset_ids) >= args.limit:
            break

    logger.info("Found %d dataset(s)", len(dataset_ids))

    if args.dry_run:
        for i, ds_id in enumerate(dataset_ids, 1):
            print(f"  {i}. {ds_id}")
        return 0

    args.output_dir.mkdir(parents=True, exist_ok=True)
    results_path = args.output_dir / "download_results.jsonl"
    results: list[dict] = []

    try:
        from datasets import load_dataset
    except ImportError:
        logger.error("datasets not installed. Run: pip install datasets")
        return 1

    for i, ds_id in enumerate(dataset_ids, 1):
        logger.info("[%d/%d] Downloading %s...", i, len(dataset_ids), ds_id)
        try:
            ds = load_dataset(
                ds_id,
                trust_remote_code=args.trust_remote_code,
            )
            out_path = args.output_dir / ds_id.replace("/", "_")
            out_path.mkdir(parents=True, exist_ok=True)
            ds.save_to_disk(str(out_path))
            results.append({"id": ds_id, "status": "ok", "path": str(out_path)})
            logger.info("  -> saved to %s", out_path)
        except Exception as e:
            logger.warning("  -> failed: %s", e)
            results.append({"id": ds_id, "status": "error", "error": str(e)})

    with open(results_path, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    ok = sum(1 for r in results if r["status"] == "ok")
    logger.info(
        "Done. %d succeeded, %d failed. Results: %s",
        ok,
        len(results) - ok,
        results_path,
    )
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
