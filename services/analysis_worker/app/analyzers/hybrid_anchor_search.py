"""Tier-2 hybrid anchor detection — sentence-level resolution.

Two operating modes
-------------------
Production (deep_mode=False, default):
    Split encounter text into clinical sentences, resolve each sentence against
    the terminology API (exact + fulltext + vector), filter returned SNOMED
    concept IDs against milestone concept sets, apply lightweight regex
    context-confidence for diagnosis disambiguation.
    Fast, deterministic, no LLM overhead.

Gold Audit (deep_mode=True):
    Same sentence-level resolution PLUS:
    • SNOMED IS_A hierarchy expansion — queries the knowledge graph to build an
      expanded concept set so that specific subtypes ("invasive ductal carcinoma")
      match parent milestone IDs ("malignant neoplasm of breast").
    • LLM disambiguation for every candidate hit — replaces regex context
      confidence with a small-model classification:
        A = confirmed/active  B = suspected/query  C = historical  D = irrelevant
      Suspected and irrelevant hits are suppressed; historical diagnosis hits are
      suppressed (but historical referral/treatment/specialist are accepted).
    Designed for maximum recall and precision at the cost of LLM latency.
    Appropriate for ground-truth V&V audits where quality > throughput.

Called by ``anchor_detector.detect_anchors()`` for milestone types still absent
after tier-1 concept matching.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import threading
from dataclasses import dataclass, field
from typing import Any

import httpx

from libs.domains.ncda_concept_sets import (
    MILESTONE_CONCEPT_SETS,
)

logger = logging.getLogger(__name__)

TERMINOLOGY_API_URL = os.getenv("TERMINOLOGY_API_URL", "http://localhost:8001")
MIN_SCORE = float(os.getenv("HYBRID_ANCHOR_MIN_SCORE", "0.55"))
HTTP_TIMEOUT = float(os.getenv("HYBRID_ANCHOR_HTTP_TIMEOUT", "60.0"))
# Max sentences per resolver call — keeps requests bounded in size/latency.
# Sentences are pre-filtered to milestone-relevant ones first.
_MAX_SENTENCES_PER_CALL = int(os.getenv("HYBRID_ANCHOR_MAX_SENTENCES", "10"))
# Max LLM disambiguation calls per search_missing_anchors invocation.
# Candidates are ranked by resolver score before capping so the best hits are
# always disambiguated.  Prevents runaway cost on patients with 500+ encounters.
_MAX_LLM_CALLS = int(os.getenv("HYBRID_ANCHOR_MAX_LLM_CALLS", "40"))


# ---------------------------------------------------------------------------
# Sentence splitting
# ---------------------------------------------------------------------------

_SENTENCE_SEP = re.compile(
    r"(?<=[.!?])\s+(?=[A-Z0-9])"   # sentence-ending punctuation + capital/digit
    r"|[\r\n]+"                      # line breaks (common in GP notes)
    r"|\s*;\s*"                      # semicolons used as statement separators
)

# Lines that are noise and should not be sent to the resolver
_NOISE_RE = re.compile(
    r"^\d{1,2}:\d{2}"            # timestamps like "09:30"
    r"|^\d{4}-\d{2}-\d{2}$"     # bare date strings
    r"|^[A-Z]{1,3}\d{1,5}$"     # short codes like "XaXbX"
    r"|^\s*$"                    # empty
)


def _split_sentences(text: str) -> list[str]:
    """Split GP encounter text into candidate clinical sentences.

    Sentences shorter than 10 characters or matching noise patterns are dropped.
    Compared to keyword-windowing, every sentence is considered — we do not
    require a pre-known keyword to be present, so subtle expressions are caught.
    """
    parts = _SENTENCE_SEP.split(text)
    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        p = part.strip()
        if len(p) < 10:
            continue
        if _NOISE_RE.match(p):
            continue
        norm = p.lower()
        if norm in seen:
            continue
        seen.add(norm)
        result.append(p)
    return result


# ---------------------------------------------------------------------------
# Context confidence — production mode (lightweight, no LLM)
# ---------------------------------------------------------------------------

_CONFIRMED_RE = re.compile(
    r"(?i)\b(?:"
    r"confirmed|histol(?:ogy|ogically)|pathol(?:ogy|ogically)|biopsy\s+(?:showed?|confirmed|revealed?)"
    r"|MDT\s+(?:confirmed|outcome)|diagnosed\s+(?:as|with)\b"
    r")"
)
_SUSPECTED_RE = re.compile(
    r"(?i)\b(?:"
    r"suspected?|suspicion|awaiting|query\s*\?|possible|probable|rule\s+out|\?\s*cancer"
    r"|under\s+investigation|to\s+be\s+confirmed|pending\s+(?:biopsy|histology|result)"
    r")"
)
_AMBIGUOUS_RE = re.compile(
    r"(?i)\b(?:history\s+of|past\s+(?:medical\s+)?history|previous(?:ly)?)\b"
)


def _context_confidence(text: str, milestone_type: str) -> float:
    """Return a 0–1 multiplier from diagnostic context signals (production mode)."""
    if milestone_type != "diagnosis":
        return 1.0
    if _CONFIRMED_RE.search(text):
        return 1.0
    if _SUSPECTED_RE.search(text):
        return 0.45  # below threshold — won't be accepted
    if _AMBIGUOUS_RE.search(text):
        return 0.75
    return 0.85  # unlabelled — treat as probable


# ---------------------------------------------------------------------------
# SNOMED IS_A hierarchy expansion — deep_mode only
# ---------------------------------------------------------------------------

_EXPANDED_SETS: dict[str, frozenset[int]] | None = None
_EXPANSION_LOCK = threading.Lock()

_IS_A_DESCENDANTS_QUERY = """
MATCH (child:Concept)-[:IS_A*1..5]->(parent:Concept)
WHERE parent.id IN $parent_ids
  AND child.active = true
