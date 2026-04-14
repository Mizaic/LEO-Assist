"""Train a lightweight supervised relation model from JSONL exports."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def train_relation_model(
    train_path: Path,
    output_path: Path,
    *,
    log_fn=None,
) -> dict[str, Any]:
    """Train label-pair relation priors and write model JSON."""
    rows = _load_jsonl(train_path)
    pair_counts: dict[str, Counter[str]] = defaultdict(Counter)
    type_counts: Counter[str] = Counter()
    sample_count = 0
    for row in rows:
        entities = list(row.get("entities") or [])
        for rel in list(row.get("relations") or []):
            s_idx = rel.get("source_idx")
            t_idx = rel.get("target_idx")
            rel_type = str(rel.get("type") or "").strip().lower()
            if (
                not isinstance(s_idx, int)
                or not isinstance(t_idx, int)
                or s_idx < 0
                or t_idx < 0
                or s_idx >= len(entities)
                or t_idx >= len(entities)
                or not rel_type
            ):
                continue
            src_label = str(entities[s_idx].get("label") or "").strip().lower()
            tgt_label = str(entities[t_idx].get("label") or "").strip().lower()
            pair_key = f"{src_label}->{tgt_label}"
            pair_counts[pair_key][rel_type] += 1
            type_counts[rel_type] += 1
            sample_count += 1

    model = {
        "version": 1,
        "sample_count": sample_count,
        "pair_priors": {
            pair: dict(counter.most_common())
            for pair, counter in pair_counts.items()
        },
        "global_priors": dict(type_counts.most_common()),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(model, indent=2), encoding="utf-8")
    if log_fn:
        log_fn(
            f"Relation trainer: {sample_count} samples, "
            f"{len(pair_counts)} label-pair priors"
        )
    return {
        "sample_count": sample_count,
        "pair_count": len(pair_counts),
        "model_path": str(output_path),
    }
