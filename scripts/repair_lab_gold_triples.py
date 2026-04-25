#!/usr/bin/env python3
"""Dry-run-first repair for deterministic lab triples in GoldLabel data."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_REPO_ROOT / "secrets" / ".env.config")
load_dotenv(_REPO_ROOT / "secrets" / ".env.secrets")

from libs.cypher.gold_label_queries import (  # noqa: E402
    GET_ALL_GOLD_LABELS_FOR_EXPORT,
    UPDATE_GOLD_LABEL_ENTITIES,
)
from libs.neo4j_client.client import KnowledgeGraphClient  # noqa: E402
from libs.ner.lab_triple_recovery import propose_lab_triples  # noqa: E402
from libs.ner.request_reason_recovery import (
    propose_request_reason_entities,
)  # noqa: E402
from libs.terminology.surface_normalize import normalize_surface  # noqa: E402
from libs.training.lab_concept_lookup import lab_lookup_texts  # noqa: E402
from scripts.lib.gold_label_snomed_check import ValidationResult  # noqa: E402
from services.terminology_api.app.queries.terminology import (  # noqa: E402
    BATCH_EXACT_QUERY,
)

_LAB_LABELS = frozenset({"procedure", "observable_entity", "finding"})


@dataclass
class RowPlan:
    label_id: str
    source: str
    candidate_id: str
    text: str
    existing_entities: list[dict[str, Any]]
    generated_entities: list[dict[str, Any]]
    kept_entities: list[dict[str, Any]]
    lookup_pairs: list[tuple[str, str]] = field(default_factory=list)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Persist safe repairs.")
    parser.add_argument("--limit", type=int, default=0, help="Optional row limit.")
    parser.add_argument(
        "--source", default="", help="Optional GoldLabel source filter."
    )
    parser.add_argument(
        "--report-dir",
        default="artifacts/lab_gold_triple_repairs",
        help="Directory for JSON reports.",
    )
    return parser.parse_args()


def _load_rows(
    client: KnowledgeGraphClient, args: argparse.Namespace
) -> list[dict[str, Any]]:
    with client.session() as session:
        rows = [dict(row) for row in session.run(GET_ALL_GOLD_LABELS_FOR_EXPORT)]
    if args.source:
        rows = [row for row in rows if str(row.get("source") or "") == args.source]
    if args.limit > 0:
        rows = rows[: args.limit]
    return rows


def _build_row_plan(row: dict[str, Any]) -> RowPlan | None:
    text = str(row.get("text") or "")
    existing = _parse_entities(row.get("entities_json"))
    generated = [*propose_lab_triples(text), *propose_request_reason_entities(text)]
    if not generated:
        return None
    kept = _preserve_non_lab_entities(existing, generated)
    pairs = [
        (lookup, str(entity.get("label") or ""))
        for entity in generated
        for lookup in _lookup_texts(entity)
    ]
    return RowPlan(
        label_id=str(row.get("label_id") or ""),
        source=str(row.get("source") or ""),
        candidate_id=str(row.get("candidate_id") or ""),
        text=text,
        existing_entities=existing,
        generated_entities=generated,
        kept_entities=kept,
        lookup_pairs=list(dict.fromkeys(pairs)),
    )


def _parse_entities(raw: Any) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(str(raw or "[]"))
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [dict(item) for item in parsed if isinstance(item, dict)]


def _preserve_non_lab_entities(
    existing: list[dict[str, Any]],
    generated: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    regions = [_span(entity) for entity in generated if _span(entity) is not None]
    kept: list[dict[str, Any]] = []
    for entity in existing:
        if not _is_replaceable_entity(entity):
            kept.append(entity)
            continue
        span = _span(entity)
        if span is not None and not any(_overlaps(span, region) for region in regions):
            kept.append(entity)
    return kept


def _is_lab_entity(entity: dict[str, Any]) -> bool:
    label = str(entity.get("label") or entity.get("semantic_tag") or "").lower()
    return label in _LAB_LABELS


def _is_replaceable_entity(entity: dict[str, Any]) -> bool:
    label = str(entity.get("label") or entity.get("semantic_tag") or "").lower()
    return label in _LAB_LABELS or label == "situation"


def _span(entity: dict[str, Any]) -> tuple[int, int] | None:
    try:
        return int(entity.get("start", 0)), int(entity.get("end", 0))
    except (TypeError, ValueError):
        return None


def _overlaps(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] < right[1] and right[0] < left[1]


def _resolve_pairs(
    plans: list[RowPlan],
    client: KnowledgeGraphClient,
) -> dict[tuple[str, str], ValidationResult]:
    pairs: list[tuple[str, str]] = []
    for plan in plans:
        pairs.extend(plan.lookup_pairs)
    unique_pairs = list(dict.fromkeys(pairs))
    return _resolve_pairs_exact(client, unique_pairs)


def _resolve_pairs_exact(
    client: KnowledgeGraphClient,
    pairs: list[tuple[str, str]],
) -> dict[tuple[str, str], ValidationResult]:
    """Resolve lookup pairs using exact Term/SurfaceForm matches only."""

    norm_to_pairs: dict[str, list[tuple[str, str]]] = {}
    for surface, label in pairs:
        norm = normalize_surface(surface)
        if norm:
            norm_to_pairs.setdefault(norm, []).append((surface, label))
    rows = _run_exact_query(client, list(norm_to_pairs))
    hits_by_norm = {
        str(row.get("input_term") or ""): row.get("hits") or [] for row in rows
    }
    return {
        pair: _validation_from_hits(
            pair, hits_by_norm.get(normalize_surface(pair[0]), [])
        )
        for pair in pairs
    }


def _run_exact_query(
    client: KnowledgeGraphClient,
    norms: list[str],
    *,
    chunk_size: int = 500,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with client.session() as session:
        for offset in range(0, len(norms), chunk_size):
            chunk = norms[offset : offset + chunk_size]
            rows.extend(
                dict(row)
                for row in session.run(BATCH_EXACT_QUERY, normalized_terms=chunk)
            )
    return rows


def _validation_from_hits(
    pair: tuple[str, str],
    hits: list[dict[str, Any]],
) -> ValidationResult:
    surface, label = pair
    for hit in hits:
        if _normalise_tag(hit.get("semantic_tag")) != _normalise_tag(label):
            continue
        return ValidationResult(
            accepted=True,
            reason="accepted_exact",
            surface_text=surface,
            proposed_label=label,
            concept_id=str(hit.get("concept_id") or ""),
            snomed_term=_strip_semantic_suffix(str(hit.get("fsn") or "")),
            semantic_tag=_normalise_tag(hit.get("semantic_tag")),
            resolver_score=float(hit.get("score") or 0.0),
            surface_match=1.0,
            candidate_count=len(hits),
            debug={"branch": "exact", "had_exact_match": True},
        )
    reason = "tag_mismatch_all" if hits else "no_candidates"
    return ValidationResult(
        accepted=False,
        reason=reason,
        surface_text=surface,
        proposed_label=label,
        candidate_count=len(hits),
        debug=_rank1_debug(hits),
    )


def _normalise_tag(raw: Any) -> str:
    return str(raw or "").strip().lower().replace(" ", "_").replace("-", "_")


def _strip_semantic_suffix(term: str) -> str:
    return term.rsplit(" (", 1)[0].strip() if term.endswith(")") else term


def _rank1_debug(hits: list[dict[str, Any]]) -> dict[str, Any]:
    if not hits:
        return {}
    top = hits[0]
    return {
        "rank1_concept_id": top.get("concept_id"),
        "rank1_term": _strip_semantic_suffix(str(top.get("fsn") or "")),
        "rank1_semantic_tag": _normalise_tag(top.get("semantic_tag")),
    }


def _finalise_plan(
    plan: RowPlan,
    validations: dict[tuple[str, str], ValidationResult],
) -> dict[str, Any]:
    resolved: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for entity in plan.generated_entities:
        result = _pick_validation(entity, validations)
        if result is None:
            unresolved.append(_unresolved_entry(entity, validations))
            continue
        resolved.append(_attach_concept(entity, result))
    final_entities = sorted([*plan.kept_entities, *resolved], key=_sort_key)
    return _report_item(plan, final_entities, unresolved)


def _pick_validation(
    entity: dict[str, Any],
    validations: dict[tuple[str, str], ValidationResult],
) -> ValidationResult | None:
    if entity.get("snomed_concept_id") and entity.get("snomed_term"):
        return ValidationResult(
            accepted=True,
            reason="accepted_pre_resolved",
            surface_text=str(entity.get("text") or ""),
            proposed_label=str(entity.get("label") or ""),
            concept_id=str(entity.get("snomed_concept_id") or ""),
            snomed_term=str(entity.get("snomed_term") or ""),
            semantic_tag=str(entity.get("semantic_tag") or entity.get("label") or ""),
            resolver_score=1.0,
            surface_match=1.0,
            candidate_count=1,
            debug={"branch": "pre_resolved"},
        )
    label = str(entity.get("label") or "")
    for lookup in _lookup_texts(entity):
        result = validations.get((lookup, label))
        if result is not None and result.accepted:
            return result
    return None


def _unresolved_entry(
    entity: dict[str, Any],
    validations: dict[tuple[str, str], ValidationResult],
) -> dict[str, Any]:
    label = str(entity.get("label") or "")
    attempts = []
    for lookup in _lookup_texts(entity):
        result = validations.get((lookup, label))
        attempts.append(
            result.to_dict() if result is not None else {"surface_text": lookup}
        )
    return {"entity": _clean_entity(entity), "attempts": attempts}


def _lookup_texts(entity: dict[str, Any]) -> list[str]:
    if entity.get("snomed_concept_id") and entity.get("snomed_term"):
        return []
    return lab_lookup_texts(entity)


def _attach_concept(
    entity: dict[str, Any],
    result: ValidationResult,
) -> dict[str, Any]:
    out = _clean_entity(entity)
    out["snomed_concept_id"] = str(result.concept_id or "")
    out["snomed_term"] = str(result.snomed_term or "")
    out["assertion"] = str(out.get("assertion") or "present")
    return out


def _clean_entity(entity: dict[str, Any]) -> dict[str, Any]:
    out = {
        "text": str(entity.get("text") or ""),
        "label": str(entity.get("label") or entity.get("semantic_tag") or ""),
        "semantic_tag": str(entity.get("label") or entity.get("semantic_tag") or ""),
        "start": int(entity.get("start", 0)),
        "end": int(entity.get("end", 0)),
        "assertion": str(entity.get("assertion") or "present"),
    }
    if "relations" in entity:
        out["relations"] = entity.get("relations") or []
    if entity.get("snomed_concept_id"):
        out["snomed_concept_id"] = str(entity.get("snomed_concept_id") or "")
    if entity.get("snomed_term"):
        out["snomed_term"] = str(entity.get("snomed_term") or "")
    return out


def _sort_key(entity: dict[str, Any]) -> tuple[int, int, str]:
    span = _span(entity) or (0, 0)
    return span[0], span[1], str(entity.get("label") or "")


def _report_item(
    plan: RowPlan,
    final_entities: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
) -> dict[str, Any]:
    changed = _entity_signature(plan.existing_entities) != _entity_signature(
        final_entities
    )
    status = "concept_unresolved" if unresolved else "repairable"
    if not changed and not unresolved:
        status = "unchanged"
    return {
        "label_id": plan.label_id,
        "source": plan.source,
        "candidate_id": plan.candidate_id,
        "status": status,
        "changed": changed and not unresolved,
        "existing_lab_count": sum(
            1 for entity in plan.existing_entities if _is_lab_entity(entity)
        ),
        "generated_lab_count": len(plan.generated_entities),
        "kept_non_lab_count": len(plan.kept_entities),
        "unresolved": unresolved,
        "entities": final_entities,
        "text_preview": plan.text[:240],
    }


def _entity_signature(entities: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    return [
        (
            entity.get("text"),
            entity.get("label") or entity.get("semantic_tag"),
            entity.get("start"),
            entity.get("end"),
            entity.get("snomed_concept_id"),
        )
        for entity in sorted(entities, key=_sort_key)
    ]


def _write_repairs(client: KnowledgeGraphClient, items: list[dict[str, Any]]) -> int:
    applied = 0
    with client.session() as session:
        for item in items:
            if item["status"] != "repairable" or not item["changed"]:
                continue
            session.run(
                UPDATE_GOLD_LABEL_ENTITIES,
                label_id=item["label_id"],
                entities_json=json.dumps(item["entities"]),
            )
            applied += 1
    return applied


def _summary(items: list[dict[str, Any]], applied: int) -> dict[str, int]:
    return {
        "labels_with_lab_hits": len(items),
        "repairable": sum(1 for item in items if item["status"] == "repairable"),
        "changed_repairable": sum(
            1 for item in items if item["status"] == "repairable" and item["changed"]
        ),
        "concept_unresolved": sum(
            1 for item in items if item["status"] == "concept_unresolved"
        ),
        "ambiguous": sum(1 for item in items if item["status"] == "ambiguous"),
        "unchanged": sum(1 for item in items if item["status"] == "unchanged"),
        "applied_labels": applied,
    }


def _write_report(report_dir: Path, report: dict[str, Any]) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    mode = "apply" if report["apply"] else "dry_run"
    path = report_dir / f"lab_gold_triple_repair_{mode}_{stamp}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return path


def main() -> int:
    args = _parse_args()

    client = KnowledgeGraphClient()
    try:
        rows = _load_rows(client, args)
        plans = [plan for row in rows if (plan := _build_row_plan(row)) is not None]
        validations = _resolve_pairs(plans, client)
        items = [_finalise_plan(plan, validations) for plan in plans]
        applied = _write_repairs(client, items) if args.apply else 0
    finally:
        client.close()

    report = {
        "apply": bool(args.apply),
        "source": args.source or None,
        "limit": args.limit or None,
        "summary": _summary(items, applied),
        "items": [
            item for item in items if item["status"] != "unchanged" or item["changed"]
        ],
    }
    path = _write_report(Path(args.report_dir), report)
    print(json.dumps({"report": str(path), **report["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
