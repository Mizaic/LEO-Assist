"""Load and expand multi-domain concept configs for NER mining."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from libs.domain_config.registry import NCDA_DOMAIN_CONFIGS
from libs.neo4j_client.client import KnowledgeGraphClient
from services.terminology_api.app.queries.terminology import DESCENDANTS_TEMPLATE

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[A-Za-z0-9]+")


@dataclass
class DomainConcept:
    concept_id: int
    preferred_term: str
    semantic_tag: str | None
    synonyms: list[str] = field(default_factory=list)
    source_keyword: str | None = None

    def all_surface_forms(self) -> list[str]:
        terms = [self.preferred_term] + self.synonyms
        if self.source_keyword:
            terms.append(self.source_keyword)
        seen: set[str] = set()
        out: list[str] = []
        for t in terms:
            s = _normalize_surface(t)
            if len(s) < 2:
                continue
            if s in seen:
                continue
            seen.add(s)
            out.append(s)
        return out


@dataclass
class DomainSearchConfig:
    domain_name: str
    source_file: str
    description: str
    semantic_tags: list[str]
    milestone_type: str | None = None
    concept_ids: list[int] = field(default_factory=list)
    concepts: list[DomainConcept] = field(default_factory=list)
    surface_forms: list[str] = field(default_factory=list)
    fulltext_queries: list[str] = field(default_factory=list)
    vector_phrases: list[str] = field(default_factory=list)
    entity_patterns: list[str] = field(default_factory=list)
    concept_map: dict[str, dict[str, Any]] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "domain_name": self.domain_name,
            "source_file": self.source_file,
            "description": self.description,
            "semantic_tags": self.semantic_tags,
            "milestone_type": self.milestone_type,
            "concept_ids": self.concept_ids,
            "concepts": [asdict(c) for c in self.concepts],
            "surface_forms": self.surface_forms,
            "fulltext_queries": self.fulltext_queries,
            "vector_phrases": self.vector_phrases,
            "entity_patterns": self.entity_patterns,
            "concept_map": self.concept_map,
            "stats": self.stats,
        }


def default_config_dir(repo_root: Path) -> Path:
    """Return the SNOMED config directory.

    Resolution order:
    1. ``NCDA_CONFIG_DIR`` environment variable (absolute path, CI/Docker friendly)
    2. ``configs/snomed/`` inside this repo (new canonical location)
    3. Legacy sibling ``auditor_2/agent/configs/`` (kept as fallback during transition)
    """
    from_env = os.environ.get("NCDA_CONFIG_DIR", "").strip()
    if from_env:
        p = Path(from_env)
        if p.exists():
            return p
        logger.warning("NCDA_CONFIG_DIR set but path not found: %s — falling back", p)

    local = repo_root / "configs" / "snomed"
    if local.exists():
        return local

    legacy = repo_root.parent / "auditor_2" / "agent" / "configs"
    logger.warning("configs/snomed/ not found; falling back to legacy path: %s", legacy)
    return legacy


def _normalize_surface(text: str | None) -> str:
    if not text:
        return ""
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _safe_domain_filename(domain_name: str) -> str:
    cfg = NCDA_DOMAIN_CONFIGS.get(domain_name)
    if cfg and cfg.file:
        return cfg.file
    return f"snomed_ncda_{domain_name}_mapping.json"


def discover_domain_files(config_dir: Path) -> dict[str, Path]:
    """Map domain_name -> file path using NCDA domain config registry."""
    files: dict[str, Path] = {}
    for domain_name, domain_cfg in NCDA_DOMAIN_CONFIGS.items():
        p = config_dir / domain_cfg.file
        if p.exists():
            files[domain_name] = p
            continue
        alt = config_dir / _safe_domain_filename(domain_name)
        if alt.exists():
            files[domain_name] = alt
        else:
            logger.warning("Domain config file not found for %s: %s", domain_name, p)
    return files


def _extract_concepts(raw: dict[str, Any]) -> list[DomainConcept]:
    mappings = raw.get("mappings") or {}
    concepts: list[DomainConcept] = []
    for keyword, payload in mappings.items():
        if not isinstance(payload, dict):
            continue
        cid = payload.get("concept_id")
        try:
            concept_id = int(cid)
        except (TypeError, ValueError):
            continue
        preferred = _normalize_surface(
            payload.get("preferred_term") or payload.get("guideline_name") or str(keyword)
        )
        if not preferred:
            continue
        semantic = payload.get("semantic_tag")
        if semantic is not None:
            semantic = str(semantic)
        synonyms = [
            _normalize_surface(s)
            for s in (payload.get("guideline_synonyms") or [])
            if _normalize_surface(str(s))
        ]
        concepts.append(
            DomainConcept(
                concept_id=concept_id,
                preferred_term=preferred,
                semantic_tag=semantic,
                synonyms=synonyms,
                source_keyword=_normalize_surface(str(keyword)),
            )
        )
    return concepts


def _mk_lucene_phrase(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    if len(_WORD_RE.findall(text)) <= 1:
        return escaped
    return f'"{escaped}"'


def _mk_pattern(text: str) -> str:
    """Create robust, case-insensitive regex pattern for a surface form."""
    escaped = re.escape(text)
    escaped = escaped.replace(r"\ ", r"\s+")
    has_word_start = bool(text and text[0].isalnum())
    has_word_end = bool(text and text[-1].isalnum())
    if has_word_start:
        escaped = r"\b" + escaped
    if has_word_end:
        escaped = escaped + r"\b"
    return escaped


def build_search_views(cfg: DomainSearchConfig) -> DomainSearchConfig:
    concept_map: dict[str, dict[str, Any]] = {}
    surfaces: set[str] = set()
    for c in cfg.concepts:
        for form in c.all_surface_forms():
            surfaces.add(form)
            concept_map[form.lower()] = {
                "concept_id": str(c.concept_id),
                "preferred_term": c.preferred_term,
                "semantic_tag": c.semantic_tag,
                "domain": cfg.domain_name,
            }

    # Longest first improves matching quality and overlap handling.
    ordered_surfaces = sorted(surfaces, key=lambda s: (-len(s), s.lower()))
    cfg.surface_forms = ordered_surfaces
    cfg.concept_map = concept_map
    # Query phrases are intentionally capped for runtime. We still keep all
    # surface forms for regex/entity extraction.
    cfg.fulltext_queries = [_mk_lucene_phrase(s) for s in ordered_surfaces[:120]]
    cfg.vector_phrases = ordered_surfaces[:80]
    cfg.entity_patterns = [_mk_pattern(s) for s in ordered_surfaces]
    cfg.concept_ids = sorted({c.concept_id for c in cfg.concepts})
    cfg.stats = {
        "concept_count": len(cfg.concepts),
        "surface_form_count": len(cfg.surface_forms),
        "fulltext_query_count": len(cfg.fulltext_queries),
        "vector_phrase_count": len(cfg.vector_phrases),
        "pattern_count": len(cfg.entity_patterns),
    }
    return cfg


def load_domain_configs(config_dir: Path) -> dict[str, DomainSearchConfig]:
    """Load all configured domains from JSON mapping files."""
    files = discover_domain_files(config_dir)
    domains: dict[str, DomainSearchConfig] = {}
    for domain_name, file_path in files.items():
        raw = json.loads(file_path.read_text(encoding="utf-8"))
        meta = raw.get("metadata") or {}
        dcfg = NCDA_DOMAIN_CONFIGS.get(domain_name)
        cfg = DomainSearchConfig(
            domain_name=domain_name,
            source_file=str(file_path),
            description=(dcfg.description if dcfg else str(meta.get("description", ""))),
            semantic_tags=list(dcfg.semantic_tags if dcfg else []),
            milestone_type=(dcfg.milestone_type if dcfg else None),
            concepts=_extract_concepts(raw),
        )
        domains[domain_name] = build_search_views(cfg)
    return domains


def _fetch_concept_forms(
    kg_session,
    concept_id: int,
    include_descendants: bool,
    descendant_depth: int,
    descendant_limit: int,
) -> list[str]:
    forms: list[str] = []

    rows_term = kg_session.run(
        """
        MATCH (c:Concept {id: $cid})<-[:DESCRIBES]-(t:Term)
        WHERE coalesce(t.active, true) = true
        RETURN DISTINCT t.surface_form AS form
        LIMIT 500
        """,
        cid=concept_id,
    )
    forms.extend([r.get("form", "") for r in rows_term if r.get("form")])

    rows_sf = kg_session.run(
        """
        MATCH (sf:SurfaceForm)-[:MAPS_TO]->(c:Concept {id: $cid})
        RETURN DISTINCT sf.form AS form
        LIMIT 500
        """,
        cid=concept_id,
    )
    forms.extend([r.get("form", "") for r in rows_sf if r.get("form")])

    if include_descendants:
        q = DESCENDANTS_TEMPLATE.format(depth=max(1, min(descendant_depth, 5)))
        rows_desc = kg_session.run(
            q,
            concept_id=concept_id,
            semantic_tag=None,
            limit=descendant_limit,
        )
        desc_ids = [int(r.get("snomed_concept_id")) for r in rows_desc if r.get("snomed_concept_id")]
        if desc_ids:
            rows_desc_terms = kg_session.run(
                """
                UNWIND $ids AS cid
                MATCH (c:Concept {id: cid})<-[:DESCRIBES]-(t:Term)
                WHERE coalesce(t.active, true) = true
                RETURN DISTINCT t.surface_form AS form
                LIMIT 2000
                """,
                ids=desc_ids,
            )
            forms.extend([r.get("form", "") for r in rows_desc_terms if r.get("form")])
    return [_normalize_surface(f) for f in forms if _normalize_surface(f)]


def expand_domains_with_kg(
    domains: dict[str, DomainSearchConfig],
    *,
    include_descendants: bool = True,
    descendant_depth: int = 2,
    descendant_limit: int = 200,
) -> dict[str, DomainSearchConfig]:
    """Expand domain surface forms using Knowledge Graph term/surfaceform nodes."""
    kg = KnowledgeGraphClient()
    try:
        with kg.session() as s:
            for dname, cfg in domains.items():
                logger.info("Expanding domain '%s' from KG (%d concepts)", dname, len(cfg.concept_ids))
                before = len(cfg.surface_forms)
                added = 0
                for cid in cfg.concept_ids:
                    for form in _fetch_concept_forms(
                        s,
                        cid,
                        include_descendants=include_descendants,
                        descendant_depth=descendant_depth,
                        descendant_limit=descendant_limit,
                    ):
                        key = form.lower()
                        if key in cfg.concept_map:
                            continue
                        cfg.concept_map[key] = {
                            "concept_id": str(cid),
                            "preferred_term": cfg.concept_map.get(key, {}).get("preferred_term", form),
                            "semantic_tag": None,
                            "domain": dname,
                            "source": "kg_expansion",
                        }
                        cfg.surface_forms.append(form)
                        added += 1
                # Rebuild search views from updated concept_map/surface_forms.
                # Keep concept objects unchanged; rebuild from surfaces.
                unique_surfaces = sorted(
                    { _normalize_surface(s) for s in cfg.surface_forms if _normalize_surface(s) },
                    key=lambda x: (-len(x), x.lower()),
                )
                cfg.surface_forms = unique_surfaces
                cfg.fulltext_queries = [_mk_lucene_phrase(s) for s in unique_surfaces[:200]]
                cfg.vector_phrases = unique_surfaces[:150]
                cfg.entity_patterns = [_mk_pattern(s) for s in unique_surfaces]
                cfg.stats.update(
                    {
                        "surface_form_count_before_kg": before,
                        "surface_form_count_after_kg": len(unique_surfaces),
                        "surface_forms_added_from_kg": added,
                        "fulltext_query_count": len(cfg.fulltext_queries),
                        "vector_phrase_count": len(cfg.vector_phrases),
                        "pattern_count": len(cfg.entity_patterns),
                    }
                )
    finally:
        kg.close()
    return domains


def dump_expanded_domains(
    domains: dict[str, DomainSearchConfig],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        dname: cfg.to_json_dict()
        for dname, cfg in domains.items()
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

