"""Export NER training data from DOCUMENTS relationships.

Produces spaCy-compatible JSONL for gold and silver labels, plus a
stratification report and export manifest.

Safety rules
------------
- PII gate: detect_phi() is run on every sentence before writing.
  If any PII is found, the ENTIRE export is aborted and the offending
  record IDs are written to a quarantine file.
- Post-export verification: scans every output line for encounter_id
  or patient_id patterns. Abort on match.
- encounter_id / patient_id are used only for grouping and are NEVER
  written to output files.

Allowed sources (gold): reviewer_correction, approved, gold
Allowed sources (silver): provisional, terminology_api, llm_auto_detected

Usage
-----
    python scripts/export_ner_training.py
    python scripts/export_ner_training.py --output-dir /tmp/ner_export
    python scripts/export_ner_training.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402

load_keyvault_secrets()

from libs.neo4j_client.client import PatientGraphClient  # noqa: E402
from libs.utils.deidentify import detect_phi  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("export_ner")

_DEFAULT_OUTPUT = ROOT / "scripts" / "investigations" / "ner_export"

_GOLD_SOURCES = {"reviewer_correction", "approved", "gold"}
_SILVER_SOURCES = {"provisional", "terminology_api", "llm_auto_detected"}
_ALLOWED_SOURCES = _GOLD_SOURCES | _SILVER_SOURCES

_SAFETY_CRITICAL_TAGS = {
    "cancer",
    "oncology",
    "safeguarding",
    "mental_health",
    "suicide",
}
_SAFETY_CRITICAL_ASSERTIONS = {"present", "historical"}
_SAFETY_MIN = 20
_IMBALANCE_MIN = 50

# ---------------------------------------------------------------------------
# Cypher queries
# ---------------------------------------------------------------------------

_Q_DOCUMENTS = """
MATCH (e:Encounter)-[r:DOCUMENTS]->(s)
WHERE r.evidence_sentence IS NOT NULL
  AND r.evidence_start >= 0
  AND (r.holdout IS NULL OR r.holdout = false)
  AND r.source IN $allowed_sources
WITH
    toString(e.id)          AS encounter_id,
    r.evidence_sentence     AS sentence,
    r.evidence_start        AS start,
    r.evidence_end          AS end_,
    r.evidence              AS span_text,
    r.sentence_index        AS sentence_index,
    coalesce(toString(s.semanticTag), 'other') AS semantic_tag,
    coalesce(r.context, '{}')                  AS context_json,
    toString(s.conceptId)                      AS concept_id,
    s.name                                     AS concept_name,
    r.source                                   AS source
ORDER BY encounter_id, sentence_index
"""

_Q_NEGATIVE_SENTENCES = """
MATCH (e:Encounter)
WHERE e.text IS NOT NULL AND trim(e.text) <> ''
AND NOT EXISTS {
    MATCH (e)-[r:DOCUMENTS]->()
    WHERE r.evidence_sentence IS NOT NULL
}
RETURN
    toString(e.id) AS encounter_id,
    e.text[..500]  AS sentence
LIMIT 2000
"""

# ---------------------------------------------------------------------------
# PII detection helpers
# ---------------------------------------------------------------------------

_ENC_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I
)
_PID_PATTERN = re.compile(r"\bpatient[_\-]?id\s*[=:]\s*[^\s,]+", re.I)


def _post_export_scan(path: Path) -> list[str]:
    """Return any lines containing encounter/patient ID patterns."""
    violations: list[str] = []
    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if _ENC_PATTERN.search(line) or _PID_PATTERN.search(line):
                violations.append(f"Line {i}: {line[:120]}")
    return violations


# ---------------------------------------------------------------------------
# Assertion extraction
# ---------------------------------------------------------------------------


def _extract_assertion(context_json: str) -> str:
    try:
        ctx = json.loads(context_json)
        return str(ctx.get("assertion") or "present")
    except Exception:
        return "present"


# ---------------------------------------------------------------------------
# Build JSONL records
# ---------------------------------------------------------------------------


def _build_record(
    sentence: str,
    spans: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a spaCy-format NER record."""
    return {
        "text": sentence,
        "spans": [
            {
                "start": s["start"],
                "end": s["end"],
                "label": s["semantic_tag"].upper(),
                "kb_id": s.get("concept_id") or "",
                "assertion": s.get("assertion") or "present",
            }
            for s in spans
            if s["start"] >= 0 and s["end"] > s["start"]
        ],
    }


