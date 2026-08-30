"""NICE guideline ingestion endpoints.

Atlas trace:
  DO: DO-24AA8840
  DI: DI-693FFEEA
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-24AA8840")

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
from app.services.nice_api_client import NICE_CODE_RE, NiceApiClient, parse_nice_ms_date
from app.services.nice_graph_upserter import NiceGraphUpserter
from app.services.recommendation_key_matcher import (
    NewRecommendation,
    OldRecommendation,
    match_recommendation_keys,
)
from libs.auth.org_scope import CallerScope

logger = logging.getLogger(__name__)
router = APIRouter(tags=["nice-guidance"])

_jobs: dict[str, dict[str, Any]] = {}
_queues: dict[str, queue.Queue] = {}
_IDLE_TIMEOUT = 300


class NiceIngestRequest(BaseModel):
    """Request body for POST /nice/ingest."""

    code: str
    diff_job_id: str | None = None

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
    logger.info(
        "Redis catalogue empty -- falling back to live NICE index search for %r", q
    )
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
            logger.debug(
                "Could not fetch Redis catalogue for taxonomy title enrichment -- codes shown only"
            )

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
                subcats.append(
                    {
                        "id": sub["id"],
                        "title": sub.get("title", ""),
                        "guideline_count": len(codes),
                        "loaded_count": sum(1 for c in codes if c in loaded_set),
                        "guidelines": guidelines,
                    }
                )
            categories.append(
                {
                    "id": row["id"],
                    "title": row["title"],
                    "subcategories": subcats,
                }
            )

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

            _jobs[job_id].update(
                {
                    "status": "done",
                    "catalogue_count": count,
                    "taxonomy_categories": taxonomy_counts.get("categories", 0),
                    "taxonomy_subcategories": taxonomy_counts.get("subcategories", 0),
                    "taxonomy_domains": taxonomy_counts.get("domains", 0),
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }
            )
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

    diff_result: dict | None = None
    if req.diff_job_id:
        from app.routers.nice_diff import _diff_jobs

        diff_job = _diff_jobs.get(req.diff_job_id)
        if diff_job and diff_job.get("status") == "done":
            diff_result = diff_job.get("diff")

    thread = threading.Thread(
        target=_run_ingest,
        args=(job_id, code, diff_result),
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
WHERE g.source IN ['nice_syndication_api', 'local_guideline']
OPTIONAL MATCH (g)-[:HAS_CHAPTER]->(ch:Chapter)
OPTIONAL MATCH (g)-[:HAS_RECOMMENDATION]->(r:Recommendation)
OPTIONAL MATCH (r)-[:HAS_RULE]->(rule:AppropriatenessRule)
OPTIONAL MATCH (g)-[:HAS_DOMAIN]->(domain:AuditDomain)
RETURN
    g.id              AS code,
    g.title           AS title,
    g.type            AS guidance_type,
    g.publicationDate AS publication_date,
    g.source          AS guideline_source,
    collect(DISTINCT domain.id)[0]   AS domain_id,
    collect(DISTINCT domain.name)[0] AS domain_name,
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
                "guideline_source": r.get("guideline_source", ""),
                "domain_id": r.get("domain_id") or "",
                "domain_name": r.get("domain_name") or "",
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


_FETCH_GUIDELINE_SUBGRAPH = """
MATCH (g:Guideline {id: $code})
OPTIONAL MATCH (g)-[:HAS_CHAPTER]->(ch:Chapter)
OPTIONAL MATCH (ch)-[:HAS_RECOMMENDATION]->(r:Recommendation)
OPTIONAL MATCH (r)-[:HAS_RULE]->(rule:AppropriatenessRule)
RETURN
    g.id              AS guideline_id,
    g.title           AS guideline_title,
    g.ingestVersion   AS ingest_version,
    g.publicationDate AS publication_date,
    ch.id             AS chapter_id,
    ch.title          AS chapter_title,
    coalesce(ch.order, 0) AS chapter_order,
    r.id                            AS rec_id,
    r.verbatim                      AS verbatim,
    r.title                         AS rec_title,
    r.urgency                       AS urgency,
    r.strength                      AS strength,
    r.sectionTitle                  AS section_title,
    coalesce(r.isNormative, false)  AS is_normative,
    r.versionId                     AS rec_version_id,
    collect(DISTINCT {
        rule_id:    rule.id,
        status:     rule.status,
        name:       rule.name,
        created_at: toString(rule.createdAt)
    }) AS rules
