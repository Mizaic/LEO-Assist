"""Auto-stamped Atlas trace.

Atlas trace:
  DO: DO-4D608335
  DI: DI-760F5FB7
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-4D608335")

Phase 7: Load NHS OPCS-4 data files into Neo4j.

Source: TRUD pack 10, item 119 ("OPCS-4 data files").

The release ships a tab-delimited text file containing one row per code:
    <code><TAB><title>

OPCS-4 code structure:
  - Single letter (e.g. "A") = chapter ("Nervous System")
  - Letter + 2 digits (e.g. "A01") = category ("Major excision of brain")
  - Letter + 3 digits with optional dot (e.g. "A01.1") = code ("Hemispherectomy")

We derive the chapter and category for every row from the leading
characters of the code, so the IS_A hierarchy can be materialised even
when the source file does not list chapter rows explicitly.

Output:
  (:OpcsCode {code, title, chapter, level, edition})
  (:OpcsCode)-[:IS_A]->(:OpcsCode)

Idempotent: MERGE on `code`. Re-running overwrites title and metadata
so existing bare nodes left by load_opcs4_map gain titles in-place.

Supports DI-LEO-AI-226, DO-LEO-AI-223.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any, Iterable

from neo4j import AsyncDriver

from .base import BatchWriter

logger = logging.getLogger(__name__)


MERGE_NODE = """
UNWIND $rows AS r
MERGE (c:OpcsCode {code: r.code})
SET c.title = r.title,
    c.chapter = r.chapter,
    c.edition = r.edition,
    c.level = r.level
