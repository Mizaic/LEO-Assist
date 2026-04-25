"""Explore how cancer diagnosis and exclusion are expressed in encounter text.

Targets patients with no coded cancer signal (cancer_status = no_cancer_signal
in the audit) and sweeps their encounters for:

  Layer 1 -- keyword hits in raw encounter text
  Layer 2 -- cancer-adjacent SNOMED concepts coded on those encounters
             (chemo, radiotherapy, oncology, tumour markers, etc.)

Output
------
  Console: summary counts and grouped examples
  CSV (--output PATH): one row per flagged encounter

Usage
-----
    python scripts/explore_cancer_expressions.py
    python scripts/explore_cancer_expressions.py --output cancer_expressions.csv
    python scripts/explore_cancer_expressions.py --patient-ids 9990002005,4187508279
    python scripts/explore_cancer_expressions.py --limit 200
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from dotenv import load_dotenv  # noqa: E402
from libs.domains.ncda_concept_sets import (  # noqa: E402
    CANCER_TYPE_IDS,
    FAST_TRACK_REFERRAL_IDS,
)
from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("explore_cancer")

# ------------------------------------------------------------------
# Cancer-adjacent SNOMED concept IDs (not direct diagnoses, but
# strong signals that a cancer pathway is / was active)
# ------------------------------------------------------------------
_ADJACENT_CONCEPT_IDS: frozenset[str] = frozenset(
    [
        # Chemotherapy
        "367336001",  # Chemotherapy
        "703423002",  # Chemotherapy regimen
        "169413002",  # Chemotherapy side effect
        # Radiotherapy
        "108290001",  # Radiation oncology
        "228748004",  # Radiotherapy
        "33195004",  # Radiation therapy
        # Oncology referral / specialty
        "306205009",  # Referral to oncology service
        "308442009",  # Referral to oncologist
        "310338000",  # Referral to clinical oncologist
        "306206005",  # Referral to haematology service
        # Tumour markers
        "166558007",  # AFP within reference range
        "166559004",  # AFP above reference range
        "274754009",  # CEA measurement
        "117877009",  # PSA measurement
        "275911002",  # CA-125
        # Biopsy / histology
        "86273004",  # Biopsy
        "168457008",  # Histology
        "726566009",  # Pathology biopsy report
        "168447004",  # Biopsy of lesion
        # History of malignancy (situation nodes)
        "266987004",  # History of malignant neoplasm
        "160303001",  # Family history of cancer
        "160303001",  # FH cancer
        # Palliative care
        "306237005",  # Referral to palliative care
        "103735009",  # Palliative care
        # MDT
        "182987002",  # MDT meeting
        "445528004",  # Cancer MDT
    ]
)

_CANCER_IDS_STR = frozenset(str(c) for c in CANCER_TYPE_IDS)
_REFERRAL_IDS_STR = frozenset(str(c) for c in FAST_TRACK_REFERRAL_IDS)

# ------------------------------------------------------------------
# Keyword patterns  (case-insensitive, whole-word where safe)
# ------------------------------------------------------------------

# Patterns that suggest a DIAGNOSIS is / was present
_DIAGNOSIS_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("cancer", re.compile(r"\bcancer\b", re.IGNORECASE)),
    ("carcinoma", re.compile(r"\bcarcinoma\b", re.IGNORECASE)),
    ("malignant", re.compile(r"\bmalignant\b", re.IGNORECASE)),
    ("malignancy", re.compile(r"\bmalignancy\b", re.IGNORECASE)),
    ("neoplasm", re.compile(r"\bneoplasm\b", re.IGNORECASE)),
    ("tumour/tumor", re.compile(r"\btumou?r\b", re.IGNORECASE)),
    ("lymphoma", re.compile(r"\blymphoma\b", re.IGNORECASE)),
    ("leukaemia", re.compile(r"\bleukaemi[a]?\b|\bleukemi[a]?\b", re.IGNORECASE)),
    ("melanoma", re.compile(r"\bmelanoma\b", re.IGNORECASE)),
    ("sarcoma", re.compile(r"\bsarcoma\b", re.IGNORECASE)),
    ("myeloma", re.compile(r"\bmyeloma\b", re.IGNORECASE)),
    ("seminoma", re.compile(r"\bseminoma\b", re.IGNORECASE)),
    ("metastasis", re.compile(r"\bmetastas[ie]", re.IGNORECASE)),
    ("oncology", re.compile(r"\boncolog", re.IGNORECASE)),
    ("chemotherapy", re.compile(r"\bchemotherap", re.IGNORECASE)),
    ("radiotherapy", re.compile(r"\bradiotherap", re.IGNORECASE)),
    ("2WW", re.compile(r"\b2ww\b|\btwo.?week.?wait", re.IGNORECASE)),
    ("fast.track", re.compile(r"\bfast.track\b", re.IGNORECASE)),
]

# Patterns that suggest an EXCLUSION / normal result
_EXCLUSION_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        "no_malignancy",
        re.compile(
            r"no (evidence of |signs of |features of )?" r"malignancy", re.IGNORECASE
        ),
    ),
    ("no_cancer", re.compile(r"no (evidence of |signs of )?cancer", re.IGNORECASE)),
    ("benign", re.compile(r"\bbenign\b", re.IGNORECASE)),
    ("NAD", re.compile(r"\bNAD\b")),
    ("normal_biopsy", re.compile(r"normal (biopsy|histology)", re.IGNORECASE)),
    ("cancer_excluded", re.compile(r"cancer (excluded|ruled out)", re.IGNORECASE)),
    (
        "discharged_2WW",
        re.compile(r"discharged.{0,30}(pathway|2ww|clinic)", re.IGNORECASE),
    ),
    ("no_polyps", re.compile(r"no polyps", re.IGNORECASE)),
    (
        "clear_scope",
        re.compile(
            r"(colonoscopy|endoscopy|cystoscopy).{0,40}" r"(normal|clear|NAD)",
            re.IGNORECASE,
        ),
    ),
    ("not_suspicious", re.compile(r"not suspicious", re.IGNORECASE)),
]


# ------------------------------------------------------------------
# Cypher queries
# ------------------------------------------------------------------

_Q_NO_SIGNAL_PATIENTS = """
MATCH (p:Patient)
WHERE NOT EXISTS {
    MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(d)
    WHERE d.conceptId IN $cancer_ids
}
AND NOT EXISTS {
    MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
}
AND NOT EXISTS {
    MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(d)
    WHERE d.conceptId IN $referral_ids
}
RETURN toString(p.id) AS patient_id
ORDER BY patient_id
"""

_Q_ENCOUNTERS_FOR_PATIENTS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) IN $patient_ids
  AND e.text IS NOT NULL
  AND size(e.text) > 0
RETURN
    toString(p.id)       AS patient_id,
    toString(e.id)       AS encounter_id,
    toString(e.date)     AS encounter_date,
    e.text               AS enc_text
ORDER BY patient_id, encounter_date
"""

