#!/usr/bin/env python3
"""Deterministic coder for non-blood-test investigation encounters in the FTR window.

Handles two text patterns that the blood-test coder cannot parse (no EMIS Read code
on the procedure line itself):

  1. Radiology / report-summary headers
       ``XR Chest: Report Summary``
       ``US Abdomen and pelvis: Report Summary``
       ``CT Thorax & abdomen: Report Summary``
       ``MRI Pelvis: Report Summary``

  2. Pathology Request blocks
       ``Pathology Request (Complete): FIT (Requested), US Pelvis (Requested)``
       ``Pathology Request (Request Sent): CT Thorax & abdomen (Requested)``

Both patterns occur in uncoded encounters and are resolved via the Terminology API.

Usage:
    # Dry run (no writes):
    .venv/bin/python scripts/code_ftr_investigations.py

    # Apply writes:
    .venv/bin/python scripts/code_ftr_investigations.py --apply

    # Limit encounters:
    .venv/bin/python scripts/code_ftr_investigations.py --apply --limit 200

    # Single patient:
    .venv/bin/python scripts/code_ftr_investigations.py --patient 9990000001 --apply
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import logging
import re
import sys
from dataclasses import dataclass
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
logger = logging.getLogger("code_ftr_investigations")

DEFAULT_REPORT_DIR = _REPO_ROOT / "artifacts" / "ftr_investigation_coding"
MODEL_NAME = "code_ftr_investigations"
MODEL_VERSION = "2026-04-30"
SOURCE = "deterministic_investigation_coder_v1"
_BATCH_SIZE = 2_000

# ---------------------------------------------------------------------------
# Cypher queries
# ---------------------------------------------------------------------------

_MATCH_QUERY = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE e.text IS NOT NULL
  AND NOT (e)-[:DOCUMENTS]->()
  AND (
       toLower(e.text) CONTAINS 'report summary'
    OR toLower(e.text) CONTAINS 'pathology request'
    OR toLower(e.text) CONTAINS 'gastroscop'
    OR toLower(e.text) CONTAINS 'colonoscop'
    OR toLower(e.text) CONTAINS 'sigmoidoscop'
    OR toLower(e.text) CONTAINS 'cystoscop'
    OR toLower(e.text) CONTAINS 'endoscop'
    OR toLower(e.text) CONTAINS 'uas urine'
    OR toLower(e.text) CONTAINS 'urine microscop'
  )
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
  AND (
       toLower(e.text) CONTAINS 'report summary'
    OR toLower(e.text) CONTAINS 'pathology request'
    OR toLower(e.text) CONTAINS 'gastroscop'
    OR toLower(e.text) CONTAINS 'colonoscop'
    OR toLower(e.text) CONTAINS 'sigmoidoscop'
    OR toLower(e.text) CONTAINS 'cystoscop'
    OR toLower(e.text) CONTAINS 'endoscop'
    OR toLower(e.text) CONTAINS 'uas urine'
    OR toLower(e.text) CONTAINS 'urine microscop'
  )
{patient_filter}
RETURN count(e) AS total
"""

# ---------------------------------------------------------------------------
# Text patterns
# ---------------------------------------------------------------------------

# Pattern 1: radiology / report-summary headers
# Matches: "XR Chest : Report Summary" / "US Abdomen and pelvis: Report Summary"
# Captures the modality+anatomy before ": Report Summary"
_REPORT_HEADER_RE = re.compile(
    r"(?m)^"
    r"(?P<procedure>"
    r"(?:XR|USS?|CT|MRI|PET|NM|DEXA?|ECHO|OGD|Endoscopy|Colonoscopy|"
    r"Flexible\s+sigmoidoscopy|Rigid\s+sigmoidoscopy|Cystoscopy|"
    r"Laparoscopy|Bronchoscopy|Colposcopy|Hysteroscopy)"
    r"[^:\n]{0,100}?"
    r")\s*:\s*Report\s+Summar",
    re.IGNORECASE,
)

# Pattern 2a: Pathology Request block header
# Matches: "Pathology Request (Complete):\n..." or "Pathology Request (Request Sent):"
_PATHO_BLOCK_RE = re.compile(
    r"Pathology\s+Request\s+\([^)]+\)\s*:?\s*\n?(?P<block>[^\n]{0,500})",
    re.IGNORECASE,
)

