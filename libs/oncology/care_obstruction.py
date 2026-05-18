"""Care-obstruction signal detection for NCDA cancer episodes.

The NCDA report asks reviewers to record events that delayed the workup
between Fast Track Referral (FTR) and diagnosis: rejected referrals,
DNAs, cancellations, and other access barriers.  These events are
clinically significant because they extend the FTR-to-Dx interval and
are a known driver of late-stage diagnosis.

The episode writer (``scripts/ncda/run_full_cancer_episode_detection.py``)
calls :func:`detect_care_obstructions` after each episode is MERGEd,
passing every encounter ``(text, flags)`` pair in the milestone-anchored
window ``[earliest_milestone - 30d, latest_milestone + 14d]``.  Scoping
the scan to the episode window dramatically reduces noise from
unrelated admin records (phlebotomy / community DN / heart-failure
service) that share the same vocabulary.

Four signal strengths are reported (mutually exclusive — the strongest
match wins, in this priority order):

  - ``"rejection"``    referral was rejected or returned by the service
                        provider — strongest obstruction signal.  Read
                        code ``XaQgL`` ("Choose and book referral
                        rejected by service provider") or free-text
                        "TRIAGE RESPONSE / Return to referrer with
                        advice / REFERRAL REJECTED - Inappropriate".
                        Forces a re-submission and is the most common
                        cause of the patient losing the 2WW slot.

  - ``"dna"``          patient did not attend an appointment.  Read
                        codes ``XacSG`` ("Did not attend clinic"),
                        ``XaF81`` ("Did not attend hospital
                        appointment"), ``Xa1kG`` ("Did not attend"),
                        or the encounter ``flags`` field literally
                        containing ``DNA`` (the EMIS structured marker).

  - ``"cancellation"`` appointment was cancelled — by the patient or
                        by the hospital.  Less severe than DNA because
                        the slot is usually re-offered, but still
                        delays the workup.

  - ``"access_barrier"`` the service was unable to contact the patient,
                          the patient declined a referral, or similar
                          softer access issues that delay care without
                          being a hard rejection / DNA.

  - ``"none"``         no obstruction evidence found in the window.

Reporting all four signal strengths lets the dashboard render the
defensible headline (``rejection + dna + cancellation``) by default
while still exposing access-barrier cases behind a tooltip / dialog.
The same shape mirrors :mod:`libs.oncology.safety_netting`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Literal, Sequence

# ---------------------------------------------------------------------------
# Signal patterns  (corpus-driven from the cancer cohort)
# ---------------------------------------------------------------------------

#: Rejection signals — the referring service returned or refused the
#: referral, forcing the GP to re-refer.  ``XaQgL`` is the canonical
#: "Choose and book referral rejected by service provider" Read code.
_REJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bXaQgL\b"),
    re.compile(r"choose\s+and\s+book\s+referral\s+rejected\s+by\s+service\s+provider", re.IGNORECASE),
    re.compile(r"\breferral\s+rejected\b(?!\s*-\s*duplicate)", re.IGNORECASE),
    re.compile(r"\breferral\s+returned\s+to\s+referrer\b", re.IGNORECASE),
    re.compile(r"\breturn\s+to\s+referrer\s+with\s+advice\b", re.IGNORECASE),
    re.compile(r"\bREFERRAL\s+REJECTED\s*-\s*Inappropriate\b", re.IGNORECASE),
    re.compile(r"\binappropriate\s+referral\b", re.IGNORECASE),
    re.compile(r"\btriage\s+response\b", re.IGNORECASE),
)

#: Per-line noise filter for rejection: phlebotomy, SPA, community DN
#: routinely emit "referral rejected - duplicate" admin housekeeping
#: that has nothing to do with cancer-pathway obstructions.  These are
#: dropped from the rejection bucket.
_REJECTION_NOISE = re.compile(
    r"referral\s+rejected\s*[-:]\s*duplicate"
    r"|referral\s+rejected\s*-\s*outside",
    re.IGNORECASE,
)

#: DNA signals — patient was a no-show.  Includes the EMIS structured
#: ``flags = "DNA"`` marker, the three DNA Read codes
#: (XacSG / XaF81 / Xa1kG), and the free-text "Did not attend" /
#: "Failed to attend" / "no-show" phrasing.
_DNA_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(XacSG|XaF81|Xa1kG)\b"),
    re.compile(r"\bdid\s+not\s+attend\b", re.IGNORECASE),
    re.compile(r"\bfailed\s+to\s+attend\b", re.IGNORECASE),
    re.compile(r"\bno[\s\-]?show\b", re.IGNORECASE),
    re.compile(r"\bDNA(?:'?d)?\b\s+(?:appointment|clinic|hospital|2WW|session)", re.IGNORECASE),
)

#: Per-line noise filter for DNA: when a "did not attend" line is
#: paired with "marked in error" in the same encounter, the DNA was
#: retracted and should not be counted.  Uses ``[\s\S]`` so the match
#: spans newlines.
_DNA_RETRACTED = re.compile(
    r"did\s+not\s+attend[\s\S]{0,200}marked\s+in\s+error"
    r"|marked\s+in\s+error[\s\S]{0,200}did\s+not\s+attend",
    re.IGNORECASE,
)

#: Cancellation signals — appointment cancelled by patient or service.
_CANCELLATION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bpatient\s+cancelled\b", re.IGNORECASE),
    re.compile(r"\bcancelled\s+by\s+patient\b", re.IGNORECASE),
    re.compile(r"\bcancelled\s+by\s+hospital\b", re.IGNORECASE),
    re.compile(r"\bhospital\s+cancelled\b", re.IGNORECASE),
    re.compile(r"\bappointment\s+cancelled\b", re.IGNORECASE),
    re.compile(r"\bappt\s+cancelled\b", re.IGNORECASE),
)

#: Access-barrier signals — softer issues that still delay care.
_ACCESS_BARRIER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bunable\s+to\s+contact\s+(?:the\s+)?patient\b", re.IGNORECASE),
    re.compile(r"\bfailed\s+to\s+contact\s+(?:the\s+)?patient\b", re.IGNORECASE),
    re.compile(r"\bpatient\s+declined\s+(?:the\s+)?referral\b", re.IGNORECASE),
    re.compile(r"\bdeclined\s+(?:the\s+)?referral\b", re.IGNORECASE),
    re.compile(r"\blost\s+to\s+follow[\s\-]?up\b", re.IGNORECASE),
)


CareObstructionSignal = Literal[
    "rejection", "dna", "cancellation", "access_barrier", "none"
]

# ---------------------------------------------------------------------------
# Pathway-relatedness classification
# ---------------------------------------------------------------------------
#
# Not every DNA / rejection / cancellation that falls in the milestone
# window is actually about the cancer pathway.  The corpus has dozens of
# obvious false positives:
#   - Patient 4246897485 (breast cancer) has 9 DNAs in window — but most
#     are MIDWIFE antenatal/postnatal appointments, not breast clinic.
#   - Patient 7324271383 (melanoma) has a DNA at "Loughborough Urgent
#     Treatment Centre" — not the dermatology clinic.
#   - Phlebotomy / district nurse / cardiac rehab / pulmonary rehab
#     pipelines emit "did not attend" lines that have nothing to do
#     with the index cancer pathway.
#
# We classify each obstruction encounter as one of:
#
#   "confirmed"  — explicit cancer-pathway markers in the text (2WW,
#                  FTR, oncology, "Choose and book referral rejected"
#                  Read code XaQgL, biopsy, MDT, NSS pathway) OR the
#                  site-specific specialty for this episode's
#                  cancer_type (e.g. "dermatology" for melanoma,
#                  "urology" for prostate).  These count and are
#                  visible to clinicians in the breakdown dialog.
#
#   "possible"   — no clear cancer markers, but no clearly-unrelated
#                  service context either.  Default bucket for
#                  generic "Did not attend session appointment"
#                  lines that don't say what the appointment was
#                  for.  These count toward the headline.
#
#   "unrelated"  — clearly came from a non-cancer service
#                  (phlebotomy, midwife, community DN, heart failure,
#                  cardiac/pulmonary rehab, podiatry, dental, IAPT,
#                  diabetes nurse, smoking cessation, urgent
#                  treatment centre, etc.) AND no cancer markers.
#                  These are FILTERED out of the headline and counted
#                  separately as ``unrelated_filtered_count`` for
#                  telemetry / debugging.

PathwayRelatedness = Literal["confirmed", "possible", "unrelated"]

#: Generic cancer-pathway markers — match any of these and the
#: encounter is "confirmed" cancer-related regardless of cancer_type.
#: Word stems use ``\w*`` suffix so e.g. "oncolog" matches both
#: "oncology" and "oncologist" (a bare ``\b`` after the stem never
#: fires because the next character is still a word char).
_CANCER_PATHWAY_MARKERS = re.compile(
    r"(?:"
    r"\b2[\s\-]?ww\b|two[\s\-]?week[\s\-]?wait|"
    r"fast[\s\-]?track[\s\-]?referral|\bFTR\b|"
    r"suspected\s+cancer|cancer\s+pathway|cancer\s+2[\s\-]?ww|"
    r"\boncolog\w*|\bonco\b|chemotherap\w*|radiotherap\w*|"
    r"\bbiopsy\b|histolog\w*|\bMDT\b|multi[\s\-]?disciplinary[\s\-]?team|"
    r"NSS\s+pathway|non[\s\-]?site[\s\-]?specific|"
    r"choose\s+and\s+book\s+referral\s+rejected|\bXaQgL\b"
    r")",
    re.IGNORECASE,
)

#: Site-specific positive markers — keyed by the canonical site key
#: produced by ``libs.oncology.cancer_types.canonical_to_site_key``
#: (lowercase, underscored).  When ``cancer_type`` is supplied, the
#: matching pattern is OR'd into the "confirmed" check.
#: Patterns use ``\w*`` after a stem so e.g. ``dermatolog\w*`` catches
#: "Dermatology" / "Dermatologist".  Bare ``\b`` after a stem never
#: matches because the next char (e.g. ``y``) is a word character.
_SITE_PATHWAY_MARKERS: dict[str, re.Pattern[str]] = {
    "breast": re.compile(
        r"(?:\bbreast(?:\s+(?:clinic|screening|team|unit))?\b|"
        r"\bmammogram\b|\bmammograph\w*)",
        re.IGNORECASE,
    ),
    "prostate": re.compile(
        r"(?:\burolog\w*|\bprostate\b|\bPSA\b|\bDRE\b|\bTRUS\b|MRI\s+prostate)",
        re.IGNORECASE,
    ),
    "melanoma": re.compile(
        r"(?:\bdermatolog\w*|skin\s+(?:clinic|lesion|cancer)|"
        r"\bmelanoma\b|pigmented\s+lesion|mole\s+clinic)",
        re.IGNORECASE,
    ),
    "skin": re.compile(
        r"(?:\bdermatolog\w*|skin\s+(?:clinic|lesion|cancer)|\bSCC\b|\bBCC\b)",
        re.IGNORECASE,
    ),
    "lung": re.compile(
        r"(?:\brespiratory\b|lung\s+(?:clinic|cancer)|chest\s+clinic|"
        r"bronchoscop\w*|CT\s+thorax|CT\s+chest|\bthoracic\b)",
        re.IGNORECASE,
    ),
    "lower_gi": re.compile(
        r"(?:\bcolorectal\b|colonoscop\w*|\bGI\s+clinic|\bgastro\w*|"
        r"FIT\s+test|sigmoidoscop\w*|rectal\s+exam)",
        re.IGNORECASE,
    ),
    "upper_gi": re.compile(
        r"(?:endoscop\w*|\bOGD\b|upper\s+GI|oesophag\w*|esophag\w*|"
        r"stomach\s+clinic|\bgastro\w*)",
        re.IGNORECASE,
    ),
    "head_neck": re.compile(
        r"(?:\bENT\b|head\s+(?:and|&)\s+neck|\bH&N\b|"
        r"maxillofacial|throat\s+clinic|oral\s+(?:clinic|surgery))",
        re.IGNORECASE,
    ),
    "lymphoma": re.compile(
        r"(?:haematolog\w*|hematolog\w*|lymph\s+node|\blymphoma\b)",
        re.IGNORECASE,
    ),
    "cervical": re.compile(
        r"(?:gyn(?:aecolog\w*)?|colposcop\w*|\bcervix\b|\bcervical\b|\bsmear\b)",
        re.IGNORECASE,
    ),
    "thyroid": re.compile(
        r"(?:endocrin\w*|\bthyroid\b|\bFNA\b|neck\s+ultrasound)",
        re.IGNORECASE,
    ),
    "ovarian": re.compile(
        r"(?:gyn(?:aecolog\w*)?|\bovarian\b|\bovary\b|\bCA[\s\-]?125\b)",
        re.IGNORECASE,
    ),
    "uterine": re.compile(
        r"(?:gyn(?:aecolog\w*)?|\buterine\b|\bendometrial\b|hysteroscop\w*)",
        re.IGNORECASE,
    ),
    "renal": re.compile(
        r"(?:\burolog\w*|renal\s+(?:clinic|cancer)|\bkidney\b|nephrolog\w*)",
        re.IGNORECASE,
    ),
    "bladder": re.compile(
        r"(?:\burolog\w*|\bbladder\b|cystoscop\w*|haematuria)",
        re.IGNORECASE,
    ),
    "pancreatic": re.compile(
        r"(?:\bHPB\b|hepatobiliary|pancrea(?:s|tic)|\bbiliary\b)",
        re.IGNORECASE,
    ),
    "haematology": re.compile(
        r"(?:haematolog\w*|hematolog\w*|leuk[ae]mia|bone\s+marrow|"
        r"\bMDS\b|\bmyeloma\b)",
        re.IGNORECASE,
    ),
    "brain": re.compile(
        r"(?:neurolog\w*|neurosurg\w*|\bbrain\b|MRI\s+head|CT\s+head)",
        re.IGNORECASE,
    ),
    "sarcoma": re.compile(
        r"(?:\bsarcoma\b|orthopaedic\s+oncolog\w*|MSK\s+oncolog\w*)",
        re.IGNORECASE,
    ),
    "unknown_primary": re.compile(
        r"(?:\bCUP\b|unknown\s+primary|\bMDT\b|metasta\w*)",
        re.IGNORECASE,
    ),
}

#: Service contexts that are CLEARLY non-cancer.  When an obstruction
#: appears in one of these contexts AND no positive cancer markers
#: are present, treat it as unrelated noise (filter from headline).
#: Patterns are corpus-driven from auditing the cohort's false positives.
_NON_CANCER_SERVICE_CONTEXT = re.compile(
    r"(?:"
    # Phlebotomy / blood services
    r"\bLLR\s+Phlebotomy\b|phlebotomy\s+(?:service|referral|venepuncture)|"
    # Community / district nursing
    r"\bLLR\s+Charnwood\s+DN\b|district\s+nurse|charnwood\s+dn|"
    # SPA / admin routing
    r"\bLLR\s+SPA\b|single\s+point\s+of\s+access|"
    # Long Term Conditions / heart failure / cardiac rehab
    r"\bLLR\s+Long\s+Term\s+Conditions\b|long\s+term\s+conditions|"
    r"community\s+heart\s+failure|heart\s+failure\s+nurse|cardiac\s+rehab|"
    # Pulmonary rehab / respiratory community
    r"pulmonary\s+rehab|"
    # Maternity / antenatal / midwife
    r"\bmidwife\b|antenatal|postnatal|maternity|\d+\+?\s*(?:wk|week)s?\s+an\s+check|"
    # Foot / podiatry
    r"\bpodiatr|chiropody|"
    # Dental
    r"dental\s+(?:clinic|practice)|dentist|orthodont|"
    # Smoking / lifestyle
    r"smoking\s+cessation|stop\s+smoking|"
    # Mental health
    r"mental\s+health|\bIAPT\b|talking\s+therap|psychiatr|"
    # Diabetes
    r"diabetes\s+(?:nurse|clinic|team|review)|"
    # Physio / MSK / joints (generic)
    r"physio(?:therap)?\s+(?:appointment|service|referral)|MSK\s+service|"
    # Hearing
    r"\baudiolog|hearing\s+aid|"
    # SLT
    r"speech\s+(?:and\s+language|therap)|\bSLT\b|"
    # Urgent / minor injuries — usually not cancer pathway
    r"urgent\s+treatment\s+centre|\bUTC\b|minor\s+injuries|"
    r"out[\s\-]?of[\s\-]?hours|\bOOH\b"
    r")",
    re.IGNORECASE,
)


def _normalise_site_for_markers(cancer_type: str | None) -> str | None:
    """Map a free-form ``cancer_type`` string to a key in
    :data:`_SITE_PATHWAY_MARKERS`.  Best-effort — falls back to
    ``None`` (generic markers only) if no mapping is found."""
    if not cancer_type:
        return None
    s = cancer_type.strip().lower()
    if not s:
        return None
    # Direct hits first
    direct = {
        "breast": "breast",
        "prostate": "prostate",
        "melanoma": "melanoma",
        "skin": "skin",
        "lung": "lung",
        "colorectal": "lower_gi",
        "lower gi": "lower_gi",
        "lower_gi": "lower_gi",
        "upper gi": "upper_gi",
        "upper_gi": "upper_gi",
        "oesophageal": "upper_gi",
        "esophageal": "upper_gi",
        "gastric": "upper_gi",
        "stomach": "upper_gi",
        "head and neck": "head_neck",
        "head_neck": "head_neck",
        "head & neck": "head_neck",
        "oropharyngeal": "head_neck",
        "lymphoma": "lymphoma",
        "leukaemia": "haematology",
        "leukemia": "haematology",
        "myeloma": "haematology",
        "haematology": "haematology",
        "cervical": "cervical",
        "thyroid": "thyroid",
        "ovarian": "ovarian",
        "uterine": "uterine",
        "endometrial": "uterine",
        "renal": "renal",
        "kidney": "renal",
        "bladder": "bladder",
        "pancreatic": "pancreatic",
        "brain": "brain",
        "sarcoma": "sarcoma",
        "unknown primary": "unknown_primary",
        "cup": "unknown_primary",
    }
    if s in direct:
        return direct[s]
    # Substring fallbacks for combined / "Other" entries
    for needle, key in direct.items():
        if needle in s:
            return key
    return None


def _classify_relatedness(
    text: str, cancer_type: str | None = None
) -> PathwayRelatedness:
    """Classify whether an obstruction encounter is related to the
    cancer pathway.  Three buckets — see module docstring for the
    rationale.  Order matters: positive cancer markers always beat the
    negative-context filter (a "2WW haematology triage" line should be
    "confirmed" even if it also says "phlebotomy" somewhere)."""
    if not text:
        return "possible"
    if _CANCER_PATHWAY_MARKERS.search(text):
        return "confirmed"
    site_key = _normalise_site_for_markers(cancer_type)
    if site_key and site_key in _SITE_PATHWAY_MARKERS:
        if _SITE_PATHWAY_MARKERS[site_key].search(text):
            return "confirmed"
    if _NON_CANCER_SERVICE_CONTEXT.search(text):
        return "unrelated"
    return "possible"


@dataclass(frozen=True)
class CareObstructionMatch:
    """Result of scanning one episode's window for care-obstruction evidence.

    Attributes:
        recorded:        Convenience boolean — ``True`` when ``signal``
                         is anything other than ``"none"``.  This is the
                         field the dashboard tile reads.
        signal:          Strongest signal found across pathway-related
                         encounters, in the hierarchy
                         rejection > dna > cancellation > access_barrier
                         > none.  ``unrelated``-classified events do
                         NOT contribute to this signal.
        type_counts:     Mapping of obstruction type to number of
                         pathway-related encounters in the window that
                         produced that signal.  Useful for the
                         dashboard breakdown dialog.  Keys are the
                         literal signal names (``"rejection"``,
                         ``"dna"``, ...) and values are the count of
                         encounters in that bucket.
        evidence_count:  Total number of encounter rows that produced
                         at least one pathway-related obstruction
                         hit.  ``<= sum(type_counts.values())``
                         because per-encounter signals collapse to
                         the strongest type.
        confirmed_count: Subset of ``evidence_count`` where the
                         encounter text contained an explicit cancer-
                         pathway marker (2WW, FTR, oncology, MDT,
                         site-specific specialty).  These are the
                         events a clinician would unambiguously agree
                         delayed THIS pathway.
        unrelated_filtered_count:
                         Number of encounter rows that produced an
                         obstruction phrase but were classified as
                         ``unrelated`` (clearly from a non-cancer
                         service: midwife, phlebotomy, district
                         nurse, cardiac rehab, UTC, etc.) and so are
                         NOT reflected in ``signal`` /
                         ``type_counts`` / ``evidence_count``.
                         Surfaced for telemetry so the dashboard can
                         show "X events filtered as unrelated".
        codes:           Distinct EMIS Read codes detected on
                         pathway-related encounters
                         (``["XaQgL", "XacSG", ...]``), sorted for
                         stable output.
        phrases:         Distinct free-text phrases detected on
                         pathway-related encounters, lowercased and
                         sorted.
    """

    recorded: bool
    signal: CareObstructionSignal
    type_counts: dict[str, int] = field(default_factory=dict)
    evidence_count: int = 0
    confirmed_count: int = 0
    unrelated_filtered_count: int = 0
    codes: tuple[str, ...] = field(default_factory=tuple)
    phrases: tuple[str, ...] = field(default_factory=tuple)


_SIGNAL_RANK: dict[CareObstructionSignal, int] = {
    "none": 0,
    "access_barrier": 1,
    "cancellation": 2,
    "dna": 3,
    "rejection": 4,
}


def _scan_one(
    text: str, flags: str | None = None
) -> tuple[CareObstructionSignal, list[str], list[str]]:
    """Classify a single encounter.  Returns ``(signal, codes, phrases)``.

    ``flags`` is the EMIS encounter ``flags`` field (e.g. ``"DNA"`` /
    ``"Letter\\nThis event was back-dated..."``).  When ``flags`` carries
    the literal token ``DNA``, that's a strong DNA signal even when the
    text body is empty.
    """
    t = text or ""
    flag_str = flags or ""
    codes: list[str] = []
    phrases: list[str] = []

    # --- Rejection (highest priority) ---
    rejection_hits = []
    for pat in _REJECTION_PATTERNS:
        for m in pat.finditer(t):
            hit = m.group(0).strip()
            if _REJECTION_NOISE.search(t):
                # Skip if the only rejection phrase is a duplicate /
                # out-of-area admin housekeeping line (not cancer related).
                continue
            rejection_hits.append(hit)
    if rejection_hits:
        for h in rejection_hits:
            if re.fullmatch(r"[A-Za-z0-9]{4,7}", h):
                codes.append(h)
            else:
                phrases.append(h.lower())
        return "rejection", codes, phrases

    # --- DNA ---
    has_dna_flag = bool(re.search(r"\bDNA\b", flag_str))
    dna_hits = []
    if not _DNA_RETRACTED.search(t):
        for pat in _DNA_PATTERNS:
            for m in pat.finditer(t):
                dna_hits.append(m.group(0).strip())
    if has_dna_flag or dna_hits:
        for h in dna_hits:
            if re.fullmatch(r"[A-Za-z0-9]{4,7}", h):
                codes.append(h)
            else:
                phrases.append(h.lower())
        if has_dna_flag and not dna_hits:
            phrases.append("dna (encounter flag)")
        return "dna", codes, phrases

    # --- Cancellation ---
    cancel_hits = []
    for pat in _CANCELLATION_PATTERNS:
        for m in pat.finditer(t):
            cancel_hits.append(m.group(0).strip())
    if cancel_hits:
        phrases.extend(h.lower() for h in cancel_hits)
        return "cancellation", codes, phrases

    # --- Access barrier (lowest) ---
    barrier_hits = []
    for pat in _ACCESS_BARRIER_PATTERNS:
        for m in pat.finditer(t):
            barrier_hits.append(m.group(0).strip())
    if barrier_hits:
        phrases.extend(h.lower() for h in barrier_hits)
        return "access_barrier", codes, phrases

    return "none", codes, phrases


def detect_care_obstructions(
    events: Iterable[tuple[str, str | None] | str],
    cancer_type: str | None = None,
) -> CareObstructionMatch:
    """Scan a collection of encounter events for care-obstruction evidence.

    Pass every encounter in the episode's referral-anchored window.
    Each event may be either:

      - A ``(text, flags)`` tuple — preferred, because the EMIS
        ``flags`` field is the most reliable DNA marker.
      - A bare ``text`` string — backward-compatible; flags treated
        as ``None``.

    ``cancer_type`` is optional but strongly recommended.  When
    supplied, site-specific positive markers (e.g. "dermatology" for
    melanoma, "urology" for prostate) extend the "confirmed cancer
    pathway" check, so an obstruction at the right specialty clinic
    is correctly classified as confirmed-related rather than left as
    "possible".  See :func:`_classify_relatedness` for the rules.

    Encounters classified as ``"unrelated"`` (clearly from a non-
    cancer service AND no positive cancer markers) are EXCLUDED from
    the headline signal and counted separately as
    ``unrelated_filtered_count`` on the result, so the dashboard can
    show "9 DNAs in window — 3 filtered as midwife / district-nurse
    appointments".

    The return value is the strongest signal across pathway-related
    events.  ``type_counts`` exposes per-bucket counts and
    ``confirmed_count`` flags how many of those came with explicit
    cancer-pathway markers.
    """
    best: CareObstructionSignal = "none"
    type_counts: dict[str, int] = {
        "rejection": 0,
        "dna": 0,
        "cancellation": 0,
        "access_barrier": 0,
    }
    evidence_count = 0
    confirmed_count = 0
    unrelated_filtered_count = 0
    all_codes: set[str] = set()
    all_phrases: set[str] = set()

    for ev in events:
        if ev is None:
            continue
        if isinstance(ev, str):
            text, flags = ev, None
        else:
            text, flags = ev

        sig, codes, phrases = _scan_one(text or "", flags)
        if sig == "none":
            continue
        # Apply pathway-relatedness filter.  Encounters classified as
        # "unrelated" are dropped from the main signal (they would
        # otherwise inflate the headline with midwife / phlebotomy /
        # community-DN noise) but counted separately for telemetry.
        relatedness = _classify_relatedness(text or "", cancer_type)
        if relatedness == "unrelated":
            unrelated_filtered_count += 1
            continue

        evidence_count += 1
        type_counts[sig] = type_counts.get(sig, 0) + 1
        if relatedness == "confirmed":
            confirmed_count += 1
        if _SIGNAL_RANK[sig] > _SIGNAL_RANK[best]:
            best = sig
        all_codes.update(codes)
        all_phrases.update(phrases)

    return CareObstructionMatch(
        recorded=best != "none",
        signal=best,
        type_counts=type_counts,
        evidence_count=evidence_count,
        confirmed_count=confirmed_count,
        unrelated_filtered_count=unrelated_filtered_count,
        codes=tuple(sorted(all_codes)),
        phrases=tuple(sorted(all_phrases)),
    )


__all__ = [
    "CareObstructionMatch",
    "CareObstructionSignal",
    "PathwayRelatedness",
    "detect_care_obstructions",
]
