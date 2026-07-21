"""Verbalise Validation Lab PMH picks using surface forms / synonyms.

Priority per concept (seeded random):
1. Active SurfaceForm aliases
2. Non-FSN Term synonyms
3. Preferred term with semantic tag stripped
"""

from __future__ import annotations

import random
from typing import Any

from libs.cypher.pmh_verbalisation_queries import (
    FSN_TYPE_ID,
    LIST_PREFERRED_TERMS_FOR_CONCEPTS,
    LIST_SURFACE_FORMS_FOR_CONCEPTS,
    LIST_TERM_SYNONYMS_FOR_CONCEPTS,
)
from libs.terminology.preferred_terms import to_preferred_term
from libs.validation_lab.models import PmhItem

_PMH_NARRATIVE_LABEL: dict[str, str] = {
    "condition": "Past medical history",
    "medication": "Current medications",
    "allergy": "Allergies",
}


def _forms_by_concept(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for row in rows or []:
        cid = str(row.get("concept_id") or "").strip()
        if not cid:
            continue
        forms = [
            str(item).strip()
            for item in (row.get("forms") or [])
            if str(item or "").strip()
        ]
        if forms:
            out[cid] = sorted(set(forms))
    return out


def load_verbalisation_pools(
    client: Any,
    concept_ids: list[str],
) -> dict[str, dict[str, list[str] | str]]:
    """Load surface forms, synonyms, and preferred terms for concept ids."""
    ids = sorted({str(cid).strip() for cid in concept_ids if str(cid).strip()})
    if not ids:
        return {}
    surface = _forms_by_concept(
        list(client.run(LIST_SURFACE_FORMS_FOR_CONCEPTS, concept_ids=ids) or [])
    )
    synonyms = _forms_by_concept(
        list(
            client.run(
                LIST_TERM_SYNONYMS_FOR_CONCEPTS,
                concept_ids=ids,
                fsn_type_id=FSN_TYPE_ID,
            )
            or []
        )
    )
    preferred_rows = list(
        client.run(LIST_PREFERRED_TERMS_FOR_CONCEPTS, concept_ids=ids) or []
    )
    preferred: dict[str, str] = {}
    for row in preferred_rows:
        cid = str(row.get("concept_id") or "").strip()
        term = to_preferred_term(str(row.get("term") or ""))
        if cid and term:
            preferred[cid] = term
    pools: dict[str, dict[str, list[str] | str]] = {}
    for cid in ids:
        pools[cid] = {
            "surface_forms": surface.get(cid) or [],
            "synonyms": synonyms.get(cid) or [],
            "preferred_term": preferred.get(cid) or "",
        }
    return pools


def pick_verbalised_term(
    concept_id: str,
    *,
    pools: dict[str, dict[str, list[str] | str]],
    rng: random.Random,
    fallback_term: str = "",
) -> str:
    """Pick one display term for a concept using the locked priority order."""
    cid = str(concept_id or "").strip()
    pool = pools.get(cid) or {}
    surface = list(pool.get("surface_forms") or [])
    if surface:
        return str(rng.choice(surface))
    synonyms = list(pool.get("synonyms") or [])
    if synonyms:
        return str(rng.choice(synonyms))
    preferred = to_preferred_term(str(pool.get("preferred_term") or ""))
    if preferred:
        return preferred
    return to_preferred_term(fallback_term) or cid


def render_verbalised_pmh_narrative(
    pmh: list[PmhItem],
    *,
    seed: str,
    pools: dict[str, dict[str, list[str] | str]] | None = None,
    client: Any | None = None,
) -> str:
    """Render verbalised PMH blocks grouped by category."""
    if not pmh:
        return ""
    concept_ids = [item.concept_id for item in pmh if item.concept_id]
    resolved_pools = pools
    if resolved_pools is None:
        if client is None:
            resolved_pools = {}
        else:
            resolved_pools = load_verbalisation_pools(client, concept_ids)
    rng = random.Random(str(seed or "validation-lab"))
    grouped: dict[str, list[str]] = {}
    for item in pmh:
        label = pick_verbalised_term(
            item.concept_id,
            pools=resolved_pools,
            rng=rng,
            fallback_term=item.term,
        )
        if not label:
            continue
        grouped.setdefault(item.category, []).append(label)
    lines: list[str] = []
    for category in ("condition", "medication", "allergy"):
        terms = grouped.get(category)
        if not terms:
            continue
        lines.append(f"{_PMH_NARRATIVE_LABEL[category]}: {', '.join(terms)}.")
    return "\n".join(lines)


def compose_submission_text(
    *,
    reason: str,
    pmh: list[PmhItem],
    seed: str,
    client: Any | None = None,
    pools: dict[str, dict[str, list[str] | str]] | None = None,
) -> str:
    """Compose reason-for-submission plus verbalised PMH narrative."""
    reason_text = str(reason or "").strip()
    pmh_block = render_verbalised_pmh_narrative(
        pmh, seed=seed, pools=pools, client=client
    )
    if reason_text and pmh_block:
        return f"{reason_text}\n\n{pmh_block}"
    return reason_text or pmh_block
