"""Synthesise minimal happy/fail/boundary test patients from rule logic trees.

For every active AppropriatenessRule in scope this generator emits:

  - happy(rule):    one patient that satisfies all required groups
  - fail(rule):     one patient that minimally violates the rule
  - happy(branch):  one patient per top-level OR branch
  - boundary(age):  age = bound and age = bound - 1 for each DEMOGRAPHIC

The output is a list of *proposals* (not persisted).  The reviewer is
expected to dry-run them, tick which to keep, then save via the
``confirm_and_save`` flow which dedups by content_hash.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from app.db.neo4j_client import CodingGraphClient
from app.services.test_patient_service import (
    PatientPayload,
    find_existing,
    list_rules_in_scope,
)


@dataclass
class Proposal:
    """A single proposed patient with provenance."""

    payload: PatientPayload
    rule_id: str
    rule_name: str
    guideline_id: str
    kind: Literal["happy", "fail", "branch", "boundary"]
    rationale: str

    def to_dict(self) -> dict:
        return {
            "patient": {
                "codes": self.payload.codes,
                "age": self.payload.age,
                "sex": self.payload.sex,
                "pathway_id": self.payload.pathway_id,
                "name": self.payload.name,
                "description": self.payload.description,
                "generation_source": "generated",
            },
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "guideline_id": self.guideline_id,
            "kind": self.kind,
            "rationale": self.rationale,
            "content_hash": self.payload.content_hash(),
        }


def generate(
    client: CodingGraphClient,
    *,
    scope_type: Literal["rule", "branch", "guideline", "all"],
    guideline_id: str | None,
    rule_id: str | None,
    branch_node_id: str | None,
    depth: Literal["minimal_pair", "boundary_plus_pairs"],
    exclude_existing: bool,
) -> dict:
    """Top-level entry point used by the FastAPI router."""
    rules = _select_rules(client, scope_type, guideline_id, rule_id)
    proposals: list[Proposal] = []
    for rule in rules:
        tree = _parse(rule.get("logic_json"))
        if tree is None:
            continue
        proposals.extend(
            _proposals_for_rule(rule, tree, depth, branch_node_id)
        )

    if exclude_existing:
        proposals = _dedup(client, proposals)

    return {
        "proposals": [p.to_dict() for p in proposals],
        "scope_type": scope_type,
        "depth": depth,
        "rules_considered": len(rules),
    }


def _select_rules(
    client: CodingGraphClient,
    scope_type: str,
    guideline_id: str | None,
    rule_id: str | None,
) -> list[dict]:
    if scope_type == "rule":
        return list_rules_in_scope(client, rule_id=rule_id)
    if scope_type == "all":
        return list_rules_in_scope(client)
    return list_rules_in_scope(client, guideline_id=guideline_id)


def _proposals_for_rule(
    rule: dict,
    tree: dict,
    depth: str,
    branch_node_id: str | None,
) -> list[Proposal]:
    rid = rule["rule_id"]
    name = rule.get("name") or rid
    gid = rule.get("guideline_id") or ""
    proposals: list[Proposal] = []

    happy = _happy_payload(tree)
    if happy is not None:
        proposals.append(
            _make(happy, rid, name, gid, "happy", "Has all required findings")
        )

    fail = _fail_payload(tree)
    if fail is not None:
        proposals.append(
            _make(
                fail,
                rid,
                name,
                gid,
                "fail",
                "Missing one required finding",
            )
        )

    if depth == "boundary_plus_pairs":
        for branch in _top_level_or_branches(tree):
            if branch_node_id and branch.get("node_id") != branch_node_id:
                continue
            payload = _happy_payload(branch)
            if payload is None:
                continue
            proposals.append(
                _make(
                    payload,
                    rid,
                    name,
                    gid,
                    "branch",
                    f"Hits OR branch {branch.get('node_id') or 'top-level'}",
                )
            )
        proposals.extend(_boundary_proposals(tree, rid, name, gid))

    return proposals


# ---------------------------------------------------------------------------
# Tree walking -- produces (codes, age, sex) triples that satisfy / violate
# ---------------------------------------------------------------------------


def _happy_payload(tree: dict) -> PatientPayload | None:
    codes, age, sex = [], None, None
    if not _collect_satisfying(tree, codes, [age], [sex]):
        return None
    age, sex = _collect_demographic(tree)
    return PatientPayload(
        codes=codes,
        age=age,
        sex=sex,
        generation_source="generated",
    )


def _collect_satisfying(
    node: dict,
    codes: list[str],
    age_box: list[Any],
    sex_box: list[Any],
) -> bool:
    """Add codes/demographics so the subtree evaluates to True."""
    if not isinstance(node, dict):
        return False
    kind = str(node.get("kind") or "").upper()

    if kind == "CONCEPT":
        cid = ((node.get("criterion") or {}).get("snomed_concept_id"))
        if cid:
            codes.append(str(cid))
            return True
        return False

    if kind == "DEMOGRAPHIC":
        # Demographics are handled separately via _collect_demographic.
        return True

    children = [c for c in (node.get("children") or []) if isinstance(c, dict)]
    if not children:
        return False

    if kind == "AND":
        return all(_collect_satisfying(c, codes, age_box, sex_box) for c in children)
    if kind == "OR":
        for child in children:
            tmp_codes: list[str] = []
            if _collect_satisfying(child, tmp_codes, age_box, sex_box):
                codes.extend(tmp_codes)
                return True
        return False
    if kind == "AT_LEAST":
        min_n = int(node.get("min") or 1)
        hits = 0
        for child in children:
            tmp: list[str] = []
            if _collect_satisfying(child, tmp, age_box, sex_box):
                codes.extend(tmp)
                hits += 1
            if hits >= min_n:
                return True
        return hits >= min_n
    if kind == "NOT":
        # A NOT is satisfied when the inner subtree is NOT satisfied;
        # do not add any codes for the inner subtree.
        return True
    return False


def _fail_payload(tree: dict) -> PatientPayload | None:
    """Drop the first leaf that the happy patient would have included."""
    happy = _happy_payload(tree)
    if happy is None or not happy.codes:
        return None
    fewer = list(happy.codes)[1:]  # remove the first code
    return PatientPayload(
        codes=fewer,
        age=happy.age,
        sex=happy.sex,
        generation_source="generated",
    )


def _collect_demographic(tree: dict) -> tuple[float | None, str | None]:
    """Walk the tree and return midpoint age + first sex constraint."""
    age, sex = None, None
    for node in _iter(tree):
        if str(node.get("kind") or "").upper() != "DEMOGRAPHIC":
            continue
        field = str(node.get("field") or "").lower()
        operator = str(node.get("operator") or "").lower()
        value = node.get("value")
        if field == "age" and value is not None:
            try:
                target = float(value)
            except (TypeError, ValueError):
                continue
            if operator in (">=", "gte"):
                age = target
            elif operator in (">", "gt"):
                age = target + 1
            elif operator in ("<=", "lte"):
                age = max(0.0, target)
            elif operator in ("<", "lt"):
                age = max(0.0, target - 1)
            else:
                age = target
        if field == "sex" and value is not None:
            sex = str(value).lower()
    return age, sex


def _top_level_or_branches(tree: dict) -> list[dict]:
    """Return the immediate children of the top-level OR (if any)."""
    if not isinstance(tree, dict):
        return []
    kind = str(tree.get("kind") or "").upper()
    if kind == "OR":
        return [c for c in (tree.get("children") or []) if isinstance(c, dict)]
    # Common shape: top-level AND wrapping a single OR.
    if kind == "AND":
        for child in tree.get("children") or []:
            if isinstance(child, dict) and str(child.get("kind") or "").upper() == "OR":
                return [
                    c for c in (child.get("children") or []) if isinstance(c, dict)
                ]
    return []


def _boundary_proposals(
    tree: dict, rule_id: str, rule_name: str, guideline_id: str
) -> list[Proposal]:
    """Emit age boundary patients for every age DEMOGRAPHIC node."""
    out: list[Proposal] = []
    base = _happy_payload(tree)
    if base is None:
        return out
    for node in _iter(tree):
        if str(node.get("kind") or "").upper() != "DEMOGRAPHIC":
            continue
        if str(node.get("field") or "").lower() != "age":
            continue
        try:
            target = float(node.get("value"))
        except (TypeError, ValueError):
            continue
        for offset, label in ((0.0, "at boundary"), (-1.0, "just below boundary")):
            payload = PatientPayload(
                codes=list(base.codes),
                age=max(0.0, target + offset),
                sex=base.sex,
                generation_source="generated",
            )
            out.append(
                _make(
                    payload,
                    rule_id,
                    rule_name,
                    guideline_id,
                    "boundary",
                    f"Age {payload.age} ({label} of {target})",
                )
            )
    return out


def _iter(node: Any):
    """Pre-order traversal of every dict node in the tree."""
    if isinstance(node, dict):
        yield node
        for child in node.get("children") or []:
            yield from _iter(child)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse(value: Any) -> dict | None:
    if not value:
        return None
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _make(
    payload: PatientPayload,
    rule_id: str,
    rule_name: str,
    guideline_id: str,
    kind: str,
    rationale: str,
) -> Proposal:
    payload.name = payload.name or _derive_name(rule_name, kind)
    payload.description = payload.description or rationale
    return Proposal(
        payload=payload,
        rule_id=rule_id,
        rule_name=rule_name,
        guideline_id=guideline_id,
        kind=kind,  # type: ignore[arg-type]
        rationale=rationale,
    )


def _derive_name(rule_name: str, kind: str) -> str:
    short = (rule_name or "rule")[:32].strip()
    label = {
        "happy": "Happy",
        "fail": "Fail",
        "branch": "Branch",
        "boundary": "Boundary",
    }.get(kind, kind.title())
    return f"{label} -- {short}"


def _dedup(
    client: CodingGraphClient, proposals: list[Proposal]
) -> list[Proposal]:
    """Drop proposals whose content_hash already exists in their guideline."""
    out: list[Proposal] = []
    seen_local: set[tuple[str, str]] = set()
    for prop in proposals:
        chash = prop.payload.content_hash()
        key = (prop.guideline_id, chash)
        if key in seen_local:
            continue
        seen_local.add(key)
        if prop.guideline_id and find_existing(
            client, guideline_id=prop.guideline_id, content_hash=chash
        ):
            continue
        out.append(prop)
    return out
