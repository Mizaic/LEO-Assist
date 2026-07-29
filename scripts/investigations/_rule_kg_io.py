"""Neo4j read/write helpers for the source_row_text backfill scripts.

Shared by the Stage 1 (deterministic) and Stage 2 (LLM-assisted) apply
scripts. Every write:

  1. is preceded by a JSON backup of the rule's current logicJson,
  2. is verified with `diff_ignoring_source_row_text` so the ONLY change
     ever written is the addition of `source_row_text` fields -- no
     clinical logic (kind/criterion/operator/value/children) can drift,
  3. is recorded as a GuidanceAuditEvent, same pattern as
     services/api/app/routers/guidance_rules.py::_UPDATE_RULE_STATUS,
  4. never touches rule.status, rule.reviewedAt, rule.reviewedBy, or
     rule.updatedAt -- this is inert UI provenance metadata, not a
     clinical review decision.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from neo4j import Driver, GraphDatabase

FETCH_RULES = """
MATCH (rule:AppropriatenessRule)
WHERE rule.status IN ['pending_review', 'active']
  AND coalesce(rule.schemaVersion, 1) = 2
  AND ($guideline_id IS NULL OR EXISTS {
        MATCH (g:Guideline {id: $guideline_id})
          -[:HAS_RECOMMENDATION]->()-[:HAS_RULE]->(rule)
      })
OPTIONAL MATCH (rule)<-[:HAS_RULE]-(rec:Recommendation)
  <-[:HAS_RECOMMENDATION]-(g:Guideline)
WITH rule, rec, g ORDER BY coalesce(rec.versionId, '') DESC
WITH rule, head(collect(rec)) AS rec, head(collect(g)) AS g
RETURN rule.id AS rule_id,
       rule.name AS name,
       rule.status AS status,
       rule.logicJson AS logic_json,
       coalesce(g.id, rule.guidelineId, 'UNKNOWN') AS guideline_id,
       rec.verbatim AS recommendation_text
"""

_WRITE_LOGIC_JSON = """
MATCH (rule:AppropriatenessRule {id: $rule_id})
SET rule.logicJson = $logic_json
MERGE (audit:GuidanceAuditEvent {id: $event_id})
ON CREATE SET
    audit.ruleId    = $rule_id,
    audit.action    = $action,
    audit.reviewer  = $actor,
    audit.reason    = $reason,
    audit.timestamp = datetime(),
    audit.immutable = true
MERGE (rule)-[:HAS_AUDIT_EVENT]->(audit)
RETURN rule.id AS id
"""


def connect() -> Driver:
    kg_uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
    kg_user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
    kg_pass = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")
    return GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))


def fetch_rule_rows(driver: Driver, guideline_id: str | None = None) -> list[dict[str, Any]]:
    with driver.session() as session:
        return session.run(FETCH_RULES, guideline_id=guideline_id).data()


def backup_rules(rows: list[dict[str, Any]], out_dir: Path) -> Path:
    """Dump {rule_id: logic_json} for every fetched rule, timestamped, for
    rollback. Always call this before the first write in a run."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"backup_{stamp}.json"
    snapshot = {r["rule_id"]: r["logic_json"] for r in rows if r.get("logic_json")}
    out_path.write_text(json.dumps(snapshot, indent=2))
    return out_path


def diff_ignoring_source_row_text(a: Any, b: Any, path: str = "$") -> list[str]:
    """Every path where `a` (before) and `b` (after) differ, ignoring
    `source_row_text` additions/changes. Non-empty result => unsafe write."""
    diffs: list[str] = []
    if isinstance(a, dict) and isinstance(b, dict):
        for key in set(a) | set(b):
            if key == "source_row_text":
                continue
            if key not in a:
                diffs.append(f"{path}.{key}: key added ({b[key]!r})")
            elif key not in b:
                diffs.append(f"{path}.{key}: key removed (was {a[key]!r})")
            else:
                diffs.extend(diff_ignoring_source_row_text(a[key], b[key], f"{path}.{key}"))
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            diffs.append(f"{path}: list length {len(a)} -> {len(b)}")
        else:
            for i, (av, bv) in enumerate(zip(a, b)):
                diffs.extend(diff_ignoring_source_row_text(av, bv, f"{path}[{i}]"))
    elif a != b:
        diffs.append(f"{path}: {a!r} -> {b!r}")
    return diffs


def write_logic_json(
    driver: Driver,
    rule_id: str,
    new_tree: dict[str, Any],
    *,
    action: str,
    actor: str,
    reason: str,
) -> None:
    with driver.session() as session:
        session.run(
            _WRITE_LOGIC_JSON,
            rule_id=rule_id,
            logic_json=json.dumps(new_tree),
            event_id=str(uuid.uuid4()),
            action=action,
            actor=actor,
            reason=reason,
        )
