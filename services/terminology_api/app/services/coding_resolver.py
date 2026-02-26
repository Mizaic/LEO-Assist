"""Hybrid SNOMED/Read code resolution.

Ported from PCA services/api/app/services/v3/coding_resolver.py.
Runs three retrieval branches (exact, fulltext, vector) and fuses scores.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Sequence

from services.terminology_api.app.queries.terminology import (
    EXACT_QUERY,
    EXACT_SURFACE_FORM_QUERY,
    FULLTEXT_QUERY,
    FULLTEXT_SURFACE_FORM_QUERY,
    VECTOR_QUERY,
)

logger = logging.getLogger(__name__)

TAG_GROUPS: dict[str, str] = {
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

_LUCENE_SPECIAL = re.compile(r'([+\-!(){}[\]^"~*?:\\/])')
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def normalize_surface(text: str) -> str:
    return " ".join(_TOKEN_RE.findall(text.lower()))


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


@dataclass(frozen=True)
class CodingCandidate:
    snomed_concept_id: str | None
    snomed_term: str | None
    read_code: str | None
    score: float
    source: str


class CodingResolver:
    """Hybrid term -> SNOMED resolver using exact + fulltext + vector retrieval."""

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
        self._vector_index_ok: bool | None = None
        self._surface_form_fulltext_ok: bool | None = None
        self._surface_form_exact_ok: bool | None = None

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
            results[text] = self._resolve_single(text, neo4j_session, embedding, expected_tag=tag)

        resolved = sum(1 for v in results.values() if v)
        branches = "exact+fulltext"
        if self._vector_index_ok:
            branches += "+vector"
        logger.info("Hybrid resolution (%s): %d/%d terms resolved", branches, resolved, len(unique_texts))

        return {text: results.get(text, []) for text in term_texts}

    def _embed(self, texts: Sequence[str]) -> list[list[float]] | None:
        if not self._embedder:
            return None
        try:
            return self._embedder.encode(texts)
        except Exception:
            logger.warning("Embedding failed — vector branch disabled", exc_info=True)
            return None

    def _resolve_single(
        self, mention: str, session, embedding: list[float] | None, expected_tag: str | None = None
    ) -> list[CodingCandidate]:
        normalized = normalize_surface(mention)
        merged: dict[str, dict[str, Any]] = {}

        def push(rec: dict[str, Any], branch: str) -> None:
            cid = rec.get("concept_id")
            if not cid:
                return
            cid = str(cid)
            base = merged.setdefault(cid, {
                "concept_id": cid,
                "fsn": rec.get("fsn"),
                "semantic_tag": rec.get("semantic_tag"),
                "read_codes": sorted(set(rec.get("read_codes") or [])),
                "lexical_raw": 0.0,
                "vector_raw": 0.0,
            })
            score = float(rec.get("score", 0.0))
            if branch == "lexical":
                base["lexical_raw"] = max(base["lexical_raw"], score)
            elif branch == "vector":
                base["vector_raw"] = max(base["vector_raw"], score)

        # Branch 1: exact
        if normalized:
            for rec in session.run(EXACT_QUERY, normalized=normalized, k=self.k_exact):
                push(dict(rec), "lexical")
            if self._surface_form_exact_ok is not False:
                try:
                    if self._surface_form_exact_ok is None:
                        probe = list(session.run(
                            "CALL db.labels() YIELD label WHERE label = 'SurfaceForm' RETURN 1 AS ok LIMIT 1"
                        ))
                        self._surface_form_exact_ok = bool(probe)
                        if not self._surface_form_exact_ok:
                            self._surface_form_fulltext_ok = False
                    if self._surface_form_exact_ok:
                        for rec in session.run(EXACT_SURFACE_FORM_QUERY, normalized=normalized, k=self.k_exact):
                            push(dict(rec), "lexical")
                except Exception:
                    self._surface_form_exact_ok = False

        # Branch 2: fulltext
        for ft_query in _build_fulltext_queries(mention):
            try:
                for rec in session.run(FULLTEXT_QUERY, ft_query=ft_query, k=self.k_fulltext):
                    push(dict(rec), "lexical")
            except Exception:
                continue
            if self._surface_form_fulltext_ok is not False:
                try:
                    for rec in session.run(FULLTEXT_SURFACE_FORM_QUERY, ft_query=ft_query, k=self.k_fulltext):
                        push(dict(rec), "lexical")
                    if self._surface_form_fulltext_ok is None:
                        self._surface_form_fulltext_ok = True
                except Exception as exc:
                    if "no such fulltext schema index" in str(exc).lower():
                        self._surface_form_fulltext_ok = False

        # Branch 3: vector
        if embedding and self._vector_index_ok is not False:
            try:
                for rec in session.run(
                    VECTOR_QUERY, index_name=self.vector_index_name, k=self.k_vector, embedding=embedding
                ):
                    push(dict(rec), "vector")
                if self._vector_index_ok is None:
                    self._vector_index_ok = True
            except Exception as exc:
                if "no such vector schema index" in str(exc).lower():
                    self._vector_index_ok = False

        if not merged:
            return []

        max_lex = max(v["lexical_raw"] for v in merged.values()) or 1.0
        max_vec = max(v["vector_raw"] for v in merged.values()) or 1.0
        expected_group = TAG_GROUPS.get(expected_tag, "") if expected_tag else ""

        scored: list[tuple[float, dict[str, Any]]] = []
        for c in merged.values():
            lex_norm = c["lexical_raw"] / max_lex if max_lex else 0.0
            vec_norm = c["vector_raw"] / max_vec if max_vec else 0.0
            fused = (self.w_lexical * lex_norm) + (self.w_vector * vec_norm)

            if expected_tag:
                candidate_tag = (c.get("semantic_tag") or "").lower()
                candidate_group = TAG_GROUPS.get(candidate_tag, "")
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