RETURN DISTINCT toInteger(child.id) AS concept_id
"""


def _fetch_expanded_sets(kg_session) -> dict[str, frozenset[int]]:
    """Expand each milestone's concept set with IS_A descendants from the knowledge graph.

    The full SNOMED hierarchy is traversed up to 5 levels so that specific
    subtypes like "invasive ductal carcinoma of breast" (a descendant of
    "malignant neoplasm of breast") are captured automatically without needing
    to maintain curated lists of every subtype.

    Result is cached module-level — the traversal runs only once per process.
    Falls back to the original base concept sets if the KG is unavailable.
    """
    global _EXPANDED_SETS
    with _EXPANSION_LOCK:
        if _EXPANDED_SETS is not None:
            return _EXPANDED_SETS

        expanded: dict[str, frozenset[int]] = {}
        for milestone_type, base_ids in MILESTONE_CONCEPT_SETS.items():
            parent_ids = [str(cid) for cid in base_ids]
            try:
                rows = list(kg_session.run(_IS_A_DESCENDANTS_QUERY, parent_ids=parent_ids))
                all_ids = set(base_ids)
                for row in rows:
                    cid = row.get("concept_id")
                    if cid:
                        all_ids.add(int(cid))
                expanded[milestone_type] = frozenset(all_ids)
                logger.info(
                    "SNOMED hierarchy expanded: %s → %d concepts (%d descendants added)",
                    milestone_type, len(all_ids), len(all_ids) - len(base_ids),
                )
            except Exception:
                logger.warning(
                    "SNOMED hierarchy expansion failed for %s — using base concept set",
                    milestone_type, exc_info=True,
                )
                expanded[milestone_type] = base_ids

        _EXPANDED_SETS = expanded
        return _EXPANDED_SETS


# ---------------------------------------------------------------------------
# LLM disambiguation — deep_mode only
# ---------------------------------------------------------------------------

_DISAMBIGUATION_SYSTEM = (
    "You are a clinical text analyst reviewing sentences from GP medical records. "
    "Classify how a clinical concept is referenced in the sentence. "
    "Reply with EXACTLY ONE LETTER and nothing else."
)

_DISAMBIGUATION_PROMPT = """\
Sentence: "{sentence}"
Matched SNOMED concept: "{concept}"

Is this sentence documenting:
A) A confirmed, active clinical event (new diagnosis confirmed, procedure performed, referral made, specialist seen)
B) A suspected, query or possible finding (awaiting investigation, not yet confirmed, under review)
C) Historical or past medical history (patient had this previously, now resolved or stable background)
D) Unclear, administrative, not clinically relevant, or not about this concept

