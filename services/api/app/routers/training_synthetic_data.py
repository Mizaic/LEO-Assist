"""Synthetic gold-standard data generation router.

Atlas trace:
  DO: DO-236545C8
  Also implements: DO-2D2CE052, DO-54397CCD, DO-6CD07544, DO-94D87FA7, DO-A35D2D57, DO-B88D4941, DO-BA2B7A99
  DI: DI-2D9F5064, DI-37B3DC71, DI-3EA60D5A, DI-54D00E21, DI-6EFD68D0, DI-A0579B64, DI-AF5A1668, DI-D2D0117E
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-236545C8")

Extracted from services/api/app/routers/training.py (2026-07 CTO peer-review
item 2: core-api router decomposition). Pure move, no behaviour change --
existing DO/DI trace headers carried over unchanged.

Routes: synthetic-gold/stats, synthetic-gold/valuesets, synthetic-candidates (generate/delete/queue).
"""

from __future__ import annotations

import json
import hashlib
import logging
import os
import re
import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from libs.auth.org_scope import (
    CallerScope,
    get_caller_scope,
)
from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient
from app.deps import require_admin
from libs.cypher.training_candidate_queries import (
    UPSERT_TRAINING_CANDIDATE,
)
from libs.cypher.gold_label_queries import (
    UPSERT_GOLD_LABEL,
)
from libs.cypher.synthetic_candidate_queries import (
    GET_ALL_VALUESETS_RAW_JSON,
    GET_CONCEPTS_WITHOUT_SURFACE_FORMS_FOR_IDS,
    GET_ENCOUNTER_CONTEXT_CANDIDATES,
    GET_GOLD_OUTPUT_EXAMPLE_CANDIDATES,
    GET_SURFACE_FORMS_FOR_CONCEPT_IDS,
    GET_SURFACE_FORMS_FOR_GENERATION,
    GET_SURFACE_FORM_TAG_COUNTS,
    GET_SYNTHETIC_GOLD_STATS,
    GET_SYNTHETIC_GOLD_TAG_BREAKDOWN,
    GET_VALUESET_RAW_JSON,
)
from libs.ner.span_finder import find_span
from libs.nlp.sentence_splitter import (
    SentenceSplitter,
    filter_header_sentences,
    is_header_sentence,
    is_non_evidence_line,
    is_referral_procedure_phrase,
)
from libs.prompts.synthetic_ner_sentences import (
    build_synthetic_sentence_prompts,
    _strip_snomed_qualifier,
)
from libs.terminology.client import TerminologyClient, get_always_ignore_patterns
from libs.pipeline.post_processing import run_post_processing
from libs.ner.deid_validator import DeIdValidator
from libs.utils.deidentify import deidentify_text

logger = logging.getLogger(__name__)

router = APIRouter()


class SyntheticGenerationRequest(BaseModel):
    limit: int = Field(default=50, ge=1, le=50)
    sentences_per_form: int = Field(default=10, ge=1, le=10)
    semantic_tags: list[str] | None = None
    valueset_ids: list[str] | None = None
    use_derived_forms: bool = False


class SyntheticQueueRequest(BaseModel):
    limit: int = Field(default=200, ge=1, le=500)
    sentences_per_form: int = Field(default=10, ge=1, le=10)
    semantic_tags: list[str] | None = None
    valueset_ids: list[str] | None = None
    use_derived_forms: bool = False


_SYNTHETIC_SOURCE = "synthetic_llm"
_SYNTHETIC_VERIFIED_BY = "llm:claude-sonnet-4-6"
_PIPELINE_QUEUE = os.getenv("PIPELINE_QUEUE_NAME", "pipeline-jobs")
_VALID_ASSERTIONS = {
    "present",
    "absent",
    "historical",
    "possible",
    "planned",
    "hypothetical",
    "family",
    "uncertain",
    "refuted",
    "declined",
    "cancelled",
}
_CONTEXT_SPLITTER = SentenceSplitter()
_OBS_VALUE_RE = re.compile(
    r"\b(?:[<>]?\s*\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?)\b",
    re.IGNORECASE,
)
_INTERPRETATION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"\bwithin\s+(?:normal|reference)\s+(?:range|limits)\b",
            re.IGNORECASE,
        ),
        "within",
    ),
    (re.compile(r"\b(?:above|high|raised|elevated)\b", re.IGNORECASE), "above"),
    (re.compile(r"\b(?:below|low|reduced)\b", re.IGNORECASE), "below"),
    (
        re.compile(
            r"\b(?:outside\s+reference\s+range|out\s+of\s+reference\s+range)\b",
            re.IGNORECASE,
        ),
        "outside",
    ),
]
_SPECULATIVE_HEDGE_RE = re.compile(
    r"\b(?:may|might|could|possibly|potentially|likely|unlikely|suggests?|indicates?|warrants?)\b",
    re.IGNORECASE,
)
_SPECULATIVE_MODAL_RE = re.compile(
    r"\b(?:may|might|could)\s+(?:suggest|indicate|reflect|represent|imply|be|rise|increase|decrease|elevate)\b",
    re.IGNORECASE,
)
_CONDITIONAL_RE = re.compile(r"\bif\b.{0,120}(?:,|\bthen\b)", re.IGNORECASE)
_EDUCATIONAL_FRAMING_RE = re.compile(
    r"\b(?:given\s+the\s+clinical\s+picture|in\s+the\s+context\s+of|depending\s+on)\b",
    re.IGNORECASE,
)
_FUTURE_TRIGGER_RE = re.compile(
    r"\b(?:develops?|worsens?|deteriorates?|later|future|risk|review)\b",
    re.IGNORECASE,
)
_ABSENT_CUE_RE = re.compile(
    r"\b(?:no|not|without|denies?|denied|negative\s+for|free\s+of|absence\s+of)\b",
    re.IGNORECASE,
)
# Explicit past-time markers that genuinely indicate a historical assertion.
# "following" and "after" are intentionally excluded — they describe temporal
# sequencing of a procedure and do not make the coded entity historical.
_HISTORICAL_CUE_RE = re.compile(
    r"\b(?:"
    r"history\s+of"
    r"|previous(?:ly)?"
    r"|prior\s+(?:to\s+)?(?:this\s+)?"
    r"|background\s+of"
    r"|known\s+(?:history\s+of\s+)?"
    r"|formerly"
    r"|(?:was|were)\s+diagnosed\s+with"
    r"|(?:diagnosed|treated)\s+in\s+\d{4}"
    r"|\d+\s+(?:year|month|week)s?\s+ago"
    r"|in\s+(?:19|20)\d{2}"
    r")\b",
    re.IGNORECASE,
)
_PLANNED_PROCEDURE_CUE_RE = re.compile(
    r"\b(?:to\s+be\s+rechecked|to\s+be\s+repeated|for\s+repeat|repeat\s+test|recheck(?:ed)?|retest)\b",
    re.IGNORECASE,
)


