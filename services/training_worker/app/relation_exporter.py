"""Relation dataset export from GoldLabel entities_json.

Atlas trace:
  DO: DO-236545C8
  DI: DI-2D9F5064
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-236545C8")
"""

from __future__ import annotations

import datetime
import json
import random
from pathlib import Path
from typing import Any

from libs.cypher.gold_label_queries import GET_ALL_GOLD_LABELS_FOR_EXPORT
from libs.neo4j_client.client import KnowledgeGraphClient
from libs.relations.policy import canonicalise_relations, is_relation_allowed


def _norm(label: str | None) -> str:
    return str(label or "").strip().lower().replace(" ", "_")


def _extract_relations(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, entity in enumerate(entities):
        canonical = canonicalise_relations(
            list(entity.get("relations") or entity.get("__relations") or []),
            len(entities),
        )
        for rel in canonical:
            target_idx = int(rel["target_idx"])
            target = entities[target_idx]
            allowed, severity = is_relation_allowed(
                source_label=_norm(entity.get("label") or entity.get("semantic_tag")),
                target_label=_norm(target.get("label") or target.get("semantic_tag")),
                relation_type=str(rel.get("type") or ""),
            )
            if not allowed and severity == "error":
                continue
            rows.append(
                {
                    "source_idx": idx,
                    "target_idx": target_idx,
                    "type": str(rel.get("type") or ""),
                    "confidence": float(rel.get("confidence") or 0.6),
                }
            )
    return rows


def export_relation_dataset(
    output_dir: Path,
    *,
    train_ratio: float = 0.8,
    seed: int = 42,
    log_fn=None,
) -> dict[str, Any]:
    """Export relation train/dev JSONL from GoldLabel records."""
    records: list[dict[str, Any]] = []
    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            rows = session.run(GET_ALL_GOLD_LABELS_FOR_EXPORT)
            for row in rows:
                text = str(row.get("text") or "")
                entities = json.loads(row.get("entities_json") or "[]")
                if not isinstance(entities, list) or not entities:
                    continue
                relations = _extract_relations(entities)
                if not relations:
                    continue
                records.append(
                    {
                        "text": text,
                        "entities": [
                            {
                                "text": str(e.get("text") or ""),
                                "label": _norm(e.get("label") or e.get("semantic_tag")),
                            }
                            for e in entities
                        ],
                        "relations": relations,
                    }
                )
    finally:
        client.close()

    random.seed(seed)
    shuffled = records[:]
    random.shuffle(shuffled)
    split_idx = max(1, int(len(shuffled) * train_ratio)) if shuffled else 0
    train = shuffled[:split_idx]
    dev = shuffled[split_idx:] or (shuffled[:1] if shuffled else [])

    output_dir.mkdir(parents=True, exist_ok=True)
    train_path = output_dir / "relation_train.jsonl"
    dev_path = output_dir / "relation_dev.jsonl"
    train_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=True) for row in train),
        encoding="utf-8",
    )
    dev_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=True) for row in dev),
        encoding="utf-8",
    )
    exported_at = datetime.datetime.now(datetime.UTC).isoformat()
    meta = {
        "exported_at": exported_at,
        "total_records": len(records),
        "train_records": len(train),
        "dev_records": len(dev),
        "seed": seed,
    }
    (output_dir / "relation_export_meta.json").write_text(
        json.dumps(meta, indent=2),
        encoding="utf-8",
    )
    if log_fn:
        log_fn(
            f"Relation export: {len(records)} records "
            f"({len(train)} train / {len(dev)} dev)"
        )
    return {
        "total": len(records),
        "train_count": len(train),
        "dev_count": len(dev),
        "exported_at": exported_at,
        "train_path": str(train_path),
        "dev_path": str(dev_path),
    }