Reply with ONLY A, B, C or D:"""

_LLM_LABEL_MAP: dict[str, str] = {
    "A": "confirmed",
    "B": "suspected",
    "C": "historical",
    "D": "irrelevant",
}


def _disambiguate_llm(sentence: str, concept_name: str, milestone_type: str) -> str:
    """Classify how concept_name is referenced in sentence using a small LLM.

    Returns one of: 'confirmed' | 'suspected' | 'historical' | 'irrelevant'

    Graceful degradation: returns 'confirmed' on any LLM failure so we do not
    silently drop valid hits because of infrastructure issues.  The disambiguation
    label is stored on the HybridAnchorHit for clinician review.
    """
    from libs.llm_client.factory import create_llm
    try:
        llm = create_llm(tier="small")
        resp = llm.converse(
            system=_DISAMBIGUATION_SYSTEM,
            messages=[{
                "role": "user",
                "content": _DISAMBIGUATION_PROMPT.format(
                    sentence=sentence[:600],
                    concept=concept_name,
                ),
            }],
            max_tokens=5,
        )
        letter = resp.text.strip().upper()[:1]
        label = _LLM_LABEL_MAP.get(letter, "irrelevant")
        logger.debug(
            "_disambiguate_llm: milestone=%s concept=%r sentence_start=%r → %s",
            milestone_type, concept_name, sentence[:60], label,
        )
        return label
    except Exception:
        logger.warning(
            "_disambiguate_llm: LLM call failed — accepting hit for milestone=%s",
            milestone_type, exc_info=True,
        )
        return "confirmed"  # fail-open: don't silently lose valid anchor hits


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Milestone keyword pre-filter
# ---------------------------------------------------------------------------
# Used to select only milestone-relevant sentences from an encounter before
# sending them to the resolver.  This keeps per-call batch sizes bounded
# without reverting to narrow keyword-window fragments — we still send the
# complete sentence, not a truncated excerpt.

MILESTONE_KEYWORDS: dict[str, list[str]] = {
    "referral": [
        "referral", "2ww", "two week", "fast track", "urgent cancer",
        "fast-track", "two-week-wait", "refer",
    ],
    "diagnosis": [
        "cancer", "carcinoma", "malignant", "neoplasm", "tumour", "tumor",
        "leukaemia", "leukemia", "lymphoma", "melanoma", "sarcoma", "myeloma",
        "metastasi", "biopsy", "histology", "pathology", "mdt", "oncol",
        "diagnosed", "diagnosis",
    ],
    "treatment_start": [
        "chemo", "radiotherapy", "surgery", "operation", "mastectomy",
        "excision", "resection", "nephrectomy", "colectomy", "immunotherapy",
        "hormone therapy", "pembroliz", "nivolumab", "herceptin", "tamoxifen",
        "anti-androgen", "commenced", "started treatment",
    ],
    "specialist_visit": [
        "oncol", "specialist clinic", "cancer clinic", "haematol", "mdt",
        "fast track clinic", "two week wait clinic", "seen in", "attended",
        "clinic appointment",
    ],
}


def _filter_sentences_for_milestone(
    sentences: list[str],
    milestone_type: str,
) -> list[str]:
    """Return sentences that contain at least one milestone keyword.

    This pre-filtering step keeps resolver batches small without discarding
    clinical context — we send whole sentences, not truncated keyword windows.
    """
    keywords = MILESTONE_KEYWORDS.get(milestone_type, [])
    if not keywords:
        return sentences
    return [
        s for s in sentences
        if any(kw in s.lower() for kw in keywords)
    ]


# Expected SNOMED semantic tags per milestone (boosts resolver scoring)
# ---------------------------------------------------------------------------

_MILESTONE_EXPECTED_TAG: dict[str, str] = {
    "referral":        "procedure",
    "diagnosis":       "disorder",
    "treatment_start": "procedure",
    "specialist_visit": "finding",
}


# ---------------------------------------------------------------------------
# Terminology API call
# ---------------------------------------------------------------------------

async def _resolve_sentences(
    sentences: list[str],
    expected_tag: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Send sentences to POST /terminology/resolve and return raw results.

    The resolver runs exact + surface-form + fulltext + vector branches and
    fuses scores.  Providing ``expected_tag`` boosts results whose SNOMED
    semantic tag matches the milestone type (e.g. "disorder" for diagnosis).
    """
    if not sentences:
        return {}
    unique = list(dict.fromkeys(sentences))
    payload: dict[str, Any] = {"terms": unique}
    if expected_tag:
        payload["expected_tags"] = {s: expected_tag for s in unique}
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.post(
                f"{TERMINOLOGY_API_URL}/terminology/resolve",
                json=payload,
            )
            resp.raise_for_status()
            return resp.json().get("results", {})
    except Exception:
        logger.warning("hybrid_anchor_search: terminology resolve failed", exc_info=True)
        return {}


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class HybridAnchorHit:
    encounter_id: str
    encounter_date: str
    concept_id: str
    concept_name: str
    milestone_type: str
    resolver_score: float
    context_confidence: float
    combined_score: float
    phrase: str
    source: str = "hybrid"
    detection_method: str = "hybrid"
    disambiguation: str = ""   # LLM label when deep_mode=True


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------

