"""Hybrid SNOMED/Read code resolution.

Ported from PCA services/api/app/services/v3/coding_resolver.py.
Runs three retrieval branches (exact, fulltext, vector) and fuses scores.

Batch optimization
~~~~~~~~~~~~~~~~~~
``resolve_candidates`` uses batched UNWIND queries so that resolving N terms
costs ~4 round trips to Neo4j regardless of N, instead of the previous
N × 8-12 sequential round trips.  The individual ``_resolve_single`` method
is preserved for backwards compatibility and single-term lookups.

Short-circuit
~~~~~~~~~~~~~
If a term is fully resolved by the exact branch (Term + SurfaceForm both
return results at score >= 1.0), the fulltext and vector branches are skipped
for that term, cutting 6-8 round trips per already-known term.

Lab-domain enrichment
~~~~~~~~~~~~~~~~~~~~~
When ``resolve_candidates`` resolves an entity to a concept whose semantic tag
is ``observable entity``, ``procedure``, or ``finding``, the resolver can
optionally traverse the SNOMED ontology family via ``get_related_concepts`` to
return the full cluster of related concepts (INTERPRETS / HAS_COMPONENT /
HAS_ASSOCIATED_FINDING edges materialised by the phase-3 loader).

This lets the pipeline emit compound lab entities (observable_entity +
qualifier_value + finding) without LLM disambiguation.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field, replace
from typing import Any, Sequence

from libs.terminology.surface_normalize import TOKEN_RE, normalize_surface
from services.terminology_api.app.queries.terminology import (
    BATCH_EXACT_QUERY,
    BATCH_FULLTEXT_QUERY,
    BATCH_RELATED_CONCEPTS_QUERY,
    EXACT_QUERY,
    EXACT_SURFACE_FORM_QUERY,
    FULLTEXT_QUERY,
    FULLTEXT_SURFACE_FORM_QUERY,
    RELATED_CONCEPTS_QUERY,
    VECTOR_QUERY,
    VECTOR_SURFACE_FORM_QUERY,
)

logger = logging.getLogger(__name__)

# Semantic tags that belong to the lab-domain observable/procedure/finding family.
# When a resolved concept carries one of these tags, the resolver can look up
# INTERPRETS / HAS_COMPONENT / HAS_ASSOCIATED_FINDING neighbours.
LAB_DOMAIN_TAGS: frozenset[str] = frozenset(
    {"observable entity", "procedure", "finding"}
)

TAG_GROUPS: dict[str, str] = {
    "disorder": "clinical",
    "finding": "clinical",
    "situation": "clinical",
    "substance": "pharma",
    "product": "pharma",
    "regime/therapy": "pharma",
    "medicinal product": "pharma",
    "clinical drug": "pharma",
    "procedure": "procedure",
    "observable entity": "observable",
    "assessment scale": "observable",
    "body structure": "anatomy",
    "physical object": "device",
    "organism": "organism",
    "qualifier value": "qualifier",
    "staging scale": "qualifier",
    "tumor staging": "qualifier",
    "attribute": "qualifier",
    "record artifact": "admin",
    "morphologic abnormality": "clinical",
    "occupation": "social",
    "environment": "social",
}

# Tag adjustment constants.
#
# Why additive boost (not multiplicative)?
# ----------------------------------------
# The previous implementation used a multiplicative boost (`fused *= 1.3`)
# which inflated weak fused scores. Combined with per-term local
# normalisation (top candidate always normalised to ~1.0), this produced
# misleading absolute scores: a term whose only candidate was a weak
# Lucene partial match could end up reporting score=1.3, looking
# indistinguishable from a curated SurfaceForm exact match.
#
# The additive boost preserves tag-matching as a tie-breaker (a candidate
# whose tag matches the LLM's expected tag wins over a same-confidence
# candidate whose tag does not), but does NOT distort the absolute
# confidence the score is meant to convey.
_TAG_EXACT_BOOST = 0.10
_TAG_PENALTY = 0.5

# Minimum calibrated score to include a candidate in results.
# This is a hard cull -- candidates below this confidence are almost
# certainly spurious fulltext token matches (e.g. one shared word out
# of a long phrase).
_MIN_SCORE = 0.15

# When both lexical and vector signals fire, the smaller signal earns a
# bonus on top of the larger signal. Keeps absolute interpretation
# (score is roughly P(correct mapping)) while rewarding agreement
# between two independent retrieval branches.
_AGREEMENT_BONUS = 0.10

# Tags that are never clinically meaningful as a primary coding result.
# These are hard-blocked when an expected clinical tag is provided,
# and soft-excluded (score floor raised to 0.5) even without an expected tag.
_NON_CLINICAL_TAGS: frozenset[str] = frozenset(
    {
        "qualifier value",
        "attribute",
        "staging scale",
        "tumor staging",
        "record artifact",
        "geographic location",
        "cell structure",
        "environment",
        "occupation",
        "organism",
        "physical object",
        "event",
        "namespace concept",
        "inactive concept",
        "special concept",
    }
)

# Clinical tag groups -- when an expected tag is one of these groups,
# hard-block any result whose tag is non-clinical.
_CLINICAL_GROUPS: frozenset[str] = frozenset(
    {
        "clinical",
        "pharma",
        "procedure",
        "observable",
        "anatomy",
    }
)

# Maximum number of tokens before we skip the raw (non-phrase) fulltext query.
# Long phrases produce dangerous partial word matches (e.g. "see" -> Holy See).
_MAX_TOKENS_FOR_RAW_QUERY = 5

_LUCENE_SPECIAL = re.compile(r'([+\-!(){}[\]^"~*?:\\/])')


def _normalise_semantic_tag(tag: str | None) -> str:
    if not tag:
        return ""
    return str(tag).strip().lower().replace("_", " ")


def _escape_lucene(text: str) -> str:
    return _LUCENE_SPECIAL.sub(r"\\\1", text)


def _build_fulltext_queries(mention: str) -> list[str]:
    cleaned = mention.strip()
    if not cleaned:
        return []
    escaped = _escape_lucene(cleaned)
    tokens = TOKEN_RE.findall(cleaned.lower())
    queries: list[str] = []

    # Phrase query (quoted) -- always included when more than one token.
    if len(tokens) > 1:
        queries.append(f'"{escaped}"')

    # Raw unquoted query -- safe only for short phrases.
    # Long phrases contain common words ("see", "recent", "with", etc.) that
    # produce dangerous partial matches against unrelated SNOMED concepts.
    if len(tokens) <= _MAX_TOKENS_FOR_RAW_QUERY:
        queries.append(escaped)

    # AND-token query -- only useful for short phrases (same reason).
    if len(tokens) <= _MAX_TOKENS_FOR_RAW_QUERY:
        token_q = " AND ".join(tokens)
        if token_q and token_q != escaped:
            queries.append(token_q)

    return queries


def _push(merged: dict[str, dict[str, Any]], rec: dict[str, Any], branch: str) -> None:
    """Merge one Neo4j result row into the per-term accumulator dict.

    Exact-branch hits are flagged via ``had_exact_match``: the exact
    queries assign a fixed score of 1.0 (Term) or 1.2 (SurfaceForm),
    so any lexical hit with score >= 1.0 came from the exact branch
    (fulltext Lucene scores below 1.0 are common; exact never returns
    less). Downstream consumers can use this flag to distinguish a
    rock-solid normalised-text match from a weak fulltext token hit.
    """
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
            "had_exact_match": False,
            "surface_form_status": "",
        },
    )
    sf_status = rec.get("surface_form_status") or ""
    if sf_status:
        base["surface_form_status"] = sf_status
    score = float(rec.get("score", 0.0))
    if branch == "lexical":
        base["lexical_raw"] = max(base["lexical_raw"], score)
    elif branch == "lexical_exact":
        base["lexical_raw"] = max(base["lexical_raw"], score)
        base["had_exact_match"] = True
    elif branch == "vector":
        base["vector_raw"] = max(base["vector_raw"], score)


def _has_lexical_candidates(merged: dict[str, dict[str, Any]]) -> bool:
    """Return True once exact/fulltext produced at least one candidate."""
    return any(
        float(candidate.get("lexical_raw", 0.0)) > 0.0 for candidate in merged.values()
    )


def _top_lexical_score(merged: dict[str, dict[str, Any]]) -> float:
    """Return the maximum raw lexical score across all current candidates."""
    if not merged:
        return 0.0
    return max(float(c.get("lexical_raw", 0.0)) for c in merged.values())


# Minimum top lexical score above which the vector branch is skipped.
# Set via TERMINOLOGY_VECTOR_SKIP_SCORE. Previously the vector branch was
# skipped whenever any lexical hit existed (score > 0), which caused weak
# partial-token matches (a chronic failure mode for multi-token phrases) to
# suppress the embedding branch entirely. A 0.7 threshold preserves the
# cost/latency win for unambiguous exact-match terms while ensuring hybrid
# retrieval actually runs when lexical is weak.
_DEFAULT_VECTOR_SKIP_SCORE = 0.7


def _vector_skip_score() -> float:
    try:
        value = float(os.getenv("TERMINOLOGY_VECTOR_SKIP_SCORE", ""))
    except (TypeError, ValueError):
        return _DEFAULT_VECTOR_SKIP_SCORE
    if value < 0.0 or value > 1.0:
        return _DEFAULT_VECTOR_SKIP_SCORE
    return value


def _parse_related_concepts_row(row: dict[str, Any]) -> list[dict[str, str]]:
    """Parse a RELATED_CONCEPTS_QUERY / BATCH_RELATED_CONCEPTS_QUERY row."""
    related: list[dict[str, str]] = []
    for key in (
        "interpreted_by_findings",
        "component_of_procedures",
        "interprets_observables",
        "has_components",
        "associated_findings",
    ):
        for item in row.get(key) or []:
            if item and item.get("id") and item.get("fsn"):
                related.append(
                    {
                        "id": str(item["id"]),
                        "fsn": str(item["fsn"]),
                        "semantic_tag": str(item.get("semantic_tag") or ""),
                        "rel": str(item.get("rel") or key),
                    }
                )
    return related


@dataclass(frozen=True)
class CodingCandidate:
    snomed_concept_id: str | None
    snomed_term: str | None
    semantic_tag: str | None
    read_code: str | None
    score: float
    source: str
    surface_form_status: str = ""
    # Absolute confidence signals (raw retrieval evidence).
    #
    # ``score`` above is now a CALIBRATED absolute confidence in
    # [0.0, 1.0] derived from these raw signals plus tag matching --
    # see ``_fuse_and_rank`` and ``_calibrate_confidence`` for the
    # exact mapping. Downstream consumers can use ``score`` directly
    # as a probability-like threshold. The raw signals are also
    # exposed so consumers that need to apply branch-specific
    # thresholds (e.g. "accept exact-match candidates only") can do
    # so without re-running the resolver.
    #
    #   had_exact_match -- True iff hit by the exact branch (Term or
    #     SurfaceForm). Strongest possible lexical signal short of a
    #     hand-curated mapping.
    #   lexical_raw    -- max raw lexical score across exact + fulltext
    #     branches. Exact = 1.0/1.2; fulltext = Lucene BM25-style
    #     (typically 0-15).
    #   vector_raw     -- cosine similarity from the embedding branch
    #     (0.0 - 1.0). >= 0.85 typically indicates strong semantic
    #     match even when token overlap is low.
    had_exact_match: bool = False
    lexical_raw: float = 0.0
    vector_raw: float = 0.0
    # For lab-domain concepts: family members discovered via SNOMED ontology edges
    # (INTERPRETS, HAS_COMPONENT, HAS_ASSOCIATED_FINDING).
    # Each entry: {"id", "fsn", "semantic_tag", "rel"}
    related_concepts: list[dict[str, str]] = field(default_factory=list)


def _calibrate_confidence(c: dict[str, Any]) -> float:
    """Compute calibrated absolute confidence in [0.0, 1.0] for one candidate.

    See ``CodingResolver._fuse_and_rank`` docstring for the full design
    rationale. Pulled out as a free function so tests and downstream
    consumers can replicate the calibration logic without instantiating
    a resolver.
    """
    if c.get("had_exact_match"):
        lex_signal = 1.0
    else:
        lex_raw = float(c.get("lexical_raw", 0.0) or 0.0)
        lex_signal = lex_raw / (lex_raw + 1.0) if lex_raw > 0 else 0.0
    vec_signal = float(c.get("vector_raw", 0.0) or 0.0)
    if vec_signal < 0.0:
        vec_signal = 0.0
    if vec_signal > 1.0:
        vec_signal = 1.0

    if lex_signal > 0.0 and vec_signal > 0.0:
        confidence = max(lex_signal, vec_signal) + (
            _AGREEMENT_BONUS * min(lex_signal, vec_signal)
        )
    else:
        confidence = max(lex_signal, vec_signal)
    return min(1.0, confidence)


def _apply_tag_adjustment(
    confidence: float,
    *,
    candidate_tag: str,
    expected_tag: str,
    expected_group: str,
) -> float:
    """Adjust calibrated confidence by tag match/mismatch.

    Exact tag match earns a small additive boost (+0.10, capped at 1.0)
    so tag-matching candidates win ties without inflating absolute
    confidence. Compatible group is neutral. Cross-group earns a
    multiplicative penalty (*0.5).
    """
    if not expected_tag:
        return confidence
    candidate_group = TAG_GROUPS.get(candidate_tag, "")
    if candidate_tag == expected_tag:
        return min(1.0, confidence + _TAG_EXACT_BOOST)
    if candidate_group and candidate_group == expected_group:
        return confidence
    if candidate_group and candidate_group != expected_group:
        return confidence * _TAG_PENALTY
    return confidence


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
        surface_form_vector_index_name: str = "surface_form_embedding_idx",
        embedder: Any | None = None,
    ) -> None:
        self.k_exact = k_exact
        self.k_fulltext = k_fulltext
        self.k_vector = k_vector
        self.w_lexical = w_lexical
        self.w_vector = w_vector
        self.vector_index_name = vector_index_name
        self.surface_form_vector_index_name = surface_form_vector_index_name
        self._embedder = embedder
        self._vector_index_ok: bool | None = None
        self._surface_form_vector_ok: bool | None = None
        self._surface_form_fulltext_ok: bool | None = None
        self._surface_form_exact_ok: bool | None = None

    @staticmethod
    def get_related_concepts(concept_id: str, neo4j_session) -> list[dict[str, str]]:
        """Query SNOMED ontology neighbours for a single lab-domain concept.

        Returns a flat list of related concept dicts, each with keys:
        ``id``, ``fsn``, ``semantic_tag``, ``rel``.

        Relationship types returned (materialised by phase-3 loader):
        - ``INTERPRETED_BY``     — findings that interpret this observable
        - ``COMPONENT_OF``       — procedures that contain this observable
        - ``INTERPRETS``         — observables that this finding interprets
        - ``HAS_COMPONENT``      — observables that this procedure measures
        - ``HAS_ASSOCIATED_FINDING`` — directly associated findings
        """
        try:
            rows = list(
                neo4j_session.run(RELATED_CONCEPTS_QUERY, concept_id=concept_id)
            )
        except Exception:
            logger.warning(
                "get_related_concepts query failed for %s", concept_id, exc_info=True
            )
            return []

        if not rows:
            return []

        return _parse_related_concepts_row(rows[0])

    @staticmethod
    def _batch_get_related_concepts(
        concept_ids: list[str], neo4j_session
    ) -> dict[str, list[dict[str, str]]]:
        """Batch version of get_related_concepts — one round trip for all IDs."""
        if not concept_ids:
            return {}
        try:
            rows = list(
                neo4j_session.run(BATCH_RELATED_CONCEPTS_QUERY, concept_ids=concept_ids)
            )
        except Exception:
            logger.warning("batch_get_related_concepts query failed", exc_info=True)
            return {}
        return {
            row["concept_id"]: _parse_related_concepts_row(dict(row))
            for row in rows
            if row.get("concept_id")
        }

    def resolve_candidates(
        self,
        term_texts: list[str],
        *,
        neo4j_session,
        expected_tags: dict[str, str] | None = None,
        enrich_lab_domain: bool = True,
    ) -> dict[str, list[CodingCandidate]]:
        """Resolve a list of clinical terms to ranked SNOMED candidates.

        Uses batched Neo4j queries: ~4 round trips total regardless of how
        many terms are in the list, instead of the previous N × 8-12 per-term
        sequential queries.
        """
        if not term_texts:
            return {}

        t0 = time.perf_counter()
        unique_texts = list(dict.fromkeys(term_texts))

        # Compute embeddings for all terms in one batch (GPU/CPU SentenceTransformer)
        embeddings = self._embed(unique_texts)
        t_embed = time.perf_counter()
        logger.debug(
            "[resolver] embed  terms=%d  elapsed=%.3fs", len(unique_texts), t_embed - t0
        )

        # merged[term][concept_id] = {lexical_raw, vector_raw, ...}
        merged_all: dict[str, dict[str, dict[str, Any]]] = {t: {} for t in unique_texts}

        # ── Batch exact branch (Term + SurfaceForm, 1 round trip) ──────────────
        normalized_map: dict[str, str] = {t: normalize_surface(t) for t in unique_texts}
        exact_hit_terms: set[str] = self._batch_exact(
            unique_texts, normalized_map, neo4j_session, merged_all
        )
        t_exact = time.perf_counter()
        logger.debug(
            "[resolver] exact  terms=%d  hits=%d  elapsed=%.3fs",
            len(unique_texts),
            len(exact_hit_terms),
            t_exact - t_embed,
        )

        # ── Batch fulltext branch (1-3 round trips total) ──────────────────────
        # Only run fulltext for terms that were NOT fully resolved by exact.
        # Short-circuit: skip if a term got exact hits from BOTH Term and SurfaceForm.
        fulltext_needed = [t for t in unique_texts if t not in exact_hit_terms]
        if fulltext_needed:
            self._batch_fulltext(fulltext_needed, neo4j_session, merged_all)
        t_fulltext = time.perf_counter()
        logger.debug(
            "[resolver] fulltext  terms_needed=%d  elapsed=%.3fs",
            len(fulltext_needed),
            t_fulltext - t_exact,
        )

        # ── Vector branch (1-2 round trips per term, run after exact+fulltext) ──
        # Run vector UNLESS the top lexical score is already strong enough
        # (see _DEFAULT_VECTOR_SKIP_SCORE). Previously vector was skipped when
        # ANY lexical hit existed (score > 0), which suppressed the embedding
        # branch precisely when weak fulltext token matches returned spurious
        # partial-word candidates for multi-token phrases -- the biggest known
        # driver of misresolved NG12 terms.
        # Set TERMINOLOGY_ENABLE_VECTOR=false to disable entirely (e.g. eval
        # runs where AuraDB vector index latency would dominate request time).
        vector_enabled = (
            os.getenv("TERMINOLOGY_ENABLE_VECTOR", "true").lower() != "false"
        )
        skip_score = _vector_skip_score()
        vector_needed = [
            t for t in unique_texts if _top_lexical_score(merged_all[t]) < skip_score
        ]
        if embeddings and vector_needed and vector_enabled:
            for text in vector_needed:
                idx = unique_texts.index(text)
                self._run_vector_for_term(
                    text, embeddings[idx], neo4j_session, merged_all[text]
                )
        t_vector = time.perf_counter()
        if embeddings:
            logger.debug(
                "[resolver] vector  terms_needed=%d  skipped=%d  elapsed=%.3fs",
                len(vector_needed),
                len(unique_texts) - len(vector_needed),
                t_vector - t_fulltext,
            )

        # ── Score fusion and candidate ranking (pure Python, no I/O) ───────────
        results: dict[str, list[CodingCandidate]] = {}
        for text in unique_texts:
            tag = (expected_tags or {}).get(text)
            results[text] = self._fuse_and_rank(merged_all[text], expected_tag=tag)

        resolved = sum(1 for v in results.values() if v)
        branches = "exact+fulltext"
        if self._vector_index_ok or self._surface_form_vector_ok:
            branches += "+vector"
        t_fuse = time.perf_counter()
        logger.info(
            "[resolver] %s  terms=%d  resolved=%d  embed=%.3fs  exact=%.3fs  fulltext=%.3fs  vector=%.3fs  fuse=%.3fs  total=%.3fs",
            branches,
            len(unique_texts),
            resolved,
            t_embed - t0,
            t_exact - t_embed,
            t_fulltext - t_exact,
            t_vector - t_fulltext,
            t_fuse - t_vector,
            t_fuse - t0,
        )

        # ── Batch lab-domain enrichment (1 round trip for all lab concepts) ────
        if enrich_lab_domain:
            lab_concept_ids: list[str] = []
            for candidates in results.values():
                if (
                    candidates
                    and (candidates[0].semantic_tag or "").lower() in LAB_DOMAIN_TAGS
                ):
                    if candidates[0].snomed_concept_id:
                        lab_concept_ids.append(candidates[0].snomed_concept_id)

            if lab_concept_ids:
                t_enrich_start = time.perf_counter()
                related_by_id = self._batch_get_related_concepts(
                    lab_concept_ids, neo4j_session
                )
                enriched = 0
                for candidates in results.values():
                    if not candidates:
                        continue
                    top = candidates[0]
                    if top.snomed_concept_id and top.snomed_concept_id in related_by_id:
                        related = related_by_id[top.snomed_concept_id]
                        if related:
                            candidates[0] = replace(top, related_concepts=related)
                            enriched += 1
                logger.info(
                    "[resolver] enrichment  lab_terms=%d  enriched=%d  elapsed=%.3fs",
                    len(lab_concept_ids),
                    enriched,
                    time.perf_counter() - t_enrich_start,
                )

        return {text: results.get(text, []) for text in term_texts}

    # ── Batch helper methods ───────────────────────────────────────────────────

    def _batch_exact(
        self,
        terms: list[str],
        normalized_map: dict[str, str],
        session,
        merged_all: dict[str, dict[str, dict[str, Any]]],
    ) -> set[str]:
        """Run batched exact match (Term + SurfaceForm) for all terms.

        Returns the set of terms that had at least one exact hit (from either
        Term or SurfaceForm), used to short-circuit fulltext/vector for those.
        """
        norm_to_terms: dict[str, list[str]] = {}
        for t in terms:
            n = normalized_map[t]
            if n:
                norm_to_terms.setdefault(n, []).append(t)

        if not norm_to_terms:
            return set()

        # Probe SurfaceForm label existence once (cached on instance)
        if self._surface_form_exact_ok is None:
            try:
                probe = list(
                    session.run(
                        "CALL db.labels() YIELD label WHERE label = 'SurfaceForm' RETURN 1 AS ok LIMIT 1"
                    )
                )
                self._surface_form_exact_ok = bool(probe)
                if not self._surface_form_exact_ok:
                    self._surface_form_fulltext_ok = False
            except Exception:
                self._surface_form_exact_ok = False

        hit_terms: set[str] = set()
        try:
            rows = list(
                session.run(
                    BATCH_EXACT_QUERY,
                    normalized_terms=list(norm_to_terms.keys()),
                )
            )
            for row in rows:
                norm = row["input_term"]
                hits = row.get("hits") or []
                for hit in hits:
                    hit = dict(hit)
                    for orig_term in norm_to_terms.get(norm, []):
                        _push(merged_all[orig_term], hit, "lexical_exact")
                        hit_terms.add(orig_term)
        except Exception:
            logger.debug(
                "BATCH_EXACT_QUERY failed — falling back to per-term exact",
                exc_info=True,
            )
            # Fallback: per-term exact queries
            for term in terms:
                norm = normalized_map[term]
                if not norm:
                    continue
                try:
                    for rec in session.run(
                        EXACT_QUERY, normalized=norm, k=self.k_exact
                    ):
                        _push(merged_all[term], dict(rec), "lexical_exact")
                        hit_terms.add(term)
                    if self._surface_form_exact_ok:
                        for rec in session.run(
                            EXACT_SURFACE_FORM_QUERY, normalized=norm, k=self.k_exact
                        ):
                            _push(merged_all[term], dict(rec), "lexical_exact")
                            hit_terms.add(term)
                except Exception:
                    pass

        return hit_terms

    def _batch_fulltext(
        self,
        terms: list[str],
        session,
        merged_all: dict[str, dict[str, dict[str, Any]]],
    ) -> None:
        """Run batched fulltext search for the given terms.

        Runs one UNION query per fulltext variant (phrase / raw / AND-tokens),
        merging results for each concept into merged_all per term.
        """
        # Build the union of all fulltext query variants across all terms.
        # We run one Neo4j query per variant string, not per term.
        variant_to_terms: dict[str, list[str]] = {}
        for term in terms:
            for ft_q in _build_fulltext_queries(term):
                variant_to_terms.setdefault(ft_q, []).append(term)

        for ft_q, _ in variant_to_terms.items():
            try:
                rows = list(
                    session.run(BATCH_FULLTEXT_QUERY, ft_query=ft_q, k=self.k_fulltext)
                )
                # The UNION query returns hits for the single ft_query string.
                # We associate those hits back to all terms that produced this variant.
                for term in variant_to_terms[ft_q]:
                    for rec in rows:
                        _push(merged_all[term], dict(rec), "lexical")
                if self._surface_form_fulltext_ok is None and rows is not None:
                    self._surface_form_fulltext_ok = True
            except Exception as exc:
                if "no such fulltext schema index" in str(exc).lower():
                    self._surface_form_fulltext_ok = False
                # Fall back to individual queries for this variant
                for term in variant_to_terms[ft_q]:
                    try:
                        for rec in session.run(
                            FULLTEXT_QUERY, ft_query=ft_q, k=self.k_fulltext
                        ):
                            _push(merged_all[term], dict(rec), "lexical")
                    except Exception:
                        pass

    def _run_vector_for_term(
        self,
        term: str,
        embedding: list[float],
        session,
        merged: dict[str, dict[str, Any]],
    ) -> None:
        """Run vector queries for a single term (Neo4j vector index is not UNWIND-batchable)."""
        if self._vector_index_ok is not False:
            try:
                for rec in session.run(
                    VECTOR_QUERY,
                    index_name=self.vector_index_name,
                    k=self.k_vector,
                    embedding=embedding,
                ):
                    _push(merged, dict(rec), "vector")
                if self._vector_index_ok is None:
                    self._vector_index_ok = True
            except Exception as exc:
                if "no such vector schema index" in str(exc).lower():
                    self._vector_index_ok = False

        if self._surface_form_vector_ok is not False:
            try:
                for rec in session.run(
                    VECTOR_SURFACE_FORM_QUERY,
                    index_name=self.surface_form_vector_index_name,
                    k=self.k_vector,
                    embedding=embedding,
                ):
                    _push(merged, dict(rec), "vector")
                if self._surface_form_vector_ok is None:
                    self._surface_form_vector_ok = True
            except Exception as exc:
                if "no such vector schema index" in str(exc).lower():
                    self._surface_form_vector_ok = False

    def _fuse_and_rank(
        self,
        merged: dict[str, dict[str, Any]],
        expected_tag: str | None = None,
    ) -> list[CodingCandidate]:
        """Score-fuse and rank merged candidates for one term.

        Returns candidates sorted by ``score`` descending, where ``score``
        is a CALIBRATED ABSOLUTE confidence in [0.0, 1.0].

        Calibrated absolute scoring (replaces per-term local normalisation)
        --------------------------------------------------------------------
        The previous implementation normalised lexical/vector raw scores
        against the per-term maximum, then multiplied by a 1.3 tag boost.
        This made the top candidate always score ~1.0-1.3 regardless of
        how strong the underlying retrieval evidence was -- a one-token
        partial Lucene match scored the same as a curated SurfaceForm
        exact hit, both reaching ~1.3 if the tag aligned. Downstream
        consumers (coder gates, surface-form validators, the SNOMED
        proposal validator) could not tell strong from weak matches.

        The new scheme produces a calibrated absolute confidence:

          1. Lexical signal in [0, 1]:
             - Exact branch (Term/SurfaceForm) -> 1.0  (strongest possible)
             - Fulltext (Lucene BM25) -> bm25 / (bm25 + 1)
               Saturating curve: BM25 of 1 -> 0.5, 5 -> 0.83, 10 -> 0.91.
          2. Vector signal in [0, 1]: cosine similarity (already absolute).
          3. Combine: max(lex, vec) + 0.10 * min(lex, vec), capped at 1.0.
             Strongest single branch wins; agreement between branches
             earns a small bonus.
          4. Tag adjustment:
             - exact tag match     -> +0.10 (additive boost, capped at 1.0)
             - compatible group    -> no change
             - cross-group         -> *0.5 (penalty)
             - non-clinical no-tag -> capped at 0.4
          5. Hard cull: scores below ``_MIN_SCORE`` (0.15) are dropped.

        Sort order: confidence DESC. Tag-matching wins ties via the +0.10
        additive boost (no implicit "tag always wins" tier).
        """
        if not merged:
            return []

        normalised_expected_tag = _normalise_semantic_tag(expected_tag)
        expected_group = (
            TAG_GROUPS.get(normalised_expected_tag, "")
            if normalised_expected_tag
            else ""
        )
        hard_block_non_clinical = bool(
            normalised_expected_tag and _CLINICAL_GROUPS.intersection({expected_group})
        )

        scored: list[tuple[float, dict[str, Any]]] = []
        for c in merged.values():
            candidate_tag = _normalise_semantic_tag(c.get("semantic_tag") or "")

            if hard_block_non_clinical and candidate_tag in _NON_CLINICAL_TAGS:
                continue

            confidence = _calibrate_confidence(c)
            confidence = _apply_tag_adjustment(
                confidence,
                candidate_tag=candidate_tag,
                expected_tag=normalised_expected_tag,
                expected_group=expected_group,
            )

            if candidate_tag in _NON_CLINICAL_TAGS and not normalised_expected_tag:
                confidence = min(confidence, 0.4)

            if confidence < _MIN_SCORE:
                continue

            scored.append((confidence, c))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            CodingCandidate(
                snomed_concept_id=c["concept_id"],
                snomed_term=c.get("fsn"),
                semantic_tag=c.get("semantic_tag"),
                read_code=(c.get("read_codes") or [None])[0],
                score=round(confidence, 4),
                source="hybrid",
                surface_form_status=c.get("surface_form_status", ""),
                had_exact_match=bool(c.get("had_exact_match", False)),
                lexical_raw=round(float(c.get("lexical_raw", 0.0)), 4),
                vector_raw=round(float(c.get("vector_raw", 0.0)), 4),
            )
            for confidence, c in scored
        ]

    def _embed(self, texts: Sequence[str]) -> list[list[float]] | None:
        if not self._embedder:
            return None
        try:
            return self._embedder.encode(texts)
        except Exception:
            if getattr(self._embedder, "resolved_device", "") == "mps" and os.getenv(
                "VECTOR_MPS_FAIL_FAST", "true"
            ).lower() in ("1", "true", "yes"):
                raise
            logger.warning("Embedding failed — vector branch disabled", exc_info=True)
            return None

    def _resolve_single(
        self,
        mention: str,
        session,
        embedding: list[float] | None,
        expected_tag: str | None = None,
    ) -> list[CodingCandidate]:
        """Resolve a single term using sequential per-term queries.

        Preserved for backwards compatibility and single-term interactive lookups.
        ``resolve_candidates`` uses the batched path for efficiency.
        """
        normalized = normalize_surface(mention)
        merged: dict[str, dict[str, Any]] = {}

        # Branch 1: exact
        if normalized:
            for rec in session.run(EXACT_QUERY, normalized=normalized, k=self.k_exact):
                _push(merged, dict(rec), "lexical_exact")
            if self._surface_form_exact_ok is not False:
                try:
                    if self._surface_form_exact_ok is None:
                        probe = list(
                            session.run(
                                "CALL db.labels() YIELD label WHERE label = 'SurfaceForm' RETURN 1 AS ok LIMIT 1"
                            )
                        )
                        self._surface_form_exact_ok = bool(probe)
                        if not self._surface_form_exact_ok:
                            self._surface_form_fulltext_ok = False
                    if self._surface_form_exact_ok:
                        for rec in session.run(
                            EXACT_SURFACE_FORM_QUERY,
                            normalized=normalized,
                            k=self.k_exact,
                        ):
                            _push(merged, dict(rec), "lexical_exact")
                except Exception:
                    self._surface_form_exact_ok = False

        # Branch 2: fulltext
        for ft_query in _build_fulltext_queries(mention):
            try:
                for rec in session.run(
                    FULLTEXT_QUERY, ft_query=ft_query, k=self.k_fulltext
                ):
                    _push(merged, dict(rec), "lexical")
            except Exception:
                continue
            if self._surface_form_fulltext_ok is not False:
                try:
                    for rec in session.run(
                        FULLTEXT_SURFACE_FORM_QUERY,
                        ft_query=ft_query,
                        k=self.k_fulltext,
                    ):
                        _push(merged, dict(rec), "lexical")
                    if self._surface_form_fulltext_ok is None:
                        self._surface_form_fulltext_ok = True
                except Exception as exc:
                    if "no such fulltext schema index" in str(exc).lower():
                        self._surface_form_fulltext_ok = False

        # Branch 3 & 4: vector
        if embedding and _top_lexical_score(merged) < _vector_skip_score():
            self._run_vector_for_term(mention, embedding, session, merged)

        return self._fuse_and_rank(merged, expected_tag=expected_tag)
