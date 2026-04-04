"""Encounter coding audit -- check SNOMED coding accuracy and surface-form coverage.

Reads encounters within a configurable date window, verifies coding via Sonnet
4.6, and checks that coded evidence phrases resolve correctly via the terminology
API.

Usage
-----
    python scripts/investigations/audit_encounter_coding.py --preflight-only
    python scripts/investigations/audit_encounter_coding.py --yes
    python scripts/investigations/audit_encounter_coding.py --patient 4587069337
    python scripts/investigations/audit_encounter_coding.py --cancer-only
    python scripts/investigations/audit_encounter_coding.py --resume
    python scripts/investigations/audit_encounter_coding.py --yes --since-days 14
    python scripts/investigations/audit_encounter_coding.py --yes --since 2026-01-01

Outputs (in --output dir, default scripts/investigations/encounter_audit/):
    encounter_audit.db           -- SQLite checkpoint (crash-safe)
    results/<PATIENT_ID>.json    -- per-patient findings
    summary.csv                  -- one row per encounter
    surface_form_gaps.json       -- gaps ready for /terminology/writeback
    severity_summary.txt         -- counts by severity
    top_issues.txt               -- top 50 most-common missing concepts
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import random
import sys
import threading
import uuid
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from dotenv import load_dotenv  # noqa: E402
from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402
from libs.terminology.client import TerminologyClient  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

from libs.llm_client.factory import create_llm  # noqa: E402
from libs.neo4j_client.client import PatientGraphClient  # noqa: E402
from scripts.investigations._audit_db import (  # noqa: E402
    STATUS_DONE,
    CheckpointDB,
)
from scripts.investigations._audit_llm import call_llm_with_retry  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("audit_coding")

TERMINOLOGY_URL = "http://localhost:8001/terminology"

# ---------------------------------------------------------------------------
# Cypher queries
# ---------------------------------------------------------------------------

_Q_VOLUME = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE e.date >= $since_date AND e.date <= $until_date
  AND e.text IS NOT NULL AND trim(e.text) <> ''
OPTIONAL MATCH (e)-[r:DOCUMENTS]->(s)
WITH p, e,
     count(r) AS doc_count,
     count(CASE WHEN r.evidence IS NOT NULL
                 AND trim(toString(r.evidence)) <> '' THEN 1 END) AS with_evidence
RETURN count(DISTINCT p) AS patient_count,
       count(e)           AS encounter_count,
       sum(doc_count)     AS total_documents,
       sum(with_evidence) AS docs_with_evidence,
       avg(size(e.text))  AS avg_text_len,
       percentileDisc(size(e.text), 0.50) AS p50_text_len,
       percentileDisc(size(e.text), 0.95) AS p95_text_len,
       max(size(e.text))  AS max_text_len
"""

_Q_ENCOUNTER_IDS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE e.date >= $since_date AND e.date <= $until_date
  AND e.text IS NOT NULL AND trim(e.text) <> ''
  {extra_where}
RETURN toString(p.id)  AS patient_id,
       toString(e.id)  AS encounter_id,
       toString(e.date) AS date,
       size(e.text)    AS text_len
ORDER BY p.id, e.date
SKIP $skip LIMIT $page_size
"""

_Q_ENCOUNTER_DETAIL = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id AND toString(e.id) = $encounter_id
OPTIONAL MATCH (e)-[r:DOCUMENTS]->(s)
RETURN e.text          AS text,
       toString(e.date) AS date,
       s.conceptId     AS concept_id,
       s.name          AS term,
       s.semanticTag   AS semantic_tag,
       r.evidence      AS evidence,
       r.value         AS value,
       r.unit          AS unit,
       r.context       AS context,
       r.confidence    AS confidence,
       r.domain        AS domain
ORDER BY r.confidence DESC
"""

_PAGE_SIZE = 500


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_encounter(
    client: PatientGraphClient, patient_id: str, encounter_id: str
) -> tuple[str, list[dict[str, Any]]]:
    """Return (text, coded_list) for one encounter."""
    rows = client.run(
        _Q_ENCOUNTER_DETAIL, patient_id=patient_id, encounter_id=encounter_id
    )
    if not rows:
        return "", []
    text = str(rows[0].get("text") or "")
    coded = [r for r in rows if r.get("concept_id") is not None]
    return text, coded


def _discover_page(
    client: PatientGraphClient,
    skip: int,
    page_size: int,
    extra_where: str,
    since_date: str,
    until_date: str,
) -> list[dict[str, Any]]:
    q = _Q_ENCOUNTER_IDS.format(extra_where=extra_where)
    return client.run(
        q, skip=skip, page_size=page_size,
        since_date=since_date, until_date=until_date,
    )