def _normalise_semantic_tag(tag: str | None) -> str:
    raw = str(tag or "finding").strip().lower()
    if not raw:
        return "finding"
    return raw.replace("-", "_").replace(" ", "_").replace("/", "_")


def _extract_concept_ids_from_valuesets(
    client: Any, valueset_ids: list[str]
) -> list[str]:
    """Return deduplicated SNOMED concept IDs for all given valueset IDs.

    ValueSet concept lists live in the rawJson FHIR compose block; we parse
    them in Python because Cypher has no native JSON-parsing support.
    """
    import json as _json

    ids: list[str] = [v for v in valueset_ids if v]
    if not ids:
        return []
    with client.session() as session:
        rows = [dict(r) for r in session.run(GET_VALUESET_RAW_JSON, valueset_ids=ids)]
    seen: set[str] = set()
    concept_ids: list[str] = []
    for row in rows:
        raw = row.get("raw_json") or "{}"
        try:
            parsed = _json.loads(raw)
        except Exception:
            continue
        includes = (parsed.get("compose") or parsed).get("include") or []
        for inc in includes:
            for c in inc.get("concept") or []:
                code = str(c.get("code") or "").strip()
                if code and code not in seen:
                    seen.add(code)
                    concept_ids.append(code)
    return concept_ids


def _load_valueset_prompt_context(
    client: Any, valueset_ids: list[str]
) -> tuple[list[str], list[str]]:
    """Return (valueset titles, domain PT strings) for prompt conditioning."""
    import json as _json

    ids = [v for v in valueset_ids if v]
    if not ids:
        return [], []
    with client.session() as session:
        rows = [dict(r) for r in session.run(GET_VALUESET_RAW_JSON, valueset_ids=ids)]
    titles_by_id: dict[str, str] = {}
    terms: set[str] = set()
    for row in rows:
        vid = str(row.get("id") or "").strip()
        if vid and vid not in titles_by_id:
            titles_by_id[vid] = str(row.get("title") or vid).strip()
        raw = row.get("raw_json") or "{}"
        try:
            parsed = _json.loads(raw)
        except Exception:
            continue
        includes = (parsed.get("compose") or parsed).get("include") or []
        for inc in includes:
            for c in inc.get("concept") or []:
                display = str(c.get("display") or "").strip()
                if display:
                    cleaned = _strip_snomed_qualifier(display)
                    if cleaned and len(cleaned) > 1:
                        terms.add(cleaned)
    return list(titles_by_id.values()), sorted(terms)


def _count_exact_phrase(text: str, phrase: str) -> int:
    if not text or not phrase:
        return 0
    pattern = re.compile(rf"(?<!\w){re.escape(phrase)}(?!\w)", re.IGNORECASE)
    return len(pattern.findall(text))


