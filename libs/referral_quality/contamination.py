"""Fail facts whose evidence sits in sealed or unclaimed form text.

Atlas trace:
  DI: DI-9A75B3C6
  DO: DO-E9A3C122
  VT: VT-C73DA421
  Risk: R-238CAF49
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from libs.pipeline.form_coverage import _is_claimable
from libs.pipeline.form_schema_normalizer import FormSchema, FormSection

FORBIDDEN = frozenset({"admin", "template_noise", "unclaimed"})


@dataclass(frozen=True)
class ContaminationHit:
    fact_text: str
    region: str
    evidence: str


def classify_lines(schema: FormSchema, letter: str) -> list[tuple[str, str]]:
    """Tag each claimable line with its taught section type or unclaimed."""
    current: FormSection | None = None
    rows: list[tuple[str, str]] = []
    for line in letter.splitlines():
        matched = _matching_section(line, schema.sections)
        if matched is not None:
            current = matched
        if not _is_claimable(line):
            continue
        kind = current.section_type if current is not None else "unclaimed"
        rows.append((line.strip(), kind))
    return rows


def find_contaminated_facts(
    facts: list[dict[str, Any]],
    schema: FormSchema,
    letter: str,
) -> list[ContaminationHit]:
    """Return hits when fact evidence traces only to a forbidden region."""
    blobs = _region_blobs(classify_lines(schema, letter))
    clinical = blobs.get("clinical", "")
    hits: list[ContaminationHit] = []
    for fact in facts:
        hit = _hit_for_fact(fact, blobs, clinical)
        if hit is not None:
            hits.append(hit)
    return hits


def _matching_section(line: str, sections: list[FormSection]) -> FormSection | None:
    for section in sections:
        if section.matches_header(line):
            return section
    return None


def _region_blobs(rows: list[tuple[str, str]]) -> dict[str, str]:
    buckets: dict[str, list[str]] = {kind: [] for kind in FORBIDDEN}
    buckets["clinical"] = []
    for line, kind in rows:
        key = kind if kind in FORBIDDEN else "clinical"
        buckets[key].append(line)
    return {key: "\n".join(lines).lower() for key, lines in buckets.items()}


def _hit_for_fact(
    fact: dict[str, Any],
    blobs: dict[str, str],
    clinical: str,
) -> ContaminationHit | None:
    evidence = str(fact.get("evidence_text") or fact.get("text") or "").strip()
    if not evidence:
        return None
    needle = evidence.lower()
    if needle in clinical:
        return None
    for kind in ("template_noise", "admin", "unclaimed"):
        if needle in blobs.get(kind, ""):
            return ContaminationHit(
                fact_text=str(fact.get("text") or evidence),
                region=kind,
                evidence=evidence,
            )
    return None
