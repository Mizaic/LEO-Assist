"""Export non-synthetic verified gold labels for offline few-shot curation."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

EXPORT_DIR = ROOT / "scripts" / "investigations" / "few_shot_review"

_Q_VERIFIED_GOLD = """
MATCH (c:TrainingCandidate)-[:PRODUCED]->(g:GoldLabel)
WHERE toLower(coalesce(c.status, '')) = 'completed'
  AND toLower(coalesce(g.source, '')) <> 'synthetic_llm'
  AND g.entities_json IS NOT NULL
WITH c, g
ORDER BY g.updated_at DESC
LIMIT $limit
RETURN
  g.id AS gold_label_id,
  g.label_id AS label_id,
  c.id AS candidate_id,
  c.candidate_id AS candidate_key,
  g.source AS source,
  g.text AS encounter_text,
  g.entities_json AS entities_json,
  g.quality_score AS quality_score,
  g.updated_at AS updated_at,
  c.lookup_term AS candidate_lookup_term,
  c.semantic_tag AS candidate_semantic_tag,
  c.assertion AS candidate_assertion
"""


def _parse_entities(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [e for e in raw if isinstance(e, dict)]
    if not isinstance(raw, str):
        return []
    text = raw.strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []
    return [e for e in parsed if isinstance(e, dict)] if isinstance(parsed, list) else []


def _coalesce_str(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _normalise_entity(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        "mention_text": _coalesce_str(
            entity, "text", "mention", "span_text", "evidence", "phrase"
        ),
        "lookup_term": _coalesce_str(entity, "lookup_term", "lookupTerm", "term"),
        "code": _coalesce_str(entity, "code", "concept_id", "conceptId"),
        "semantic_tag": _coalesce_str(
            entity, "semantic_tag", "semanticTag", "label"
        ).lower(),
        "assertion": _coalesce_str(entity, "assertion", "status").lower() or "present",
        "value": _coalesce_str(entity, "value"),
        "unit": _coalesce_str(entity, "unit"),
    }


def build_review_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        entities = _parse_entities(record.get("entities_json"))
        if not entities:
            continue
        normalised_entities = [_normalise_entity(entity) for entity in entities]
        rows.append(
            {
                "gold_label_id": str(record.get("gold_label_id") or ""),
                "label_id": str(record.get("label_id") or ""),
                "candidate_id": str(record.get("candidate_key") or ""),
                "source": str(record.get("source") or ""),
                "quality_score": float(record.get("quality_score") or 0.0),
                "encounter_text": str(record.get("encounter_text") or ""),
                "updated_at": str(record.get("updated_at") or ""),
                "candidate_context": {
                    "lookup_term": str(record.get("candidate_lookup_term") or ""),
                    "semantic_tag": str(record.get("candidate_semantic_tag") or ""),
                    "assertion": str(record.get("candidate_assertion") or ""),
                },
                "entities": normalised_entities,
            }
        )
    return rows


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_source: Counter[str] = Counter()
    by_semantic_tag: Counter[str] = Counter()
    by_assertion: Counter[str] = Counter()
    mention_lookup_pairs: Counter[str] = Counter()

    for row in rows:
        by_source[row.get("source", "")] += 1
        for entity in row.get("entities", []):
            mention = str(entity.get("mention_text") or "").strip().lower()
            lookup = str(entity.get("lookup_term") or "").strip().lower()
            semantic_tag = str(entity.get("semantic_tag") or "").strip().lower()
            assertion = str(entity.get("assertion") or "").strip().lower()

            if semantic_tag:
                by_semantic_tag[semantic_tag] += 1
            if assertion:
                by_assertion[assertion] += 1
            if mention or lookup:
                mention_lookup_pairs[f"{mention} -> {lookup}"] += 1

    return {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "row_count": len(rows),
        "entity_count": sum(len(row.get("entities", [])) for row in rows),
        "by_source": dict(by_source.most_common()),
        "top_semantic_tags": dict(by_semantic_tag.most_common(25)),
        "assertion_distribution": dict(by_assertion.most_common()),
        "top_mention_lookup_pairs": dict(mention_lookup_pairs.most_common(50)),
    }


def _query_verified_gold(limit: int) -> list[dict[str, Any]]:
    from libs.neo4j_client.client import KnowledgeGraphClient

    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            return [dict(r) for r in session.run(_Q_VERIFIED_GOLD, limit=limit)]
    finally:
        client.close()


def _load_env() -> None:
    load_dotenv(ROOT / "secrets" / ".env.config", override=False)
    load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)
    load_dotenv(ROOT / "secrets" / ".env", override=False)
    try:
        from libs.keyvault.loader import load_keyvault_secrets

        load_keyvault_secrets()
    except ModuleNotFoundError:
        print("Key Vault dependencies missing; using local environment only.")


def _build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export verified gold rows for offline few-shot review."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=25000,
        help="Maximum rows to fetch from Neo4j.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(EXPORT_DIR),
        help="Directory for output JSON files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview counts only; do not write files.",
    )
    return parser.parse_args()


def main() -> None:
    args = _build_args()
    _load_env()

    raw_rows = _query_verified_gold(limit=args.limit)
    review_rows = build_review_rows(raw_rows)
    summary = build_summary(review_rows)

    print(
        json.dumps(
            {
                "mode": "dry-run" if args.dry_run else "write",
                "raw_rows": len(raw_rows),
                "review_rows": len(review_rows),
                "entity_count": summary["entity_count"],
                "by_source": summary["by_source"],
            },
            indent=2,
        )
    )

    if args.dry_run:
        return

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    export_path = output_dir / f"verified_gold_few_shot_review_{ts}.json"
    summary_path = output_dir / f"verified_gold_few_shot_review_{ts}.summary.json"
    export_path.write_text(json.dumps(review_rows, indent=2), encoding="utf-8")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {"export_path": str(export_path), "summary_path": str(summary_path)},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
