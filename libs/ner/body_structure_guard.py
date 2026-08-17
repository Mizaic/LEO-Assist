"""Keep named body-part sites; always keep six reproductive organs.

Atlas trace:
  DO: DO-8E641A9E
  DI: DI-6ACD24D2
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-8E641A9E")
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from libs.ner.precision_gates import REPRODUCTIVE_ANATOMY_SNOMED_IDS

logger = logging.getLogger(__name__)

_SEED_PATH = Path(__file__).parent / "resources" / "body_structure_guard.json"
_BODY_LABELS = frozenset({"body_structure", "body structure"})

_always_keep_ids: set[int] = set(REPRODUCTIVE_ANATOMY_SNOMED_IDS)
_keep_as_site_ids: set[int] = set()
_always_keep_re: re.Pattern[str] | None = None
_keep_as_site_re: re.Pattern[str] | None = None
_drop_orphan = True
_loaded = False


def _entity_text(ent: dict[str, Any]) -> str:
    parts = (
        ent.get("text"),
        ent.get("lookup_term"),
        ent.get("term"),
        ent.get("normalized"),
    )
    return " ".join(str(p) for p in parts if p)


def _entity_concept_id(ent: dict[str, Any]) -> int | None:
    raw = ent.get("snomed_concept_id") or ent.get("concept_id")
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _compile_alts(patterns: list[str]) -> re.Pattern[str] | None:
    parts = [p.strip() for p in patterns if p.strip() and not p.strip().isdigit()]
    if not parts:
        return None
    return re.compile(r"\b(?:" + "|".join(f"(?:{p})" for p in parts) + r")\b", re.I)


def _as_int(pattern: str) -> int | None:
    text = pattern.strip()
    if not text.isdigit():
        return None
    return int(text)


def _load_seed_rules() -> list[dict[str, Any]]:
    if not _SEED_PATH.exists():
        return []
    data = json.loads(_SEED_PATH.read_text(encoding="utf-8"))
    return [r for r in data.get("rules", []) if r.get("active", True)]


def _fetch_neo4j_rules() -> list[dict[str, Any]]:
    try:
        from libs.pipeline.config_loader import _fetch_neo4j_rules

        return _fetch_neo4j_rules("body_structure_guard")
    except Exception:
        logger.warning(
            "Could not fetch Neo4j body-structure guard rules -- using seed only",
            exc_info=True,
        )
        return []


def _apply_rule(
    row: dict[str, Any],
    always_ids: set[int],
    site_ids: set[int],
    always_pats: list[str],
    site_pats: list[str],
) -> bool | None:
    if not row.get("active", True):
        return None
    rtype = str(row.get("rule_type") or "").strip()
    pattern = str(row.get("pattern") or "").strip()
    if rtype == "drop_orphan":
        return pattern.lower() not in {"false", "0", "off", "no"}
    cid = _as_int(pattern)
    if rtype == "always_keep":
        if cid is not None:
            always_ids.add(cid)
        elif pattern:
            always_pats.append(pattern)
    elif rtype == "keep_as_site":
        if cid is not None:
            site_ids.add(cid)
        elif pattern:
            site_pats.append(pattern)
    return None


def reload_body_structure_guard() -> None:
    """Rebuild keep rules from seed JSON plus Neo4j custom rows."""
    global _always_keep_ids, _keep_as_site_ids
    global _always_keep_re, _keep_as_site_re, _drop_orphan, _loaded
    always_ids = set(REPRODUCTIVE_ANATOMY_SNOMED_IDS)
    site_ids: set[int] = set()
    always_pats: list[str] = []
    site_pats: list[str] = []
    drop_orphan = True
    for row in _load_seed_rules() + _fetch_neo4j_rules():
        flag = _apply_rule(row, always_ids, site_ids, always_pats, site_pats)
        if flag is not None:
            drop_orphan = flag
    _always_keep_ids = always_ids
    _keep_as_site_ids = site_ids
    _always_keep_re = _compile_alts(always_pats)
    _keep_as_site_re = _compile_alts(site_pats)
    _drop_orphan = drop_orphan
    _loaded = True
    logger.info(
        "Body-structure guard reloaded: %d always-keep ids, %d site ids",
        len(_always_keep_ids),
        len(_keep_as_site_ids),
    )


def _ensure_loaded() -> None:
    if not _loaded:
        reload_body_structure_guard()


def is_always_keep_body_structure(ent: dict[str, Any]) -> bool:
    """True for the six reproductive organs (id or name)."""
    _ensure_loaded()
    cid = _entity_concept_id(ent)
    if cid is not None and cid in _always_keep_ids:
        return True
    text = _entity_text(ent)
    return bool(_always_keep_re and text and _always_keep_re.search(text))


def should_keep_body_structure(ent: dict[str, Any]) -> bool:
    """True when the span is a reproductive organ or a configured site."""
    _ensure_loaded()
    if is_always_keep_body_structure(ent):
        return True
    cid = _entity_concept_id(ent)
    if cid is not None and cid in _keep_as_site_ids:
        return True
    text = _entity_text(ent)
    return bool(_keep_as_site_re and text and _keep_as_site_re.search(text))


def _is_body_structure(ent: dict[str, Any]) -> bool:
    label = str(ent.get("label") or ent.get("semantic_tag") or "")
    return (
        label.lower().replace(" ", "_") in {"body_structure"} or label in _BODY_LABELS
    )


def _linked_site_indices(entities: list[dict[str, Any]]) -> set[int]:
    linked: set[int] = set()
    for ent in entities:
        for rel in ent.get("__relations") or []:
            if not isinstance(rel, dict):
                continue
            if str(rel.get("type") or "").strip().lower() != "finding_site":
                continue
            idx = rel.get("target_idx")
            if isinstance(idx, int):
                linked.add(idx)
    return linked


def suppress_orphan_body_structures(entities: list[dict[str, Any]]) -> None:
    """Mark unlinked keep-as-site spans so persist skips them."""
    _ensure_loaded()
    if not _drop_orphan:
        return
    linked = _linked_site_indices(entities)
    for i, ent in enumerate(entities):
        if not _is_body_structure(ent):
            continue
        if is_always_keep_body_structure(ent):
            continue
        if i not in linked:
            ent["_relation_suppressed"] = True
