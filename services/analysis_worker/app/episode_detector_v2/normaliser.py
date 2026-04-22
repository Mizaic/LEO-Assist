"""Timeline Normaliser -- canonical event stream from raw graph data.

Atlas trace:
  DI: DI-8A5FCF4F
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-8A5FCF4F")

Reads the patient's ``Encounter`` and ``[:DOCUMENTS]`` SNOMED links
from the live patient graph and turns them into a deterministic,
immutable list of :class:`TimelineEvent` ordered by ``occurred_on``.

The normaliser is **pure**: given the same patient_client output it
must produce the same :class:`TimelineEvent` list (so downstream
components can rely on stable ordering and stable encounter ids).

Live-graph schema (verified 2026-04-22 against dev Neo4j)::

    (:Patient {id})-[:HAS_ENCOUNTER]->(:Encounter {id, date, text})
    (:Encounter)-[:DOCUMENTS {conceptId, value, unit, context, ...}]
        ->(:Procedure | :Observable_entity | :Clinical_finding |
           :Situation | :Disease | :SnomedConcept {conceptId, name,
                                                   semanticTag})

The translator in :func:`load_timeline` reshapes those rows into the
abstract row format consumed by :func:`normalise_from_rows` (which
remains stable for unit tests with synthetic inputs).
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any

from .site_keys import (
    site_for_clinic_seen_concept,
    site_for_referral_concept,
)
from .types import TimelineEvent

logger = logging.getLogger(__name__)


# Live-graph timeline query. Returns one row per encounter with its
# DOCUMENTS edges aggregated into ``raw_codes`` so the Python translator
# can split them into coded_entities / observation_results / referral.
_TIMELINE_QUERY = """
    MATCH (p:Patient {id: $patient_id})-[:HAS_ENCOUNTER]->(e:Encounter)
    OPTIONAL MATCH (e)-[r:DOCUMENTS]->(c)
    WITH e,
         collect({
             concept_id: coalesce(r.conceptId, c.conceptId),
             display_name: c.name,
             semantic_tag: coalesce(c.semanticTag, head(labels(c))),
             assertion_json: r.context,
             modifiers_json: r.modifiers,
             evidence_sentence: coalesce(
                 r.evidence_sentence, r.evidence
             ),
             value: r.value,
             unit: r.unit,
             decision_tier: r.decision_tier,
             model_version: r.model_version
         }) AS raw_codes
    RETURN e.id AS encounter_id,
           e.date AS occurred_on,
           e.text AS encounter_text,
           raw_codes
    ORDER BY e.date ASC, e.id ASC