"""

MERGE_PARENT = """
UNWIND $rows AS r
MATCH (child:OpcsCode {code: r.child})
MATCH (parent:OpcsCode {code: r.parent})
MERGE (child)-[:IS_A]->(parent)
"""


# -- Helpers --------------------------------------------------------------


_CHAPTER_NAMES: dict[str, str] = {
    "A": "Nervous System",
    "B": "Endocrine System and Breast",
    "C": "Eye",
    "D": "Ear",
    "E": "Respiratory Tract",
    "F": "Mouth",
    "G": "Upper Digestive System",
    "H": "Lower Digestive System",
    "J": "Other Abdominal Organs - Principally Digestive",
    "K": "Heart",
    "L": "Arteries and Veins",
    "M": "Urinary",
    "N": "Male Genital Organs",
    "P": "Lower Female Genital Tract",
    "Q": "Upper Female Genital Tract",
    "R": "Female Genital Tract Associated with Pregnancy, Childbirth and the Puerperium",
    "S": "Skin",
    "T": "Soft Tissue",
    "U": "Diagnostic Imaging, Testing and Rehabilitation",
    "V": "Bones and Joints of Skull and Spine",
    "W": "Other Bones and Joints",
    "X": "Miscellaneous Operations",
    "Y": "Subsidiary Classification of Methods of Operation",
    "Z": "Subsidiary Classification of Sites of Operation",
    "O": "Overflow Codes (additions to OPCS-4)",
}


def _normalise_code(code: str) -> str:
    """Return canonical dotted form (e.g. A011 -> A01.1, A01 unchanged)."""
    code = code.strip().upper()
    if not code or "." in code:
        return code
    if re.fullmatch(r"[A-Z]\d{3}", code):
        return f"{code[:3]}.{code[3:]}"
    return code


def _classify_level(code: str) -> str:
    """Derive level from canonical code shape."""
    if re.fullmatch(r"[A-Z]", code):
        return "chapter"
    if re.fullmatch(r"[A-Z]\d{2}", code):
        return "category"
    if re.fullmatch(r"[A-Z]\d{2}\.\d", code):
        return "code"
    return "code"


def _chapter_of(code: str) -> str:
    return code[:1] if code else ""


def _category_of(code: str) -> str:
    return code[:3] if len(code) >= 3 else ""


def _stream_rows(filepath: Path) -> Iterable[tuple[str, str]]:
    """Yield (code, title) tuples from a tab-delimited OPCS-4 file."""
    with open(filepath, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                parts = re.split(r"\s{2,}", line, maxsplit=1)
            if len(parts) < 2:
                continue
            code, title = parts[0].strip(), parts[1].strip()
            if not code or not title:
                continue
            yield code, title


def _read_edition(filepath: Path) -> str:
    """Best-effort edition string from filename (e.g. 'OPCS49 ... Nov 2024.txt')."""
    name = filepath.name
    match = re.search(r"OPCS[ -]?4(\d+)?", name, re.IGNORECASE)
    base = match.group(0).upper() if match else "OPCS-4"
    date_match = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[ ]?(\d{4})", name)
    if date_match:
        return f"{base} {date_match.group(1)} {date_match.group(2)}"
    return base


# -- Loader ---------------------------------------------------------------


async def _existing_titles(driver: AsyncDriver, codes: set[str]) -> dict[str, str]:
    """Fetch current titles for the given codes (for drift detection)."""
    if not codes:
        return {}
    query = (
        "UNWIND $codes AS code "
        "MATCH (c:OpcsCode {code: code}) "
        "RETURN c.code AS code, c.title AS title"
    )
    out: dict[str, str] = {}
    async with driver.session() as session:
        result = await session.run(query, codes=list(codes))
        async for record in result:
            out[record["code"]] = record["title"] or ""
    return out


def _build_node_rows(
    file_rows: Iterable[tuple[str, str]],
    edition: str,
) -> tuple[list[dict], list[dict]]:
    """Materialise nodes and IS_A parents from raw (code, title) pairs.

    Synthesises chapter and category nodes when the source file omits them
    so the IS_A hierarchy is always closed at the chapter root.
    """
    nodes_by_code: dict[str, dict] = {}
    parents: list[dict] = []
    seen_parent_edges: set[tuple[str, str]] = set()

    def _ensure(code: str, title: str, level: str) -> None:
        if code in nodes_by_code:
            existing = nodes_by_code[code]
            if title and not existing["title"]:
                existing["title"] = title
            return
        nodes_by_code[code] = {
            "code": code,
            "title": title,
            "chapter": _chapter_of(code),
            "edition": edition,
            "level": level,
        }

    def _link(child: str, parent: str) -> None:
        if not parent or child == parent:
            return
        key = (child, parent)
        if key in seen_parent_edges:
            return
        seen_parent_edges.add(key)
        parents.append({"child": child, "parent": parent})

    for raw_code, title in file_rows:
        code = _normalise_code(raw_code)
        if not code:
            continue
        level = _classify_level(code)
        _ensure(code, title, level)

        if level == "code":
            category = _category_of(code)
            chapter = _chapter_of(code)
            _ensure(category, "", "category")
            _ensure(chapter, _CHAPTER_NAMES.get(chapter, ""), "chapter")
            _link(code, category)
            _link(category, chapter)
        elif level == "category":
            chapter = _chapter_of(code)
            _ensure(chapter, _CHAPTER_NAMES.get(chapter, ""), "chapter")
            _link(code, chapter)

    return list(nodes_by_code.values()), parents


async def load_opcs4(
    driver: AsyncDriver,
    filepath: Path,
    batch_size: int = 5_000,
) -> dict[str, Any]:
    """Load an OPCS-4 codes-and-titles file into Neo4j.

    Returns a structured summary dict (used by callers and surfaced in the
    Sync from TRUD log panel).
    """
    label = f"OPCS4({filepath.name})"
    edition = _read_edition(filepath)
    logger.info("%s: starting (edition=%s)", label, edition)
    t0 = time.monotonic()

    nodes, parents = _build_node_rows(_stream_rows(filepath), edition)
    code_set = {n["code"] for n in nodes}
    prior_titles = await _existing_titles(driver, code_set)
    titles_first_time = sum(
        1 for n in nodes if n["title"] and not prior_titles.get(n["code"])
    )
    titles_drifted = sum(
        1
        for n in nodes
        if n["title"]
        and prior_titles.get(n["code"])
        and prior_titles[n["code"]] != n["title"]
    )

    async with driver.session() as session:
        node_writer = BatchWriter(session, MERGE_NODE, batch_size, f"{label}/nodes")
        for row in nodes:
            await node_writer.add(row)
        nodes_written = await node_writer.finish()

        parent_writer = BatchWriter(session, MERGE_PARENT, batch_size, f"{label}/IS_A")
        for row in parents:
            await parent_writer.add(row)
        edges_written = await parent_writer.finish()

    summary = {
        "edition": edition,
        "nodes_upserted": nodes_written,
        "is_a_edges_upserted": edges_written,
        "titles_first_time": titles_first_time,
        "titles_drifted": titles_drifted,
        "duration_s": round(time.monotonic() - t0, 1),
    }
    logger.info("%s: summary %s", label, summary)
    return summary
