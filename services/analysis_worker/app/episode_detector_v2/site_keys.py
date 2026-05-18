"""Canonical site keys and per-site activation registry.

Atlas trace:
  DI: DI-8A5FCF4F
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-8A5FCF4F")

A site is **auto-eligible** only when its real signal extractors and
candidate generators have been built and the regression-cohort
precision exceeds the per-site activation threshold (currently >= 0.95
across the labelled cohort, subject to Clinical Safety Officer
sign-off).

Sites that are not auto-eligible silently produce zero candidate
episodes -- the detector returns a fail-safe empty list rather than
guessing. Mission Control manual curation remains the source of
episodes for those sites.
"""

from __future__ import annotations

from dataclasses import dataclass

# Canonical site keys -- match libs/oncology and the legacy site_resolution.
SITE_BREAST = "breast"
SITE_UPPER_GI = "upper_gi"
SITE_LUNG = "lung"
SITE_LOWER_GI = "lower_gi"
SITE_GYNAE = "gynae"
SITE_HEAD_NECK = "head_neck"
SITE_HAEMATOLOGY = "haematology"
SITE_SKIN = "skin"
SITE_PROSTATE_UROLOGICAL = "prostate_urological"
SITE_BRAIN_CNS = "brain_cns"
SITE_UNKNOWN = "unknown"

ALL_SITES = (
    SITE_BREAST,
    SITE_UPPER_GI,
    SITE_LUNG,
    SITE_LOWER_GI,
    SITE_GYNAE,
    SITE_HEAD_NECK,
    SITE_HAEMATOLOGY,
    SITE_SKIN,
    SITE_PROSTATE_UROLOGICAL,
    SITE_BRAIN_CNS,
)


@dataclass(frozen=True)
class SiteActivation:
    """Whether a site is auto-eligible and at which confidence tier."""

    site_key: str
    auto_publish: bool
    suggest: bool


# As of v1 of v2: only breast is auto-eligible. Other sites are
# review-only (suggest=False, auto_publish=False) so the detector
# returns zero auto-episodes for them.
ACTIVATION: dict[str, SiteActivation] = {
    SITE_BREAST: SiteActivation(SITE_BREAST, auto_publish=True, suggest=True),
    SITE_UPPER_GI: SiteActivation(SITE_UPPER_GI, auto_publish=False, suggest=False),
    SITE_LUNG: SiteActivation(SITE_LUNG, auto_publish=False, suggest=False),
    SITE_LOWER_GI: SiteActivation(SITE_LOWER_GI, auto_publish=False, suggest=False),
    SITE_GYNAE: SiteActivation(SITE_GYNAE, auto_publish=False, suggest=False),
    SITE_HEAD_NECK: SiteActivation(SITE_HEAD_NECK, auto_publish=False, suggest=False),
    SITE_HAEMATOLOGY: SiteActivation(
        SITE_HAEMATOLOGY, auto_publish=False, suggest=False
    ),
    SITE_SKIN: SiteActivation(SITE_SKIN, auto_publish=False, suggest=False),
    SITE_PROSTATE_UROLOGICAL: SiteActivation(
        SITE_PROSTATE_UROLOGICAL, auto_publish=False, suggest=False
    ),
    SITE_BRAIN_CNS: SiteActivation(SITE_BRAIN_CNS, auto_publish=False, suggest=False),
}


def is_auto_eligible(site_key: str) -> bool:
    """Return True if the site can be auto-published.

    Reads the champion rulebook from the installed bundle (see
    libs/episode_detector/loader.py). Falls back to the Python-constant
    ``ACTIVATION`` table when no rulebook is installed for the site --
    this happens in tests that don't initialise the bundle and in the
    bootstrap path before the registry has loaded.
    """
    from ._rulebook_adapter import auto_publish_for  # local to avoid cycle

    record = ACTIVATION.get(site_key.lower())
    return auto_publish_for(
        site_key.lower(),
        fallback=bool(record and record.auto_publish),
    )


