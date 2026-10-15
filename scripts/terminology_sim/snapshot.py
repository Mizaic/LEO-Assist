"""Snapshot candidate pools for simulation cases from the knowledge graph.

Read-only. Runs the same fulltext variants and limits as the resolver
(200 index hits, best 40 concepts per variant and index), but keeps the
wording that matched, and always runs fulltext even after an exact hit so
the "hidden" view of a pool has data. Exact Term hits keep their
acceptability, and tied exact concepts keep which of them sit above the
others, read with the resolver's own ancestry step, so ties settle offline
exactly as they do in production.

Usage:
    python -m scripts.terminology_sim.snapshot CASES.json OUT.json.gz
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from libs.neo4j_client.client import KnowledgeGraphClient
from libs.terminology.client import _normalise_for_resolve
from libs.terminology.surface_normalize import normalize_surface
from scripts.terminology_sim.env import load_local_env
from scripts.terminology_sim.pool import Case, Hit, Pool, merged_for, save_pools
from services.terminology_api.app.queries.terminology import _ACCEPTABILITY_RANK
from services.terminology_api.app.services.coding_resolver import (
    _build_fulltext_queries,
)
from services.terminology_api.app.services.lookup_guards import annotate_ancestry

_K = 40
_BATCH = 25

_TERM_FT = """
UNWIND $queries AS q
CALL {
  WITH q
  CALL db.index.fulltext.queryNodes('term_fulltext', q) YIELD node, score
  WITH node, score LIMIT 200
  MATCH (node)-[:DESCRIBES]->(c:Concept) WHERE c.active = true
  WITH c, node, score ORDER BY score DESC
  WITH c, collect({t: node.surface_form, s: score})[0] AS best
  ORDER BY best.s DESC LIMIT $k
  RETURN collect({id: c.id, fsn: c.fsn, tag: c.semantic_tag,
                  matched: best.t, score: best.s}) AS hits
}
RETURN q, hits
"""

_SF_FT = """
UNWIND $queries AS q
CALL {
  WITH q
  CALL db.index.fulltext.queryNodes('surface_form_fulltext', q)
    YIELD node AS sf, score
  WITH sf, score LIMIT 200
  MATCH (sf)-[:MAPS_TO]->(c:Concept)
  WHERE c.active = true
    AND coalesce(sf.status, 'approved') IN ['approved', 'active']
    AND coalesce(c.is_local, false) = false
  WITH c, sf, score ORDER BY score DESC
  WITH c, collect({t: sf.form, s: score})[0] AS best
  ORDER BY best.s DESC LIMIT $k
  RETURN collect({id: c.id, fsn: c.fsn, tag: c.semantic_tag,
                  matched: best.t, score: best.s}) AS hits
}
RETURN q, hits
"""

_EXACT = """
UNWIND $norms AS norm
CALL {
  WITH norm
  OPTIONAL MATCH (t:Term {normalized_form: norm})-[d:DESCRIBES]->(c:Concept)
  WHERE c.active = true
  RETURN collect(DISTINCT {id: c.id, fsn: c.fsn, tag: c.semantic_tag,
                           matched: t.surface_form, index: 'term_exact',
                           acceptability_rank: __ACCEPTABILITY_RANK__}) AS th
}
CALL {
  WITH norm
  OPTIONAL MATCH (sf:SurfaceForm {normalized: norm})-[:MAPS_TO]->(c:Concept)
  WHERE c.active = true
    AND coalesce(sf.status, 'approved') IN ['approved', 'active']
    AND coalesce(c.is_local, false) = false
  RETURN collect(DISTINCT {id: c.id, fsn: c.fsn, tag: c.semantic_tag,
                           matched: sf.form, index: 'sf_exact'}) AS sh
}
RETURN norm, [x IN th + sh WHERE x.id IS NOT NULL] AS hits
""".replace("__ACCEPTABILITY_RANK__", _ACCEPTABILITY_RANK)


def _hits(rows: list[dict[str, Any]], index: str, variant: str) -> list[Hit]:
    return [
        Hit(
            concept_id=str(r["id"]),
            fsn=str(r.get("fsn") or ""),
            semantic_tag=str(r.get("tag") or ""),
            matched=str(r.get("matched") or ""),
            score=float(r.get("score") or 1.0),
            index=r.get("index") or index,
            variant=variant,
            acceptability_rank=int(r.get("acceptability_rank") or 0),
        )
        for r in rows
    ]


def _fulltext_by_query(session, queries: list[str]) -> dict[str, list[Hit]]:
    found: dict[str, list[Hit]] = {q: [] for q in queries}
    for start in range(0, len(queries), _BATCH):
        batch = queries[start : start + _BATCH]
        for cypher, index in ((_TERM_FT, "term"), (_SF_FT, "sf")):
            for rec in session.run(cypher, queries=batch, k=_K):
                found[rec["q"]].extend(_hits(rec["hits"] or [], index, rec["q"]))
    return found


def _exact_by_norm(session, norms: list[str]) -> dict[str, list[Hit]]:
    found: dict[str, list[Hit]] = {n: [] for n in norms}
    for start in range(0, len(norms), _BATCH):
        rows = session.run(_EXACT, norms=norms[start : start + _BATCH])
        for rec in rows:
            found[rec["norm"]] = _hits(rec["hits"] or [], "", "exact")
    return found


def snapshot(cases: list[Case], session) -> list[Pool]:
    phrases = {c.case_id: _normalise_for_resolve(c.phrase) for c in cases}
    variants = {cid: _build_fulltext_queries(p) for cid, p in phrases.items()}
    all_queries = sorted({q for qs in variants.values() for q in qs})
    norms = sorted({normalize_surface(p) for p in phrases.values() if p})
    by_query = _fulltext_by_query(session, all_queries)
    by_norm = _exact_by_norm(session, norms)
    pools = []
    for case in cases:
        phrase = phrases[case.case_id]
        fulltext = [h for q in variants[case.case_id] for h in by_query[q]]
        exact = by_norm.get(normalize_surface(phrase), []) if phrase else []
        pools.append(Pool(case=case, exact=exact, fulltext=fulltext))
    _add_tied_ancestors(pools, session)
    return pools


def _add_tied_ancestors(pools: list[Pool], session) -> None:
    merged = {p.case.case_id: merged_for(p) for p in pools if len(p.exact) > 1}
    annotate_ancestry(merged, session)
    for pool in pools:
        cands = merged.get(pool.case.case_id, {})
        if any(c.get("ancestry_failed") for c in cands.values()):
            raise RuntimeError(
                "tie ancestry lookup failed; pools would score a different rule"
            )
        pool.exact_ancestors = {
            cid: sorted(c["ancestor_ids"])
            for cid, c in cands.items()
            if c.get("ancestor_ids")
        }


def load_cases(path: Path) -> list[Case]:
    return [Case(**row) for row in json.loads(path.read_text(encoding="utf-8"))]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("cases", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args(argv)
    cases = load_cases(args.cases)
    load_local_env()
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            pools = snapshot(cases, session)
    finally:
        client.close()
    save_pools(args.out, pools)
    print(f"Wrote {len(pools)} pools to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
