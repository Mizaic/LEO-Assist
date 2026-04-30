"""Deterministic relation closure (R16d + simple finding_site heuristics).

R16d: for every lab/vitals triple on the same sentence, emit:
    FINDING  -interprets->   OBSERVABLE_ENTITY
    OBSERVABLE_ENTITY -component_of-> PROCEDURE

Simple finding_site: for constructions like "X in Y" / "Y X" where X is
a FINDING and Y is a BODY_STRUCTURE on the same sentence, emit
    FINDING -finding_site-> BODY_STRUCTURE

Returns a list of relation dicts:
    {
        "head_id":   "e3",
        "tail_id":   "e2",
        "type":      "interprets",
        "confidence": 0.99,
        "rationale": "R16d deterministic",
        "source":    "deterministic",
    }

The LLM RelationLinker handles the harder cases
(finding_site for non-trivial constructions, associated_finding, qualifies).
"""

from __future__ import annotations

import re
from typing import Any

from libs.relations.policy import is_relation_allowed

# Body-structure prepositions that support finding_site
_IN_PREP_RE = re.compile(
    r"\b(?:in|at|of|on|involving|affecting)\s+the\b",
    re.IGNORECASE,
)


def _labels_of(e: dict[str, Any]) -> frozenset[str]:
    return frozenset(l.upper() for l in (e.get("labels") or []))


def _sid(e: dict[str, Any]) -> int | None:
    return e.get("sentence_id")


def _quote(e: dict[str, Any]) -> str:
    return (e.get("quote") or "").strip()


def _rel(
    head_id: str,
    tail_id: str,
    rel_type: str,
    confidence: float,
    rationale: str,
) -> dict[str, Any]:
    return {
        "head_id":    head_id,
        "tail_id":    tail_id,
        "type":       rel_type,
        "confidence": confidence,
        "rationale":  rationale,
        "source":     "deterministic",
    }


def _r16d_relations(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Emit interprets + component_of for co-located lab/vitals triples."""
    relations: list[dict[str, Any]] = []

    # Group by sentence_id
    by_sid: dict[int | None, list[dict[str, Any]]] = {}
    for e in entities:
        by_sid.setdefault(_sid(e), []).append(e)

    for sid, ents in by_sid.items():
        procs  = [e for e in ents if "PROCEDURE"        in _labels_of(e)]
        obs    = [e for e in ents if "OBSERVABLE_ENTITY" in _labels_of(e)]
        finds  = [e for e in ents if "FINDING"           in _labels_of(e)]

        # Only apply R16d when all three come from the same starting quote
        # (shared-start invariant). Group by common prefix.
        for proc in procs:
            proc_q = _quote(proc)
            matching_obs = [
                o for o in obs
                if _quote(o).startswith(proc_q)
            ]
            matching_finds = [
                f for f in finds
                if _quote(f).startswith(proc_q)
            ]

            for o in matching_obs:
                allowed, _ = is_relation_allowed(
                    source_label="observable_entity",
                    target_label="procedure",
                    relation_type="component_of",
                )
                if allowed:
                    relations.append(_rel(
                        o["id"], proc["id"],
                        "component_of", 0.99,
                        "R16d deterministic component_of",
                    ))

            for f in matching_finds:
                for o in matching_obs:
                    if _quote(f).startswith(_quote(o)):
                        allowed, _ = is_relation_allowed(
                            source_label="finding",
                            target_label="observable_entity",
                            relation_type="interprets",
                        )
                        if allowed:
                            relations.append(_rel(
                                f["id"], o["id"],
                                "interprets", 0.99,
                                "R16d deterministic interprets",
                            ))
                            break

    return relations


def _simple_finding_site_relations(
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Emit finding_site for unambiguous 'finding in body_structure' phrases.

    Only cases where the body_structure quote appears inside the finding
    quote AND they share the same sentence_id.
    """
    relations: list[dict[str, Any]] = []
    by_sid: dict[int | None, list[dict[str, Any]]] = {}
    for e in entities:
        by_sid.setdefault(_sid(e), []).append(e)

    for sid, ents in by_sid.items():
        finds  = [e for e in ents if "FINDING"        in _labels_of(e)]
        bodies = [e for e in ents if "BODY_STRUCTURE" in _labels_of(e)]
        if not finds or not bodies:
            continue
        for f in finds:
            fq = _quote(f).lower()
            for b in bodies:
                bq = _quote(b).lower()
                if not bq or bq not in fq:
                    continue
                # Check that body quote appears after a prep or directly after name
                pos = fq.find(bq)
                prefix = fq[:pos]
                if _IN_PREP_RE.search(prefix) or pos == 0:
                    allowed, _ = is_relation_allowed(
                        source_label="finding",
                        target_label="body_structure",
                        relation_type="finding_site",
                    )
                    if allowed:
                        relations.append(_rel(
                            f["id"], b["id"],
                            "finding_site", 0.90,
                            "deterministic finding_site (body_structure in finding quote)",
                        ))

    return relations


def add_deterministic_relations(
    entities: list[dict[str, Any]],
    existing_relations: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return existing_relations plus all deterministic R16d + site relations.

    Deduplicates by (head_id, tail_id, type).
    """
    base = list(existing_relations or [])
    new = _r16d_relations(entities) + _simple_finding_site_relations(entities)

    seen: set[tuple[str, str, str]] = set()
    for r in base:
        seen.add((r.get("head_id", ""), r.get("tail_id", ""), r.get("type", "")))

    for r in new:
        key = (r.get("head_id", ""), r.get("tail_id", ""), r.get("type", ""))
        if key not in seen:
            base.append(r)
            seen.add(key)

    return base


def needs_llm_relation_pass(entities: list[dict[str, Any]]) -> bool:
    """Return True if there are FINDING+BODY_STRUCTURE or QUALIFIER+target pairs
    that the LLM relation linker should reason about."""
    labels_all = set()
    for e in entities:
        labels_all.update(_labels_of(e))
    if "FINDING" in labels_all and "BODY_STRUCTURE" in labels_all:
        return True
    if "QUALIFIER_VALUE" in labels_all:
        return True
    if "FINDING" in labels_all and (
        "DISORDER" in labels_all or "PROCEDURE" in labels_all
    ):
        return True
    return False