# Pattern 2b: individual "(Requested)" items within a pathology block
# Matches: "CT Thorax & abdomen (Requested)" or just "FIT (Requested)"
_REQUESTED_ITEM_RE = re.compile(
    r"(?P<test>[A-Z][A-Za-z0-9&/\s\-\.]{1,80}?)"
    r"(?:\s*\([^)]{1,60}\))?"   # optional sub-qualifier e.g. (Complete)
    r"\s*\(Requested\)",
    re.IGNORECASE,
)

# Pattern 3: short gastroscopy/endoscopy report filing lines with no Read code
# e.g. "Gastroscopy Report to [PERSON]"
_ENDO_REPORT_RE = re.compile(
    r"(?m)^(?P<procedure>"
    r"(?:Gastroscopy|OGD|Colonoscopy|Flexible\s+Sigmoidoscopy|Cystoscopy|"
    r"Colposcopy|Hysteroscopy|Bronchoscopy|Laparoscopy|Sigmoidoscopy)"
    r")\s+(?:Report|Letter|Result)\b",
    re.IGNORECASE,
)

# Pattern 4: UAS Urine Microscopy short result
_URINE_MICRO_RE = re.compile(
    r"(?m)^(?P<procedure>UAS\s+Urine\s+Microscopy|Urine\s+Microscopy)\s*:",
    re.IGNORECASE,
)

# Noise: skip procedures that are obviously too short or are free-text noise
_NOISE_PROCEDURE_RE = re.compile(
    r"^(?:report|letter|result|summary|none|n/a|see\s+above|as\s+per)\s*$",
    re.IGNORECASE,
)

# Canonical surface-form aliases for common imaging abbreviations so the
# terminology API gets a proper English description to match against.
_IMAGING_ALIASES: dict[str, str] = {
    "xr chest": "Chest X-ray",
    "xr spine": "X-ray spine",
    "xr abdomen": "Abdominal X-ray",
    "xr pelvis": "Pelvic X-ray",
    "xr hand": "X-ray hand",
    "xr foot": "X-ray foot",
    "xr knee": "X-ray knee",
    "xr hip": "X-ray hip",
    "xr shoulder": "X-ray shoulder",
    "xr wrist": "X-ray wrist",
    "xr ankle": "X-ray ankle",
    "uss pelvis": "Ultrasound pelvis",
    "uss abdomen": "Ultrasound abdomen",
    "us pelvis": "Ultrasound pelvis",
    "us abdomen": "Ultrasound abdomen",
    "us abdomen and pelvis": "Ultrasound abdomen and pelvis",
    "us pelvis ta and transvaginal": "Transvaginal ultrasound pelvis",
    "us thyroid": "Ultrasound thyroid",
    "us neck": "Ultrasound neck",
    "us liver": "Ultrasound liver",
    "us breast": "Ultrasound breast",
    "us scrotum": "Ultrasound scrotum",
    "us testes": "Ultrasound testes",
    "uss breast": "Ultrasound breast",
    "ct thorax": "CT scan of thorax",
    "ct abdomen": "CT scan of abdomen",
    "ct pelvis": "CT scan of pelvis",
    "ct thorax & abdomen": "CT scan of thorax and abdomen",
    "ct thorax and abdomen": "CT scan of thorax and abdomen",
    "ct abdomen & pelvis": "CT scan of abdomen and pelvis",
    "ct abdomen and pelvis": "CT scan of abdomen and pelvis",
    "ct thorax abdomen and pelvis": "CT scan of thorax abdomen and pelvis",
    "ct thorax & abdomen & pelvis": "CT scan of thorax abdomen and pelvis",
    "ct tap": "CT scan of thorax abdomen and pelvis",
    "ct head": "CT scan of head",
    "ct brain": "CT scan of brain",
    "ct chest": "CT scan of thorax",
    "ct colonoscopy": "CT colonoscopy",
    "ct iu": "CT urogram",
    "mri pelvis": "MRI pelvis",
    "mri abdomen": "MRI abdomen",
    "mri spine": "MRI spine",
    "mri breast": "MRI breast",
    "mri brain": "MRI brain",
    "mri liver": "MRI liver",
    "mri prostate": "MRI prostate",
    "mri rectum": "MRI rectum",
    "uas urine microscopy": "Urine microscopy",
    "urine microscopy": "Urine microscopy",
    "ogd": "Upper gastrointestinal endoscopy",
    "fit": "Faecal immunochemical test",
    "fit test": "Faecal immunochemical test",
    "fobt": "Faecal occult blood test",
    "coeliac disease screen": "Coeliac disease antibody test",
}