# ---------------------------------------------------------------------------
# Phase 0 -- Pre-flight
# ---------------------------------------------------------------------------


def _print_volumes(
    client: PatientGraphClient,
    since_date: str,
    until_date: str,
) -> dict[str, Any]:
    rows = client.run(_Q_VOLUME, since_date=since_date, until_date=until_date)
    v = rows[0] if rows else {}
    logger.info("--- Volume counts (2024-2026) ---")
    for k, val in v.items():
        logger.info("  %-22s %s", k, val)
    enc = int(v.get("encounter_count") or 0)
    docs = int(v.get("total_documents") or 0)
    with_ev = int(v.get("docs_with_evidence") or 0)
    ev_pct = round(100 * with_ev / docs, 1) if docs else 0
    logger.info("  evidence_coverage     %s%%", ev_pct)
    sonnet_1w = round(enc * 3 / 3600, 1)
    sonnet_5w = round(enc * 3 / 3600 / 5, 1)
    logger.info("--- Rough estimates ---")
    logger.info("  LLM calls needed:     %d (one per encounter)", enc)
    logger.info("  Estimated time (1 worker):  ~%.1f hours", sonnet_1w)
    logger.info("  Estimated time (5 workers): ~%.1f hours  (--workers 5)", sonnet_5w)
    logger.info("  Tip: --workers 5 is safe for Bedrock; --workers 10 if credits allow")
    return v


def _run_sample(
    client: PatientGraphClient,
    llm: Any,
    n: int = 10,
    extra_where: str = "",
    since_date: str = "2024-01-01",
    until_date: str = "2027-01-01",
) -> None:
    """Process n random encounters and print results for human review."""
    rows = _discover_page(client, 0, 2000, extra_where, since_date, until_date)
    sample = random.sample(rows, min(n, len(rows)))
    logger.info("--- Running %d-encounter pre-flight sample ---", len(sample))
    for i, row in enumerate(sample, 1):
        text, coded = _load_encounter(client, row["patient_id"], row["encounter_id"])
        if not text:
            continue
        result = call_llm_with_retry(llm, text, coded)
        assessment = result.get("encounter_assessment", "?")
        missing_n = len(result.get("missing", []))
        wrong_n = len(result.get("wrong_assertion", []))
        over_n = len(result.get("overcoded", []))
        conf = result.get("confidence", "?")
        logger.info(
            "  [%d/%d] %s  patient=%s  assessment=%s  missing=%d"
            "  wrong_assertion=%d  overcoded=%d  confidence=%s",
            i, len(sample), row["date"], row["patient_id"],
            assessment, missing_n, wrong_n, over_n, conf,
        )
        for m in result.get("missing", []):
            logger.info(
                "    MISSING [%s] %s -- %s",
                m.get("severity", "?"), m.get("term", "?"), m.get("reason", ""),
            )
        for w in result.get("wrong_assertion", []):
            logger.info(
                "    ASSERTION [%s] %s: %s -> %s",
                w.get("severity", "?"), w.get("name", "?"),
                w.get("current_assertion"), w.get("suggested_assertion"),
            )
        if result.get("notes"):
            logger.info("    NOTE: %s", result["notes"])


def run_preflight(
    client: PatientGraphClient,
    tier: str = "big",
    cancer_only: bool = False,
    sample_n: int = 10,
    since_date: str = "2024-01-01",
    until_date: str = "2027-01-01",
) -> bool:
    """Print volume stats and run sample. Returns True if user confirms."""
    extra_where = (
        "AND EXISTS { (p)-[:HAS_EPISODE_OF_CARE]->(:EpisodeOfCare) }"
        if cancer_only else ""
    )
    _print_volumes(client, since_date, until_date)
    llm = create_llm(provider="aws", tier=tier)
    _run_sample(
        client, llm, n=sample_n, extra_where=extra_where,
        since_date=since_date, until_date=until_date,
    )
    logger.info("--- Sample complete ---")
    try:
        answer = input("\nProceed with full audit? [y/N] ").strip().lower()
        return answer in {"y", "yes"}
    except EOFError:
        # Non-interactive terminal (e.g. backgrounded shell) -- require --yes flag
        logger.info("Non-interactive terminal: use --yes to proceed without prompt.")
        return False


# ---------------------------------------------------------------------------
# Phase 1 -- Discovery
# ---------------------------------------------------------------------------


