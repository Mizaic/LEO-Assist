"""Auto-stamped Atlas trace.

Atlas trace:
  DO: DO-0A64F95A
  Also implements: DO-0DFA6961, DO-2340F614, DO-694875ED, DO-6C398363, DO-B7060F57, DO-FCF80123
  DI: DI-080A2454, DI-37DDAADE, DI-4885D9FF, DI-6051F076, DI-E3689657
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-0A64F95A")
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from libs.domain_config.registry import DomainRegistry

# DI-LEO-AI-155: text-only site classification using gold-mined surface forms.
from services.analysis_worker.app.analyzers.cancer_site_terms import (
    match_cancer_site,
)

# DI-LEO-AI-159 / DI-LEO-AI-171 / DI-LEO-AI-172: Read/CTV3 code
# recognition for problem-list malignancy diagnoses, free-text
# malignancy terms on problem-list lines, active-cancer-care codes,
# adjuvant-therapy inference, benign-explanation problems, history-of-
# cancer guards, and explicit fast-track 2WW referral site
# reconciliation.
from libs.domains.code_inventories import (
    BENIGN_PHRASE_REQUIRES_CANCER_CONTEXT,
    adjuvant_therapy_is_newly_issued,
    encounter_diagnosis_is_narrative_restatement,
    encounter_is_cancer_care_review_restatement,
    encounter_problem_is_off_pathway,
    encounter_restates_past_event,
    find_active_cancer_care_code,
    find_adjuvant_therapy_drug,
    find_benign_explanation_code,
    find_cancer_follow_up_phrase,
    find_cancer_treatment_procedure_code,
    find_fast_track_referral_site,
    find_malignancy_code,
    find_malignancy_code_in_problem_line,
    find_malignancy_term_in_problem_line,
    find_specialist_clinic_site,
    match_benign_investigation_phrase,
    text_contains_history_of_cancer,
    text_has_cancer_pathway_context,
)


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
    first_presentation_anchors: list[dict[str, Any]] = field(default_factory=list)
    # DI-LEO-AI-145: "Seen in fast-track/2WW clinic" attendance encounters.
    first_seen_anchors: list[dict[str, Any]] = field(default_factory=list)
    # DI-LEO-AI-204: care_obstruction encounters (DNA due to mobility,
    # patient/family refusal of pathway investigations, hospital-cancelled
    # referral, safeguarding block, avoidable delay).
    care_obstruction_anchors: list[dict[str, Any]] = field(default_factory=list)
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
    "first_presentation": "first_presentation_anchors",
    "first_seen": "first_seen_anchors",
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


def _dedupe_first_presentation(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dedupe first-presentation anchors by encounter+concept, not encounter only.

    A single encounter can DOCUMENT multiple relevant concepts (symptom + place +
    sign). Keeping only one row per encounter loses signal and can incorrectly
    drop symptom evidence when a place/procedure concept appears first.
    """
    seen: set[tuple[str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        encounter_id = str(row.get("encounter_id") or "")
        concept_id = str(row.get("concept_id") or row.get("concept_name") or "")
        assertion = str(row.get("assertion") or "present")
        if not encounter_id or not concept_id:
            continue
        key = (encounter_id, concept_id, assertion)
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(row))
    return out


_AnchorBuckets = tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],  # DI-LEO-AI-145: first_seen
    list[dict[str, Any]],  # DI-LEO-AI-204: care_obstruction (Pattern G)
]


# Domains whose concepts complete a pathway without confirming cancer.
# Their diagnosis anchors are tagged is_pathway_completion=True so the
# episode builder processes them after cancer diagnoses, ensuring cancer
# concepts claim referrals first.
_PATHWAY_COMPLETION_DOMAINS: frozenset[str] = frozenset({"no_cancer_discharge"})

# -- first_presentation quality gates --------------------------------------
# Keep symptom/sign and investigation evidence, drop place/admin-only noise.
_FP_EXCLUDE_NAME_RE = re.compile(
    r"\b("
    r"seen in|seen by|consultation|appointment|outpatient|"
    r"clinic|service|general practitioner surgery|primary care establishment"
    r")\b",
    re.IGNORECASE,
)
_FP_INVESTIGATION_NAME_RE = re.compile(
    r"\b("
    r"test|scan|ct|mri|ultrasound|xray|x-ray|biopsy|histology|"
    r"colonoscopy|gastroscopy|endoscopy|psa|cea|ca125|investigation|imaging"
    r")\b",
    re.IGNORECASE,
)


def _is_first_presentation_row(row: dict[str, Any]) -> bool:
    tag = str(row.get("semantic_tag") or "").strip().lower().replace("_", " ")
    name = str(row.get("concept_name") or "").strip()
    if not name:
        return False
    if tag in {"environment", "place", "physical_object"}:
        return False
    if _FP_EXCLUDE_NAME_RE.search(name):
        return False
    if tag == "procedure":
        return bool(_FP_INVESTIGATION_NAME_RE.search(name))
    return True


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


def _build_construct_anchor_map(
    rows: list[dict[str, Any]],
    registry: DomainRegistry,
) -> dict[str, list[dict[str, Any]]]:
    """Build milestone anchors from role-based construct definitions."""
    by_encounter: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        encounter_id = str(row.get("encounter_id") or "")
        if not encounter_id:
            continue
        by_encounter.setdefault(encounter_id, []).append(row)

    anchors_by_milestone: dict[str, list[dict[str, Any]]] = {}
    for domain_name, cfg in registry.get_milestone_domains().items():
        if not cfg.milestone_type or not cfg.constructs:
            continue
        for encounter_rows in by_encounter.values():
            concept_ids = set()
            for row in encounter_rows:
                try:
                    concept_ids.add(int(row.get("concept_id")))
                except (TypeError, ValueError):
                    continue
            if not concept_ids:
                continue
            for construct in cfg.constructs:
                role_matches: list[tuple[str, list[int]]] = []
                for role in construct.roles:
                    matched_ids = [
                        cid for cid in role.concept_ids if int(cid) in concept_ids
                    ]
                    if matched_ids:
                        role_matches.append((role.role, matched_ids))
                if construct.logic == "ANY":
                    matched = bool(role_matches)
                else:
                    matched = all(
                        (not role.required)
                        or any(int(cid) in concept_ids for cid in role.concept_ids)
                        for role in construct.roles
                    )
                if not matched:
                    continue
                seed_id = 0
                for _role, ids in role_matches:
                    if ids:
                        seed_id = int(ids[0])
                        break
                base_row = encounter_rows[0]
                anchors_by_milestone.setdefault(cfg.milestone_type, []).append(
                    {
                        "encounter_id": base_row.get("encounter_id"),
                        "encounter_date": base_row.get("encounter_date"),
                        "concept_id": seed_id,
                        "concept_name": f"Construct: {construct.display_name}",
                        "semantic_tag": "Situation",
                        "source": "construct_match",
                        "confidence": 0.8,
                        "evidence": base_row.get("evidence"),
                        "assertion": "present",
                        "construct_id": construct.construct_id,
                    }
                )
    return anchors_by_milestone


