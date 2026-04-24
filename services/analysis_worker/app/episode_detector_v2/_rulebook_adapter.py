"""Runtime adapter between the v2 detector and libs/episode_detector bundles.

Atlas trace:
  DI: DI-FA3CE229 (runtime loader and bundle)
  DI: DI-AC6838DD (gold-patient gate on rulebook promotion)

The v2 detector historically read module-level Python constants
(SITE_ACTIVATION, BREAST_SNOMED_*, _FORM_TYPE_TO_SITE, etc). This
adapter gives those call sites a single seam to ask the rulebook
bundle instead, falling back to the constant when the bundle has no
entry for the site. The fallback matters because:

  1. v0 rulebooks shipped in the binary are byte-identical to the
     Python constants (proven by tests/episode_detector/test_rulebook_parity.py),
     so switching to the bundle with only v0 installed is a no-op.
  2. Customer instances without a registered champion for a given
     site stay on the v0 behaviour automatically.

Every accessor here returns plain Python values (frozenset / tuple /
dict). Callers do not need to know the bundle exists. This keeps the
detector extractors clean.
"""

from __future__ import annotations

from functools import lru_cache

from libs.episode_detector.loader import current_bundle
from libs.episode_detector.rulebook import SiteRulebook


def _site(site_key: str) -> SiteRulebook | None:
    try:
        return current_bundle().get(site_key)
    except Exception:  # pragma: no cover - defensive
        return None


def auto_publish_for(site_key: str, *, fallback: bool) -> bool:
    """Return the auto_publish flag from the champion rulebook, or the
    Python-constant fallback when no rulebook is installed for the site.
    """
    rb = _site(site_key)
    if rb is None:
        return fallback
    return bool(rb.activation.auto_publish)


def suggest_for(site_key: str, *, fallback: bool) -> bool:
    rb = _site(site_key)
    if rb is None:
        return fallback
    return bool(rb.activation.suggest)


def anchor_suspected_snomed(site_key: str) -> frozenset[str]:
    rb = _site(site_key)
    if rb is None:
        return frozenset()
    return frozenset(rb.anchors.suspected_snomed)


def anchor_confirmed_snomed(site_key: str) -> frozenset[str]:
    rb = _site(site_key)
    if rb is None:
        return frozenset()
    return frozenset(rb.anchors.confirmed_snomed)


def anchor_referral_snomed(site_key: str) -> frozenset[str]:
    rb = _site(site_key)
    if rb is None:
        return frozenset()
    return frozenset(rb.anchors.referral_snomed)


def cross_site_guard_for(site_key: str) -> frozenset[str]:
    """SNOMED codes that must NOT contribute to this site's candidate,
    even if they otherwise classify to it. Prevents cross-site leakage
    (R-5FA0C950), for example a stray urinary-suspected code on a
    patient whose pathway is otherwise breast.
    """
    rb = _site(site_key)
    if rb is None:
        return frozenset()
    return frozenset(rb.cross_site_guard)


def benign_closure_tokens(site_key: str) -> tuple[str, ...]:
    """Tokens that satisfy the benign-closure rule for the site.

    Each token is either a ``snomed:<code>`` reference or a symbolic
    label the boundary detector evaluates (for example
    ``result.negative_terms`` or ``repeat_anchor_clinic_seen``).
    """
    rb = _site(site_key)
    if rb is None:
        return ()
    return tuple(rb.closure.benign.requires_any_of)


def benign_closure_no_confirmed_days(site_key: str, *, fallback: int) -> int:
    """Number of days after the benign signal during which the presence
    of a confirmed SNOMED disqualifies the benign closure.
    """
    rb = _site(site_key)
    if rb is None:
        return fallback
    return int(rb.closure.benign.and_no_confirmed_within_days)


def completed_closure_tokens(site_key: str) -> tuple[str, ...]:
    rb = _site(site_key)
    if rb is None:
        return ()
    return tuple(rb.closure.completed.requires_any_of)


def completed_quiet_window_days(site_key: str, *, fallback: int) -> int:
    """Number of days of no confirmed-site activity that must follow
    the completed-closure signal before the episode is counted as
    completed. Falls back to the benign quiet window when the
    completed rule omits one (every v1 rulebook sets at least one).
    """
    rb = _site(site_key)
    if rb is None:
        return fallback
    completed_days = rb.closure.completed.and_no_confirmed_within_days
    if completed_days is not None:
        return int(completed_days)
    benign_days = rb.closure.benign.and_no_confirmed_within_days
    if benign_days is not None:
        return int(benign_days)
    return fallback


def result_positive_terms(site_key: str) -> tuple[str, ...]:
    rb = _site(site_key)
    if rb is None:
        return ()
    return tuple(rb.signals.result_channel.positive_terms)


def result_negative_terms(site_key: str) -> tuple[str, ...]:
    rb = _site(site_key)
    if rb is None:
        return ()
    return tuple(rb.signals.result_channel.negative_terms)


def result_investigation_terms(site_key: str) -> tuple[str, ...]:
    rb = _site(site_key)
    if rb is None:
        return ()
    return tuple(rb.signals.result_channel.investigation_terms)


def result_observation_snomed(site_key: str) -> frozenset[str]:
    rb = _site(site_key)
    if rb is None:
        return frozenset()
    return frozenset(rb.signals.result_channel.observation_snomed)


def text_channel_regex(site_key: str) -> tuple[str, ...]:
    """Return the site's text-channel regex catalogue.

    Each entry is a case-insensitive regex string that, when matched
    anywhere in the encounter free text, is taken as evidence that
    the encounter plausibly relates to the site. The extractor
    compiles these once per call and emits a Signal per match.
    Returns ``()`` when no rulebook is installed for the site or the
    catalogue is empty.
    """
    rb = _site(site_key)
    if rb is None:
        return ()
    return tuple(rb.signals.text_channel.regex_catalogue)


def text_channel_context_catalogue(
    site_key: str,
) -> dict[str, tuple[str, ...]]:
    """Return the site's per-context-tag regex catalogue.

    Keys are canonical context-tier milestone tags (see
    libs.episode_detector.rulebook.CONTEXT_MILESTONE_TAGS); values
    are tuples of case-insensitive regex strings. Used by the
    text_channel extractor to emit role="context_milestone"
    signals (DI-2C015ADE).

    Returns an empty dict when no rulebook is installed for the
    site or the catalogue is empty. An empty catalogue means the
    text channel contributes no context signals for that site --
    the episode_engine LLM is still free to propose context
    milestones from the raw encounter text.
    """
    rb = _site(site_key)
    if rb is None:
        return {}
    return {
        tag: tuple(patterns)
        for tag, patterns in (rb.signals.text_channel.context_role_catalogue.items())
        if patterns
    }


@lru_cache(maxsize=1)
def _all_sites_cached() -> tuple[str, ...]:
    """Convenience: list of sites the current bundle ships. Cached to
    keep the extractors' tight loops cheap; ``clear_cache`` is called
    by the loader when the bundle changes.
    """
    try:
        return tuple(current_bundle().sites.keys())
    except Exception:  # pragma: no cover - defensive
        return ()


def clear_cache() -> None:
    """Reset the adapter's internal caches. Tests and the dry-run
    CLI call this when they swap the current bundle.
    """
    _all_sites_cached.cache_clear()
