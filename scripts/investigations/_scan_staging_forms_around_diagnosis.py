"""Scan encounter text around confirmed diagnosis anchors for staging forms.

Window:
- 30 days before diagnosis_confirmed anchor
- 90 days after diagnosis_confirmed anchor

Outputs:
- scripts/investigations/output/staging_window_encounters.json
- scripts/investigations/output/staging_surface_form_scan.json
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets
from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient
from services.terminology_api.app.queries.terminology import BATCH_EXACT_QUERY

load_keyvault_secrets()

WINDOW_BEFORE_DAYS = 30
WINDOW_AFTER_DAYS = 90
BATCH_SIZE = 400

OUT_ENCOUNTERS = (
    ROOT / "scripts" / "investigations" / "output" / "staging_window_encounters.json"
)
OUT_SCAN = (
    ROOT / "scripts" / "investigations" / "output" / "staging_surface_form_scan.json"
)
MAPPING_FILE = (
    ROOT / "configs" / "snomed" / "snomed_ncda_stage_of_diagnosis_mapping.json"
)

Q_DIAG_ANCHORS = """
MATCH (ep:EpisodeOfCare)<-[r:IS_PART_OF {milestone_type:'diagnosis_confirmed'}]-(e:Encounter)
WHERE ep.patient_id IS NOT NULL AND e.date IS NOT NULL
WITH ep, min(toString(e.date)) AS diagnosis_date
RETURN
  ep.patient_id AS patient_id,
  ep.episode_id AS episode_id,
  diagnosis_date
ORDER BY diagnosis_date
"""

Q_WINDOW_ENCOUNTERS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id
  AND toString(e.date) >= $start_date
  AND toString(e.date) <= $end_date
  AND e.text IS NOT NULL
  AND trim(e.text) <> ''
RETURN
  toString(e.id) AS encounter_id,
  toString(e.date) AS encounter_date,
  e.text AS text,
  coalesce(e.classification_content_type, '') AS content_type,
  coalesce(e.classification_encounter_purpose, '') AS purpose
ORDER BY encounter_date
"""

Q_STAGE_VALUESET_PARENTS = """
MATCH (v:ValueSet {id: 'ncda-stage-of-diagnosis'})
RETURN v.rawJson AS raw
"""

Q_STAGE_ISA = """
MATCH (ancestor:Concept)<-[:IS_A*1..5]-(d:Concept)
WHERE ancestor.id IN $ids AND d.active = true
RETURN ancestor.id AS parent_id, d.id AS child_id
"""

Q_STAGE_VALUESET_CHECK = """
MATCH (v:ValueSet {id: 'ncda-stage-of-diagnosis'})
RETURN v.id AS id, v.name AS name
"""

STAGE_PATTERNS: list[tuple[str, str]] = [
    (r"\b(?:c|p|y|r)?t[0-4](?:[a-c])?\b", "tnm_t_component"),
    (r"\b(?:c|p|y|r)?n[0-3](?:[a-c])?\b", "tnm_n_component"),
    (r"\b(?:c|p|y|r)?m[0-1](?:[a-c])?\b", "tnm_m_component"),
    (
        r"\b(?:c|p|y|r)?t[0-4](?:[a-c])?\s*(?:n[0-3](?:[a-c])?)\s*(?:m[0-1](?:[a-c])?)\b",
        "tnm_triplet",
    ),
    (r"\btnm(?:\s+stage)?\b", "tnm_system"),
    (r"\bann\s*arbor(?:\s*stage)?\b", "ann_arbor_system"),
    (r"\bbinet(?:\s*stage)?\b", "binet_system"),
    (r"\bchang(?:\s*stage)?\b", "chang_system"),
    (r"\bfigo(?:\s*stage)?\b", "figo_system"),
    (r"\binrg(?:ss)?(?:\s*stage)?\b", "inrg_system"),
    (r"\bmurphy(?:\s*st\.?\s*jude)?(?:\s*stage)?\b", "murphy_st_jude_system"),
    (r"\br-?iss(?:\s*stage)?\b", "riss_system"),
    (r"\broyal\s+marsden(?:\s*stage)?\b", "royal_marsden_system"),
    (r"\bwilms?(?:\s*tumo?u?r)?(?:\s*stage)?\b", "wilms_system"),
    (
        r"\bstage\s*(?:0|i{1,3}|iv|v|vi|vii|viii|ix|x|[1-4][a-c]?|[1-3]s|l1|l2|ms|m)\b",
        "generic_stage_token",
    ),
    (
        r"\b(?:binet|ann\s*arbor|figo|chang|inrg|r-?iss|wilms?|royal\s+marsden|murphy)\s*(?:stage)?\s*(?:a|b|c|i{1,3}|iv|v|[1-4][a-c]?|l1|l2|ms|m)\b",
        "system_stage_pair",
    ),
]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower().strip())


def _chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _extract_forms(text: str) -> list[tuple[str, str]]:
    forms: list[tuple[str, str]] = []
    for pat, label in STAGE_PATTERNS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            phrase = _norm(m.group(0))
            if phrase:
                forms.append((phrase, label))
    return forms


def _load_mapping_terms() -> set[str]:
    data = json.loads(MAPPING_FILE.read_text(encoding="utf-8"))
    terms: set[str] = set()
    for key, info in (data.get("mappings") or {}).items():
        terms.add(_norm(key.replace("_", " ")))
        pt = info.get("preferred_term")
        if pt:
            terms.add(_norm(str(pt)))
        for syn in info.get("guideline_synonyms") or []:
            terms.add(_norm(str(syn)))
    return terms


