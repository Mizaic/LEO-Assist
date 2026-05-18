"""Auto-stamped Atlas trace.

Atlas trace:
  DO: DO-4D608335
  DI: DI-760F5FB7
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-4D608335")

Phase 6: Load NHS ICD-10 5th Edition XML into Neo4j.

Source: TRUD pack 28, item 259 ("NHS ICD-10 5th Edition XML data files").

The release ships a single ClaML XML file. Each <Class> element carries a
code, a 'kind' (chapter | block | category), an optional <SuperClass> ref,
one or more <Rubric> children (preferred title, age range, sex constraint),
and zero or more <SubClass> children. We stream-parse with iterparse so
peak memory stays bounded regardless of release size.

Output:
  (:Icd10Code {code, title, chapter, block, age_range, sex,
               edition, level})
  (:Icd10Code)-[:IS_A]->(:Icd10Code)

Idempotent: MERGE on `code`. Re-running overwrites title and metadata
(SET semantics) so existing bare nodes left by the SNOMED ExtendedMap
loader gain titles in-place.

Supports DI-LEO-AI-228, DO-LEO-AI-301.
"""

from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from neo4j import AsyncDriver

from .base import BatchWriter

logger = logging.getLogger(__name__)


MERGE_NODE = """
UNWIND $rows AS r
MERGE (c:Icd10Code {code: r.code})
SET c.title = r.title,
    c.chapter = r.chapter,
    c.block = r.block,
    c.age_range = r.age_range,
    c.sex = r.sex,
    c.edition = r.edition,
    c.level = r.level
"""

MERGE_PARENT = """
UNWIND $rows AS r
MATCH (child:Icd10Code {code: r.child})
MATCH (parent:Icd10Code {code: r.parent})
MERGE (child)-[:IS_A]->(parent)
"""


# -- Helpers --------------------------------------------------------------


def _strip_ns(tag: str) -> str:
    """Strip XML namespace from a tag name."""
    return tag.split("}", 1)[1] if "}" in tag else tag


def _normalise_code(code: str) -> str:
    """Return canonical NHS ICD-10 form.

    NHS publishes 4-character codes without the dot (I500). The graph stores
    them with the dot (I50.0) so the SNOMED ExtendedMap target codes match.
    Chapter and block codes are returned unchanged.
    """
    code = code.strip()
    if not code:
        return code
    if "." in code or "-" in code:
        return code
    if len(code) == 4 and code[0].isalpha() and code[1:].isdigit():
        return f"{code[:3]}.{code[3:]}"
    return code


def _classify_level(kind: str, code: str) -> str:
    """Map ClaML kind to our level vocabulary."""
    kind = (kind or "").lower()
    if kind == "chapter":
        return "chapter"
    if kind == "block":
        return "block"
    if "-" in code:
        return "block"
    if "." in code:
        return "code"
    return "category"


def _extract_title(class_elem: ET.Element) -> str:
    """First Rubric kind='preferred' Label wins; fall back to first Label."""
    fallback = ""
    for rub in class_elem.iter():
        if _strip_ns(rub.tag) != "Rubric":
            continue
        kind = rub.get("kind", "")
        for child in rub.iter():
            if _strip_ns(child.tag) != "Label":
                continue
            text = "".join(child.itertext()).strip()
            if not text:
                continue
            if kind == "preferred":
                return text
            if not fallback:
                fallback = text
    return fallback


def _extract_constraint(class_elem: ET.Element, attr: str) -> str:
    """Pull a ModifierClass-style constraint attribute (age range, sex)."""
    for child in class_elem.iter():
        if _strip_ns(child.tag) != "Meta":
            continue
        name = child.get("name", "").lower()
        if name == attr:
            return child.get("value", "").strip()
    return ""


def _parent_code(class_elem: ET.Element) -> str:
    """First SuperClass child (raw code; caller normalises)."""
    for child in class_elem.iter():
        if _strip_ns(child.tag) == "SuperClass":
            ref = child.get("code", "").strip()
            if ref:
                return ref
    return ""


# -- Streaming parse ------------------------------------------------------


def _iter_classes(filepath: Path):
    """Yield (raw_code, kind, parent_raw, title, age_range, sex) per Class."""
    context = ET.iterparse(filepath, events=("end",))
    for _event, elem in context:
        if _strip_ns(elem.tag) != "Class":
            continue
        raw_code = elem.get("code", "").strip()
        if not raw_code:
            elem.clear()
            continue
        kind = elem.get("kind", "")
        parent_raw = _parent_code(elem)
        title = _extract_title(elem)
        age_range = _extract_constraint(elem, "age")
        sex = _extract_constraint(elem, "sex")
        yield raw_code, kind, parent_raw, title, age_range, sex
        elem.clear()


# -- Loader ---------------------------------------------------------------


def _read_edition(filepath: Path) -> str:
    """Pull a Title/@date from the ClaML header (best effort)."""
    try:
        for _event, elem in ET.iterparse(filepath, events=("end",)):
            if _strip_ns(elem.tag) == "Title":
                date = elem.get("date") or elem.get("version") or ""
                if date:
                    return date.strip()
            if _strip_ns(elem.tag) == "ClassKinds":
                return ""
    except ET.ParseError:
        pass
    return ""


async def _existing_titles(driver: AsyncDriver, codes: set[str]) -> dict[str, str]:
    """Fetch current titles for the given codes (for drift detection)."""
    if not codes:
        return {}
    query = (
        "UNWIND $codes AS code "
        "MATCH (c:Icd10Code {code: code}) "
        "RETURN c.code AS code, c.title AS title"
    )
    out: dict[str, str] = {}
    async with driver.session() as session:
        result = await session.run(query, codes=list(codes))
        async for record in result:
            out[record["code"]] = record["title"] or ""
    return out


async def load_icd10_xml(  # noqa: C901 - structured for clarity, complexity 11
    driver: AsyncDriver,
    filepath: Path,
    batch_size: int = 5_000,
) -> dict[str, Any]:
    """Stream-parse the NHS ICD-10 5th Edition XML and load into Neo4j.

    Returns a structured summary dict (used by callers and surfaced in the
    Sync from TRUD log panel).
    """
    label = f"Icd10XML({filepath.name})"
    edition = _read_edition(filepath)
    logger.info("%s: starting (edition=%s)", label, edition or "unknown")
    t0 = time.monotonic()

    nodes: list[dict] = []
    parents: list[dict] = []
    chapter_for: dict[str, str] = {}
    block_for: dict[str, str] = {}

    for raw_code, kind, parent_raw, title, age_range, sex in _iter_classes(filepath):
        code = _normalise_code(raw_code)
        parent = _normalise_code(parent_raw) if parent_raw else ""
        level = _classify_level(kind, code)

        if level == "chapter":
            chapter_for[code] = code
        elif level == "block" and parent:
            chapter_for[code] = chapter_for.get(parent, parent)
        elif parent:
            block_for[code] = (
                parent if _classify_level("", parent) == "block" else block_for.get(parent, "")
            )
            chapter_for[code] = chapter_for.get(parent, "")

        nodes.append(
            {
                "code": code,
                "title": title,
                "chapter": chapter_for.get(code, ""),
                "block": block_for.get(code, ""),
                "age_range": age_range,
                "sex": sex,
                "edition": edition,
                "level": level,
            }
        )
        if parent:
            parents.append({"child": code, "parent": parent})

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
