"""Stage 3 silver-label generation logic.

Atlas trace:
  DO: DO-2C1A2392
  DI: DI-7FF67ECE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C1A2392")

Pure functions plus a pluggable LLM-callback Protocol. The orchestrating
script lives in scripts/ncda/build_silver_labels.py.

Core ideas:
  - LLM-at-curation only - never inference. Replaceable with any callable
    that conforms to LlmRelabelFn.
  - Deterministic fallback labeller (read codes + phrase patterns) is used
    when no LLM is provided; this is also useful for unit tests.
  - Output schema is fixed so the role/linkage classifiers can read it
    directly.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Callable, Iterable, Literal, Protocol

from libs.domains.read_code_ncda_lookup import (
    TREATMENT_DRUG_TOKENS,
    lookup_read_code,
)
from services.analysis_worker.app.ncda_detector.audit_rules import (
    _DX_EXCLUDED_PHRASES,
    _DX_FOUND_PHRASES,
    _EMIS_MAJOR_DX,
    _TREATMENT_PHRASES,
    extract_read_codes,
    text_supports_role,
)
from services.analysis_worker.app.ncda_detector.tidy_rules import (
    _infer_dx_outcome,
    _strip_problem_lines,
)

NcdaRole = Literal["ftr", "seen", "dx", "treatment", "none"]
DxOutcome = Literal["cancer_found", "cancer_excluded"]


@dataclass(frozen=True)
class SilverLabel:
    """One silver-labelled encounter row."""

    patient_id: str
    encounter_id: str
    encounter_date: str | None
    role: NcdaRole
    outcome: DxOutcome | None
    confidence: float
    rationale: str
    supporting_quote: str
    site_hint: str | None
    source: Literal["llm", "deterministic"]


class LlmRelabelFn(Protocol):
    """Callable that takes (text, flags) and returns a structured label."""

    def __call__(
        self, text: str, flags: str | None
    ) -> dict[str, object]:
        ...


def deterministic_label(
    *, patient_id: str, encounter_id: str, encounter_date: str | None,
    text: str, flags: str | None,
) -> SilverLabel:
    """Bootstrap labeller using only Read codes + curated phrases.

    Confidence scores are deliberately conservative (max 0.7) so LLM-driven
    labels can outweigh deterministic ones during training when both exist.

    Exclusion pass runs first: certain encounter structures are definitively
    ``none`` regardless of any 2WW/fast-track text they contain:
      - Auto-filed lab / radiology results (PSA, FIT, CXR, bloods).
      - Type-4 retrospective admin tracking notes ("2WW Clinic?:").
      - Scheduled task creation encounters.
      - Referral triage / rejection admin notes.
    These exclusions prevent the phrase matcher from firing on e.g.
    "refer as a 2WW" in a PSA advisory or "Seen in 2WW Clinic?" in an
    admin tracking note.
    """
    excluded, excl_rationale = _is_excluded_none(text)
    if excluded:
        return SilverLabel(
            patient_id=patient_id,
            encounter_id=encounter_id,
            encounter_date=encounter_date,
            role="none",
            outcome=None,
            confidence=0.85,
            rationale=excl_rationale,
            supporting_quote=(text or "").strip()[:160],
            site_hint=None,
            source="deterministic",
        )

    # PRISM questionnaire check: "- PRISM 2WW [Site] - questionnaire started"
    # is an unambiguous active FTR submission regardless of what other Read
    # codes appear in the questionnaire body text.
    if _PRISM_QUESTIONNAIRE.search(text or ""):
        return SilverLabel(
            patient_id=patient_id,
            encounter_id=encounter_id,
            encounter_date=encounter_date,
            role="ftr",
            outcome=None,
            confidence=0.85,
            rationale="PRISM 2WW questionnaire entry - active FTR submission.",
            supporting_quote=(text or "").strip()[:160],
            site_hint=_extract_site_hint(text),
            source="deterministic",
        )

    # EMIS "Major: <cancer term> (New Episode)" is the strongest possible
    # signal that a NEW cancer diagnosis has just been recorded. It outranks
    # any seen-in / treatment Read codes that might appear earlier in the same
    # composite back-dated encounter (e.g. dermatology UHL bundles where the
    # same Encounter node spans referral, attendance, histology, and excision).
    # Guard: "(New Episode)" MUST be present — "Major: <cancer>" alone appears
    # in routine problem-list recalls (prescriptions, LTC reviews) for EXISTING
    # diagnoses and must not be promoted to a fresh dx/cancer_found.
    if _EMIS_MAJOR_DX.search(text or "") and _EMIS_NEW_EPISODE.search(text or ""):
        return SilverLabel(
            patient_id=patient_id,
            encounter_id=encounter_id,
            encounter_date=encounter_date,
            role="dx",
            outcome="cancer_found",
            confidence=0.85,
            rationale="EMIS 'Major: <cancer> ... (New Episode)' - new diagnosis recorded.",
            supporting_quote=(text or "").strip()[:160],
            site_hint=_extract_site_hint(text),
            source="deterministic",
        )

    role, outcome = _best_role_from_codes(text)
    # Only call the phrase matcher when no codes were found at all (role is None).
    # When codes mapped to "none" are present (role == "none"), that code lookup
    # result is trusted - falling through to phrases would re-fire on incidental
    # 2WW/fast-track text present in many clinical consultations.
    if role is None:
        role, outcome = _best_role_from_phrases(text)
    if role is None:
        role = "none"
    if role == "dx" and outcome is None:
        outcome = _infer_dx_outcome(text or "")
    confidence = 0.7 if role != "none" else 0.5
    quote = (text or "").strip()[:160]
    return SilverLabel(
        patient_id=patient_id,
        encounter_id=encounter_id,
        encounter_date=encounter_date,
        role=role,
        outcome=outcome,
        confidence=confidence,
        rationale="Deterministic Read-code + phrase pattern label.",
        supporting_quote=quote,
        site_hint=_extract_site_hint(text),
        source="deterministic",
    )


_AUTO_FILED_LABS = re.compile(
    r"\bAuto-filed\b",
    re.IGNORECASE,
)
# Strong secondary-care cancer-confirmed signals.  When these appear alongside
# an "Auto-filed" line we should NOT silence the encounter, because we are
# looking at a long composite encounter that contains both an auto-filed lab
# (e.g. vitamin D level) AND a genuine diagnosis/treatment block.
_CANCER_CONFIRMED_SIGNAL = re.compile(
    r"\b("
    r"malignant\s+(?:melanoma|neoplasm|tumou?r|carcinoma|lesion)"
    r"|melanoma\s+(?:in\s+situ|of\s+skin)"
    r"|invasive\s+(?:ductal|lobular)?\s*carcinoma"
    r"|adenocarcinoma|squamous\s+cell\s+carcinoma|basal\s+cell\s+carcinoma"
    r"|histolog(?:y|ical)\s+(?:result|confirms|confirmed|positive|malignant)"
    r"|wide\s+local\s+excision|excision\s+of\s+(?:skin\s+)?(?:lesion|tumou?r|mass)"
    r"|MDT\s+outcome\s+(?:malignant|positive|cancer)"
    r")\b",
    re.IGNORECASE,
)
_ADMIN_TRACKING_2WW = re.compile(
    r"2WW\s+Seen in 2WW Clinic\?",
    re.IGNORECASE,
)
_ADMIN_OPA_DATE = re.compile(
    r"2WW\s+Date of First outpatient appointment:",
    re.IGNORECASE,
)
_SCHEDULED_TASK = re.compile(
    r"Scheduled Task Creation",
    re.IGNORECASE,
)
_TRIAGE_REJECTION = re.compile(
    r"(Referral Rejected|TRIAGE RESPONSE|Choose and book referral rejected"
    r"|Return to referrer with advice)",
    re.IGNORECASE,
)
# EMIS phlebotomy template marker.  These are nurse blood-draw monitoring
# encounters.  EMIS reuses several Read codes inside phlebotomy templates
# (e.g. XE1Sf labelled "Infectious disease: prevention/control") that
# collide with cancer Dx codes in our lookup.  Exclude the whole template.
_PHLEBOTOMY_TEMPLATE = re.compile(
    r"\bPhlebotomy\s+(?:Test|Service)\b",
    re.IGNORECASE,
)
_BENIGN_SKIN_LESION_REFERRAL_ADMIN = re.compile(
    r"\bBenign Skin Lesion PRISM to Unknown\b",
    re.IGNORECASE,
)
_GENETICS_REFERRAL_ADMIN = re.compile(
    r"\bReferral to genetics service\b|\bGenetics Breast Cancer Family History Clinic\b",
    re.IGNORECASE,
)
# DNA / Did-Not-Attend appointment encounters.  These are admin "Patient
# Attended - Outcome / Did not attend clinic (XacSG)" notes or the bare
# "Did not attend hospital appointment (XaF81) (New Episode)" / "Did not
# attend (Xa1kG)" / "Did not attend for Session appointment" patterns.  The
# patient was a no-show, so the encounter is NOT a real first_seen / OPD
# attendance and must be silenced.  Without this guard a DNA dermatology
# slot ends up labelled `seen` and the linker uses it as the first_seen
# milestone for the cancer pathway (see patient 6040304227 melanoma).
_DNA_APPOINTMENT = re.compile(
    r"\bDid\s+not\s+attend\b\s*"
    r"(?:clinic|hospital(?:\s+appointment)?|appointment|for\s+(?:a\s+)?(?:Session|appointment|clinic))?"
    r"(?:\s*\([A-Za-z0-9.]+\))?"
    r"|\bDNA\b\s+(?:appointment|clinic|hospital|2WW)"
    r"|^\s*DNA\s*$",
    re.IGNORECASE | re.MULTILINE,
)
# Provisional / suspected diagnosis qualifiers that should KEEP the encounter
# as `seen` rather than promote it to `dx/cancer_found` even when a strong
# cancer noun (e.g. "Squamous Cell Carcinoma") appears in the text.  Live
# corpus examples (patient 6040304227, 2024-11-13 dermatology consult):
#   "Suspected skin cancer (XaFww) - Squamous Cell Carcinoma"
#   "?? BCC however, Scc can not be ruled out"
#   "?suspected BCC vs SCC"
#   "Squamous cell carcinoma cannot be ruled out"
# These are SEEN milestones (clinician suspects but has not confirmed),
# not Dx milestones.  Confirmation lives in a separate later encounter
# (excision biopsy, MDT outcome, "Major: Squamous cell carcinoma (Y356f)").
_PROVISIONAL_DX_QUALIFIER = re.compile(
    r"\b(?:suspected\s+(?:skin\s+)?(?:cancer|carcinoma|melanoma|tumou?r|lesion)"
    r"|suspect\s+(?:scc|bcc|carcinoma|melanoma|cancer|malignan)"
    r"|\?\s*(?:scc|bcc|carcinoma|melanoma|cancer|malignan)"
    r"|cannot\s+be\s+ruled\s+out|can\s+not\s+be\s+ruled\s+out|cant\s+be\s+ruled\s+out"
    r"|to\s+rule\s+out\s+(?:cancer|malignan|scc|bcc|carcinoma|melanoma)"
    r"|differential\s+(?:diagnosis|dx)"
    r"|provisional\s+diagnosis"
    r"|working\s+diagnosis"
    r")\b"
    r"|\?\?\s*(?:scc|bcc|carcinoma|melanoma)"
    r"|\(\s*XaFww\s*\)",
    re.IGNORECASE,
)
# A note confirming a referral was cancelled by the patient / GP / secondary
# care.  These contain "2WW" or "referral" language but the pathway did not
# proceed — must not be labelled ftr.
_EMIS_NEW_EPISODE = re.compile(r"\(New Episode\)", re.IGNORECASE)
# When a dx-phrase (e.g. "lymphoma", "malignant") is immediately preceded by an
# existing-condition qualifier, the encounter is a monitoring/follow-up visit for
# a known diagnosis — not a new NCDA Dx event.  This guard prevents "BG of
# lymphoma" or "known carcinoma" in a routine GP note from misfiring as dx.
#
# Also catches POST-EVENT narrative recaps where the GP describes a treatment
# that has already happened ("recently was in hospital for hemicolectomy due
# to malignant tumour of colon", "post-op for prostate ca", "underwent WLE
# for melanoma").  These phrases unambiguously imply the cancer is already
# established; the labeller must not promote them to dx/cancer_found.  We are
# careful NOT to match bare temporal adverbs like "recently" because they can
# legitimately co-occur with a new dx (e.g. "recently diagnosed with...").
_EXISTING_CONDITION_PREFIX = re.compile(
    r"(?:"
    # Single-keyword qualifiers (matched then \s+ optional "of ").
    r"\b(?:b/g|bg|background|known|history|hx|previous|prior|existing"
    r"|established|longstanding|chronic|ongoing)\s+(?:of\s+)?"
    r"|"
    # Post-event recap qualifiers: surgery / treatment that already happened.
    r"\bdue\s+to\s+"                                # "due to malignant tumour"
    r"|\btreated\s+for\s+"                          # "treated for malignant"
    # Patient is already an oncology patient for the named cancer.  Without
    # this guard a duty-list telephone-triage encounter that just recaps
    # the patient's current oncology context (e.g. "Currently under
    # oncology for GOJ adenocarcinoma - had 3 cycles of chemo so far")
    # gets promoted to dx/cancer_found and spawns a phantom new episode.
    r"|\b(?:currently\s+)?under\s+(?:the\s+)?(?:care\s+of\s+)?"
    r"(?:oncolog(?:y|ist)|haematolog(?:y|ist)|cancer\s+services|MDT)\s+for\s+"
    # "had N cycles of <chemo|chemotherapy|radio|radiotherapy>"
    r"|\bhad\s+(?:\d+\s+(?:more\s+)?)?(?:more\s+)?cycle[s]?\s+of\s+"
    # Surveillance / monitoring of an existing cancer.  Prevents
    # GP follow-up notes ("had bloods for lymphoma done too early",
    # "monitoring for prostate ca", "follow up for endometrial cancer")
    # from misfiring on the bare cancer noun via _DX_FOUND_PHRASES.
    r"|\bhad\s+(?:bloods?|tests?|bloodwork|labs|imaging|ct|mri|us|ultrasound|scans?)"
    r"\s+(?:done\s+)?(?:too\s+early\s+)?for\s+"
    r"|\b(?:monitoring|surveillance|follow[\s-]?up|f\s*/\s*u)\s+for\s+"
    r"|\bpost[-\s]?op(?:erative)?\s+(?:for\s+)?"    # "post-op for", "post-operative"
    r"|\bunder(?:went|going)\s+\S+(?:\s+\S+){0,4}\s+(?:for|to)\s+"  # "underwent WLE for melanoma"
    # NEW: bare "underwent <surgery>" without a trailing "for ..." qualifier.
    # Required so a follow-up note like "Patient underwent thyroidectomy this
    # morning" silences the treatment-phrase match cleanly.
    r"|\bunder(?:went|going)\s+(?:a\s+|an\s+|the\s+)?(?:hemi)?(?:colectomy"
    r"|mastectomy|lumpectomy|prostatectomy|hysterectomy|nephrectomy"
    r"|cystectomy|lobectomy|pancreatectomy|gastrectomy|oesophagectomy"
    r"|esophagectomy|thyroidectomy|orchidectomy|splenectomy"
    r"|tonsillectomy|adrenalectomy|parotidectomy|excision|resection|biopsy)\b"
    r"|\bafter\s+(?:surgery|operation|treatment|chemo(?:therapy)?"
    r"|radio(?:therapy)?|hemicolectomy|mastectomy|lumpectomy|prostatectomy"
    r"|hysterectomy|nephrectomy|cystectomy|lobectomy|pancreatectomy"
    r"|gastrectomy|oesophagectomy|esophagectomy|thyroidectomy|orchidectomy"
    r"|splenectomy|tonsillectomy|adrenalectomy|parotidectomy"
    r"|excision|resection|biopsy)\s+(?:for\s+)?"        # "after surgery for"
    r"|\bfollowing\s+(?:surgery|operation|treatment|chemo(?:therapy)?"
    r"|radio(?:therapy)?|hemicolectomy|mastectomy|lumpectomy|prostatectomy"
    r"|hysterectomy|nephrectomy|cystectomy|lobectomy|pancreatectomy"
    r"|gastrectomy|oesophagectomy|esophagectomy|thyroidectomy|orchidectomy"
    r"|splenectomy|tonsillectomy|adrenalectomy|parotidectomy"
    r"|excision|resection|biopsy)\s+(?:for\s+)?"        # "following surgery for"
    r"|\bhad\s+(?:a\s+|an\s+|the\s+)?(?:hemi)?(?:colectomy|mastectomy"
    r"|lumpectomy|prostatectomy|hysterectomy|nephrectomy|cystectomy"
    r"|lobectomy|pancreatectomy|gastrectomy|oesophagectomy|esophagectomy"
    r"|thyroidectomy|orchidectomy|splenectomy|tonsillectomy"
    r"|adrenalectomy|parotidectomy"
    r"|excision|resection|biopsy)\b"                                # ends at the surgery name; trailing context is optional
    r"(?:\s+in\s+\S+\s+\d{4})?"                                     # "had a thyroidectomy in March 2024"
    r"(?:\s+for\s+)?"                                               # "had a mastectomy for"
    r"|\bin\s+hospital\s+for\s+\S+(?:\s+\S+){0,4}\s+(?:due\s+to|for|after)\s+"
                                                                     # "in hospital for X due to / for / after"
    r")",
    re.IGNORECASE,
)
_CANCELLED_REFERRAL = re.compile(
    r"(?:pt|patient)\s+cancelled\s+(?:this\s+)?referral"
    r"|referral\s+(?:cancelled|withdrawn)\s+by\s+(?:patient|pt|gp)"
    r"|referral\s+cancelled\b"
    r"|(?:pt|patient)\s+declined\s+(?:the\s+)?referral"
    r"|did\s+not\s+attend.*(?:2WW|referral|clinic).*not\s+seen",
    re.IGNORECASE | re.DOTALL,
)
# Follow-up admin / clinical notes that quote a previously CONCLUDED 2WW
# pathway (NSS / 2WW / fast-track / cancer pathway "discharged" or with
# "Recommendations to GP:" hand-over text).  Without this guard the phrase
# matcher fires on the recapped "2WW" / "Fast track" text and creates a
# phantom FTR anchor.  See patient 6261656266 (NSS pathway concluded
# 2024-10-02, GP follow-up admin note 2024-10-24 misfired as a new FTR).
_FOLLOWUP_TO_CONCLUDED_2WW_PATHWAY = re.compile(
    r"\b(?:"
    r"discharge(?:d)?\s+from\s+(?:the\s+)?(?:NSS|2WW|fast[-\s]?track|cancer"
    r"|two[-\s]?week(?:\s+wait)?)\s+pathway"
    # Inverse word order: "NSS pathway ... was/got discharged".  Handles
    # GP recap notes that lead with the pathway name and then say it was
    # closed without using the canonical "discharged from <type> pathway".
    # Window is bounded to ~80 chars to avoid stretching across unrelated
    # clauses.
    r"|(?:NSS|2WW|cancer|fast[-\s]?track)\s+pathway\b[^.\n]{0,80}\b"
    r"(?:was|got|now)?\s*discharge(?:d)?\b"
    # "noted had NSS pathway 2ww referral and was discharged"
    # "noted had / has had / had a NSS pathway done / referral / completed"
    # patterns: a recap of a previously completed referral.
    r"|\b(?:noted\s+)?(?:has\s+)?had\s+(?:a\s+|an\s+|the\s+)?"
    r"(?:NSS|2WW|cancer|fast[-\s]?track|two[-\s]?week)\s+(?:pathway|referral)\b"
    r"[^.\n]{0,80}\b(?:done|completed|finished|discharge(?:d)?)\b"
    r"|(?:NSS|2WW|cancer|fast[-\s]?track)\s+pathway\s+update\s+letter"
    r"|Recommendations?\s+to\s+GP\s*:\s*(?:please\s+|pls\s+)?(?:follow|continue|monitor)"
    # Discussion of a CONCLUDED NSS/2WW work-up: "recent NSS work up... d/c
    # from the MDT" / "no concerns for malignancy".  Captures the clinical-
    # supervision style of recap that was missing from the original
    # discharge-from-pathway pattern.
    r"|(?:recent\s+)?(?:NSS|2WW|fast[-\s]?track)\s+work[-\s]?up\b[^.\n]{0,80}"
    r"\b(?:d/?c|discharge(?:d)?|no\s+concerns?|no\s+malignancy)\b"
    r")\b",
    re.IGNORECASE,
)

_SITE_TOKENS: dict[str, tuple[str, ...]] = {
    "urological": ("prostate", "psa", "urology", "urological", "bladder", "haematuria",
                    "kidney", "renal", "nephrectomy"),
    "breast": ("breast", "mammogram", "mammography"),
    # NB: bare "thorax" intentionally NOT here — it appears in melanoma /
    # colorectal staging CTs ("CT Neck thorax abdomen and pelvis") and would
    # mis-route those to lung.  We instead match the qualified forms
    # "ct thorax" / "ct chest" plus "bronchoscop" / "respiratory".  See
    # patient 7324271383 (right-thigh melanoma with CT staging).
    "lung": ("lung", "chest x-ray", "cxr", "thoracic", "ct thorax", "ct chest",
              "respiratory", "bronchoscop"),
    "lower_gi": ("lower gi", "colorectal", "bowel", "rectal", "colon", "fit positive",
                  "caecum", "cecum", "rectum", "anal canal", "ileum"),
    "upper_gi": ("upper gi", "oesophag", "stomach", "gastric", "dysphagia"),
    # NB: order matters and the token list is deliberately narrow.  Bare
    # "squamous cell carcinoma" (without a site qualifier) is intentionally
    # NOT here because it appears on both head_neck (oropharyngeal /
    # buccal mucosa) and skin diagnoses, and a wrong wildcard match would
    # cross-site link a head_neck FTR to a skin dx (or vice versa).  We
    # instead match the precise patterns that uniquely identify skin
    # cancers (BCC, AK, the qualified "squamous cell carcinoma of skin",
    # "of scalp", etc.).  See patient 4802297327: buccal-mucosa SCC was
    # being misrouted to site=skin under the looser pattern.
    "skin": ("skin", "dermoscopy", "dermatology", "melanoma", "lesion",
             "basal cell carcinoma", "bcc", "actinic keratosis", "ak ",
             "wide local excision", "wle",
             "excision of basal", "excision of squamous",
             "squamous cell carcinoma of skin",
             "squamous cell carcinoma - r vertex",
             "squamous cell carcinoma - l vertex",
             "squamous cell carcinoma of scalp",
             # Single-word body-site fallbacks that uniquely identify
             "scalp", "vertex"),
    "head_neck": ("head and neck", "head & neck", "thyroid", "larynx",
                  "pharynx", "tongue", "papillary thyroid", "follicular thyroid",
                  "thyroidectomy", "buccal mucosa", "oral cavity",
                  "squamous cell carcinoma of buccal",
                  "squamous cell carcinoma of tongue",
                  "squamous cell carcinoma of larynx",
                  "squamous cell carcinoma of pharynx"),
    "gynaecological": ("gynae", "gynaecolog", "cervix", "endometri", "ovari", "uterus"),
    "haematological": ("haematol", "lymphoma", "leukaemia", "myeloma", "sll", "cll"),
    "brain": ("brain", "cns", "neurosurg", "headache", "seizure"),
    "nss": ("non-site specific", "nss", "weight loss", "fatigue"),
}


def _is_excluded_none(text: str) -> tuple[bool, str]:
    """Return (True, rationale) if this encounter is definitively role=none.

    Covers four encounter structural types that contain 2WW language but are
    NOT active FTR submissions:
      1. Auto-filed lab/radiology results (PSA, FIT, CXR, bloods).
      2. Retrospective Type-4 admin tracking notes.
      3. Scheduled-task creation encounters.
      4. Triage/rejection admin notes.
    """
    t = text or ""
    # Exclusion rules below all silence encounters whose 2WW/cancer text is
    # admin scaffolding rather than a real anchor.  When the same encounter
    # also contains a confirmed-cancer signal (histology/excision/malignant
    # neoplasm phrases) we should NOT silence it - the labeller below will
    # then pick up the dx/treatment role from the genuine clinical block.
    has_confirmed_cancer = bool(_CANCER_CONFIRMED_SIGNAL.search(t))
    if _AUTO_FILED_LABS.search(t) and not has_confirmed_cancer:
        return True, "Auto-filed lab or radiology result - not an NCDA anchor."
    if _ADMIN_TRACKING_2WW.search(t) and not has_confirmed_cancer:
        return True, "Retrospective 2WW clinic-attendance tracking note."
    if _ADMIN_OPA_DATE.search(t) and not has_confirmed_cancer:
        return True, "2WW outpatient appointment date recording - admin note."
    if _SCHEDULED_TASK.search(t) and not has_confirmed_cancer:
        return True, "Scheduled task creation encounter - admin only."
    if _TRIAGE_REJECTION.search(t) and not has_confirmed_cancer:
        return True, "Referral triage response or rejection note."
    if _PHLEBOTOMY_TEMPLATE.search(t) and not has_confirmed_cancer:
        return True, "Phlebotomy template encounter — monitoring visit, not an NCDA anchor."
    if _BENIGN_SKIN_LESION_REFERRAL_ADMIN.search(t) and not has_confirmed_cancer:
        return True, "Benign skin lesion referral admin — not a cancer FTR."
    if _GENETICS_REFERRAL_ADMIN.search(t):
        return True, "Genetics/family-history referral admin — not an NCDA cancer FTR."
    if _CANCELLED_REFERRAL.search(t):
        return True, "Referral was cancelled by patient/GP — not an active NCDA anchor."
    if _FOLLOWUP_TO_CONCLUDED_2WW_PATHWAY.search(t) and not has_confirmed_cancer:
        return True, (
            "Follow-up admin note quoting a previously concluded 2WW / NSS / "
            "fast-track pathway — not a new NCDA anchor."
        )
    # DNA / Did-Not-Attend appointment — patient did not present, so the
    # encounter is not a real first_seen / OPD attendance.
    if _DNA_APPOINTMENT.search(t) and not has_confirmed_cancer:
        return True, (
            "Did-not-attend appointment — patient was a no-show, "
            "not a real first_seen anchor."
        )
    return False, ""


_PRIMARY_MAJOR_SITE_RE = re.compile(
    r"^Major:\s+(?:malignant\s+(?:tumou?r|neoplasm)\s+of"
    r"|carcinoma\s+of"
    r"|adenocarcinoma\s+of"
    r"|invasive\s+(?:ductal|lobular)\s+carcinoma"
    r"|infiltrating\s+duct\s+carcinoma"
    r"|squamous\s+cell\s+carcinoma\s+(?:of|-)"
    r"|basal\s+cell\s+carcinoma\s+(?:of|-))"
    r"\s*([A-Za-z][\w\s\-/]{0,60})",
    re.IGNORECASE | re.MULTILINE,
)


def _extract_site_hint(text: str) -> str | None:
    """Return a cancer site hint based on keyword signals in the encounter text.

    Two-pass strategy:
      1. Look for a "Major: <primary cancer term> <site>" line first.  When
         present (e.g. "Major: Carcinoma of caecum"), the site of the primary
         cancer wins over keywords elsewhere in the text — without this the
         dx encounter "Major: Metastasis to lung. Major: Metastasis to liver.
         Major: Carcinoma of caecum" was misrouted to site=lung because
         "lung" is the first keyword to fire under the broad scan.
      2. Fall back to the broad keyword scan over ``_SITE_TOKENS``.
    """
    lower = (text or "").lower()
    if text:
        m = _PRIMARY_MAJOR_SITE_RE.search(text)
        if m:
            primary_phrase = m.group(0).lower()
            for site, tokens in _SITE_TOKENS.items():
                if any(tok in primary_phrase for tok in tokens):
                    return site
    for site, tokens in _SITE_TOKENS.items():
        if any(tok in lower for tok in tokens):
            return site
    return None


_ROLE_PRIORITY: dict[str, int] = {
    "ftr": 5, "seen": 4, "dx": 3, "treatment": 2, "none": 0,
}


def _best_role_from_codes(text: str) -> tuple[NcdaRole | None, DxOutcome | None]:
    """Return the highest-priority role found among all Read codes in the text.

    Iterates ALL codes rather than stopping at the first match, so that a
    high-priority FTR code (XaMeC) beats a generic none-code (Xa1qL) even
    when the generic code appears earlier in the text.  ``none`` codes are
    only returned when no higher-priority match was found.

    Cancer-affirming "Problem: ..." header lines are stripped before code
    extraction so that EMIS problem-list recap codes (e.g. "Problem: Malignant
    tumour of breast (X78WM)" in a phlebotomy encounter) do not elevate a
    routine monitoring visit to dx/cancer_found role.
    """
    best_role: NcdaRole | None = None
    best_outcome: DxOutcome | None = None
    best_priority: int = -1

    # Strip cancer-affirming Problem headers before code lookup so that codes
    # recapping existing diagnoses (in phlebotomy / LTC review encounters) are
    # not found by extract_read_codes.
    code_text = _strip_problem_lines(text or "")

    for token in extract_read_codes(code_text):
        looked = lookup_read_code(token)
        if looked is None:
            continue
        role, outcome = looked
        priority = _ROLE_PRIORITY.get(role, 0)
        if role == "dx" and outcome is not None:
            priority = max(priority, _ROLE_PRIORITY["seen"] + 1)
        if priority > best_priority:
            best_role = role
            best_outcome = outcome
            best_priority = priority

    if best_role is not None and best_role != "none":
        return best_role, best_outcome
    if _bare_drug_token_present(text or ""):
        return ("treatment", None)
    if best_role == "none":
        return ("none", None)
    return (None, None)


def _bare_drug_token_present(text: str) -> bool:
    """Detect cancer drug tokens even when not wrapped in parens."""
    if not text:
        return False
    upper = text.upper()
    return any(drug in upper for drug in TREATMENT_DRUG_TOKENS)


_PRISM_QUESTIONNAIRE = re.compile(
    r"PRISM\s+2WW.*questionnaire\s+started",
    re.IGNORECASE,
)


def _phrase_match_outside_existing_condition(
    text: str, pattern: re.Pattern[str]
) -> bool:
    """Return True if ``pattern`` matches ``text`` AND the match is NOT
    inside an existing-condition / post-event qualifier.

    Uses an 80-character window that INCLUDES the matched term itself.
    This is required for the ``treatment`` phrase guard because the matched
    treatment word (e.g. "oesophagectomy") is itself part of the qualifier
    pattern (``had <surgery>``).  For the dx-phrase guard the matched term
    (e.g. "adenocarcinoma") is not in the qualifier vocabulary so widening
    the window is harmless.
    """
    m = pattern.search(text)
    if not m:
        return False
    window = text[max(0, m.start() - 80): m.end()]
    return not _EXISTING_CONDITION_PREFIX.search(window)


def _best_role_from_phrases(text: str) -> tuple[NcdaRole | None, DxOutcome | None]:
    """Match NCDA role from free-text phrases.

    Note: PRISM questionnaire encounters are intercepted BEFORE this function
    is called (in deterministic_label), so "suspected lymphoma" in a PRISM
    questionnaire body will not cause this function to return "dx".
    The original ordering (dx > ftr) is preserved so that discharge notes
    ("Discharged from 2WW, no malignancy") return dx, not ftr.

    For dx phrases (e.g. "lymphoma", "malignant") an existing-condition prefix
    guard is applied: if the 80 characters before the match end with qualifiers
    like "BG of", "known", "history of", the phrase describes a pre-existing
    diagnosis and must not promote the encounter to dx/cancer_found.
    Cancer-excluded signals (_DX_EXCLUDED_PHRASES) bypass this guard because
    "no malignancy" / "benign" are outcome results regardless of context.

    The same existing-condition guard is now applied to ``treatment`` phrase
    matches as well (e.g. "background thyroidectomy", "post-op for prostate
    ca") so that recap mentions of historical treatment do not anchor a new
    ``treatment_started`` milestone.
    """
    t = _strip_problem_lines(text or "")
    # --- dx role: direct match with existing-condition guard on found-phrases ---
    if _DX_EXCLUDED_PHRASES.search(t):
        return "dx", _infer_dx_outcome(t)
    m_found = _DX_FOUND_PHRASES.search(t)
    if m_found:
        prefix = t[max(0, m_found.start() - 80): m_found.start()]
        # Provisional-dx guard: when the cancer noun is qualified by a
        # "suspected" / "?? <cancer>" / "cannot be ruled out" / "rule out
        # <cancer>" pattern anywhere in the text, the encounter is a SEEN
        # milestone (clinician suspects but has not confirmed), not a Dx
        # event.  Without this guard "Suspected skin cancer (XaFww) -
        # Squamous Cell Carcinoma" promotes to dx/cancer_found and steals
        # the diagnosis_confirmed milestone from the real later excision-
        # biopsy encounter (see patient 6040304227 melanoma).
        if not _EXISTING_CONDITION_PREFIX.search(prefix) and \
                not _PROVISIONAL_DX_QUALIFIER.search(t):
            return "dx", _infer_dx_outcome(t)
    # --- remaining roles ---
    for role in ("ftr", "seen", "treatment"):
        if role == "treatment":
            # Apply existing-condition prefix guard to treatment phrase
            # matches (parity with dx-found handling above).
            if _phrase_match_outside_existing_condition(t, _TREATMENT_PHRASES):
                return (role, None)
            continue
        if text_supports_role(t, role):  # type: ignore[arg-type]
            return (role, None)  # type: ignore[return-value]
    return (None, None)


def label_with_llm(
    *,
    patient_id: str,
    encounter_id: str,
    encounter_date: str | None,
    text: str,
    flags: str | None,
    llm: LlmRelabelFn,
) -> SilverLabel:
    """Label one encounter via the supplied LLM callback.

    The callback returns a dict with keys role / outcome / confidence /
    rationale / supporting_quote / site_hint. Falls back to deterministic
    labels on any LLM error (logged by caller).
    """
    response = llm(text, flags)
    role = str(response.get("role", "none"))
    if role not in {"ftr", "seen", "dx", "treatment", "none"}:
        role = "none"
    outcome_raw = response.get("outcome")
    outcome: DxOutcome | None = None
    if role == "dx" and outcome_raw in ("cancer_found", "cancer_excluded"):
        outcome = outcome_raw  # type: ignore[assignment]
    return SilverLabel(
        patient_id=patient_id,
        encounter_id=encounter_id,
        encounter_date=encounter_date,
        role=role,  # type: ignore[arg-type]
        outcome=outcome,
        confidence=float(response.get("confidence", 0.5)),
        rationale=str(response.get("rationale", "")).strip()[:500],
        supporting_quote=str(response.get("supporting_quote", "")).strip()[:300],
        site_hint=response.get("site_hint"),  # type: ignore[arg-type]
        source="llm",
    )


def label_corpus(
    rows: Iterable[dict],
    *,
    llm: LlmRelabelFn | None = None,
) -> list[SilverLabel]:
    """Label every encounter row; LLM if provided, else deterministic."""
    out: list[SilverLabel] = []
    for r in rows:
        if llm is None:
            out.append(deterministic_label(**_kwargs_from_row(r)))
            continue
        try:
            out.append(label_with_llm(llm=llm, **_kwargs_from_row(r)))
        except Exception:
            out.append(deterministic_label(**_kwargs_from_row(r)))
    return out


def _kwargs_from_row(r: dict) -> dict:
    return {
        "patient_id": r["patient_id"],
        "encounter_id": r["encounter_id"],
        "encounter_date": r.get("encounter_date"),
        "text": r.get("text") or "",
        "flags": r.get("flags"),
    }


def labels_to_dicts(labels: Iterable[SilverLabel]) -> list[dict]:
    return [asdict(label) for label in labels]
