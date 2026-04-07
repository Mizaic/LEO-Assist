from __future__ import annotations

import re
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
    specialist_outcome_letter_anchors: list[dict[str, Any]] = field(
        default_factory=list
    )
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
    "specialist_outcome_letter": "specialist_outcome_letter_anchors",
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
    list[dict[str, Any]],
]


# Domains whose concepts complete a pathway without confirming cancer.
# Their diagnosis anchors are tagged is_pathway_completion=True so the
# episode builder processes them after cancer diagnoses, ensuring cancer
# concepts claim referrals first.
_PATHWAY_COMPLETION_DOMAINS: frozenset[str] = frozenset({"no_cancer_discharge"})


def _build_buckets(
    registry: DomainRegistry,
) -> tuple[dict[str, MilestoneBucket], frozenset[int]]:
    """Build merged milestone buckets and the pathway-completion concept ID set.

    Multiple domains sharing the same milestone_type have their concept IDs
    merged so no domain silently overwrites another.

    Returns:
        buckets: milestone_type -> MilestoneBucket (merged across domains).
        pathway_completion_ids: concept IDs from _PATHWAY_COMPLETION_DOMAINS.
            Diagnosis anchors with these IDs are tagged is_pathway_completion=True
            and are processed last in the episode grouping step so that cancer
            diagnoses always claim referrals before benign pathway-closure codes.
    """
    merged_ids: dict[str, set[int]] = {}
    merged_no_filter: set[str] = set()
    merged_filters: dict[str, set[str]] = {}
    pathway_completion_ids: set[int] = set()

    for name, cfg in registry.get_milestone_domains().items():
        if not cfg.milestone_type:
            continue
        concept_ids = {
            int(c) for c in (registry.get_concept_ids(name) or []) if c is not None
        }
        mt = cfg.milestone_type
        merged_ids.setdefault(mt, set()).update(concept_ids)

        if not cfg.assertion_filter:
            merged_no_filter.add(mt)
        else:
            merged_filters.setdefault(mt, set()).update(cfg.assertion_filter)

        if name in _PATHWAY_COMPLETION_DOMAINS:
            pathway_completion_ids.update(concept_ids)

    buckets = {
        mt: MilestoneBucket(
            concept_ids=frozenset(ids),
            assertion_filter=(
                frozenset()
                if mt in merged_no_filter
                else frozenset(merged_filters.get(mt, set()))
            ),
        )
        for mt, ids in merged_ids.items()
    }
    return buckets, frozenset(pathway_completion_ids)