def is_suggest_eligible(site_key: str) -> bool:
    """Return True if candidates for this site should be surfaced
    (even if only as a review-only suggestion). Reads the champion
    rulebook; see ``is_auto_eligible`` for the fallback contract.
    """
    from ._rulebook_adapter import suggest_for  # local to avoid cycle

    record = ACTIVATION.get(site_key.lower())
    return suggest_for(
        site_key.lower(),
        fallback=bool(record and record.suggest),
    )


# Breast-specific SNOMED concept ids used by the real extractors.
# Kept here so the breast modules import a single source of truth.
BREAST_SNOMED_SUSPECTED = frozenset(
    {
        "134405005",  # Suspected breast cancer (situation)
        "395557000",  # Tumour of breast (disorder)
        "395557000",
        "126926006",
        "188153005",
    }
)
BREAST_SNOMED_CONFIRMED = frozenset(
    {
        "254837009",  # Malignant neoplasm of breast (disorder)
        "1701000119104",  # Carcinoma of left breast
        "1711000119102",  # Carcinoma of right breast
        "109888004",  # DCIS
        "109889007",  # Lobular carcinoma in situ
        "408643008",  # Infiltrating duct carcinoma of breast
        "713609000",  # Invasive carcinoma of breast
    }
)
BREAST_SNOMED_BENIGN_CLOSURE = frozenset(
    {
        "266569009",  # No abnormality detected (finding)
        "260385009",  # Negative
        "162467007",  # No anomaly detected
        "281900007",  # No abnormality detected on examination
    }
)


# -- Cross-site referral registry ------------------------------------------
# Maps the SNOMED concept id of a "Fast track referral for suspected X
# cancer (procedure)" to the canonical site key. Used by the normaliser
# to synthesise a ``referral_form`` dict so the existing pathway-channel
# extractor can pick the encounter up without changing its public
# contract.
#
# Pulled from the live patient graph (NHS England 2WW codes). Where a
# more specific 2WW SNOMED is added, append it here -- the registry is
# the single source of truth for "what counts as a 2WW referral".
REFERRAL_SNOMED_TO_SITE: dict[str, str] = {
    "276341000000100": SITE_BREAST,  # Fast track ref breast
    "276551000000108": SITE_UPPER_GI,  # Fast track ref upper GI
    "276391000000105": SITE_LOWER_GI,  # Fast track ref lower GI
    "276401000000108": SITE_LUNG,  # Fast track ref lung
    "276431000000102": SITE_PROSTATE_UROLOGICAL,  # Fast track ref urological
    "276411000000105": SITE_GYNAE,  # Fast track ref gynae
    "276421000000104": SITE_HEAD_NECK,  # Fast track ref head/neck
    "280521000000108": SITE_HEAD_NECK,  # Fast track ref suspected head/neck
    "276441000000106": SITE_SKIN,  # Fast track ref skin
    "276361000000104": SITE_HAEMATOLOGY,  # Fast track ref haematology
    "276371000000106": SITE_BRAIN_CNS,  # Fast track ref brain/CNS
}


# Maps "Seen in fast track suspected X cancer clinic (finding)" SNOMED
# ids to the canonical site key. These are first-clinic-seen events --
# they confirm the referral was acted on and provide a strong end-to-end
# pathway signal even when no separate referral form survives the
# extraction.
CLINIC_SEEN_SNOMED_TO_SITE: dict[str, str] = {
    "382431000000103": SITE_BREAST,
    "382811000000108": SITE_UPPER_GI,
    "382841000000109": SITE_PROSTATE_UROLOGICAL,
    "382621000000103": SITE_HEAD_NECK,
    # Lower-GI / lung / gynae / etc clinic-seen codes are added as we
    # encounter them in the live graph; until then the corresponding
    # encounters fall back to the code/text channels for evidence.
}


def site_for_referral_concept(concept_id: str) -> str | None:
    """Return the canonical site key for a 2WW referral concept, or None.

    Checks the champion rulebooks first -- any site whose
    ``anchors.referral_snomed`` lists this concept id wins -- and falls
    back to the baked-in Python registry for sites without a rulebook
    or running in tests that bypass the bundle.
    """
    from ._rulebook_adapter import anchor_referral_snomed

    cid = (concept_id or "").strip()
    if not cid:
        return None
    for site in ALL_SITES:
        if cid in anchor_referral_snomed(site):
            return site
    return REFERRAL_SNOMED_TO_SITE.get(cid)


