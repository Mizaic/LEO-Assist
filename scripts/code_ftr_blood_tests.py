#!/usr/bin/env python3
"""Deterministic coder for all uncoded blood result encounters.

Finds ANY encounter containing EMIS-format lab entries (``Description (ReadCode)
value unit [range]``) that has no existing SNOMED coding. Resolves each lab item
via the Terminology API and writes ``(Encounter)-[:DOCUMENTS]->(Concept)`` +
``(Patient)-[:HAS_<tag>]->(Concept)`` links to Neo4j.

Usage:
    # Dry run -- prints a summary and writes a JSON/CSV report, no Neo4j writes:
    .venv/bin/python scripts/code_ftr_blood_tests.py

    # Apply writes:
    .venv/bin/python scripts/code_ftr_blood_tests.py --apply

    # Limit encounters (useful for testing):
    .venv/bin/python scripts/code_ftr_blood_tests.py --apply --limit 100

    # Restrict to a single patient:
    .venv/bin/python scripts/code_ftr_blood_tests.py --patient 9990000001 --apply
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_REPO_ROOT / "secrets" / ".env.config", override=True)
load_dotenv(_REPO_ROOT / "secrets" / ".env", override=False)
load_dotenv(_REPO_ROOT / "secrets" / ".env.secrets", override=False)

from libs.cypher.documents_queries import upsert_encounter_documents_link  # noqa: E402
from libs.neo4j_client.client import PatientGraphClient  # noqa: E402
from libs.terminology.client import ResolvedTerm, TerminologyClient  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("code_ftr_blood_tests")

DEFAULT_REPORT_DIR = _REPO_ROOT / "artifacts" / "ftr_blood_test_coding"

MODEL_NAME = "code_ftr_blood_tests"
MODEL_VERSION = "2026-04-30"
SOURCE = "deterministic_lab_coder_v1"

# ---------------------------------------------------------------------------
# Encounter query: uncoded labs in the FTR/2WW clinical window
# ---------------------------------------------------------------------------

_MATCH_QUERY = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE e.text IS NOT NULL
  AND NOT (e)-[:DOCUMENTS]->()
{patient_filter}
RETURN
  toString(p.id)  AS patient_id,
  toString(e.id)  AS encounter_id,
  e.date          AS date,
  e.text          AS text
ORDER BY patient_id, encounter_id
SKIP $skip LIMIT $batch_size
"""

