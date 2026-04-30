#!/usr/bin/env python3
"""Export the cancer cohort encounter window for LLM annotation.

For each patient flagged as having a cancer EpisodeOfCare in the latest
NCDA detector run, pulls every Encounter inside `dx_date +/- 90 days`
and writes a per-patient JSONL to disk. The JSONL is the input to
``annotate_cancer_cohort.py`` (which calls Claude with the prompt at
prompts/cancer_cohort_annotation_v1.md).

Read-only: this script never writes to the patient graph. It only
reads from Neo4j and writes JSON to the local artifact directory.

Cohort source: artifacts/ncda_full_run/full_ncda_dry_run_*.json
                (latest by mtime unless --ncda-artifact provided)
Output dir:    data/cancer_cohort/p{patient_id}.jsonl
                + data/cancer_cohort/cohort_manifest.json

Each output line is one Encounter:
{
  "patient_id":              "4187508279",
  "encounter_id":            "<uuid>",
  "encounter_date":          "2025-03-10",
  "encounter_flags":         "Face to face\\nLinked to Appointment",
  "text":                    "<full encounter text>",
  "sentences": [
    {"sentence_id": 1, "text": "...", "start": 0,  "end": 35},
    {"sentence_id": 2, "text": "...", "start": 36, "end": 90}
  ],
  "existing_coded_concepts": [
    {"name": "Malignant neoplasm of breast suspected (situation)",
     "labels": ["Situation"]}
  ],
  "patient_context": {
    "gender":            "F",
    "year_of_birth":     1958,
    "age_at_diagnosis":  67,
    "cancer_site":       "breast",
    "cohort":            "1a",
    "diagnosis_date":    "2025-04-14",
    "diagnosis_route":   "gp_surgery_fast_track"
  }
}

Atlas trace: design-input pending; this script supports the cancer
cohort gold-data refresh discussed in agent transcript
1eed5e51-4068-4dc3-8d11-d40dd62767e8.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("export_cancer_cohort")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_WINDOW_DAYS = 90
DEFAULT_OUTPUT_DIR = ROOT / "data" / "cancer_cohort"
DEFAULT_NCDA_GLOB = ROOT / "artifacts" / "ncda_full_run"


# ---------------------------------------------------------------------------
# Cypher queries (read-only)
# ---------------------------------------------------------------------------

PATIENT_DEMOGRAPHICS_QUERY = """
MATCH (p:Patient)
WHERE coalesce(toString(p.id), toString(p.patient_id)) = $pid
RETURN
    coalesce(p.gender, '')   AS gender,
    toString(p.birthDate)     AS birth_date
LIMIT 1
"""

ENCOUNTERS_IN_WINDOW_QUERY = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE coalesce(toString(p.id), toString(p.patient_id)) = $pid
  AND date(e.date) >= date($d_from)
  AND date(e.date) <= date($d_to)
  AND e.text IS NOT NULL
  AND trim(e.text) <> ''
OPTIONAL MATCH (e)-[:DOCUMENTS]->(c)
WITH e, collect(DISTINCT {
    name:      coalesce(c.name, c.term, ''),
    labels:    labels(c),
    concept_id: coalesce(toString(c.conceptId), '')
}) AS coded
RETURN
    e.id                AS encounter_id,
    toString(e.date)     AS encounter_date,
    coalesce(e.flags, '') AS encounter_flags,
    e.text               AS text,
    coded                AS existing_coded_concepts
ORDER BY date(e.date) ASC, e.id ASC
"""


# ---------------------------------------------------------------------------
# Sentence splitting (lightweight; the production splitter has more deps)
# ---------------------------------------------------------------------------

# A pragmatic regex splitter that respects newlines and standard sentence
# terminators. We do NOT pull in PyRuSH / medspacy here to keep this
# script's dependency surface small. The annotator script can re-split
# with the production splitter if needed.
_SENT_SPLIT_RE = re.compile(
    r"""
    (?<=[\.\?!])\s+(?=[A-Z\d\(\[\-])     # period/?/! followed by capital/digit
    |
    (?<=:)\s*\n+                          # colon then newline
    |
    \n{2,}                                # paragraph break
    |
    (?<=\S)\s*\n(?=\s*-\s)                # newline before bullet
    """,
    re.VERBOSE,
)


def split_sentences(text: str) -> list[dict[str, Any]]:
    """Return a list of sentence dicts with id, text, start, end."""
    if not text or not text.strip():
        return []
    out: list[dict[str, Any]] = []
    cursor = 0
    pieces = _SENT_SPLIT_RE.split(text)
    for raw in pieces:
        if raw is None:
            continue
        s = raw.strip("\n\r")
        if not s.strip():
            cursor += len(raw) if raw else 0
            continue
        # Locate the substring forward from cursor to recover offsets
        loc = text.find(s, cursor)
        if loc < 0:
            loc = cursor
        out.append({
            "sentence_id": len(out) + 1,
            "text": s,
            "start": loc,
            "end": loc + len(s),
        })
        cursor = loc + len(s)
    return out


