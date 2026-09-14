#!/usr/bin/env python3
"""Plan and apply Patient HAS_* and Encounter DOCUMENTS from letter-chunk codes.

Atlas trace:
  DI: DI-58596C1A
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-58596C1A")

Blank assertion is treated as present (legacy persist default). Only present
and historical get a patient shortcut. Dry-run is the default. --apply writes.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_REPO_ROOT / "secrets" / ".env.config", override=True)
load_dotenv(_REPO_ROOT / "secrets" / ".env", override=False)
load_dotenv(_REPO_ROOT / "secrets" / ".env.secrets", override=False)

from libs.cypher.documents_queries import _REL_BY_LABEL, _label_for_tag  # noqa: E402
from libs.neo4j_client.client import PatientGraphClient  # noqa: E402

DEFAULT_REPORT_DIR = _REPO_ROOT / "artifacts" / "chunk_patient_link_backfills"
_SHORTCUT_ASSERTIONS = frozenset({"present", "historical"})
_ALLOWED_SHORTCUTS = frozenset(_REL_BY_LABEL.values())
_BACKFILL_SOURCE = "backfill_chunk_patient_links"

STAMP_ASSERTION = """
MATCH ()-[r:DOCUMENTS]->()
WHERE elementId(r) = $rel_id
  AND (r.assertion IS NULL OR trim(toString(r.assertion)) = '')
SET r.assertion = $assertion,
    r.assertion_backfilled_at = datetime(),
    r.assertion_backfilled_by = $backfill_source
RETURN elementId(r) AS rel_id
"""

WRITE_ENCOUNTER = """
MATCH (enc:Encounter)
WHERE toString(enc.id) = $encounter_id
MATCH ()-[r:DOCUMENTS]->(n)
WHERE elementId(r) = $rel_id
MERGE (enc)-[er:DOCUMENTS {conceptId: n.conceptId}]->(n)
SET er.assertion = coalesce(er.assertion, $assertion, r.assertion),
    er.value = coalesce(er.value, r.value),
    er.unit = coalesce(er.unit, r.unit),
    er.observed_at = coalesce(er.observed_at, r.observed_at),
    er.referenceRange = coalesce(er.referenceRange, r.referenceRange),
    er.evidence = coalesce(er.evidence, r.evidence),
    er.evidence_sentence = coalesce(er.evidence_sentence, r.evidence_sentence),
    er.confidence = coalesce(er.confidence, r.confidence),
    er.context = coalesce(er.context, r.context),
    er.source = coalesce(er.source, r.source),
    er.model_name = coalesce(er.model_name, r.model_name),
    er.model_version = coalesce(er.model_version, r.model_version),
    er.contract_version = coalesce(er.contract_version, r.contract_version),
    er.run_id = coalesce(er.run_id, r.run_id),
    er.semantic_tag = coalesce(er.semantic_tag, r.semantic_tag),
    er.coded_at = coalesce(er.coded_at, datetime()),
    er.backfilled_at = datetime(),
    er.backfilled_by = $backfill_source
RETURN elementId(er) AS encounter_rel_id
"""

LIST_CHUNK_LINKS = """
MATCH (p:Patient)
WHERE toString(p.id) = $patient_id
MATCH (p)<-[:FOR_PATIENT]-(rr:ReferralRequest)
      -[:HAS_DOCUMENT]->(:DocumentReference)-[:HAS_CHUNK]->(c:Chunk)
      -[r:DOCUMENTS]->(n)
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(preferred:Encounter)
WHERE toString(preferred.id) = toString(rr.id) + ':referral-assessment'
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(anyEnc:Encounter)
WITH p, rr, c, r, n, coalesce(preferred, anyEnc) AS enc
OPTIONAL MATCH (enc)-[er:DOCUMENTS]->(n)
OPTIONAL MATCH (p)-[shortcut]->(n)
WHERE type(shortcut) STARTS WITH 'HAS_'
RETURN elementId(r) AS rel_id,
       toString(p.id) AS patient_id,
       toString(n.conceptId) AS concept_id,
       coalesce(n.name, n.term) AS name,
       coalesce(n.semanticTag, r.semantic_tag) AS semantic_tag,
       r.assertion AS assertion,
       toString(rr.id) AS referral_id,
       toString(enc.id) AS encounter_id,
       shortcut IS NOT NULL AS has_shortcut,
       er IS NOT NULL AS has_encounter_doc