def site_for_clinic_seen_concept(concept_id: str) -> str | None:
    """Return the canonical site key for a 'seen in fast track clinic' code.

    See ``site_for_referral_concept`` for the rulebook-first fallback
    contract. Clinic-seen codes live on
    ``anchors.clinic_seen_snomed`` in the v1 rulebooks.
    """
    from libs.episode_detector.loader import current_bundle

    cid = (concept_id or "").strip()
    if not cid:
        return None
    try:
        bundle = current_bundle()
        for site in ALL_SITES:
            rb = bundle.get(site)
            if rb is None:
                continue
            if cid in rb.anchors.clinic_seen_snomed:
                return site
    except Exception:
        pass
    return CLINIC_SEEN_SNOMED_TO_SITE.get(cid)


# -- Cross-site "suspected cancer" SNOMED registry -------------------------
# Maps SNOMED situation/disorder codes for "suspected <site> cancer" or
# "malignant neoplasm of <site>" to the canonical site key. Used by
# ``code_channel`` to emit a suspected/confirmed signal for every site
# (not just breast). For stub sites this still produces no auto
# episodes -- but the coverage check now sees the encounter, so the
# silent-drop fail-safe correctly flags it for human review.
SUSPECTED_SITE_SNOMED: dict[str, tuple[str, str]] = {
    # (concept_id) -> (site_key, intent)
    # Lung
    "162573006": (SITE_LUNG, "suspected"),  # Suspected lung cancer
    "254637007": (SITE_LUNG, "confirmed"),  # Non-small cell lung cancer
    "254632001": (SITE_LUNG, "confirmed"),  # Small cell lung cancer
    "363358000": (SITE_LUNG, "confirmed"),  # Malignant neoplasm of lung
    "363504009": (SITE_LUNG, "confirmed"),  # Carcinoma of lung
    # Upper GI (oesophagus / stomach)
    "162574000": (SITE_UPPER_GI, "suspected"),  # Suspected upper GI cancer (situation)
    "315266007": (SITE_UPPER_GI, "suspected"),  # Suspected stomach cancer
    "363402007": (SITE_UPPER_GI, "confirmed"),  # Malignant neoplasm of stomach
    "363349007": (SITE_UPPER_GI, "confirmed"),  # Malignant neoplasm of oesophagus
    "16013000": (SITE_UPPER_GI, "confirmed"),  # Carcinoma of oesophagus
    # Lower GI (colon / rectum)
    "162575004": (SITE_LOWER_GI, "suspected"),  # Suspected lower GI cancer
    "363406005": (SITE_LOWER_GI, "confirmed"),  # Malignant neoplasm of colon
    "363351006": (SITE_LOWER_GI, "confirmed"),  # Malignant neoplasm of rectum
    "254582000": (SITE_LOWER_GI, "confirmed"),  # Adenocarcinoma of rectum
    "255081007": (SITE_LOWER_GI, "confirmed"),  # Carcinoma of cecum
    "255084004": (SITE_LOWER_GI, "confirmed"),  # SCC anal margin
    # Prostate / urological
    "315268008": (SITE_PROSTATE_UROLOGICAL, "suspected"),  # Suspected prostate cancer
    "399068003": (SITE_PROSTATE_UROLOGICAL, "confirmed"),  # Mal neo of prostate
    "254900004": (SITE_PROSTATE_UROLOGICAL, "confirmed"),  # Carcinoma prostate
    "363448003": (SITE_PROSTATE_UROLOGICAL, "confirmed"),  # Malignant tumor prostate
    "254915003": (SITE_PROSTATE_UROLOGICAL, "confirmed"),  # Clear cell kidney ca
    "126885006": (SITE_PROSTATE_UROLOGICAL, "confirmed"),  # Bladder neoplasm
    "363455001": (SITE_PROSTATE_UROLOGICAL, "confirmed"),  # Malignant bladder tumor
    "255109008": (
        SITE_PROSTATE_UROLOGICAL,
        "confirmed",
    ),  # Transitional cell bladder ca
    # Gynae
    "315267003": (SITE_GYNAE, "suspected"),  # Suspected gynaecological cancer
    "363354007": (SITE_GYNAE, "confirmed"),  # Malignant neoplasm of cervix
    "363443007": (SITE_GYNAE, "confirmed"),  # Malignant neoplasm of ovary
    "254878006": (SITE_GYNAE, "confirmed"),  # Endometrial carcinoma
    "188192002": (SITE_GYNAE, "confirmed"),  # Malignant neoplasm endometrium
    "1260086007": (SITE_GYNAE, "confirmed"),  # Endometrioid carcinoma endometrium
    "254887002": (SITE_GYNAE, "confirmed"),  # Adenocarcinoma cervix
    "254863004": (SITE_GYNAE, "confirmed"),  # Malignant granulosa cell tumor ovary
    # Head and neck
    "315264005": (SITE_HEAD_NECK, "suspected"),  # Suspected head/neck cancer
    "363375008": (SITE_HEAD_NECK, "confirmed"),  # Malignant neoplasm of larynx
    "254437001": (SITE_HEAD_NECK, "confirmed"),  # SCC buccal mucosa
    "363478007": (SITE_HEAD_NECK, "confirmed"),  # Malignant thyroid neoplasm
    "255029007": (SITE_HEAD_NECK, "confirmed"),  # Papillary thyroid carcinoma
    # Skin
    "276751004": (SITE_SKIN, "suspected"),  # Suspected skin cancer (melanoma)
    "372244006": (SITE_SKIN, "confirmed"),  # Malignant melanoma
    "310498001": (SITE_SKIN, "confirmed"),  # Malignant melanoma of back
    "302837001": (SITE_SKIN, "confirmed"),  # Lentigo maligna melanoma
    "402815007": (SITE_SKIN, "confirmed"),  # Squamous cell carcinoma
    "254651007": (SITE_SKIN, "confirmed"),  # Squamous cell carcinoma of skin
    # Haematology
    "162576003": (SITE_HAEMATOLOGY, "suspected"),  # Suspected haematological cancer
    "93143009": (SITE_HAEMATOLOGY, "confirmed"),  # Leukaemia
    "118600007": (SITE_HAEMATOLOGY, "confirmed"),  # Lymphoma
    "92814006": (SITE_HAEMATOLOGY, "confirmed"),  # Chronic lymphoid leukaemia
    "302841002": (SITE_HAEMATOLOGY, "confirmed"),  # Small lymphocytic lymphoma
    "425333006": (SITE_HAEMATOLOGY, "confirmed"),  # Myeloproliferative disorder
    # Brain / CNS
    "315278009": (SITE_BRAIN_CNS, "suspected"),  # Suspected brain tumour
    "428061005": (SITE_BRAIN_CNS, "confirmed"),  # Malignant neoplasm of brain
}