def run_discovery(
    client: PatientGraphClient,
    db: CheckpointDB,
    cancer_only: bool = False,
    patient_id: str | None = None,
    since_date: str = "2024-01-01",
    until_date: str = "2027-01-01",
) -> int:
    """Enumerate all encounters and insert into SQLite. Returns total inserted."""
    extra_where_parts = []
    if cancer_only:
        extra_where_parts.append(
            "AND EXISTS { (p)-[:HAS_EPISODE_OF_CARE]->(:EpisodeOfCare) }"
        )
    if patient_id:
        extra_where_parts.append(f"AND toString(p.id) = '{patient_id}'")
    extra_where = "\n  ".join(extra_where_parts)

    total_inserted = 0
    skip = 0
    while True:
        page = _discover_page(
            client, skip, _PAGE_SIZE, extra_where, since_date, until_date
        )
        if not page:
            break
        inserted = db.insert_encounters(page)
        total_inserted += inserted
        skip += _PAGE_SIZE
        logger.info(
            "Discovery: fetched %d records (skip=%d, new=%d, total=%d)",
            len(page), skip - _PAGE_SIZE, inserted, total_inserted,
        )
        if len(page) < _PAGE_SIZE:
            break
    logger.info("Discovery complete: %d encounters queued.", total_inserted)
    return total_inserted


# ---------------------------------------------------------------------------
# Phase 2 -- Coding audit (LLM)
# ---------------------------------------------------------------------------


def _audit_one(
    client: PatientGraphClient,
    llm: Any,
    db: CheckpointDB,
    row: dict[str, Any],
    cost_acc: "CostAccumulator | None" = None,
) -> bool:
    """Process one encounter: LLM call + checkpoint.

    Returns False if the cost cap was hit (caller should stop the loop).
    """
    pid, eid = row["patient_id"], row["encounter_id"]
    try:
        text, coded = _load_encounter(client, pid, eid)
        if not text.strip():
            db.mark_done(
                eid, {"encounter_assessment": "skipped", "reason": "empty text"}
            )
            return True
        from scripts.investigations._audit_llm import build_user_message
        user_msg = build_user_message(text, coded)
        result = call_llm_with_retry(llm, text, coded)

        if cost_acc is not None:
            from scripts.investigations._audit_llm import SYSTEM_PROMPT
            input_chars = len(SYSTEM_PROMPT) + len(user_msg)
            output_chars = len(json.dumps(result))
            if cost_acc.add(input_chars, output_chars):
                logger.warning(
                    "audit.cost_cap_hit: cumulative_usd=%.2f cap=%.2f -- pausing",
                    cost_acc.total_usd, cost_acc.cap_usd,
                )
                db.mark_done(
                    eid, {"encounter_assessment": "skipped", "reason": "cost_cap"}
                )
                return False

        _norm = {
            "not clean": "has_issues",
            "not_clean": "has_issues",
            "has issues": "has_issues",
            "has_issue": "has_issues",
            "issues_found": "has_issues",
            "errors_found": "has_issues",
            "incomplete": "needs_review",
            "requires_review": "needs_review",
        }
        result["encounter_assessment"] = _norm.get(
            str(result.get("encounter_assessment", "")).lower(),
            result.get("encounter_assessment", ""),
        )
        result["_meta"] = {
            "patient_id": pid,
            "encounter_id": eid,
            "date": row.get("date"),
            "coded_count": len(coded),
        }
        db.mark_done(eid, result)
        logger.info(
            "Coded %s (%s) -- %s  missing=%d  wrong=%d  overcoded=%d",
            eid[:8], row.get("date"), result.get("encounter_assessment"),
            len(result.get("missing", [])),
            len(result.get("wrong_assertion", [])),
            len(result.get("overcoded", [])),
        )
    except Exception as exc:
        logger.error("Error processing %s: %s", eid, exc)
        db.mark_error(eid, str(exc))
    return True


def _audit_worker(
    neo_client: PatientGraphClient,
    tier: str,
    db: CheckpointDB,
    rows: list[dict[str, Any]],
    worker_id: int,
    cost_acc: "CostAccumulator | None" = None,
) -> None:
    """Thread worker: each thread owns its own LLM client instance."""
    llm = create_llm(provider="aws", tier=tier)
    for i, row in enumerate(rows, 1):
        ok = _audit_one(neo_client, llm, db, row, cost_acc)
        if not ok:
            logger.info("Worker-%d: stopped at cost cap after %d rows", worker_id, i)
            return
        if i % 20 == 0:
            logger.info("Worker-%d: %d/%d done", worker_id, i, len(rows))


