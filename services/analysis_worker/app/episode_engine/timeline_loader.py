"""Stage 1: pull a patient's encounters and serialise into a compact,
prompt-ready timeline with same-day grouping.

Two views are produced:

- ``timeline_text``: the trunk view used by segmenter + classifier. Short
  per-encounter snippets, same-day grouping markers. Optimised for cheap
  segmentation across long histories.

- ``encounter_index``: a dict keyed by encounter_id so the milestone
  extractor (and the writer) can look up the full encounter text for an
  encounter referenced in a window.

The loader is read-only and deterministic. It does NOT call any LLM.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from libs.llm_client.prompt_safety import sanitise_for_prompt
from libs.neo4j_client.client import PatientGraphClient

logger = logging.getLogger(__name__)

# Cap text per encounter in the trunk view used by the segmenter +
# classifier. The trunk view is intentionally short so the LLM can
# segment a multi-year timeline in one cheap call.
_TRUNK_SNIPPET_CHARS = 240

# Per-encounter cap for the full-snippet stored in the encounter_index.
# Historically this was the only safety net for the milestone extractor
# and silently shortened encounters whose text exceeded 4000 chars (a
# real risk for dense discharge letters and stitched encounter
# bundles -- see DI-LEO-AI-525). The window partitioner now performs
# the real safety-net work (see ``services/analysis_worker/app/
# episode_engine/window_partitioner.py``); this cap is retained ONLY as
# a corner-case fallback for callers that bypass the partitioner (for
# example direct unit tests that hand the milestone extractor a single
# untruncated encounter). Production code paths must NOT rely on this
# cap to keep prompts within budget; the partitioner is the source of
# truth.
_FULL_SNIPPET_CHARS = 16_000

_WHITESPACE_RX = re.compile(r"[ \t]+")
_NEWLINES_RX = re.compile(r"\s*\n\s*")


_LOAD_TIMELINE_Q = """
MATCH (p:Patient {id: $patient_id})-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE e.text IS NOT NULL
RETURN e.id          AS encounter_id,
       e.date        AS date,
       e.text        AS text,
       e.flags       AS flags,
       e.coding_status AS coding_status
ORDER BY e.date ASC, e.id ASC
"""


def _normalise(text: str | None) -> str:
    if not text:
        return ""
    text = _NEWLINES_RX.sub(" / ", text)
    text = _WHITESPACE_RX.sub(" ", text)
    return text.strip()


def _trunk_line(encounter_id: str, text: str) -> str:
    """One-liner for the segmenter view."""
    snippet = _normalise(text)[:_TRUNK_SNIPPET_CHARS]
    short_id = encounter_id[:8]
    return f"  [{short_id}] {snippet}"


def _full_snippet(text: str) -> str:
    """Per-encounter snippet for the milestone extractor view."""
    return sanitise_for_prompt(_normalise(text), max_chars=_FULL_SNIPPET_CHARS)


def load_timeline(
    patient_id: str,
    *,
    client: PatientGraphClient | None = None,
) -> tuple[str, dict[str, dict[str, Any]], int]:
    """Return (trunk_text, encounter_index, encounter_count).

    trunk_text is the same-day-grouped, capped view fed to segmenter and
    classifier prompts. encounter_index maps encounter_id -> raw row with
    a ``full_snippet`` key for the milestone extractor.
    """
    owns_client = client is None
    if owns_client:
        client = PatientGraphClient()
    try:
        rows = client.run(_LOAD_TIMELINE_Q, patient_id=patient_id) or []
    finally:
        if owns_client and client is not None:
            client.close()

    if not rows:
        logger.info("No encounters for patient %s", patient_id)
        return "", {}, 0

    encounter_index: dict[str, dict[str, Any]] = {}
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        eid = str(row.get("encounter_id") or "")
        if not eid:
            continue
        d = str(row.get("date") or "")
        text = row.get("text") or ""
        record = {
            "encounter_id": eid,
            "date": d,
            "text": text,
            "flags": row.get("flags"),
            "coding_status": row.get("coding_status"),
            "full_snippet": _full_snippet(text),
        }
        encounter_index[eid] = record
        by_date.setdefault(d, []).append(record)

    sections: list[str] = []
    for d in sorted(by_date.keys()):
        day_records = by_date[d]
        header = f"== {d} ({len(day_records)} record{'s' if len(day_records) != 1 else ''}) =="
        body = "\n".join(_trunk_line(r["encounter_id"], r["text"]) for r in day_records)
        sections.append(f"{header}\n{body}")

    trunk_text = "\n\n".join(sections)
    return trunk_text, encounter_index, len(encounter_index)