async def search_missing_anchors(
    encounters: list[dict[str, Any]],
    missing_milestone_types: list[str],
    *,
    min_score: float = MIN_SCORE,
    deep_mode: bool = False,
    kg_session=None,
) -> list[HybridAnchorHit]:
    """Run hybrid search across encounters for missing milestone types.

    Parameters
    ----------
    encounters:
        List of ``{"encounter_id": str, "encounter_date"/"date": str, "text": str}``.
    missing_milestone_types:
        Subset of ``["referral", "diagnosis", "treatment_start", "specialist_visit"]``.
    deep_mode:
        When ``True``, activates SNOMED IS_A hierarchy expansion and LLM
        disambiguation.  Requires ``kg_session`` for hierarchy expansion.
        Use for gold-dataset audits.
    kg_session:
        An open ``KnowledgeGraphClient`` session for SNOMED hierarchy expansion.
        Only used when ``deep_mode=True``.

    Returns
    -------
    List of HybridAnchorHit sorted by encounter_date then combined_score desc.
    """
    # Resolve effective concept sets (expanded in deep_mode)
    if deep_mode and kg_session is not None:
        effective_sets = _fetch_expanded_sets(kg_session)
    else:
        effective_sets = MILESTONE_CONCEPT_SETS

    hits: list[HybridAnchorHit] = []
    # In deep_mode, LLM calls are expensive and must not be serialised.
    # We collect raw resolver hits first (Phase 1), then fire all LLM calls
    # concurrently (Phase 2) so wall-time ≈ one LLM call latency regardless
    # of the number of candidates.
    raw_candidates: list[dict] = []

    # ------------------------------------------------------------------
    # Phase 1 — resolver pass (async HTTP, already concurrent per call)
    # ------------------------------------------------------------------
    for enc in encounters:
        enc_id = str(enc.get("encounter_id", ""))
        enc_date = str(enc.get("encounter_date") or enc.get("date", ""))
        text = str(enc.get("text") or "")
        if not text.strip():
            continue

        sentences = _split_sentences(text)
        if not sentences:
            continue

        for milestone_type in missing_milestone_types:
            milestone_concept_ids = effective_sets.get(milestone_type, frozenset())
            if not milestone_concept_ids:
                continue

            # Pre-filter to milestone-relevant sentences, then cap batch size.
            relevant = _filter_sentences_for_milestone(sentences, milestone_type)
            if not relevant:
                continue
            batch = relevant[:_MAX_SENTENCES_PER_CALL]

            expected_tag = _MILESTONE_EXPECTED_TAG.get(milestone_type)
            resolved = await _resolve_sentences(batch, expected_tag=expected_tag)

            if not resolved:
                continue

            for sentence, candidates in resolved.items():
                for candidate in candidates:
                    raw_id = candidate.get("snomed_concept_id")
                    if not raw_id:
                        continue
                    try:
                        concept_int = int(raw_id)
                    except (ValueError, TypeError):
                        continue

                    if concept_int not in milestone_concept_ids:
                        continue

                    resolver_score = float(candidate.get("score") or 0.0)
                    concept_name = candidate.get("snomed_term") or ""

                    if not deep_mode:
                        # Production path: instant regex context confidence
                        ctx_conf = _context_confidence(sentence, milestone_type)
                        if ctx_conf < 0.5 and milestone_type == "diagnosis":
                            continue
                        combined = resolver_score * ctx_conf
                        if combined >= min_score:
                            hits.append(HybridAnchorHit(
                                encounter_id=enc_id,
                                encounter_date=enc_date,
                                concept_id=raw_id,
                                concept_name=concept_name,
                                milestone_type=milestone_type,
                                resolver_score=resolver_score,
                                context_confidence=ctx_conf,
                                combined_score=combined,
                                phrase=sentence,
                                disambiguation="",
                            ))
                    else:
                        # Deep mode: queue for concurrent LLM disambiguation
                        raw_candidates.append({
                            "enc_id": enc_id,
                            "enc_date": enc_date,
                            "raw_id": raw_id,
                            "concept_name": concept_name,
                            "milestone_type": milestone_type,
                            "resolver_score": resolver_score,
                            "sentence": sentence,
                        })
                    break  # one hit per sentence per milestone type is enough

    # ------------------------------------------------------------------
    # Phase 2 (deep_mode only) — concurrent LLM disambiguation
    # ------------------------------------------------------------------
    if deep_mode and raw_candidates:
        # Rank by resolver score and cap to avoid excessive LLM cost on
        # patients with hundreds of qualifying encounters.
        top = sorted(raw_candidates, key=lambda r: -r["resolver_score"])[:_MAX_LLM_CALLS]
        logger.info(
            "search_missing_anchors: deep_mode — disambiguating %d/%d candidates concurrently",
            len(top), len(raw_candidates),
        )

        async def _disambiguate_one(rc: dict) -> tuple[dict, str]:
            label = await asyncio.to_thread(
                _disambiguate_llm, rc["sentence"], rc["concept_name"], rc["milestone_type"],
            )
            return rc, label

        results = await asyncio.gather(
            *[_disambiguate_one(rc) for rc in top],
            return_exceptions=True,
        )

        for item in results:
            if isinstance(item, BaseException):
                logger.warning(
                    "search_missing_anchors: disambiguation task failed — %r", item,
                )
                continue
            rc, disambiguation = item
            if disambiguation in ("suspected", "irrelevant"):
                logger.debug(
                    "deep audit: enc=%s milestone=%s concept=%r → suppressed (%s)",
                    rc["enc_id"], rc["milestone_type"], rc["concept_name"], disambiguation,
                )
                continue
            # Historical diagnosis is not a new anchor; historical referral/
            # treatment/specialist still counts (the event happened).
            if disambiguation == "historical" and rc["milestone_type"] == "diagnosis":
                continue
            ctx_conf = 1.0 if disambiguation == "confirmed" else 0.8
            combined = rc["resolver_score"] * ctx_conf
            if combined < min_score:
                continue
            hits.append(HybridAnchorHit(
                encounter_id=rc["enc_id"],
                encounter_date=rc["enc_date"],
                concept_id=rc["raw_id"],
                concept_name=rc["concept_name"],
                milestone_type=rc["milestone_type"],
                resolver_score=rc["resolver_score"],
                context_confidence=ctx_conf,
                combined_score=combined,
                phrase=rc["sentence"],
                disambiguation=disambiguation,
            ))

    hits.sort(key=lambda h: (h.encounter_date, -h.combined_score))
    return hits


