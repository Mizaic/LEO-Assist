"""Backfill TNM/staging DOCUMENTS edges from encounter text surface forms.

Default mode is dry-run. Use --apply to write to Neo4j.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets
from libs.neo4j_client.client import PatientGraphClient

load_keyvault_secrets()

ENCOUNTERS_FILE = (
    ROOT / "scripts" / "investigations" / "output" / "staging_window_encounters.json"
)
MAPPINGS_FILE = (
    ROOT
    / "scripts"
    / "investigations"
    / "output"
    / "staging_surface_form_upserts_compiled.json"
)

_Q_EXISTS = """
MATCH (e:Encounter)-[r:DOCUMENTS]->(c)
WHERE toString(e.id) = $encounter_id AND toString(c.conceptId) = $concept_id
RETURN count(r) AS n
"""

_Q_UPSERT = """
MATCH (e:Encounter {id: $encounter_id})<-[:HAS_ENCOUNTER]-(p:Patient)
MERGE (s:Observable_entity {conceptId: $concept_id})
SET s.semanticTag  = $semantic_tag,
    s.name         = $name,
    s.readCode     = '',
    s.source       = $source,
    s.updated_at   = datetime(),
    s.created_at   = coalesce(s.created_at, datetime())
MERGE (e)-[r:DOCUMENTS {conceptId: $concept_id}]->(s)
SET r.coded_at          = datetime(),
    r.evidence          = $evidence,
    r.confidence        = $confidence,
    r.domain            = $domain,
    r.context           = $context,
    r.modifiers         = $modifiers,
    r.value             = $numeric_value,
    r.unit              = $unit,
    r.referenceRange    = $reference_range,
    r.source            = $source,
    r.model_name        = $model_name,
    r.model_version     = $model_version,
    r.contract_version  = $contract_version,
    r.run_id            = $run_id,
    r.audit_flag        = $audit_flag,
    r.decision_tier     = $decision_tier,
    r.evidence_sentence = $evidence_sentence,
    r.evidence_start    = $evidence_start,
    r.evidence_end      = $evidence_end,
    r.sentence_index    = $sentence_index,
    r.holdout           = $holdout
MERGE (p)-[:HAS_OBSERVABLE]->(s)
"""


def _compile_patterns(
    mappings: list[dict[str, Any]],
) -> list[tuple[str, str, str, re.Pattern[str]]]:
    rows = sorted(mappings, key=lambda r: len(str(r["surface_form"])), reverse=True)
    out: list[tuple[str, str, str, re.Pattern[str]]] = []
    for row in rows:
        sf = str(row["surface_form"]).strip()
        if not sf:
            continue
        cid = str(row["concept_id"])
        term = str(row.get("term") or "")
        patt = re.compile(
            rf"(?<![A-Za-z0-9]){re.escape(sf)}(?![A-Za-z0-9])", re.IGNORECASE
        )
        out.append((sf, cid, term, patt))
    return out


def _make_params(
    encounter_id: str,
    concept_id: str,
    name: str,
    evidence: str,
    start: int,
    end: int,
    run_id: str,
) -> dict[str, Any]:
    return {
        "encounter_id": encounter_id,
        "concept_id": concept_id,
        "semantic_tag": "Observable_entity",
        "name": name,
        "source": "rule_based_staging_backfill",
        "evidence": evidence,
        "confidence": 0.95,
        "domain": "cancer_audit",
        "context": json.dumps(
            {
                "assertion": "present",
                "negated": False,
                "refuted": False,
                "uncertain": False,
                "historical": False,
                "planned": False,
                "hypothetical": False,
                "family": False,
                "declined": False,
                "cancelled": False,
            }
        ),
        "modifiers": json.dumps({}),
        "numeric_value": None,
        "unit": None,
        "reference_range": None,
        "model_name": "staging_surface_form_backfill",
        "model_version": "1.0",
        "contract_version": "1.0",
        "run_id": run_id,
        "audit_flag": False,
        "decision_tier": "auto",
        "evidence_sentence": evidence,
        "evidence_start": start,
        "evidence_end": end,
        "sentence_index": 0,
        "holdout": False,
    }


def main(apply: bool = False) -> None:
    encounters = json.loads(ENCOUNTERS_FILE.read_text(encoding="utf-8"))
    mappings = json.loads(MAPPINGS_FILE.read_text(encoding="utf-8"))
    patterns = _compile_patterns(mappings)
    run_id = str(uuid.uuid4())
    print(f"run_id={run_id}")
    print(f"apply={apply}")

    candidates: list[dict[str, Any]] = []
    for row in encounters:
        enc_id = str(row.get("encounter_id") or "")
        text = str(row.get("text") or "")
        if not enc_id or not text:
            continue
        for sf, cid, term, patt in patterns:
            for match in patt.finditer(text):
                candidates.append(
                    {
                        "encounter_id": enc_id,
                        "surface_form": sf,
                        "concept_id": cid,
                        "term": term,
                        "evidence": text[
                            max(0, match.start() - 80) : min(
                                len(text), match.end() + 80
                            )
                        ],
                        "start": match.start(),
                        "end": match.end(),
                    }
                )

    dedup: dict[tuple[str, str], dict[str, Any]] = {}
    for c in candidates:
        key = (c["encounter_id"], c["concept_id"])
        dedup.setdefault(key, c)
    rows = list(dedup.values())
    print(f"matched_candidates={len(candidates)}")
    print(f"dedup_rows={len(rows)}")

    client = PatientGraphClient()
    wrote = skipped = 0
    try:
        with client.session() as session:
            for row in rows:
                exists = session.run(
                    _Q_EXISTS,
                    encounter_id=row["encounter_id"],
                    concept_id=row["concept_id"],
                ).single()
                if exists and int(exists["n"] or 0) > 0:
                    skipped += 1
                    continue
                if not apply:
                    wrote += 1
                    continue
                params = _make_params(
                    encounter_id=row["encounter_id"],
                    concept_id=row["concept_id"],
                    name=row["term"],
                    evidence=row["evidence"],
                    start=int(row["start"]),
                    end=int(row["end"]),
                    run_id=run_id,
                )
                session.run(_Q_UPSERT, **params)
                wrote += 1
    finally:
        client.close()

    print(f"to_write={wrote}")
    print(f"already_present={skipped}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write to Neo4j")
    args = parser.parse_args()
    main(apply=args.apply)
