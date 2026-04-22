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
