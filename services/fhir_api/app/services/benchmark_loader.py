"""Benchmark loader: JSON flattening and mapping engine.

Used by the upload wizard endpoint to transform arbitrary benchmark JSON
into flat BenchmarkValue records. Supports built-in templates (e.g. NCDA).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


def infer_structure(raw_json: Dict[str, Any]) -> Dict[str, Any]:
    """Detect keys, nesting, and types for wizard step 2.

    Returns a simplified structure summary for UI display.
    """
    result: Dict[str, Any] = {"keys": [], "sample": {}, "depth": 0}

    def walk(obj: Any, path: str = "", depth: int = 0) -> None:
        if depth > 5:
            return
        result["depth"] = max(result["depth"], depth)
        if isinstance(obj, dict):
            for k, v in obj.items():
                if path:
                    full = f"{path}.{k}"
                else:
                    full = k
                result["keys"].append(full)
                if depth < 2 and len(result.get("sample", {})) < 10:
                    if isinstance(v, (dict, list)):
                        result.setdefault("sample", {})[k] = type(v).__name__
                    else:
                        result.setdefault("sample", {})[k] = v
                walk(v, full, depth + 1)
        elif isinstance(obj, list):
            for i, item in enumerate(obj[:3]) if obj else []:
                walk(item, f"{path}[{i}]", depth + 1)

    walk(raw_json)
    return result


def _build_entity_map(entities: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    """Map entity id -> {scope_type, scope_name, scope_id, ods_code}.

    For gp_practice entities the canonical scope_id is the ODS code when
    present; otherwise the entity id is used.  This ensures benchmark values
    can be matched against live Organization nodes (which are keyed by ODS).
    """
    result: Dict[str, Dict[str, str]] = {}
    for e in entities:
        eid = e.get("id")
        if not eid:
            continue
        scope_type = e.get("type", "unknown")
        ods_code = e.get("ods_code") or ""
        # Use ODS as canonical scope_id for practices; keep entity id otherwise
        if scope_type == "gp_practice" and ods_code:
            canonical_scope_id = ods_code
        else:
            canonical_scope_id = eid
        result[eid] = {
            "scope_type": scope_type,
            "scope_name": e.get("name", eid),
            "scope_id": canonical_scope_id,
            "ods_code": ods_code,
        }
    return result


def _is_composite_sex(value: Any) -> bool:
    """Detect male/female dict that should be stored as single composite benchmark."""
    if not isinstance(value, dict) or len(value) != 2:
        return False
    keys = set(value.keys())
    if keys != {"male", "female"}:
        return False
    return all(
        v is not None and isinstance(v, (int, float)) and not isinstance(v, bool)
        for v in value.values()
    )


def _flatten_simple_value(
    entity_id: str,
    value: Any,
    category: str,
    metric_id: str,
    label: str,
    unit: str,
    entity_map: Dict[str, Dict[str, str]],
    audit_id: str,
    source: str,
) -> List[Dict[str, Any]]:
    """Flatten a single entity's value which may be scalar or dict."""
    scope = entity_map.get(entity_id)
    if scope is None:
        return []
    # Use canonical scope_id (ODS for practices; entity id for all others)
    canonical_id = scope.get("scope_id", entity_id)
    base: Dict[str, Any] = {
        "audit_id": audit_id,
        "scope_id": canonical_id,
        "scope_type": scope["scope_type"],
        "scope_name": scope["scope_name"],
        "unit": unit,
        "category": category,
        "source": source,
    }
    if isinstance(value, dict) and _is_composite_sex(value):
        return [
            {
                **base,
                "metric_id": metric_id,
                "label": label,
                "value": None,
                "value_json": value,
            }
        ]
    if isinstance(value, dict):
        return [
            {
                **base,
                "metric_id": f"{metric_id}.{sub_key}",
                "label": f"{label} ({sub_key})",
                "value": sub_val,
            }
            for sub_key, sub_val in value.items()
            if sub_val is not None and not isinstance(sub_val, dict)
        ]
    return [{**base, "metric_id": metric_id, "label": label, "value": value}]


def _flatten_by_cancer_type(
    category: str,
    by_cancer: Dict[str, Any],
    entity_map: Dict[str, Dict[str, str]],
    audit_id: str,
    source: str,
) -> List[Dict[str, Any]]:
    """Flatten a by_cancer_type block into dotted metric_id records.

    Structure: { cancer_type: { metric_key: { values: { entity_id: val } } } }
    Produces metric_ids like: investigations.by_cancer_type.breast.blood_test_pct

    The *category* stored is kept as the parent section (e.g. "investigations") so
    that _fetch_benchmark_metrics(set_id, "investigations") returns both the
    top-level metrics and the per-cancer-type breakdown in a single query.
    """
    nodes: List[Dict[str, Any]] = []
    for cancer_type, metrics in by_cancer.items():
        if not isinstance(metrics, dict):
            continue
        for metric_key, metric in metrics.items():
            if not isinstance(metric, dict) or "values" not in metric:
                continue
            metric_id = f"{category}.by_cancer_type.{cancer_type}.{metric_key}"
            label = metric.get("label", f"{cancer_type} {metric_key}")
            unit = metric.get("unit", "%")
            for entity_id, value in metric["values"].items():
                nodes.extend(
                    _flatten_simple_value(
                        entity_id,
                        value,
                        category,  # store under parent category so audit API finds it
                        metric_id,
                        label,
                        unit,
                        entity_map,
                        audit_id,
                        source,
                    )
                )
    return nodes


