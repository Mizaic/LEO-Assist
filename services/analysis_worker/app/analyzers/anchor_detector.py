from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from libs.domain_config.registry import DomainRegistry


@dataclass(frozen=True)
class MilestoneBucket:
    concept_ids: frozenset
    assertion_filter: frozenset  # empty = accept all assertions


@dataclass
class AnchorResult:
    patient_id: str
    referral_anchors: list[dict[str, Any]] = field(default_factory=list)
    diagnosis_anchors: list[dict[str, Any]] = field(default_factory=list)
    treatment_anchors: list[dict[str, Any]] = field(default_factory=list)
    specialist_visit_anchors: list[dict[str, Any]] = field(default_factory=list)
    benign_closure_anchors: list[dict[str, Any]] = field(default_factory=list)
    detection_method: str = "none"
    expanded_start: str | None = None
    expanded_end: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def has_referral(self) -> bool:
        return bool(self.referral_anchors)

    @property
    def earliest_date(self) -> str | None:
        if not self.referral_anchors:
            return None
        return str(self.referral_anchors[0].get("encounter_date") or "")


_MILESTONE_TYPE_TO_BUCKET_KEY = {
    "referral": "referral_anchors",
    "diagnosis": "diagnosis_anchors",
    "treatment_start": "treatment_anchors",
    "specialist_visit": "specialist_visit_anchors",
    "benign_closure": "benign_closure_anchors",
}


def _dedupe_by_encounter(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        encounter_id = str(row.get("encounter_id") or "")
        if not encounter_id or encounter_id in seen:
            continue
        seen.add(encounter_id)
        out.append(dict(row))
    return out


_AnchorBuckets = tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]


def _build_buckets(registry: DomainRegistry) -> dict[str, MilestoneBucket]:
    """Build a milestone_type -> MilestoneBucket map from the registry."""
    buckets: dict[str, MilestoneBucket] = {}
    for name, cfg in registry.get_milestone_domains().items():
        if not cfg.milestone_type:
            continue
        concept_ids = frozenset(
            int(c) for c in (registry.get_concept_ids(name) or [])
            if c is not None
        )
        buckets[cfg.milestone_type] = MilestoneBucket(
            concept_ids=concept_ids,
            assertion_filter=frozenset(cfg.assertion_filter),
        )
    return buckets


def _classify_anchor_rows(
    rows: list[dict[str, Any]],
    buckets: dict[str, MilestoneBucket],
) -> _AnchorBuckets:
    referrals: list[dict[str, Any]] = []
    diagnoses: list[dict[str, Any]] = []
    treatments: list[dict[str, Any]] = []
    specialists: list[dict[str, Any]] = []
    benign_closures: list[dict[str, Any]] = []

    bucket_lists = {
        "referral": referrals,
        "diagnosis": diagnoses,
        "treatment_start": treatments,
        "specialist_visit": specialists,
        "benign_closure": benign_closures,
    }

    for row in rows:
        try:
            concept_id = int(row.get("concept_id"))
        except (TypeError, ValueError):
            continue
        assertion = str(row.get("assertion") or "present")

        for milestone_type, bucket in buckets.items():
            if concept_id not in bucket.concept_ids:
                continue
            if bucket.assertion_filter and assertion not in bucket.assertion_filter:
                continue
            target = bucket_lists.get(milestone_type)
            if target is not None:
                target.append(dict(row))

    return (
        _dedupe_by_encounter(referrals),
        _dedupe_by_encounter(diagnoses),
        _dedupe_by_encounter(treatments),
        _dedupe_by_encounter(specialists),
        _dedupe_by_encounter(benign_closures),
    )


_ANCHOR_QUERY = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(c)
WHERE toString(p.id) = $patient_id
  AND toString(e.date) >= $start_date
  AND toString(e.date) <= $end_date
RETURN
    toString(e.id)              AS encounter_id,
    toString(e.date)            AS encounter_date,
    c.conceptId                 AS concept_id,
    c.name                      AS concept_name,
    c.semanticTag               AS semantic_tag,
    r.source                    AS source,
    coalesce(r.confidence, 0.0) AS confidence,
    r.evidence                  AS evidence,
    coalesce(r.assertion, 'present') AS assertion
ORDER BY encounter_date
"""


def detect_anchors(
    patient_id: str,
    start_date: str,
    end_date: str,
    patient_client,
    registry: DomainRegistry,
    expand_months: int = 3,
) -> AnchorResult:
    buckets = _build_buckets(registry)
    rows = patient_client.run(
        _ANCHOR_QUERY,
        patient_id=patient_id,
        start_date=start_date,
        end_date=end_date,
    )
    referrals, diagnoses, treatments, specialists, benign_closures = (
        _classify_anchor_rows(list(rows or []), buckets)
    )
    has_anchors = any((referrals, diagnoses, treatments, specialists, benign_closures))
    result = AnchorResult(
        patient_id=patient_id,
        referral_anchors=referrals,
        diagnosis_anchors=diagnoses,
        treatment_anchors=treatments,
        specialist_visit_anchors=specialists,
        benign_closure_anchors=benign_closures,
        detection_method="concept" if has_anchors else "none",
    )
    if referrals:
        try:
            raw_date = str(referrals[0].get("encounter_date"))
            referral_date = datetime.fromisoformat(raw_date)
            delta = timedelta(days=30 * expand_months)
            result.expanded_start = (referral_date - delta).date().isoformat()
            result.expanded_end = (referral_date + delta).date().isoformat()
        except (TypeError, ValueError):
            result.errors.append("invalid_referral_date")
    return result
