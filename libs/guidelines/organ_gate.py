"""Drop organ-specific guideline rules the patient cannot have.

Atlas:
  DI: DI-D260D249, DI-9AA2CDA5
  DO: DO-C9F7BFC8
  VT: VT-76A1816F
"""

from __future__ import annotations

from typing import Any, Iterable

_FEMALE_ORGAN_IDS = frozenset(
    {
        "71252005",  # cervix uteri
        "35039007",  # uterus
        "15497006",  # ovary structure
        "31435000",  # fallopian tube
    }
)
_MALE_ORGAN_IDS = frozenset(
    {
        "41216001",  # prostate gland
        "40689003",  # testis
    }
)


def _concept_ids_in_tree(node: dict[str, Any] | None) -> set[str]:
    if not node:
        return set()
    ids: set[str] = set()
    concept_id = str(node.get("concept_id") or "").strip()
    if concept_id:
        ids.add(concept_id)
    for child in node.get("children") or []:
        if isinstance(child, dict):
            ids |= _concept_ids_in_tree(child)
    return ids


def rule_requires_absent_organ(
    rule: dict[str, Any],
    patient_sex: str | None,
    patient_fact_ids: Iterable[str],
) -> bool:
    """True when the rule needs an organ this patient does not have."""
    sex = str(patient_sex or "").lower().strip()
    facts = {str(item).strip() for item in patient_fact_ids if str(item).strip()}
    tree_ids = _concept_ids_in_tree(rule.get("logic_tree"))
    if sex in {"female", "f"}:
        return bool(tree_ids & _MALE_ORGAN_IDS) and not bool(facts & _MALE_ORGAN_IDS)
    if sex in {"male", "m"}:
        return bool(tree_ids & _FEMALE_ORGAN_IDS) and not bool(
            facts & _FEMALE_ORGAN_IDS
        )
    return False