_COUNT_QUERY = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE e.text IS NOT NULL
  AND NOT (e)-[:DOCUMENTS]->()
{patient_filter}
RETURN count(e) AS total
"""

# ---------------------------------------------------------------------------
# EMIS lab-entry parsing
#
# EMIS writes structured lab results as:
#   Description (ReadCode) numeric unit [low - high]
#
# Examples:
#   Haemoglobin A1c level - IFCC standardised (XaPbt) 36 mmol/mol [20 - 41]
#   Serum albumin level (XE2eA) 46 g/L [35 - 50]
#   Liver function tests (X77WP)
#   Serum cholesterol level (44P..) 6.8 mmol/L [0 - 5]
#   eGFR using creatinine (XaK8y) 78 mL/min/1.73m^2 [>=60]
#
# Read codes are alphanumeric + dots, 3-9 chars.
# ---------------------------------------------------------------------------

_LAB_LINE_RE = re.compile(
    r"(?m)^"
    r"(?P<description>[A-Z][^\n()]{3,120}?)\s*"
    r"\((?P<read_code>[A-Za-z0-9][A-Za-z0-9.]{2,8})\)"
    r"(?P<rest>[^\n]*)",
)

_VALUE_UNIT_RE = re.compile(
    r"^\s+"
    r"(?P<value>-?\d[\d.,]*(?:\s*[xX]10\^?\d+/[Ll])?)"
    r"(?:\s+(?P<unit>[^\s\[()]{1,30}(?:[/\s][^\s\[()]{1,20})?))?"
    r"(?:\s+\[(?P<range>[^\]]{1,60})\])?"
)

# Tokens in parentheses that are clearly NOT EMIS Read codes.
_NON_READ_CODE_RE = re.compile(
    r"^\s*(?:"
    r"\d{4}[-/]\d{2}[-/]\d{2}"     # ISO dates
    r"|\d{1,2}[ap]m"               # times
    r"|[A-Z]{2,}[a-z]{0,2}\s+\d"   # e.g. "BP 120"
    r"|[A-Z][a-z]+"                # single CamelCase word (likely a name)
    r")\s*$",
    re.IGNORECASE,
)

# Descriptions that are obviously NOT lab tests (admin / narrative text).
_NOISE_DESCRIPTION_RE = re.compile(
    r"(?i)^(?:"
    r"none|comment|note|advice|checking|assisting|contact|trigger|template"
    r"|admin|administrative|letter|referral|appointment|clinic"
    r"|telephone|visit|review|follow.?up|consultation"
    r")",
)


@dataclass
class LabEntry:
    """A single parsed lab item from encounter text."""

    description: str
    read_code: str
    surface_form: str          # description + (ReadCode) sent to terminology
    numeric_value: float | None
    unit: str | None
    reference_range: str | None
    evidence_line: str         # the original matched line


@dataclass
class Proposal:
    patient_id: str
    encounter_id: str
    date: str
    entry: LabEntry
    # populated after resolution
    concept_id: str | None = None
    snomed_term: str | None = None
    semantic_tag: str | None = None
    score: float = 0.0
    had_exact_match: bool = False
    status: str = "pending"
    write_eligible: bool = False
    already_linked: bool = field(default=False)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write DOCUMENTS + HAS_<tag> links to Neo4j (default: dry run).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Cap the number of encounters processed (0 = no cap).",
    )
    parser.add_argument(
        "--patient",
        type=str,
        default="",
        help="Restrict to a single patient ID.",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
        help="Directory for JSON + CSV reports.",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


_BATCH_SIZE = 2_000


def _build_query(patient_id: str) -> str:
    if patient_id:
        patient_filter = f"AND toString(p.id) = '{patient_id}'"
    else:
        patient_filter = ""
    return _MATCH_QUERY.format(patient_filter=patient_filter)


def _build_count_query(patient_id: str) -> str:
    if patient_id:
        patient_filter = f"AND toString(p.id) = '{patient_id}'"
    else:
        patient_filter = ""
    return _COUNT_QUERY.format(patient_filter=patient_filter)


def _count_rows(patient_id: str) -> int:
    client = PatientGraphClient()
    try:
        rows = client.run(_build_count_query(patient_id))
        return int(rows[0]["total"]) if rows else 0
    finally:
        client.close()


def _load_batch(patient_id: str, skip: int, limit: int) -> list[dict[str, Any]]:
    """Load one page of uncoded encounters."""
    client = PatientGraphClient()
    try:
        return client.run(
            _build_query(patient_id),
            skip=skip,
            batch_size=min(limit, _BATCH_SIZE) if limit > 0 else _BATCH_SIZE,
        )
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _parse_numeric(rest: str) -> tuple[float | None, str | None, str | None]:
    """Extract optional numeric value, unit, and reference range from the
    trailing part of a lab line (everything after the Read code)."""
    m = _VALUE_UNIT_RE.match(rest)
    if not m:
        return None, None, None
    raw_val = m.group("value")
    try:
        numeric_value: float | None = float(raw_val.replace(",", ""))
    except (TypeError, ValueError):
        numeric_value = None
    raw_unit = (m.group("unit") or "").strip() or None
    raw_range = (m.group("range") or "").strip() or None
    return numeric_value, raw_unit, raw_range


def _parse_lab_entries(text: str) -> list[LabEntry]:
    """Extract all EMIS-format lab entries from encounter text."""
    entries: list[LabEntry] = []
    seen_surfaces: set[str] = set()
    for m in _LAB_LINE_RE.finditer(text):
        description = m.group("description").strip()
        read_code = m.group("read_code").strip()
        rest = m.group("rest") or ""

        # Filter out parenthesised tokens that are clearly not Read codes
        if _NON_READ_CODE_RE.match(read_code):
            continue

        # Skip descriptions that are obviously admin / narrative, not lab tests
        if len(description) < 6 or _NOISE_DESCRIPTION_RE.match(description):
            continue

        # Build the surface form the terminology API is trained on
        surface_form = f"{description} ({read_code})"

        # Deduplicate within a single encounter (same test repeated)
        if surface_form in seen_surfaces:
            continue
        seen_surfaces.add(surface_form)

        numeric_value, unit, reference_range = _parse_numeric(rest)
        entries.append(
            LabEntry(
                description=description,
                read_code=read_code,
                surface_form=surface_form,
                numeric_value=numeric_value,
                unit=unit,
                reference_range=reference_range,
                evidence_line=m.group(0).strip(),
            )
        )
    return entries


def _build_proposals(rows: list[dict[str, Any]]) -> list[Proposal]:
    proposals: list[Proposal] = []
    for row in rows:
        text = str(row.get("text") or "")
        for entry in _parse_lab_entries(text):
            proposals.append(
                Proposal(
                    patient_id=str(row.get("patient_id") or ""),
                    encounter_id=str(row.get("encounter_id") or ""),
                    date=str(row.get("date") or ""),
                    entry=entry,
                )
            )
    logger.info(
        "Parsed %d lab proposals from %d encounters", len(proposals), len(rows)
    )
    return proposals


# ---------------------------------------------------------------------------
# Terminology resolution
# ---------------------------------------------------------------------------


def _resolve(proposals: list[Proposal]) -> dict[str, list[ResolvedTerm]]:
    """Batch-resolve all unique surface forms via the Terminology API."""
    surfaces = list(dict.fromkeys(p.entry.surface_form for p in proposals))
    logger.info("Resolving %d unique surface forms via Terminology API ...", len(surfaces))
    results = TerminologyClient(timeout=60, max_retries=2).resolve(
        surfaces,
        # Most EMIS lab entries are observable entities; allow the API to
        # match procedure / finding / disorder too so we don't miss tumour
        # markers coded as clinical findings.
        expected_tags=None,
    )
    logger.info(
        "Resolution complete: %d/%d surfaces resolved",
        sum(1 for v in results.values() if v),
        len(surfaces),
    )
    return results


# ---------------------------------------------------------------------------
# Finalisation
# ---------------------------------------------------------------------------

# Semantic tags we will NOT write -- these are anatomy/taxonomy nodes that
# should never be coded as encounter-level findings.
_BLOCKED_TAGS: frozenset[str] = frozenset(
    {
        "body structure",
        "bodystructure",
        "organism",
        "physical object",
        "record artifact",
        "namespace concept",
        "special concept",
    }
)


def _tag_ok(semantic_tag: str | None) -> bool:
    raw = (semantic_tag or "").strip().lower()
    return raw not in _BLOCKED_TAGS


def _finalise(proposal: Proposal, candidates: list[ResolvedTerm]) -> None:
    top = candidates[0] if candidates else None
    if top is None or not top.concept_id:
        proposal.status = "unresolved"
        return
    if not _tag_ok(top.semantic_tag):
        proposal.status = "blocked_tag"
        return
    proposal.concept_id = top.concept_id
    proposal.snomed_term = top.term
    proposal.semantic_tag = top.semantic_tag
    proposal.score = float(top.score or 0.0)
    proposal.had_exact_match = bool(top.had_exact_match)
    proposal.status = "safe"
    proposal.write_eligible = True


# ---------------------------------------------------------------------------
# Neo4j writes
# ---------------------------------------------------------------------------


def _apply(proposals: list[Proposal]) -> int:
    eligible = [p for p in proposals if p.write_eligible and not p.already_linked]
    if not eligible:
        logger.info("No proposals are write-eligible; skipping Neo4j writes")
        return 0

    client = PatientGraphClient()
    applied = 0
    try:
        with client.session() as session:
            for proposal in eligible:
                try:
                    upsert_encounter_documents_link(
                        session,
                        proposal.patient_id,
                        proposal.encounter_id,
                        str(proposal.concept_id),
                        str(proposal.semantic_tag or "other"),
                        str(proposal.snomed_term or proposal.entry.description),
                        proposal.entry.surface_form,
                        read_code=proposal.entry.read_code,
                        evidence_sentence=proposal.entry.evidence_line,
                        assertion="present",
                        source=SOURCE,
                        model_name=MODEL_NAME,
                        model_version=MODEL_VERSION,
                        confidence=proposal.score,
                        numeric_value=proposal.entry.numeric_value,
                        unit=proposal.entry.unit,
                        reference_range=proposal.entry.reference_range,
                    )
                    applied += 1
                except Exception:
                    logger.warning(
                        "Write failed: patient=%s encounter=%s concept=%s",
                        proposal.patient_id,
                        proposal.encounter_id,
                        proposal.concept_id,
                        exc_info=True,
                    )
    finally:
        client.close()

    logger.info("Applied %d DOCUMENTS links to Neo4j", applied)
    return applied


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _to_row(proposal: Proposal) -> dict[str, Any]:
    e = proposal.entry
    return {
        "status": proposal.status,
        "write_eligible": proposal.write_eligible,
        "already_linked": proposal.already_linked,
        "patient_id": proposal.patient_id,
        "encounter_id": proposal.encounter_id,
        "date": proposal.date,
        "read_code": e.read_code,
        "surface_form": e.surface_form,
        "description": e.description,
        "numeric_value": e.numeric_value,
        "unit": e.unit,
        "reference_range": e.reference_range,
        "evidence_line": e.evidence_line,
        "concept_id": proposal.concept_id,
        "snomed_term": proposal.snomed_term,
        "semantic_tag": proposal.semantic_tag,
        "score": proposal.score,
        "had_exact_match": proposal.had_exact_match,
    }


def _summary(proposals: list[Proposal], applied: int, encounters: int) -> dict[str, int]:
    return {
        "encounters_scanned": encounters,
        "proposals": len(proposals),
        "safe": sum(1 for p in proposals if p.status == "safe"),
        "already_linked": sum(1 for p in proposals if p.already_linked),
        "unresolved": sum(1 for p in proposals if p.status == "unresolved"),
        "blocked_tag": sum(1 for p in proposals if p.status == "blocked_tag"),
        "applied": applied,
    }


def _write_report(
    report_dir: Path,
    proposals: list[Proposal],
    summary: dict[str, int],
    apply: bool,
) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    mode = "apply" if apply else "dry_run"
    rows = [_to_row(p) for p in proposals]
    json_path = report_dir / f"ftr_blood_test_coding_{mode}_{stamp}.json"
    csv_path = report_dir / f"ftr_blood_test_coding_{mode}_{stamp}.csv"
    json_path.write_text(
        json.dumps({"apply": apply, "summary": summary, "items": rows}, indent=2),
        encoding="utf-8",
    )
    if rows:
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    logger.info("Report written to %s", json_path)
    return json_path


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    args = _parse_args()

    total = _count_rows(args.patient)
    if total == 0:
        logger.warning("No uncoded encounters found -- nothing to do")
        return 0

    cap = args.limit if args.limit > 0 else total
    logger.info(
        "Found %d uncoded encounters (processing up to %d in batches of %d)",
        total, cap, _BATCH_SIZE,
    )

    all_proposals: list[Proposal] = []
    total_encounters_scanned = 0
    total_applied = 0
    skip = 0

    while skip < cap:
        batch_rows = _load_batch(args.patient, skip, cap - skip)
        if not batch_rows:
            break

        batch_proposals = _build_proposals(batch_rows)
        total_encounters_scanned += len(batch_rows)
        skip += len(batch_rows)

        if not batch_proposals:
            logger.info(
                "Batch %d-%d: no EMIS lab entries found, skipping",
                skip - len(batch_rows), skip,
            )
            continue

        resolved = _resolve(batch_proposals)
        for proposal in batch_proposals:
            candidates = resolved.get(proposal.entry.surface_form, [])
            _finalise(proposal, candidates)

        if args.apply:
            batch_applied = _apply(batch_proposals)
            total_applied += batch_applied

        all_proposals.extend(batch_proposals)
        safe = sum(1 for p in batch_proposals if p.status == "safe")
        logger.info(
            "Progress: %d/%d encounters | batch proposals=%d safe=%d | "
            "total applied=%d",
            total_encounters_scanned, cap,
            len(batch_proposals), safe, total_applied,
        )

    summary = _summary(all_proposals, total_applied, total_encounters_scanned)
    report_path = _write_report(args.report_dir, all_proposals, summary, args.apply)

    print(json.dumps({"report": str(report_path), **summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
