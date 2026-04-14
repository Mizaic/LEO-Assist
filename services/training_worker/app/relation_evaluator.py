"""Evaluate lightweight relation model against dev JSONL."""

from __future__ import annotations

import json
from collections import Counter
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


def _safe_div(num: float, den: float) -> float:
    return num / den if den else 0.0


def evaluate_relation_model(
    model_path: Path,
    dev_path: Path,
    *,
    log_fn=None,
) -> dict[str, Any]:
    """Compute per-type precision/recall/F1 for relation predictions."""
    if not model_path.exists():
        return {
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "per_type": {},
            "passed_gates": False,
            "sample_count": 0,
        }
    model = json.loads(model_path.read_text(encoding="utf-8"))
    pair_priors = dict(model.get("pair_priors") or {})
    dev_rows = _load_jsonl(dev_path)

    tp: Counter[str] = Counter()
    fp: Counter[str] = Counter()
    fn: Counter[str] = Counter()
    sample_count = 0

    for row in dev_rows:
        entities = list(row.get("entities") or [])
        gold = list(row.get("relations") or [])
        gold_by_pair = {
            (int(rel["source_idx"]), int(rel["target_idx"])): str(rel.get("type") or "")
            for rel in gold
            if isinstance(rel, dict)
            and isinstance(rel.get("source_idx"), int)
            and isinstance(rel.get("target_idx"), int)
        }
        pred_by_pair: dict[tuple[int, int], str] = {}
        for (s_idx, t_idx), gold_type in gold_by_pair.items():
            if s_idx >= len(entities) or t_idx >= len(entities):
                continue
            src_label = str(entities[s_idx].get("label") or "").strip().lower()
            tgt_label = str(entities[t_idx].get("label") or "").strip().lower()
            pair_key = f"{src_label}->{tgt_label}"
            priors = pair_priors.get(pair_key) or {}
            if not priors:
                continue
            pred_type = max(priors.items(), key=lambda item: float(item[1]))[0]
            pred_by_pair[(s_idx, t_idx)] = pred_type
            sample_count += 1
            if pred_type == gold_type:
                tp[gold_type] += 1
            else:
                fp[pred_type] += 1
                fn[gold_type] += 1
        for pair, gold_type in gold_by_pair.items():
            if pair not in pred_by_pair:
                fn[gold_type] += 1

    per_type: dict[str, dict[str, float]] = {}
    labels = set(tp.keys()) | set(fp.keys()) | set(fn.keys())
    for label in labels:
        p = _safe_div(tp[label], tp[label] + fp[label])
        r = _safe_div(tp[label], tp[label] + fn[label])
        f1 = _safe_div(2 * p * r, p + r)
        per_type[label] = {
            "precision": round(p, 4),
            "recall": round(r, 4),
            "f1": round(f1, 4),
        }

    total_tp = sum(tp.values())
    total_fp = sum(fp.values())
    total_fn = sum(fn.values())
    precision = _safe_div(total_tp, total_tp + total_fp)
    recall = _safe_div(total_tp, total_tp + total_fn)
    f1 = _safe_div(2 * precision * recall, precision + recall)
    passed = f1 >= 0.6
    if log_fn:
        log_fn(
            f"Relation evaluator: P={precision:.3f} R={recall:.3f} F1={f1:.3f} "
            f"(sampled_pairs={sample_count})"
        )
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "per_type": per_type,
        "passed_gates": passed,
        "sample_count": sample_count,
        "min_f1": 0.6,
    }