def site_intent_for_suspected_concept(
    concept_id: str,
) -> tuple[str, str] | None:
    """Return (site_key, intent) for a known suspected/confirmed cancer SNOMED.

    Rulebook-first: walks every installed champion rulebook and returns
    the first match on ``anchors.confirmed_snomed`` (intent
    ``"confirmed"``) or ``anchors.suspected_snomed`` (intent
    ``"suspected"``). Falls back to the Python registry for sites
    without a rulebook. Breast keeps the first-match semantics the
    legacy code already had: the breast classify path in
    ``code_channel`` is called before this lookup, so breast-specific
    tuning is unchanged.

    A SNOMED listed on a site's ``cross_site_guard`` never wins for
    that site -- prevents cross-site leakage (R-5FA0C950).
    """
    from libs.episode_detector.loader import current_bundle

    cid = (concept_id or "").strip()
    if not cid:
        return None
    try:
        bundle = current_bundle()
        for site in ALL_SITES:
            rb = bundle.get(site)
            if rb is None:
                continue
            if cid in rb.cross_site_guard:
                continue
            if cid in rb.anchors.confirmed_snomed:
                return site, "confirmed"
            if cid in rb.anchors.suspected_snomed:
                return site, "suspected"
    except Exception:
        pass
    return SUSPECTED_SITE_SNOMED.get(cid)