def run_coding_audit(
    client: PatientGraphClient,
    tier: str,
    db: CheckpointDB,
    workers: int = 1,
    cost_cap_usd: float = 100.0,
    neo_client_for_alerts: "PatientGraphClient | None" = None,
) -> float:
    """Phase 2: iterate pending encounters, optionally with concurrent workers.

    Returns cumulative estimated cost in USD.
    """
    pending = list(db.pending_encounters())
    logger.info(
        "Phase 2: %d encounters to process with %d worker(s) cost_cap=$%.0f.",
        len(pending), workers, cost_cap_usd,
    )
    cost_acc = CostAccumulator(cap_usd=cost_cap_usd)

    if workers <= 1:
        llm = create_llm(provider="aws", tier=tier)
        for i, row in enumerate(pending, 1):
            ok = _audit_one(client, llm, db, row, cost_acc)
            if not ok:
                logger.warning(
                    "Cost cap reached at encounter %d/%d ($%.2f).",
                    i, len(pending), cost_acc.total_usd,
                )
                if neo_client_for_alerts:
                    _create_cost_cap_alert(
                        neo_client_for_alerts, cost_acc.total_usd, cost_cap_usd
                    )
                break
            if i % 50 == 0:
                counts = db.counts()
                logger.info(
                    "Progress: %d/%d done  errors=%d  cost=~$%.2f",
                    counts["done"], counts["total"], counts["error"],
                    cost_acc.total_usd,
                )
        return cost_acc.total_usd

    chunks = [pending[i::workers] for i in range(workers)]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _audit_worker, client, tier, db, chunk, wid, cost_acc
            ): wid
            for wid, chunk in enumerate(chunks, 1)
            if chunk
        }
        for fut in as_completed(futures):
            wid = futures[fut]
            exc = fut.exception()
            if exc:
                logger.error("Worker-%d raised: %s", wid, exc)
            else:
                logger.info("Worker-%d finished.", wid)

    if cost_acc.is_capped and neo_client_for_alerts:
        _create_cost_cap_alert(
            neo_client_for_alerts, cost_acc.total_usd, cost_cap_usd
        )

    counts = db.counts()
    logger.info(
        "Phase 2 complete: done=%d  error=%d  cost=~$%.2f",
        counts["done"], counts["error"], cost_acc.total_usd,
    )
    return cost_acc.total_usd


# ---------------------------------------------------------------------------
# Phase 3 -- Surface-form coverage
# ---------------------------------------------------------------------------


def _check_surface_forms(
    encounter_id: str,
    coded: list[dict[str, Any]],
    db: CheckpointDB,
) -> None:
    """Check each evidence phrase resolves to the expected SNOMED concept.

    Uses TerminologyClient so input normalisation (lab-value stripping,
    EMIS code stripping) is applied automatically, and results are
    re-keyed to the original evidence phrases.
    """
    candidates = [
        c for c in coded
        if c.get("evidence") and c.get("concept_id") is not None
    ]
    if not candidates:
        return

    unique_terms = list({c["evidence"] for c in candidates})
    tags = {
        c["evidence"]: c.get("semantic_tag", "disorder")
        for c in candidates
    }
    try:
        results = TerminologyClient().resolve(unique_terms, expected_tags=tags)
    except Exception as exc:
        logger.warning("Resolve batch failed: %s", exc)
        return

    for c in candidates:
        ev = c["evidence"]
        expected_id = str(c["concept_id"])
        hits = results.get(ev, [])
        found_pos = next(
            (i for i, h in enumerate(hits) if str(h.concept_id) == expected_id),
            None,
        )
        top = hits[0] if hits else None
        gap_type = _gap_type(found_pos)
        if gap_type is None:
            continue
        db.upsert_surface_gap({
            "encounter_id": encounter_id,
            "evidence": ev,
            "expected_concept_id": expected_id,
            "expected_name": c.get("term"),
            "semantic_tag": c.get("semantic_tag"),
            "resolver_top_result": top.term if top else None,
            "resolver_top_score": top.score if top else None,
            "gap_type": gap_type,
        })


def _gap_type(position: int | None) -> str | None:
    """Return gap type string or None if resolved well."""
    if position is None:
        return "not_found"
    if position >= 4:
        return "wrong_rank"
    return None


def run_surface_form_audit(
    client: PatientGraphClient,
    db: CheckpointDB,
) -> None:
    """Phase 3: check surface-form resolver coverage for all coded DOCUMENTS."""
    logger.info("Phase 3: checking surface-form coverage ...")
    done_rows = list(db.all_results())
    checked = 0
    for row in done_rows:
        if row["status"] != STATUS_DONE:
            continue
        pid = row["patient_id"]
        eid = row["encounter_id"]
        _, coded = _load_encounter(client, pid, eid)
        _check_surface_forms(eid, coded, db)
        checked += 1
        if checked % 200 == 0:
            logger.info("Surface-form: checked %d encounters", checked)
    gaps = db.counts()["surface_gaps"]
    logger.info("Phase 3 complete: %d surface-form gaps found.", gaps)