def _load_stage_concepts(kg: KnowledgeGraphClient) -> set[str]:
    rows = kg.run(Q_STAGE_VALUESET_PARENTS) or []
    if not rows:
        return set()
    raw = rows[0].get("raw") or "{}"
    vs = json.loads(raw) if isinstance(raw, str) else raw
    parents: set[str] = set()
    for include in (vs.get("compose") or {}).get("include") or []:
        for c in include.get("concept") or []:
            code = str(c.get("code") or "").strip()
            if code:
                parents.add(code)
    all_codes = set(parents)
    if parents:
        desc = kg.run(Q_STAGE_ISA, ids=list(parents)) or []
        for r in desc:
            child = str(r.get("child_id") or "").strip()
            if child:
                all_codes.add(child)
    return all_codes


def main() -> None:
    kg = KnowledgeGraphClient()
    pg = PatientGraphClient()
    try:
        if not (kg.run(Q_STAGE_VALUESET_CHECK) or []):
            raise RuntimeError("ncda-stage-of-diagnosis ValueSet not found.")

        anchor_rows = pg.run(Q_DIAG_ANCHORS) or []
        windows: list[dict[str, Any]] = []
        seen = set()
        for r in anchor_rows:
            pid = str(r.get("patient_id") or "")
            eid = str(r.get("episode_id") or "")
            diag = str(r.get("diagnosis_date") or "")[:10]
            if not pid or not eid or not diag:
                continue
            key = (pid, eid, diag)
            if key in seen:
                continue
            seen.add(key)
            d = date.fromisoformat(diag)
            windows.append(
                {
                    "patient_id": pid,
                    "episode_id": eid,
                    "diagnosis_date": diag,
                    "window_start": (
                        d - timedelta(days=WINDOW_BEFORE_DAYS)
                    ).isoformat(),
                    "window_end": (d + timedelta(days=WINDOW_AFTER_DAYS)).isoformat(),
                }
            )

        all_encounters: list[dict[str, Any]] = []
        for i, w in enumerate(windows, 1):
            rows = (
                pg.run(
                    Q_WINDOW_ENCOUNTERS,
                    patient_id=w["patient_id"],
                    start_date=w["window_start"],
                    end_date=w["window_end"],
                )
                or []
            )
            for e in rows:
                all_encounters.append(
                    {
                        **w,
                        "encounter_id": str(e.get("encounter_id") or ""),
                        "encounter_date": str(e.get("encounter_date") or ""),
                        "content_type": str(e.get("content_type") or ""),
                        "purpose": str(e.get("purpose") or ""),
                        "text": str(e.get("text") or ""),
                    }
                )
            if i % 1000 == 0:
                print(f"processed windows {i}/{len(windows)}")

        OUT_ENCOUNTERS.write_text(
            json.dumps(all_encounters, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        mapping_terms = _load_mapping_terms()
        stage_concepts = _load_stage_concepts(kg)

        form_counts: Counter[str] = Counter()
        form_labels: dict[str, set[str]] = defaultdict(set)
        samples: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for enc in all_encounters:
            forms = set(_extract_forms(enc["text"]))
            for phrase, label in forms:
                form_counts[phrase] += 1
                form_labels[phrase].add(label)
                if len(samples[phrase]) < 8:
                    samples[phrase].append(
                        {
                            "patient_id": enc["patient_id"],
                            "episode_id": enc["episode_id"],
                            "diagnosis_date": enc["diagnosis_date"],
                            "encounter_id": enc["encounter_id"],
                            "encounter_date": enc["encounter_date"],
                        }
                    )

        all_forms = sorted(form_counts.keys())
        exact_hits: dict[str, list[dict[str, Any]]] = {}
        for chunk in _chunked(all_forms, BATCH_SIZE):
            rows = kg.run(BATCH_EXACT_QUERY, normalized_terms=chunk) or []
            for r in rows:
                phrase = _norm(str(r.get("input_term") or ""))
                hits = []
                for h in r.get("hits") or []:
                    cid = str(h.get("concept_id") or "")
                    if cid and cid in stage_concepts:
                        hits.append(
                            {
                                "concept_id": cid,
                                "fsn": h.get("fsn"),
                                "semantic_tag": h.get("semantic_tag"),
                                "score": h.get("score"),
                                "surface_form_status": h.get("surface_form_status", ""),
                            }
                        )
                if hits:
                    hits.sort(key=lambda x: float(x.get("score") or 0.0), reverse=True)
                    exact_hits[phrase] = hits

        covered = []
        missed = []
        for phrase, cnt in form_counts.most_common():
            labels = sorted(form_labels[phrase])
            item = {
                "surface_form": phrase,
                "count": int(cnt),
                "pattern_labels": labels,
                "sample_hits": samples[phrase],
                "in_stage_mapping_terms": phrase in mapping_terms,
            }
            if phrase in exact_hits:
                best = exact_hits[phrase][0]
                covered.append(
                    {**item, "best_hit": best, "all_hits": exact_hits[phrase]}
                )
            else:
                missed.append(item)

        out = {
            "summary": {
                "diagnosis_anchor_windows": len(windows),
                "encounters_scanned": len(all_encounters),
                "unique_surface_forms_found": len(form_counts),
                "covered_forms": len(covered),
                "missed_forms": len(missed),
                "window_before_days": WINDOW_BEFORE_DAYS,
                "window_after_days": WINDOW_AFTER_DAYS,
            },
            "covered": covered,
            "missed": missed,
        }
        OUT_SCAN.write_text(
            json.dumps(out, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"Wrote {OUT_ENCOUNTERS}")
        print(f"Wrote {OUT_SCAN}")
        print(out["summary"])
    finally:
        pg.close()
        kg.close()


if __name__ == "__main__":
    main()
