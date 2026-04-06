"""Full audit of all SurfaceForm -> Concept MAPS_TO relationships.

Pulls every surface form from the knowledge graph via the Terminology API,
then applies heuristic checks to flag suspect mappings before any guideline
rules are committed.

Checks applied
--------------
SITUATION_FOR_ACTIVE_FINDING
    Form text implies a positive clinical finding but concept semantic_tag is
    'situation'.  E.g. "chest pain" -> "No chest pain (situation)".

PROCEDURE_FOR_SYMPTOM
    Form text describes a symptom/sign but concept is a procedure.

MULTI_MAPPING
    Same normalised form has more than one MAPS_TO edge (resolver uses highest
    confidence, but duplicates are noise and can hide wrong mappings).

GUIDELINE_CONFIG_LOADER
    Source is 'guideline_config_loader'. These were found to inject wrong
    'history of X' situation codes.  Flag all for manual review.

MORPHOLOGIC_FOR_FINDING
    Concept semantic_tag is 'morphologic abnormality' for a plain-symptom form.

INACTIVE_CONCEPT
    The MAPS_TO target is inactive in SNOMED (c.active = false).

LOW_CONFIDENCE_MANUAL
    A manually-written surface form (source='manual') has confidence < 1.0,
    which suggests it was written in error.

SUSPECT_SITUATION_TAG
    Concept semantic_tag = 'situation' and form does NOT begin with common
    negative/history prefixes. Includes absence situations, history-of, etc.

Outputs
-------
  scripts/investigations/surface_form_audit.json  -- machine-readable full report
  stdout                                           -- summary + flagged rows
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

from neo4j import GraphDatabase

OUTPUT_PATH = ROOT / "scripts" / "investigations" / "surface_form_audit.json"

# ---------------------------------------------------------------------------
# Neo4j connection
# ---------------------------------------------------------------------------
kg_uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
kg_user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
kg_pass = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

# ---------------------------------------------------------------------------
# Cypher: pull every SurfaceForm + its MAPS_TO edges in one shot
# ---------------------------------------------------------------------------
_FETCH_ALL = """
MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept)
RETURN sf.normalized    AS normalized,
       sf.form          AS form,
       sf.source        AS source,
       sf.status        AS status,
       c.id             AS concept_id,
       c.fsn            AS concept_fsn,
       c.semantic_tag   AS semantic_tag,
       c.active         AS concept_active,
       m.confidence     AS confidence,
       m.provenance     AS provenance
ORDER BY sf.form
"""

_FETCH_DUPLICATES = """
MATCH (sf:SurfaceForm)-[r:MAPS_TO]->(c:Concept)
WITH sf, count(DISTINCT c) AS n_concepts, count(r) AS n_rels
WHERE n_rels > 1
WITH sf, n_concepts, n_rels
MATCH (sf)-[r:MAPS_TO]->(c:Concept)
RETURN sf.normalized AS normalized,
       sf.form       AS form,
       n_concepts,
       n_rels,
       collect({
           concept_id: c.id, fsn: c.fsn,
           confidence: r.confidence, provenance: r.provenance,
           source: sf.source
       }) AS mappings