def _normalise_procedure(raw: str) -> str:
    """Apply alias mapping and clean whitespace."""
    cleaned = " ".join(raw.strip().split())
    lower = cleaned.lower()
    return _IMAGING_ALIASES.get(lower, cleaned)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class InvEntry:
    procedure_raw: str       # as extracted from text
    surface_form: str        # normalised term sent to terminology
    evidence_line: str       # original matched line for provenance
    source_pattern: str      # which pattern matched: report_header / pathology_request / etc.


@dataclass
class Proposal:
    patient_id: str
    encounter_id: str
    date: str
    entry: InvEntry
    concept_id: str | None = None
    snomed_term: str | None = None
    semantic_tag: str | None = None
    score: float = 0.0
    had_exact_match: bool = False
    status: str = "pending"
    write_eligible: bool = False
    already_linked: bool = False


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--patient", type=str, default="")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Neo4j
# ---------------------------------------------------------------------------


def _build_query(patient_id: str) -> str:
    pf = f"AND toString(p.id) = '{patient_id}'" if patient_id else ""
    return _MATCH_QUERY.format(patient_filter=pf)


def _build_count_query(patient_id: str) -> str:
    pf = f"AND toString(p.id) = '{patient_id}'" if patient_id else ""
    return _COUNT_QUERY.format(patient_filter=pf)


def _count_rows(patient_id: str) -> int:
    client = PatientGraphClient()
    try:
        rows = client.run(_build_count_query(patient_id))
        return int(rows[0]["total"]) if rows else 0
    finally:
        client.close()


def _load_batch(patient_id: str, skip: int, limit: int) -> list[dict[str, Any]]:
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


def _parse_entries(text: str) -> list[InvEntry]:
    entries: list[InvEntry] = []
    seen: set[str] = set()

    def _add(raw: str, line: str, pattern: str) -> None:
        sf = _normalise_procedure(raw)
        key = sf.lower()
        if key in seen or len(sf) < 3 or _NOISE_PROCEDURE_RE.match(sf):
            return
        seen.add(key)
        entries.append(InvEntry(
            procedure_raw=raw.strip(),
            surface_form=sf,
            evidence_line=line.strip(),
            source_pattern=pattern,
        ))

    # Pattern 1: radiology report headers
    for m in _REPORT_HEADER_RE.finditer(text):
        _add(m.group("procedure"), m.group(0), "report_header")

    # Pattern 2: Pathology Request blocks
    for block_m in _PATHO_BLOCK_RE.finditer(text):
        block = block_m.group("block") or ""
        for item_m in _REQUESTED_ITEM_RE.finditer(block):
            test_name = item_m.group("test").strip()
            if len(test_name) >= 2:
                _add(test_name, block_m.group(0)[:120], "pathology_request")

    # Pattern 3: endoscopy filing lines
    for m in _ENDO_REPORT_RE.finditer(text):
        _add(m.group("procedure"), m.group(0), "endoscopy_report")

    # Pattern 4: urine microscopy
    for m in _URINE_MICRO_RE.finditer(text):
        _add(m.group("procedure"), m.group(0), "urine_microscopy")

    return entries


def _build_proposals(rows: list[dict[str, Any]]) -> list[Proposal]:
    proposals: list[Proposal] = []
    for row in rows:
        text = str(row.get("text") or "")
        for entry in _parse_entries(text):
            proposals.append(Proposal(
                patient_id=str(row.get("patient_id") or ""),
                encounter_id=str(row.get("encounter_id") or ""),
                date=str(row.get("date") or ""),
                entry=entry,
            ))
    return proposals


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def _resolve(proposals: list[Proposal]) -> dict[str, list[ResolvedTerm]]:
    surfaces = list(dict.fromkeys(p.entry.surface_form for p in proposals))
    logger.info("Resolving %d unique surface forms ...", len(surfaces))
    results = TerminologyClient(timeout=60, max_retries=2).resolve(surfaces)
    resolved_count = sum(1 for v in results.values() if v)
    logger.info("Resolution complete: %d/%d resolved", resolved_count, len(surfaces))
    return results


# ---------------------------------------------------------------------------
# Finalisation
# ---------------------------------------------------------------------------

_BLOCKED_TAGS: frozenset[str] = frozenset({
    "body structure", "bodystructure", "organism",
    "physical object", "record artifact",
    "namespace concept", "special concept",
})


