"""Knowledge-graph promotion for cancer_audit ``stage_of_diagnosis`` subdomain.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

1. Upserts ``ValueSet`` node ``ncda-stage-of-diagnosis`` (FHIR-shaped ``rawJson``) so
   ``DomainRegistry`` / anchor / analytics load the same concept set as the JSON file.
2. ``MERGE (AuditDomain {id: cancer_audit})-[:HAS_SUBDOMAIN]->(ValueSet)``.
3. Ensures ``(:Concept {id})`` stubs exist for every SNOMED code in the mapping (for
   ``SurfaceForm`` resolution).
4. Upserts ``SurfaceForm``-[:MAPS_TO]->Concept pins for mapping synonyms and a short
   list of encounter-shaped phrases.

Patient-graph ``:DOCUMENTS`` backfill lives in
``scripts/investigations/_backfill_uncoded_staging_documents.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
MAPPING_PATH = (
    REPO_ROOT / "configs" / "snomed" / "snomed_ncda_stage_of_diagnosis_mapping.json"
)
VS_ID = "ncda-stage-of-diagnosis"
VS_NAME = "stage_of_diagnosis"
SNOMED_SYSTEM = "http://snomed.info/sct"

_MERGE_CONCEPT = """
MERGE (c:Concept {id: $id})
SET c.fsn = coalesce(c.fsn, $fsn)
RETURN c.id AS id
"""

_UPSERT_SURFACE = """
MATCH (c:Concept {id: $concept_id})
MERGE (sf:SurfaceForm {normalized: $normalized})
ON CREATE SET sf.form = $form,
              sf.source = 'stage_of_diagnosis_kg',
              sf.status = 'active',
              sf.created_at = datetime(),
              sf.created_by = 'promote_stage_of_diagnosis'
SET sf.form = $form
MERGE (sf)-[m:MAPS_TO]->(c)
ON CREATE SET m.created_at = datetime(),
              m.created_by = 'promote_stage_of_diagnosis',
              m.approved_at = datetime()
SET m.confidence = 1.0,
    m.provenance = 'stage_of_diagnosis_mapping'
