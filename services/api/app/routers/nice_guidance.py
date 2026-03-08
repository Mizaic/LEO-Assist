"""NICE guideline ingestion endpoints.

Provides:
  GET  /nice/catalogue?q=   -- searchable guideline index (Redis-cached, relevance-ranked)
  GET  /nice/taxonomy       -- taxonomy hierarchy from Neo4j with loaded status per guideline
  POST /nice/catalogue/sync -- sync full NICE index to Redis + taxonomy to Neo4j
  POST /nice/ingest         -- fire-and-track ingest by NICE code
  GET  /nice/events         -- SSE progress stream for a job
  GET  /nice/jobs/{job_id}/status
  GET  /nice/jobs

All endpoints require the ai.admin role.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.db.neo4j_client import CodingGraphClient
from app.deps import require_admin
from app.services.nice_api_client import NICE_CODE_RE, NiceApiClient
from app.services.nice_graph_upserter import NiceGraphUpserter
from libs.auth.org_scope import CallerScope

logger = logging.getLogger(__name__)
router = APIRouter(tags=["nice-guidance"])

_jobs: dict[str, dict[str, Any]] = {}
_queues: dict[str, queue.Queue] = {}
_IDLE_TIMEOUT = 300


class NiceIngestRequest(BaseModel):
    """Request body for POST /nice/ingest."""

    code: str

    @property
    def validated_code(self) -> str:
        """Return upper-cased code; raises ValueError for non-NICE codes."""
        upper = self.code.strip().upper()
        if not NICE_CODE_RE.match(upper):
            raise ValueError(
                f"'{self.code}' is not a valid NICE guidance code. "
                "Expected format: NG151, CG89, TA123, QS12, etc."
            )
        return upper


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _emit(job_id: str, event: str, data: dict) -> None:
    q = _queues.get(job_id)
    if q:
        q.put(_sse(event, data))
    _jobs.get(job_id, {}).update(data)


@router.get("/nice/catalogue")
async def get_catalogue(
    q: str = Query(default="", min_length=0),
    scope: CallerScope = Depends(require_admin),
) -> list[dict]:
    """Search the NICE guideline catalogue by keyword or condition name.

    Primary source is the Redis-cached catalogue (3,661+ guidelines) with
    relevance-ranked results so that NG/CG clinical guidelines appear before
    technology appraisals when a condition name is typed.

    Ranking (lower score = higher in list):
      0 -- exact code match (e.g. "NG12")
      1 -- title starts with query
      2 -- title contains query, NG or CG type
      3 -- title contains query, other type
      4 -- code starts with query (partial code e.g. "ng1")

    Falls back to the live NICE index API only when the Redis cache is empty
    (i.e. before the first catalogue sync has been run).
    """
    client = NiceApiClient()
    if not q:
        entries = await client.fetch_catalogue()
        return entries[:20]

    q_lower = q.lower().strip()

    # Primary: search the Redis catalogue with relevance scoring
    entries = await client.fetch_catalogue()
    if entries:
        return _ranked_search(entries, q_lower)

    # Fallback (cache cold): live NICE index search
    logger.info("Redis catalogue empty -- falling back to live NICE index search for %r", q)
    return await client.search_index(q)


# Code prefixes for clinical guidelines -- ranked above technology appraisals (TA)
# when a condition name search matches both types
_CLINICAL_PREFIXES = {"NG", "CG", "QS"}


def _ranked_search(entries: list[dict], q_lower: str, limit: int = 20) -> list[dict]:
    """Return up to *limit* entries from the Redis catalogue ranked by relevance.

    Uses the code prefix (NG/CG/QS) to prioritise clinical guidelines over
    technology appraisals when a condition name matches both, so that e.g.
    searching "cancer" surfaces NG12 before drug technology appraisals.

    Relevance tiers (ascending -- lower score = higher in list):
      0  exact code match  (e.g. user typed "NG12")
      1  title starts with query
      2  title contains query AND code prefix is NG/CG/QS
      3  title contains query, any other code type (TA, DG, IPG, ...)
      4  code starts with query (partial code, e.g. "ng1")
    Entries matching none of the above are excluded.
    Within each tier, results are sorted alphabetically by title.
    """
    scored: list[tuple[int, dict]] = []
    for entry in entries:
        code = entry.get("code", "")
        code_lower = code.lower()
        title = entry.get("title", "").lower()
        is_clinical = code[:2].upper() in _CLINICAL_PREFIXES

        if code_lower == q_lower:
            score = 0
        elif title.startswith(q_lower):
            score = 1
        elif q_lower in title and is_clinical:
            score = 2
        elif q_lower in title:
            score = 3
        elif code_lower.startswith(q_lower):
            score = 4
        else:
            continue

        scored.append((score, entry))

    scored.sort(key=lambda x: (x[0], x[1].get("title", "")))
    return [e for _, e in scored[:limit]]


_FETCH_TAXONOMY = """
MATCH (cat:TaxonomyCategory)
OPTIONAL MATCH (cat)-[:HAS_SUBCATEGORY]->(sub:TaxonomySubcategory)
WITH cat,
     collect({
         id:              sub.id,
         title:           sub.title,
         guideline_codes: coalesce(sub.guidelineCodes, [])
     }) AS subcategories
