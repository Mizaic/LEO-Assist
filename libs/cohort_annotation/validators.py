"""Validators for annotation output.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

Four hard checks applied to every entity and relation:
1. Verbatim quote alignment -- quote must be a case-sensitive substring of
   the indicated sentence.
2. Label schema check -- every label must be in VALID_LABELS.
3. Assertion enum check -- assertion must be in VALID_ASSERTIONS.
4. Nested-start invariant -- for a set of entities sharing the same sentence
   and the same lead quote prefix, their start positions must be equal (i.e.
   PROCEDURE, OBSERVABLE_ENTITY, FINDING all start at the same char offset
   in the sentence text).
5. Relation policy check -- every relation must satisfy
   libs.relations.policy.is_relation_allowed.

Entities that fail are moved to qa_drops; relations that fail are removed.
Returns (clean_entities, clean_relations, qa_drops).
"""

from __future__ import annotations

from typing import Any

from libs.cohort_annotation.state import (
    VALID_ASSERTIONS,
    VALID_LABELS,
    VALID_RELATION_TYPES,
)
from libs.relations.policy import is_relation_allowed


def _sentence_text(
    sentences: list[dict[str, Any]],
    sentence_id: int,
) -> str | None:
    for s in sentences:
        if s.get("sentence_id") == sentence_id:
            return s.get("text")
    return None


def _labels_of(e: dict[str, Any]) -> list[str]:
    return [l.upper() for l in (e.get("labels") or [])]


def _first_label(e: dict[str, Any]) -> str:
    lbls = _labels_of(e)
    return lbls[0] if lbls else ""


def validate_entities(
    entities: list[dict[str, Any]],
    sentences: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (clean_entities, qa_drops)."""
    clean: list[dict[str, Any]] = []
    drops: list[dict[str, Any]] = []

    for e in entities:
        eid = e.get("id", "?")
        sid = e.get("sentence_id")
        quote = e.get("quote") or ""
        labels = _labels_of(e)
        assertion = (e.get("assertion") or "present").lower().strip()

        # 1. Quote must be non-empty
        if not quote.strip():
            drops.append({"entity_id": eid, "reason": "empty_quote", "entity": e})
            continue

        # 2. Label schema check
        bad_labels = [l for l in labels if l not in VALID_LABELS]
        if bad_labels:
            drops.append({
                "entity_id": eid,
                "reason": f"invalid_label:{','.join(bad_labels)}",
                "entity": e,
            })
            continue

        # 3. Assertion enum check
        if assertion not in VALID_ASSERTIONS:
            drops.append({
                "entity_id": eid,
                "reason": f"invalid_assertion:{assertion}",
                "entity": e,
            })
            continue

        # 4. Verbatim quote alignment
        if sid is not None:
            sent_text = _sentence_text(sentences, sid)
            if sent_text is not None and quote not in sent_text:
                drops.append({
                    "entity_id": eid,
                    "reason": "quote_not_found_in_sentence",
                    "entity": e,
                })
                continue

        clean.append(e)

    return clean, drops


def _get_start_in_sentence(
    sentence_text: str,
    quote: str,
) -> int | None:
    idx = sentence_text.find(quote)
    return idx if idx >= 0 else None


def validate_nested_start_invariant(
    entities: list[dict[str, Any]],
    sentences: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Reject lab/vitals triple sets where spans don't share the same start.

    Groups entities by (sentence_id, leading_quote_prefix). The prefix is the
    shorter PROCEDURE quote for the group. If any co-member has a different
    start position, the whole group is added to drops except the PROCEDURE.
    """
    clean: list[dict[str, Any]] = []
    drops: list[dict[str, Any]] = []

    from collections import defaultdict

    # group by sentence_id
    by_sid: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for e in entities:
        sid = e.get("sentence_id")
        if sid is not None:
            by_sid[sid].append(e)
        else:
            clean.append(e)

    for sid, ents in by_sid.items():
        sent_text = _sentence_text(sentences, sid)
        if sent_text is None:
            clean.extend(ents)
            continue

        # Find PROCEDURE entities as anchor points
        procs = [e for e in ents if "PROCEDURE" in _labels_of(e)]
        grouped_ids: set[str] = set()

        for proc in procs:
            proc_q = proc.get("quote") or ""
            proc_start = _get_start_in_sentence(sent_text, proc_q)
            if proc_start is None:
                continue
            # Find other entities whose quote starts with proc_q
            group = [
                e for e in ents
                if (e.get("quote") or "").startswith(proc_q) and e is not proc
            ]
            if not group:
                continue
            bad = False
            for member in group:
                mem_q = member.get("quote") or ""
                mem_start = _get_start_in_sentence(sent_text, mem_q)
                if mem_start is not None and mem_start != proc_start:
                    bad = True
                    drops.append({
                        "entity_id": member.get("id", "?"),
                        "reason": "nested_start_invariant_violation",
                        "entity": member,
                    })
                    grouped_ids.add(member.get("id", ""))
            if bad:
                drops.append({
                    "entity_id": proc.get("id", "?"),
                    "reason": "nested_start_invariant_violation_anchor",
                    "entity": proc,
                })
                grouped_ids.add(proc.get("id", ""))
            else:
                for m in group:
                    grouped_ids.add(m.get("id", ""))
                grouped_ids.add(proc.get("id", ""))

        for e in ents:
            if e.get("id", "") not in grouped_ids:
                clean.append(e)

    return clean, drops


def validate_relations(
    relations: list[dict[str, Any]],
    entities: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (clean_relations, dropped_relations).

    Checks:
    - head_id and tail_id must reference existing entity ids.
    - relation type must be in VALID_RELATION_TYPES.
    - source/target labels must satisfy policy.
    """
    entity_map: dict[str, dict[str, Any]] = {
        e.get("id", ""): e for e in entities if e.get("id")
    }
    clean: list[dict[str, Any]] = []
    drops: list[dict[str, Any]] = []

    for r in relations:
        rel_type = (r.get("type") or "").lower().strip()
        head_id = r.get("head_id", "")
        tail_id = r.get("tail_id", "")

        if rel_type not in VALID_RELATION_TYPES:
            drops.append({"relation": r, "reason": f"invalid_type:{rel_type}"})
            continue

        head = entity_map.get(head_id)
        tail = entity_map.get(tail_id)
        if head is None:
            drops.append({"relation": r, "reason": f"head_not_found:{head_id}"})
            continue
        if tail is None:
            drops.append({"relation": r, "reason": f"tail_not_found:{tail_id}"})
            continue

        head_label = _first_label(head).lower()
        tail_label = _first_label(tail).lower()

        allowed, _ = is_relation_allowed(
            source_label=head_label,
            target_label=tail_label,
            relation_type=rel_type,
        )
        if not allowed:
            drops.append({
                "relation": r,
                "reason": f"policy_violation:{head_label}-{rel_type}->{tail_label}",
            })
            continue

        clean.append(r)

    return clean, drops


def run_all_validators(
    entities: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    sentences: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Run all validators. Returns (entities, relations, qa_drops)."""
    entities, drops1 = validate_entities(entities, sentences)
    entities, drops2 = validate_nested_start_invariant(entities, sentences)
    relations, rel_drops = validate_relations(relations, entities)
    all_drops = drops1 + drops2 + [{"relation": d["relation"], "reason": d["reason"]} for d in rel_drops]
    return entities, relations, all_drops
