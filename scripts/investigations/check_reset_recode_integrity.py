from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from libs.keyvault.loader import load_keyvault_secrets
from libs.neo4j_client.client import PatientGraphClient


def _load_env() -> None:
    load_dotenv(ROOT / "secrets" / ".env.config", override=False)
    load_dotenv(ROOT / "secrets" / ".env", override=False)
    load_keyvault_secrets()
    os.environ.setdefault("NEO4J_USER", "neo4j")


def _analyze_documents(rows: list[dict]) -> dict:
    missing_sentence = 0
    missing_sentence_index = 0
    missing_offsets = 0
    offset_out_of_bounds = 0
    offset_slice_mismatch = 0
    evidence_not_in_sentence = 0

    for row in rows:
        evidence = (row.get("evidence") or "").strip()
        sentence = (row.get("evidence_sentence") or "").strip()
        start = row.get("evidence_start")
        end = row.get("evidence_end")
        sentence_index = row.get("sentence_index")

        if not sentence:
            missing_sentence += 1
        if sentence_index is None:
            missing_sentence_index += 1
        if start is None or end is None:
            missing_offsets += 1

        if evidence and sentence and evidence.lower() not in sentence.lower():
            evidence_not_in_sentence += 1

        if isinstance(start, int) and isinstance(end, int) and sentence:
            if start < 0 or end < start or end > len(sentence):
                offset_out_of_bounds += 1
            elif evidence and sentence[start:end].lower() != evidence.lower():
                offset_slice_mismatch += 1

    return {
        "documents_count": len(rows),
        "missing_evidence_sentence": missing_sentence,
        "missing_sentence_index": missing_sentence_index,
        "missing_offsets": missing_offsets,
        "offset_out_of_bounds": offset_out_of_bounds,
        "offset_slice_mismatch": offset_slice_mismatch,
        "evidence_not_in_sentence": evidence_not_in_sentence,
    }


def run(patient_id: str) -> dict:
    q_docs = f"""
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(s)
WHERE toString(p.id) = '{patient_id}'
RETURN
  toString(e.id) AS encounter_id,
  toString(s.conceptId) AS concept_id,
  coalesce(toString(r.evidence), '') AS evidence,
  coalesce(toString(r.evidence_sentence), '') AS evidence_sentence,
  r.evidence_start AS evidence_start,
  r.evidence_end AS evidence_end,
  r.sentence_index AS sentence_index
"""
    q_encounters = f"""
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = '{patient_id}'
OPTIONAL MATCH (e)-[r:DOCUMENTS]->()
WITH e, collect(r) AS rels
RETURN
  toString(e.id) AS encounter_id,
  size(rels) AS documents_count,
  reduce(m = 0, x IN rels |
    m + CASE
      WHEN x.evidence_sentence IS NULL OR trim(toString(x.evidence_sentence)) = '' THEN 1
      ELSE 0
    END
  ) AS missing_evidence_sentence
ORDER BY documents_count DESC
"""
    q_stale_shortcuts = f"""
MATCH (p:Patient)-[pr]->(s)
WHERE toString(p.id) = '{patient_id}'
  AND type(pr) IN [
    'HAS_FINDING',
    'HAS_DISORDER',
    'HAS_SITUATION',
    'HAS_OBSERVABLE',
    'HAS_PROCEDURE',
    'HAS_CONCEPT'
  ]
  AND NOT EXISTS {{
    MATCH (p)-[:HAS_ENCOUNTER]->(:Encounter)-[:DOCUMENTS]->(s)
  }}
RETURN type(pr) AS rel_type, count(*) AS count
ORDER BY count DESC
"""
    q_duplicates = f"""
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(s)
WHERE toString(p.id) = '{patient_id}'
WITH
  toString(e.id) AS encounter_id,
  toString(s.conceptId) AS concept_id,
  coalesce(toString(r.evidence), '') AS evidence,
  coalesce(toString(r.evidence_sentence), '') AS evidence_sentence,
  coalesce(r.sentence_index, -1) AS sentence_index,
  count(*) AS copies
WHERE copies > 1
RETURN encounter_id, concept_id, evidence, evidence_sentence, sentence_index, copies
ORDER BY copies DESC
LIMIT 20
"""
    q_with_sentence_samples = f"""
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(s)
WHERE toString(p.id) = '{patient_id}'
  AND r.evidence_sentence IS NOT NULL
  AND trim(toString(r.evidence_sentence)) <> ''
RETURN
  toString(e.id) AS encounter_id,
  toString(s.conceptId) AS concept_id,
  coalesce(toString(r.evidence), '') AS evidence,
  coalesce(toString(r.evidence_sentence), '') AS evidence_sentence,
  r.sentence_index AS sentence_index
LIMIT 10
"""
    q_focus_encounter = f"""
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(s)
WHERE toString(p.id) = '{patient_id}'
  AND toString(e.id) = '70b740e6-7f63-4284-b49b-7c34915573da'
RETURN
  toString(s.conceptId) AS concept_id,
  coalesce(toString(r.evidence), '') AS evidence,
  coalesce(toString(r.evidence_sentence), '') AS evidence_sentence,
  r.sentence_index AS sentence_index
ORDER BY concept_id
"""

    client = PatientGraphClient()
    try:
        doc_rows = client.run(q_docs)
        encounter_rows = client.run(q_encounters)
        stale_shortcuts = client.run(q_stale_shortcuts)
        duplicate_rows = client.run(q_duplicates)
        with_sentence_samples = client.run(q_with_sentence_samples)
        focus_encounter_rows = client.run(q_focus_encounter)
    finally:
        client.close()

    metrics = _analyze_documents(doc_rows)
    return {
        "patient_id": patient_id,
        "encounter_count": len(encounter_rows),
        **metrics,
        "stale_patient_shortcuts": stale_shortcuts,
        "duplicate_documents_groups_top20": duplicate_rows,
        "sentence_mapped_samples": with_sentence_samples,
        "focus_encounter_70b740e6_rows": focus_encounter_rows,
        "top_encounters": encounter_rows[:10],
    }


if __name__ == "__main__":
    _load_env()
    result = run("6310920987")
    print(json.dumps(result, indent=2))
