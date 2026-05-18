"""Text-channel signal extractor tests.

Atlas trace:
  VT (to be created): text-channel regex catalogue coverage

The text channel reads the champion rulebook's
``signals.text_channel.regex_catalogue`` and emits a low-confidence
``Signal(channel="text")`` per (encounter, site) when an encounter's
``text_snippet`` matches a pattern. These tests lock the contract:

1. A plain-text mention of "breast lump" emits a breast signal, and
   does not emit signals for other sites.
2. Multiple sites can fire on the same encounter when the text
   genuinely mentions both (e.g. a case summary mentioning prostate
   and breast would be flagged for both).
3. An encounter with no text emits nothing.
4. The extractor tolerates an empty bundle (fail-safe).
5. Malformed regex strings in the bundle do not raise.
6. Confidence is the documented 0.55 so the voting layer's
   diversity requirement still blocks text-alone auto-publishing.
"""

from __future__ import annotations

from datetime import date

import pytest

from libs.episode_detector.loader import (
    load_default_bundle,
    override_sites,
    set_current_bundle,
)
from libs.episode_detector.rulebook import (
    SiteRulebook,
    Signals,
    TextChannel,
)
from services.analysis_worker.app.episode_detector_v2 import _rulebook_adapter
from services.analysis_worker.app.episode_detector_v2.signals.text_channel import (
    extract_text_signals,
)
from services.analysis_worker.app.episode_detector_v2.types import TimelineEvent


@pytest.fixture(autouse=True)
def _install_default_bundle():
    """Every test runs against the shipped default bundle (v0 + v1 where
    curated). The bundle is replaced on each test so monkey-patches
    never leak."""
    from libs.episode_detector import loader
    from pathlib import Path

    bundle = load_default_bundle()
    overrides: dict[str, SiteRulebook] = {}
    for path in sorted(Path(loader.DEFAULTS_DIR).glob("*.v1.json")):
        rb = loader.load_rulebook(path)
        overrides[rb.site_key] = rb
    bundle = override_sites(bundle, overrides)
    set_current_bundle(bundle)
    _rulebook_adapter.clear_cache()
    yield
    set_current_bundle(load_default_bundle())
    _rulebook_adapter.clear_cache()


def _event(encounter_id: str, text: str) -> TimelineEvent:
    return TimelineEvent(
        encounter_id=encounter_id,
        occurred_on=date(2025, 1, 1),
        event_kind="encounter",
        text_snippet=text,
    )


def test_breast_lump_fires_breast_signal_only():
    events = [_event("enc-1", "Patient reports a new lump in breast, tender.")]
    signals = extract_text_signals(events)
    breast = [s for s in signals if s.site_key == "breast"]
    assert breast, "expected a breast text signal for 'lump in breast'"
    assert all(s.channel == "text" for s in breast)
    assert all(s.intent == "suspected" for s in breast)
    assert all(s.confidence == pytest.approx(0.55) for s in breast)
    assert all(s.role == "diagnosis" for s in breast)
    # No false-positive sites should fire on a pure breast phrase.
    other_sites = {s.site_key for s in signals if s.site_key != "breast"}
    assert (
        other_sites == set()
    ), f"unexpected sites fired on 'lump in breast' text: {other_sites}"


def test_neck_2ww_with_background_breast_history_does_not_fire_breast_signal():
    events = [
        _event(
            "enc-1",
            "Refer re neck - ?2ww neck as has breast cancer ??relevant "
            "?skin based - hard to be sure",
        )
    ]

    signals = extract_text_signals(events)

    breast_signals = [s for s in signals if s.site_key == "breast"]
    head_neck_signals = [s for s in signals if s.site_key == "head_neck"]
    assert breast_signals == []
    assert head_neck_signals


def test_hrt_screening_background_does_not_fire_breast_signal():
    events = [
        _event(
            "enc-1",
            "Hormone replacement therapy review. HRT questionnaire. "
            "Breast screening up to date: Yes. "
            "Family history of breast cancer: No.",
        )
    ]

    signals = extract_text_signals(events)

    assert [s for s in signals if s.site_key == "breast"] == []


def test_menopause_breast_cancer_risk_discussion_does_not_fire_breast_signal():
    events = [
        _event(
            "enc-1",
            "Problem: Menopausal symptoms. Discussed HRT patches. "
            "Patient worried about breast cancer and risk of breast cancer. "
            "History of breast cyst checked by breast clinic previously.",
        )
    ]

    signals = extract_text_signals(events)

    assert [s for s in signals if s.site_key == "breast"] == []