# ---------------------------------------------------------------------------
# Phase 4 -- Report generation
# ---------------------------------------------------------------------------


def _collect_results(db: CheckpointDB) -> tuple[dict, list]:
    """Return (per_patient dict, summary_rows list)."""
    per_patient: dict[str, list] = defaultdict(list)
    summary_rows: list[dict] = []

    for row in db.all_results():
        result = row["result"] or {}
        pid = row["patient_id"]
        per_patient[pid].append(row)

        def _sev_count(key: str, sev: str) -> int:
            return sum(1 for x in result.get(key, []) if x.get("severity") == sev)

        summary_rows.append({
            "encounter_id": row["encounter_id"],
            "patient_id": pid,
            "date": row["date"],
            "status": row["status"],
            "assessment": result.get("encounter_assessment", ""),
            "coded_count": result.get("_meta", {}).get("coded_count", ""),
            "missing_critical": _sev_count("missing", "critical"),
            "missing_high": _sev_count("missing", "high"),
            "missing_medium": _sev_count("missing", "medium"),
            "missing_low": _sev_count("missing", "low"),
            "wrong_assertion": len(result.get("wrong_assertion", [])),
            "overcoded": len(result.get("overcoded", [])),
            "confidence": result.get("confidence", ""),
        })
    return per_patient, summary_rows


def _write_per_patient(per_patient: dict, out_dir: Path) -> None:
    results_dir = out_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    for pid, rows in per_patient.items():
        path = results_dir / f"{pid}.json"
        path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    logger.info("Per-patient files written to %s", results_dir)


def _write_summary_csv(summary_rows: list[dict], out_dir: Path) -> None:
    if not summary_rows:
        return
    path = out_dir / "summary.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(summary_rows)
    logger.info("Summary CSV: %s", path)


def _write_severity_summary(summary_rows: list[dict], out_dir: Path) -> None:
    totals: Counter = Counter()
    for r in summary_rows:
        totals["missing_critical"] += int(r.get("missing_critical") or 0)
        totals["missing_high"] += int(r.get("missing_high") or 0)
        totals["missing_medium"] += int(r.get("missing_medium") or 0)
        totals["missing_low"] += int(r.get("missing_low") or 0)
        totals["wrong_assertion"] += int(r.get("wrong_assertion") or 0)
        totals["overcoded"] += int(r.get("overcoded") or 0)
        if str(r.get("assessment")) == "has_issues":
            totals["encounters_with_issues"] += 1
        if str(r.get("assessment")) == "clean":
            totals["encounters_clean"] += 1
    lines = ["SEVERITY SUMMARY", "=" * 40]
    for k, v in sorted(totals.items()):
        lines.append(f"  {k:<30} {v}")
    (out_dir / "severity_summary.txt").write_text("\n".join(lines), encoding="utf-8")


def _write_top_issues(db: CheckpointDB, out_dir: Path) -> None:
    term_counter: Counter = Counter()
    for row in db.all_results():
        result = row.get("result") or {}
        for m in result.get("missing", []):
            key = m.get("snomed_search") or m.get("term") or "unknown"
            term_counter[key] += 1
    lines = ["TOP 50 MISSING CONCEPTS", "=" * 40]
    for term, count in term_counter.most_common(50):
        lines.append(f"  {count:>5}  {term}")
    (out_dir / "top_issues.txt").write_text("\n".join(lines), encoding="utf-8")


def generate_reports(db: CheckpointDB, out_dir: Path) -> None:
    """Phase 4: write all report files from SQLite data."""
    logger.info("Phase 4: generating reports ...")
    out_dir.mkdir(parents=True, exist_ok=True)

    per_patient, summary_rows = _collect_results(db)
    _write_per_patient(per_patient, out_dir)
    _write_summary_csv(summary_rows, out_dir)
    _write_severity_summary(summary_rows, out_dir)
    _write_top_issues(db, out_dir)

    gaps = db.all_surface_gaps()
    gap_path = out_dir / "surface_form_gaps.json"
    gap_path.write_text(json.dumps(gaps, indent=2), encoding="utf-8")

    counts = db.counts()
    logger.info(
        "Reports complete. Encounters: total=%d done=%d error=%d "
        "surface_gaps=%d",
        counts["total"], counts["done"], counts["error"], counts["surface_gaps"],
    )
    logger.info("Output directory: %s", out_dir.resolve())


# ---------------------------------------------------------------------------
# Run ID generation and Neo4j writer (Phase 4b)
# ---------------------------------------------------------------------------

_Q_CHECK_AUDIT_RUN = """
MATCH (a:AuditRun {run_id: $run_id})
RETURN a.status AS status
"""