def _finalise(proposal: Proposal, candidates: list[ResolvedTerm]) -> None:
    top = candidates[0] if candidates else None
    if top is None or not top.concept_id:
        proposal.status = "unresolved"
        return
    raw_tag = (top.semantic_tag or "").strip().lower()
    if raw_tag in _BLOCKED_TAGS:
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
# Writes
# ---------------------------------------------------------------------------


def _apply(proposals: list[Proposal]) -> int:
    eligible = [p for p in proposals if p.write_eligible and not p.already_linked]
    if not eligible:
        return 0
    client = PatientGraphClient()
    applied = 0
    try:
        with client.session() as session:
            for p in eligible:
                try:
                    upsert_encounter_documents_link(
                        session,
                        p.patient_id,
                        p.encounter_id,
                        str(p.concept_id),
                        str(p.semantic_tag or "other"),
                        str(p.snomed_term or p.entry.surface_form),
                        p.entry.surface_form,
                        read_code=None,
                        evidence_sentence=p.entry.evidence_line,
                        assertion="present",
                        source=SOURCE,
                        model_name=MODEL_NAME,
                        model_version=MODEL_VERSION,
                        confidence=p.score,
                    )
                    applied += 1
                except Exception:
                    logger.warning(
                        "Write failed patient=%s encounter=%s concept=%s",
                        p.patient_id, p.encounter_id, p.concept_id, exc_info=True,
                    )
    finally:
        client.close()
    logger.info("Applied %d DOCUMENTS links", applied)
    return applied


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _to_row(p: Proposal) -> dict[str, Any]:
    return {
        "status": p.status,
        "write_eligible": p.write_eligible,
        "patient_id": p.patient_id,
        "encounter_id": p.encounter_id,
        "date": p.date,
        "source_pattern": p.entry.source_pattern,
        "procedure_raw": p.entry.procedure_raw,
        "surface_form": p.entry.surface_form,
        "evidence_line": p.entry.evidence_line[:120],
        "concept_id": p.concept_id,
        "snomed_term": p.snomed_term,
        "semantic_tag": p.semantic_tag,
        "score": p.score,
        "had_exact_match": p.had_exact_match,
    }


def _summary(proposals: list[Proposal], applied: int, scanned: int) -> dict[str, int]:
    return {
        "encounters_scanned": scanned,
        "proposals": len(proposals),
        "safe": sum(1 for p in proposals if p.status == "safe"),
        "unresolved": sum(1 for p in proposals if p.status == "unresolved"),
        "blocked_tag": sum(1 for p in proposals if p.status == "blocked_tag"),
        "applied": applied,
    }


def _write_report(
    report_dir: Path, proposals: list[Proposal], summary: dict, apply: bool
) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    mode = "apply" if apply else "dry_run"
    rows = [_to_row(p) for p in proposals]
    json_path = report_dir / f"ftr_investigation_coding_{mode}_{stamp}.json"
    csv_path = report_dir / f"ftr_investigation_coding_{mode}_{stamp}.csv"
    json_path.write_text(
        json.dumps({"apply": apply, "summary": summary, "items": rows}, indent=2),
        encoding="utf-8",
    )
    if rows:
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    logger.info("Report written to %s", json_path)
    return json_path


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    args = _parse_args()

    total = _count_rows(args.patient)
    if total == 0:
        logger.warning("No matching encounters found -- nothing to do")
        return 0

    cap = args.limit if args.limit > 0 else total
    logger.info(
        "Found %d matching investigation encounters (cap=%d, batch=%d)",
        total, cap, _BATCH_SIZE,
    )

    all_proposals: list[Proposal] = []
    scanned = 0
    total_applied = 0
    skip = 0

    while skip < cap:
        rows = _load_batch(args.patient, skip, cap - skip)
        if not rows:
            break

        proposals = _build_proposals(rows)
        scanned += len(rows)
        skip += len(rows)

        if not proposals:
            logger.info("Batch %d: no investigation entries parsed, skipping", skip)
            continue

        resolved = _resolve(proposals)
        for p in proposals:
            _finalise(p, resolved.get(p.entry.surface_form, []))

        if args.apply:
            total_applied += _apply(proposals)

        all_proposals.extend(proposals)
        safe = sum(1 for p in proposals if p.status == "safe")
        logger.info(
            "Progress: %d/%d | proposals=%d safe=%d | total applied=%d",
            scanned, cap, len(proposals), safe, total_applied,
        )

    summary = _summary(all_proposals, total_applied, scanned)
    report_path = _write_report(args.report_dir, all_proposals, summary, args.apply)
    print(json.dumps({"report": str(report_path), **summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
