"""Merge all per-run NER mining outputs into a single deduplicated corpus.

Scans every folder under exports/ner/runs/ for domain_entities_merged.jsonl,
deduplicates across all runs using stable SHA-256 keys, and writes the final
merged corpus to exports/ner/all_domains/.

Outputs:
    exports/ner/all_domains/domain_entities_merged.jsonl   (deduped, all runs)
    exports/ner/all_domains/domain_<domain>.jsonl          (per-domain subsets)
    exports/ner/all_domains/merge_audit.json               (run counts, dedup stats)

Run after one or more mine_all_domains.py runs, before qa_all_domains_ner.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from collections import defaultdict
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

DEFAULT_RUNS_DIR = ROOT / "exports" / "ner" / "runs"
DEFAULT_OUT_DIR = ROOT / "exports" / "ner" / "all_domains"


# ---------------------------------------------------------------------------
# Stable dedupe key (mirrors seed_ingester._dedupe_key)
# ---------------------------------------------------------------------------


def _dedupe_key(record: dict[str, Any]) -> str:
    import re

    text_norm = re.sub(r"\s+", " ", (record.get("text") or "").lower().strip())
    spans = sorted(
        (int(e.get("start", 0)), int(e.get("end", 0)), str(e.get("label", "")))
        for e in (record.get("entities") or [])
    )
    raw = text_norm + "|" + json.dumps(spans, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def merge_runs(
    runs_dir: Path,
    out_dir: Path,
    run_pattern: str = "*/domain_entities_merged.jsonl",
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)

    run_files = sorted(runs_dir.glob(run_pattern))
    if not run_files:
        logger.warning("No run files found matching %s/%s", runs_dir, run_pattern)

    seen_keys: set[str] = set()
    all_records: list[dict[str, Any]] = []

    run_stats: list[dict[str, Any]] = []

    for run_file in run_files:
        run_name = run_file.parent.name
        run_in = 0
        run_kept = 0
        run_deduped = 0
        run_invalid = 0

        with run_file.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                run_in += 1
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    run_invalid += 1
                    continue

                if not rec.get("text") or not rec.get("entities"):
                    run_invalid += 1
                    continue

                key = _dedupe_key(rec)
                if key in seen_keys:
                    run_deduped += 1
                    continue

                seen_keys.add(key)
                # Tag which run this record came from
                meta = dict(rec.get("metadata") or {})
                meta.setdefault("run_id", run_name)
                rec["metadata"] = meta
                all_records.append(rec)
                run_kept += 1

        logger.info(
            "Run %-25s  in=%d  kept=%d  deduped=%d  invalid=%d",
            run_name,
            run_in,
            run_kept,
            run_deduped,
            run_invalid,
        )
        run_stats.append(
            {
                "run_id": run_name,
                "file": str(run_file),
                "records_in": run_in,
                "records_kept": run_kept,
                "records_deduped": run_deduped,
                "records_invalid": run_invalid,
            }
        )

    # Sort deterministically by document_id for reproducible output
    all_records.sort(key=lambda r: r.get("document_id") or "")

    # Write merged
    merged_path = out_dir / "domain_entities_merged.jsonl"
    with merged_path.open("w", encoding="utf-8") as mf:
        for rec in all_records:
            mf.write(json.dumps(rec, ensure_ascii=False) + "\n")
    logger.info("Merged %d records → %s", len(all_records), merged_path)

    # Write per-domain files
    per_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    domain_entity_counts: dict[str, int] = defaultdict(int)
    for rec in all_records:
        domains_in_rec = {
            e.get("domain") for e in (rec.get("entities") or []) if e.get("domain")
        }
        for dm in domains_in_rec:
            per_domain[dm].append(rec)
            domain_entity_counts[dm] += sum(
                1 for e in rec.get("entities", []) if e.get("domain") == dm
            )

    domain_record_counts: dict[str, int] = {}
    for dm, recs in sorted(per_domain.items()):
        domain_file = out_dir / f"domain_{dm}.jsonl"
        with domain_file.open("w", encoding="utf-8") as df:
            for rec in sorted(recs, key=lambda r: r.get("document_id") or ""):
                df.write(json.dumps(rec, ensure_ascii=False) + "\n")
        domain_record_counts[dm] = len(recs)

    total_in = sum(r["records_in"] for r in run_stats)
    total_ded = sum(r["records_deduped"] for r in run_stats)

    audit: dict[str, Any] = {
        "runs_scanned": len(run_files),
        "runs_dir": str(runs_dir),
        "total_records_in": total_in,
        "total_records_kept": len(all_records),
        "total_records_deduped": total_ded,
        "domain_record_counts": dict(sorted(domain_record_counts.items())),
        "domain_entity_counts": dict(sorted(domain_entity_counts.items())),
        "per_run": run_stats,
        "outputs": {
            "merged_jsonl": str(merged_path),
            "per_domain_files": [
                str(out_dir / f"domain_{dm}.jsonl") for dm in sorted(per_domain)
            ],
        },
    }
    (out_dir / "merge_audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info(
        "Merge complete: runs=%d  in=%d  kept=%d  deduped=%d  domains=%d",
        len(run_files),
        total_in,
        len(all_records),
        total_ded,
        len(per_domain),
    )
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runs-dir",
        default=str(DEFAULT_RUNS_DIR),
        help="Directory containing run subfolders.",
    )
    parser.add_argument(
        "--out-dir",
        default=str(DEFAULT_OUT_DIR),
        help="Output directory for merged corpus.",
    )
    parser.add_argument(
        "--run-ids",
        nargs="*",
        default=[],
        help="Restrict to specific run IDs (subfolder names). "
        "Default: all runs in --runs-dir.",
    )
    args = parser.parse_args()

    runs_dir = Path(args.runs_dir)
    out_dir = Path(args.out_dir)

    if args.run_ids:
        # Only merge specified runs
        pattern = f"{{{','.join(args.run_ids)}}}/domain_entities_merged.jsonl"
    else:
        pattern = "*/domain_entities_merged.jsonl"

    audit = merge_runs(runs_dir=runs_dir, out_dir=out_dir, run_pattern=pattern)
    print(
        json.dumps(
            {
                "runs_scanned": audit["runs_scanned"],
                "total_records_in": audit["total_records_in"],
                "total_records_kept": audit["total_records_kept"],
                "total_records_deduped": audit["total_records_deduped"],
                "domains": len(audit["domain_record_counts"]),
                "merged_jsonl": audit["outputs"]["merged_jsonl"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