_Q_CREATE_AUDIT_RUN = """
MERGE (a:AuditRun {run_id: $run_id})
ON CREATE SET
    a.triggered_by          = $triggered_by,
    a.since_date            = $since_date,
    a.until_date            = $until_date,
    a.status                = 'running',
    a.encounter_count       = $encounter_count,
    a.pct_clean             = $pct_clean,
    a.critical_count        = $critical_count,
    a.auditor_model_version = $auditor_model_version,
    a.started_at            = datetime(),
    a.completed_at          = datetime(),
    a.cost_usd              = $cost_usd
ON MATCH SET
    a.status                = 'running',
    a.encounter_count       = $encounter_count,
    a.pct_clean             = $pct_clean,
    a.critical_count        = $critical_count,
    a.auditor_model_version = $auditor_model_version,
    a.completed_at          = datetime(),
    a.cost_usd              = $cost_usd
SET a.status = 'complete'
RETURN a.run_id AS run_id
"""

_Q_CREATE_DRIFT_METRIC = """
MATCH (a:AuditRun {run_id: $run_id})
MERGE (d:DriftMetric {metric_id: $metric_id})
ON CREATE SET
    d.run_id                = $run_id,
    d.metric_type           = 'audit',
    d.week_start            = $week_start,
    d.pct_clean             = $pct_clean,
    d.pct_clean_by_domain   = $pct_clean_by_domain,
    d.critical_count        = $critical_count,
    d.high_count            = $high_count,
    d.overcoded_count       = $overcoded_count,
    d.parse_error_count     = $parse_error_count,
    d.top_missing_terms     = $top_missing_terms,
    d.top_overcoded_terms   = $top_overcoded_terms,
    d.auditor_model_version = $auditor_model_version,
    d.model_version_changed = $model_version_changed,
    d.recorded_at           = datetime()
ON MATCH SET
    d.pct_clean             = $pct_clean,
    d.critical_count        = $critical_count,
    d.recorded_at           = datetime()
MERGE (a)-[:HAS_METRIC]->(d)
RETURN d.metric_id AS metric_id
"""


# ---------------------------------------------------------------------------
# Cost tracking (Phase 2)
# ---------------------------------------------------------------------------

_COST_PER_INPUT_TOKEN = 0.000003   # Sonnet input ($/token)
_COST_PER_OUTPUT_TOKEN = 0.000015  # Sonnet output ($/token)
_CHARS_PER_TOKEN = 4               # rough estimate for English clinical text

_Q_CREATE_COST_CAP_ALERT = """
MERGE (a:SafetyNetAlert {alert_id: $alert_id})
ON CREATE SET
    a.alert_type   = 'audit_cost_cap',
    a.severity     = 'high',
    a.description  = $description,
    a.created_at   = datetime()
RETURN a.alert_id AS alert_id
"""


class CostAccumulator:
    """Thread-safe USD cost accumulator for the Phase 2 audit loop."""

    def __init__(self, cap_usd: float) -> None:
        self.cap_usd = cap_usd
        self._lock = threading.Lock()
        self._total_usd: float = 0.0
        self._capped: bool = False

    def add(self, input_chars: int, output_chars: int) -> bool:
        """Add estimated cost and return True if the cap was just exceeded."""
        input_tokens = input_chars / _CHARS_PER_TOKEN
        output_tokens = output_chars / _CHARS_PER_TOKEN
        cost = (
            input_tokens * _COST_PER_INPUT_TOKEN
            + output_tokens * _COST_PER_OUTPUT_TOKEN
        )
        with self._lock:
            self._total_usd += cost
            if not self._capped and self._total_usd >= self.cap_usd:
                self._capped = True
                return True
        return False

    @property
    def total_usd(self) -> float:
        with self._lock:
            return self._total_usd

    @property
    def is_capped(self) -> bool:
        with self._lock:
            return self._capped


def _create_cost_cap_alert(neo_client: PatientGraphClient, cost_usd: float, cap_usd: float) -> None:
    alert_id = str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"audit_cost_cap:{date.today().isoformat()}",
    ))
    description = (
        f"Audit run paused: cumulative cost ${cost_usd:.2f} reached "
        f"the ${cap_usd:.0f} cap. Remaining encounters were skipped."
    )
    try:
        neo_client.run(
            _Q_CREATE_COST_CAP_ALERT,
            alert_id=alert_id,
            description=description,
        )
        logger.warning(
            "audit.cost_cap_hit: cost_usd=%.2f cap_usd=%.2f alert_id=%s",
            cost_usd, cap_usd, alert_id,
        )
    except Exception:
        logger.error("Failed to create cost_cap alert", exc_info=True)


