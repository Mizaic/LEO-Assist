"""NICE guideline diff -- compare stored recs against the live NICE API.

Atlas trace:
  DO: DO-EC41233C
  DI: DI-9D0DF618
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-EC41233C")

Provides:
  POST /nice/{code}/diff/start    -- trigger an async diff job
  GET  /nice/{code}/diff/{job_id} -- poll the diff result

The diff matches stored Recommendation nodes to live NICE content by
recommendation number (e.g. "1.5.6"). For each changed/removed
recommendation, the rules that would be affected are attached to the result
so the reviewer can decide how to proceed before re-ingesting.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.db.neo4j_client import CodingGraphClient
from app.deps import require_admin
from app.routers.nice_guidance import _extract_recommendations_from_section
from app.services.nice_api_client import NICE_CODE_RE, NiceApiClient
from libs.auth.org_scope import CallerScope

logger = logging.getLogger(__name__)
router = APIRouter(tags=["nice-diff"])

_diff_jobs: dict[str, dict[str, Any]] = {}

_FETCH_STORED_RECS = """
MATCH (g:Guideline {id: $code})-[:HAS_RECOMMENDATION]->(r:Recommendation)
WHERE r.isNormative = true
RETURN r.title AS number, r.verbatim AS text,
       coalesce(r.sectionTitle, '') AS section_title
ORDER BY r.id
"""

_FETCH_RULES_FOR_RECS = """
MATCH (r:Recommendation {guidelineId: $code})-[:HAS_RULE]->(rule)
WHERE r.title IN $numbers
  AND rule.status IN ['active', 'pending_review']
RETURN r.title AS number,
       rule.id AS rule_id, rule.name AS rule_name, rule.status AS rule_status
"""


# -- Diff helpers ------------------------------------------------------------


def _norm(text: str) -> str:
    return " ".join(text.split()) if text else ""


def _compute_diff(stored: list[dict], remote: list[dict]) -> dict[str, Any]:
    s = {r["number"]: r for r in stored if r.get("number")}
    rem = {r["number"]: r for r in remote if r.get("number")}
    added = [
        {"number": n, "text": rem[n]["text"], "section_title": rem[n].get("section_title", "")}
        for n in rem if n not in s
    ]
    removed = [
        {"number": n, "text": s[n]["text"], "section_title": s[n].get("section_title", ""), "rules": []}
        for n in s if n not in rem
    ]
    modified = [
        {
            "number": n,
            "section_title": rem[n].get("section_title", s[n].get("section_title", "")),
            "old_text": s[n]["text"],
            "new_text": rem[n]["text"],
            "rules": [],
        }
        for n in s if n in rem and _norm(s[n]["text"]) != _norm(rem[n]["text"])
    ]
    unchanged_numbers = [
        n for n in s if n in rem and _norm(s[n]["text"]) == _norm(rem[n]["text"])
    ]
    return {
        "added": added, "removed": removed, "modified": modified,
        "unchanged_count": len(unchanged_numbers),
        "total_stored": len(s), "total_remote": len(rem),
        "_unchanged_numbers": unchanged_numbers,
    }


def _annotate_rules(diff: dict[str, Any], code: str) -> int:
    """Attach affected rules to modified/removed items; return total count."""
    at_risk = [c["number"] for c in diff["modified"] + diff["removed"]]
    if not at_risk:
        return 0
    neo = CodingGraphClient()
    try:
        rows = neo.run(_FETCH_RULES_FOR_RECS, code=code, numbers=at_risk)
    finally:
        neo.close()
    by_num: dict[str, list[dict]] = {}
    for r in rows:
        by_num.setdefault(r["number"], []).append(
            {"rule_id": r["rule_id"], "name": r["rule_name"], "status": r["rule_status"]}
        )
    for item in diff["modified"] + diff["removed"]:
        item["rules"] = by_num.get(item["number"], [])
    return sum(len(item["rules"]) for item in diff["modified"] + diff["removed"])


async def _fetch_remote_recs(code: str) -> list[dict]:
    """Fetch all normative recommendations from the live NICE API (read-only)."""
    client = NiceApiClient()
    chapters = await client.get_chapters(code)
    recs: list[dict] = []
    for chapter in chapters:
        href = chapter.get("Href", "") or chapter.get("Uri", "")
        if not href:
            continue
        try:
            chapter_data = await client.get_chapter_content(href)
        except RuntimeError:
            continue
        for sec_uri in client.get_section_uris(chapter_data):
            try:
                section_data = await client.get_section_content(sec_uri)
            except RuntimeError:
                continue
            for item in _extract_recommendations_from_section(section_data, code):
                title, text = item.get("Title", ""), item.get("Text", "")
                if title and text:
                    recs.append({"number": title, "text": text,
                                 "section_title": item.get("SectionTitle", "")})
    return recs


async def _async_diff(job_id: str, code: str) -> None:
    """Async diff: Neo4j stored recs vs live NICE API."""
    _diff_jobs[job_id]["step"] = "Fetching stored recommendations..."
    neo = CodingGraphClient()
    try:
        stored_rows = neo.run(_FETCH_STORED_RECS, code=code)
    finally:
        neo.close()
    stored = [
        {"number": r["number"], "text": r.get("text", ""),
         "section_title": r.get("section_title", "")}
        for r in stored_rows if r.get("number")
    ]
    _diff_jobs[job_id]["step"] = (
        f"Fetching {len(stored)} recommendations from NICE API..."
    )
    remote = await _fetch_remote_recs(code)
    diff = _compute_diff(stored, remote)
    rules_at_risk = _annotate_rules(diff, code)
    _diff_jobs[job_id].update({
        "status": "done", "step": "Complete",
        "diff": diff, "rules_at_risk": rules_at_risk,
    })


def _run_diff(job_id: str, code: str) -> None:
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_async_diff(job_id, code))
    except Exception as exc:
        logger.exception("Diff failed for %s: %s", code, exc)
        _diff_jobs[job_id].update({"status": "error", "error": str(exc)})
    finally:
        loop.close()


# -- Endpoints ----------------------------------------------------------------


@router.post("/nice/{code}/diff/start", status_code=202)
async def start_diff(
    code: str,
    scope: CallerScope = Depends(require_admin),
) -> dict:
    """Start an async diff job for a loaded guideline.

    Fetches live NICE recommendations and compares them against what is stored
    in Neo4j to identify added, removed, and modified recommendations.

    Returns:
        ``{"job_id": "..."}`` -- poll GET /nice/{code}/diff/{job_id}.

    Raises:
        422: Invalid NICE code format.
    """
    code_upper = code.strip().upper()
    if not NICE_CODE_RE.match(code_upper):
        raise HTTPException(status_code=422, detail=f"Invalid NICE code: {code}")
    job_id = str(uuid.uuid4())
    _diff_jobs[job_id] = {"job_id": job_id, "code": code_upper,
                          "status": "running", "step": "Queued"}
    threading.Thread(target=_run_diff, args=(job_id, code_upper), daemon=True).start()
    return {"job_id": job_id}


@router.get("/nice/{code}/diff/{job_id}")
def get_diff(
    code: str,
    job_id: str,
    scope: CallerScope = Depends(require_admin),
) -> dict:
    """Poll a diff job started via POST /nice/{code}/diff/start.

    Returns the job dict including ``status`` (``"running"`` | ``"done"`` |
    ``"error"``), a ``step`` progress message, and on completion a ``diff``
    object with ``added``, ``removed``, ``modified``, ``unchanged_count``,
    and ``rules_at_risk``.

    Raises:
        404: Job not found.
    """
    job = _diff_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Diff job not found")
    return job
