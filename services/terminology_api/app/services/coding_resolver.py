"""Lexical SNOMED/Read code resolution.

Atlas trace:
  DO: DO-E0193D2A
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-E0193D2A")

Ported from PCA services/api/app/services/v3/coding_resolver.py.
Runs two retrieval branches (exact surface-form, fulltext) and fuses scores.

Vector branch removed
~~~~~~~~~~~~~~~~~~~~~
Vector (embedding) lookup was removed because it produced wrong SNOMED codes
when a span's surface tokens semantically overlapped with a different concept.
The concrete failure mode: "Haemoglobin A1c level ... Outside reference range"
(a finding) resolved to "Mean corpuscular haemoglobin outside reference range"
because the vector for "haemoglobin" is closer to MCH than HbA1c.

Lexical retrieval is deterministic and traceable. When neither exact surface
form nor fulltext match succeeds, the resolver returns an empty list, and the
calling pipeline can escalate to Haiku for disambiguation rather than silently
returning a wrong concept.

Batch optimization
~~~~~~~~~~~~~~~~~~
``resolve_candidates`` uses batched UNWIND queries so that resolving N terms
costs ~3 round trips to Neo4j regardless of N.

Short-circuit
~~~~~~~~~~~~~
If a term is fully resolved by the exact branch (Term + SurfaceForm both
return results at score >= 1.0), the fulltext branch is skipped for that
term, cutting 3-5 round trips per already-known term.

Lab-domain enrichment
~~~~~~~~~~~~~~~~~~~~~
When ``resolve_candidates`` resolves an entity to a concept whose semantic tag
is ``observable entity``, ``procedure``, or ``finding``, the resolver can
optionally traverse the SNOMED ontology family via ``get_related_concepts`` to
return the full cluster of related concepts (INTERPRETS / HAS_COMPONENT /
HAS_ASSOCIATED_FINDING edges materialised by the phase-3 loader).
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from libs.terminology.surface_normalize import TOKEN_RE, normalize_surface
from services.terminology_api.app.services.cache import TerminologyCache
from services.terminology_api.app.queries.terminology import (
    BATCH_EXACT_QUERY,
    BATCH_FULLTEXT_QUERY,
    BATCH_RELATED_CONCEPTS_QUERY,
    EXACT_QUERY,
    EXACT_SURFACE_FORM_QUERY,
    FULLTEXT_QUERY,
    FULLTEXT_SURFACE_FORM_QUERY,
    RELATED_CONCEPTS_QUERY,
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


from libs.terminology.surface_form_policy import is_resolvable_surface_form_status


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
    if sf_status and not is_resolvable_surface_form_status(sf_status):
        return
    if sf_status:
        base["surface_form_status"] = sf_status
    score = float(rec.get("score", 0.0))
    if branch == "lexical":
        base["lexical_raw"] = max(base["lexical_raw"], score)
    elif branch == "lexical_exact":
        base["lexical_raw"] = max(base["lexical_raw"], score)
        base["had_exact_match"] = True


def _parse_related_concepts_row(row: dict[str, Any]) -> list[dict[str, str]]:
    """Parse a RELATED_CONCEPTS_QUERY / BATCH_RELATED_CONCEPTS_QUERY row."""
    related: list[dict[str, str]] = []
    for key in (
        "interpreted_by_findings",
        "component_of_procedures",
        "interprets_observables",
        "has_components",
        "associated_findings",
        "finding_sites",
        "procedure_sites",
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
    #   vector_raw     -- always 0.0 (vector branch removed; field kept
    #     for API backward compatibility).
    had_exact_match: bool = False
    lexical_raw: float = 0.0
    vector_raw: float = 0.0
    # For lab-domain concepts: family members discovered via SNOMED ontology edges
    # (INTERPRETS, HAS_COMPONENT, HAS_ASSOCIATED_FINDING).
    # Each entry: {"id", "fsn", "semantic_tag", "rel"}
    related_concepts: list[dict[str, str]] = field(default_factory=list)


def _calibrate_confidence(c: dict[str, Any]) -> float:
    """Compute calibrated absolute confidence in [0.0, 1.0] for one candidate.

    Pulled out as a free function so tests and downstream consumers can
    replicate the calibration logic without instantiating a resolver.

    Lexical signal mapping:
      - Exact branch (Term / SurfaceForm exact match) -> 1.0
      - Fulltext (Lucene BM25) -> bm25 / (bm25 + 1)
        Saturating: BM25=1 -> 0.5, BM25=5 -> 0.83, BM25=10 -> 0.91.
    """
    if c.get("had_exact_match"):
        return 1.0
    lex_raw = float(c.get("lexical_raw", 0.0) or 0.0)
    if lex_raw <= 0.0:
        return 0.0
    return min(1.0, lex_raw / (lex_raw + 1.0))


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
    """Lexical term -> SNOMED resolver using exact surface-form + fulltext retrieval."""

    def __init__(
        self,
        *,
        k_exact: int = 30,
        k_fulltext: int = 40,
    ) -> None:
        self.k_exact = k_exact
        self.k_fulltext = k_fulltext
        self._surface_form_fulltext_ok: bool | None = None
        self._surface_form_exact_ok: bool | None = None
        self._cache = TerminologyCache()

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

    def _package_fingerprint(self, neo4j_session, org_id: str | None) -> str:
        """Stable fingerprint of active packages visible for org_id."""
        try:
            rows = list(
                neo4j_session.run(
                    """
                    MATCH (p:LocalTerminologyPackage {status: 'active'})
                    WHERE p.scope = 'global'
                       OR ($org_id IS NOT NULL AND p.scope = 'tenant'
                           AND p.org_id = $org_id)
                    RETURN p.id AS id, coalesce(p.version, 1) AS version
                    """,
                    org_id=(org_id or "").strip() or None,
                )
            )
            parts = sorted(f"{r['id']}:{r['version']}" for r in rows if r.get("id"))
            return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()[:12]
        except Exception:
            return ""

    def resolve_candidates(
        self,
        term_texts: list[str],
        *,
        neo4j_session,
        expected_tags: dict[str, str] | None = None,
        enrich_lab_domain: bool = True,
        org_id: str | None = None,
    ) -> dict[str, list[CodingCandidate]]:
        """Resolve a list of clinical terms to ranked SNOMED candidates.

        Uses batched Neo4j queries: ~4 round trips total regardless of how
        many terms are in the list, instead of the previous N × 8-12 per-term
        sequential queries. Local SurfaceForms are limited to active packages
        for org_id (global + matching tenant).
        """
        if not term_texts:
            return {}

        t0 = time.perf_counter()
        unique_texts = list(dict.fromkeys(term_texts))
        oid = (org_id or "").strip() or None
        package_fp = self._package_fingerprint(neo4j_session, oid)

        # ── 1. Cache Interception ─────────────────────────────────────────────
        cache_keys: dict[str, str] = {}
        for text in unique_texts:
            tag = (expected_tags or {}).get(text)
            cache_keys[text] = self._cache.generate_key(
                text,
                tag,
                enrich_lab_domain,
                org_id=oid,
                package_fingerprint=package_fp,
            )

        cached_payloads = self._cache.mget(list(cache_keys.values()))

        results: dict[str, list[CodingCandidate]] = {}
        misses: list[str] = []
        for text in unique_texts:
            key = cache_keys[text]
            if key in cached_payloads:
                results[text] = [CodingCandidate(**c) for c in cached_payloads[key]]
            else:
                misses.append(text)

        t_cache = time.perf_counter()
        logger.debug(
            "[resolver] cache  hits=%d  misses=%d  elapsed=%.3fs",
            len(unique_texts) - len(misses),
            len(misses),
            t_cache - t0,
        )

        if not misses:
            return {text: results.get(text, []) for text in term_texts}

        # merged[term][concept_id] = {lexical_raw, ...}
        merged_all: dict[str, dict[str, dict[str, Any]]] = {t: {} for t in misses}

        # ── Batch exact branch (Term + SurfaceForm, 1 round trip) ──────────────
        normalized_map: dict[str, str] = {t: normalize_surface(t) for t in misses}
        exact_hit_terms: set[str] = self._batch_exact(
            misses, normalized_map, neo4j_session, merged_all, org_id=oid
        )
        t_exact = time.perf_counter()
        logger.debug(
            "[resolver] exact  terms=%d  hits=%d  elapsed=%.3fs",
            len(misses),
            len(exact_hit_terms),
            t_exact - t_cache,
        )

        # ── Batch fulltext branch (1-3 round trips total) ──────────────────────
        # Only run fulltext for terms that were NOT fully resolved by exact.
        # Short-circuit: skip if a term got exact hits from BOTH Term and SurfaceForm.
        fulltext_needed = [t for t in misses if t not in exact_hit_terms]
        if fulltext_needed:
            self._batch_fulltext(fulltext_needed, neo4j_session, merged_all, org_id=oid)
        t_fulltext = time.perf_counter()
        logger.debug(
            "[resolver] fulltext  terms_needed=%d  elapsed=%.3fs",
            len(fulltext_needed),
            t_fulltext - t_exact,
        )

        # ── Score fusion and candidate ranking (pure Python, no I/O) ───────────
        for text in misses:
            tag = (expected_tags or {}).get(text)
            results[text] = self._fuse_and_rank(merged_all[text], expected_tag=tag)

        # ── Batch lab-domain enrichment (1 round trip for all lab concepts) ────
        if enrich_lab_domain:
            lab_concept_ids: list[str] = []
            for text in misses:
                candidates = results.get(text, [])
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
                for text in misses:
                    candidates = results.get(text, [])
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

        # ── Cache Writeback ────────────────────────────────────────────────────
        cache_writes: dict[str, Any] = {}
        for text in misses:
            key = cache_keys[text]
            cache_writes[key] = [asdict(c) for c in results.get(text, [])]

        self._cache.msetex(cache_writes)

        resolved = sum(1 for text in misses if results.get(text))
        t_fuse = time.perf_counter()
        logger.info(
            "[resolver] exact+fulltext  terms=%d  resolved=%d  exact=%.3fs  fulltext=%.3fs  fuse=%.3fs  total=%.3fs",
            len(misses),
            resolved,
            t_exact - t_cache,
            t_fulltext - t_exact,
            t_fuse - t_fulltext,
            t_fuse - t_cache,
        )

        return {text: results.get(text, []) for text in term_texts}

    # ── Batch helper methods ───────────────────────────────────────────────────

    def _batch_exact(
        self,
        terms: list[str],
        normalized_map: dict[str, str],
        session,
        merged_all: dict[str, dict[str, dict[str, Any]]],
        org_id: str | None = None,
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

        oid = (org_id or "").strip() or None

        # Probe SurfaceForm label existence once (cached on instance)
        if self._surface_form_exact_ok is None:
            try:
                probe = list(
                    session.run(
                        "CALL db.labels() YIELD label "
                        "WHERE label = 'SurfaceForm' RETURN 1 AS ok LIMIT 1"
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
                    org_id=oid,
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
                "BATCH_EXACT_QUERY failed - falling back to per-term exact",
                exc_info=True,
            )
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
                            EXACT_SURFACE_FORM_QUERY,
                            normalized=norm,
                            k=self.k_exact,
                            org_id=oid,
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
        org_id: str | None = None,
    ) -> None:
        """Run batched fulltext search for the given terms.

        Runs one UNION query per fulltext variant (phrase / raw / AND-tokens),
        merging results for each concept into merged_all per term.
        """
        oid = (org_id or "").strip() or None
        variant_to_terms: dict[str, list[str]] = {}
        for term in terms:
            for ft_q in _build_fulltext_queries(term):
                variant_to_terms.setdefault(ft_q, []).append(term)

        for ft_q, _ in variant_to_terms.items():
            try:
                rows = list(
                    session.run(
                        BATCH_FULLTEXT_QUERY,
                        ft_query=ft_q,
                        k=self.k_fulltext,
                        org_id=oid,
                    )
                )
                for term in variant_to_terms[ft_q]:
                    for rec in rows:
                        _push(merged_all[term], dict(rec), "lexical")
                if self._surface_form_fulltext_ok is None and rows is not None:
                    self._surface_form_fulltext_ok = True
            except Exception as exc:
                if "no such fulltext schema index" in str(exc).lower():
                    self._surface_form_fulltext_ok = False
                for term in variant_to_terms[ft_q]:
                    try:
                        for rec in session.run(
                            FULLTEXT_QUERY, ft_query=ft_q, k=self.k_fulltext
                        ):
                            _push(merged_all[term], dict(rec), "lexical")
                        if self._surface_form_fulltext_ok is not False:
                            for rec in session.run(
                                FULLTEXT_SURFACE_FORM_QUERY,
                                ft_query=ft_q,
                                k=self.k_fulltext,
                                org_id=oid,
                            ):
                                _push(merged_all[term], dict(rec), "lexical")
                    except Exception:
                        pass

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

        Calibrated absolute confidence mapping:

          1. Lexical signal in [0, 1]:
             - Exact branch (Term/SurfaceForm) -> 1.0  (strongest possible)
             - Fulltext (Lucene BM25) -> bm25 / (bm25 + 1)
               Saturating curve: BM25=1 -> 0.5, BM25=5 -> 0.83, BM25=10 -> 0.91.
          2. Tag adjustment:
             - exact tag match     -> +0.10 (additive boost, capped at 1.0)
             - compatible group    -> no change
             - cross-group         -> *0.5 (penalty)
             - non-clinical no-tag -> capped at 0.4
          3. Hard cull: scores below ``_MIN_SCORE`` (0.15) are dropped.

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
                source="lexical",
                surface_form_status=c.get("surface_form_status", ""),
                had_exact_match=bool(c.get("had_exact_match", False)),
                lexical_raw=round(float(c.get("lexical_raw", 0.0)), 4),
                vector_raw=0.0,
            )
            for confidence, c in scored
        ]

    def _resolve_single(
        self,
        mention: str,
        session,
        expected_tag: str | None = None,
        org_id: str | None = None,
    ) -> list[CodingCandidate]:
        """Resolve a single term using sequential per-term queries.

        Preserved for backwards compatibility and single-term interactive lookups.
        ``resolve_candidates`` uses the batched path for efficiency.
        """
        normalized = normalize_surface(mention)
        merged: dict[str, dict[str, Any]] = {}
        oid = (org_id or "").strip() or None

        # Branch 1: exact
        if normalized:
            for rec in session.run(EXACT_QUERY, normalized=normalized, k=self.k_exact):
                _push(merged, dict(rec), "lexical_exact")
            if self._surface_form_exact_ok is not False:
                try:
                    if self._surface_form_exact_ok is None:
                        probe = list(
                            session.run(
                                "CALL db.labels() YIELD label "
                                "WHERE label = 'SurfaceForm' "
                                "RETURN 1 AS ok LIMIT 1"
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
                            org_id=oid,
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
                        org_id=oid,
                    ):
                        _push(merged, dict(rec), "lexical")
                    if self._surface_form_fulltext_ok is None:
                        self._surface_form_fulltext_ok = True
                except Exception as exc:
                    if "no such fulltext schema index" in str(exc).lower():
                        self._surface_form_fulltext_ok = False

        return self._fuse_and_rank(merged, expected_tag=expected_tag)