def test_hrt_anxiety_followup_with_old_breast_lump_issue_does_not_fire_breast_signal():
    events = [
        _event(
            "enc-1",
            "History: anxiety and perimenopause. Has tried HRT patches but "
            "didn't help much - had to stop this due to issues with breast lump.",
        )
    ]

    signals = extract_text_signals(events)

    assert [s for s in signals if s.site_key == "breast"] == []


def test_negative_throat_review_does_not_fire_head_neck_signal():
    events = [
        _event(
            "enc-1",
            "Problem: C/O: a rash. History: Rash all over body. "
            "No cough or cold symptoms. Throat not sore. Pink urticarial rash.",
        )
    ]

    signals = extract_text_signals(events)

    assert [s for s in signals if s.site_key == "head_neck"] == []


def test_empty_text_emits_nothing():
    assert extract_text_signals([_event("enc-1", "")]) == []


def test_multi_site_mention_fires_both():
    events = [
        _event(
            "enc-1",
            "GP letter: referred for suspected breast lump and raised PSA.",
        )
    ]
    signals = extract_text_signals(events)
    site_keys = {s.site_key for s in signals}
    assert "breast" in site_keys
    assert "prostate_urological" in site_keys


def test_no_matches_returns_empty():
    events = [_event("enc-1", "Routine blood pressure check, no concerns.")]
    signals = extract_text_signals(events)
    assert signals == []


def test_empty_catalogue_is_safe():
    # Install a bundle where every site has an empty text catalogue.
    bundle = load_default_bundle()
    overrides = {}
    for site_key, rb in bundle.sites.items():
        overrides[site_key] = SiteRulebook(
            site_key=rb.site_key,
            rulebook_version=rb.rulebook_version,
            schema_version=rb.schema_version,
            signals=Signals(
                code_channel=rb.signals.code_channel,
                text_channel=TextChannel(regex_catalogue=()),
                pathway_channel=rb.signals.pathway_channel,
                result_channel=rb.signals.result_channel,
                treatment_channel=rb.signals.treatment_channel,
            ),
            anchors=rb.anchors,
            closure=rb.closure,
            cross_site_guard=rb.cross_site_guard,
            windows=rb.windows,
            activation=rb.activation,
            tier_thresholds=rb.tier_thresholds,
            scorer_weights=rb.scorer_weights,
        )
    set_current_bundle(override_sites(bundle, overrides))
    _rulebook_adapter.clear_cache()
    events = [_event("enc-1", "Patient reports a new lump in breast.")]
    assert extract_text_signals(events) == []


def test_bad_regex_is_skipped_not_raised():
    bundle = load_default_bundle()
    rb = bundle.get("breast")
    assert rb is not None
    bad_rb = SiteRulebook(
        site_key=rb.site_key,
        rulebook_version=rb.rulebook_version,
        schema_version=rb.schema_version,
        signals=Signals(
            code_channel=rb.signals.code_channel,
            text_channel=TextChannel(
                regex_catalogue=(
                    r"\b(breast\b",  # unbalanced paren
                    r"\bmammogra\w*",
                )
            ),
            pathway_channel=rb.signals.pathway_channel,
            result_channel=rb.signals.result_channel,
            treatment_channel=rb.signals.treatment_channel,
        ),
        anchors=rb.anchors,
        closure=rb.closure,
        cross_site_guard=rb.cross_site_guard,
        windows=rb.windows,
        activation=rb.activation,
        tier_thresholds=rb.tier_thresholds,
        scorer_weights=rb.scorer_weights,
    )
    set_current_bundle(override_sites(bundle, {"breast": bad_rb}))
    _rulebook_adapter.clear_cache()

    events = [_event("enc-1", "Post-mammography appointment booked.")]
    signals = extract_text_signals(events)
    # The good regex still matched; the bad one was skipped.
    assert any(s.site_key == "breast" for s in signals)


def test_citation_truncates_long_matches():
    events = [
        _event(
            "enc-1",
            "Very long text mentioning breast " + "x" * 100 + " and more.",
        )
    ]
    signals = extract_text_signals(events)
    breast = [s for s in signals if s.site_key == "breast"]
    assert breast
    for s in breast:
        assert len(s.citation) <= len("Text mention: '") + 60 + 2


