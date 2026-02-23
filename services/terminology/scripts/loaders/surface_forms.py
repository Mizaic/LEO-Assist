"""
Phase 6: Load surface forms into Neo4j as (:SurfaceForm) nodes.

Sources:
  - external_content/known_terms.json         — 3,446 clinical terms (list of strings)
  - external_content/encounter_analysis.json   — unmatched terms from encounter NLP
  - external_content/clinical_term_analysis.json — Read codes from clinical data
  - external_content/umls/LEXICON.txt          — SPECIALIST Lexicon base forms + variants
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from neo4j import AsyncDriver

from .base import BatchWriter, normalize_term

logger = logging.getLogger(__name__)

MERGE_SURFACE_FORM = """
UNWIND $rows AS r
MERGE (sf:SurfaceForm {form: r.form})
SET sf.normalized = r.normalized,
    sf.source = r.source,
    sf.mapped = false
"""


def _parse_lexicon(filepath: Path):
    """Parse SPECIALIST Lexicon text format into base+variant entries."""
    current_base = None
    variants = []

    with open(filepath, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith("{base="):
                current_base = line[6:]
                variants = [current_base]
            elif line.startswith("spelling_variant="):
                variants.append(line[17:])
            elif line == "}" and current_base:
                for v in variants:
                    yield v
                current_base = None
                variants = []


def _extract_unmatched_terms(data: dict) -> list[str]:
    """Extract unmatched terms from encounter_analysis.json summary."""
    terms = []
    summary = data.get("summary", {})
    for term_pair in summary.get("top_unmatched_terms", []):
        if isinstance(term_pair, list) and len(term_pair) >= 1:
            terms.append(str(term_pair[0]))
    return terms


def _extract_clinical_read_terms(data: dict) -> list[str]:
    """Extract Read code terms from clinical_term_analysis.json."""
    terms = []
    global_data = data.get("global_analysis", {})
    for code_pair in global_data.get("top_read_codes", []):
        if isinstance(code_pair, list) and len(code_pair) >= 1:
            terms.append(str(code_pair[0]))
    return terms


async def load_known_terms(
    driver: AsyncDriver,
    filepath: Path,
    batch_size: int = 5_000,
) -> int:
    """Load known_terms.json as SurfaceForm nodes."""
    label = "known_terms"
    logger.info("%s: loading from %s", label, filepath.name)
    with open(filepath, encoding="utf-8") as f:
        terms = json.load(f)

    async with driver.session() as session:
        writer = BatchWriter(session, MERGE_SURFACE_FORM, batch_size, label)
        for term in terms:
            t = str(term).strip()
            if t:
                await writer.add({
                    "form": t,
                    "normalized": normalize_term(t),
                    "source": "known_terms",
                })
        return await writer.finish()


async def load_encounter_analysis(
    driver: AsyncDriver,
    filepath: Path,
    batch_size: int = 5_000,
) -> int:
    """Load unmatched terms from encounter_analysis.json."""
    label = "encounter_analysis"
    logger.info("%s: loading from %s", label, filepath.name)
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

    terms = _extract_unmatched_terms(data)
    async with driver.session() as session:
        writer = BatchWriter(session, MERGE_SURFACE_FORM, batch_size, label)
        for t in terms:
            t = t.strip()
            if t:
                await writer.add({
                    "form": t,
                    "normalized": normalize_term(t),
                    "source": "encounter_analysis",
                })
        return await writer.finish()


async def load_clinical_term_analysis(
    driver: AsyncDriver,
    filepath: Path,
    batch_size: int = 5_000,
) -> int:
    """Load Read code terms from clinical_term_analysis.json."""
    label = "clinical_term_analysis"
    logger.info("%s: loading from %s", label, filepath.name)
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

    terms = _extract_clinical_read_terms(data)
    async with driver.session() as session:
        writer = BatchWriter(session, MERGE_SURFACE_FORM, batch_size, label)
        for t in terms:
            t = t.strip()
            if t:
                await writer.add({
                    "form": t,
                    "normalized": normalize_term(t),
                    "source": "clinical_term_analysis",
                })
        return await writer.finish()


async def load_lexicon(
    driver: AsyncDriver,
    filepath: Path,
    batch_size: int = 5_000,
) -> int:
    """Load SPECIALIST Lexicon base forms and spelling variants."""
    label = "LEXICON"
    logger.info("%s: loading from %s", label, filepath.name)
    async with driver.session() as session:
        writer = BatchWriter(session, MERGE_SURFACE_FORM, batch_size, label)
        for term in _parse_lexicon(filepath):
            t = term.strip()
            if t:
                await writer.add({
                    "form": t,
                    "normalized": normalize_term(t),
                    "source": "lexicon",
                })
        return await writer.finish()