UNION
MATCH (p:Patient)
WHERE toString(p.id) = $patient_id
MATCH (p)-[:HAS_DOCUMENT]->(:DocumentReference)-[:HAS_CHUNK]->(c:Chunk)
      -[r:DOCUMENTS]->(n)
OPTIONAL MATCH (p)<-[:FOR_PATIENT]-(rr:ReferralRequest)
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(preferred:Encounter)
WHERE rr IS NOT NULL
  AND toString(preferred.id) = toString(rr.id) + ':referral-assessment'
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(anyEnc:Encounter)
WITH p, rr, c, r, n, coalesce(preferred, anyEnc) AS enc
OPTIONAL MATCH (enc)-[er:DOCUMENTS]->(n)
OPTIONAL MATCH (p)-[shortcut]->(n)
WHERE type(shortcut) STARTS WITH 'HAS_'
RETURN elementId(r) AS rel_id,
       toString(p.id) AS patient_id,
       toString(n.conceptId) AS concept_id,
       coalesce(n.name, n.term) AS name,
       coalesce(n.semanticTag, r.semantic_tag) AS semantic_tag,
       r.assertion AS assertion,
       toString(rr.id) AS referral_id,
       toString(enc.id) AS encounter_id,
       shortcut IS NOT NULL AS has_shortcut,
       er IS NOT NULL AS has_encounter_doc