def _safe_parse_json_array(raw_text: str) -> list[dict[str, Any]]:
    text = str(raw_text or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [x for x in parsed if isinstance(x, dict)]
    except Exception:
        pass
    match = re.search(r"\[\s*\{.*\}\s*\]", text, re.DOTALL)
    if not match:
        return []
    try:
        parsed = json.loads(match.group(0))
        if isinstance(parsed, list):
            return [x for x in parsed if isinstance(x, dict)]
    except Exception:
        return []
    return []


def _is_synthetic_non_evidence_sentence(text: str) -> bool:
    sentence = str(text or "").strip()
    if not sentence:
        return True
    # Only apply the specific high-precision phrase blocklist here — NOT the
    # broad structural patterns from is_non_evidence_line (e.g.
    # "^(Discussed|Advised|Counselled)") which are designed for runtime
    # encounter parsing and are too aggressive for synthetic sentence validation.
    return any(pattern.search(sentence) for pattern in get_always_ignore_patterns())


def _has_observation_value(text: str) -> bool:
    return bool(_OBS_VALUE_RE.search(str(text or "")))


def _is_speculative_or_educational(sentence: str) -> bool:
    text = str(sentence or "").strip()
    if not text:
        return False
    has_hedge = bool(_SPECULATIVE_HEDGE_RE.search(text))
    has_conditional = bool(_CONDITIONAL_RE.search(text))
    has_educational_framing = bool(_EDUCATIONAL_FRAMING_RE.search(text))
    has_future_trigger = bool(_FUTURE_TRIGGER_RE.search(text))
    has_value = _has_observation_value(text)
    if has_conditional and has_hedge:
        return True
    if _SPECULATIVE_MODAL_RE.search(text):
        return True
    if has_educational_framing and has_hedge:
        return True
    if has_future_trigger and has_hedge and has_value:
        return True
    # Broad catch-all for speculative/value statements (e.g. "possibly around 90 U/L").
    if has_hedge and has_value:
        return True
    return False


def _has_absent_evidence(sentence: str) -> bool:
    return bool(_ABSENT_CUE_RE.search(str(sentence or "")))


def _has_historical_evidence(sentence: str) -> bool:
    """Return True only when the sentence contains an explicit past-time marker.

    Words like 'following' and 'after' are excluded because they describe
    procedural sequencing, not temporal distance from the present.
    """
    return bool(_HISTORICAL_CUE_RE.search(str(sentence or "")))


def _is_invalid_observable_assertion(semantic_tag: str, assertion: str) -> bool:
    tag = _normalise_semantic_tag(semantic_tag)
    val = str(assertion or "").strip().lower()
    return tag == "observable_entity" and val == "planned"


def _is_mismatched_semantic_sentence(semantic_tag: str, sentence: str) -> bool:
    tag = _normalise_semantic_tag(semantic_tag)
    text = str(sentence or "")
    if tag in {"finding", "disorder"} and (
        is_referral_procedure_phrase(text) or _PLANNED_PROCEDURE_CUE_RE.search(text)
    ):
        return True
    return False


def _detect_interpretation_phrase(sentence: str) -> tuple[str, int, int, str] | None:
    raw = str(sentence or "")
    for pattern, key in _INTERPRETATION_PATTERNS:
        match = pattern.search(raw)
        if match:
            return match.group(0), match.start(), match.end(), key
    return None


def _pick_related_finding(
    interpreted_by_findings: list[dict[str, Any]],
    interpretation_key: str,
) -> dict[str, Any] | None:
    key = interpretation_key.strip().lower()
    if not interpreted_by_findings:
        return None
    if key == "within":
        preferred_tokens = (
            "within reference range",
            "within normal range",
            "within normal limits",
            "level (finding)",
            "normal",
        )
    elif key == "above":
        preferred_tokens = (
            "above reference range",
            "above upper limit of normal",
            "upper limit of normal",
            "high",
            "raised",
            "elevated",
            "outside reference range",
            "out of reference range",
            "abnormal",
        )
    elif key == "below":
        preferred_tokens = (
            "below reference range",
            "below lower limit of normal",
            "lower limit of normal",
            "low",
            "reduced",
            "outside reference range",
            "out of reference range",
            "abnormal",
        )
    else:
        preferred_tokens = (
            "outside reference range",
            "out of reference range",
            "abnormal",
            "high",
            "low",
        )

    def _score(item: dict[str, Any]) -> tuple[int, int]:
        fsn = str(item.get("fsn") or "").lower()
        best = 0
        for idx, token in enumerate(preferred_tokens):
            if token in fsn:
                best = max(best, len(preferred_tokens) - idx)
        # Secondary preference for finding-tagged concepts only.
        sem = _normalise_semantic_tag(str(item.get("semantic_tag") or ""))
        if sem != "finding":
            best = 0
        return (best, len(fsn))

    ranked = sorted(interpreted_by_findings, key=_score, reverse=True)
    if not ranked:
        return None
    top = ranked[0]
    if _score(top)[0] <= 0:
        return None
    return top


def _extract_context_snippet(encounter_text: str, max_chars: int = 500) -> str | None:
    """Extract a clinically useful snippet while dropping admin/header noise."""
    if not encounter_text:
        return None
    deid = deidentify_text(encounter_text, ner=True).strip()
    if not deid:
        return None
    # First pass: strip clearly administrative lines before sentence splitting.
    cleaned_lines = []
    for raw_line in deid.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if is_header_sentence(line):
            continue
        if is_non_evidence_line(line):
            continue
        cleaned_lines.append(line)
    if not cleaned_lines:
        return None
    cleaned_text = "\n".join(cleaned_lines)
    chunks = _CONTEXT_SPLITTER.split(cleaned_text)
    if not chunks:
        return None
    chunks = filter_header_sentences(chunks)
    clinical_lines = [
        c.text.strip()
        for c in chunks
        if c.text.strip() and not is_non_evidence_line(c.text)
    ]
    if not clinical_lines:
        return None
    snippet = " ".join(clinical_lines[:3])
    snippet = re.sub(r"\s+", " ", snippet).strip()
    if len(snippet) < 40:
        return None
    return snippet[:max_chars].strip()


def _pick_diverse_context_examples(
    rows: list[dict[str, Any]], cap: int = 10
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen_patients: set[str] = set()
    seen_months: set[str] = set()

    # Pass 1: maximise patient + month diversity.
    for row in rows:
        pid = str(row.get("patient_id") or "")
        month = str(row.get("month_bucket") or "")
        if pid in seen_patients or month in seen_months:
            continue
        selected.append(row)
        seen_patients.add(pid)
        seen_months.add(month)
        if len(selected) >= cap:
            return selected

    # Pass 2: patient diversity only.
    for row in rows:
        if len(selected) >= cap:
            return selected
        pid = str(row.get("patient_id") or "")
        if pid in seen_patients:
            continue
        if row in selected:
            continue
        selected.append(row)
        seen_patients.add(pid)

    # Pass 3: fill remaining.
    for row in rows:
        if len(selected) >= cap:
            break
        if row in selected:
            continue
        selected.append(row)
    return selected


def _pick_similarity_context_examples(
    rows: list[dict[str, Any]],
    query_terms: list[str],
    cap: int = 10,
) -> list[str]:
    """Pick encounter snippets most similar to the target terms.

    Uses full de-identified encounter text for lexical matching so prompt
    examples reflect real note phrasing for this specific term/domain.
    """
    cleaned_terms = [str(t).strip().lower() for t in query_terms if str(t).strip()]
    if not cleaned_terms:
        return []
    token_stop = {
        "the",
        "and",
        "with",
        "from",
        "that",
        "this",
        "was",
        "were",
        "for",
        "has",
        "have",
        "had",
        "of",
        "in",
        "on",
        "to",
    }
    tokens: set[str] = set()
    for term in cleaned_terms:
        for tok in re.findall(r"[a-z0-9]{3,}", term):
            if tok not in token_stop:
                tokens.add(tok)
    ranked: list[tuple[int, str]] = []
    for row in rows:
        snippet = str(row.get("_context_snippet") or "").strip()
        text_l = str(row.get("_text_lower") or "").strip()
        if not snippet or not text_l:
            continue
        score = 0
        for phrase in cleaned_terms:
            if len(phrase) >= 4 and phrase in text_l:
                score += 12
        for tok in tokens:
            if tok in text_l:
                score += 1
        if score <= 0:
            continue
        ranked.append((score, snippet))
    if not ranked:
        return []
    ranked.sort(key=lambda x: x[0], reverse=True)
    picked: list[str] = []
    seen: set[str] = set()
    for _, snippet in ranked:
        k = snippet.lower()
        if k in seen:
            continue
        seen.add(k)
        picked.append(snippet)
        if len(picked) >= cap:
            break
    return picked


def _extract_gold_output_examples(
    rows: list[dict[str, Any]],
    cap: int = 5,
) -> list[dict[str, str]]:
    examples: list[dict[str, str]] = []
    seen_sentences: set[str] = set()
    for row in rows:
        sentence = deidentify_text(str(row.get("text") or ""), ner=True).strip()
        if not sentence:
            continue
        sentence_key = sentence.lower()
        if sentence_key in seen_sentences:
            continue
        if _is_synthetic_non_evidence_sentence(sentence):
            continue
        if _is_speculative_or_educational(sentence):
            continue
        entities = _safe_parse_json_array(str(row.get("entities_json") or "[]"))
        assertion = "present"
        for entity in entities:
            raw_assertion = str(entity.get("assertion") or "").strip().lower()
            if raw_assertion in _VALID_ASSERTIONS:
                assertion = raw_assertion
                break
        examples.append({"sentence": sentence, "assertion": assertion})
        seen_sentences.add(sentence_key)
        if len(examples) >= cap:
            break
    return examples


@router.get("/synthetic-gold/stats")
def get_synthetic_gold_stats(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            stats_row = session.run(GET_SYNTHETIC_GOLD_STATS).single()
            tag_rows = [dict(r) for r in session.run(GET_SYNTHETIC_GOLD_TAG_BREAKDOWN)]
            option_rows = [dict(r) for r in session.run(GET_SURFACE_FORM_TAG_COUNTS)]
            labels_row = session.run(
                """
                MATCH (g:GoldLabel)
                WHERE g.source = $source
                RETURN count(g) AS total
                """,
                source=_SYNTHETIC_SOURCE,
            ).single()
        stats_payload = dict(stats_row) if stats_row else {}
        return {
            "total_surface_forms": int(stats_payload.get("total_surface_forms") or 0),
            "covered_surface_forms": int(
                stats_payload.get("covered_surface_forms") or 0
            ),
            "synthetic_gold_labels": int((labels_row or {}).get("total") or 0),
            "tag_breakdown": tag_rows,
            "tag_options": option_rows,
        }
    finally:
        client.close()


@router.get("/synthetic-gold/valuesets")
def get_synthetic_gold_valuesets(
    scope: CallerScope = Depends(get_caller_scope),
) -> dict[str, Any]:
    """Return all NCDA value sets with concept count and surface-form coverage."""
    import json as _json

    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            vs_rows = [dict(r) for r in session.run(GET_ALL_VALUESETS_RAW_JSON)]
            sf_count_rows = session.run(
                """
                MATCH (sf:SurfaceForm)-[:MAPS_TO]->(c:Concept)
                WHERE coalesce(sf.status, 'active') = 'active'
                RETURN toString(c.id) AS concept_id, count(sf) AS sf_count
                """
            )
            sf_map: dict[str, int] = {
                str(r["concept_id"]): int(r["sf_count"]) for r in sf_count_rows
            }
    finally:
        client.close()

    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for row in vs_rows:
        vid = str(row.get("id") or "")
        if vid in seen:
            continue
        seen.add(vid)
        raw = row.get("raw_json") or "{}"
        try:
            parsed = _json.loads(raw)
        except Exception:
            parsed = {}
        includes = (parsed.get("compose") or parsed).get("include") or []
        concepts: list[str] = []
        for inc in includes:
            for c in inc.get("concept") or []:
                code = str(c.get("code") or "").strip()
                if code:
                    concepts.append(code)
        with_sf = [code for code in concepts if sf_map.get(code, 0) > 0]
        result.append(
            {
                "id": vid,
                "title": str(row.get("title") or vid),
                "concept_count": len(concepts),
                "sf_count": len(with_sf),
                "no_sf_count": len(concepts) - len(with_sf),
                "derivable_count": len(concepts) - len(with_sf),
            }
        )
    result.sort(key=lambda x: x["id"])
    return {"valuesets": result}


@router.post("/synthetic-candidates")
def generate_synthetic_candidates(
    body: SyntheticGenerationRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    from libs.llm_client.factory import create_llm

    semantic_tags = [
        _normalise_semantic_tag(str(tag))
        for tag in (body.semantic_tags or [])
        if str(tag).strip()
    ]

    validator = DeIdValidator()
    llm = create_llm(provider="aws", tier="big")
    terminology = TerminologyClient()

    counts = {
        "forms_processed": 0,
        "candidates_written": 0,
        "gold_labels_written": 0,
        "forms_zero_written": 0,
        "context_examples_sampled": 0,
        "context_examples_used": 0,
        "context_examples_preview": [],
        "skipped_phi": 0,
        "skipped_no_match": 0,
        "skipped_both_forms": 0,
        "enriched_multi_entity": 0,
        "derived_forms_used": 0,
        "skipped_non_evidence": 0,
        "skipped_speculative": 0,
        "skipped_planned_observable": 0,
        "skipped_observable_no_value": 0,
        "skipped_semantic_mismatch": 0,
        "skipped_empty": 0,
        "errors": [],
    }

    client = KnowledgeGraphClient()
    pg_client = PatientGraphClient()
    related_finding_cache: dict[str, list[dict[str, Any]]] = {}
    gold_examples_cache: dict[str, list[dict[str, str]]] = {}
    try:
        with pg_client.session() as pg_session:
            raw_context_rows = [
                dict(r)
                for r in pg_session.run(
                    GET_ENCOUNTER_CONTEXT_CANDIDATES,
                    limit=5000,
                )
            ]
        prepared_context_rows: list[dict[str, Any]] = []
        for row in raw_context_rows:
            text = str(row.get("encounter_text") or "").strip()
            if not text:
                continue
            snippet = _extract_context_snippet(text, max_chars=500)
            if not snippet:
                continue
            enriched = dict(row)
            enriched["_text_lower"] = text.lower()
            enriched["_context_snippet"] = snippet
            prepared_context_rows.append(enriched)

        picked_rows = _pick_diverse_context_examples(prepared_context_rows, cap=10)
        fallback_context_examples = [
            str(r.get("_context_snippet") or "").strip()
            for r in picked_rows
            if str(r.get("_context_snippet") or "").strip()
        ][:10]
        counts["context_examples_sampled"] = len(fallback_context_examples)
        counts["context_examples_used"] = len(fallback_context_examples)
        counts["context_examples_preview"] = fallback_context_examples[:2]

        # Resolve valueset concept IDs so we can filter surface forms.
        valueset_concept_ids: list[str] | None = None
        valueset_scope_titles: list[str] = []
        domain_preferred_terms: list[str] = []
        if body.valueset_ids:
            valueset_concept_ids = _extract_concept_ids_from_valuesets(
                client, body.valueset_ids
            )
            valueset_scope_titles, domain_preferred_terms = (
                _load_valueset_prompt_context(client, body.valueset_ids)
            )

        with client.session() as session:
            if valueset_concept_ids is not None:
                form_rows = [
                    dict(r)
                    for r in session.run(
                        GET_SURFACE_FORMS_FOR_CONCEPT_IDS,
                        concept_ids=valueset_concept_ids,
                        limit=body.limit,
                        semantic_tags=semantic_tags,
                    )
                ]
                # For valueset concepts that have no surface forms, derive a
                # form from the concept's preferred term so generation still
                # produces training data for those concepts.
                if body.use_derived_forms:
                    remaining = max(0, body.limit - len(form_rows))
                    if remaining > 0:
                        derived_rows = [
                            dict(r)
                            for r in session.run(
                                GET_CONCEPTS_WITHOUT_SURFACE_FORMS_FOR_IDS,
                                concept_ids=valueset_concept_ids,
                                limit=remaining,
                                semantic_tags=semantic_tags,
                            )
                        ]
                        form_rows = form_rows + derived_rows
                        counts["derived_forms_used"] = len(derived_rows)
            else:
                form_rows = [
                    dict(r)
                    for r in session.run(
                        GET_SURFACE_FORMS_FOR_GENERATION,
                        limit=body.limit,
                        semantic_tags=semantic_tags,
                    )
                ]
            # Build a lookup so secondary entity metadata is available when a
            # generated sentence contains more than one known surface form.
            form_to_row: dict[str, dict] = {
                str(r.get("form") or "").strip(): dict(r)
                for r in form_rows
                if str(r.get("form") or "").strip()
            }
            known_forms = list(form_to_row.keys())
            for row in form_rows:
                counts["forms_processed"] += 1
                form = str(row.get("form") or "").strip()
                if not form:
                    counts["skipped_empty"] += 1
                    continue
                preferred_term = str(row.get("preferred_term") or "")
                concept_id = str(row.get("concept_id") or "")
                semantic_tag = _normalise_semantic_tag(
                    str(row.get("semantic_tag") or "")
                )
                gold_output_examples = gold_examples_cache.get(semantic_tag)
                if gold_output_examples is None:
                    semantic_tag_token = f'"semantic_tag": "{semantic_tag}"'.lower()
                    gold_rows = [
                        dict(r)
                        for r in session.run(
                            GET_GOLD_OUTPUT_EXAMPLE_CANDIDATES,
                            semantic_tag_token=semantic_tag_token,
                            limit=120,
                        )
                    ]
                    gold_output_examples = _extract_gold_output_examples(
                        gold_rows, cap=5
                    )
                    gold_examples_cache[semantic_tag] = gold_output_examples

                similarity_context = _pick_similarity_context_examples(
                    prepared_context_rows,
                    query_terms=[form, preferred_term],
                    cap=10,
                )
                context_examples = (
                    similarity_context
                    if similarity_context
                    else fallback_context_examples
                )

                system_prompt, user_prompt, clean_preferred_term = (
                    build_synthetic_sentence_prompts(
                        surface_form=form,
                        preferred_term=preferred_term,
                        concept_id=concept_id,
                        semantic_tag=semantic_tag,
                        n_sentences=body.sentences_per_form,
                        context_examples=context_examples,
                        gold_output_examples=gold_output_examples,
                        valueset_scope_titles=valueset_scope_titles,
                        domain_preferred_terms=domain_preferred_terms,
                    )
                )
                target_count = body.sentences_per_form
                accepted_for_form = 0
                max_attempts = 3
                for attempt_idx in range(max_attempts):
                    if accepted_for_form >= target_count:
                        break
                    corrective_block = ""
                    if attempt_idx > 0:
                        corrective_block = (
                            "\n\nRETRY INSTRUCTIONS:\n"
                            "- Previous outputs were filtered by deterministic guards.\n"
                            "- Avoid administrative/template lines.\n"
                            "- Avoid referral, recheck, repeat-test, or planned-action wording unless semantic tag is procedure.\n"
                            "- Keep semantic meaning aligned to the target semantic tag.\n"
                            "- Only produce definitive clinical evidence statements.\n"
                        )
                    attempt_prompt = f"{user_prompt}{corrective_block}"
                    try:
                        response = llm.converse(
                            system=system_prompt,
                            messages=[{"role": "user", "content": attempt_prompt}],
                            max_tokens=2200,
                            temperature=0.4,
                            agent_task="training_synthetic_sentence_generator",
                        )
                        sentences = _safe_parse_json_array(response.text)
                    except Exception as exc:
                        counts["errors"].append(f"llm:{form[:40]}: {exc}")
                        break

                    for item in sentences[:target_count]:
                        if accepted_for_form >= target_count:
                            break
                        sentence = str(item.get("sentence") or "").strip()
                        if not sentence:
                            counts["skipped_empty"] += 1
                            continue
                        assertion = (
                            str(item.get("assertion") or "present").strip().lower()
                        )
                        if assertion not in _VALID_ASSERTIONS:
                            assertion = "present"
                        if _is_invalid_observable_assertion(semantic_tag, assertion):
                            counts["skipped_planned_observable"] += 1
                            continue

                        deid_sentence = deidentify_text(sentence, ner=True)
                        if assertion == "absent" and not _has_absent_evidence(
                            deid_sentence
                        ):
                            assertion = "present"
                        if assertion == "historical" and not _has_historical_evidence(
                            deid_sentence
                        ):
                            assertion = "present"
                        if _is_mismatched_semantic_sentence(
                            semantic_tag, deid_sentence
                        ):
                            counts["skipped_semantic_mismatch"] += 1
                            continue
                        if _is_synthetic_non_evidence_sentence(deid_sentence):
                            counts["skipped_non_evidence"] += 1
                            continue
                        if _is_speculative_or_educational(deid_sentence):
                            counts["skipped_speculative"] += 1
                            continue
                        if semantic_tag == "observable_entity" and (
                            not _has_observation_value(deid_sentence)
                            or is_referral_procedure_phrase(deid_sentence)
                        ):
                            counts["skipped_observable_no_value"] += 1
                            continue
                        # Hard guard: exactly one occurrence of the target mention.
                        mention_count = _count_exact_phrase(deid_sentence, form)
                        if mention_count != 1:
                            counts["skipped_no_match"] += 1
                            continue
                        # Reject "AG - Atrophic gastritis..." style sentences where
                        # the model has written BOTH the abbreviation and the full
                        # preferred term in the same sentence.
                        if (
                            clean_preferred_term
                            and clean_preferred_term.lower() != form.lower()
                            and _count_exact_phrase(deid_sentence, clean_preferred_term)
                            > 0
                            and _count_exact_phrase(deid_sentence, form) > 0
                        ):
                            counts["skipped_both_forms"] += 1
                            continue
                        span = find_span(deid_sentence, form, clean_preferred_term)
                        if span is None:
                            counts["skipped_no_match"] += 1
                            continue
                        start, end = span
                        mention_text = deid_sentence[start:end]

                        entities_payload: list[dict[str, Any]] = [
                            {
                                "text": mention_text,
                                "label": semantic_tag,
                                "semantic_tag": semantic_tag,
                                "start": start,
                                "end": end,
                                "assertion": assertion,
                                "snomed_concept_id": concept_id,
                            }
                        ]

                        # Co-occurring known surface forms: label them all so the
                        # NER model is never trained with an unlabelled entity in
                        # the same sentence (which would be a false negative).
                        has_co_occurrence = False
                        for other in known_forms:
                            if other.lower() == form.lower():
                                continue
                            if _count_exact_phrase(deid_sentence, other) != 1:
                                continue
                            other_row = form_to_row.get(other) or {}
                            other_tag = _normalise_semantic_tag(
                                str(other_row.get("semantic_tag") or "")
                            )
                            other_concept = str(other_row.get("concept_id") or "")
                            if not other_tag or not other_concept:
                                continue
                            # Skip observable co-occurrences without a numeric value
                            if (
                                other_tag == "observable_entity"
                                and not _has_observation_value(deid_sentence)
                            ):
                                continue
                            other_span = find_span(deid_sentence, other)
                            if other_span is None:
                                continue
                            os_, oe_ = other_span
                            other_assertion = (
                                "absent"
                                if _has_absent_evidence(deid_sentence)
                                else "present"
                            )
                            entities_payload.append(
                                {
                                    "text": deid_sentence[os_:oe_],
                                    "label": other_tag,
                                    "semantic_tag": other_tag,
                                    "start": os_,
                                    "end": oe_,
                                    "assertion": other_assertion,
                                    "snomed_concept_id": other_concept,
                                }
                            )
                            has_co_occurrence = True
                        if has_co_occurrence:
                            counts["enriched_multi_entity"] = (
                                counts.get("enriched_multi_entity", 0) + 1
                            )

                        interpretation = _detect_interpretation_phrase(deid_sentence)
                        if semantic_tag == "observable_entity":
                            if interpretation:
                                phrase_text, i_start, i_end, qualifier = interpretation
                                related = related_finding_cache.get(concept_id)
                                if related is None:
                                    related_resp = terminology.get_related(concept_id)
                                    related = list(
                                        related_resp.get("interpreted_by_findings")
                                        or []
                                    )
                                    related_finding_cache[concept_id] = related
                                finding = _pick_related_finding(related, qualifier)
                                if finding:
                                    entities_payload.append(
                                        {
                                            "text": phrase_text,
                                            "label": "finding",
                                            "semantic_tag": "finding",
                                            "start": i_start,
                                            "end": i_end,
                                            "assertion": assertion,
                                            "snomed_concept_id": str(
                                                finding.get("id") or ""
                                            ),
                                        }
                                    )
                        elif (
                            semantic_tag in {"finding", "disorder"}
                            and interpretation
                            and _has_observation_value(deid_sentence)
                        ):
                            # If LLM anchored on finding/disorder for a measurable lab
                            # statement, add an observable companion entity too.
                            try:
                                resolved_obs = terminology.resolve_one(
                                    mention_text or form,
                                    label="observable_entity",
                                )
                            except Exception:
                                resolved_obs = None
                            if (
                                resolved_obs
                                and str(resolved_obs.concept_id or "").strip()
                            ):
                                entities_payload.append(
                                    {
                                        "text": mention_text,
                                        "label": "observable_entity",
                                        "semantic_tag": "observable_entity",
                                        "start": start,
                                        "end": end,
                                        "assertion": "present",
                                        "snomed_concept_id": str(
                                            resolved_obs.concept_id
                                        ),
                                    }
                                )

                        try:
                            entities_payload = run_post_processing(
                                deid_sentence,
                                entities_payload,
                                rules=None,
                                enable_disorder_gate=False,
                                coding_mode="hitl",
                            )
                        except Exception as exc:
                            counts["errors"].append(f"post_process:{form[:40]}: {exc}")
                            continue
                        if not entities_payload:
                            counts["skipped_non_evidence"] += 1
                            continue

                        record_issues = validator.check_record(
                            {
                                "text": deid_sentence,
                                "entities": [
                                    {
                                        "entity_id": str(i),
                                        "text": str(e.get("text") or ""),
                                    }
                                    for i, e in enumerate(entities_payload)
                                ],
                                "metadata": {},
                            }
                        )
                        if record_issues:
                            counts["skipped_phi"] += 1
                            continue

                        candidate_id = hashlib.sha256(
                            deid_sentence.encode("utf-8")
                        ).hexdigest()
                        label_id = f"synthetic-{uuid.uuid4().hex}"
                        entities_json = json.dumps(
                            entities_payload,
                            ensure_ascii=False,
                        )

                        session.run(
                            UPSERT_TRAINING_CANDIDATE,
                            candidate_id=candidate_id,
                            text=deid_sentence,
                            entities_json=entities_json,
                            source=_SYNTHETIC_SOURCE,
                            status="completed",
                            schema_version="v4",
                        )
                        session.run(
                            UPSERT_GOLD_LABEL,
                            label_id=label_id,
                            text=deid_sentence,
                            entities_json=entities_json,
                            quality_score=0.85,
                            source=_SYNTHETIC_SOURCE,
                            verified_by=_SYNTHETIC_VERIFIED_BY,
                            candidate_id=candidate_id,
                            schema_version="v4",
                        )
                        counts["candidates_written"] += 1
                        counts["gold_labels_written"] += 1
                        accepted_for_form += 1
                if accepted_for_form == 0:
                    counts["forms_zero_written"] += 1
    finally:
        pg_client.close()
        client.close()

    return counts


@router.delete("/synthetic-candidates")
def delete_synthetic_candidates(
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            row = session.run(
                """
                MATCH (g:GoldLabel {source: $source})
                WITH collect(g) AS labels
                RETURN size(labels) AS gold_labels
                """,
                source=_SYNTHETIC_SOURCE,
            ).single()
            gold_labels = int((row or {}).get("gold_labels") or 0)
            row = session.run(
                """
                MATCH (c:TrainingCandidate {source: $source})
                RETURN count(c) AS candidates
                """,
                source=_SYNTHETIC_SOURCE,
            ).single()
            candidates = int((row or {}).get("candidates") or 0)
            session.run(
                """
                MATCH (g:GoldLabel {source: $source})
                DETACH DELETE g
                """,
                source=_SYNTHETIC_SOURCE,
            )
            session.run(
                """
                MATCH (c:TrainingCandidate {source: $source})
                DETACH DELETE c
                """,
                source=_SYNTHETIC_SOURCE,
            )
        return {
            "deleted_gold_labels": gold_labels,
            "deleted_candidates": candidates,
        }
    finally:
        client.close()


@router.post("/synthetic-candidates/queue")
async def queue_synthetic_candidates(
    body: SyntheticQueueRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict[str, Any]:
    from libs.message_bus.base import Message
    from libs.message_bus.factory import create_message_bus

    semantic_tags = [
        _normalise_semantic_tag(str(tag))
        for tag in (body.semantic_tags or [])
        if str(tag).strip()
    ]
    client = KnowledgeGraphClient()
    valueset_concept_ids: list[str] | None = None
    if body.valueset_ids:
        valueset_concept_ids = _extract_concept_ids_from_valuesets(
            client, body.valueset_ids
        )
    try:
        with client.session() as session:
            if valueset_concept_ids is not None:
                rows = [
                    dict(r)
                    for r in session.run(
                        GET_SURFACE_FORMS_FOR_CONCEPT_IDS,
                        concept_ids=valueset_concept_ids,
                        limit=body.limit,
                        semantic_tags=semantic_tags,
                    )
                ]
                if body.use_derived_forms:
                    remaining = max(0, body.limit - len(rows))
                    if remaining > 0:
                        derived = [
                            dict(r)
                            for r in session.run(
                                GET_CONCEPTS_WITHOUT_SURFACE_FORMS_FOR_IDS,
                                concept_ids=valueset_concept_ids,
                                limit=remaining,
                                semantic_tags=semantic_tags,
                            )
                        ]
                        rows = rows + derived
            else:
                rows = [
                    dict(r)
                    for r in session.run(
                        GET_SURFACE_FORMS_FOR_GENERATION,
                        limit=body.limit,
                        semantic_tags=semantic_tags,
                    )
                ]
    finally:
        client.close()

    if not rows:
        return {"queued": False, "estimated_forms": 0, "queued_batches": 0}

    batches = [rows[i : i + 50] for i in range(0, len(rows), 50)]
    bus = create_message_bus()
    try:
        for idx, batch in enumerate(batches):
            message = Message(
                body={
                    "event_type": "synthetic-gold-generate",
                    "batch_index": idx,
                    "payload": {
                        "surface_forms": batch,
                        "sentences_per_form": body.sentences_per_form,
                        "semantic_tags": semantic_tags,
                    },
                },
                correlation_id=f"synthetic-{uuid.uuid4().hex}",
                subject="synthetic-gold-generate",
            )
            await bus.send(_PIPELINE_QUEUE, message)
    finally:
        await bus.close()

    return {
        "queued": True,
        "estimated_forms": len(rows),
        "queued_batches": len(batches),
    }