def hits_to_anchor_entries(hits: list[HybridAnchorHit]) -> dict[str, list[dict[str, Any]]]:
    """Convert HybridAnchorHit list to the anchor dict format used by anchor_detector.

    Returns ``{"referral": [...], "diagnosis": [...], ...}`` — same shape as
    tier-1 concept anchors so results can be merged directly.
    """
    by_type: dict[str, list[dict[str, Any]]] = {
        "referral": [],
        "diagnosis": [],
        "treatment_start": [],
        "specialist_visit": [],
    }
    seen: dict[str, set[str]] = {k: set() for k in by_type}

    for hit in hits:
        mtype = hit.milestone_type
        if mtype not in by_type:
            continue
        if hit.encounter_id in seen[mtype]:
            continue
        seen[mtype].add(hit.encounter_id)
        entry: dict[str, Any] = {
            "encounter_id":     hit.encounter_id,
            "encounter_date":   hit.encounter_date,
            "concept_id":       hit.concept_id,
            "concept_name":     hit.concept_name,
            "confidence":       hit.combined_score,
            "source":           hit.source,
            "detection_method": hit.detection_method,
            "phrase_matched":   hit.phrase,
        }
        if hit.disambiguation:
            entry["disambiguation"] = hit.disambiguation
        by_type[mtype].append(entry)

    return by_type


# ---------------------------------------------------------------------------
# Public aliases — backward compatibility
# ---------------------------------------------------------------------------

#: Regex that matches confirmed-diagnosis language (production mode context check).
CONFIRMED_RE = _CONFIRMED_RE

#: Regex that matches suspected/pending language (production mode context check).
SUSPECTED_RE = _SUSPECTED_RE

#: Regex that matches historical/ambiguous language (production mode context check).
AMBIGUOUS_RE = _AMBIGUOUS_RE


def context_confidence(text: str, milestone_type: str) -> float:
    """Public wrapper around ``_context_confidence`` (production mode)."""
    return _context_confidence(text, milestone_type)


def split_sentences(text: str) -> list[str]:
    """Public wrapper around ``_split_sentences``.

    Returns clinical sentences from encounter text — use this instead of
    keyword-windowing wherever encounter text needs to be broken into units.
    """
    return _split_sentences(text)


def disambiguate_llm(sentence: str, concept_name: str, milestone_type: str) -> str:
    """Public wrapper around ``_disambiguate_llm`` for use in audit scripts."""
    return _disambiguate_llm(sentence, concept_name, milestone_type)