"""


# -- Live-graph row translator ----------------------------------------------


_REFERRAL_NAME_FRAGMENTS = (
    "fast track referral",
    "two week wait referral",
    "2 week wait referral",
    "two-week wait referral",
)

_NEGATING_ASSERTIONS = {"absent", "negated", "ruled_out", "negative"}


def _parse_assertion(assertion_json: Any) -> str:
    """Extract a single canonical assertion label from the rel.context JSON."""
    if not assertion_json:
        return "present"
    try:
        ctx = (
            json.loads(assertion_json)
            if isinstance(assertion_json, str)
            else assertion_json
        )
    except (TypeError, ValueError):
        return "present"
    if not isinstance(ctx, dict):
        return "present"
    if ctx.get("negated") or ctx.get("refuted"):
        return "negated"
    if ctx.get("declined") or ctx.get("cancelled"):
        return "ruled_out"
    if ctx.get("family"):
        return "family_history"
    if ctx.get("historical"):
        return "history"
    if ctx.get("uncertain"):
        return "uncertain"
    if ctx.get("hypothetical"):
        return "hypothetical"
    if ctx.get("planned"):
        return "planned"
    raw = ctx.get("assertion")
    if isinstance(raw, str) and raw:
        return raw.strip().lower()
    return "present"


def _is_referral_doc(doc: dict[str, Any]) -> str | None:
    """Return the canonical site_key if the doc represents a 2WW referral."""
    site = site_for_referral_concept(str(doc.get("concept_id") or ""))
    if site:
        return site
    name = str(doc.get("display_name") or "").lower()
    if any(frag in name for frag in _REFERRAL_NAME_FRAGMENTS):
        for frag in _REFERRAL_NAME_FRAGMENTS:
            if frag in name:
                # Best-effort site inference from the name -- the
                # registry is the canonical path; the name match is a
                # safety net for new/unmapped referral SNOMEDs.
                if "breast" in name:
                    return "breast"
                if "upper gastrointestinal" in name or "upper gi" in name:
                    return "upper_gi"
                if "lower gastrointestinal" in name or "lower gi" in name:
                    return "lower_gi"
                if "lung" in name:
                    return "lung"
                if "urological" in name or "prostate" in name:
                    return "prostate_urological"
                if "gynae" in name:
                    return "gynae"
                if "head and neck" in name:
                    return "head_neck"
                if "skin" in name or "melanoma" in name:
                    return "skin"
                if "haematological" in name or "haematology" in name:
                    return "haematology"
                if "brain" in name or "cns" in name:
                    return "brain_cns"
                return None
    return None


def _coded_entity_from_doc(doc: dict[str, Any]) -> dict[str, Any] | None:
    """Translate one [:DOCUMENTS] row into a coded_entity row."""
    cid = str(doc.get("concept_id") or "").strip()
    if not cid:
        return None
    return {
        "concept_id": cid,
        "display_name": doc.get("display_name") or "",
        "assertion": _parse_assertion(doc.get("assertion_json")),
        "role": doc.get("semantic_tag") or "",
        "evidence": doc.get("evidence_sentence") or "",
        "decision_tier": doc.get("decision_tier") or "",
        "model_version": doc.get("model_version") or "",
    }


def _observation_from_doc(doc: dict[str, Any]) -> dict[str, Any] | None:
    """Translate an Observable_entity DOCUMENTS row into an observation row."""
    semantic = (doc.get("semantic_tag") or "").lower()
    if "observable" not in semantic:
        return None
    if doc.get("value") in (None, ""):
        return None
    interpretation = "abnormal" if "outside reference" in (
        str(doc.get("display_name") or "").lower()
    ) else None
    return {
        "observation_code": doc.get("concept_id") or "",
        "display_name": doc.get("display_name") or "",
        "value": doc.get("value"),
        "unit": doc.get("unit") or "",
        "interpretation": interpretation,
    }


def _referral_form_from_doc(
    doc: dict[str, Any], site_key: str
) -> dict[str, Any]:
    """Build a referral_form dict the existing pathway-channel can read."""
    return {
        "form_type": f"2ww_{site_key}",
        "urgency": "2ww",
        "source": "snomed_referral",
        "reason": doc.get("display_name") or "",
        "concept_id": doc.get("concept_id") or "",
    }


def _clinic_seen_signal(doc: dict[str, Any]) -> str | None:
    """Return the site_key for a 'seen in fast track X clinic' SNOMED."""
    return site_for_clinic_seen_concept(str(doc.get("concept_id") or ""))


def _row_from_live(row: dict[str, Any]) -> dict[str, Any]:
    """Translate a live-graph row into the abstract row shape."""
    raw_codes = row.get("raw_codes") or []
    docs = [d for d in raw_codes if d and d.get("concept_id")]
    coded: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    referral: dict[str, Any] | None = None
    for doc in docs:
        ce = _coded_entity_from_doc(doc)
        if ce is not None:
            coded.append(ce)
        obs = _observation_from_doc(doc)
        if obs is not None:
            observations.append(obs)
        if referral is None:
            site = _is_referral_doc(doc)
            if site is not None:
                referral = _referral_form_from_doc(doc, site)
    # Promote the first clinic-seen finding to an additional "referral"
    # signal when no explicit referral form exists -- this lets the
    # pathway channel still flag the encounter for sites where the
    # referral SNOMED never made it onto the document but the clinic
    # follow-up did.
    if referral is None:
        for doc in docs:
            site = _clinic_seen_signal(doc)
            if site is not None:
                referral = {
                    "form_type": f"2ww_{site}",
                    "urgency": "2ww",
                    "source": "clinic_seen_finding",
                    "reason": doc.get("display_name") or "",
                    "concept_id": doc.get("concept_id") or "",
                }
                break
    text = row.get("encounter_text") or ""
    return {
        "encounter_id": row.get("encounter_id") or "",
        "occurred_on": row.get("occurred_on"),
        "encounter_type": "encounter",
        "doc_snippets": [text] if text else [],
        "codes": coded,
        "observations": observations,
        "referral": referral,
    }


def _to_date(raw: Any) -> date | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    text = str(raw)
    try:
        return date.fromisoformat(text[:10])
    except (TypeError, ValueError):
        return None


def _row_to_event(row: dict[str, Any]) -> TimelineEvent | None:
    encounter_id = str(row.get("encounter_id") or "").strip()
    if not encounter_id:
        return None
    occurred_on = _to_date(row.get("occurred_on"))
    if occurred_on is None:
        return None
    snippets = [s for s in (row.get("doc_snippets") or []) if s]
    codes = tuple(c for c in (row.get("codes") or []) if c and c.get("concept_id"))
    observations = tuple(o for o in (row.get("observations") or []) if o)
    referral = row.get("referral") if row.get("referral") else None
    return TimelineEvent(
        encounter_id=encounter_id,
        occurred_on=occurred_on,
        event_kind="encounter",
        text_snippet=" \n".join(snippets)[:4000],
        coded_entities=codes,
        referral_form=referral,
        observation_results=observations,
        raw=dict(row),
    )


async def load_timeline(
    patient_id: str,
    patient_client: Any,
) -> list[TimelineEvent]:
    """Return a deterministic ordered timeline for ``patient_id``.

    ``patient_client.run`` is called synchronously here because the
    existing PatientGraphClient driver is sync; the call is safe inside
    the analysis-worker thread pool.
    """
    if not patient_id:
        return []
    try:
        rows = patient_client.run(_TIMELINE_QUERY, patient_id=patient_id)
    except Exception:
        logger.exception("Timeline query failed for patient %s", patient_id)
        return []
    events: list[TimelineEvent] = []
    for row in rows:
        translated = _row_from_live(dict(row))
        evt = _row_to_event(translated)
        if evt is not None:
            events.append(evt)
    events.sort(key=lambda e: (e.occurred_on, e.encounter_id))
    return events


def normalise_from_rows(rows: list[dict[str, Any]]) -> list[TimelineEvent]:
    """Pure helper used by tests -- skip the graph round-trip."""
    events = [evt for evt in (_row_to_event(r) for r in rows) if evt is not None]
    events.sort(key=lambda e: (e.occurred_on, e.encounter_id))
    return events