# ---------------------------------------------------------------------------
# NCDA cohort loader
# ---------------------------------------------------------------------------


def find_latest_ncda_artifact(directory: Path) -> Path:
    """Return path of newest full_ncda_dry_run_<ts>.json (NOT a summary)."""
    candidates = [
        p for p in directory.glob("full_ncda_dry_run_*.json")
        if "summary" not in p.name and "raw_pathways" not in p.name
    ]
    if not candidates:
        raise FileNotFoundError(
            f"No NCDA artifact found in {directory}. "
            "Run scripts/ncda/run_full_cancer_episode_detection.py first."
        )
    return max(candidates, key=lambda p: p.stat().st_mtime)


def load_cohort(ncda_artifact: Path) -> list[dict[str, Any]]:
    """Return one record per (patient, episode) with anchor dates + site."""
    with ncda_artifact.open() as f:
        data = json.load(f)
    rows: list[dict[str, Any]] = []
    for ep in data.get("episode_candidates", []):
        dx = (ep.get("dx") or {}).get("encounter_date")
        ftr = (ep.get("ftr") or {}).get("encounter_date")
        seen = (ep.get("seen") or {}).get("encounter_date")
        tx = (ep.get("treatment") or {}).get("encounter_date")
        anchor = dx or ftr or seen or tx
        if not anchor:
            logger.warning(
                "skipping episode without any milestone date for patient %s",
                ep.get("patient_id"),
            )
            continue
        rows.append({
            "patient_id":      str(ep["patient_id"]),
            "cohort":          ep.get("cohort"),
            "site":            ep.get("site") or "unknown",
            "diagnosis_route": ep.get("diagnosis_route") or "",
            "diagnosis_date":  dx or anchor,
            "anchor_date":     anchor,
            "ftr_date":        ftr,
            "seen_date":       seen,
            "treatment_date":  tx,
        })
    return rows