def _flatten_simple_section(
    category: str,
    section: Dict[str, Any],
    entity_map: Dict[str, Dict[str, str]],
    audit_id: str,
    source: str,
) -> List[Dict[str, Any]]:
    """Flatten a section with {metric_key: {label, unit, values}} structure.

    Also handles a nested ``by_cancer_type`` sub-object (e.g. under
    ``investigations``) where each cancer type contains per-metric objects.
    """
    nodes: List[Dict[str, Any]] = []
    for metric_key, metric in section.items():
        if not isinstance(metric, dict):
            continue
        if metric_key == "by_cancer_type":
            nodes.extend(
                _flatten_by_cancer_type(category, metric, entity_map, audit_id, source)
            )
            continue
        if "values" not in metric:
            continue
        metric_id = f"{category}.{metric_key}"
        label = metric.get("label", metric_key)
        unit = metric.get("unit", "")
        for entity_id, value in metric["values"].items():
            nodes.extend(
                _flatten_simple_value(
                    entity_id,
                    value,
                    category,
                    metric_id,
                    label,
                    unit,
                    entity_map,
                    audit_id,
                    source,
                )
            )
    return nodes


def _flatten_condition_type_section(
    section: Dict[str, Any],
    entity_map: Dict[str, Dict[str, str]],
    audit_id: str,
    source: str,
) -> List[Dict[str, Any]]:
    """Flatten the condition_type section with its array structure."""
    nodes: List[Dict[str, Any]] = []
    unit = section.get("unit", "pct")
    for cancer in section.get("cancer_types", []):
        cancer_name = cancer.get("type", "")
        metric_id = f"condition_type.{cancer_name}"
        label = f"{cancer_name.capitalize()} cancer"
        for entity_id, value in cancer.get("values", {}).items():
            if isinstance(value, dict):
                sub_val = value.get("pct")
                if sub_val is not None:
                    nodes.extend(
                        _flatten_simple_value(
                            entity_id,
                            sub_val,
                            "condition_type",
                            metric_id,
                            label,
                            unit,
                            entity_map,
                            audit_id,
                            source,
                        )
                    )
            else:
                nodes.extend(
                    _flatten_simple_value(
                        entity_id,
                        value,
                        "condition_type",
                        metric_id,
                        label,
                        unit,
                        entity_map,
                        audit_id,
                        source,
                    )
                )
    return nodes


def _flatten_ncda(
    data: Dict[str, Any], audit_id: str, source: str
) -> List[Dict[str, Any]]:
    """Flatten NCDA-style JSON into BenchmarkValue records."""
    entity_map = _build_entity_map(data.get("entities", []))
    benchmarks = data.get("benchmarks", {})
    nodes: List[Dict[str, Any]] = []

    for category, section in benchmarks.items():
        if not isinstance(section, dict):
            continue
        if category == "condition_type":
            nodes.extend(
                _flatten_condition_type_section(section, entity_map, audit_id, source)
            )
        else:
            nodes.extend(
                _flatten_simple_section(category, section, entity_map, audit_id, source)
            )
    return nodes


def apply_mapping_template(
    raw_json: Dict[str, Any], template_id: str
) -> Optional[List[Dict[str, Any]]]:
    """Apply a built-in mapping template. Returns flat BenchmarkValue records or None."""
    if template_id == "ncda":
        audit = raw_json.get("audit", {})
        year = audit.get("year", "unknown")
        audit_id = f"ncda-{year}"
        source = audit.get("name", f"NCDA {year}")
        return _flatten_ncda(raw_json, audit_id, source)
    return None


def flatten_benchmarks(
    raw_json: Dict[str, Any],
    mapping: Optional[Dict[str, Any]] = None,
    template_id: Optional[str] = None,
    audit_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Walk JSON using mapping or template and produce flat BenchmarkValue records.

    Args:
        raw_json: Source JSON
        mapping: Custom mapping (future: path-based). If None, uses template_id.
        template_id: Built-in template name (e.g. "ncda")
        audit_id: Override audit_id for template output

    Returns:
        List of {audit_id, metric_id, scope_type, scope_id, scope_name, value, unit, label, category, source}
    """
    if template_id:
        nodes = apply_mapping_template(raw_json, template_id)
        if nodes and audit_id:
            for n in nodes:
                n["audit_id"] = audit_id
        return nodes or []

    if mapping:
        # Future: custom path-based mapping
        raise NotImplementedError("Custom mapping not yet implemented")

    return []
