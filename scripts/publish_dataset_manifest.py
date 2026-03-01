"""Publish the versioned dataset manifest for downstream model training.

Reads summary.json, qa_report.json, and training_adapters/spacy/meta.json
from exports/ner/all_domains/ and writes:

    exports/ner/all_domains/manifest.json

The manifest is the cross-plan handoff contract:
    - dataset_version, schema_version, deid_version
    - domains list with record/entity counts
    - quality_metrics (clean %, reject %, de-id issue rates)
    - seed_merge block (seed_rows_in, kept, deduped, rejected, reason_counts)
    - training_adapter_paths
    - file hashes (SHA-256) for reproducible verification

Run after:
    python scripts/mine_all_domains.py
    python scripts/qa_all_domains_ner.py
    python scripts/export_training_adapters.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

ALL_DOMAINS_DIR = ROOT / "exports" / "ner" / "all_domains"

# Version constants — bump these when schema or de-id rules change
DATASET_VERSION = "v1.0.0"
SCHEMA_VERSION = "v1"
DEID_VERSION = "v1"   # mirrors libs/utils/deidentify.py + deid_validator.py version


# ---------------------------------------------------------------------------
# File hash
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _line_count(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for _ in f:
            count += 1
    return count


# ---------------------------------------------------------------------------
# Build manifest
# ---------------------------------------------------------------------------

def build_manifest(
    all_domains_dir: Path,
    dataset_version: str,
    schema_version: str,
    deid_version: str,
) -> dict[str, Any]:
    summary_path = all_domains_dir / "summary.json"
    qa_path = all_domains_dir / "qa_report.json"
    merged_path = all_domains_dir / "domain_entities_merged.jsonl"
    rejected_path = all_domains_dir / "domain_entities_rejected.jsonl"
    adapter_meta_path = all_domains_dir / "training_adapters" / "spacy" / "meta.json"

    summary: dict[str, Any] = {}
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))

    qa: dict[str, Any] = {}
    if qa_path.exists():
        qa = json.loads(qa_path.read_text(encoding="utf-8"))

    adapter_meta: dict[str, Any] = {}
    if adapter_meta_path.exists():
        adapter_meta = json.loads(adapter_meta_path.read_text(encoding="utf-8"))

    # Prefer merge_audit.json as authoritative domain source (produced by merge_ner_runs.py).
    # Fall back to qa_report / summary for backward compatibility.
    merge_audit_path = all_domains_dir / "merge_audit.json"
    merge_audit: dict[str, Any] = {}
    if merge_audit_path.exists():
        merge_audit = json.loads(merge_audit_path.read_text(encoding="utf-8"))

    domain_record_counts: dict[str, int] = (
        merge_audit.get("domain_record_counts")
        or qa.get("domain_record_counts")
        or summary.get("qa_pass", {}).get("domain_record_counts")
        or summary.get("domain_record_counts")
        or {}
    )
    domain_entity_counts: dict[str, int] = (
        merge_audit.get("domain_entity_counts")
        or qa.get("domain_entity_counts")
        or summary.get("domain_entity_counts")
        or {}
    )

    # Discover domain files — only include those with at least 1 record so stale
    # files from previous pipeline formats don't inflate the domain count.
    domain_files = sorted(all_domains_dir.glob("domain_*.jsonl"))
    domains_info: list[dict[str, Any]] = []
    for df in domain_files:
        if df.name == "domain_entities_merged.jsonl":
            continue
        domain_name = df.stem.removeprefix("domain_").removeprefix("entities_")
        lc = _line_count(df)
        if lc == 0:
            continue  # skip empty stale files
        domains_info.append(
            {
                "domain": domain_name,
                "file": df.name,
                "record_count": lc,
                "entity_count": domain_entity_counts.get(domain_name, 0),
                "sha256": _sha256_file(df),
            }
        )

    # Quality metrics
    mined_total = qa.get("mined_records_total") or summary.get("records_written", 0)
    mined_clean = qa.get("mined_records_clean") or 0
    mined_rejected = qa.get("mined_records_rejected") or 0
    final_records = qa.get("final_merged_records") or _line_count(merged_path)

    quality_metrics: dict[str, Any] = {
        "mined_records_total": mined_total,
        "mined_records_clean": mined_clean,
        "mined_records_rejected": mined_rejected,
        "final_merged_records": final_records,
        "clean_pct": round(mined_clean / max(mined_total, 1) * 100, 2),
        "rejected_pct": round(mined_rejected / max(mined_total, 1) * 100, 2),
        "deid_reject_reasons": qa.get("deid_reject_reasons") or {},
        "precision_reject_reasons": qa.get("precision_reject_reasons") or {},
        "schema_reject_reasons": qa.get("schema_reject_reasons") or {},
    }

    # Seed merge audit block
    seed_merge: dict[str, Any] = qa.get("seed_integration") or {}

    # Training adapter paths
    adapter_outputs: dict[str, Any] = adapter_meta.get("outputs") or {}

    # File hashes for reproducibility
    file_hashes: dict[str, str | None] = {
        "domain_entities_merged.jsonl": _sha256_file(merged_path),
        "domain_entities_rejected.jsonl": _sha256_file(rejected_path),
        "qa_report.json": _sha256_file(qa_path),
        "summary.json": _sha256_file(summary_path),
    }
    if adapter_meta_path.exists():
        file_hashes["training_adapters/spacy/train.spacy"] = _sha256_file(
            all_domains_dir / "training_adapters" / "spacy" / "train.spacy"
        )
        file_hashes["training_adapters/spacy/dev.spacy"] = _sha256_file(
            all_domains_dir / "training_adapters" / "spacy" / "dev.spacy"
        )

    manifest: dict[str, Any] = {
        "dataset_version": dataset_version,
        "schema_version": schema_version,
        "deid_version": deid_version,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "source": "raw_encounter_text_only",
        "domains": domains_info,
        "domain_count": len(domains_info),
        "quality_metrics": quality_metrics,
        "seed_merge": seed_merge,
        "training_adapters": adapter_outputs,
        "file_hashes": file_hashes,
        "artifact_paths": {
            "merged_jsonl": str(merged_path),
            "rejected_jsonl": str(rejected_path),
            "qa_report": str(qa_path),
            "summary": str(summary_path),
            "manifest": str(all_domains_dir / "manifest.json"),
            "training_adapters_dir": str(all_domains_dir / "training_adapters"),
        },
        "compatibility_promise": {
            "stable_label_enum": True,
            "deterministic_ids": True,
            "strict_offset_validity": True,
            "reproducible_dataset_versioning": True,
        },
    }
    return manifest


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(ALL_DOMAINS_DIR))
    parser.add_argument("--dataset-version", default=DATASET_VERSION)
    parser.add_argument("--schema-version", default=SCHEMA_VERSION)
    parser.add_argument("--deid-version", default=DEID_VERSION)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    manifest = build_manifest(
        all_domains_dir=out_dir,
        dataset_version=args.dataset_version,
        schema_version=args.schema_version,
        deid_version=args.deid_version,
    )

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Manifest written: %s", manifest_path)

    print(
        json.dumps(
            {
                "dataset_version": manifest["dataset_version"],
                "schema_version": manifest["schema_version"],
                "deid_version": manifest["deid_version"],
                "domains": manifest["domain_count"],
                "final_merged_records": manifest["quality_metrics"]["final_merged_records"],
                "seed_merge": manifest["seed_merge"],
                "manifest": str(manifest_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