_Q_CODED_ON_ENCOUNTER = """
MATCH (e:Encounter)-[r:DOCUMENTS]->(d)
WHERE toString(e.id) IN $encounter_ids
RETURN
    toString(e.id)       AS encounter_id,
    d.conceptId          AS concept_id,
    d.name               AS concept_name,
    d.semanticTag        AS semantic_tag,
    r.context            AS context_json
"""


# ------------------------------------------------------------------
# Text analysis helpers
# ------------------------------------------------------------------


def _find_keyword_hits(
    text: str,
) -> tuple[list[str], list[str]]:
    """Return (diagnosis_hits, exclusion_hits) pattern names."""
    diag = [name for name, pat in _DIAGNOSIS_PATTERNS if pat.search(text)]
    excl = [name for name, pat in _EXCLUSION_PATTERNS if pat.search(text)]
    return diag, excl


def _snippet(text: str, pattern: re.Pattern, window: int = 120) -> str:
    """Return a short snippet around the first match of pattern in text."""
    m = pattern.search(text)
    if not m:
        return ""
    start = max(0, m.start() - window // 2)
    end = min(len(text), m.end() + window // 2)
    raw = text[start:end].replace("\n", " ").replace("\r", "")
    return "..." + raw.strip() + "..."


def _best_snippet(text: str, hits: list[str]) -> str:
    """Return a snippet around the first matched pattern."""
    for name, pat in _DIAGNOSIS_PATTERNS + _EXCLUSION_PATTERNS:
        if name in hits:
            s = _snippet(text, pat)
            if s:
                return s
    return text[:200]


def _parse_assertion(context_json: str | None) -> str:
    try:
        ctx = json.loads(context_json or "{}")
    except (ValueError, TypeError):
        return "present"
    if ctx.get("negated") or ctx.get("refuted"):
        return "absent"
    if ctx.get("uncertain"):
        return "possible"
    if ctx.get("historical"):
        return "historical"
    return ctx.get("assertion", "present")


# ------------------------------------------------------------------
# Data loading
# ------------------------------------------------------------------


def _load_no_signal_patients(session, patient_ids: list[str]) -> list[str]:
    """Return patient IDs with no cancer signal, filtered if --patient-ids given."""
    if patient_ids:
        return patient_ids
    rows = session.run(
        _Q_NO_SIGNAL_PATIENTS,
        cancer_ids=list(_CANCER_IDS_STR),
        referral_ids=list(_REFERRAL_IDS_STR),
    )
    return [r["patient_id"] for r in rows]


def _load_encounters(session, patient_ids: list[str], limit: int) -> list[dict]:
    """Load all non-empty encounters for the given patients."""
    rows = session.run(
        _Q_ENCOUNTERS_FOR_PATIENTS,
        patient_ids=patient_ids,
    )
    result = []
    for row in rows:
        result.append(dict(row))
        if limit and len(result) >= limit:
            break
    return result


def _load_coded_concepts(session, encounter_ids: list[str]) -> dict[str, list[dict]]:
    """Return encounter_id -> list of coded concept rows."""
    result: dict[str, list[dict]] = {}
    if not encounter_ids:
        return result
    rows = session.run(
        _Q_CODED_ON_ENCOUNTER,
        encounter_ids=encounter_ids,
    )
    for row in rows:
        eid = row["encounter_id"]
        result.setdefault(eid, []).append(dict(row))
    return result


# ------------------------------------------------------------------
# Analysis
# ------------------------------------------------------------------


def _classify_encounter(
    enc: dict,
    coded: list[dict],
) -> dict | None:
    """Analyse one encounter. Return a result row or None if no hit."""
    text = enc.get("enc_text") or ""
    diag_hits, excl_hits = _find_keyword_hits(text)
    if not diag_hits and not excl_hits:
        return None

    # Adjacent SNOMED concepts coded on this encounter
    adjacent = [
        c for c in coded if str(c.get("concept_id", "")) in _ADJACENT_CONCEPT_IDS
    ]
    cancer_concepts = [
        c for c in coded if str(c.get("concept_id", "")) in _CANCER_IDS_STR
    ]
    referral_concepts = [
        c for c in coded if str(c.get("concept_id", "")) in _REFERRAL_IDS_STR
    ]

    # Determine what category this looks like
    if excl_hits and not diag_hits:
        signal_type = "likely_excluded"
    elif diag_hits and excl_hits:
        signal_type = "mixed_signals"
    else:
        signal_type = "likely_diagnosis"

    all_hits = diag_hits + excl_hits
    snippet = _best_snippet(text, all_hits)

    return {
        "patient_id": enc["patient_id"],
        "encounter_id": enc["encounter_id"],
        "encounter_date": enc["encounter_date"],
        "signal_type": signal_type,
        "diagnosis_keywords": "|".join(diag_hits),
        "exclusion_keywords": "|".join(excl_hits),
        "cancer_concepts_coded": len(cancer_concepts),
        "referral_concepts_coded": len(referral_concepts),
        "adjacent_concepts_coded": len(adjacent),
        "adjacent_concept_names": "|".join(c.get("concept_name", "") for c in adjacent),
        "text_snippet": snippet,
    }


# ------------------------------------------------------------------
# Reporting
# ------------------------------------------------------------------


def _print_report(rows: list[dict]) -> None:
    if not rows:
        logger.info("No cancer language found in any encounter for these patients.")
        return

    by_signal: dict[str, int] = defaultdict(int)
    by_keyword: dict[str, int] = defaultdict(int)
    by_excl_keyword: dict[str, int] = defaultdict(int)
    patients_hit: set[str] = set()

    for row in rows:
        by_signal[row["signal_type"]] += 1
        patients_hit.add(row["patient_id"])
        for kw in row["diagnosis_keywords"].split("|"):
            if kw:
                by_keyword[kw] += 1
        for kw in row["exclusion_keywords"].split("|"):
            if kw:
                by_excl_keyword[kw] += 1

    logger.info("=" * 64)
    logger.info(
        "CANCER EXPRESSION EXPLORATION -- %d flagged encounters, %d patients",
        len(rows),
        len(patients_hit),
    )
    logger.info("=" * 64)

    logger.info("Signal type breakdown:")
    for sig, cnt in sorted(by_signal.items(), key=lambda x: -x[1]):
        logger.info("  %-25s %d encounters", sig, cnt)

    logger.info("")
    logger.info("Diagnosis keyword frequencies:")
    for kw, cnt in sorted(by_keyword.items(), key=lambda x: -x[1]):
        logger.info("  %-25s %d", kw, cnt)

    logger.info("")
    logger.info("Exclusion keyword frequencies:")
    for kw, cnt in sorted(by_excl_keyword.items(), key=lambda x: -x[1]):
        logger.info("  %-25s %d", kw, cnt)

    logger.info("")
    logger.info("Sample encounters (up to 10):")
    shown = 0
    for row in rows:
        if shown >= 10:
            break
        logger.info(
            "  [%s] %s  type=%-20s diag=%s excl=%s",
            row["patient_id"],
            row["encounter_date"],
            row["signal_type"],
            row["diagnosis_keywords"],
            row["exclusion_keywords"],
        )
        logger.info("  snippet: %s", row["text_snippet"][:200])
        logger.info("")
        shown += 1

    logger.info("=" * 64)


def _write_csv(rows: list[dict], path: str) -> None:
    if not rows:
        logger.warning("No rows to write")
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    logger.info("Wrote %d rows to %s", len(rows), path)


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Explore cancer expression patterns in no-signal patients"
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        default="",
        help="Write flagged encounters to a CSV file",
    )
    parser.add_argument(
        "--patient-ids",
        metavar="IDS",
        default="",
        help="Comma-separated patient IDs (default: all no-signal patients)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Cap the number of encounters scanned (0 = unlimited)",
    )
    args = parser.parse_args()

    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "")

    if not neo4j_password:
        logger.error(
            "NEO4J_PASSWORD is not set. "
            "Ensure secrets/.env exists or AZURE_KEYVAULT_URL is configured."
        )
        sys.exit(1)

    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

    explicit_ids = (
        [p.strip() for p in args.patient_ids.split(",") if p.strip()]
        if args.patient_ids
        else []
    )

    with driver.session() as session:
        logger.info("Identifying no-signal patients...")
        patient_ids = _load_no_signal_patients(session, explicit_ids)
        logger.info("Scanning encounters for %d patients...", len(patient_ids))

        encounters = _load_encounters(session, patient_ids, args.limit)
        logger.info("Loaded %d encounters", len(encounters))

        encounter_ids = [e["encounter_id"] for e in encounters]
        logger.info("Loading coded concepts for those encounters...")
        coded_by_enc = _load_coded_concepts(session, encounter_ids)

    driver.close()

    logger.info("Analysing encounter text...")
    results: list[dict] = []
    for enc in encounters:
        coded = coded_by_enc.get(enc["encounter_id"], [])
        row = _classify_encounter(enc, coded)
        if row:
            results.append(row)

    _print_report(results)

    if args.output:
        _write_csv(results, args.output)
    elif results:
        logger.info("Run with --output cancer_expressions.csv for the full detail.")


if __name__ == "__main__":
    main()