def test_every_auto_eligible_site_has_at_least_one_regex():
    """Promotion gate: a site that ships with a v1 rulebook must have
    a non-empty text_channel regex catalogue. A text-only dry-run is
    the canonical triage pathway and it must fire for every auto-
    eligible site, otherwise coding-triage precision drops silently.
    """
    bundle = load_default_bundle()
    from pathlib import Path
    from libs.episode_detector.loader import DEFAULTS_DIR, load_rulebook

    for path in sorted(Path(DEFAULTS_DIR).glob("*.v1.json")):
        rb = load_rulebook(path)
        assert (
            rb.signals.text_channel.regex_catalogue
        ), f"{rb.site_key} v1 has empty text_channel.regex_catalogue"
    # v0 rulebooks too: every site in site_keys.ALL_SITES must have
    # at least one pattern so detector-first coding triage covers the
    # whole device portfolio.
    from services.analysis_worker.app.episode_detector_v2 import (
        site_keys as sk,
    )

    for site in sk.ALL_SITES:
        rb = bundle.get(site)
        assert rb is not None, f"no default rulebook for {site}"
        assert (
            rb.signals.text_channel.regex_catalogue
        ), f"{site} default rulebook has empty text_channel.regex_catalogue"


# ----------------------------------------------------------------------
# Context-milestone signals (DI-2C015ADE)
# ----------------------------------------------------------------------


def test_context_signal_emitted_for_primary_care_investigations():
    """A GP letter mentioning 'FBC' should fire a context_milestone
    signal tagged primary_care_investigations for every installed
    site (the context catalogue is site-scoped but generic primary-
    care language intentionally fires across sites)."""
    events = [_event("enc-1", "FBC and LFTs arranged, awaiting results.")]
    signals = extract_text_signals(events)
    context = [s for s in signals if s.role == "context_milestone"]
    assert context, "expected context_milestone signals on FBC/LFT text"
    pc = [s for s in context if s.context_tag == "primary_care_investigations"]
    assert pc, "expected primary_care_investigations context tag"
    # Every context signal carries the right intent + confidence.
    for s in pc:
        assert s.channel == "text"
        assert s.intent == "suggested"
        assert s.confidence == pytest.approx(0.55)
        assert s.citation.startswith("Context mention: '")


def test_specialist_diagnostics_is_site_specific():
    """'colonoscopy' is site-specific. Only lower_gi should fire the
    specialist_diagnostics context tag on this text; other sites must
    not emit a specialist_diagnostics signal for the same snippet."""
    events = [_event("enc-1", "Flexible sigmoidoscopy scheduled next week.")]
    signals = extract_text_signals(events)
    diag = [
        s
        for s in signals
        if s.role == "context_milestone" and s.context_tag == "specialist_diagnostics"
    ]
    assert diag, "expected a specialist_diagnostics context signal"
    sites = {s.site_key for s in diag}
    assert sites == {"lower_gi"}, f"expected only lower_gi to fire, got {sites}"


def test_referral_sent_fires_for_2ww_language():
    events = [
        _event(
            "enc-1",
            "2WW referral sent under suspected cancer pathway.",
        )
    ]
    signals = extract_text_signals(events)
    ref = [
        s
        for s in signals
        if s.role == "context_milestone" and s.context_tag == "referral_sent"
    ]
    assert ref, "2WW referral language should raise referral_sent signals"
    # The generic referral_sent pattern is shared across sites so
    # multiple sites are expected to fire (dedup happens later, in
    # the episode_engine consumer and voting layers).
    assert len({s.site_key for s in ref}) >= 1


def test_context_catalogue_promotion_gate_all_sites_all_tags():
    """Every installed site must carry a non-empty catalogue for
    each of the seven canonical context-tier milestone tags. The
    gate guards against a site shipping without one of the seven
    context surfaces wired, which would silently drop that class of
    reviewer evidence."""
    from libs.episode_detector.loader import DEFAULTS_DIR, load_rulebook
    from libs.episode_detector.rulebook import CONTEXT_MILESTONE_TAGS
    from pathlib import Path
    from services.analysis_worker.app.episode_detector_v2 import (
        site_keys as sk,
    )

    assert len(CONTEXT_MILESTONE_TAGS) == 7
    for site in sk.ALL_SITES:
        paths = sorted(Path(DEFAULTS_DIR).glob(f"{site}.v*.json"))
        assert paths, f"no rulebook files for {site}"
        # Every rulebook for the site (v0 and, where shipped, v1)
        # must carry the seven-tag context catalogue in full.
        for path in paths:
            rb = load_rulebook(path)
            cat = rb.signals.text_channel.context_role_catalogue
            for tag in CONTEXT_MILESTONE_TAGS:
                patterns = cat.get(tag) or ()
                assert patterns, f"{path.name} missing context_role_catalogue[{tag!r}]"


