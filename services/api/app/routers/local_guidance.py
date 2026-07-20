"""Admin endpoints for structuring and importing local clinical guidelines."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db.neo4j_client import CodingGraphClient
from app.deps import require_admin
from app.schemas.local_guideline import (
    LocalChapterDraft,
    LocalGuidelineDraft,
    LocalGuidelineMetadata,
    LocalRecommendationDraft,
)
from app.services.guideline_graph_writer import GuidelineGraphWriter
from app.services.local_guideline_blank import build_blank_local_draft
from app.services.local_guideline_diff import diff_local_guidelines
from app.services.local_guideline_structurer import structure_local_guideline
from app.services.local_guideline_verifier import verify_local_guideline
from libs.auth.org_scope import CallerScope

router = APIRouter(prefix="/guidance/local", tags=["local-guidance"])

_FETCH_STORED_DRAFT = """
MATCH (g:Guideline {id: $guideline_id, source: 'local_guideline'})
OPTIONAL MATCH (g)-[:HAS_CHAPTER]->(ch:Chapter)-[:HAS_RECOMMENDATION]->(r:Recommendation)
RETURN g.id AS short_code, g.title AS title,
       coalesce(g.publicationDate, '') AS publication_date,
       coalesce(g.versionLabel, '') AS version_label,
       ch.title AS chapter_title, coalesce(ch.order, 0) AS chapter_order,
       coalesce(r.number, r.id) AS stable_key,
       coalesce(r.title, '') AS rec_title,
       coalesce(r.verbatim, '') AS verbatim,
       coalesce(r.likelyIncorrect, false) AS likely_incorrect
ORDER BY chapter_order, stable_key
"""

_FETCH_SUBGRAPH = """
MATCH (g:Guideline {id: $guideline_id, source: 'local_guideline'})
OPTIONAL MATCH (g)-[:HAS_CHAPTER]->(ch:Chapter)
OPTIONAL MATCH (ch)-[:HAS_RECOMMENDATION]->(r:Recommendation)
WHERE coalesce(r.isNormative, false)
OPTIONAL MATCH (r)-[:HAS_RULE]->(rule:AppropriatenessRule)
RETURN g.id AS guideline_id, g.title AS guideline_title, g.ingestVersion AS ingest_version,
       ch.id AS chapter_id, ch.title AS chapter_title, coalesce(ch.order, 0) AS chapter_order,
       r.id AS rec_id, r.number AS stable_key, r.title AS rec_title, r.verbatim AS verbatim,
       coalesce(r.likelyIncorrect, false) AS likely_incorrect,
       collect(DISTINCT {
           rule_id:    rule.id,
           status:     rule.status,
           name:       rule.name,
           created_at: toString(rule.createdAt)
       }) AS rules
