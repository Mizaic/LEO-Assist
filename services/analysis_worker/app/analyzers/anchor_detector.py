"""Anchor detection: finds referral, diagnosis, and treatment milestones.

Three-tier cascade
------------------
Tier 1 — :DOCUMENTS + SNOMED concept IDs (highest precision)
    The coding worker writes DOCUMENTS relationships after extracting and
    resolving SNOMED concepts.  Each coded concept is matched against the
    NCDA milestone domain sets (``libs.domains.ncda_concept_sets``).

Tier 2 — Hybrid terminology search (catches what the coding worker missed)
    For milestone types *still* absent after Tier 1, we apply lightweight
    keyword-windowing on raw encounter text to extract candidate phrases, then
    call ``POST /terminology/resolve`` which fuses exact, surface-form,
    fulltext, and vector branches.  Returned concept IDs are checked against
    the same milestone concept sets.  A context-confidence modifier downgrades
    "suspected / awaiting" language so it does not incorrectly become a
    "diagnosis" anchor.

    This tier is critical for subtle expressions:
    • "Biopsy confirmed squamous cell carcinoma" (diagnosis — not just
      "biopsy awaited")
    • "Commenced pembrolizumab" (treatment — not captured if the exact
      concept was missed by extraction)

Tier 3 — Regex patterns on raw text (legacy / pre-coding fallback)
    Fires automatically when the patient has *zero* :DOCUMENTS relationships
    at all (e.g. before the coding worker has run).  Kept for backward-
    compatibility; should rarely fire once the pipeline is stable.

Domain → milestone mapping
  fast_track_referrals  → "referral"
  cancer_types          → "diagnosis"
  treatment             → "treatment_start"
  seen_by_specialist    → "specialist_visit"
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from libs.domains.ncda_concept_sets import (
    CANCER_TYPE_IDS,
    FAST_TRACK_REFERRAL_IDS,
    MILESTONE_CONCEPT_SETS,
    SEEN_BY_SPECIALIST_IDS,
    TREATMENT_IDS,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex fallback — used ONLY when no DOCUMENTS exist in the patient graph
# ---------------------------------------------------------------------------
_FAST_TRACK_RE = re.compile(
    r"(?i)fast\s*track\s*referral\s+for\s+suspected\s+(\S[\w\s()]+?)(?:\s*\(|$)"
)
_2WW_RE = re.compile(
    r"(?i)(?:2ww|two\s*week\s*wait|2\s*week\s*wait)\s+(?:referral\s+)?(?:to\s+)?(\w[\w\s]*?)(?:\s*[-.]|$)"
)
_CANCER_TYPE_MAP = {
    "lower gi": "lower gastrointestinal",
    "upper gi": "upper GI",
    "colorectal": "colorectal",
    "bowel": "colorectal",
    "breast": "breast",
    "lung": "lung",
    "skin": "skin",
    "urolog": "urological",
    "gynae": "gynaecological",
    "haematol": "haematology",
    "head and neck": "head and neck",
}
_DIAGNOSIS_RE = re.compile(
    r"(?i)(?:"
    r"biopsy\s+(?:confirmed|shows?|revealed)\s+(\S[\w\s]+?)(?:\s*[-.,;(]|$)"
    r"|diagnosed?\s+(?:with|as)\s+(\S[\w\s]+?)(?:\s*[-.,;(]|$)"
    r"|MDT\s+(?:confirmed|outcome)\s*:?\s*(\S[\w\s]+?)(?:\s*[-.,;(]|$)"
    r")"
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class AnchorResult:
    patient_id: str
    referral_anchors: list[dict[str, Any]] = field(default_factory=list)
    diagnosis_anchors: list[dict[str, Any]] = field(default_factory=list)
    treatment_anchors: list[dict[str, Any]] = field(default_factory=list)
    specialist_visit_anchors: list[dict[str, Any]] = field(default_factory=list)
    earliest_date: str | None = None
    latest_date: str | None = None
    expanded_start: str | None = None
    expanded_end: str | None = None
    expanded_encounters: list[dict[str, Any]] = field(default_factory=list)
    detection_method: str = "concept"  # "concept" | "regex" | "none"

    @property
    def has_referral(self) -> bool:
        return bool(self.referral_anchors)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def detect_anchors(
    patient_id: str,
    start_date: str,
    end_date: str,
    patient_client,
    expand_months: int = 3,
    use_hybrid: bool = True,
    deep_mode: bool = False,
    kg_session=None,
) -> AnchorResult:
    """Detect milestone anchors for a patient via three-tier cascade.

    Tier 1: SNOMED concept matching against :DOCUMENTS in the patient graph.
    Tier 2: Hybrid terminology search (sentence-level) for any milestone types
            still missing.  In ``deep_mode``, also expands concept sets via
            SNOMED IS_A hierarchy and applies LLM disambiguation.
    Tier 3: Regex text patterns — only when no :DOCUMENTS exist at all AND
            ``deep_mode`` is False.  Suppressed in deep_mode because the
            resolver + LLM provide better signal without hand-crafted patterns.

    Parameters
    ----------
    patient_client:
        Connected ``PatientGraphClient``.
    use_hybrid:
        Set ``False`` to skip Tier 2 (useful in test / dry-run contexts where
        the Terminology API may not be reachable).
    deep_mode:
        When ``True``, activates SNOMED hierarchy expansion and LLM
        disambiguation in Tier 2, and suppresses the Tier 3 regex fallback.
        Use for gold-dataset audits where quality trumps throughput.
    kg_session:
        Open ``KnowledgeGraphClient`` session for SNOMED hierarchy expansion.
        Only used when ``deep_mode=True``.
    """
    result = AnchorResult(patient_id=patient_id)
    encounters: list[dict[str, Any]] | None = None  # fetched lazily, at most once

    # ------------------------------------------------------------------ #
    # Tier 1: concept matching via :DOCUMENTS                             #
    # ------------------------------------------------------------------ #
    coded = _fetch_coded_encounters(patient_id, start_date, end_date, patient_client)
    has_documents = bool(coded)

    if has_documents:
        _apply_concept_anchors(coded, result)
        result.detection_method = "concept"
        logger.info(
            "detect_anchors: patient=%s tier-1 (%d coded rows) "
            "→ referrals=%d diagnoses=%d treatments=%d specialist=%d",
            patient_id,
            len(coded),
            len(result.referral_anchors),
            len(result.diagnosis_anchors),
            len(result.treatment_anchors),
            len(result.specialist_visit_anchors),
        )

    # ------------------------------------------------------------------ #
    # Tier 2: hybrid terminology search for still-missing milestones      #
    # ------------------------------------------------------------------ #
    def _anchor_lists() -> dict[str, list]:
        return {
            "referral":         result.referral_anchors,
            "diagnosis":        result.diagnosis_anchors,
            "treatment_start":  result.treatment_anchors,
            "specialist_visit": result.specialist_visit_anchors,
        }

    missing = [mtype for mtype, lst in _anchor_lists().items() if not lst]

    if missing and use_hybrid:
        if encounters is None:
            encounters = _fetch_encounters_with_text(
                patient_id, start_date, end_date, patient_client
            )
        _apply_hybrid_anchors(encounters, missing, result, deep_mode=deep_mode, kg_session=kg_session)
        if result.detection_method == "concept":
            result.detection_method = "concept+hybrid" if not deep_mode else "concept+hybrid+llm"
        elif not has_documents:
            result.detection_method = "hybrid" if not deep_mode else "hybrid+llm"

        logger.info(
            "detect_anchors: patient=%s tier-2 hybrid%s for %s "
            "→ referrals=%d diagnoses=%d treatments=%d specialist=%d",
            patient_id,
            " (deep)" if deep_mode else "",
            missing,
            len(result.referral_anchors),
            len(result.diagnosis_anchors),
            len(result.treatment_anchors),
            len(result.specialist_visit_anchors),
        )

    # ------------------------------------------------------------------ #
    # Tier 3: regex fallback — only when no :DOCUMENTS at all             #
    # Suppressed in deep_mode: resolver + LLM provide better signal       #
    # ------------------------------------------------------------------ #
    missing_after_hybrid = [mtype for mtype, lst in _anchor_lists().items() if not lst]
    if not has_documents and missing_after_hybrid and not deep_mode:
        if encounters is None:
            encounters = _fetch_encounters_with_text(
                patient_id, start_date, end_date, patient_client
            )
        _apply_regex_anchors(encounters, result)
        result.detection_method = "regex"
        logger.info(
            "detect_anchors: patient=%s tier-3 regex (no DOCUMENTS) "
            "→ referrals=%d diagnoses=%d",
            patient_id,
            len(result.referral_anchors),
            len(result.diagnosis_anchors),
        )

    _expand_window(patient_id, expand_months, result, patient_client)
    return result


# ---------------------------------------------------------------------------
# Concept-based detection (primary path)
# ---------------------------------------------------------------------------

def _fetch_coded_encounters(
    patient_id: str,
    start_date: str,
    end_date: str,
    client,
) -> list[dict[str, Any]]:
    """Return encounters that have at least one :DOCUMENTS relationship."""
    # Collect all milestone concept IDs in a single query pass
    all_ids = list(
        FAST_TRACK_REFERRAL_IDS
        | CANCER_TYPE_IDS
        | TREATMENT_IDS
        | SEEN_BY_SPECIALIST_IDS
    )
    rows = client.run(
        "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(c) "
        "WHERE toString(p.id) = $pid "
        "  AND toString(e.date) >= $start "
        "  AND toString(e.date) <= $end "
        "  AND toInteger(c.conceptId) IN $ids "
        "RETURN toString(e.id) AS encounter_id, "
        "       toString(e.date) AS encounter_date, "
        "       toInteger(c.conceptId) AS concept_id, "
        "       c.name AS concept_name, "
        "       c.semanticTag AS semantic_tag, "
        "       r.domain AS domain, "
        "       r.confidence AS confidence, "
        "       r.source AS source "
        "ORDER BY e.date",
        pid=patient_id,
        start=start_date,
        end=end_date,
        ids=all_ids,
    )
    return [dict(r) for r in rows]


def _apply_concept_anchors(
    coded_rows: list[dict[str, Any]],
    result: AnchorResult,
) -> None:
    """Populate anchor lists from coded encounter rows."""
    # Group by encounter so each encounter appears once per anchor type
    seen: dict[str, set[str]] = {
        "referral": set(),
        "diagnosis": set(),
        "treatment_start": set(),
        "specialist_visit": set(),
    }

    for row in coded_rows:
        enc_id = str(row["encounter_id"])
        enc_date = str(row["encounter_date"])
        concept_id = int(row["concept_id"])
        concept_name = row.get("concept_name") or ""
        confidence = row.get("confidence") or 0.0
        source = row.get("source") or "provisional"

        anchor_entry = {
            "encounter_id": enc_id,
            "encounter_date": enc_date,
            "concept_id": concept_id,
            "concept_name": concept_name,
            "confidence": confidence,
            "source": source,
            "detection_method": "concept",
        }

        if concept_id in FAST_TRACK_REFERRAL_IDS and enc_id not in seen["referral"]:
            result.referral_anchors.append(anchor_entry)
            seen["referral"].add(enc_id)

        if concept_id in CANCER_TYPE_IDS and enc_id not in seen["diagnosis"]:
            result.diagnosis_anchors.append(anchor_entry)
            seen["diagnosis"].add(enc_id)

        if concept_id in TREATMENT_IDS and enc_id not in seen["treatment_start"]:
            result.treatment_anchors.append(anchor_entry)
            seen["treatment_start"].add(enc_id)

        if concept_id in SEEN_BY_SPECIALIST_IDS and enc_id not in seen["specialist_visit"]:
            result.specialist_visit_anchors.append(anchor_entry)
            seen["specialist_visit"].add(enc_id)


# ---------------------------------------------------------------------------
# Tier 2: hybrid terminology search
# ---------------------------------------------------------------------------

def _apply_hybrid_anchors(
    encounters: list[dict[str, Any]],
    missing_milestone_types: list[str],
    result: AnchorResult,
    *,
    deep_mode: bool = False,
    kg_session=None,
) -> None:
    """Run hybrid search and merge results into ``result``.

    The hybrid search module is async; we bridge into it from the synchronous
    caller using a thread-pool when an event loop is already running (analysis
    worker), or via ``loop.run_until_complete`` otherwise (audit script).

    ``deep_mode`` and ``kg_session`` are forwarded to ``search_missing_anchors``
    to activate SNOMED hierarchy expansion and LLM disambiguation.
    """
    from services.analysis_worker.app.analyzers.hybrid_anchor_search import (
        hits_to_anchor_entries,
        search_missing_anchors,
    )

    coro = search_missing_anchors(
        encounters,
        missing_milestone_types,
        deep_mode=deep_mode,
        kg_session=kg_session,
    )

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, coro)
                hits = future.result(timeout=600 if deep_mode else 30)
        else:
            hits = loop.run_until_complete(coro)
    except Exception:
        logger.warning(
            "_apply_hybrid_anchors: hybrid search failed — skipping tier 2",
            exc_info=True,
        )
        return

    by_type = hits_to_anchor_entries(hits)
    if by_type.get("referral"):
        result.referral_anchors.extend(by_type["referral"])
    if by_type.get("diagnosis"):
        result.diagnosis_anchors.extend(by_type["diagnosis"])
    if by_type.get("treatment_start"):
        result.treatment_anchors.extend(by_type["treatment_start"])
    if by_type.get("specialist_visit"):
        result.specialist_visit_anchors.extend(by_type["specialist_visit"])


# ---------------------------------------------------------------------------
# Regex fallback (tier 3 — no DOCUMENTS available yet)
# ---------------------------------------------------------------------------

def _fetch_encounters_with_text(
    patient_id: str,
    start_date: str,
    end_date: str,
    client,
) -> list[dict[str, Any]]:
    return client.run(
        "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
        "WHERE toString(p.id) = $pid "
        "  AND toString(e.date) >= $start "
        "  AND toString(e.date) <= $end "
        "RETURN e.id AS encounter_id, toString(e.date) AS date, e.text AS text "
        "ORDER BY e.date",
        pid=patient_id, start=start_date, end=end_date,
    )


def _apply_regex_anchors(
    encounters: list[dict[str, Any]],
    result: AnchorResult,
) -> None:
    for enc in encounters:
        text = enc.get("text") or ""
        enc_id = str(enc.get("encounter_id", ""))
        enc_date = str(enc.get("date", ""))

        condition_type = _detect_referral_in_text(text)
        if condition_type:
            result.referral_anchors.append({
                "encounter_id": enc_id,
                "encounter_date": enc_date,
                "concept_name": f"Fast track referral for suspected {condition_type} cancer",
                "source": "regex_fallback",
                "detection_method": "regex",
            })

        if _DIAGNOSIS_RE.search(text):
            m = _DIAGNOSIS_RE.search(text)
            matched = next((g for g in m.groups() if g), "unknown") if m else "unknown"
            result.diagnosis_anchors.append({
                "encounter_id": enc_id,
                "encounter_date": enc_date,
                "concept_name": matched.strip(),
                "source": "regex_fallback",
                "detection_method": "regex",
            })


def _detect_referral_in_text(text: str) -> str | None:
    m = _FAST_TRACK_RE.search(text)
    if m:
        return _normalise_condition_type(m.group(1).strip())
    m = _2WW_RE.search(text)
    if m:
        return _normalise_condition_type(m.group(1).strip())
    return None


def _normalise_condition_type(raw: str) -> str:
    low = raw.lower().rstrip(".")
    for keyword, standard in _CANCER_TYPE_MAP.items():
        if keyword in low:
            return standard
    return raw.split("(")[0].strip() if raw else "unknown"


# ---------------------------------------------------------------------------
# Window expansion (shared)
# ---------------------------------------------------------------------------

def _expand_window(
    patient_id: str,
    expand_months: int,
    result: AnchorResult,
    client,
) -> None:
    all_dates: list[str] = []
    for anchors in [
        result.referral_anchors,
        result.diagnosis_anchors,
        result.treatment_anchors,
        result.specialist_visit_anchors,
    ]:
        for a in anchors:
            d = a.get("encounter_date", "")
            if d:
                all_dates.append(d[:10])

    if not all_dates:
        return

    all_dates.sort()
    result.earliest_date = all_dates[0]
    result.latest_date = all_dates[-1]

    try:
        earliest = datetime.strptime(result.earliest_date, "%Y-%m-%d")
        latest = datetime.strptime(result.latest_date, "%Y-%m-%d")
        result.expanded_start = (earliest - timedelta(days=expand_months * 30)).strftime("%Y-%m-%d")
        result.expanded_end = (latest + timedelta(days=expand_months * 30)).strftime("%Y-%m-%d")

        if result.expanded_start and result.expanded_end:
            result.expanded_encounters = client.run(
                "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
                "WHERE toString(p.id) = $pid "
                "  AND toString(e.date) >= $start "
                "  AND toString(e.date) <= $end "
                "RETURN e.id AS encounter_id, toString(e.date) AS date, e.text AS text "
                "ORDER BY e.date",
                pid=patient_id,
                start=result.expanded_start,
                end=result.expanded_end,
            )
    except ValueError:
        pass
