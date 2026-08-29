"""Shared completeness schema evaluation for runtime and preview paths.

Atlas trace:
  DO: DO-69F520C9
  DI: DI-F22160C3
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-69F520C9")
"""

from __future__ import annotations

from functools import partial
from typing import Any, Callable

from libs.completeness.logic_groups import evaluate_logic_group
from libs.pipeline.form_section_hits import form_hit_result
from libs.terminology.semantic_tag import normalise_semantic_tag

_ISA_DESCENDANTS_QUERY = (
    "MATCH (ancestor:Concept)<-[:IS_A*1..5]-(d:Concept) "
    "WHERE ancestor.id IN $ids AND d.active = true "
    "RETURN ancestor.id AS parent_id, d.id AS child_id"
)


def concept_ids_from_entities(entities: list[dict[str, Any]]) -> set[int]:
    """Collect SNOMED concept IDs from pipeline entity dicts."""
    ids: set[int] = set()
    for entity in entities:
        concept_id = entity.get("concept_id") or entity.get("snomed_concept_id")
        if not concept_id and isinstance(entity.get("coding"), dict):
            concept_id = entity["coding"].get("snomed_concept_id")
        try:
            parsed = int(str(concept_id or "").strip())
        except ValueError:
            continue
        if parsed > 0:
            ids.add(parsed)
    return ids


def semantic_tags_from_entities(entities: list[dict[str, Any]]) -> set[str]:
    """Collect normalised semantic tags from pipeline entity dicts."""
    tags: set[str] = set()
    for entity in entities:
        raw = entity.get("semantic_tag") or entity.get("label") or ""
        if str(raw).strip():
            tags.add(normalise_semantic_tag(str(raw)))
    return tags


def normalise_category_tags(raw_tags: list[Any]) -> set[str]:
    """Normalise configured semantic category labels for comparison."""
    return {normalise_semantic_tag(str(tag)) for tag in raw_tags if str(tag).strip()}


def build_isa_expansion(
    required_ids: set[int],
    kg_run: Callable[..., list[dict[str, Any]]] | None,
) -> dict[int, set[int]]:
    """Map each required concept ID to itself plus active IS_A descendants."""
    if not required_ids:
        return {}
    expansion = {rid: {rid} for rid in required_ids}
    if kg_run is None:
        return expansion
    try:
        rows = kg_run(
            _ISA_DESCENDANTS_QUERY,
            ids=[str(rid) for rid in sorted(required_ids)],
        )
    except Exception:
        return expansion
    for row in rows or []:
        parent = _parse_concept_id(row.get("parent_id"))
        child = _parse_concept_id(row.get("child_id"))
        if parent and child:
            expansion.setdefault(parent, {parent}).add(child)
    return expansion


def evaluate_completeness_groups(
    schema: list[dict[str, Any]],
    *,
    present_concept_ids: set[int],
    present_semantic_tags: set[str],
    isa_expansion: dict[int, set[int]] | None = None,
    section_hits: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Evaluate completeness groups against facts and taught-form hits."""
    matched: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    leaf = partial(
        _evaluate_leaf,
        present_concept_ids=present_concept_ids,
        present_semantic_tags=present_semantic_tags,
        isa_expansion=isa_expansion,
        section_hits=section_hits or [],
    )
    for group in schema:
        row = evaluate_logic_group(group, leaf)
        (matched if row["matched"] else missing).append(row)
    required_unassessed = [
        row
        for row in missing
        if row["required"] and row.get("outcome") == "not_assessable"
    ]
    return {
        "matched_groups": matched,
        "missing_groups": missing,
        "complete": not any(row["required"] for row in missing),
        "concept_ids": sorted(present_concept_ids),
        "degraded": bool(required_unassessed),
    }


def _evaluate_leaf(
    group: dict[str, Any],
    *,
    present_concept_ids: set[int],
    present_semantic_tags: set[str],
    isa_expansion: dict[int, set[int]] | None,
    section_hits: list[dict[str, Any]],
) -> dict[str, Any]:
    required_ids = {
        int(cid) for cid in group.get("concept_ids", []) if _parse_concept_id(cid)
    }
    categories = normalise_category_tags(list(group.get("semantic_categories") or []))
    id_hits, absent_ids = _concept_match(
        required_ids, present_concept_ids, isa_expansion
    )
    tag_hit = bool(categories & present_semantic_tags)
    missing_tags = bool(categories) and not tag_hit
    form_matched, form_assessable = form_hit_result(group, section_hits)
    matched, outcome = _leaf_outcome(
        required_ids=required_ids,
        categories=categories,
        absent_ids=absent_ids,
        missing_tags=missing_tags,
        form_matched=form_matched,
        form_assessable=form_assessable,
        has_form=_has_form_fields(group),
    )
    return {
        "name": str(group.get("name") or ""),
        "required": bool(group.get("required", True)),
        "matched": matched,
        "outcome": outcome,
        "matched_concept_ids": id_hits,
        "missing_concept_ids": absent_ids,
        "matched_semantic_category": tag_hit,
        "matched_member_names": [],
    }


def _has_form_fields(group: dict[str, Any]) -> bool:
    return bool(
        str(group.get("section_id") or "").strip()
        or str(group.get("item_pattern") or "").strip()
    )


def _leaf_outcome(
    *,
    required_ids: set[int],
    categories: set[str],
    absent_ids: list[int],
    missing_tags: bool,
    form_matched: bool,
    form_assessable: bool,
    has_form: bool,
) -> tuple[bool, str]:
    has_legacy = bool(required_ids) or bool(categories)
    if form_assessable and form_matched:
        return True, "matched"
    if has_legacy:
        matched = not absent_ids and not missing_tags
        return matched, "matched" if matched else "not_matched"
    if has_form and form_assessable:
        return False, "not_matched"
    return False, "not_assessable"


def _concept_match(
    required_ids: set[int],
    present_concept_ids: set[int],
    isa_expansion: dict[int, set[int]] | None,
) -> tuple[list[int], list[int]]:
    if not required_ids:
        return [], []
    hits: list[int] = []
    absent: list[int] = []
    for rid in sorted(required_ids):
        match_ids = {rid}
        if isa_expansion:
            match_ids = isa_expansion.get(rid, {rid})
        if match_ids & present_concept_ids:
            hits.append(rid)
        else:
            absent.append(rid)
    if hits:
        return hits, []
    return [], absent


def _parse_concept_id(value: Any) -> int:
    try:
        parsed = int(str(value or "").strip())
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0