ORDER BY chapter_order, rec_id
"""


@router.get("/nice/{code}/subgraph")
def get_guideline_subgraph(
    code: str,
    scope: CallerScope = Depends(require_admin),
) -> dict:
    """Return the full Neo4j subgraph for a NICE guideline as a structured tree.

    This endpoint lets administrators inspect exactly what is stored in the
    knowledge graph — chapters, recommendations with their full verbatim text,
    and any rules — without needing direct Neo4j browser access.

    Returns a tree shaped as::

        {
          "guideline_id": "NG12",
          "guideline_title": "...",
          "ingest_version": 2,
          "chapters": [
            {
              "chapter_id": "NG12:v2:CH000",
              "chapter_title": "1 Recommendations",
              "order": 0,
              "recommendations": [
                {
                  "rec_id": "NG12:v2:CH000:SEC000:R000",
                  "rec_title": "1.1.1",
                  "verbatim": "Offer a 2-week-wait referral ...",
                  "urgency": "urgent_2w",
                  "rules": [{"rule_id": "...", "status": "active", ...}]
                }
              ]
            }
          ],
          "totals": {"chapters": 3, "recommendations": 42, "rules": 15}
        }

    Raises:
        404: If the guideline code is not found in Neo4j.
    """
    code_upper = code.strip().upper()
    neo = CodingGraphClient()
    try:
        rows = neo.run(_FETCH_GUIDELINE_SUBGRAPH, code=code_upper)
    finally:
        neo.close()

    if not rows:
        raise HTTPException(
            status_code=404, detail=f"Guideline {code_upper} not found in Neo4j"
        )

    # Build tree from flat rows
    guideline_info: dict = {}
    chapters: dict[str, dict] = {}  # chapter_id → chapter dict

    for row in rows:
        if not guideline_info:
            guideline_info = {
                "guideline_id": row["guideline_id"],
                "guideline_title": row.get("guideline_title", ""),
                "ingest_version": row.get("ingest_version"),
                "publication_date": row.get("publication_date", ""),
            }

        ch_id = row.get("chapter_id")
        if ch_id and ch_id not in chapters:
            chapters[ch_id] = {
                "chapter_id": ch_id,
                "chapter_title": row.get("chapter_title", ""),
                "order": row.get("chapter_order", 0),
                "recommendations": [],
            }

        rec_id = row.get("rec_id")
        if rec_id and ch_id:
            # Filter out NULL-only rule entries (OPTIONAL MATCH with no rules)
            raw_rules = [r for r in (row.get("rules") or []) if r.get("rule_id")]
            chapters[ch_id]["recommendations"].append(
                {
                    "rec_id": rec_id,
                    "rec_title": row.get("rec_title", ""),
                    "verbatim": row.get("verbatim", ""),
                    "urgency": row.get("urgency", ""),
                    "strength": row.get("strength", ""),
                    "section_title": row.get("section_title", ""),
                    "is_normative": row.get("is_normative", False),
                    "version_id": row.get("rec_version_id", ""),
                    "rules": raw_rules,
                }
            )

    chapter_list = sorted(chapters.values(), key=lambda c: c["order"])
    total_recs = sum(len(c["recommendations"]) for c in chapter_list)
    total_rules = sum(
        len(r["rules"]) for c in chapter_list for r in c["recommendations"]
    )

    return {
        **guideline_info,
        "chapters": chapter_list,
        "totals": {
            "chapters": len(chapter_list),
            "recommendations": total_recs,
            "rules": total_rules,
        },
    }


_FETCH_GUIDELINE_LOCAL_DATE = """
MATCH (g:Guideline {id: $code})
WHERE g.source = 'nice_syndication_api'
RETURN
    g.lastModifiedDate                AS last_modified_date,
    toString(date(g.createdAt))       AS ingest_date