RETURN cat.id AS id, cat.title AS title, subcategories
ORDER BY cat.title
"""

_CHECK_LOADED_CODES = """
MATCH (g:Guideline)
WHERE g.id IN $codes AND g.source = 'nice_syndication_api'
RETURN g.id AS code, g.title AS title
"""


@router.get("/nice/taxonomy")
async def get_taxonomy(scope: CallerScope = Depends(require_admin)) -> dict:
    """Return the NICE taxonomy hierarchy with per-guideline titles and loaded status.

    Used by the taxonomy browser drawer in the admin UI.

    Returns:
        ``{"available": false}`` when no taxonomy has been synced yet
        (the UI should trigger a sync automatically).

        ``{"available": true, "categories": [...]}`` where each subcategory
        contains a ``guidelines`` list of ``{code, title, loaded}`` objects.
        Titles are resolved from the Redis catalogue so the drawer is fully
        self-contained without the caller needing to pass a catalogue prop.
        Falls back to showing the raw code as title when Redis is unavailable.
    """
    neo = CodingGraphClient()
    try:
        rows = neo.run(_FETCH_TAXONOMY)
        if not rows:
            return {"available": False, "categories": []}

        all_codes: list[str] = []
        for row in rows:
            for sub in row.get("subcategories") or []:
                all_codes.extend(sub.get("guideline_codes") or [])

        loaded_rows = neo.run(_CHECK_LOADED_CODES, codes=list(set(all_codes)))
        loaded_set: set[str] = {r["code"] for r in loaded_rows}

        # Resolve titles from the Redis catalogue so the drawer shows human-readable names.
        title_map: dict[str, str] = {}
        try:
            catalogue = await NiceApiClient().fetch_catalogue()
            title_map = {e["code"]: e["title"] for e in catalogue}
        except Exception:
            logger.debug("Could not fetch Redis catalogue for taxonomy title enrichment -- codes shown only")

        categories = []
        for row in rows:
            subcats = []
            for sub in row.get("subcategories") or []:
                if not sub.get("id"):
                    continue
                codes: list[str] = sub.get("guideline_codes") or []
                guidelines = [
                    {
                        "code": c,
                        "title": title_map.get(c, c),  # fallback: show raw code
                        "loaded": c in loaded_set,
                    }
                    for c in codes
                ]
                subcats.append({
                    "id": sub["id"],
                    "title": sub.get("title", ""),
                    "guideline_count": len(codes),
                    "loaded_count": sum(1 for c in codes if c in loaded_set),
                    "guidelines": guidelines,
                })
            categories.append({
                "id": row["id"],
                "title": row["title"],
                "subcategories": subcats,
            })

        return {"available": True, "categories": categories}
    finally:
        neo.close()


@router.post("/nice/catalogue/sync", status_code=202)
async def sync_catalogue(
    scope: CallerScope = Depends(require_admin),
) -> dict:
    """Sync the full NICE guidance index into the Redis catalogue.

    Walks every page of the NICE guidance index and replaces the local Redis
    catalogue so the admin search autocomplete works from day one without
    requiring guidelines to be individually ingested first.

    The sync runs in the background. Check ``GET /nice/catalogue/sync/status``
    to see when it completes.
    """
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "job_id": job_id,
        "code": "__catalogue_sync__",
        "status": "queued",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "error": None,
    }

    def _run_sync() -> None:
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            client = NiceApiClient()
            upserter = NiceGraphUpserter()

            # Step 1: sync Redis catalogue from NICE index
            count = loop.run_until_complete(client.sync_catalogue_from_index())
            _jobs[job_id].update({"status": "running", "catalogue_count": count})

            # Step 2: walk NICE taxonomy and upsert to Neo4j
            taxonomy_entries = loop.run_until_complete(client.fetch_taxonomy())
            taxonomy_counts = upserter.upsert_taxonomy(taxonomy_entries)

            _jobs[job_id].update({
                "status": "done",
                "catalogue_count": count,
                "taxonomy_categories": taxonomy_counts.get("categories", 0),
                "taxonomy_subcategories": taxonomy_counts.get("subcategories", 0),
                "taxonomy_domains": taxonomy_counts.get("domains", 0),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as exc:
            logger.exception("Catalogue sync failed: %s", exc)
            _jobs[job_id].update({"status": "error", "error": str(exc)})
        finally:
            loop.close()

    threading.Thread(target=_run_sync, daemon=True).start()
    return {"job_id": job_id}


@router.post("/nice/ingest", status_code=202)
async def ingest_guideline(
    req: NiceIngestRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict:
    """Trigger ingest of a NICE guideline by code.

    The job runs in the background. Use GET /nice/events?job_id=
    to stream progress, or GET /nice/jobs/{job_id}/status to poll.
    """
    try:
        code = req.validated_code
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "job_id": job_id,
        "code": code,
        "status": "queued",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "error": None,
    }
    _queues[job_id] = queue.Queue()
    thread = threading.Thread(
        target=_run_ingest,
        args=(job_id, code),
        daemon=True,
    )
    thread.start()
    return {"job_id": job_id}


@router.get("/nice/events")
async def stream_events(
    job_id: str = Query(...),
    scope: CallerScope = Depends(require_admin),
) -> StreamingResponse:
    """Stream SSE progress events for an ingest job."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    def _generate():
        q = _queues.get(job_id)
        if not q:
            yield _sse("error", {"message": "No event queue for job"})
            return
        yield _sse("connected", {"job_id": job_id})
        idle = 0
        while idle < _IDLE_TIMEOUT:
            try:
                msg = q.get(timeout=1)
                yield msg
                idle = 0
                if '"done"' in msg or '"error"' in msg:
                    break
            except queue.Empty:
                idle += 1

    return StreamingResponse(_generate(), media_type="text/event-stream")


