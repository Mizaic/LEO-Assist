"""Stage 1 deterministic audit checks for reviewed-episode milestones.

Pure functions that take parsed graph rows and emit
:class:`libs.data.ncda_label_audit.AuditFinding` rows. No I/O.

The orchestrating script lives in scripts/ncda/audit_reviewed_episodes.py.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

from libs.data.ncda_label_audit import AuditFinding, FindingType, Severity
from libs.domains.read_code_ncda_lookup import (
    READ_CODE_TO_NCDA_ROLE,
    NcdaRole,
    lookup_read_code,
)

# (XYZ) - GP Read codes, drug names, and free-text tokens are all matched.
# Curation is deferred to lookup_read_code() (which handles drugs and junk).
_READ_CODE_RE = re.compile(r"\(([A-Za-z0-9.]+)\)")

# Plain-text patterns supporting each role when no curated Read code is present.
#
# Screening programme pathways — equivalent to GP 2WW for NCDA purposes.
# NOTE: "NHS Breast Screening" alone is too broad — it also appears on
# NORMAL mammogram letters.  Breast screening FTRs are instead detected
# via Read code 68621 (Breast neoplasm screening abnormal) in the lookup.
#
# An earlier version included the bare phrase "Bowel Cancer Screening" here on
# the assumption it only appeared on positive-FIT referrals.  In practice that
# phrase is a generic admin string used for every routine screening invitation
# routed through the GP, including post-treatment surveillance for already-
# diagnosed bowel-cancer patients.  This created phantom FTR anchors that
# spawned duplicate cohort-1a episodes after the real diagnosis (see patient
# 6243439488).  Genuine positive-screen referrals are still captured via:
#   - Read code (XaPVj) "Bowel cancer screening FOBT positive result letter"
#     (in libs/domains/read_code_ncda_lookup.py)
#   - The explicit "FIT Positive" / "FOBT Abnormal" phrases below.
_FTR_PHRASES = re.compile(
    r"\b(2WW|2 ?week ?wait|fast.track|FTS|USC|urgent suspected cancer"
    r"|PRISM 2WW|fast.?track referral|two.?week.?wait"
    r"|FOBT Abnormal|FIT Positive)\b",
    re.IGNORECASE,
)
_SEEN_PHRASES = re.compile(
    r"\b(seen in|specialist clinic|outpatient (?:clinic|appt)"
    r"|attended.*(?:clinic|consultant|appointment)"
    r"|review in clinic"
    # EMIS "Patient Attended - Outcome" template field — literal marker
    # used by UHL Dermatology / Urology / Breast clinics for any OPD
    # attendance (consultation, dermoscopy, lesion examination).
    r"|Patient\s+Attended\s*-\s*Outcome"
    # "Skin Cancer Follow Up" / "<Site> Cancer Follow Up" template fields
    # are post-attendance follow-up visits.
    r"|(?:skin|breast|lung|urolog|prostate|colorectal|gynae|ENT|head\s+and\s+neck)"
    r"\s+cancer\s+follow[-\s]?up"
    # Specialist clinic letter back to a GP practice ("Dermatology to
    # Woodbrook Medical Centre", "Urology to Whitehill Surgery").  These
    # are letters from a specialist clinic informing the GP that the
    # patient was seen.  Cancer-specialty list is deliberately narrow so
    # cardiology / physio / pharmacy / etc. letters do NOT spuriously
    # anchor a `seen` milestone for a cancer pathway.
    r"|(?:dermatology|urology|breast(?:\s+clinic)?|colorectal"
    r"|gastroenterolog\w*|gynaecolog\w*|haematolog\w*|oncolog\w*|ENT"
    r"|head\s+(?:and|&)\s+neck|respiratory)\s+to\s+"
    r"[A-Z][\w&'.-]+(?:\s+[A-Z][\w&'.-]+){0,5}?\s+"
    r"(?:Medical\s+Centre|Surgery|Health\s+Centre|Practice|Hospital|Clinic)"
    r")\b",
    # NOTE: "clinic letter" intentionally removed — it matched GP letters from
    # any clinic (flu vaccine, physiotherapy, cardiology) not just cancer
    # specialist appointments, causing false Seen-In anchors that pushed the
    # Dx selection window to after the actual Dx date.
    re.IGNORECASE,
)
_DX_FOUND_PHRASES = re.compile(
    r"\b(malignant|carcinoma|adenocarcinoma|lymphoma|melanoma"
    r"|sarcoma|tumour confirmed|new (?:cancer )?diagnosis"
    r"|MDT outcome.*malignant|histology.*malignant)\b",
    re.IGNORECASE,
)
# EMIS-specific pattern for a NEW cancer diagnosis being added to the problem
# list: "Major: [cancer term] (Code) (New Episode)".  This is the clearest
# possible EMIS signal that a new cancer diagnosis has just been recorded,
# distinct from "Problem: [cancer term]" which just recalls an existing entry.
_EMIS_MAJOR_DX = re.compile(
    r"^Major:\s+(?:malignant|carcinoma|adenocarcinoma|lymphoma|melanoma"
    r"|sarcoma|mesothelioma)\b",
    re.IGNORECASE | re.MULTILINE,
)
# Context tokens that, when present near "all clear", confirm the phrase is
# describing a cancer / pathway / imaging outcome rather than a generic
# safety-net plan.  Without this guard a cardiology oncall note such as
# "advised if all clear, obs stable to continue Bumetanide" would match
# "all clear" and be promoted to dx/cancer_excluded — which is what spawned
# the phantom prostate-pathway closure on patient 6040304227.
_CANCER_CTX_NEAR_ALL_CLEAR = (
    r"cancer|malignan|2WW|pathway|MDT|biopsy|specimen|histology|imaging"
    r"|scan|MRI|CT|USS|ultrasound|colonoscop|endoscop|gastroscop|cystoscop"
    r"|bronchoscop|hysteroscop|colposcop|mammogram|breast|FIT|FOBT"
    r"|x[-\s]?ray|cxr|melanoma|tumou?r|metasta|lesion|nodule|mass"
)
_DX_EXCLUDED_PHRASES = re.compile(
    r"\b(no malignancy|benign|cancer ruled out|cancer excluded"
    r"|d/?c (from|after).*(2WW|pathway|clinic)"
    r"|discharged from (clinic|cancer|2WW|pathway)"
    r"|reassur(ed|ance).*no malignancy|no evidence of (cancer|malignancy)"
    r"|dysplastic naevus|atypical naevus|compound naevus|melanocytic naevi)\b"
    # "all clear" — only when a cancer / imaging / pathway context word
    # appears within ~80 chars on either side of the phrase.
    r"|(?:\b(?:" + _CANCER_CTX_NEAR_ALL_CLEAR + r")\b[\s\S]{0,80}\ball clear\b"
    r"|\ball clear\b[\s\S]{0,80}\b(?:" + _CANCER_CTX_NEAR_ALL_CLEAR + r")\b)",
    re.IGNORECASE,
)
_TREATMENT_PHRASES = re.compile(
    r"\b(chemotherapy|radiotherapy|brachytherapy|mastectomy|prostatectomy"
    r"|lumpectomy|cystectomy|colectomy|hysterectomy|oesophagectomy|nephrectomy"
    r"|orchidectomy|thyroidectomy|chemo administration|first cycle|cycle 1"
    r"|started chemo|radiation oncology|targeted therapy|immunotherapy"
    r"|hormone therapy)\b",
    re.IGNORECASE,
)

# v2 milestones canonicalise to one NCDA role for the role_mismatch check.
_V2_MILESTONE_TO_ROLE: dict[str, NcdaRole] = {
    "referral": "ftr",
    "referral_sent": "ftr",
    "first_seen": "seen",
    "diagnosis_confirmed": "dx",
    "treatment_started": "treatment",
    "benign_closure": "dx",  # consolidated to dx in Stage 2 with cancer_excluded
    "outcome_letter": "dx",  # consolidated to dx if carrying diagnosis content
}


def extract_read_codes(text: str) -> list[str]:
    """Return GP Read code tokens found in encounter text via (XYZ) regex."""
    if not text:
        return []
    return _READ_CODE_RE.findall(text)


def text_supports_role(text: str, role: NcdaRole) -> bool:
    """Return True when encounter text contains role-supporting phrases."""
    if not text:
        return False
    if role == "ftr":
        return bool(_FTR_PHRASES.search(text))
    if role == "seen":
        return bool(_SEEN_PHRASES.search(text))
    if role == "dx":
        # EMIS "Major: [cancer] (New Episode)" is a definitive new-diagnosis signal
        # and is checked first so it is not confused with "Problem: [cancer]" lines
        # (which just recall an existing condition) or generic keyword hits.
        return (
            bool(_EMIS_MAJOR_DX.search(text))
            or bool(_DX_FOUND_PHRASES.search(text))
            or bool(_DX_EXCLUDED_PHRASES.search(text))
        )
    if role == "treatment":
        return bool(_TREATMENT_PHRASES.search(text))
    return False


def read_codes_support_role(text: str, role: NcdaRole) -> bool:
    """Return True when any GP Read code in text maps to the requested role."""
    for token in extract_read_codes(text):
        result = lookup_read_code(token)
        if result is None:
            continue
        if result[0] == role:
            return True
    return False


# ---------------------------------------------------------------------------
# Helper for back-date awareness (Encounter.flags carries the entry date).
# ---------------------------------------------------------------------------
_BACK_DATE_RE = re.compile(
    r"back-?dated.*?on:?\s*(\d{1,2}\s+\w+\s+\d{4})|"
    r"entered on:?\s*(\d{1,2}\s+\w+\s+\d{4})",
    re.IGNORECASE,
)


def parse_entry_date(flags: str | None) -> str | None:
    """Extract the entry/back-date from flags. Returns ISO date or None."""
    if not flags:
        return None
    m = _BACK_DATE_RE.search(flags)
    if not m:
        return None
    raw = m.group(1) or m.group(2)
    if not raw:
        return None
    for fmt in ("%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Audit rules. Each takes a small structured input and emits AuditFinding[s].
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MilestonedEncounter:
    """A reviewed encounter row carrying its current milestone."""

    patient_id: str
    episode_id: str | None
    encounter_id: str
    milestone_type: str
    encounter_date: str | None
    text: str | None
    flags: str | None


def find_role_mismatches(
    encounters: Iterable[MilestonedEncounter],
) -> list[AuditFinding]:
    """Flag encounters whose milestone_type lacks both Read-code and phrase support."""
    findings: list[AuditFinding] = []
    for enc in encounters:
        canonical_role = _V2_MILESTONE_TO_ROLE.get(enc.milestone_type)
        if canonical_role is None:
            continue
        if read_codes_support_role(enc.text or "", canonical_role):
            continue
        if text_supports_role(enc.text or "", canonical_role):
            continue
        findings.append(_role_mismatch_finding(enc, canonical_role))
    return findings


def _role_mismatch_finding(
    enc: MilestonedEncounter, expected_role: NcdaRole
) -> AuditFinding:
    quote = (enc.text or "").strip()[:160]
    return AuditFinding(
        patient_id=enc.patient_id,
        episode_id=enc.episode_id,
        encounter_id=enc.encounter_id,
        finding_type="role_mismatch",
        severity="medium",
        rationale=(
            f"Milestone '{enc.milestone_type}' implies role '{expected_role}', but "
            f"no curated Read code or phrase pattern supports it in this encounter."
        ),
        current_milestone=enc.milestone_type,
        suggested_role=None,
        suggested_outcome=None,
        supporting_quote=quote,
        encounter_date=enc.encounter_date,
        entry_date=parse_entry_date(enc.flags),
    )


_ROLE_ORDER: dict[NcdaRole, int] = {
    "ftr": 0,
    "seen": 1,
    "dx": 2,
    "treatment": 3,
    "none": 4,
}


def find_out_of_sequence(
    encounters: Iterable[MilestonedEncounter],
) -> list[AuditFinding]:
    """Flag anchor pairs that violate FTR <= SEEN <= Dx <= TREATMENT."""
    enc_list = [e for e in encounters if e.encounter_date]
    by_role: dict[NcdaRole, list[MilestonedEncounter]] = {}
    for enc in enc_list:
        role = _V2_MILESTONE_TO_ROLE.get(enc.milestone_type)
        if role is None or role == "none":
            continue
        by_role.setdefault(role, []).append(enc)
    findings: list[AuditFinding] = []
    for role_a, list_a in by_role.items():
        for role_b, list_b in by_role.items():
            if _ROLE_ORDER[role_a] >= _ROLE_ORDER[role_b]:
                continue
            findings.extend(_pair_violations(role_a, role_b, list_a, list_b))
    return findings


def _pair_violations(
    role_a: NcdaRole,
    role_b: NcdaRole,
    list_a: list[MilestonedEncounter],
    list_b: list[MilestonedEncounter],
) -> list[AuditFinding]:
    out: list[AuditFinding] = []
    for enc_a in list_a:
        for enc_b in list_b:
            d_a = _to_date(enc_a.encounter_date)
            d_b = _to_date(enc_b.encounter_date)
            if d_a is None or d_b is None:
                continue
            if d_a <= d_b:
                continue
            out.append(_out_of_sequence_finding(enc_a, role_a, enc_b, role_b, d_a, d_b))
    return out


def _to_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _out_of_sequence_finding(
    enc_a: MilestonedEncounter,
    role_a: NcdaRole,
    enc_b: MilestonedEncounter,
    role_b: NcdaRole,
    d_a: date,
    d_b: date,
) -> AuditFinding:
    return AuditFinding(
        patient_id=enc_a.patient_id,
        episode_id=enc_a.episode_id,
        encounter_id=enc_a.encounter_id,
        finding_type="out_of_sequence",
        severity="high",
        rationale=(
            f"{role_a.upper()} on {d_a.isoformat()} is later than "
            f"{role_b.upper()} on {d_b.isoformat()} (encounter "
            f"{enc_b.encounter_id}); expected {role_a.upper()} <= {role_b.upper()}."
        ),
        current_milestone=enc_a.milestone_type,
        suggested_role=role_a,
        suggested_outcome=None,
        encounter_date=enc_a.encounter_date,
        entry_date=parse_entry_date(enc_a.flags),
    )


def find_duplicate_roles(
    encounters: Iterable[MilestonedEncounter],
) -> list[AuditFinding]:
    """Flag episodes carrying >1 anchor of the same canonical role."""
    role_counts: Counter[NcdaRole] = Counter()
    role_examples: dict[NcdaRole, list[MilestonedEncounter]] = {}
    for enc in encounters:
        role = _V2_MILESTONE_TO_ROLE.get(enc.milestone_type)
        if role is None or role == "none":
            continue
        role_counts[role] += 1
        role_examples.setdefault(role, []).append(enc)
    findings: list[AuditFinding] = []
    for role, count in role_counts.items():
        if count <= 1:
            continue
        for enc in role_examples[role][1:]:  # first one is canonical
            findings.append(_duplicate_role_finding(enc, role, count))
    return findings


def _duplicate_role_finding(
    enc: MilestonedEncounter, role: NcdaRole, count: int
) -> AuditFinding:
    return AuditFinding(
        patient_id=enc.patient_id,
        episode_id=enc.episode_id,
        encounter_id=enc.encounter_id,
        finding_type="multiple_anchors_per_role",
        severity="medium",
        rationale=(
            f"Episode has {count} encounters tagged with role '{role}'. "
            "Reviewer must pick the canonical anchor."
        ),
        current_milestone=enc.milestone_type,
        suggested_role=role,
        encounter_date=enc.encounter_date,
        entry_date=parse_entry_date(enc.flags),
    )