"""


@dataclass(frozen=True)
class PlannedLink:
    patient_id: str
    concept_id: str
    name: str
    semantic_tag: str
    assertion: str
    shortcut_rel: str
    encounter_id: str
    stamp_assertion: bool
    write_shortcut: bool
    write_encounter: bool
    rel_id: str = ""


def effective_assertion(raw: Any) -> str:
    text = str(raw or "").strip().lower()
    return text or "present"


def _derived_encounter_id(row: dict[str, Any]) -> str:
    existing = str(row.get("encounter_id") or "").strip()
    if existing:
        return existing
    referral_id = str(row.get("referral_id") or "").strip()
    if referral_id:
        return f"{referral_id}:referral-assessment"
    return ""


def _shortcut_rel(semantic_tag: str) -> str:
    return _REL_BY_LABEL[_label_for_tag(semantic_tag)]


def _shortcut_query(rel_type: str) -> str:
    if rel_type not in _ALLOWED_SHORTCUTS:
        raise ValueError(f"Unsupported shortcut rel {rel_type!r}")
    return (
        "MATCH (p:Patient)\n"
        "WHERE toString(p.id) = $patient_id\n"
        "MATCH ()-[r:DOCUMENTS]->(n)\n"
        "WHERE elementId(r) = $rel_id\n"
        "  AND $assertion IN ['present', 'historical']\n"
        f"MERGE (p)-[:{rel_type}]->(n)\n"
        "RETURN $concept_id AS concept_id\n"
    )


def apply_statements(plan: PlannedLink) -> list[tuple[str, dict[str, Any]]]:
    params = {
        "rel_id": plan.rel_id,
        "patient_id": plan.patient_id,
        "concept_id": plan.concept_id,
        "assertion": plan.assertion,
        "encounter_id": plan.encounter_id,
        "backfill_source": _BACKFILL_SOURCE,
    }
    statements: list[tuple[str, dict[str, Any]]] = []
    if plan.stamp_assertion:
        statements.append((STAMP_ASSERTION, params))
    if plan.write_shortcut:
        statements.append((_shortcut_query(plan.shortcut_rel), params))
    if plan.write_encounter:
        statements.append((WRITE_ENCOUNTER, params))
    return statements


def plan_chunk_link(row: dict[str, Any]) -> PlannedLink | None:
    raw_assertion = row.get("assertion")
    assertion = effective_assertion(raw_assertion)
    stamp = not str(raw_assertion or "").strip()
    write_shortcut = assertion in _SHORTCUT_ASSERTIONS and not bool(
        row.get("has_shortcut")
    )
    encounter_id = _derived_encounter_id(row)
    write_encounter = bool(encounter_id) and not bool(row.get("has_encounter_doc"))
    if not (stamp or write_shortcut or write_encounter):
        return None
    return PlannedLink(
        patient_id=str(row.get("patient_id") or ""),
        concept_id=str(row.get("concept_id") or ""),
        name=str(row.get("name") or ""),
        semantic_tag=str(row.get("semantic_tag") or ""),
        assertion=assertion,
        shortcut_rel=_shortcut_rel(str(row.get("semantic_tag") or "")),
        encounter_id=encounter_id,
        stamp_assertion=stamp,
        write_shortcut=write_shortcut,
        write_encounter=write_encounter,
        rel_id=str(row.get("rel_id") or ""),
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patient-id", required=True)
    parser.add_argument("--apply", action="store_true", help="Write the planned links.")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    return parser.parse_args()


def _apply_one(session: Any, plan: PlannedLink) -> None:
    for query, params in apply_statements(plan):
        rows = list(session.run(query, **params))
        if rows:
            continue
        raise RuntimeError(
            f"backfill write returned no rows for {plan.concept_id} "
            f"({plan.name})"
        )


def _apply_plans(
    client: PatientGraphClient, plans: list[PlannedLink]
) -> dict[str, int]:
    with client.session() as session:
        for plan in plans:
            _apply_one(session, plan)
    return _summarise(plans)


def _load_rows(client: PatientGraphClient, patient_id: str) -> list[dict[str, Any]]:
    with client.session() as session:
        return [
            dict(row)
            for row in session.run(LIST_CHUNK_LINKS, patient_id=patient_id)
        ]


def _dedupe_plans(plans: list[PlannedLink]) -> list[PlannedLink]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[PlannedLink] = []
    for plan in plans:
        key = (plan.patient_id, plan.concept_id, plan.rel_id or plan.encounter_id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(plan)
    return unique


def _summarise(plans: list[PlannedLink]) -> dict[str, Any]:
    return {
        "chunk_edges": len(plans),
        "stamp_assertion": sum(1 for plan in plans if plan.stamp_assertion),
        "write_shortcut": sum(1 for plan in plans if plan.write_shortcut),
        "write_encounter": sum(1 for plan in plans if plan.write_encounter),
        "unique_concepts": len({plan.concept_id for plan in plans}),
    }


def _write_report(
    report_dir: Path,
    patient_id: str,
    mode: str,
    rows: list[dict[str, Any]],
    plans: list[PlannedLink],
    written: dict[str, int] | None = None,
) -> Path:
    summary = _summarise(plans)
    payload = {
        "mode": mode,
        "patient_id": patient_id,
        "source_rows": len(rows),
        "summary": summary,
        "written": written or {},
        "plans": [asdict(plan) for plan in plans],
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    report = report_dir / f"{patient_id}-{mode}.json"
    report.write_text(json.dumps(payload, indent=2) + "\n", encoding="ascii")
    return report


def main() -> int:
    args = _parse_args()
    client = PatientGraphClient()
    rows = _load_rows(client, args.patient_id)
    plans = _dedupe_plans(
        [plan for plan in (plan_chunk_link(row) for row in rows) if plan]
    )
    mode = "apply" if args.apply else "dry_run"
    written = _apply_plans(client, plans) if args.apply else None
    report = _write_report(
        args.report_dir, args.patient_id, mode, rows, plans, written
    )
    print(
        json.dumps(
            {
                "report": str(report),
                "mode": mode,
                **_summarise(plans),
                "written": written or {},
                "source_rows": len(rows),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