"""


@router.get("/nice/{code}/check-update")
async def check_guideline_update(
    code: str,
    scope: CallerScope = Depends(require_admin),
) -> dict:
    """Check whether NICE has published a newer version of a loaded guideline.

    Fetches the live NICE ``LastModified`` timestamp and compares it against
    the ``lastModifiedDate`` stored in Neo4j at last ingest.  The UI calls
    this per guideline from the 'Check for updates' toolbar action.

    Returns:
        {
          "code": "NG12",
          "local_date": "2024-04-15",
          "remote_date": "2026-04-15",
          "update_available": true,
          "remote_title": "Suspected cancer: recognition and referral"
        }

    Raises:
        404: Guideline is not loaded in Neo4j.
        503: NICE Syndication API is unreachable.
    """
    code_upper = code.strip().upper()
    neo = CodingGraphClient()
    try:
        rows = neo.run(_FETCH_GUIDELINE_LOCAL_DATE, code=code_upper)
    finally:
        neo.close()

    if not rows:
        raise HTTPException(
            status_code=404, detail=f"Guideline {code_upper} not loaded"
        )

    local_date: str = rows[0].get("last_modified_date") or ""
    ingest_date: str = rows[0].get("ingest_date") or ""

    try:
        guidance = await NiceApiClient().get_guidance(code_upper)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503, detail=f"NICE API unreachable: {exc}"
        ) from exc

    meta = guidance.get("MetadataApplicationProfile") or {}
    raw_remote = guidance.get("LastModified") or meta.get("Modified") or ""
    remote_date: str = parse_nice_ms_date(raw_remote)
    remote_title: str = guidance.get("Title", "")

    # Compare stored last-modified against the live API.
    # For guidelines ingested before the date-fix (lastModifiedDate is null),
    # fall back to comparing the ingest date so they are not silently missed.
    compare_local = local_date or ingest_date
    update_available = bool(
        compare_local and remote_date and remote_date > compare_local
    )

    return {
        "code": code_upper,
        "local_date": local_date,
        "ingest_date": ingest_date,
        "remote_date": remote_date,
        "update_available": update_available,
        "remote_title": remote_title,
    }


def _extract_recommendations_from_section(
    section_json: dict[str, Any],
    guidance_number: str,
    chapter_id: str | None = None,
) -> list[dict[str, Any]]:
    """Parse a NICE section's ``Content`` XHTML to extract individual recommendations.

    The NICE Syndication API delivers recommendation text inside a ``Content``
    field of section-level JSON as XHTML.  Each **canonical** recommendation is
    wrapped in::

        <article class="numbered-paragraph" id="ng12-chapter-1-recommendations">
          <h5>1.1.1</h5>
          <p>Offer a 2-week-wait referral …</p>
        </article>

    This function extracts every such article and returns it as a plain dict
    compatible with :meth:`NiceGraphUpserter.upsert_recommendation`.

    **Why no fallback**: NICE guidelines contain two presentations of the same
    content — chapters of numbered recommendations (canonical) and cross-reference
    chapters organised by symptom/sign.  The cross-reference chapters contain the
    same recommendations as prose tables, not as ``<article>`` elements.  If we
    used a fallback to store the entire section as a single recommendation we
    would create duplicate, corrupt "recommendations" from the symptom index
    (e.g. one giant blob covering Abdominal pain, Dysphagia, Rectal bleeding …).
    Returning an empty list for non-article sections is intentional — only
    numbered recommendation chapters are ingested.

    Each returned dict carries ``isNormative: True`` so downstream consumers
    (rule generator, bitmap compiler) can distinguish canonical recs from any
    legacy fallback data that may already be in the graph.

    Alongside the flattened ``Text``, each dict also carries
    ``ListStructure`` -- the recommendation's own nested list markup,
    parsed by :func:`nice_list_parser.parse_recommendation_list_structure`
    and offset-aligned to that SAME ``Text`` string. ``None`` when the
    recommendation is a plain sentence with no ``<ul>`` at all (most of
    them). See the highlight-to-build wizard plan's "Ingestion" section.

    Args:
        section_json: Parsed NICE section JSON (must contain ``Content``).
        guidance_number: NICE guidance code (used to construct stable IDs).
        chapter_id: Optional chapter ID for linking.

    Returns:
        List of recommendation dicts, each with ``Text`` (verbatim clinical text),
        ``Title`` (number/heading), ``SectionId``, ``SectionTitle``,
        ``ChapterId``, ``ListStructure``, and ``isNormative`` keys.  Empty
        list if the section contains no ``<article class="numbered-paragraph">``
        elements.
    """
    from bs4 import BeautifulSoup  # imported here to keep module-level imports light

    from app.services.companion_panel_parser import (
        parse_companion_panels_after_article,
    )
    from app.services.nice_list_parser import (
        parse_recommendation_list_structure,
        recommendation_title_from_article,
    )

    html = (section_json or {}).get("Content") or ""
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    section_id = (section_json or {}).get("SectionId") or ""
    section_title = (section_json or {}).get("Title") or ""
    chapter_id_from_api = (section_json or {}).get("ChapterId") or chapter_id

    recs: list[dict[str, Any]] = []
    for article in soup.find_all("article", {"class": "numbered-paragraph"}):
        article_id = article.get("id") or ""
        rec_title = recommendation_title_from_article(article, section_title)
        inner_text = article.get_text(" ", strip=True)
        if not inner_text:
            continue
        companion_panels = parse_companion_panels_after_article(article, inner_text)
        recs.append(
            {
                "Title": rec_title,
                "Text": inner_text,
                "ArticleId": article_id,
                "SectionId": section_id,
                # SectionTitle = the cancer-site / topic label from the section heading
                # e.g. "Lung cancer", "Oesophageal cancer", "1.1 Lung cancer"
                "SectionTitle": section_title,
                "ChapterId": chapter_id_from_api,
                # True = came from a canonical <article> element, not a cross-ref table
                "isNormative": True,
                "ListStructure": parse_recommendation_list_structure(
                    article, inner_text
                ),
                # Sibling panel--primary boxes (e.g. NG12 1.7.1 weighted
                # 7-point checklist) that sit outside the <article>.
                "CompanionPanels": companion_panels or None,
            }
        )

    # No fallback: sections without <article> elements are cross-reference tables
    # (symptom/sign index chapters) — returning [] intentionally skips them.
    return recs


# Kept for unit-test backward compat (tests that mock chapter Items structure)
def _collect_leaf_items(chapter_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Recursively collect leaf items from a chapter JSON Items tree.

    .. deprecated::
        The ingest pipeline now uses :func:`_extract_recommendations_from_section`
        which parses the section-level ``Content`` HTML to obtain actual
        recommendation text.  This function is retained for unit tests that
        mock the old chapter-Items API shape.
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


def _run_ingest(job_id: str, code: str, diff_result: dict | None = None) -> None:
    """Background thread: fetch from NICE API and upsert to Neo4j."""
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_async_ingest(job_id, code, diff_result))
    except Exception as exc:
        logger.exception("Ingest failed for %s: %s", code, exc)
        _emit(job_id, "error", {"status": "error", "error": str(exc)})
    finally:
        loop.close()


async def _walk_chapter_recommendations(
    client: NiceApiClient,
    upserter: NiceGraphUpserter,
    code: str,
    chapters: list[dict[str, Any]],
    guideline_id: str,
    version_id: str,
    job_id: str,
) -> list[dict[str, Any]]:
    """Walk every chapter/section, upserting Chapter nodes and collecting
    every recommendation found -- one dict per recommendation:
    ``{"rec_id", "chapter_id", "item"}``.

    Recommendation *upserting* is deliberately deferred to the caller:
    ``recommendation_key_matcher.match_recommendation_keys()`` needs to see
    every new recommendation's number before it can safely resolve any
    single one's stable identity (an old recommendation whose number
    survives elsewhere must never be claimed by a different new
    recommendation's text-similarity fallback -- see that module's
    docstring). Chapter nodes have no such dependency, so they're still
    upserted here, same as before this was extracted.
    """
    entries: list[dict[str, Any]] = []
    for ch_idx, chapter in enumerate(chapters):
        chapter_id = f"{version_id}:CH{ch_idx:03d}"
        chapter_title = chapter.get("Title", f"Chapter {ch_idx + 1}")
        upserter.upsert_chapter(
            guideline_id, chapter_id, chapter_title, ch_idx, version_id=version_id
        )

        href = chapter.get("Href", "") or chapter.get("Uri", "")
        if not href:
            continue

        try:
            chapter_data = await client.get_chapter_content(href)
        except RuntimeError as exc:
            logger.debug("Could not fetch chapter '%s': %s", chapter_title, exc)
            continue

        section_uris = client.get_section_uris(chapter_data)
        logger.debug("Chapter '%s' has %d section(s)", chapter_title, len(section_uris))
        if not section_uris:
            # Some chapters (appendices, evidence reviews) have no section
            # links -- skip them; they don't contain numbered recommendations.
            logger.debug("Skipping chapter '%s' — no section links", chapter_title)
            continue

        for sec_idx, sec_uri in enumerate(section_uris):
            entries.extend(
                await _collect_section_recommendations(
                    client, code, sec_uri, chapter_id, sec_idx, chapter_title, job_id
                )
            )
    return entries


async def _collect_section_recommendations(
    client: NiceApiClient,
    code: str,
    sec_uri: str,
    chapter_id: str,
    sec_idx: int,
    chapter_title: str,
    job_id: str,
) -> list[dict[str, Any]]:
    """Fetch one section and return its recommendations as collected
    entries, or ``[]`` on fetch failure / no recommendations."""
    try:
        section_data = await client.get_section_content(sec_uri)
    except RuntimeError as exc:
        logger.debug("Could not fetch section %s: %s", sec_uri, exc)
        return []

    rec_items = _extract_recommendations_from_section(
        section_data, code, chapter_id=chapter_id
    )
    if not rec_items:
        logger.debug("Section %s yielded no recommendations", sec_uri)
        return []

    _emit(
        job_id,
        "progress",
        {
            "step": (
                f"'{chapter_title}' › section {sec_idx + 1}: "
                f"{len(rec_items)} recommendation(s)…"
            ),
        },
    )
    return [
        {
            "rec_id": f"{chapter_id}:SEC{sec_idx:03d}:R{rec_idx:03d}",
            "chapter_id": chapter_id,
            "item": item,
        }
        for rec_idx, item in enumerate(rec_items)
    ]


def _resolve_and_upsert_recommendations(
    upserter: NiceGraphUpserter,
    guideline_id: str,
    version_id: str,
    rec_entries: list[dict[str, Any]],
    old_recs: list[dict[str, Any]],
) -> int:
    """Resolve a stable ``recommendation_key`` for every collected
    recommendation, then upsert each one with its resolved identity.

    ``old_recs`` empty (first-ever ingest) mints a fresh key for
    everything, no matching attempted -- see
    ``recommendation_key_matcher.match_recommendation_keys()``.

    Returns the number of recommendations upserted.
    """
    new_recs = [
        NewRecommendation(
            ref=entry["rec_id"],
            number=entry["item"].get("Title", ""),
            text=entry["item"].get("Text", entry["item"].get("Title", "")),
        )
        for entry in rec_entries
    ]
    old_recommendations = [
        OldRecommendation(
            number=row["number"],
            text=row.get("text") or "",
            recommendation_key=row["recommendation_key"],
        )
        for row in old_recs
        if row.get("number")
    ]
    key_matches = match_recommendation_keys(new_recs, old_recommendations)

    for entry in rec_entries:
        match = key_matches[entry["rec_id"]]
        upserter.upsert_recommendation(
            guideline_id,
            entry["rec_id"],
            entry["item"],
            chapter_id=entry["chapter_id"],
            version_id=version_id,
            recommendation_key=match.recommendation_key,
            renumbered_from=match.renumbered_from,
        )
    return len(rec_entries)


async def _async_ingest(
    job_id: str, code: str, diff_result: dict | None = None
) -> None:
    """Async ingest: NICE Syndication API -> Neo4j hierarchical graph.

    When *diff_result* is supplied (smart ingest) only rules for changed or
    removed recommendations are affected; rules for unchanged recommendations
    are re-attached to the new recommendation nodes so reviewers keep their
    approved work.

    Rules not yet approved (``pending_review``) for a changed/removed
    recommendation are archived (``superseded``) so they drop out of the
    review queue. Already-**approved** rules (``active``) are never
    superseded by ingest -- they stay active (still enforced) and are only
    flagged (``guidelineTextChanged=true``) so a human decides whether to
    re-approve, edit, or explicitly retire them. See
    NiceGraphUpserter.clear_guideline_content().

    Pipeline (3 levels, matching the NICE API structure)
    -----------------------------------------------------
    Level 1 -- Guideline document
        ``GET /NG12.json``  ->  list of chapter ``Uri`` links
    Level 2 -- Chapter JSON
        ``GET /NG12-chapter-1.json``  ->  list of section ``Uri`` links
        (Resources where Rel = "/linkrels/guidance/section")
    Level 3 -- Section JSON  <- **this is where the recommendation text lives**
        ``GET /NG12-section-1.1.json``  ->  ``Content`` field (XHTML)
        Parsed with BeautifulSoup -> ``<article class="numbered-paragraph">``
        -> one Recommendation node per article (full clinical text as verbatim)

    Versioning
    ----------
    Each ingest increments ``Guideline.ingestVersion``.  Child node IDs embed
    the version so old nodes (and their GuidanceAuditEvent decisions) are never
    overwritten::

        Chapter:        ``NG12:v2:CH000``
        Recommendation: ``NG12:v2:CH000:SEC001:R003``

    Graph structure created
    -----------------------
    ::

        (Guideline)-[:HAS_CHAPTER]->(Chapter)
        (Chapter)-[:HAS_RECOMMENDATION]->(Recommendation)
        (Guideline)-[:HAS_RECOMMENDATION]->(Recommendation)   # bitmap shortcut
    """
    _emit(job_id, "progress", {"status": "running", "step": "Fetching guideline..."})
    client = NiceApiClient()
    upserter = NiceGraphUpserter()

    guidance = await client.get_guidance(code)
    _emit(job_id, "progress", {"step": "Saving guideline node..."})

    guideline_id, ingest_version = upserter.upsert_guideline(guidance)
    old_version_id = (
        f"{guideline_id}:v{ingest_version - 1}" if ingest_version > 1 else None
    )
    version_id = f"{guideline_id}:v{ingest_version}"

    if ingest_version > 1:
        _emit(
            job_id,
            "progress",
            {
                "step": f"Archiving previous version (v{ingest_version - 1}) for audit trail...",
            },
        )

    # Smart ingest: only supersede rules for changed/removed recs.
    # Full ingest: supersede all (changed_numbers=None).
    changed_numbers: list[str] | None = None
    unchanged_numbers: list[str] = []
    if diff_result and ingest_version > 1:
        changed_numbers = [c["number"] for c in diff_result.get("modified", [])] + [
            c["number"] for c in diff_result.get("removed", [])
        ]
        unchanged_numbers = diff_result.get("_unchanged_numbers", [])

    archive_result = upserter.clear_guideline_content(guideline_id, changed_numbers)
    superseded = archive_result["superseded"]
    flagged_active = archive_result["flagged_active"]
    if superseded or flagged_active:
        step_parts = []
        if superseded:
            step_parts.append(f"archived {superseded} awaiting-review rule(s)")
        if flagged_active:
            step_parts.append(
                f"flagged {flagged_active} approved rule(s) for re-review "
                "(still active, not retired)"
            )
        _emit(
            job_id,
            "progress",
            {
                "step": f"{'; '.join(step_parts).capitalize()} — previous decisions preserved."
            },
        )

    _emit(job_id, "progress", {"step": "Fetching chapters..."})
    chapters = await client.get_chapters(code)
    logger.info("Guideline %s v%d: %d chapter(s)", code, ingest_version, len(chapters))

    rec_entries = await _walk_chapter_recommendations(
        client, upserter, code, chapters, guideline_id, version_id, job_id
    )

    old_recs = (
        upserter.fetch_recommendations_for_key_matching(guideline_id, old_version_id)
        if old_version_id
        else []
    )
    total_recs = _resolve_and_upsert_recommendations(
        upserter, guideline_id, version_id, rec_entries, old_recs
    )

    title = guidance.get("Title", code)
    guidance_type = guidance.get(
        "GuidanceType", guidance.get("Type", "clinical-guideline")
    )
    await client.add_to_catalogue(code, title, guidance_type)

    # Smart ingest: re-attach unchanged rules to the new rec nodes.
    reattached = 0
    if unchanged_numbers and old_version_id:
        _emit(
            job_id,
            "progress",
            {
                "step": f"Re-attaching {len(unchanged_numbers)} unchanged rule set(s)...",
            },
        )
        reattached = upserter.reattach_unchanged_rules(
            guideline_id, old_version_id, version_id, unchanged_numbers
        )

    logger.info(
        "Ingest complete: %s v%d  chapters=%d  recommendations=%d",
        code,
        ingest_version,
        len(chapters),
        total_recs,
    )
    _emit(
        job_id,
        "done",
        {
            "status": "done",
            "step": "Complete",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "recommendation_count": total_recs,
            "chapter_count": len(chapters),
            "ingest_version": ingest_version,
            "version_id": version_id,
            "rules_reattached": reattached,
            "smart_ingest": diff_result is not None,
        },
    )