# ---------------------------------------------------------------------------
# Stratification report
# ---------------------------------------------------------------------------


def _build_stratification_report(
    gold_rows: list[dict],
    silver_rows: list[dict],
    neg_count: int,
) -> str:
    from collections import Counter

    tag_counts: Counter = Counter()
    assertion_counts: Counter = Counter()
    safety_counts: Counter = Counter()

    for row in gold_rows + silver_rows:
        tag = str(row.get("semantic_tag") or "other").lower()
        assertion = str(row.get("assertion") or "present")
        tag_counts[tag] += 1
        assertion_counts[assertion] += 1
        for kw in _SAFETY_CRITICAL_TAGS:
            if kw in tag:
                safety_counts[tag] += 1

    lines = [
        "NER Training Corpus - Stratification Report",
        "=" * 44,
        f"Generated: {datetime.now(tz=timezone.utc).isoformat()}",
        "",
        f"Gold records  : {len(gold_rows)}",
        f"Silver records: {len(silver_rows)}",
        f"Negative sentences: {neg_count}",
        "",
        "Counts by semantic tag",
        "-" * 30,
    ]
    for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1]):
        warn = " WARNING: < 50 examples" if count < _IMBALANCE_MIN else ""
        lines.append(f"  {tag:<35} {count:>6}{warn}")

    lines += ["", "Counts by assertion", "-" * 30]
    for assertion, count in sorted(assertion_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  {assertion:<25} {count:>6}")

    lines += ["", "Safety-critical categories", "-" * 30]
    blocked_any = False
    for tag, count in sorted(safety_counts.items(), key=lambda x: -x[1]):
        blocked = count < _SAFETY_MIN
        if blocked:
            blocked_any = True
        status = "BLOCKED" if blocked else "ok"
        lines.append(f"  {tag:<35} {count:>6}  [{status}]")
    if not safety_counts:
        lines.append("  (none found)")

    if blocked_any:
        lines += ["", "WARNING: Safety-critical export is BLOCKED."]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main export logic
# ---------------------------------------------------------------------------


def _is_safety_critical_blocked(rows: list[dict]) -> bool:
    from collections import Counter

    counts: Counter = Counter()
    for row in rows:
        tag = str(row.get("semantic_tag") or "").lower()
        assertion = str(row.get("assertion") or "present")
        for kw in _SAFETY_CRITICAL_TAGS:
            if kw in tag and assertion in _SAFETY_CRITICAL_ASSERTIONS:
                counts[tag] += 1
    return any(c < _SAFETY_MIN for c in counts.values())


def export(output_dir: Path, dry_run: bool) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    client = PatientGraphClient()

    try:
        logger.info("Querying DOCUMENTS with evidence sentences ...")
        with client.session() as session:
            rows = [
                dict(r)
                for r in session.run(
                    _Q_DOCUMENTS, allowed_sources=list(_ALLOWED_SOURCES)
                )
            ]
            logger.info("Querying negative sentences ...")
            neg_rows = [dict(r) for r in session.run(_Q_NEGATIVE_SENTENCES)]
    finally:
        client.close()

    logger.info("Loaded %d positive rows, %d negative rows.", len(rows), len(neg_rows))

    # -- PII gate -----------------------------------------------------------
    phi_violations: list[str] = []
    for row in rows:
        sentence = str(row.get("sentence") or "")
        phi = detect_phi(sentence)
        if phi:
            phi_violations.append(f"{row.get('concept_id')}:{phi}")

    if phi_violations:
        quarantine = output_dir / "ner_phi_quarantine.txt"
        quarantine.write_text("\n".join(phi_violations), encoding="utf-8")
        logger.error(
            "evidence.phi_detected count=%d -- export ABORTED. " "Quarantine file: %s",
            len(phi_violations),
            quarantine,
        )
        sys.exit(1)

    # -- Add assertion to rows ----------------------------------------------
    for row in rows:
        row["assertion"] = _extract_assertion(str(row.get("context_json") or "{}"))

    # -- Safety-critical block check ----------------------------------------
    safety_blocked = _is_safety_critical_blocked(rows)
    if safety_blocked:
        logger.warning("Safety-critical categories are under the minimum threshold.")

    # -- Group by (encounter_id, sentence_index) -> multi-entity records -----
    gold_records: list[dict] = []
    silver_records: list[dict] = []

    grouped: dict[tuple, dict] = {}
    for row in rows:
        key = (row.get("encounter_id"), row.get("sentence_index"))
        if key not in grouped:
            grouped[key] = {
                "sentence": row["sentence"],
                "spans": [],
                "source": row.get("source"),
            }
        grouped[key]["spans"].append(row)

    for group in grouped.values():
        sentence = str(group["sentence"] or "")
        source = str(group["source"] or "")
        record = _build_record(sentence, group["spans"])
        if source in _GOLD_SOURCES:
            gold_records.append(record)
        else:
            silver_records.append(record)

    # -- Negative examples --------------------------------------------------
    neg_records: list[dict] = []
    for row in neg_rows:
        sentence = str(row.get("sentence") or "").strip()
        if not sentence:
            continue
        phi = detect_phi(sentence)
        if phi:
            continue
        neg_records.append({"text": sentence, "spans": []})

    if dry_run:
        logger.info(
            "[DRY RUN] Would write gold=%d silver=%d neg=%d",
            len(gold_records),
            len(silver_records),
            len(neg_records),
        )
        return

    # -- Write output files -------------------------------------------------
    gold_path = output_dir / "ner_training_gold.jsonl"
    silver_path = output_dir / "ner_training_silver.jsonl"
    report_path = output_dir / "ner_stratification_report.txt"
    manifest_path = output_dir / "ner_export_manifest.json"

    _write_jsonl(gold_path, gold_records)
    _write_jsonl(silver_path, silver_records)

    # -- Post-export verification -------------------------------------------
    for path in (gold_path, silver_path):
        violations = _post_export_scan(path)
        if violations:
            logger.error(
                "Post-export scan found ID patterns in %s:\n%s",
                path,
                "\n".join(violations[:5]),
            )
            gold_path.unlink(missing_ok=True)
            silver_path.unlink(missing_ok=True)
            sys.exit(1)

    report = _build_stratification_report(
        [
            r
            for g in grouped.values()
            if g["source"] in _GOLD_SOURCES
            for r in g["spans"]
        ],
        [
            r
            for g in grouped.values()
            if g["source"] not in _GOLD_SOURCES
            for r in g["spans"]
        ],
        len(neg_records),
    )
    report_path.write_text(report, encoding="utf-8")

    manifest = {
        "export_id": str(uuid.uuid4()),
        "exported_at": datetime.now(tz=timezone.utc).isoformat(),
        "gold_count": len(gold_records),
        "silver_count": len(silver_records),
        "negative_count": len(neg_records),
        "safety_critical_blocked": safety_blocked,
        "training_ready": len(gold_records) >= 5000 and not safety_blocked,
        "files": {
            "gold": str(gold_path),
            "silver": str(silver_path),
            "report": str(report_path),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    logger.info(
        "Export complete: gold=%d silver=%d neg=%d safety_blocked=%s",
        len(gold_records),
        len(silver_records),
        len(neg_records),
        safety_blocked,
    )
    logger.info("Output: %s", output_dir.resolve())


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    logger.info("Wrote %d records to %s", len(records), path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export NER training data")
    parser.add_argument(
        "--output-dir",
        default=str(_DEFAULT_OUTPUT),
        metavar="DIR",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview counts without writing files",
    )
    args = parser.parse_args()
    export(Path(args.output_dir), dry_run=args.dry_run)


if __name__ == "__main__":
    main()