def test_diagnosis_and_context_signals_coexist_without_collision():
    """An encounter mentioning both site-specific language and a
    generic primary-care investigation must emit BOTH a diagnosis
    signal (for the site) and a context_milestone signal -- they do
    not clobber each other."""
    events = [
        _event(
            "enc-1",
            "GP appointment for suspected breast lump; bloods taken.",
        )
    ]
    signals = extract_text_signals(events)
    diag = [s for s in signals if s.role == "diagnosis" and s.site_key == "breast"]
    ctx = [s for s in signals if s.role == "context_milestone"]
    assert diag, "expected a breast diagnosis text signal"
    assert ctx, "expected at least one context_milestone signal"
    # context_tag is populated on context signals only.
    assert all(s.context_tag for s in ctx)
    assert all(not s.context_tag for s in diag)


def test_exclusion_catalogue_suppresses_normal_screening_signal():
    """NHS Breast Screening Programme normal result must NOT produce a
    breast diagnosis signal even though the text contains 'breast'.

    The exclusion_catalogue in the breast rulebook gates the text channel
    so that routine-normal-screening encounters never seed a false episode.
    This test uses the v1 breast rulebook which carries the exclusion list.
    """
    from libs.episode_detector.loader import DEFAULTS_DIR, load_rulebook, override_sites

    breast_v1 = load_rulebook(DEFAULTS_DIR / "breast.v1.json")
    bundle = override_sites(load_default_bundle(), {"breast": breast_v1})
    set_current_bundle(bundle)
    _rulebook_adapter.clear_cache()

    normal_text = (
        "As per GP report list from the NHS Breast Screening Programme.\n"
        "Breast neoplasm screening normal (68620)"
    )
    events = [_event("excl-001", normal_text)]
    signals = extract_text_signals(events)

    breast_text = [s for s in signals if s.site_key == "breast"]
    assert not breast_text, (
        "Normal breast screening encounter must NOT emit ANY breast text "
        "signal (diagnosis or context) -- the NHS BSP line also matches "
        "referral_sent; suppressing only diagnosis would still pollute "
        "the pathway. Later encounters (recall, malignant code) are "
        "unaffected."
    )


def test_exclusion_catalogue_does_not_suppress_abnormal_screening_signal():
    """The exclusion catalogue must NOT suppress abnormal screening results.

    'Breast neoplasm screening abnormal' is the episode trigger; only
    the 'normal' variant is excluded.
    """
    from libs.episode_detector.loader import DEFAULTS_DIR, load_rulebook, override_sites

    breast_v1 = load_rulebook(DEFAULTS_DIR / "breast.v1.json")
    bundle = override_sites(load_default_bundle(), {"breast": breast_v1})
    set_current_bundle(bundle)
    _rulebook_adapter.clear_cache()

    abnormal_text = (
        "As per GP report list from the NHS Breast Screening Programme.\n"
        "Breast neoplasm screening abnormal (68621)"
    )
    events = [_event("incl-001", abnormal_text)]
    signals = extract_text_signals(events)

    breast_diag = [
        s for s in signals if s.role == "diagnosis" and s.site_key == "breast"
    ]
    assert breast_diag, (
        "Abnormal breast screening encounter MUST emit a breast diagnosis "
        "signal -- it is the start of a screening-detected cancer pathway"
    )


def test_exclusion_does_not_block_subsequent_recall_encounter():
    """Real patient: routine 'screening normal' then weeks later recall/malignant.

    A prior all-clear (68620) must not be confused with a later
    'Breast neoplasm screening (XE1TY) (New Episode)' or malignant code
    -- those encounters are NOT excluded and must still emit text signals.
    """
    from libs.episode_detector.loader import DEFAULTS_DIR, load_rulebook, override_sites

    breast_v1 = load_rulebook(DEFAULTS_DIR / "breast.v1.json")
    bundle = override_sites(load_default_bundle(), {"breast": breast_v1})
    set_current_bundle(bundle)
    _rulebook_adapter.clear_cache()

    recall_text = (
        "24 May 2024 - Breast neoplasm screening (XE1TY) (New Episode)\n"
        "Assessment clinic booking."
    )
    events = [_event("recall-001", recall_text)]
    signals = extract_text_signals(events)
    breast = [s for s in signals if s.site_key == "breast"]
    assert breast, (
        "Recall / work-up after a prior 'normal' letter must still surface "
        "breast text-channel evidence; interval cancer is a known pattern"
    )