def _run_escalation_check(neo_client: PatientGraphClient) -> None:
    """Run alert escalation check after each audit run (Phase 4 tail)."""
    try:
        from libs.audit.escalation import run_escalation_check
        run_escalation_check(neo_client)
    except Exception:
        logger.error("Escalation check failed", exc_info=True)


def make_run_id(triggered_by: str, since_date: str) -> str:
    """Return a deterministic run_id for scheduled runs, UUID for manual."""
    if triggered_by == "schedule":
        d = date.fromisoformat(since_date)
        iso_year, iso_week, _ = d.isocalendar()
        return f"audit-{iso_year}-W{iso_week:02d}"
    return f"audit-manual-{uuid.uuid4().hex[:8]}"


def _resolve_run_id(neo_client: PatientGraphClient, run_id: str) -> str:
    """Guard against overwriting a completed AuditRun (QA-002).

    If the run_id already exists with status='complete', generate a suffixed
    retry ID. 'running' or 'failed' nodes can be overwritten on retry.
    """
    rows = neo_client.run(_Q_CHECK_AUDIT_RUN, run_id=run_id)
    if not rows:
        return run_id
    status = rows[0].get("status", "")
    if status != "complete":
        return run_id
    # Find the next available retry suffix
    for n in range(1, 100):
        candidate = f"{run_id}-retry-{n}"
        check = neo_client.run(_Q_CHECK_AUDIT_RUN, run_id=candidate)
        if not check or check[0].get("status") != "complete":
            logger.warning(
                "AuditRun %r is complete -- using retry ID %r", run_id, candidate
            )
            return candidate
    return f"{run_id}-retry-{uuid.uuid4().hex[:4]}"


