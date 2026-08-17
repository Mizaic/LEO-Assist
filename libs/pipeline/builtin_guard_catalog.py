"""Read-only catalog of built-in NER guard rules.

Atlas trace:
  DI: Pipeline Guards list built-in rules as read-only
  DO: this module + workbench list merge + Knowledge UI badge

Built-ins live in JSON seed files and Python constants. This catalog
exposes them in the same shape as :NerGuardRule list rows so the
Pipeline Guards page can show what already runs. Rows are read-only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_SEED_DIR = Path(__file__).parent.parent / "ner" / "resources"

_FAMILIES = (
    "scope_guard",
    "lab_value_guard",
    "referral_routing_guard",
    "assertion_guard",
    "entity_type_norm",
    "checkbox_norm",
    "situation_lookup",
    "term_concept_blocklist",
    "body_structure_guard",
    "fact_link_guard",
)


def _row(
    rule_id: str,
    family: str,
    rule_type: str,
    pattern: str,
    summary: str = "",
) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "family": family,
        "rule_type": rule_type,
        "pattern": pattern,
        "summary": summary,
        "active": True,
        "org_id": None,
        "plan_definition_id": None,
        "priority": 10,
        "created_by": "system",
        "created_at": "",
        "source": "builtin",
        "readonly": True,
    }


def _alts_to_rows(
    family: str,
    rule_type: str,
    prefix: str,
    parts: tuple[str, ...] | str,
    *,
    split_pipe: bool = False,
) -> list[dict[str, Any]]:
    joined = parts if isinstance(parts, str) else "".join(parts)
    chunks = joined.split("|") if split_pipe else [joined]
    if not split_pipe and isinstance(parts, tuple):
        chunks = [p.lstrip("|").rstrip("|") for p in parts]
    rows: list[dict[str, Any]] = []
    for i, raw in enumerate(chunks, 1):
        pattern = raw.strip().lstrip("|").rstrip("|")
        if not pattern:
            continue
        rows.append(_row(f"{prefix}-{i:03d}", family, rule_type, pattern))
    return rows


def _set_to_rows(
    family: str,
    rule_type: str,
    prefix: str,
    values: set[str] | frozenset[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i, value in enumerate(sorted(values), 1):
        text = str(value).strip()
        if not text:
            continue
        rows.append(_row(f"{prefix}-{i:03d}", family, rule_type, text))
    return rows


def _json_seed_rows(
    filename: str, family: str, rule_type: str, pattern_key: str
) -> list[dict[str, Any]]:
    path = _SEED_DIR / filename
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for item in data.get("rules", []):
        if not item.get("active", True):
            continue
        pattern = str(item.get(pattern_key) or item.get("pattern") or "")
        rule_id = str(item.get("rule_id") or "")
        if not rule_id or not pattern:
            continue
        summary = str(item.get("comment") or item.get("canonical") or "")
        item_type = str(item.get("rule_type") or rule_type)
        rows.append(_row(rule_id, family, item_type, pattern, summary=summary))
    return rows


def _scope_rows() -> list[dict[str, Any]]:
    from libs.ner.scope_guard import _BUILTIN_SAFETY_NETTING_ALTS, _RECOMMENDATION_RE

    rows = _alts_to_rows(
        "scope_guard",
        "safety_netting",
        "builtin-scope-sn",
        _BUILTIN_SAFETY_NETTING_ALTS,
    )
    rows.append(
        _row(
            "builtin-scope-rec-001",
            "scope_guard",
            "recommendation",
            _RECOMMENDATION_RE.pattern,
        )
    )
    return rows


def _lab_rows() -> list[dict[str, Any]]:
    from libs.ner.lab_value_guard import _BUILTIN_LAB_PATTERNS

    return _alts_to_rows(
        "lab_value_guard",
        "lab_pattern",
        "builtin-lab",
        _BUILTIN_LAB_PATTERNS,
        split_pipe=True,
    )


def _routing_rows() -> list[dict[str, Any]]:
    from libs.ner.referral_routing_guard import (
        _BUILTIN_NAMED_TEST_ALTS,
        _KEEP_ACTION_RE,
        _SITE,
    )

    rows = _alts_to_rows(
        "referral_routing_guard",
        "named_test",
        "builtin-route-test",
        _BUILTIN_NAMED_TEST_ALTS,
        split_pipe=True,
    )
    site_inner = _SITE.strip()
    if site_inner.startswith("(?:") and site_inner.endswith(")"):
        site_inner = site_inner[3:-1]
    rows.extend(
        _alts_to_rows(
            "referral_routing_guard",
            "site",
            "builtin-route-site",
            site_inner,
            split_pipe=True,
        )
    )
    rows.append(
        _row(
            "builtin-route-keep-001",
            "referral_routing_guard",
            "keep_action",
            _KEEP_ACTION_RE.pattern,
        )
    )
    return rows


def _assertion_rows() -> list[dict[str, Any]]:
    from libs.pipeline.post_processing import _BUILTIN_LIFESTYLE_CONCEPT_IDS

    labels = {
        "8517006": "Ex-smoker",
        "266919005": "Never smoked tobacco",
        "8392000": "Non-smoker",
    }
    rows: list[dict[str, Any]] = []
    for i, cid in enumerate(sorted(_BUILTIN_LIFESTYLE_CONCEPT_IDS), 1):
        rows.append(
            _row(
                f"builtin-assert-{i:03d}",
                "assertion_guard",
                "lifestyle_concept",
                cid,
                summary=labels.get(cid, cid),
            )
        )
    return rows


def _entity_norm_rows() -> list[dict[str, Any]]:
    from libs.pipeline.post_processing import (
        _BUILTIN_EPISODE_MARKER_TEXTS,
        _SEVERITY_MODIFIER_TEXTS,
    )

    rows = _set_to_rows(
        "entity_type_norm",
        "episode_marker",
        "builtin-episode",
        _BUILTIN_EPISODE_MARKER_TEXTS,
    )
    rows.extend(
        _set_to_rows(
            "entity_type_norm",
            "severity_modifier",
            "builtin-severity",
            _SEVERITY_MODIFIER_TEXTS,
        )
    )
    return rows


def _checkbox_rows() -> list[dict[str, Any]]:
    from libs.ner.form_checkbox_normalizer import _BUILTIN_ADMIN_QUESTION_ALTS

    return _alts_to_rows(
        "checkbox_norm",
        "admin_question",
        "builtin-checkbox",
        _BUILTIN_ADMIN_QUESTION_ALTS,
    )


def list_builtin_guard_rules(family: str | None = None) -> list[dict[str, Any]]:
    """Return built-in guard rows, optionally filtered by family."""
    builders = {
        "situation_lookup": lambda: _json_seed_rows(
            "situation_lookup.json",
            "situation_lookup",
            "situation_lookup",
            "pattern",
        ),
        "term_concept_blocklist": lambda: _json_seed_rows(
            "term_concept_blocklist.json",
            "term_concept_blocklist",
            "term_concept_blocklist",
            "surface_form",
        ),
        "scope_guard": _scope_rows,
        "lab_value_guard": _lab_rows,
        "referral_routing_guard": _routing_rows,
        "assertion_guard": _assertion_rows,
        "entity_type_norm": _entity_norm_rows,
        "checkbox_norm": _checkbox_rows,
        "body_structure_guard": lambda: _json_seed_rows(
            "body_structure_guard.json",
            "body_structure_guard",
            "keep_as_site",
            "pattern",
        ),
        "fact_link_guard": lambda: _json_seed_rows(
            "fact_link_guard.json",
            "fact_link_guard",
            "allowed_relation",
            "pattern",
        ),
    }
    wanted = [family] if family else list(_FAMILIES)
    rows: list[dict[str, Any]] = []
    for key in wanted:
        builder = builders.get(key)
        if builder is None:
            continue
        rows.extend(builder())
    return rows


def builtin_rule_ids() -> frozenset[str]:
    """Stable set of built-in rule_id values for mutation guards."""
    return frozenset(r["rule_id"] for r in list_builtin_guard_rules())


def is_builtin_rule_id(rule_id: str) -> bool:
    """True when rule_id belongs to a shipped built-in rule."""
    if not rule_id:
        return False
    return rule_id in builtin_rule_ids()


def merge_listed_rules(
    custom: list[dict[str, Any]],
    family: str | None = None,
) -> list[dict[str, Any]]:
    """Custom Neo4j rules first, then built-ins that are not overridden."""
    custom_ids = {row.get("rule_id") for row in custom}
    tagged_custom: list[dict[str, Any]] = []
    for row in custom:
        tagged_custom.append(
            {**row, "source": row.get("source") or "custom", "readonly": False}
        )
    builtins = [
        row
        for row in list_builtin_guard_rules(family)
        if row["rule_id"] not in custom_ids
    ]
    return tagged_custom + builtins
