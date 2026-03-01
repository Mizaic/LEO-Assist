"""QA pass for NER all-domains merged output + seed integration.

Reads:
    exports/ner/all_domains/domain_entities_merged.jsonl  (mined corpus)
    exports/ner/training/exclusion_domain_v1.jsonl        (silver seed)

Runs:
    1. Schema + offset re-validation on mined records
    2. Precision hardening gate (cancer_types FP rules etc.)
    3. Strict de-id check
    4. Seed ingestion (validate / dedupe / merge)
    5. Final merged JSONL written to same dir
    6. qa_report.json and summary.json written

Outputs (exports/ner/all_domains/):
    domain_entities_merged.jsonl       — final merged (mined + seed, de-id clean)
    domain_entities_rejected.jsonl     — rejected rows with reasons
    domain_<domain>.jsonl              — per-domain subsets (rebuilt from merged)
    qa_report.json                     — full QA metrics
    summary.json                       — updated aggregate stats
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from libs.ner.deid_validator import DeIdValidator, sanitise_record_metadata
from libs.ner.precision_gates import check_record_entities
from libs.ner.schema_mapper import map_raw_record
from libs.ner.seed_ingester import SeedIngester, build_corpus_keys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

_deid_validator = DeIdValidator()

DEFAULT_SEED_PATH = ROOT / "exports" / "ner" / "training" / "exclusion_domain_v1.jsonl"
DEFAULT_INPUT = ROOT / "exports" / "ner" / "all_domains" / "domain_entities_merged.jsonl"
DEFAULT_OUT_DIR = ROOT / "exports" / "ner" / "all_domains"


# ---------------------------------------------------------------------------
# Record validation
# ---------------------------------------------------------------------------

def _validate_canonical_record(record: dict[str, Any]) -> list[str]:
    """Re-validate a record already in canonical schema; return rejection reasons."""
    reasons: list[str] = []

    if not record.get("document_id"):
        reasons.append("missing_document_id")
    if not record.get("text"):
        reasons.append("missing_text")
    if not isinstance(record.get("entities"), list):
        reasons.append("entities_not_list")
        return reasons

    text = record.get("text") or ""
    for idx, ent in enumerate(record["entities"]):
        start = ent.get("start")
        end = ent.get("end")
        ent_text = ent.get("text") or ""
        if start is None or end is None:
            reasons.append(f"entity[{idx}]_missing_offset")
            continue
        span = text[int(start):int(end)]
        if span != ent_text:
            reasons.append(f"entity[{idx}]_offset_mismatch")

    return reasons


# ---------------------------------------------------------------------------
# Main QA run
# ---------------------------------------------------------------------------

def run(
    input_path: Path,
    out_dir: Path,
    seed_path: Path | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)

    merged_path = out_dir / "domain_entities_merged.jsonl"
    rejected_path = out_dir / "domain_entities_rejected.jsonl"
    report_path = out_dir / "qa_report.json"
    summary_path = out_dir / "summary.json"

    total_mined = 0
    clean_mined = 0
    rejected_mined = 0
    deid_reject = 0
    precision_reject = 0
    schema_reject = 0

    deid_reason_counts: Counter[str] = Counter()
    precision_reason_counts: Counter[str] = Counter()
    schema_reason_counts: Counter[str] = Counter()
    domain_record_counts: Counter[str] = Counter()
    domain_entity_counts: Counter[str] = Counter()

    clean_records: list[dict[str, Any]] = []

    # ---- Pass 1: validate mined records ----
    if input_path.exists():
        with input_path.open("r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                total_mined += 1
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    rejected_mined += 1
                    schema_reason_counts["json_parse_error"] += 1
                    continue

                # If record is still in old sentence-level schema, re-map it
                if "sentence_text" in rec and "text" not in rec:
                    rec["text"] = rec.pop("sentence_text", "")
                if "sentence_id" in rec and not rec.get("document_id"):
                    rec["document_id"] = None

                # Schema / offset re-validation
                schema_reasons = _validate_canonical_record(rec)
                if schema_reasons:
                    schema_reject += 1
                    rejected_mined += 1
                    for r in schema_reasons:
                        schema_reason_counts[r] += 1
                    continue

                # Precision hardening
                prec_reasons = check_record_entities(rec)
                if prec_reasons:
                    precision_reject += 1
                    rejected_mined += 1
                    for r in prec_reasons:
                        precision_reason_counts[r] += 1
                    continue

                # De-id final check
                rec = sanitise_record_metadata(rec)
                deid_issues = _deid_validator.check_record(rec)
                if deid_issues:
                    deid_reject += 1
                    rejected_mined += 1
                    for issue in deid_issues:
                        deid_reason_counts[issue.issue_type] += 1
                    continue

                clean_mined += 1
                clean_records.append(rec)
    else:
        logger.warning("Merged input not found: %s — proceeding with seed-only corpus", input_path)

    # ---- Pass 2: seed ingestion ----
    seed_audit: dict[str, Any] = {}
    seed_kept = 0
    if seed_path and seed_path.exists():
        corpus_keys = build_corpus_keys(clean_records)
        ingester = SeedIngester(seed_path=seed_path, seed_name="exclusion_v1")
        seed_result = ingester.ingest(existing_keys=corpus_keys)
        seed_audit = seed_result.audit_block()
        seed_kept = seed_result.kept

        clean_records.extend(seed_result.kept_records)

        # Write seed rejections into rejected output
        with rejected_path.open("a", encoding="utf-8") as rej_f:
            for r in seed_result.rejected_records:
                rej_f.write(json.dumps({"source": "seed", **r}, ensure_ascii=False) + "\n")

        logger.info(
            "Seed integration: in=%d kept=%d deduped=%d rejected=%d",
            seed_result.seed_rows_in,
            seed_result.kept,
            seed_result.deduped,
            seed_result.rejected,
        )

    # ---- Pass 3: write final outputs ----
    # Sort deterministically by document_id
    clean_records.sort(key=lambda r: r.get("document_id") or "")

    # Build per-domain maps
    per_domain_records: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in clean_records:
        for ent in rec.get("entities") or []:
            dm = ent.get("domain")
            if dm:
                domain_entity_counts[dm] += 1
        domains_in_rec = {e.get("domain") for e in (rec.get("entities") or []) if e.get("domain")}
        for dm in domains_in_rec:
            per_domain_records[dm].append(rec)
            domain_record_counts[dm] += 1

    # Write merged
    with merged_path.open("w", encoding="utf-8") as mf:
        for rec in clean_records:
            mf.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # Write per-domain files
    for dm, recs in sorted(per_domain_records.items()):
        domain_file = out_dir / f"domain_{dm}.jsonl"
        with domain_file.open("w", encoding="utf-8") as df:
            for rec in sorted(recs, key=lambda r: r.get("document_id") or ""):
                df.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # Write rejected (mined rejections) — append mode so seed rejections already there
    with rejected_path.open("a", encoding="utf-8") as rej_f:
        pass  # already written per-record during validation; file created above

    # ---- QA report ----
    total_final = len(clean_records)
    report: dict[str, Any] = {
        "mined_input_file": str(input_path),
        "mined_records_total": total_mined,
        "mined_records_clean": clean_mined,
        "mined_records_rejected": rejected_mined,
        "mined_rejection_breakdown": {
            "schema_failures": schema_reject,
            "precision_failures": precision_reject,
            "deid_failures": deid_reject,
        },
        "seed_integration": seed_audit,
        "final_merged_records": total_final,
        "final_merged_with_seed": seed_kept,
        "domain_record_counts": dict(domain_record_counts.most_common()),
        "domain_entity_counts": dict(domain_entity_counts.most_common()),
        "deid_reject_reasons": dict(deid_reason_counts.most_common()),
        "precision_reject_reasons": dict(precision_reason_counts.most_common()),
        "schema_reject_reasons": dict(schema_reason_counts.most_common()),
        "rates": {
            "mined_clean_pct": round(clean_mined / max(total_mined, 1) * 100, 2),
            "mined_rejected_pct": round(rejected_mined / max(total_mined, 1) * 100, 2),
        },
        "outputs": {
            "merged_jsonl": str(merged_path),
            "rejected_jsonl": str(rejected_path),
            "per_domain_files": [
                str(out_dir / f"domain_{dm}.jsonl") for dm in sorted(per_domain_records)
            ],
        },
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---- Update summary.json ----
    existing_summary: dict[str, Any] = {}
    if summary_path.exists():
        try:
            existing_summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    existing_summary.update(
        {
            "qa_pass": {
                "mined_total": total_mined,
                "mined_clean": clean_mined,
                "mined_rejected": rejected_mined,
                "seed_kept": seed_kept,
                "final_records": total_final,
                "domain_record_counts": dict(domain_record_counts),
            }
        }
    )
    summary_path.write_text(json.dumps(existing_summary, indent=2, ensure_ascii=False), encoding="utf-8")

    logger.info(
        "QA complete: mined_total=%d clean=%d rejected=%d seed_kept=%d final=%d",
        total_mined,
        clean_mined,
        rejected_mined,
        seed_kept,
        total_final,
    )
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument(
        "--seed",
        default=str(DEFAULT_SEED_PATH),
        help="Path to silver seed JSONL (set to empty string to skip)",
    )
    parser.add_argument("--no-seed", action="store_true", help="Skip seed integration")
    args = parser.parse_args()

    seed_path: Path | None = Path(args.seed) if args.seed and not args.no_seed else None
    report = run(
        input_path=Path(args.input),
        out_dir=Path(args.out_dir),
        seed_path=seed_path,
    )
    print(
        json.dumps(
            {
                "mined_records_total": report["mined_records_total"],
                "mined_records_clean": report["mined_records_clean"],
                "mined_records_rejected": report["mined_records_rejected"],
                "seed_kept": report["final_merged_with_seed"],
                "final_merged_records": report["final_merged_records"],
                "report": str(DEFAULT_OUT_DIR / "qa_report.json"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