@router.get("/nice/jobs/{job_id}/status")
def get_job_status(
    job_id: str,
    scope: CallerScope = Depends(require_admin),
) -> dict:
    """Return current status of an ingest job."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/nice/jobs")
def list_jobs(scope: CallerScope = Depends(require_admin)) -> list[dict]:
    """List all active and recently completed ingest jobs."""
    return list(_jobs.values())


_FETCH_LOADED_GUIDELINES = """
MATCH (g:Guideline)
WHERE g.source = 'nice_syndication_api'
OPTIONAL MATCH (g)-[:HAS_CHAPTER]->(ch:Chapter)
OPTIONAL MATCH (g)-[:HAS_RECOMMENDATION]->(r:Recommendation)
OPTIONAL MATCH (r)-[:HAS_RULE]->(rule:AppropriatenessRule)
RETURN
    g.id              AS code,
    g.title           AS title,
    g.type            AS guidance_type,
    g.publicationDate AS publication_date,
    count(DISTINCT ch)   AS chapter_count,
    count(DISTINCT r)    AS recommendation_count,
    count(DISTINCT CASE WHEN rule.status = 'pending_review' THEN rule END) AS rules_pending,
    count(DISTINCT CASE WHEN rule.status = 'active'         THEN rule END) AS rules_approved,
    count(DISTINCT CASE WHEN rule.status = 'rejected'       THEN rule END) AS rules_rejected