RETURN sf.normalized AS normalized, c.id AS concept_id
"""

# Phrases shaped like real encounter text (short keys resolve reliably in hybrid search).
_EXTRA_SURFACE: list[tuple[str, str]] = [
    ("TNM8 category: pT1b", "399703000"),
    ("TNM8 T stage: pT3b (at least)", "399703000"),
    ("pT3b", "399703000"),
    ("pT1 pNx", "399703000"),
    ("T4N1M1", "399703000"),
    ("t4N1M1", "399703000"),
    ("Breslow thickness: 3.7 mm (at least)", "106243009"),
    ("Breslow thickness 3.7 mm", "106243009"),
    ("Breslow thickness: 0.8mm", "106243009"),
    ("Clark level: III", "21165006"),
    ("Clark level III", "21165006"),
    ("Medical history of stage IV cancer", "258232002"),
    ("Suspected stage 4", "258232002"),
    ("stage 4 CA", "258232002"),
    ("Squamous cell carcinoma stage T1", "399703000"),
    ("grade 2 ductal", "369791003"),
    ("Gleason 3+4=7", "57403001"),
]


def load_mapping() -> dict[str, Any]:
    return json.loads(MAPPING_PATH.read_text(encoding="utf-8"))


def _build_concepts(mapping: dict[str, Any]) -> list[dict[str, Any]]:
    concepts: list[dict[str, Any]] = []
    for key, value in (mapping.get("mappings") or {}).items():
        cid = value.get("concept_id")
        display = value.get("preferred_term") or key.replace("_", " ")
        if not cid:
            continue
        designations: list[dict[str, Any]] = []
        for syn in value.get("guideline_synonyms") or []:
            if syn:
                designations.append({"use": {"code": "synonym"}, "value": str(syn)})
        designations.append({"use": {"code": "benchmark_key"}, "value": key})
        concepts.append(
            {"code": str(cid), "display": str(display), "designation": designations}
        )
    return concepts


def build_valueset_fhir_dict(mapping: dict[str, Any]) -> dict[str, Any]:
    concepts = _build_concepts(mapping)
    return {
        "resourceType": "ValueSet",
        "id": VS_ID,
        "url": f"https://leo.ai/fhir/ValueSet/{VS_ID}",
        "version": "1.0.0",
        "name": VS_NAME,
        "title": "Stage of diagnosis",
        "status": "active",
        "description": (
            "Cancer stage at diagnosis. Includes staging system concepts and "
            "available SNOMED stage findings for cancer audit tagging."
        ),
        "milestoneType": "diagnosis",
        "semanticTags": [
            "Clinical_finding",
            "Tumor_staging",
            "Observable_entity",
            "Staging_scale",
        ],
        "assertionFilter": [],
        "extension": [
            {
                "url": "https://leo.ai/fhir/StructureDefinition/domain-config",
                "extension": [
                    {"url": "milestoneType", "valueCode": "diagnosis"},
                    {"url": "semanticTag", "valueString": "Clinical_finding"},
                    {"url": "semanticTag", "valueString": "Tumor_staging"},
                    {"url": "semanticTag", "valueString": "Observable_entity"},
                    {"url": "semanticTag", "valueString": "Staging_scale"},
                ],
            }
        ],
        "compose": {"include": [{"system": SNOMED_SYSTEM, "concept": concepts}]},
    }


def _upsert_valueset_flat(vs_id: str, vs_dict: dict[str, Any]) -> None:
    analytics = REPO_ROOT / "services" / "analytics_api"
    if str(analytics) not in sys.path:
        sys.path.insert(0, str(analytics))
    from app.routers.domains import _upsert_valueset_flat

    _upsert_valueset_flat(vs_id, vs_dict)


def link_valueset_to_cancer_audit(kg: Any) -> None:
    kg.run(
        "MATCH (d:AuditDomain {id: 'cancer_audit'}), (v:ValueSet {id: $vs_id}) "
        "MERGE (d)-[:HAS_SUBDOMAIN]->(v)",
        vs_id=VS_ID,
    )


def seed_valueset_to_kg(mapping: dict[str, Any] | None = None) -> None:
    """Upsert ValueSet flat row + rawJson and link under ``cancer_audit``."""
    from libs.neo4j_client.client import KnowledgeGraphClient

    m = mapping if mapping is not None else load_mapping()
    vs = build_valueset_fhir_dict(m)
    _upsert_valueset_flat(VS_ID, vs)
    kg = KnowledgeGraphClient()
    try:
        link_valueset_to_cancer_audit(kg)
    finally:
        kg.close()


def ensure_concepts_for_mapping(kg: Any, mapping: dict[str, Any]) -> int:
    """MERGE minimal :Concept nodes for terminology / surface resolution."""
    n = 0
    for _key, entry in (mapping.get("mappings") or {}).items():
        cid = entry.get("concept_id")
        if cid is None:
            continue
        fsn = str(entry.get("preferred_term") or "")
        kg.run(_MERGE_CONCEPT, id=str(int(cid)), fsn=fsn)
        n += 1
    return n


def _normalize_form(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _collect_surface_pairs(mapping: dict[str, Any]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for _key, entry in (mapping.get("mappings") or {}).items():
        cid = entry.get("concept_id")
        if cid is None:
            continue
        cs = str(int(cid))
        term = (entry.get("preferred_term") or "").strip()
        if term:
            pairs.append((term, cs))
        for syn in entry.get("guideline_synonyms") or []:
            syn = str(syn).strip()
            if syn:
                pairs.append((syn, cs))
    pairs.extend(_EXTRA_SURFACE)
    return pairs


def ensure_surface_forms_for_mapping(kg: Any, mapping: dict[str, Any]) -> tuple[int, int]:
    """Return (written_or_updated, skipped_duplicates)."""
    seen: set[tuple[str, str]] = set()
    written = 0
    skipped = 0
    for form, concept_id in _collect_surface_pairs(mapping):
        norm = _normalize_form(form)
        if not norm:
            continue
        key = (norm, concept_id)
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        rows = kg.run(
            _UPSERT_SURFACE,
            normalized=norm,
            form=form.strip(),
            concept_id=concept_id,
        )
        if rows:
            written += 1
    return written, skipped


def verify_subdomain_linked(kg: Any) -> bool:
    rows = kg.run(
        "MATCH (d:AuditDomain {id: 'cancer_audit'})-[:HAS_SUBDOMAIN]->(v:ValueSet {id: $id}) "
        "RETURN v.rawJson AS raw, v.milestoneType AS milestoneType, v.name AS name",
        id=VS_ID,
    )
    if not rows:
        return False
    row = rows[0]
    raw = row.get("raw") or "{}"
    vs = json.loads(raw) if isinstance(raw, str) else raw
    concept_count = sum(
        len(include.get("concept") or [])
        for include in (vs.get("compose") or {}).get("include") or []
    )
    return (
        row.get("name") == VS_NAME
        and row.get("milestoneType") == "diagnosis"
        and concept_count > 0
    )