def _merge_anchor_lists(
    base_rows: list[dict[str, Any]],
    construct_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge anchors preferring construct-derived rows per encounter."""
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for row in construct_rows + base_rows:
        encounter_id = str(row.get("encounter_id") or "")
        if not encounter_id or encounter_id in seen:
            continue
        seen.add(encounter_id)
        merged.append(row)
    return merged


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
    first_presentations: list[dict[str, Any]] = []
    # DI-LEO-AI-145: coded path never produces first_seen anchors; text-only.
    first_seens: list[dict[str, Any]] = []

    bucket_lists = {
        "referral": referrals,
        "diagnosis": diagnoses,
        "treatment_start": treatments,
        "specialist_visit": specialists,
        "benign_closure": benign_closures,
        "specialist_outcome_letter": specialist_letters,
        "first_presentation": first_presentations,
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
            if milestone_type == "first_presentation":
                if not _is_first_presentation_row(row_copy):
                    continue
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
        _dedupe_first_presentation(first_presentations),
        first_seens,  # DI-LEO-AI-145: always empty from coded path
        [],  # DI-LEO-AI-204: care_obstruction is text-only (Pattern G)
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

# DI-LEO-AI-149: histology-aware confirmed-cancer detection. The legacy
# pattern only matched 'confirmed', 'diagnosed', 'biopsy showed', and a few
# generic verbs. Investigation of 79 auto-closed text-path episodes found
# 24 (30%) where the histology letter used vocabulary the regex did not
# cover -- e.g. 'Invasive ductal carcinoma, grade 2', 'Adenocarcinoma of
# colon (T2 N0 M0)', 'DCIS high grade', 'Gleason 7 (3+4) prostate'. These
# additional alternations capture standard histology-result phrasing
# without changing the upstream _is_referral_enc / not _has_no_cancer
# guards that prevent suspected-cancer referrals from being mis-classified
# as confirmed diagnoses.
_RE_CONFIRMED_CANCER = re.compile(
    r"\b(?:confirmed|diagnosed|diagnosis of|biopsy (?:showed|confirmed|proven)|"
    r"histology|histological|histopathology|histopathological|"
    r"proven|malignancy confirmed|cancer confirmed|"
    r"positive for|diagnostic|definitive|"
    r"invasive ductal|invasive lobular|invasive carcinoma|"
    r"DCIS|LCIS|in[-\s]?situ|carcinoma in[-\s]?situ|"
    r"adenocarcinoma|squamous cell carcinoma|basal cell carcinoma|"
    r"BCC|SCC|"
    r"high[-\s]grade|low[-\s]grade|"
    r"poorly differentiated|moderately differentiated|well differentiated|"
    r"grade [123iv]+|"
    r"Gleason\s*\d|"
    r"T[0-4][a-c]?\s*N[0-3][a-c]?\s*M[01x]|"
    r"stage\s*(?:I{1,3}V?|IV|[1-4])(?:[abc])?\b|"
    r"FIGO\s*(?:I{1,3}V?|IV|[1-4])(?:[abc])?\b|"
    r"Dukes[''\s]?[ABCD]|"
    r"Breslow|Clark[''\s]?level|"
    r"melanoma in[-\s]?situ|melanoma confirmed|"
    r"metasta(?:sis|tic|ses)|metastatic disease|"
    r"lymph node involvement|positive (?:margin|node|lymph node)s?|"
    r"infiltrating (?:ductal|lobular|carcinoma)|"
    r"frank malignancy|frankly malignant)\b",
    re.IGNORECASE,
)
# DI-LEO-AI-149: include histology-specific cancer terms (DCIS, LCIS,
# Gleason, Dukes, FIGO etc.) so the classifier's
# 'has_cancer AND has_confirmed' guard accepts modern histology-letter
# vocabulary without needing the generic 'cancer / carcinoma / malignant'
# words to also be present.
_RE_CANCER_TERM = re.compile(
    r"\b(?:cancer|carcinoma|malignant|malignancy|melanoma|lymphoma|leukaemia|"
    r"leukemia|myeloma|sarcoma|mesothelioma|neoplasm|tumou?r|adenocarcinoma|"
    r"glioblastoma|glioma|squamous cell|basal cell|papillary|anaplastic|"
    r"metasta(?:sis|tic|ses)|oncolog|"
    r"DCIS|LCIS|BCC|SCC|"
    r"invasive ductal|invasive lobular|invasive carcinoma|"
    r"infiltrating (?:ductal|lobular|carcinoma)|"
    r"in[-\s]?situ|carcinoma in[-\s]?situ|"
    r"Gleason\s*\d|"
    r"Dukes[''\s]?[ABCD]|"
    r"FIGO\s*(?:I{1,3}V?|IV|[1-4])|"
    r"Breslow|Clark[''\s]?level)\b",
    re.IGNORECASE,
)
# DI-LEO-AI-149: histology-aware benign-closure detection. The legacy
# pattern relied on explicit 'no cancer / NED / nothing sinister' phrasing
# and missed the standard benign-histology vocabulary that appears in
# 19/79 (24%) auto-closed episodes -- e.g. 'Lipoma', 'Sebaceous cyst',
# 'Fibroadenoma', 'No malignant cells', 'Normal appearance', 'Unremarkable
# biopsy'. Adding these terms lets the episode builder close benign
# pathways at the right calendar date instead of leaving them as
# stale_post_specialist for 90+ days.
# DI-LEO-AI-178 split (R-LEO-AI-173 follow-up):
# Definitive benign findings -- inherently benign histology / pathology /
# explicit "no cancer" statements. These are sufficient on their own to
# emit a benign_closure anchor and do NOT require co-occurring
# cancer-pathway context.
_RE_DEFINITIVE_BENIGN = re.compile(
    r"\b(?:no evidence of (?:cancer|malignancy|malignant)|"
    r"not malignant|no cancer|discharged from cancer pathway|"
    r"normal biopsy|benign biopsy|"
    r"no evidence of disease|NED|all clear|nothing sinister|"
    r"no cancer found|no malignancy|no malignant|"
    r"no malignant cells|no atypia|no atypical cells|"
    r"no abnormality detected|no significant abnormality|"
    r"normal appearance|normal histology|normal biopsy result|"
    r"unremarkable biopsy|unremarkable histology|unremarkable findings|"
    r"benign (?:naevus|nevus|lesion|finding|cyst|polyp|nodule)|"
    r"lipoma|fibroadenoma|sebaceous cyst|epidermal cyst|epidermoid cyst|"
    r"seborrhoeic keratos[ie]s|seborrheic keratos[ie]s|"
    r"actinic keratos[ie]s|solar keratos[ie]s|"
    r"skin tag|acrochordon|dermatofibroma|"
    r"inflammatory change|reactive change|reactive atypia|"
    r"hyperplastic polyp|inflammatory polyp|"
    r"fibrocystic change|cystic change|"
    r"intramucosal|hamartoma)\b",
    re.IGNORECASE,
)
# Generic benign-disposition phrases -- these are ambiguous on their own
# (e.g. "discharged from clinic" can apply to any clinic) and only count
# towards a benign_closure when accompanied by cancer-pathway context.
_RE_GENERIC_BENIGN_PHRASE = re.compile(
    r"\b(?:benign|reassured|"
    r"discharge(?:d)? back to gp|discharge(?:d)? from clinic|"
    r"reassur(?:e|ed|ance) given)\b",
    re.IGNORECASE,
)
# Combined view -- any benign signal at all. Kept for callers that just
# need a single "is there any 'no cancer' wording?" check.
_RE_NO_CANCER = re.compile(
    "(?:"
    + _RE_DEFINITIVE_BENIGN.pattern
    + ")|(?:"
    + _RE_GENERIC_BENIGN_PHRASE.pattern
    + ")",
    re.IGNORECASE,
)
_RE_REFERRAL = re.compile(
    r"\b(?:fast.?track|2WW|two.week.wait|urgent (?:cancer )?referral|"
    r"suspected cancer referral|cancer referral|urgent suspected cancer|"
    r"straight to test|direct access|PRISM.*2WW)\b",
    re.IGNORECASE,
)
# DI-LEO-AI-201 (Pattern C+D): narrative-reference guard. The legacy
# behaviour fired text_generic referral anchors any time _RE_REFERRAL
# matched -- including phone consults that NARRATED past pathway
# activity ("referred to 2WW clinic but not attended", "previous
# positive FIT and 2WW", "explained 2WW referral requested again but
# got rejected", "noted ongoing borderline anaemia and previous
# positive FIT and 2WW and its outcome where pt did not want any
# invasive investigation"). These mentions are historical or
# descriptive, not new referral events, but they spawned phantom
# in-progress / completed pathways that polluted the cohort.
#
# When a text_generic referral candidate matches _RE_REFERRAL but
# (a) carries no STRUCTURAL referral evidence AND
# (b) carries narrative-reference markers
# we suppress the referral anchor. Encounters with structural
# evidence (PRISM proforma, Outbound referral, Fast track Read code,
# "Refer via 2WW" instruction, Choose-and-book line, Hospital fast-
# track referral status row) still fire as before.
_RE_NARRATIVE_REFERRAL_REFERENCE = re.compile(
    r"\b(?:previous(?:ly)?\s+(?:positive\s+)?(?:FIT|2WW|TWW|fast.?track|"
    r"referral)|"
    r"had\s+(?:a\s+)?(?:previous\s+|prior\s+)?"
    r"(?:2WW|TWW|fast.?track|referral|FIT)|"
    r"history\s+of\s+(?:2WW|TWW|fast.?track|referral)|"
    r"hx\s+of\s+(?:2WW|TWW|fast.?track|referral)|"
    r"prior\s+(?:2WW|TWW|fast.?track|referral)|"
    r"noted\s+(?:ongoing|previous|past|prior)|"
    r"did\s+not\s+attend|not\s+attended|"
    r"missed\s+(?:the\s+)?(?:2WW|TWW|fast.?track|appointment|"
    r"referral|clinic)|"
    r"\bDNA(?:'?d)?\b|"
    r"explained\s+(?:that\s+)?(?:the\s+)?(?:2WW|TWW|referral)|"
    r"discussed\s+(?:the\s+)?(?:2WW|TWW|referral)|"
    r"outcome\s+where\s+(?:pt|patient)|"
    r"(?:pt|patient)\s+did\s+not\s+want|"
    r"(?:pt|patient)\s+declined|"
    # DI-LEO-AI-212 (Pattern J): "was/were/has been seen by ENT under
    # 2ww in Jan", "seen under 2WW last month", "seen in fast track
    # clinic previously" -- past-tense seen-narrative referencing the
    # historical 2WW pathway. The encounter is a follow-up describing
    # what happened, not a new referral event.
    r"(?:was|were|has\s+been|had\s+been)\s+seen\s+"
    r"(?:by|under|in|at)\s+.{0,40}?"
    r"\b(?:2WW|TWW|fast.?track|clinic|specialist)\b|"
    r"\bseen\s+(?:by|under|in|at)\s+.{0,40}?"
    r"\b(?:2WW|TWW|fast.?track)\b|"
    # DI-LEO-AI-212 (Pattern J): "Write to ENT to clarify ...",
    # "letter to ENT", "email to consultant" -- clinician-to-clinician
    # clarification, not a new referral.
    r"(?:write|writing|wrote|letter|email|message)\s+(?:to|back\s+to)\s+"
    r"(?:ENT|consultant|specialist|hospital|registrar|clinic)|"
    # DI-LEO-AI-216 (Pattern L): retrospective self-narration of the
    # original referral inside a follow-up / cancer-care-review note,
    # e.g. "Referred by me on 2ww earlier this year, confirmed breast
    # cancer", "I referred her last month", "We referred him in Jan",
    # "GP referred via 2WW back in March". These narrate a previous
    # referral event and must not open a fresh EpisodeOfCare.
    r"(?:referred|referral)\s+by\s+(?:me|us|GP|the\s+GP|"
    r"(?:Dr|Mr|Mrs|Ms|Miss)\b)|"
    r"\b(?:I|we)\s+referred\b|"
    r"(?:^|\W)GP\s+referred\b|"
    r"\breferred\s+(?:on\s+)?(?:2WW|TWW|fast.?track)\s+"
    r"(?:earlier|last|previously|back|in\s+(?:Jan(?:uary)?|Feb(?:ruary)?|"
    r"Mar(?:ch)?|Apr(?:il)?|May|Jun[e]?|Jul[y]?|Aug(?:ust)?|Sep(?:tember)?|"
    r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?|\d{4}))|"
    r"\bpreviously\s+referred\b|"
    r"refused\s+(?:to\s+)?(?:attend|come|engage|be\s+seen))\b",
    re.IGNORECASE,
)
# DI-LEO-AI-211 (Pattern I): boilerplate referral guidance in
# auto-filed lab results / standardised disclaimer text. Lab reports
# (PSA, CA125, FIT, calprotectin, etc.) carry standardised guidance
# such as "If the PSA value remains elevated above the age specific
# threshold, refer as a 2WW (Please note that referrals made at the
# time of UTI will be rejected)." This is conditional guidance, NOT
# an actual referral; the patient may not breach the threshold.
# When _RE_REFERRAL fires on text like this AND no structural
# referral evidence is present, the candidate is suppressed.
_RE_BOILERPLATE_REFERRAL_GUIDANCE = re.compile(
    r"(?:"
    r"\bif\s+(?:the\s+)?(?:PSA|CEA|CA[\s-]?125|FIT|calprotectin|"
    r"value|level|result|reading|score|test)\b"
    r".{0,160}?"
    r"\b(?:elevated|above|over|exceeds?|raised|abnormal|positive|"
    r"high|>=?|greater\s+than)\b"
    r".{0,160}?"
    r"\brefer(?:\s+as)?\b|"
    r"\b(?:please\s+)?refer\s+(?:as\s+)?(?:a\s+|an\s+)?"
    r"(?:2WW|TWW|two.week.wait|fast.?track)\s+if\b|"
    r"\bshould\s+be\s+referred\s+(?:as\s+)?(?:a\s+|an\s+)?"
    r"(?:2WW|TWW|fast.?track)\b|"
    r"\bconsider\s+(?:a\s+|an\s+)?(?:2WW|TWW|fast.?track)\s+referral\s+if\b|"
    r"\b(?:please\s+note\s+that\s+)?referrals?\s+made\s+(?:at\s+the\s+"
    r"time\s+of|during|whilst)\b"
    r")",
    re.IGNORECASE | re.DOTALL,
)
# DI-LEO-AI-211 (Pattern I): auto-filed lab/result encounter prefix.
# Practice EMRs prepend "Auto-filed" to results that arrived from the
# lab without a clinician keystroke. Such encounters never represent
# a new referral event -- they are read-only result drops carrying
# standardised disclaimer text. We treat the "Auto-filed" prefix as
# strong evidence the encounter is a result drop rather than a
# clinical event.
_RE_AUTO_FILED_PREFIX = re.compile(
    r"(?im)^\s*\d{1,2}:\d{2}\s*-\s*Surgery:\s*Auto.?filed\b",
)
# DI-LEO-AI-210 (Pattern H): family-history-of-cancer markers. A
# cancer mention that ONLY appears in a family-history context must
# not classify the encounter as a patient cancer event. The classic
# trigger is "FH prostate ca - father diagnosed at 75" appended to a
# PSA request: the patient does not have prostate cancer; family
# history is the indication for screening. The guard suppresses both
# (a) text_generic referrals where _RE_REFERRAL matches solely from
# disclaimer or family-history context and (b) downstream cancer-
# type inference from FH-only encounter text.
_RE_FAMILY_HISTORY_CANCER = re.compile(
    r"(?:"
    r"\bF[Hh][Xx]?\b\.?\s*(?:of\s+)?[A-Za-z\s]{0,40}?"
    r"\b(?:cancer|ca\b|carcinoma|malignan\w+|tumou?r|melanoma|"
    r"lymphoma|leuk(?:a|e)mia|sarcoma|adenocarcinoma)|"
    r"\bfamily\s+history\s+(?:of\s+)?[A-Za-z\s]{0,40}?"
    r"\b(?:cancer|ca\b|carcinoma|malignan\w+|tumou?r|melanoma|"
    r"lymphoma|leuk(?:a|e)mia|sarcoma)|"
    r"\b(?:father|mother|dad|mum|sister|brother|sibling|son|"
    r"daughter|aunt|uncle|cousin|grandfather|grandmother|"
    r"grandparent|relative|next\s+of\s+kin)\b"
    r"[^.\n]{0,80}?"
    r"\b(?:had|has|diagnosed\s+with|died\s+(?:from|of)|"
    r"history\s+of)\b"
    r"[^.\n]{0,40}?"
    r"\b(?:cancer|ca\b|carcinoma|malignan\w+|tumou?r|melanoma|"
    r"lymphoma|leuk(?:a|e)mia|sarcoma)"
    r")",
    re.IGNORECASE,
)
# DI-LEO-AI-201 (Pattern C+D): structural referral evidence. These are
# tokens that only appear when the encounter is a real referral event
# (workflow/template/Read-code/lab-instruction), not when the GP is
# narrating past activity. A text_generic referral fires only when at
# least one structural marker is present.
_RE_STRUCTURAL_REFERRAL = re.compile(
    r"(?:"
    r"\bXa(?:Mep|Me[A-Z]|alp)\b|"
    r"\bOutbound\s+referral\b|"
    r"\bHospital\s+Fast\s+track\s+referral\b|"
    r"\bChoose\s+and\s+book(?!\s+referral\s+rejected)|"
    r"\bChoice\s+and\s+booking\b|"
    r"\bPRISM\s+Pathway\s+&\s+Referral\b|"
    r"PRISM\s+\w+.{0,40}Pathway\s+Accessed|"
    r"\bRefer\s+via\s+2WW\b|"
    r"\brefer\s+via\s+(?:2WW|TWW|fast.?track)\b|"
    r"\bFast\s+track\s+referral\s+for\s+suspected\b"
    r")",
    re.IGNORECASE | re.DOTALL,
)
# DI-LEO-AI-204 (Pattern G): care-obstruction signals. These mark
# encounters where care was actively impeded -- patient/family
# refusing pathway investigations, hospital cancelling a referral
# for procedural reasons, missed/avoidable delays, or safeguarding
# concerns affecting access to care. They are NOT new referrals or
# rejections (those have their own anchors); they are quality
# signals the QA team needs to surface so blocked pathways can be
# escalated. The anchor fires on the encounter where the
# obstruction is documented; the episode builder attaches the
# anchor as an IS_PART_OF edge with milestone_type=care_obstruction
# and stamps a HITL flag on the parent episode.
_RE_CARE_OBSTRUCTION = re.compile(
    r"(?:"
    r"\b(?:not\s+attended|did\s+not\s+attend|DNA(?:'?d)?)\b"
    r".{0,80}\b(?:mobility|transport|carer|family|cancel|refuse|declin|"
    r"unable|safeguard|capacity)\b|"
    r"\b(?:refus(?:ed|ing|al)|declin(?:ed|ing|es))\b"
    r".{0,80}\b(?:colonoscopy|gastroscopy|endoscopy|biopsy|ct|mri|"
    r"scan|investigation|referral|2WW|TWW|fast.?track|appointment|"
    r"clinic|admission|treatment|assessment)\b|"
    r"\bsafeguard(?:ing)?\b|"
    r"\bavoidable\s+delay\b|"
    r"\bbest\s+interest\s+(?:meeting|decision)\b|"
    r"\bfailed\s+(?:to\s+attend|encounter|engage)\b|"
    r"\bunable\s+to\s+(?:attend|access|reach\s+patient)\b|"
    r"\b(?:family|son|daughter|carer|next\s+of\s+kin)\b"
    r".{0,80}\b(?:refus|declin|abusive|aggressive|terminated\s+"
    r"the\s+call|hung\s+up|f\*+k\s+off|fk\s+off|F\s+off)\b|"
    r"\bhospital\s+(?:cancel(?:l?ed)?|retract(?:ed)?|withdrew)\s+"
    r"(?:the\s+)?referral\b|"
    r"\bretract(?:ed|ing)?\s+(?:this\s+)?referral\b"
    r")",
    re.IGNORECASE | re.DOTALL,
)
# DI-LEO-AI-124: PRISM is the practice's digital proforma platform used
# for many referral classes (2WW cancer, sexual health, MSK, IBD,
# cardiology, ultrasound, hospice, advice & guidance, mental-health
# crisis, etc.). A finalised / submitted / completed PRISM questionnaire
# is the authoritative referral trigger ONLY when paired with cancer
# context (see _RE_PRISM_CANCER_CONTEXT below); otherwise it is some
# other specialty pathway and must not open a 2WW cancer episode.
_RE_REFERRAL_PRISM = re.compile(
    r"\b(?:PRISM|2WW\s*proforma|2WW\s*questionnaire)\b"
    r".{0,80}?"
    r"\b(?:finalised|finalized|completed|submitted|sent|issued)\b",
    re.IGNORECASE | re.DOTALL,
)
# DI-LEO-AI-195: PRISM cancer-2WW context guard. A PRISM proforma is a
# cancer 2WW only when the same encounter text also carries one of:
#   - the literal 2WW / TWW / two-week wait token,
#   - a "fast track referral for suspected ..." or "suspected cancer"
#     clinical phrase,
#   - a 2WW Read code (XaMeA-XaMeZ family covers fast-track referrals
#     for suspected breast / dermatology / lung / lower GI / upper GI /
#     urology / gynaecology / head and neck / haematology / NSS).
# This is a generic, practice-agnostic discriminator -- across the
# observed dataset every cancer-2WW PRISM template name contained
# "2WW" while no non-cancer PRISM template did.
_RE_PRISM_CANCER_CONTEXT = re.compile(
    r"\b(?:2WW|TWW|two[- ]week[- ]wait|"
    r"fast[- ]?track\s+referral\s+for\s+suspected|"
    r"suspected\s+cancer|XaMe[A-Z])\b",
    re.IGNORECASE,
)
# DI-LEO-AI-182: referral REJECTION and RESUBMISSION recognisers.
# Captures the workflow-quality signal "Choose and book referral
# rejected by service provider" / "Referral Marked in Error" /
# "Referral re-submitted". These are not new pathways -- they are
# audit events on an existing referral that introduce delay (6+ days
# common in 2WW). Surfaced as referral_subtype values so DQ tooling
# can measure rejection-to-resubmission delay without changing the
# milestone-type schema.
_RE_REFERRAL_REJECTED = re.compile(
    r"\b(?:referral\s+rejected\s+by\s+service\s+provider|"
    r"choose\s+and\s+book\s+referral\s+rejected|"
    r"e-?referral\s+(?:service\s+)?referral\s+rejected|"
    r"referral\s+(?:was\s+)?rejected\s+by\s+(?:the\s+)?(?:hospital|provider|service)|"
    r"hospital\s+rejected\s+(?:the\s+)?referral|"
    r"referral\s+returned\s+(?:by|from)\s+(?:hospital|provider|service))\b",
    re.IGNORECASE,
)
# Marked-in-Error on a referral row counts as a rejection-equivalent
# audit event (referral was withdrawn / amended). Match the referral-
# specific phrasing only so we do not catch unrelated "Marked in Error"
# notes (e.g. lab values).
_RE_REFERRAL_MARKED_IN_ERROR = re.compile(
    r"\b(?:referral\s+(?:out\s+)?(?:status\s+)?marked\s+in\s+error|"
    r"e-?referral\s+(?:service\s+)?referral\s+marked\s+in\s+error|"
    r"hospital\s+(?:fast\s+track\s+)?referral\s+(?:for\s+suspected\s+\w[\w\s]{0,40})?\s*"
    r"marked\s+in\s+error)\b",
    re.IGNORECASE,
)
_RE_REFERRAL_RESUBMITTED = re.compile(
    r"\b(?:re-?submitted|resubmitted|referral\s+re-?sent|"
    r"re-?referred|new\s+referral\s+sent|"
    r"referral\s+(?:re-)?issued|amended\s+referral\s+sent)\b",
    re.IGNORECASE,
)
# DI-LEO-AI-145: fast-track/2WW CLINIC ATTENDANCE (first_seen milestone).
# Matches the secondary-care filing note that the patient WAS SEEN at the
# clinic -- distinct from the GP-side referral ('Fast track referral for
# suspected X') and from any diagnosis text.  Must not overlap _RE_REFERRAL.
#
# DI-LEO-AI-201 (Pattern B): the previous bare alternation
# ``\b2WW\s+clinic\b`` matched any GP narrative phrase containing
# "2WW clinic" (e.g. "referred to 2WW clinic but not attended due to
# mobility issues") and emitted a phantom first_seen anchor on the
# referring GP's home visit. Patient 4643293950 had a Nov 2024 home
# visit narrative that fired first_seen on a DNA event; the episode
# rescue path then promoted the open Jan 2024 referral to "completed"
# with end_date = Nov, mass-claiming downstream encounters into the
# wrong episode. Every alternation now requires an attestation verb
# (seen|attended|reviewed) within proximity of the clinic token.
_RE_FIRST_SEEN = re.compile(
    r"\bseen in (?:fast.?track|2WW|TWW|two.week.wait)"
    r"(?:\s+suspected\s+\w[\w\s]{0,30})?\s*clinic\b|"
    r"\battended (?:fast.?track|2WW|TWW)\b.{0,40}clinic\b|"
    r"\breviewed in (?:fast.?track|2WW|TWW|two.week.wait)\b.{0,40}clinic\b|"
    r"\bseen in 2WW\b",
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
    # DI-LEO-AI-145: SNOMED 308467007 "Patient seen by specialist" is the
    # closest standard concept for a first fast-track/2WW clinic attendance.
    "first_seen": {
        "concept_id": 308467007,
        "concept_name": "Text: first seen at fast-track/2WW clinic",
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
    # DI-LEO-AI-204 (Pattern G): SNOMED 182888003 "Patient unable to
    # comply with treatment" -- closest standard concept for a care-
    # obstruction event (DNA due to mobility, refusal of pathway
    # investigation, hospital-cancelled referral, safeguarding block).
    "care_obstruction": {
        "concept_id": 182888003,
        "concept_name": "Text: care obstruction or pathway block",
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

    first_presentation anchors are NOT detected via text search -- symptom and
    sign detection requires the coded SNOMED path (via surface forms in the
    terminology server) to handle assertion and negation correctly.
    """
    referrals: list[dict[str, Any]] = []
    diagnoses: list[dict[str, Any]] = []
    treatments: list[dict[str, Any]] = []
    specialists: list[dict[str, Any]] = []
    benign_closures: list[dict[str, Any]] = []
    specialist_letters: list[dict[str, Any]] = []
    first_presentations: list[dict[str, Any]] = []
    first_seens: list[dict[str, Any]] = []  # DI-LEO-AI-145
    care_obstructions: list[dict[str, Any]] = []  # DI-LEO-AI-204 (Pattern G)

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
        # DI-LEO-AI-155: derive a canonical NCDA cancer-site key from the
        # encounter free text using the gold-mined dictionary, and stash
        # it on every anchor produced from this row. Downstream
        # _extract_condition_key_from_anchor prefers this over the
        # generic "Text: ..." sentinel concept_name.
        _site_match = match_cancer_site(text)
        if _site_match is not None:
            base["site_key"] = _site_match[0]
            base["site_hits"] = _site_match[1]

        has_cancer = bool(_RE_CANCER_TERM.search(text))
        has_confirmed = bool(_RE_CONFIRMED_CANCER.search(text))
        has_definitive_benign = bool(_RE_DEFINITIVE_BENIGN.search(text))
        has_generic_benign_phrase = bool(_RE_GENERIC_BENIGN_PHRASE.search(text))
        has_no_cancer = has_definitive_benign or has_generic_benign_phrase

        # DI-LEO-AI-171: history-of-cancer guard. A problem line that
        # encodes "personal history of cancer" must NOT fire a fresh
        # diagnosis anchor, even if other malignancy patterns are
        # present in the same encounter text.
        _is_history = text_contains_history_of_cancer(text)

        # DI-LEO-AI-159: problem-list Read/CTV3 code recognition
        # DI-LEO-AI-171: free-text malignancy term + active-care code
        _malignancy_hit = find_malignancy_code(text) if not _is_history else None
        # DI-LEO-AI-215 (Pattern K): the strict "code on a Major:/
        # Problem: line" variant. Used as the safe override gate for
        # the same-encounter referral suppression. Free-prose code
        # mentions ("Considering malignant tumour of breast (X78WM)")
        # MUST NOT override the gate -- only true problem-list
        # additions like "Major: Invasive carcinoma of breast (Ya0ln)
        # - lobular (New Episode)".
        _malignancy_problem_hit = (
            find_malignancy_code_in_problem_line(text) if not _is_history else None
        )
        _malignancy_term_hit = (
            find_malignancy_term_in_problem_line(text) if not _is_history else None
        )
        _active_care_hit = (
            find_active_cancer_care_code(text) if not _is_history else None
        )
        _benign_code_hit = find_benign_explanation_code(text)
        _benign_phrase_hit = match_benign_investigation_phrase(text)
        _ftr_hit = find_fast_track_referral_site(text)
        _spec_clinic_hit = find_specialist_clinic_site(text)
        # DI-LEO-AI-175: treatment procedure code recognition
        # (7G055 wide excision, X90PX biopsy action) - the existing
        # _RE_TREATMENT path will OR with this below.
        _treatment_proc_hit = find_cancer_treatment_procedure_code(text)
        # DI-LEO-AI-177: cancer follow-up template recogniser. The
        # history-of-cancer guard is applied inside the helper.
        _follow_up_hit = find_cancer_follow_up_phrase(text)

        # DI-LEO-AI-172: adjuvant cancer-therapy inference. A drug hit
        # only counts as a diagnosis signal when EITHER the prescription
        # is being newly issued OR the encounter co-mentions an active-
        # cancer-care code or malignancy term. This avoids firing on
        # routine repeat-prescription reviews.
        _drug_hit = find_adjuvant_therapy_drug(text) if not _is_history else None
        _drug_supports_diagnosis = False
        if _drug_hit is not None:
            if (
                adjuvant_therapy_is_newly_issued(text)
                or _active_care_hit is not None
                or _malignancy_term_hit is not None
                or _malignancy_hit is not None
            ):
                _drug_supports_diagnosis = True

        if (
            _malignancy_hit is not None
            or _malignancy_term_hit is not None
            or _active_care_hit is not None
            or _drug_supports_diagnosis
            or _follow_up_hit is not None
        ):
            has_cancer = True
            has_confirmed = True

        # DI-LEO-AI-178: benign-investigation phrase scope guard.
        # Read-code hits always count. Phrase hits are gated when the
        # phrase label is in BENIGN_PHRASE_REQUIRES_CANCER_CONTEXT
        # (broad phrases like "no further action", "discharged from
        # care", "discharged from clinic"). For those labels we
        # require the encounter to ALSO carry cancer-pathway context
        # (cancer / 2WW / fast track regex hit OR a derived cancer
        # site_key OR a benign Read-code hit) before firing
        # has_no_cancer. This prevents the day-17 closure bug where
        # an unrelated CKD note containing "no further action"
        # silently closed a parallel skin-cancer episode (R-LEO-AI-173).
        # NOTE: _site_match is deliberately NOT part of the gate.
        # match_cancer_site() uses a gold-mined dictionary that
        # includes incidental terms such as "chronic kidney disease
        # stage 3" (renal site). Trusting it here would re-open the
        # day-17 closure bug (R-LEO-AI-173). Only the strict
        # cancer-pathway regex or a co-occurring benign Read code
        # satisfy the gate.
        _phrase_should_count = False
        if _benign_phrase_hit is not None:
            if _benign_phrase_hit not in BENIGN_PHRASE_REQUIRES_CANCER_CONTEXT:
                _phrase_should_count = True
            elif _benign_code_hit is not None or text_has_cancer_pathway_context(text):
                _phrase_should_count = True
        if _benign_code_hit is not None or _phrase_should_count:
            has_no_cancer = True

        # Site reconciliation -- prefer the most explicit signal.
        # Order: 2WW Read code > malignancy code > malignancy term >
        # adjuvant drug > existing surface-form match.
        if _ftr_hit is not None:
            base["site_key"] = _ftr_hit[1]
            base["site_hits"] = [_ftr_hit[0]]
            base["site_source"] = "explicit_2ww_code"
        elif _malignancy_hit is not None and "site_key" not in base:
            base["site_key"] = _malignancy_hit[1]
            base["site_hits"] = [_malignancy_hit[0]]
            base["site_source"] = "explicit_malignancy_code"
        elif _malignancy_term_hit is not None and "site_key" not in base:
            base["site_key"] = _malignancy_term_hit[1]
            base["site_hits"] = [_malignancy_term_hit[0]]
            base["site_source"] = "malignancy_term_problem_line"
        elif (
            _drug_supports_diagnosis
            and _drug_hit is not None
            and _drug_hit[1] != "non_site_specific"
            and "site_key" not in base
        ):
            base["site_key"] = _drug_hit[1]
            base["site_hits"] = [_drug_hit[0]]
            base["site_source"] = "adjuvant_therapy_drug"
        elif (
            _follow_up_hit is not None
            and _follow_up_hit[1] not in ("non_site_specific", "")
            and "site_key" not in base
        ):
            base["site_key"] = _follow_up_hit[1]
            base["site_hits"] = [_follow_up_hit[0]]
            base["site_source"] = "cancer_follow_up_template"

        if is_letter_transfer:
            s = _TEXT_SENTINEL["specialist_outcome_letter"]
            specialist_letters.append({**base, **s})

        # Referral (DI-LEO-AI-124: PRISM primacy over generic fast-track text)
        # DI-LEO-AI-145: first_seen takes priority over generic fast-track so
        # "Seen in fast track clinic" notes are not mis-labelled as referrals.
        # DI-LEO-AI-182: rejection / marked-in-error / resubmission audit
        # events take HIGHEST priority -- the encounter is about a referral
        # but represents a workflow status change, not a fresh referral.
        # This avoids double-counting a 6-day-delayed pathway as two
        # separate referrals.
        # DI-LEO-AI-195: PRISM cancer-context guard -- a PRISM proforma is
        # only a cancer 2WW when the surrounding text carries an explicit
        # 2WW / suspected-cancer / fast-track signal. Other PRISM templates
        # (sexual health, MSK, IBD, cardiology, mental-health crisis, etc.)
        # must NOT open a 2WW cancer pathway.
        is_first_seen_note = bool(_RE_FIRST_SEEN.search(text))
        is_prism_cancer = bool(
            _RE_REFERRAL_PRISM.search(text) and _RE_PRISM_CANCER_CONTEXT.search(text)
        )
        # DI-LEO-AI-195: "Marked in Error: Amended data" / "amendment" are
        # administrative QOF / data-quality corrections to a referral row,
        # NOT clinical rejections. Only treat marked-in-error as a
        # rejection-equivalent event when no "amended data" / "amendment"
        # qualifier is present.
        _mie_match = _RE_REFERRAL_MARKED_IN_ERROR.search(text)
        _is_admin_amendment = bool(
            _mie_match
            and re.search(
                r"\b(?:amended\s+data|amendment|data\s+amendment|"
                r"reason\s*[:\-]?\s*amended)\b",
                text,
                re.IGNORECASE,
            )
        )
        is_referral_rejected = bool(
            _RE_REFERRAL_REJECTED.search(text)
            or (_mie_match and not _is_admin_amendment)
        )
        is_referral_resubmitted = bool(_RE_REFERRAL_RESUBMITTED.search(text)) and (
            _RE_REFERRAL.search(text) is not None or is_prism_cancer
        )
        if is_referral_rejected:
            s = _TEXT_SENTINEL["referral"]
            referrals.append(
                {
                    **base,
                    **s,
                    "referral_subtype": "rejected",
                    "confidence": 0.9,
                }
            )
        elif is_referral_resubmitted:
            s = _TEXT_SENTINEL["referral"]
            referrals.append(
                {
                    **base,
                    **s,
                    "referral_subtype": "resubmitted",
                    "confidence": 0.85,
                }
            )
        elif is_prism_cancer:
            s = _TEXT_SENTINEL["referral"]
            referrals.append(
                {
                    **base,
                    **s,
                    "referral_subtype": "prism",
                    "confidence": 0.9,
                }
            )
        elif _RE_REFERRAL.search(text) and not is_first_seen_note:
            # DI-LEO-AI-201 (Pattern C+D): suppress text_generic referral
            # when the encounter only NARRATES past pathway activity.
            # DI-LEO-AI-210 (Pattern H): suppress when the only cancer/
            # referral context is family-history (FH prostate ca, etc.).
            # DI-LEO-AI-211 (Pattern I): suppress when the only referral
            # text is conditional boilerplate guidance from an auto-
            # filed lab report.
            # DI-LEO-AI-220 (Pattern N3): suppress when the encounter is
            # a structured form-field restatement of a past event
            # (e.g. "Date of First outpatient appointment: 07 Apr
            # 2025" entered on 13 May 2025).
            # In every case EXCEPT N3, real STRUCTURAL evidence
            # (PRISM/Outbound/Read code/Choose-and-book/Hospital row/
            # "Refer via 2WW") overrides the suppression -- a real
            # referral was issued. N3 overrides even structural codes
            # because a label of the shape "Field: ... <past date>"
            # is by definition a restatement, not a fresh event.
            _has_structural = bool(_RE_STRUCTURAL_REFERRAL.search(text))
            _has_narrative = bool(_RE_NARRATIVE_REFERRAL_REFERENCE.search(text))
            _has_fh = bool(_RE_FAMILY_HISTORY_CANCER.search(text))
            _is_auto_filed = bool(_RE_AUTO_FILED_PREFIX.search(text))
            _has_boilerplate = bool(_RE_BOILERPLATE_REFERRAL_GUIDANCE.search(text))
            _is_form_restatement = encounter_restates_past_event(text, date)
            _suppress = (
                (_has_narrative and not _has_structural)
                or (_has_fh and not _has_structural)
                or (_is_auto_filed and not _has_structural)
                or (_has_boilerplate and not _has_structural)
                or _is_form_restatement
            )
            if _suppress:
                pass  # suppressed: not a real referral event
            else:
                s = _TEXT_SENTINEL["referral"]
                referrals.append(
                    {
                        **base,
                        **s,
                        "referral_subtype": "text_generic",
                    }
                )

        # Diagnosis -- cancer
        # DI-LEO-AI-145: skip if encounter is also a referral; "Fast track
        # referral for suspected X" contains cancer terms but represents
        # a suspected case only -- confirmed diagnosis comes later.
        # DI-LEO-AI-182: rejection/resubmission encounters are also
        # referral-class events; they must not emit benign or diagnosis.
        # DI-LEO-AI-215 (Pattern K): a hard problem-list diagnosis
        # signal -- a malignancy Read code (Ya0ln, X78WM, B-family),
        # a malignancy term inside a "Major:/Problem:" line, or an
        # active-cancer-care Read code -- represents an EMIS problem-
        # list ADDITION ("Major: Invasive carcinoma of breast (Ya0ln)
        # - lobular (New Episode)") and is the strongest possible
        # confirmed-diagnosis signal. It MUST fire diagnosis_confirmed
        # even on an encounter that ALSO carries the same-day 2WW
        # referral row, because GPs routinely add the working
        # diagnosis to the problem list at the same time they issue
        # the fast-track referral. Soft signals (adjuvant drug only,
        # follow-up template only, surface-form cancer mention only)
        # still respect the referral gate to avoid the original
        # DI-LEO-AI-145 trap.
        _is_referral_enc = bool(
            is_referral_rejected
            or is_referral_resubmitted
            or is_prism_cancer
            or (_RE_REFERRAL.search(text) and not is_first_seen_note)
        )
        _has_hard_dx_evidence = (
            _malignancy_problem_hit is not None
            or _malignancy_term_hit is not None
            or _active_care_hit is not None
        )
        _dx_referral_blocked = _is_referral_enc and not _has_hard_dx_evidence
        # DI-LEO-AI-402 (Pattern N4): cancer-care-review restatement
        # guard. When the encounter is a cancer-care-review template
        # restating known history (the literal "Cancer care review"
        # marker, OR the N1 known-cancer narrative shapes such as
        # "known X cancer", "post mastectomy recovery review", "PMHx
        # X carcinoma", "referred by me on 2ww earlier this year,
        # confirmed X cancer") AND the encounter carries no fresh-
        # diagnosis marker ("(New Episode)", "newly diagnosed", etc.),
        # SUPPRESS the diagnosis_confirmed emission entirely. The
        # active_cancer_care_code / problem_list_code / follow-up-
        # template hits on these encounters are the GP keeping the
        # problem list current, not a new diagnosis.
        _dx_cancer_review_blocked = encounter_is_cancer_care_review_restatement(
            text
        )
        if (
            has_cancer
            and has_confirmed
            and not has_no_cancer
            and not _dx_referral_blocked
            and not _dx_cancer_review_blocked
        ):
            s = _TEXT_SENTINEL["diagnosis_cancer"]
            extra: dict[str, Any] = {}
            if _malignancy_hit is not None:
                extra["diagnosis_source"] = "problem_list_code"
                extra["diagnosis_code"] = _malignancy_hit[0]
                extra["confidence"] = 0.9
            elif _malignancy_term_hit is not None:
                extra["diagnosis_source"] = "malignancy_term_problem_line"
                extra["diagnosis_term"] = _malignancy_term_hit[0]
                extra["confidence"] = 0.85
                extra["hitl_required"] = True
            elif _active_care_hit is not None:
                extra["diagnosis_source"] = "active_cancer_care_code"
                extra["diagnosis_code"] = _active_care_hit
                extra["confidence"] = 0.85
                extra["hitl_required"] = True
            elif _drug_supports_diagnosis and _drug_hit is not None:
                extra["diagnosis_source"] = "adjuvant_therapy_drug"
                extra["diagnosis_drug"] = _drug_hit[0]
                extra["diagnosis_drug_indication"] = _drug_hit[2]
                extra["confidence"] = 0.75
                extra["hitl_required"] = True
            elif _follow_up_hit is not None:
                # DI-LEO-AI-177: cancer follow-up template recogniser.
                extra["diagnosis_source"] = "cancer_follow_up_template"
                extra["diagnosis_term"] = _follow_up_hit[0]
                extra["confidence"] = 0.8
                extra["hitl_required"] = True
                if "site_key" not in base and _follow_up_hit[1]:
                    base["site_key"] = _follow_up_hit[1]
                    base["site_hits"] = [_follow_up_hit[0]]
                    base["site_source"] = "cancer_follow_up_template"
            # DI-LEO-AI-401 (Pattern N1): tag the diagnosis anchor when
            # the encounter body is a sick note or a "known X cancer"
            # narrative restatement. The episode builder uses this flag
            # to reject floating diagnosis-led EpisodeOfCare groups
            # whose anchors are ALL narrative restatements.
            if encounter_diagnosis_is_narrative_restatement(text):
                extra["is_narrative_restatement"] = True
            diagnoses.append({**base, **s, **extra})

        # Benign closure -- also guarded from referral encounters
        # (DI-LEO-AI-145).
        #
        # DI-LEO-AI-178: do NOT emit a benign_closure when the only
        # signal is a broad disposition phrase ("discharged from clinic",
        # "no further action", "discharge back to GP" etc.) firing in an
        # encounter with no cancer-pathway context. We split signals
        # into definitive benign findings (inherently benign histology
        # such as "lipoma", "fibroadenoma", "no malignant cells",
        # "unremarkable histology") and generic disposition phrases.
        # Definitive findings are always sufficient. Generic phrases
        # require ONE of:
        #   - a concrete benign Read code hit, OR
        #   - a benign-investigation-phrase hit that passes the gate, OR
        #   - cancer-pathway context in the same encounter.
        _generic_benign_with_context = has_generic_benign_phrase and (
            text_has_cancer_pathway_context(text)
            or _benign_code_hit is not None
            or (_benign_phrase_hit is not None and _phrase_should_count)
        )
        _emit_benign = (
            has_definitive_benign
            or _benign_code_hit is not None
            or (_benign_phrase_hit is not None and _phrase_should_count)
            or _generic_benign_with_context
        )
        if _emit_benign and not _is_referral_enc:
            s = _TEXT_SENTINEL["diagnosis_benign"]
            extra = {"is_pathway_completion": True}
            if _benign_code_hit is not None:
                extra["benign_source"] = "problem_list_code"
                extra["benign_code"] = _benign_code_hit
                extra["confidence"] = 0.85
            elif _benign_phrase_hit is not None and _phrase_should_count:
                extra["benign_source"] = "investigation_phrase"
                extra["benign_phrase"] = _benign_phrase_hit
                extra["confidence"] = 0.8
            elif has_definitive_benign:
                extra["benign_source"] = "definitive_benign_finding"
                extra["confidence"] = 0.8
            else:
                extra["benign_source"] = "no_cancer_phrase_in_context"
                extra["confidence"] = 0.7
            benign_closures.append({**base, **s, **extra})

        # Specialist visit
        if _RE_SPECIALIST.search(text):
            s = _TEXT_SENTINEL["specialist"]
            specialists.append({**base, **s})

        # DI-LEO-AI-145: first_seen -- clinic attendance AFTER referral.
        # Detected separately from referral to avoid milestone confusion.
        # Takes priority over generic fast-track referral (guarded above).
        # DI-LEO-AI-175: an explicit specialist clinic Read code
        # (e.g. XaPyd "Seen in fast track suspected skin cancer
        # clinic") is also a first_seen signal even without the
        # surface-form _RE_FIRST_SEEN match.
        if is_first_seen_note or _spec_clinic_hit is not None:
            # DI-LEO-AI-220 (Pattern N3): structured-form-field
            # restatement guard. When the encounter body contains a
            # form-field line of the shape "Field: ... <embedded date>"
            # whose embedded date is >= 14 days BEFORE the encounter
            # date (e.g. "Seen in 2WW Clinic?: Seen in fast track
            # suspected breast cancer clinic (XaPyQ) 28 Apr 2025"
            # entered on 10 Jun 2025), the encounter is restating the
            # earlier first_seen event -- the real first_seen will
            # already have fired from the source encounter. Suppress
            # the duplicate.
            if not encounter_restates_past_event(text, date):
                s = _TEXT_SENTINEL["first_seen"]
                fs_extra: dict[str, Any] = {"confidence": 0.85}
                if _spec_clinic_hit is not None:
                    fs_extra["first_seen_source"] = "specialist_clinic_code"
                    fs_extra["first_seen_code"] = _spec_clinic_hit[0]
                    if "site_key" not in base:
                        base["site_key"] = _spec_clinic_hit[1]
                        base["site_hits"] = [_spec_clinic_hit[0]]
                        base["site_source"] = "specialist_clinic_code"
                first_seens.append({**base, **s, **fs_extra})

        # Treatment - includes free-text patterns AND
        # CANCER_TREATMENT_PROCEDURE_CODES (DI-LEO-AI-175 - 7G055
        # wide excision, X90PX biopsy action).
        if _RE_TREATMENT.search(text) or _treatment_proc_hit is not None:
            s = _TEXT_SENTINEL["treatment"]
            treatment_extra: dict[str, Any] = {}
            if _treatment_proc_hit is not None:
                treatment_extra["treatment_source"] = "procedure_code"
                treatment_extra["treatment_code"] = _treatment_proc_hit
            treatments.append({**base, **s, **treatment_extra})

        # DI-LEO-AI-204 (Pattern G): care_obstruction signals.
        # Independent of other milestones -- an encounter can be both a
        # rejection (workflow) and a care_obstruction (clinical refusal
        # / safeguarding). Emitted whenever the regex hits, regardless
        # of referral / diagnosis classification.
        # DI-LEO-AI-219 (Pattern N5): off-pathway non-cancer Problem-
        # header guard. When the encounter's Problem header is
        # unambiguously non-cancer (foreign travel, vaccination, repeat
        # prescription, sick note, etc.) and the body's cancer mention
        # is incidental, do NOT emit care_obstruction even if the
        # regex hits. Closes the Pattern N5 travel-vaccine exemplar 2025-07-01 MMR /
        # Mexico travel-vaccine misfire.
        if _RE_CARE_OBSTRUCTION.search(text) and not encounter_problem_is_off_pathway(
            text
        ):
            s = _TEXT_SENTINEL["care_obstruction"]
            care_obstructions.append(
                {
                    **base,
                    **s,
                    "obstruction_source": "text_pattern",
                    "confidence": 0.7,
                    "hitl_required": True,
                }
            )

    return (
        _dedupe_by_encounter(referrals),
        _dedupe_by_encounter(diagnoses),
        _dedupe_by_encounter(treatments),
        _dedupe_by_encounter(specialists),
        _dedupe_by_encounter(benign_closures),
        _dedupe_by_encounter(specialist_letters),
        first_presentations,  # always empty -- coded path only
        _dedupe_by_encounter(first_seens),  # DI-LEO-AI-145
        _dedupe_by_encounter(care_obstructions),  # DI-LEO-AI-204
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
        first_presentations,
        _coded_first_seens,  # always empty from coded path; DI-LEO-AI-145
        _coded_care_obstructions,  # always empty from coded path; DI-LEO-AI-204
    ) = _classify_anchor_rows(coded_rows, buckets, pathway_completion_ids)
    # DI-LEO-AI-145: coded path does not produce first_seen anchors; they
    # come exclusively from text search.  Initialise empty here so the
    # merge block below is uniform.
    first_seens: list[dict[str, Any]] = []
    care_obstructions: list[dict[str, Any]] = []  # DI-LEO-AI-204
    construct_map = _build_construct_anchor_map(coded_rows, registry)
    referrals = _merge_anchor_lists(referrals, construct_map.get("referral", []))
    diagnoses = _merge_anchor_lists(diagnoses, construct_map.get("diagnosis", []))
    treatments = _merge_anchor_lists(
        treatments, construct_map.get("treatment_start", [])
    )
    specialists = _merge_anchor_lists(
        specialists, construct_map.get("specialist_visit", [])
    )
    benign_closures = _merge_anchor_lists(
        benign_closures, construct_map.get("benign_closure", [])
    )
    specialist_letters = _merge_anchor_lists(
        specialist_letters, construct_map.get("specialist_outcome_letter", [])
    )
    first_presentations = _merge_anchor_lists(
        first_presentations, construct_map.get("first_presentation", [])
    )

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
            _t_fp,  # always empty; first_presentation is coded-path only
            t_first_seens,  # DI-LEO-AI-145
            t_care_obstructions,  # DI-LEO-AI-204 (Pattern G)
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
        seen_enc = {r["encounter_id"] for r in first_seens}
        first_seens += [r for r in t_first_seens if r["encounter_id"] not in seen_enc]
        seen_enc = {r["encounter_id"] for r in care_obstructions}
        care_obstructions += [
            r for r in t_care_obstructions if r["encounter_id"] not in seen_enc
        ]

    # DI-LEO-AI-145: An encounter coded with BOTH a referral procedure AND a
    # cancer finding was produced by the PRISM workflow: "Fast track referral
    # for suspected X cancer".  The cancer concept is SUSPECTED, not confirmed.
    # Allowing the same encounter to be both a referral anchor and a
    # diagnosis/benign-closure anchor would fire diagnosis_confirmed on the
    # GP referral day -- weeks before the histology letter arrives.
    # Rule: referral encounter IDs are excluded from diagnoses and benign_closures.
    _referral_enc_ids: set[str] = {str(r.get("encounter_id") or "") for r in referrals}
    diagnoses = [
        d
        for d in diagnoses
        if str(d.get("encounter_id") or "") not in _referral_enc_ids
    ]
    benign_closures = [
        b
        for b in benign_closures
        if str(b.get("encounter_id") or "") not in _referral_enc_ids
    ]

    has_anchors = any(
        (
            referrals,
            diagnoses,
            treatments,
            specialists,
            benign_closures,
            specialist_letters,
            first_presentations,
            first_seens,
            care_obstructions,
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
        first_presentation_anchors=_dedupe_first_presentation(first_presentations),
        first_seen_anchors=_dedupe_by_encounter(first_seens),  # DI-LEO-AI-145
        care_obstruction_anchors=_dedupe_by_encounter(care_obstructions),
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