def _write_audit_results_to_neo4j(
    neo_client: PatientGraphClient,
    run_id: str,
    since_date: str,
    until_date: str,
    summary_rows: list[dict[str, Any]],
    db: "CheckpointDB",
    triggered_by: str = "schedule",
    auditor_model_version: str = "",
    cost_usd: float = 0.0,
) -> None:
    """Write AuditRun and DriftMetric nodes to Neo4j."""
    total = len(summary_rows)
    clean_count = sum(
        1 for r in summary_rows if str(r.get("assessment")) == "clean"
    )
    pct_clean = round(100.0 * clean_count / total, 2) if total else 0.0
    critical_count = sum(
        int(r.get("missing_critical") or 0) for r in summary_rows
    )
    high_count = sum(
        int(r.get("missing_high") or 0) for r in summary_rows
    )
    overcoded_count = sum(
        int(r.get("overcoded") or 0) for r in summary_rows
    )
    parse_error_count = sum(
        1 for r in summary_rows if str(r.get("status")) == "error"
    )

    domain_clean: dict[str, list] = defaultdict(list)
    term_counter: Counter = Counter()
    overcoded_counter: Counter = Counter()
    for row in db.all_results():
        result = row.get("result") or {}
        domain = result.get("_meta", {}).get("domain") or "unknown"
        assessment = result.get("encounter_assessment", "")
        domain_clean[domain].append(assessment == "clean")
        for m in result.get("missing", []):
            key = m.get("snomed_search") or m.get("term") or "unknown"
            term_counter[key] += 1
        for oc in result.get("overcoded", []):
            key = oc.get("term") or oc.get("concept_id") or "unknown"
            overcoded_counter[key] += 1

    pct_clean_by_domain = {
        d: round(100.0 * sum(vals) / len(vals), 1) if vals else 0.0
        for d, vals in domain_clean.items()
    }
    top_missing = [t for t, _ in term_counter.most_common(20)]
    top_overcoded = [t for t, _ in overcoded_counter.most_common(20)]

    d = date.fromisoformat(since_date)
    iso_year, iso_week, _ = d.isocalendar()
    week_start = str(d - timedelta(days=d.weekday()))
    metric_id = f"{run_id}-{week_start}"

    try:
        neo_client.run(
            _Q_CREATE_AUDIT_RUN,
            run_id=run_id,
            triggered_by=triggered_by,
            since_date=since_date,
            until_date=until_date,
            encounter_count=total,
            pct_clean=pct_clean,
            critical_count=critical_count,
            auditor_model_version=auditor_model_version,
            cost_usd=cost_usd,
        )
        neo_client.run(
            _Q_CREATE_DRIFT_METRIC,
            run_id=run_id,
            metric_id=metric_id,
            week_start=week_start,
            pct_clean=pct_clean,
            pct_clean_by_domain=json.dumps(pct_clean_by_domain),
            critical_count=critical_count,
            high_count=high_count,
            overcoded_count=overcoded_count,
            parse_error_count=parse_error_count,
            top_missing_terms=json.dumps(top_missing),
            top_overcoded_terms=json.dumps(top_overcoded),
            auditor_model_version=auditor_model_version,
            model_version_changed=False,
        )
        logger.info(
            "Neo4j write complete: run_id=%s metric_id=%s pct_clean=%.1f%%",
            run_id, metric_id, pct_clean,
        )
    except Exception:
        logger.error("Failed to write audit results to Neo4j", exc_info=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Encounter coding audit")
    p.add_argument("--preflight-only", action="store_true")
    p.add_argument("--yes", action="store_true", help="Skip approval gate")
    p.add_argument("--tier", choices=["small", "big"], default="big")
    p.add_argument("--cancer-only", action="store_true")
    p.add_argument("--patient", metavar="ID", help="Audit a single patient")
    p.add_argument(
        "--workers", type=int, default=1, metavar="N",
        help="Concurrent LLM workers (default 1; try 5-10 for Bedrock)",
    )
    p.add_argument("--skip-resolve", action="store_true")
    p.add_argument("--skip-discovery", action="store_true",
                   help="Skip Phase 1 (resume from existing DB)")
    p.add_argument("--report-only", action="store_true",
                   help="Skip Phases 0-3, regenerate reports only")
    p.add_argument(
        "--since-days", type=int, default=7, metavar="N",
        help="Audit encounters from the last N days (default 7). "
             "Overridden by --since.",
    )
    p.add_argument(
        "--since", metavar="YYYY-MM-DD",
        help="Explicit start date for audit window (overrides --since-days).",
    )
    p.add_argument(
        "--triggered-by",
        choices=["schedule", "manual", "validation"],
        default="manual",
        help="How this run was triggered (used in AuditRun node).",
    )
    p.add_argument("--skip-neo4j-write", action="store_true",
                   help="Do not write AuditRun/DriftMetric to Neo4j.")
    p.add_argument(
        "--cost-cap",
        type=float,
        default=100.0,
        metavar="USD",
        help="Maximum estimated cost in USD before pausing the run (default $100).",
    )
    p.add_argument(
        "--output",
        default=str(ROOT / "scripts" / "investigations" / "encounter_audit"),
        metavar="DIR",
    )
    return p.parse_args()


def _compute_date_window(args: argparse.Namespace) -> tuple[str, str]:
    """Return (since_date, until_date) as ISO strings."""
    until_date = date.today().isoformat()
    if args.since:
        since_date = args.since
    else:
        since_date = (date.today() - timedelta(days=args.since_days)).isoformat()
    return since_date, until_date


def main() -> None:
    args = _parse_args()
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = out_dir / "encounter_audit.db"

    since_date, until_date = _compute_date_window(args)
    logger.info("Audit window: %s -> %s", since_date, until_date)

    neo_client = PatientGraphClient()
    db = CheckpointDB(db_path)

    try:
        if args.report_only:
            generate_reports(db, out_dir)
            return

        triggered_by = args.triggered_by
        run_id = make_run_id(triggered_by, since_date)
        run_id = _resolve_run_id(neo_client, run_id)
        logger.info("Run ID: %s (triggered_by=%s)", run_id, triggered_by)

        # Phase 0 -- pre-flight
        if not args.yes:
            confirmed = run_preflight(
                neo_client,
                tier=args.tier,
                cancer_only=args.cancer_only,
                since_date=since_date,
                until_date=until_date,
            )
            if not confirmed:
                logger.info("Audit cancelled by user.")
                return
        else:
            _print_volumes(neo_client, since_date, until_date)

        if args.preflight_only:
            return

        # Phase 1 -- discovery
        if not args.skip_discovery:
            run_discovery(
                neo_client, db,
                cancer_only=args.cancer_only,
                patient_id=args.patient,
                since_date=since_date,
                until_date=until_date,
            )

        # Phase 2 -- LLM coding audit
        run_coding_audit(
            neo_client,
            args.tier,
            db,
            workers=args.workers,
            cost_cap_usd=args.cost_cap,
            neo_client_for_alerts=neo_client,
        )

        # Phase 3 -- surface-form check
        if not args.skip_resolve:
            run_surface_form_audit(neo_client, db)

        # Phase 4 -- reports + optional Neo4j write
        generate_reports(db, out_dir)

        if not args.skip_neo4j_write:
            _, summary_rows = _collect_results(db)
            _write_audit_results_to_neo4j(
                neo_client=neo_client,
                run_id=run_id,
                since_date=since_date,
                until_date=until_date,
                summary_rows=summary_rows,
                db=db,
                triggered_by=triggered_by,
            )
            _run_escalation_check(neo_client)

    finally:
        neo_client.close()
        db.close()


if __name__ == "__main__":
    main()
