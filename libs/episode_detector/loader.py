"""Rulebook bundle loader.

Atlas trace:
  DI: DI-FA3CE229 (runtime loader + bundle)
  DI: DI-BF97CEAC (registry wiring -- loads champion rulebook per site)

At process boot the detector calls ``load_default_bundle()`` to build a
``RulebookBundle`` from the frozen v0 JSON files shipped with the
detector binary. When the Knowledge Graph model registry is available,
the runtime replaces each site's rulebook with the current champion
via ``load_registry_bundle`` (wiring lives in the analysis worker, not
here, so this module stays graph-free and hermetic).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Mapping

from libs.episode_detector.rulebook import (
    RulebookBundle,
    SiteRulebook,
    from_mapping,
    validate_no_pii,
)


DEFAULTS_DIR: Path = Path(__file__).resolve().parent / "defaults"


def load_default_bundle(*, defaults_dir: Path | None = None) -> RulebookBundle:
    """Load the shipped v0 rulebooks from disk into a RulebookBundle.

    Each *.json file in ``defaults_dir`` is parsed, validated for PII,
    and keyed by its site_key. Files whose name starts with '_' or '.'
    are ignored (reserved for README, schema exports, etc).
    """

    root = defaults_dir or DEFAULTS_DIR
    rulebooks: dict[str, SiteRulebook] = {}
    # Only .v0.json files are the shipped defaults. Higher versions
    # (v1, v2, ...) live on disk alongside v0 as editable authoring
    # artefacts, but the registry, not the loader, is responsible for
    # promoting them. This keeps the v0 baseline byte-identical to the
    # pre-rulebook Python constants and makes the parity test trivial.
    for path in sorted(root.glob("*.v0.json")):
        if path.name.startswith(("_", ".")):
            continue
        rb = load_rulebook(path)
        rulebooks[rb.site_key] = rb
    return RulebookBundle(sites=MappingProxyType(rulebooks))


def load_rulebook(path: str | Path) -> SiteRulebook:
    """Load and validate a single rulebook JSON file.

    Used by authoring flows (e.g. loading breast.v1.json for a
    VT run) and by the registry when materialising a champion into
    an in-memory bundle.
    """

    with Path(path).open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    rb = from_mapping(data)
    validate_no_pii(rb)
    return rb


def build_bundle_from_rulebooks(
    rulebooks: Iterable[SiteRulebook],
) -> RulebookBundle:
    """Build a RulebookBundle from an in-memory iterable of rulebooks.

    Used by the registry wiring when pulling champions from Neo4j, and
    by tests. Each rulebook is re-validated for PII before it is
    installed in the bundle.
    """

    out: dict[str, SiteRulebook] = {}
    for rb in rulebooks:
        validate_no_pii(rb)
        out[rb.site_key] = rb
    return RulebookBundle(sites=MappingProxyType(out))


def override_sites(
    bundle: RulebookBundle,
    overrides: Mapping[str, SiteRulebook],
) -> RulebookBundle:
    """Return a new bundle with the given sites replaced. Used by the
    champion/challenger harness when running a challenger for one site
    while keeping all other sites on champion.
    """

    merged = dict(bundle.sites)
    for site, rb in overrides.items():
        validate_no_pii(rb)
        merged[site] = rb
    return RulebookBundle(sites=MappingProxyType(merged))


# ----------------------------------------------------------------------
# Process-wide current bundle (set at boot, read by extractors).
# ----------------------------------------------------------------------

_current_bundle: RulebookBundle | None = None


def set_current_bundle(bundle: RulebookBundle) -> None:
    """Install the bundle to be returned by ``current_bundle``. The
    detector runner calls this once at startup. Tests use it to swap
    in a synthetic bundle.
    """

    global _current_bundle
    _current_bundle = bundle


def clear_current_bundle() -> None:
    """Reset the process-wide bundle. Tests call this in teardown so
    state does not leak between tests.
    """

    global _current_bundle
    _current_bundle = None


def current_bundle() -> RulebookBundle:
    """Return the process-wide bundle, lazily initialised to the
    shipped v0 defaults if the runner has not installed one yet. This
    keeps the detector fail-safe: even if the registry is unreachable,
    the v0 defaults ship with the binary and behaviour is identical to
    the pre-rulebook code path.
    """

    global _current_bundle
    if _current_bundle is None:
        _current_bundle = load_default_bundle()
    return _current_bundle
