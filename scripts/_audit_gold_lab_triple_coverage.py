#!/usr/bin/env python3
"""Audit existing GoldLabel coverage for long lab observation triples.

Answers: do we already have enough gold-labelled "Reticulocyte count
- observation (42X..) 96 10^9/L [20 - 80]"-style triples in Neo4j to
let the spancat model learn the long observable span natively after
the next training run, or do we need to seed more?

Counts, per GoldLabel that contains a procedure / observable_entity /
finding entity:

    - rows total
    - rows where the longest observable_entity exceeds 60 chars
    - rows where the longest observable_entity exceeds 100 chars
    - rows that contain ALL THREE (procedure + observable_entity +
      finding) co-occurring in the same label
    - rows whose text matches the production lab grammar

Run from repo root:

    .venv/bin/python scripts/_audit_gold_lab_triple_coverage.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(_REPO_ROOT / "secrets" / ".env.config")
load_dotenv(_REPO_ROOT / "secrets" / ".env.secrets")

from libs.neo4j_client.client import KnowledgeGraphClient


_LAB_GRAMMAR_RE = re.compile(
    r"(?P<name>[A-Za-z][\w \-/']{2,80})"
    r"(?:\s*\([0-9A-Za-z.]+\))?"
    r"\s*[:\-]?\s*"
    r"(?P<value>[<>]?\s*\d+(?:[.,]\d+)?)"
    r"\s*"
    r"(?P<unit>[%a-zA-Z][\w/\^\.\-]*)",
)


def _entities(label: dict[str, Any]) -> list[dict[str, Any]]:
    raw = label.get("entities_json") or "[]"
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        return [e for e in data if isinstance(e, dict)]
    return []


def _label_set(entities: list[dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for ent in entities:
        lab = str(ent.get("label", "")).strip().lower().replace(" ", "_")
        if lab:
            out.add(lab)
    return out


def _max_obs_len(entities: list[dict[str, Any]]) -> int:
    best = 0
    for ent in entities:
        if str(ent.get("label", "")).strip().lower().replace(" ", "_") != "observable_entity":
            continue
        text = str(ent.get("text", "") or "")
        if len(text) > best:
            best = len(text)
    return best


def _looks_like_lab(text: str) -> bool:
    if not text:
        return False
    return bool(_LAB_GRAMMAR_RE.search(text))


def main() -> int:
    client = KnowledgeGraphClient()
    cypher = """
    MATCH (g:GoldLabel)
    WHERE g.entities_json IS NOT NULL
    RETURN g.label_id AS label_id,
           g.text AS text,
           g.entities_json AS entities_json,
           g.source AS source
    """
    with client.session() as session:
        rows = [dict(r) for r in session.run(cypher)]

    total = len(rows)
    counts = Counter()
    obs_len_buckets = Counter()
    triple_rows: list[str] = []
    long_obs_examples: list[tuple[int, str, str]] = []

    for row in rows:
        ents = _entities(row)
        labels = _label_set(ents)
        text = str(row.get("text", "") or "")
        if "procedure" in labels:
            counts["has_procedure"] += 1
        if "observable_entity" in labels:
            counts["has_observable"] += 1
        if "finding" in labels:
            counts["has_finding"] += 1
        if {"procedure", "observable_entity", "finding"}.issubset(labels):
            counts["has_full_triple"] += 1
            if len(triple_rows) < 8:
                triple_rows.append(text[:160])
        if _looks_like_lab(text):
            counts["text_matches_lab_grammar"] += 1

        olen = _max_obs_len(ents)
        if olen > 0:
            if olen <= 30:
                obs_len_buckets["obs_len_<=30"] += 1
            elif olen <= 60:
                obs_len_buckets["obs_len_31-60"] += 1
            elif olen <= 100:
                obs_len_buckets["obs_len_61-100"] += 1
            else:
                obs_len_buckets["obs_len_>100"] += 1
            if olen > 60 and len(long_obs_examples) < 8:
                obs_text = next(
                    (
                        str(e.get("text", ""))
                        for e in ents
                        if str(e.get("label", "")).strip().lower().replace(" ", "_")
                        == "observable_entity"
                    ),
                    "",
                )
                long_obs_examples.append((olen, obs_text[:160], text[:160]))

    print(json.dumps({
        "total_gold_labels": total,
        "counts": dict(counts),
        "observable_text_length_buckets": dict(obs_len_buckets),
        "sample_full_triple_rows": triple_rows,
        "sample_long_observable_rows": [
            {"obs_len": ln, "obs_text": ot, "row_text": rt}
            for ln, ot, rt in long_obs_examples
        ],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