ORDER BY chapter_order, rec_id
"""

_LINK_DOMAIN = """
MATCH (g:Guideline {id: $guideline_id, source: 'local_guideline'})
MATCH (d:AuditDomain {id: $domain_id})
MERGE (g)-[:HAS_DOMAIN]->(d)
RETURN d.id AS domain_id
"""


class StructureRequest(BaseModel):
    """Paste payload for local guideline structuring."""

    metadata: LocalGuidelineMetadata
    text: str = Field(min_length=20, max_length=200000)


class ImportRequest(BaseModel):
    """Verified draft payload for graph import."""

    draft: LocalGuidelineDraft


class CreateBlankGuidelineRequest(BaseModel):
    """Create a local guideline shell without pasted source text."""

    metadata: LocalGuidelineMetadata


class LinkDomainRequest(BaseModel):
    """A local guideline domain link."""

    domain_id: str = Field(min_length=1)


class RestructureRequest(BaseModel):
    """Paste updated text for an existing local guideline."""

    text: str = Field(min_length=20, max_length=200000)
    metadata: LocalGuidelineMetadata | None = None


class ReimportRequest(BaseModel):
    """Admin-confirmed draft for re-import (diff recomputed server-side)."""

    draft: LocalGuidelineDraft
    diff_job_id: str | None = None


@router.post("/structure")
async def structure_guideline(
    request: StructureRequest, scope: CallerScope = Depends(require_admin)
) -> LocalGuidelineDraft:
    """Build and verify a local guideline draft without persisting it."""
    _ = scope
    draft = structure_local_guideline(request.metadata, request.text)
    return verify_local_guideline(draft, request.text)


@router.post("/import", status_code=201)
async def import_guideline(
    request: ImportRequest, scope: CallerScope = Depends(require_admin)
) -> dict:
    """Persist only a verified local guideline draft."""
    _ = scope
    if request.draft.likely_incorrect:
        raise HTTPException(
            status_code=422,
            detail="Fix verification issues before importing this guideline.",
        )
    return GuidelineGraphWriter().upsert_local_guideline(request.draft)


@router.post("/create-blank", status_code=201)
async def create_blank_guideline(
    request: CreateBlankGuidelineRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict:
    """Create a local guideline shell for hand-authored rules (no paste)."""
    _ = scope
    draft = build_blank_local_draft(request.metadata)
    return GuidelineGraphWriter().upsert_local_guideline(draft)


@router.delete("/{guideline_id}")
async def delete_local_guideline(
    guideline_id: str, scope: CallerScope = Depends(require_admin)
) -> dict:
    """Delete a local guideline and clean related chapters, recommendations, rules."""
    _ = scope
    result = GuidelineGraphWriter().delete_local_guideline(guideline_id)
    if not result:
        raise HTTPException(status_code=404, detail="Local guideline not found.")
    return result


@router.post("/{guideline_id}/link-domain")
async def link_domain(
    guideline_id: str,
    request: LinkDomainRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict:
    """Link a locally curated guideline to an existing audit domain."""
    _ = scope
    client = CodingGraphClient()
    try:
        rows = client.run(
            _LINK_DOMAIN, guideline_id=guideline_id, domain_id=request.domain_id
        )
    finally:
        client.close()
    if not rows:
        raise HTTPException(status_code=404, detail="Guideline or domain not found.")
    return {"guideline_id": guideline_id, "domain_id": request.domain_id}


@router.get("/{guideline_id}/subgraph")
async def get_local_subgraph(
    guideline_id: str, scope: CallerScope = Depends(require_admin)
) -> dict:
    """Return current local guideline chapters and normative recommendations."""
    _ = scope
    client = CodingGraphClient()
    try:
        rows = client.run(_FETCH_SUBGRAPH, guideline_id=guideline_id)
    finally:
        client.close()
    if not rows:
        raise HTTPException(status_code=404, detail="Local guideline not found.")
    return _build_subgraph(rows)


@router.post("/{guideline_id}/re-structure")
async def restructure_guideline(
    guideline_id: str,
    request: RestructureRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict:
    """Re-structure pasted text and diff against the stored local guideline."""
    _ = scope
    previous = _load_stored_draft(guideline_id)
    meta = request.metadata or previous.metadata
    if meta.short_code != guideline_id:
        raise HTTPException(
            status_code=400,
            detail="Metadata short_code must match the guideline id.",
        )
    draft = verify_local_guideline(
        structure_local_guideline(meta, request.text), request.text
    )
    return {"draft": draft, "diff": diff_local_guidelines(previous, draft)}


@router.post("/{guideline_id}/re-import")
async def reimport_guideline(
    guideline_id: str,
    request: ReimportRequest,
    scope: CallerScope = Depends(require_admin),
) -> dict:
    """Re-import a draft after recomputing the diff server-side."""
    _ = scope
    _ = request.diff_job_id  # accepted for parity; never trusted
    if request.draft.metadata.short_code != guideline_id:
        raise HTTPException(
            status_code=400,
            detail="Draft short_code must match the guideline id.",
        )
    if request.draft.likely_incorrect:
        raise HTTPException(
            status_code=422,
            detail="Fix verification issues before re-importing.",
        )
    previous = _load_stored_draft(guideline_id)
    diff = diff_local_guidelines(previous, request.draft)
    result = GuidelineGraphWriter().upsert_local_guideline(request.draft)
    return {**result, "diff": diff}


def _load_stored_draft(guideline_id: str) -> LocalGuidelineDraft:
    """Load the current local guideline as a draft for diffing."""
    client = CodingGraphClient()
    try:
        rows = client.run(_FETCH_STORED_DRAFT, guideline_id=guideline_id)
    finally:
        client.close()
    if not rows:
        raise HTTPException(status_code=404, detail="Local guideline not found.")
    first = rows[0]
    chapters: dict[int, LocalChapterDraft] = {}
    for row in rows:
        order = int(row.get("chapter_order") or 0)
        chapter = chapters.setdefault(
            order,
            LocalChapterDraft(
                title=row.get("chapter_title") or f"Chapter {order}",
                order=order,
                recommendations=[],
            ),
        )
        if row.get("stable_key") and row.get("verbatim"):
            chapter.recommendations.append(
                LocalRecommendationDraft(
                    stable_key=row["stable_key"],
                    title=row.get("rec_title") or "",
                    verbatim=row["verbatim"],
                    verification_flag=bool(row.get("likely_incorrect")),
                )
            )
    return LocalGuidelineDraft(
        metadata=LocalGuidelineMetadata(
            short_code=first["short_code"],
            title=first.get("title") or guideline_id,
            publication_date=first.get("publication_date") or "",
            version_label=first.get("version_label") or "",
        ),
        chapters=[chapters[key] for key in sorted(chapters.keys())],
        likely_incorrect=False,
        verification_errors=[],
    )


def _build_subgraph(rows: list[dict]) -> dict:
    """Convert flat Neo4j rows into the common chapter tree shape."""
    chapters: dict[str, dict] = {}
    first = rows[0]
    for row in rows:
        chapter_id = row.get("chapter_id")
        if not chapter_id:
            continue
        chapter = chapters.setdefault(
            chapter_id,
            {
                "chapter_id": chapter_id,
                "chapter_title": row.get("chapter_title", ""),
                "order": row.get("chapter_order", 0),
                "recommendations": [],
            },
        )
        if row.get("rec_id"):
            raw_rules = [r for r in (row.get("rules") or []) if r.get("rule_id")]
            chapter["recommendations"].append(
                {
                    "rec_id": row["rec_id"],
                    "stable_key": row.get("stable_key", ""),
                    "rec_title": row.get("rec_title", ""),
                    "verbatim": row.get("verbatim", ""),
                    "is_normative": True,
                    "likely_incorrect": bool(row.get("likely_incorrect")),
                    "rules": raw_rules,
                }
            )
    chapter_list = sorted(chapters.values(), key=lambda value: value["order"])
    total_recs = sum(len(chapter["recommendations"]) for chapter in chapter_list)
    total_rules = sum(
        len(rec["rules"])
        for chapter in chapter_list
        for rec in chapter["recommendations"]
    )
    return {
        "guideline_id": first["guideline_id"],
        "guideline_title": first.get("guideline_title", ""),
        "ingest_version": first.get("ingest_version"),
        "chapters": chapter_list,
        "totals": {
            "chapters": len(chapter_list),
            "recommendations": total_recs,
            "rules": total_rules,
        },
    }
