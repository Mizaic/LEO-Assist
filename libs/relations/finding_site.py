"""Finding-site tail checks and nearby-site prediction.

Atlas:
  DI: DI-044827AD, DI-6ACD24D2
  DO: DO-49256B13
  Risk: R-1BC83D6A
"""

from __future__ import annotations

import re
from typing import Any

from libs.relations.policy import allowed_relation_types, is_relation_allowed

_NEAR_SITE_CHARS = 80
_STATUS_SITE_RE = re.compile(
    r"\b("
    r"in\s*situ|insitu|"
    r"has\s+womb|"
    r"womb\s+in\s*situ|"
    r"uterus\s+(still\s+)?present|"
    r"no\s+hysterectomy"
    r")\b",
    re.IGNORECASE,
)
_SITE_ALIASES: dict[str, tuple[str, ...]] = {
    "cervix": ("cervix", "cervical"),
    "vagina": ("vagina", "vaginal"),
    "uterus": ("uterus", "uterine", "womb"),
    "ovary": ("ovary", "ovarian", "ovaries"),
    "breast": ("breast",),
    "abdomen": ("abdomen", "abdominal"),
    "arm": ("arm",),
    "liver": ("liver", "hepatic"),
}


def _norm_label(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _norm_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def is_status_site_phrase(text: str) -> bool:
    """True when the span is organ-present or in-situ status, not a site."""
    return bool(_STATUS_SITE_RE.search((text or "").strip()))


def is_usable_finding_site_tail(entity: dict[str, Any]) -> bool:
    """True for a body-structure span that can be a finding site."""
    label = _norm_label(entity.get("label") or entity.get("semantic_tag"))
    if label != "body_structure":
        return False
    return not is_status_site_phrase(str(entity.get("text") or ""))


def site_mentioned_in_finding(
    source: dict[str, Any],
    target: dict[str, Any],
) -> bool:
    """True when the finding phrase names this anatomy site."""
    src = _norm_text(source.get("text"))
    tgt = _norm_text(target.get("text"))
    if not src or not tgt:
        return False
    if tgt in src:
        return True
    return _alias_mentioned(src, tgt)


def _alias_mentioned(src: str, tgt: str) -> bool:
    for aliases in _SITE_ALIASES.values():
        if tgt not in aliases and not any(alias in tgt for alias in aliases):
            continue
        if any(alias in src for alias in aliases):
            return True
    return False


def _near_offsets(source: dict[str, Any], target: dict[str, Any]) -> bool:
    if not isinstance(source.get("start"), int):
        return False
    if not isinstance(target.get("start"), int):
        return False
    return abs(int(source["start"]) - int(target["start"])) <= _NEAR_SITE_CHARS


def finding_site_supported(
    source: dict[str, Any],
    target: dict[str, Any],
) -> bool:
    """True when the tail is usable anatomy in the same phrase or nearby."""
    if not is_usable_finding_site_tail(target):
        return False
    if site_mentioned_in_finding(source, target):
        return True
    return _near_offsets(source, target)


def _entity_label(entity: dict[str, Any]) -> str:
    return str(entity.get("label") or entity.get("semantic_tag") or "")


def pick_relation_type(
    source: dict[str, Any],
    target: dict[str, Any],
    pair_prior: dict[str, Any],
    allowed_types: list[str],
) -> tuple[str | None, float]:
    """Pick a relation type. No-prior pairs need a supported finding site."""
    has_offsets = isinstance(source.get("start"), int) and isinstance(
        target.get("start"), int
    )
    if not pair_prior:
        if "finding_site" not in allowed_types:
            return None, 0.0
        if not finding_site_supported(source, target):
            return None, 0.0
        distance = 0
        if has_offsets:
            distance = abs(int(source["start"]) - int(target["start"]))
        return "finding_site", max(0.62, 0.9 - min(distance, 1200) / 3000.0)

    rel_type = max(allowed_types, key=lambda t: float(pair_prior.get(t) or 0.0))
    total = sum(float(v) for v in pair_prior.values()) or 1.0
    prior = float(pair_prior.get(rel_type) or 0.0) / total
    confidence = max(0.82, min(0.95, 0.55 + prior))
    if has_offsets:
        distance = abs(int(source.get("start") or 0) - int(target.get("start") or 0))
        confidence = max(0.62, 0.9 - min(distance, 1200) / 3000.0)
    return rel_type, confidence


def predict_nearby_finding_sites(
    entities: list[dict[str, Any]],
    pair_priors: dict[str, Any],
) -> list[dict[str, Any]]:
    """Pair entities using priors, else a supported finding_site only."""
    relations: list[dict[str, Any]] = []
    for i, source in enumerate(entities):
        src_label = _entity_label(source)
        relations.extend(
            _predict_source_rows(i, source, src_label, entities, pair_priors)
        )
    return relations


def _predict_source_rows(
    source_idx: int,
    source: dict[str, Any],
    src_label: str,
    entities: list[dict[str, Any]],
    pair_priors: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for j, target in enumerate(entities):
        if source_idx == j:
            continue
        tgt_label = _entity_label(target)
        src_key = str(src_label).strip().lower()
        tgt_key = str(tgt_label).strip().lower()
        pair_key = f"{src_key}->{tgt_key}"
        pair_prior = dict(pair_priors.get(pair_key) or {})
        allowed_types = [
            rt
            for rt in allowed_relation_types()
            if is_relation_allowed(
                source_label=src_label, target_label=tgt_label, relation_type=rt
            )[0]
        ]
        if not allowed_types:
            continue
        rel_type, conf = pick_relation_type(source, target, pair_prior, allowed_types)
        if rel_type is None:
            continue
        rows.append(
            {
                "head_idx": source_idx,
                "tail_idx": j,
                "type": rel_type,
                "confidence": round(conf, 4),
            }
        )
    return rows
