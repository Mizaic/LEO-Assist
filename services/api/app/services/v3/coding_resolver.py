"""Hybrid SNOMED/Read code resolution for extracted terms.

Resolution runs three retrieval branches in parallel per term, then
normalises and fuses scores to produce a ranked candidate list:

1. **Exact** — normalized-form equality on ``Term.normalized_form``.
2. **Fulltext** — Lucene ``term_fulltext`` index with escaped + AND-token queries.
3. **Vector** — cosine similarity on ``term_embedding_idx`` (when embeddings are
   available).

Scores from each branch are min-max normalised independently, then fused
with configurable weights (default 0.6 lexical / 0.4 vector).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Sequence

from app.services.term_patcher import normalize_surface

logger = logging.getLogger(__name__)

# Semantic-tag groups for reranking: tags within the same group are compatible
_TAG_GROUPS: dict[str, str] = {
    "disorder": "clinical",
    "finding": "clinical",
    "situation": "clinical",
    "substance": "pharma",
    "product": "pharma",
    "regime/therapy": "pharma",
    "procedure": "procedure",
    "observable entity": "observable",
    "body structure": "anatomy",
    "organism": "organism",
    "qualifier value": "qualifier",
    "attribute": "qualifier",
}

_TAG_BOOST = 1.3
_TAG_COMPAT_BOOST = 1.1
_TAG_PENALTY = 0.5

# ── Lucene helpers ────────────────────────────────────────────
_LUCENE_SPECIAL = re.compile(r'([+\-!(){}[\]^"~*?:\\/])')
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _escape_lucene(text: str) -> str:
    return _LUCENE_SPECIAL.sub(r"\\\1", text)


def _build_fulltext_queries(mention: str) -> list[str]:
    cleaned = mention.strip()
    if not cleaned:
        return []
    escaped = _escape_lucene(cleaned)
    tokens = _TOKEN_RE.findall(cleaned.lower())
    queries: list[str] = []
    if len(tokens) > 1:
        queries.append(f'"{escaped}"')
    queries.append(escaped)
    token_q = " AND ".join(tokens)
    if token_q and token_q != escaped:
        queries.append(token_q)
    return queries


# ── Cypher queries ────────────────────────────────────────────
_EXACT_QUERY = """
MATCH (t:Term {normalized_form: $normalized})-[:DESCRIBES]->(c:Concept)
WHERE c.active = true
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
WITH c, collect(DISTINCT rd.code) AS read_codes
RETURN c.id AS concept_id, c.fsn AS fsn, c.semantic_tag AS semantic_tag,
       read_codes, 1.0 AS score
LIMIT $k
"""

_EXACT_SURFACE_FORM_QUERY = """
MATCH (sf:SurfaceForm {normalized: $normalized})-[:MAPS_TO]->(c:Concept)
WHERE c.active = true
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
WITH c, collect(DISTINCT rd.code) AS read_codes
RETURN c.id AS concept_id, c.fsn AS fsn, c.semantic_tag AS semantic_tag,
       read_codes, 1.2 AS score
LIMIT $k
"""

_FULLTEXT_QUERY = """
CALL db.index.fulltext.queryNodes("term_fulltext", $ft_query) YIELD node, score
MATCH (node)-[:DESCRIBES]->(c:Concept)
WHERE c.active = true
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
WITH c, max(score) AS best_score, collect(DISTINCT rd.code) AS read_codes
RETURN c.id AS concept_id, c.fsn AS fsn, c.semantic_tag AS semantic_tag,
       read_codes, best_score AS score
ORDER BY best_score DESC
LIMIT $k
"""

_FULLTEXT_SURFACE_FORM_QUERY = """
CALL db.index.fulltext.queryNodes("surface_form_fulltext", $ft_query) YIELD node, score
MATCH (node)-[:MAPS_TO]->(c:Concept)
WHERE c.active = true
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
WITH c, max(score) AS best_score, collect(DISTINCT rd.code) AS read_codes
RETURN c.id AS concept_id, c.fsn AS fsn, c.semantic_tag AS semantic_tag,
       read_codes, best_score * 1.2 AS score
ORDER BY best_score DESC
LIMIT $k
"""

_VECTOR_QUERY = """
CALL db.index.vector.queryNodes($index_name, $k, $embedding) YIELD node, score
MATCH (node)-[:DESCRIBES]->(c:Concept)
WHERE c.active = true
OPTIONAL MATCH (c)-[:MAPS_TO_READ]->(rd:ReadCode)
WITH c, max(score) AS best_score, collect(DISTINCT rd.code) AS read_codes
RETURN c.id AS concept_id, c.fsn AS fsn, c.semantic_tag AS semantic_tag,
       read_codes, best_score AS score