def _classify_anchor_rows(
    rows: list[dict[str, Any]],
    buckets: dict[str, MilestoneBucket],
    pathway_completion_ids: frozenset[int] = frozenset(),
) -> _AnchorBuckets:
    referrals: list[dict[str, Any]] = []
    diagnoses: list[dict[str, Any]] = []
    treatments: list[dict[str, Any]] = []
    specialists: list[dict[str, Any]] = []
    benign_closures: list[dict[str, Any]] = []
    specialist_letters: list[dict[str, Any]] = []

    bucket_lists = {
        "referral": referrals,
        "diagnosis": diagnoses,
        "treatment_start": treatments,
        "specialist_visit": specialists,
        "benign_closure": benign_closures,
        "specialist_outcome_letter": specialist_letters,
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
            if target is None:
                continue
            row_copy = dict(row)
            if milestone_type == "diagnosis" and concept_id in pathway_completion_ids:
                row_copy["is_pathway_completion"] = True
            target.append(row_copy)

    return (
        _dedupe_by_encounter(referrals),
        _dedupe_by_encounter(diagnoses),
        _dedupe_by_encounter(treatments),
        _dedupe_by_encounter(specialists),
        _dedupe_by_encounter(benign_closures),
        _dedupe_by_encounter(specialist_letters),
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

# Fetch encounter text for all encounters, including uncoded ones.
# Coding status is flagged so we can prefer coded-encounter anchors.
_TEXT_ENCOUNTER_QUERY = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id
  AND toString(e.date) >= $start_date
  AND toString(e.date) <= $end_date
  AND e.text IS NOT NULL AND trim(e.text) <> ''
RETURN
    toString(e.id)                              AS encounter_id,
    toString(e.date)                            AS encounter_date,
    coalesce(e.coding_status, 'coded')          AS coding_status,
    coalesce(e.classification_content_type, '') AS content_type,
    coalesce(e.classification_clinical_significance, '') AS significance,
    e.classification_domains                    AS domains,
    e.classification_encounter_purpose          AS purpose,
    e.text                                      AS text
ORDER BY encounter_date
"""

# -- Text pattern sets (compiled once at module level) --

_RE_CONFIRMED_CANCER = re.compile(
    r"\b(?:confirmed|diagnosed|diagnosis of|biopsy (?:showed|confirmed|proven)|"
    r"histology|histological|proven|malignancy confirmed|cancer confirmed|"
    r"positive for|diagnostic|definitive)\b",
    re.IGNORECASE,
)
_RE_CANCER_TERM = re.compile(
    r"\b(?:cancer|carcinoma|malignant|malignancy|melanoma|lymphoma|leukaemia|"
    r"leukemia|myeloma|sarcoma|mesothelioma|neoplasm|tumou?r|adenocarcinoma|"
    r"glioblastoma|glioma|squamous cell|basal cell|papillary|anaplastic|"
    r"metasta(?:sis|tic|ses)|oncolog)\b",
    re.IGNORECASE,
)
_RE_NO_CANCER = re.compile(
    r"\b(?:no evidence of (?:cancer|malignancy|malignant)|benign|not malignant|"
    r"no cancer|discharged from cancer pathway|normal biopsy|benign biopsy|"
    r"no evidence of disease|NED|all clear|nothing sinister|"
    r"no cancer found|no malignancy|no malignant|reassured)\b",
    re.IGNORECASE,
)
_RE_REFERRAL = re.compile(
    r"\b(?:fast.?track|2WW|two.week.wait|urgent (?:cancer )?referral|"
    r"suspected cancer referral|cancer referral|urgent suspected cancer|"
    r"straight to test|direct access|PRISM.*2WW)\b",
    re.IGNORECASE,
)
_RE_SPECIALIST = re.compile(
    r"\b(?:seen (?:in|at) (?:fast.?track|dermatol|oncol|urol|haematol|"
    r"colorectal|colorect|breast|lung|upper gi|lower gi|head and neck|"
    r"gynaecol|skin|cancer))|(?:clinic appointment|attended clinic|"
    r"specialist review|outpatient clinic|OPD|received letter from specialist|"
    r"seen by specialist|seen by (?:consultant|professor|Mr|Miss|Mrs|Dr))\b",
    re.IGNORECASE,
)
_RE_TREATMENT = re.compile(
    r"\b(?:chemotherapy|radiotherapy|immunotherapy|hormone therapy|SACT|"
    r"systemic anti.cancer|tamoxifen|letrozole|anastrozole|exemestane|"
    r"capecitabine|oxaliplatin|carboplatin|cisplatin|herceptin|trastuzumab|"
    r"pembrolizumab|nivolumab|atezolizumab|bevacizumab|rituximab|"
    r"mastectomy|lumpectomy|excision of (?:lesion|tumou?r|cancer)|"
    r"wide local excision|colectomy|hemicolectomy|anterior resection|"
    r"Whipple|pancreatectomy|nephrectomy|prostatectomy|cystectomy|"
    r"orchidectomy|thyroidectomy|laryngectomy|glossectomy|tonsillectomy|"
    r"skin (?:graft|flap)|Mohs surgery|VATS|lobectomy|pneumonectomy|"
    r"started treatment|commenced treatment|treatment started)\b",
    re.IGNORECASE,
)

# Sentinel concept IDs for text-derived anchors.
# Using the root parent IDs from each ValueSet so they appear as valid rows.
_TEXT_SENTINEL = {
    "referral": {
        "concept_id": 38586004,
        "concept_name": "Text: fast-track cancer referral",
    },
    "diagnosis_cancer": {
        "concept_id": 363346000,
        "concept_name": "Text: confirmed cancer diagnosis",
    },
    "diagnosis_benign": {
        "concept_id": 395100000,
        "concept_name": "Text: no evidence of cancer",
    },
    "specialist": {
        "concept_id": 306206005,
        "concept_name": "Text: specialist clinic attendance",
    },
    "treatment": {
        "concept_id": 401004,
        "concept_name": "Text: cancer treatment procedure",
    },
    # SNOMED 308470004 Letter (record artifact) -- aligns with specialist_outcome_letter ValueSet
    "specialist_outcome_letter": {
        "concept_id": 308470004,
        "concept_name": "Text: specialist outcome letter received",
    },
}


def _purpose_has_clinic_letter(purpose: Any) -> bool:
    if purpose is None:
        return False
    if isinstance(purpose, (list, tuple)):
        return any(str(p) == "clinic_letter" for p in purpose)
    return str(purpose) == "clinic_letter"


def _classify_text_encounters(
    text_rows: list[dict[str, Any]],
    already_coded_ids: set[str],
) -> _AnchorBuckets:
    """Classify uncoded encounter text into milestone buckets.

    Only processes encounters NOT already represented by coded DOCUMENTS rows,
    and only clinical-significance encounters (not admin-only, not empty text).
    Returns rows using sentinel concept IDs so the episode builder can use them.

    document_transfer encounters tagged ``clinic_letter`` are always scanned;
    filing-note text may be very short.
    """
    referrals: list[dict[str, Any]] = []
    diagnoses: list[dict[str, Any]] = []
    treatments: list[dict[str, Any]] = []
    specialists: list[dict[str, Any]] = []
    benign_closures: list[dict[str, Any]] = []
    specialist_letters: list[dict[str, Any]] = []

    for row in text_rows:
        enc_id = row.get("encounter_id") or ""
        if enc_id in already_coded_ids:
            continue  # already handled via DOCUMENTS path

        content_type = str(row.get("content_type") or "")
        if content_type == "admin_only":
            continue  # skip pure admin notes

        text = row.get("text") or ""
        is_letter_transfer = (
            content_type == "document_transfer"
            and _purpose_has_clinic_letter(row.get("purpose"))
        )
        if len(text) < 10 and not is_letter_transfer:
            continue

        date = str(row.get("encounter_date") or "")
        base = {
            "encounter_id": enc_id,
            "encounter_date": date,
            "source": "text_search",
            "confidence": 0.6,
            "evidence": text[:200],
            "assertion": "present",
        }

        has_cancer = bool(_RE_CANCER_TERM.search(text))
        has_confirmed = bool(_RE_CONFIRMED_CANCER.search(text))
        has_no_cancer = bool(_RE_NO_CANCER.search(text))

        if is_letter_transfer:
            s = _TEXT_SENTINEL["specialist_outcome_letter"]
            specialist_letters.append({**base, **s})

        # Referral
        if _RE_REFERRAL.search(text):
            s = _TEXT_SENTINEL["referral"]
            referrals.append({**base, **s})

        # Diagnosis -- cancer
        if has_cancer and has_confirmed and not has_no_cancer:
            s = _TEXT_SENTINEL["diagnosis_cancer"]
            diagnoses.append({**base, **s})

        # Benign closure
        if has_no_cancer:
            s = _TEXT_SENTINEL["diagnosis_benign"]
            row_copy = {**base, **s, "is_pathway_completion": True}
            benign_closures.append(row_copy)

        # Specialist visit
        if _RE_SPECIALIST.search(text):
            s = _TEXT_SENTINEL["specialist"]
            specialists.append({**base, **s})

        # Treatment
        if _RE_TREATMENT.search(text):
            s = _TEXT_SENTINEL["treatment"]
            treatments.append({**base, **s})

    return (
        _dedupe_by_encounter(referrals),
        _dedupe_by_encounter(diagnoses),
        _dedupe_by_encounter(treatments),
        _dedupe_by_encounter(specialists),
        _dedupe_by_encounter(benign_closures),
        _dedupe_by_encounter(specialist_letters),
    )


def detect_anchors(
    patient_id: str,
    start_date: str,
    end_date: str,
    patient_client,
    registry: DomainRegistry,
    expand_months: int = 3,
    use_text_search: bool = True,
) -> AnchorResult:
    """Detect clinical anchors for a patient using two complementary layers.

    Layer 1 -- SNOMED codes: exact concept-ID match against the IS_A-expanded
    ValueSet buckets via DOCUMENTS relationships on coded encounters.

    Layer 2 -- text search: regex classification of encounter free text for
    encounters that are uncoded or where coding may be incomplete.  Text-derived
    anchors use sentinel concept IDs (root parents) and are merged with SNOMED
    results; coded anchors take precedence for the same encounter.
    """
    buckets, pathway_completion_ids = _build_buckets(registry)

    # -- Layer 1: SNOMED-coded encounters --
    coded_rows = list(
        patient_client.run(
            _ANCHOR_QUERY,
            patient_id=patient_id,
            start_date=start_date,
            end_date=end_date,
        )
        or []
    )
    (
        referrals,
        diagnoses,
        treatments,
        specialists,
        benign_closures,
        specialist_letters,
    ) = _classify_anchor_rows(coded_rows, buckets, pathway_completion_ids)

    # -- Layer 2: encounter text (uncoded + all encounters) --
    if use_text_search:
        already_coded_ids = {str(r.get("encounter_id") or "") for r in coded_rows}
        text_rows = list(
            patient_client.run(
                _TEXT_ENCOUNTER_QUERY,
                patient_id=patient_id,
                start_date=start_date,
                end_date=end_date,
            )
            or []
        )
        (
            t_refs,
            t_diags,
            t_treats,
            t_specs,
            t_benign,
            t_letters,
        ) = _classify_text_encounters(text_rows, already_coded_ids)
        # Merge: coded anchors first, then text-derived for encounters not
        # already represented in the coded set.
        seen_enc = {r["encounter_id"] for r in referrals}
        referrals += [r for r in t_refs if r["encounter_id"] not in seen_enc]
        seen_enc = {r["encounter_id"] for r in diagnoses}
        diagnoses += [r for r in t_diags if r["encounter_id"] not in seen_enc]
        seen_enc = {r["encounter_id"] for r in treatments}
        treatments += [r for r in t_treats if r["encounter_id"] not in seen_enc]
        seen_enc = {r["encounter_id"] for r in specialists}
        specialists += [r for r in t_specs if r["encounter_id"] not in seen_enc]
        seen_enc = {r["encounter_id"] for r in benign_closures}
        benign_closures += [r for r in t_benign if r["encounter_id"] not in seen_enc]
        seen_enc = {r["encounter_id"] for r in specialist_letters}
        specialist_letters += [
            r for r in t_letters if r["encounter_id"] not in seen_enc
        ]

    has_anchors = any(
        (
            referrals,
            diagnoses,
            treatments,
            specialists,
            benign_closures,
            specialist_letters,
        )
    )
    detection_method = "concept+text" if has_anchors else "none"
    if has_anchors and not use_text_search:
        detection_method = "concept"

    result = AnchorResult(
        patient_id=patient_id,
        referral_anchors=_dedupe_by_encounter(referrals),
        diagnosis_anchors=_dedupe_by_encounter(diagnoses),
        treatment_anchors=_dedupe_by_encounter(treatments),
        specialist_visit_anchors=_dedupe_by_encounter(specialists),
        benign_closure_anchors=_dedupe_by_encounter(benign_closures),
        specialist_outcome_letter_anchors=_dedupe_by_encounter(specialist_letters),
        detection_method=detection_method,
    )
    all_refs = result.referral_anchors
    if all_refs:
        try:
            raw_date = str(all_refs[0].get("encounter_date"))
            referral_date = datetime.fromisoformat(raw_date)
            delta = timedelta(days=30 * expand_months)
            result.expanded_start = (referral_date - delta).date().isoformat()
            result.expanded_end = (referral_date + delta).date().isoformat()
        except (TypeError, ValueError):
            result.errors.append("invalid_referral_date")
    return result