def collapse_to_one_per_patient(
    cohort: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Pick the earliest dx-anchored episode per patient.

    A patient may legitimately have several cancer episodes. For the
    annotation refresh we want a single +/- 90d window, so we anchor on
    the EARLIEST diagnosis_date the detector produced.
    """
    by_patient: dict[str, dict[str, Any]] = {}
    for ep in cohort:
        pid = ep["patient_id"]
        if pid not in by_patient:
            by_patient[pid] = ep
            continue
        if (ep["anchor_date"] or "") < (by_patient[pid]["anchor_date"] or ""):
            by_patient[pid] = ep
    return sorted(
        by_patient.values(),
        key=lambda e: (e["anchor_date"] or "", e["patient_id"]),
    )


# ---------------------------------------------------------------------------
# Neo4j client (read-only sessions)
# ---------------------------------------------------------------------------


def make_driver():
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD") or os.getenv("NEO4J_PASS") or ""
    if not password:
        raise RuntimeError(
            "NEO4J_PASSWORD not set in env. Check secrets/.env.secrets"
        )
    return GraphDatabase.driver(uri, auth=(user, password))


def fetch_demographics(driver, patient_id: str) -> dict[str, Any]:
    with driver.session() as session:
        record = session.run(PATIENT_DEMOGRAPHICS_QUERY, pid=patient_id).single()
    if not record:
        return {"gender": "", "birth_date": None, "year_of_birth": None}
    raw = dict(record)
    yob = None
    if raw.get("birth_date"):
        try:
            yob = int(str(raw["birth_date"])[:4])
        except (ValueError, TypeError):
            pass
    return {
        "gender":         raw.get("gender") or "",
        "birth_date":     raw.get("birth_date"),
        "year_of_birth":  yob,
    }


def fetch_encounters_in_window(
    driver,
    patient_id: str,
    d_from: str,
    d_to: str,
) -> list[dict[str, Any]]:
    with driver.session() as session:
        result = session.run(
            ENCOUNTERS_IN_WINDOW_QUERY,
            pid=patient_id,
            d_from=d_from,
            d_to=d_to,
        )
        return [dict(r) for r in result]


# ---------------------------------------------------------------------------
# Per-patient export
# ---------------------------------------------------------------------------


def age_at(anchor_date: str, year_of_birth: int | None) -> int | None:
    if year_of_birth is None or not anchor_date:
        return None
    try:
        anchor_year = int(str(anchor_date)[:4])
        return max(0, anchor_year - year_of_birth)
    except (ValueError, TypeError):
        return None


def export_patient(
    driver,
    cohort_row: dict[str, Any],
    window_days: int,
    output_dir: Path,
) -> dict[str, Any]:
    pid = cohort_row["patient_id"]
    anchor = cohort_row["anchor_date"]
    anchor_dt = datetime.strptime(anchor[:10], "%Y-%m-%d")
    d_from = (anchor_dt - timedelta(days=window_days)).strftime("%Y-%m-%d")
    d_to   = (anchor_dt + timedelta(days=window_days)).strftime("%Y-%m-%d")

    demo = fetch_demographics(driver, pid)
    encounters = fetch_encounters_in_window(driver, pid, d_from, d_to)

    patient_context = {
        "gender":            demo.get("gender"),
        "year_of_birth":     demo.get("year_of_birth"),
        "age_at_diagnosis":  age_at(anchor, demo.get("year_of_birth")),
        "cancer_site":       cohort_row.get("site"),
        "cohort":            cohort_row.get("cohort"),
        "diagnosis_date":    cohort_row.get("diagnosis_date"),
        "diagnosis_route":   cohort_row.get("diagnosis_route"),
        "window_from":       d_from,
        "window_to":         d_to,
    }

    out_path = output_dir / f"p{pid}.jsonl"
    n_chars = 0
    with out_path.open("w") as f:
        for enc in encounters:
            text = enc.get("text") or ""
            n_chars += len(text)
            sentences = split_sentences(text)
            line = {
                "patient_id":              pid,
                "encounter_id":            enc.get("encounter_id"),
                "encounter_date":          enc.get("encounter_date"),
                "encounter_flags":         enc.get("encounter_flags"),
                "text":                    text,
                "sentences":               sentences,
                "existing_coded_concepts": enc.get("existing_coded_concepts") or [],
                "patient_context":         patient_context,
            }
            f.write(json.dumps(line, ensure_ascii=True) + "\n")

    summary = {
        "patient_id":     pid,
        "anchor_date":    anchor,
        "window_from":    d_from,
        "window_to":      d_to,
        "n_encounters":   len(encounters),
        "n_chars":        n_chars,
        "n_sentences":    sum(len(split_sentences(e.get("text") or "")) for e in encounters),
        "output_file":    str(out_path.relative_to(ROOT)),
        "patient_context": patient_context,
    }
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument(
        "--ncda-artifact",
        type=Path,
        help=(
            "Path to a specific full_ncda_dry_run_<ts>.json. "
            "Defaults to newest in artifacts/ncda_full_run/."
        ),
    )
    p.add_argument(
        "--window-days",
        type=int,
        default=DEFAULT_WINDOW_DAYS,
        help=f"Days either side of diagnosis (default {DEFAULT_WINDOW_DAYS}).",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Where to write per-patient JSONL (default {DEFAULT_OUTPUT_DIR.relative_to(ROOT)}/).",
    )
    p.add_argument(
        "--patient",
        type=str,
        action="append",
        help="Limit to one or more patient IDs (repeatable).",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Cap number of patients exported (0 = all).",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    artifact = args.ncda_artifact or find_latest_ncda_artifact(DEFAULT_NCDA_GLOB)
    logger.info("loading NCDA cohort from %s", artifact)
    cohort = collapse_to_one_per_patient(load_cohort(artifact))

    if args.patient:
        wanted = {str(p) for p in args.patient}
        cohort = [c for c in cohort if c["patient_id"] in wanted]
    if args.limit > 0:
        cohort = cohort[: args.limit]

    if not cohort:
        logger.error("no patients selected after filtering")
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(
        "exporting %d patient(s), window +/- %d days, output dir %s",
        len(cohort), args.window_days, args.output_dir.relative_to(ROOT),
    )

    driver = make_driver()
    manifest: list[dict[str, Any]] = []
    try:
        for i, row in enumerate(cohort, start=1):
            try:
                summary = export_patient(
                    driver, row, args.window_days, args.output_dir
                )
            except Exception as exc:
                logger.error(
                    "[%d/%d] patient %s FAILED: %s",
                    i, len(cohort), row["patient_id"], exc,
                )
                continue
            manifest.append(summary)
            logger.info(
                "[%d/%d] %s site=%s anchor=%s -> %d encounters, %d chars, %d sentences",
                i, len(cohort),
                row["patient_id"],
                row.get("site"),
                row["anchor_date"],
                summary["n_encounters"],
                summary["n_chars"],
                summary["n_sentences"],
            )
    finally:
        driver.close()

    manifest_path = args.output_dir / "cohort_manifest.json"
    totals = {
        "n_patients":  len(manifest),
        "n_encounters": sum(m["n_encounters"] for m in manifest),
        "n_chars":      sum(m["n_chars"] for m in manifest),
        "n_sentences":  sum(m["n_sentences"] for m in manifest),
    }
    with manifest_path.open("w") as f:
        json.dump({
            "generated_at":    datetime.now().strftime("%Y%m%dT%H%M%SZ"),
            "ncda_artifact":   str(artifact.relative_to(ROOT)),
            "window_days":     args.window_days,
            "totals":          totals,
            "patients":        manifest,
        }, f, indent=2)

    logger.info(
        "DONE  -> %d patients, %d encounters, %d chars, %d sentences",
        totals["n_patients"], totals["n_encounters"],
        totals["n_chars"], totals["n_sentences"],
    )
    logger.info("manifest: %s", manifest_path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