ORDER BY best_score DESC
LIMIT $k
"""

_READ_CODE_QUERY = """
MATCH (rd:ReadCode {code: $read_code})<-[:MAPS_TO_READ]-(c:Concept)
WHERE c.active = true
RETURN c.id AS concept_id, c.fsn AS fsn
LIMIT 1
"""


@dataclass(frozen=True)
class CodingCandidate:
    snomed_concept_id: str | None
    snomed_term: str | None
    read_code: str | None
    score: float
    source: str


class CodingResolver:
    """Hybrid term → SNOMED resolver using exact + fulltext + vector retrieval."""

    def __init__(
        self,
        *,
        k_exact: int = 30,
        k_fulltext: int = 40,
        k_vector: int = 40,
        w_lexical: float = 0.6,
        w_vector: float = 0.4,
        vector_index_name: str = "term_embedding_idx",
        embedder: Any | None = None,
    ) -> None:
        self.k_exact = k_exact
        self.k_fulltext = k_fulltext
        self.k_vector = k_vector
        self.w_lexical = w_lexical
        self.w_vector = w_vector
        self.vector_index_name = vector_index_name
        self._embedder = embedder
        self._vector_index_ok: bool | None = None  # None = not yet probed
        self._surface_form_fulltext_ok: bool | None = None
        self._surface_form_exact_ok: bool | None = None  # None = not yet probed

    # ── Public API ────────────────────────────────────────────

    def resolve_candidates(
        self,
        term_texts: list[str],
        *,
        neo4j_session,
        expected_tags: dict[str, str] | None = None,
    ) -> dict[str, list[CodingCandidate]]:
        if not term_texts:
            return {}

        unique_texts = list(dict.fromkeys(term_texts))
        embeddings = self._embed(unique_texts)

        results: dict[str, list[CodingCandidate]] = {}
        for idx, text in enumerate(unique_texts):
            embedding = embeddings[idx] if embeddings else None
            tag = (expected_tags or {}).get(text)
            results[text] = self._resolve_single(
                text, neo4j_session, embedding, expected_tag=tag,
            )

        resolved = sum(1 for v in results.values() if v)
        branches = "exact+fulltext"
        if self._vector_index_ok:
            branches += "+vector"
        logger.info(
            "Hybrid resolution (%s): %d/%d terms resolved",
            branches, resolved, len(unique_texts),
        )

        out: dict[str, list[CodingCandidate]] = {}
        for text in term_texts:
            out[text] = results.get(text, [])
        return out

    # ── Internals ─────────────────────────────────────────────

    def _embed(self, texts: Sequence[str]) -> list[list[float]] | None:
        if not self._embedder:
            return None
        try:
            return self._embedder.encode(texts)
        except RuntimeError as exc:
            if "interpreter shutdown" in str(exc).lower():
                logger.warning(
                    "Embedding model load failed (interpreter shutdown) - vector branch disabled"
                )
            else:
                logger.warning("Embedding failed - vector branch disabled", exc_info=True)
            return None
        except Exception:
            logger.warning("Embedding failed - vector branch disabled", exc_info=True)
            return None

    def _resolve_single(
        self,
        mention: str,
        session,
        embedding: list[float] | None,
        expected_tag: str | None = None,
    ) -> list[CodingCandidate]:
        normalized = normalize_surface(mention)
        merged: dict[str, dict[str, Any]] = {}

        def push(rec: dict[str, Any], branch: str) -> None:
            cid = rec.get("concept_id")
            if not cid:
                return
            cid = str(cid)
            base = merged.setdefault(
                cid,
                {
                    "concept_id": cid,
                    "fsn": rec.get("fsn"),
                    "semantic_tag": rec.get("semantic_tag"),
                    "read_codes": sorted(set(rec.get("read_codes") or [])),
                    "lexical_raw": 0.0,
                    "vector_raw": 0.0,
                },
            )
            score = float(rec.get("score", 0.0))
            if branch == "lexical":
                base["lexical_raw"] = max(base["lexical_raw"], score)
            elif branch == "vector":
                base["vector_raw"] = max(base["vector_raw"], score)

        # Branch 1: exact match (Term + SurfaceForm)
        if normalized:
            for rec in session.run(_EXACT_QUERY, normalized=normalized, k=self.k_exact):
                push(dict(rec), "lexical")
            if self._surface_form_exact_ok is not False:
                try:
                    if self._surface_form_exact_ok is None:
                        # Probe: SurfaceForm schema may not be loaded
                        probe = list(session.run(
                            "CALL db.labels() YIELD label WHERE label = 'SurfaceForm' RETURN 1 AS ok LIMIT 1"
                        ))
                        self._surface_form_exact_ok = bool(probe)
                        if not self._surface_form_exact_ok:
                            logger.info(
                                "SurfaceForm label not found - surface form branches disabled"
                            )
                            self._surface_form_fulltext_ok = False
                    if self._surface_form_exact_ok:
                        for rec in session.run(
                            _EXACT_SURFACE_FORM_QUERY, normalized=normalized, k=self.k_exact
                        ):
                            push(dict(rec), "lexical")
                except Exception:
                    self._surface_form_exact_ok = False

        # Branch 2: fulltext (Term + SurfaceForm)
        for ft_query in _build_fulltext_queries(mention):
            try:
                for rec in session.run(_FULLTEXT_QUERY, ft_query=ft_query, k=self.k_fulltext):
                    push(dict(rec), "lexical")
            except Exception:
                continue
            if self._surface_form_fulltext_ok is not False:
                try:
                    for rec in session.run(_FULLTEXT_SURFACE_FORM_QUERY, ft_query=ft_query, k=self.k_fulltext):
                        push(dict(rec), "lexical")
                    if self._surface_form_fulltext_ok is None:
                        self._surface_form_fulltext_ok = True
                except Exception as exc:
                    if "no such fulltext schema index" in str(exc).lower():
                        self._surface_form_fulltext_ok = False
                        logger.info(
                            "SurfaceForm fulltext index not found - "
                            "surface form fulltext branch disabled for this session"
                        )
                    # Other errors silently ignored for this optional branch

        # Branch 3: vector (skip if index was already found missing)
        if embedding and self._vector_index_ok is not False:
            try:
                for rec in session.run(
                    _VECTOR_QUERY,
                    index_name=self.vector_index_name,
                    k=self.k_vector,
                    embedding=embedding,
                ):
                    push(dict(rec), "vector")
                if self._vector_index_ok is None:
                    self._vector_index_ok = True
                    logger.info("Vector index '%s' is available", self.vector_index_name)
            except Exception as exc:
                if "no such vector schema index" in str(exc).lower():
                    self._vector_index_ok = False
                    logger.warning(
                        "Vector index '%s' not found in Neo4j - "
                        "vector branch disabled for this session. "
                        "Run the terminology loader to create it.",
                        self.vector_index_name,
                    )
                else:
                    logger.warning("Vector query failed for %r: %s", mention, exc)

        if not merged:
            return []

        # Normalise and fuse scores
        max_lex = max(v["lexical_raw"] for v in merged.values()) or 1.0
        max_vec = max(v["vector_raw"] for v in merged.values()) or 1.0

        expected_group = _TAG_GROUPS.get(expected_tag, "") if expected_tag else ""

        scored: list[tuple[float, dict[str, Any]]] = []
        for c in merged.values():
            lex_norm = c["lexical_raw"] / max_lex if max_lex else 0.0
            vec_norm = c["vector_raw"] / max_vec if max_vec else 0.0
            fused = (self.w_lexical * lex_norm) + (self.w_vector * vec_norm)

            if expected_tag:
                candidate_tag = (c.get("semantic_tag") or "").lower()
                candidate_group = _TAG_GROUPS.get(candidate_tag, "")
                if candidate_tag == expected_tag:
                    fused *= _TAG_BOOST
                elif candidate_group and candidate_group == expected_group:
                    fused *= _TAG_COMPAT_BOOST
                elif candidate_group and candidate_group != expected_group:
                    fused *= _TAG_PENALTY

            scored.append((fused, c))

        scored.sort(key=lambda x: x[0], reverse=True)

        return [
            CodingCandidate(
                snomed_concept_id=c["concept_id"],
                snomed_term=c.get("fsn"),
                read_code=(c.get("read_codes") or [None])[0],
                score=round(fused, 4),
                source="hybrid",
            )
            for fused, c in scored
        ]

    def resolve_read_code(
        self,
        read_code: str,
        *,
        neo4j_session,
    ) -> CodingCandidate | None:
        """Resolve a Read/CTV3 code to a SNOMED concept. Returns None if not found."""
        if not read_code or not read_code.strip():
            return None
        try:
            result = neo4j_session.run(_READ_CODE_QUERY, read_code=read_code.strip())
            row = result.single()
            if not row:
                return None
            return CodingCandidate(
                snomed_concept_id=str(row["concept_id"]),
                snomed_term=row.get("fsn"),
                read_code=read_code.strip(),
                score=0.95,
                source="inline_read_code",
            )
        except Exception:
            return None
