"""SNOMED investigation family: procedure, observable, and finding.

A result or finding can prove a recommended procedure is already done
when SNOMED links them with Interprets (363714003) or Has component
(246093002). Shared leftover pairs live on InvestigationFamily in
Neo4j. FIT stays as a packaged fallback until that family is seeded.

Atlas trace:
  DI: DI-B3B44F09
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-B3B44F09")
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping

from libs.guidelines.investigation_family_catalog import family_ids_for_concept

RelatedLookup = Callable[[str], dict[str, Any]]

FIT_KIT_PROCEDURE_ID = "149421000000109"
FIT_RESULT_OBSERVABLE_ID = "1049361000000101"
FIT_FAMILY_IDS: frozenset[str] = frozenset(
    {
        FIT_KIT_PROCEDURE_ID,
        FIT_RESULT_OBSERVABLE_ID,
        "1101361000000103",  # BCSP liquid FIT normal
        "1101371000000105",  # BCSP liquid FIT abnormal
        "1101381000000107",  # BCSP liquid FIT technical failure
        "1101391000000109",  # BCSP liquid FIT sample rejected
    }
)

_RELATED_KEYS = (
    "has_components",
    "interpreted_by_findings",
    "interprets_observables",
    "component_of_procedures",
    "associated_findings",
)


def _ids_from_related(related: dict[str, Any] | None) -> set[str]:
    ids: set[str] = set()
    if not related:
        return ids
    for key in _RELATED_KEYS:
        for item in related.get(key) or []:
            concept_id = str(item.get("id") or "").strip()
            if concept_id:
                ids.add(concept_id)
    return ids


def curated_family_ids(concept_id: str) -> set[str]:
    """Return extra family ids for known unlinked investigation pairs."""
    cid = str(concept_id or "").strip()
    if cid in FIT_FAMILY_IDS:
        return set(FIT_FAMILY_IDS)
    return set()


def evidence_ids_for_action(
    concept_id: str,
    *,
    related: dict[str, Any] | None = None,
    families: Mapping[str, set[str]] | None = None,
) -> set[str]:
    """Ids that mean this investigation has already been done."""
    cid = str(concept_id or "").strip()
    if not cid:
        return set()
    evidence = {cid}
    evidence |= _ids_from_related(related)
    evidence |= family_ids_for_concept(cid, families)
    evidence |= curated_family_ids(cid)
    return evidence


def patient_fact_ids(
    patient_codes: Iterable[str] | None,
    observations: Iterable[dict[str, Any]] | None,
) -> set[str]:
    """Coded concepts plus observation observable ids."""
    facts = {str(code).strip() for code in (patient_codes or []) if str(code).strip()}
    for row in observations or []:
        observable_id = str(row.get("observable_id") or "").strip()
        if observable_id:
            facts.add(observable_id)
    return facts


def reverse_action_match(
    action_id: str,
    fact_ids: Iterable[str],
    related_lookup: RelatedLookup,
) -> bool:
    """True when a patient fact Interprets or is a component of the action."""
    aid = str(action_id or "").strip()
    if not aid:
        return False
    for fact_id in fact_ids:
        related = related_lookup(str(fact_id))
        if aid in _ids_from_related(related):
            return True
        if _finding_interprets_action_component(aid, related, related_lookup):
            return True
    return False


def _finding_interprets_action_component(
    action_id: str,
    finding_related: dict[str, Any],
    related_lookup: RelatedLookup,
) -> bool:
    """True when the finding Interprets an observable of this procedure."""
    for item in finding_related.get("interprets_observables") or []:
        obs_id = str(item.get("id") or "").strip()
        if not obs_id:
            continue
        obs_related = related_lookup(obs_id)
        proc_ids = {
            str(proc.get("id") or "").strip()
            for proc in (obs_related.get("component_of_procedures") or [])
        }
        if action_id in proc_ids:
            return True
    return False