ORDER BY g.id
"""


@router.get("/nice/loaded")
def list_loaded_guidelines(
    scope: CallerScope = Depends(require_admin),
) -> list[dict]:
    """List all NICE guidelines stored in the knowledge graph with rule status.

    Returns one entry per Guideline node that originated from the NICE
    Syndication API.  Each entry includes chapter and recommendation counts,
    and a breakdown of AppropriatenessRule statuses so the admin can see
    at a glance which guidelines still need rule generation or review.

    Returns:
        List of dicts with keys: ``code``, ``title``, ``guidance_type``,
        ``publication_date``, ``chapter_count``, ``recommendation_count``,
        ``rules_pending``, ``rules_approved``, ``rules_rejected``.
    """
    neo = CodingGraphClient()
    try:
        rows = neo.run(_FETCH_LOADED_GUIDELINES)
        return [
            {
                "code": r["code"],
                "title": r.get("title", ""),
                "guidance_type": r.get("guidance_type", ""),
                "publication_date": r.get("publication_date", ""),
                "chapter_count": r.get("chapter_count", 0),
                "recommendation_count": r.get("recommendation_count", 0),
                "rules_pending": r.get("rules_pending", 0),
                "rules_approved": r.get("rules_approved", 0),
                "rules_rejected": r.get("rules_rejected", 0),
            }
            for r in rows
        ]
    finally:
        neo.close()


def _collect_leaf_items(chapter_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Recursively collect leaf recommendation items from a chapter JSON.

    NICE chapter JSON nests items in up to three levels:
        Chapter (top) → section group (Title only) → recommendation (Title + Text).

    Only items that carry actual recommendation wording (``Text`` field, or a
    ``Title`` with no sub-``Items``) are returned.  Intermediate groupings (e.g.
    "1.1 Colorectal cancer") are traversed but not stored as nodes.

    Args:
        chapter_data: Parsed JSON dict for a NICE chapter resource.

    Returns:
        Flat list of leaf item dicts each containing at least ``Title`` or ``Text``.
    """
    results: list[dict[str, Any]] = []

    def _walk(items: list[dict]) -> None:
        for item in items:
            sub = item.get("Items", [])
            if sub:
                _walk(sub)
            elif item.get("Text") or item.get("Title"):
                results.append(item)

    _walk(chapter_data.get("Items", chapter_data.get("Resources", [])))
    return results


def _run_ingest(job_id: str, code: str) -> None:
    """Background thread: fetch from NICE API and upsert to Neo4j."""
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_async_ingest(job_id, code))
    except Exception as exc:
        logger.exception("Ingest failed for %s: %s", code, exc)
        _emit(job_id, "error", {"status": "error", "error": str(exc)})
    finally:
        loop.close()


async def _async_ingest(job_id: str, code: str) -> None:
    """Async ingest: fetch NICE API content and build hierarchical Neo4j graph.

    Graph structure created::

        (Guideline)-[:HAS_CHAPTER]->(Chapter)-[:HAS_RECOMMENDATION]->(Recommendation)
        (Guideline)-[:HAS_RECOMMENDATION]->(Recommendation)   # shortcut for queries

    On re-ingest, all existing Chapters, Recommendations, and derived
    AppropriatenessRule nodes are deleted before re-creating from the API.
    """
    _emit(job_id, "progress", {"status": "running", "step": "Fetching guideline..."})
    client = NiceApiClient()
    upserter = NiceGraphUpserter()

    guidance = await client.get_guidance(code)
    _emit(job_id, "progress", {"step": "Saving guideline node..."})
    guideline_id = upserter.upsert_guideline(guidance)

    # Clear stale content so re-ingests produce a clean graph
    _emit(job_id, "progress", {"step": "Clearing previous content..."})
    upserter.clear_guideline_content(guideline_id)

    _emit(job_id, "progress", {"step": "Fetching chapters..."})
    chapters = await client.get_chapters(code)
    logger.info("Guideline %s has %d chapter(s)", code, len(chapters))

    total_recs = 0
    for ch_idx, chapter in enumerate(chapters):
        chapter_id = f"{guideline_id}:CH{ch_idx:03d}"
        chapter_title = chapter.get("Title", f"Chapter {ch_idx + 1}")
        upserter.upsert_chapter(guideline_id, chapter_id, chapter_title, ch_idx)

        href = chapter.get("Href", "") or chapter.get("Uri", "")
        if not href:
            logger.debug("Chapter %d of %s has no URI -- skipping content fetch", ch_idx, code)
            continue

        try:
            chapter_data = await client.get_chapter_content(href)
        except RuntimeError as exc:
            logger.debug("Could not fetch chapter '%s' for %s: %s", chapter_title, code, exc)
            continue

        leaf_items = _collect_leaf_items(chapter_data)
        _emit(job_id, "progress", {
            "step": f"Saving {len(leaf_items)} recommendations from '{chapter_title}'...",
        })

        for rec_idx, item in enumerate(leaf_items):
            rec_id = f"{chapter_id}:R{rec_idx:03d}"
            upserter.upsert_recommendation(guideline_id, rec_id, item, chapter_id=chapter_id)
            total_recs += 1

    title = guidance.get("Title", code)
    guidance_type = guidance.get("Type", "clinical-guideline")
    await client.add_to_catalogue(code, title, guidance_type)

    logger.info(
        "Ingest complete for %s: %d chapter(s), %d recommendation(s)",
        code, len(chapters), total_recs,
    )
    _emit(job_id, "done", {
        "status": "done",
        "step": "Complete",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "recommendation_count": total_recs,
        "chapter_count": len(chapters),
    })