ORDER BY n_rels DESC, sf.form
"""

# ---------------------------------------------------------------------------
# Heuristics
# ---------------------------------------------------------------------------
_NEGATIVE_PREFIXES = (
    "no ", "not ", "absent ", "absence ", "negative ",
    "history of ", "h/o ", "hx ", "ex-", "ex ",
    "denied ", "denies ", "never ",
)

_SYMPTOM_KEYWORDS = {
    "pain", "ache", "aching", "swelling", "cough", "fever", "nausea",
    "vomiting", "diarrhoea", "diarrhea", "bleeding", "blood", "fatigue",
    "tired", "weight loss", "breathless", "dyspnoea", "wheeze", "stridor",
    "haemoptysis", "haematemesis", "jaundice", "rash", "itch", "lump",
    "mass", "discharge", "urgency", "frequency", "constipation", "backache",
    "back pain", "headache", "dizziness", "syncope", "palpitation",
    "lymphadenopathy", "clubbing", "thrombocytosis", "anaemia", "anemia",
    "reflux", "dyspepsia", "dysphagia",
}


def _is_negative_phrase(form: str) -> bool:
    low = form.lower().strip()
    return any(low.startswith(p) for p in _NEGATIVE_PREFIXES)


def _looks_like_symptom(form: str) -> bool:
    low = form.lower()
    return any(kw in low for kw in _SYMPTOM_KEYWORDS)


def _audit_row(row: dict) -> list[str]:
    flags: list[str] = []
    form = str(row.get("form") or "").strip()
    stag = str(row.get("semantic_tag") or "").lower()
    source = str(row.get("source") or "").lower()
    active = row.get("concept_active")
    conf = float(row.get("confidence") or 0.0)

    if not row.get("concept_active"):
        flags.append("INACTIVE_CONCEPT")

    if source == "guideline_config_loader":
        flags.append("GUIDELINE_CONFIG_LOADER")

    if stag == "situation" and not _is_negative_phrase(form):
        flags.append("SUSPECT_SITUATION_TAG")
        if _looks_like_symptom(form):
            flags.append("SITUATION_FOR_ACTIVE_FINDING")

    if stag == "procedure" and _looks_like_symptom(form):
        flags.append("PROCEDURE_FOR_SYMPTOM")

    if stag == "morphologic abnormality" and _looks_like_symptom(form):
        flags.append("MORPHOLOGIC_FOR_FINDING")

    if source == "manual" and conf < 1.0:
        flags.append("LOW_CONFIDENCE_MANUAL")

    return flags


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"Connecting to knowledge graph: {kg_uri}")
    driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))

    print("Fetching all surface form mappings ...")
    with driver.session() as s:
        rows = [dict(r) for r in s.run(_FETCH_ALL)]

    print(f"  {len(rows)} SurfaceForm->Concept edges found")

    print("Fetching duplicate surface forms ...")
    with driver.session() as s:
        dups = [dict(r) for r in s.run(_FETCH_DUPLICATES)]

    print(f"  {len(dups)} surface forms with multiple MAPS_TO edges")
    driver.close()

    # Build normalized -> [rows] index for duplicate detection
    by_norm: dict[str, list[dict]] = {}
    for row in rows:
        norm = str(row.get("normalized") or "")
        by_norm.setdefault(norm, []).append(row)

    # Audit each row
    flagged: list[dict] = []
    clean: int = 0
    counts: dict[str, int] = {}

    for row in rows:
        norm = str(row.get("normalized") or "")
        flags = _audit_row(row)
        if len(by_norm[norm]) > 1:
            flags.append("MULTI_MAPPING")
        if flags:
            record = dict(row)
            record["flags"] = flags
            flagged.append(record)
            for f in flags:
                counts[f] = counts.get(f, 0) + 1
        else:
            clean += 1

    # Sort flagged by priority: INACTIVE > SITUATION_FOR_ACTIVE > GUIDELINE
    _priority = {
        "INACTIVE_CONCEPT": 0,
        "SITUATION_FOR_ACTIVE_FINDING": 1,
        "GUIDELINE_CONFIG_LOADER": 2,
        "PROCEDURE_FOR_SYMPTOM": 3,
        "MULTI_MAPPING": 4,
        "SUSPECT_SITUATION_TAG": 5,
        "MORPHOLOGIC_FOR_FINDING": 6,
        "LOW_CONFIDENCE_MANUAL": 7,
    }
    flagged.sort(key=lambda r: min(_priority.get(f, 99) for f in r["flags"]))

    # Print summary
    print()
    print("=" * 70)
    print("SURFACE FORM AUDIT SUMMARY")
    print("=" * 70)
    print(f"  Total edges     : {len(rows)}")
    print(f"  Unique forms    : {len(by_norm)}")
    print(f"  Clean           : {clean}")
    print(f"  Flagged         : {len(flagged)}")
    print()
    print("  Flag counts:")
    for flag, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"    {flag:<40s} {n}")

    print()
    print("=" * 70)
    print("FLAGGED SURFACE FORMS")
    print("=" * 70)

    for r in flagged:
        flags_str = ", ".join(r["flags"])
        cid = r.get("concept_id", "?")
        fsn = r.get("concept_fsn", "?")
        stag = r.get("semantic_tag", "?")
        source = r.get("source", "?")
        conf = r.get("confidence", "?")
        prov = r.get("provenance", "?")
        print(
            f"\n  [{flags_str}]\n"
            f"    form     : {r.get('form')!r}\n"
            f"    concept  : {cid} | {fsn} ({stag})\n"
            f"    source   : {source}  conf={conf}  provenance={prov}"
        )
        if "MULTI_MAPPING" in r["flags"]:
            others = [
                x for x in by_norm[str(r.get("normalized") or "")]
                if x.get("concept_id") != cid
            ]
            if others:
                print(f"    other targets: {[(x['concept_id'], x['concept_fsn']) for x in others]}")

    # Write JSON report
    report = {
        "total_edges": len(rows),
        "unique_forms": len(by_norm),
        "clean": clean,
        "flagged_count": len(flagged),
        "flag_counts": counts,
        "duplicates": dups,
        "flagged": flagged,
    }
    OUTPUT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    print(f"\nFull report: {OUTPUT_PATH}")
    print(f"  ({len(flagged)} flagged, {clean} clean)")


if __name__ == "__main__":
    main()
