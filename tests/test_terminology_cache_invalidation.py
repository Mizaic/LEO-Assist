"""VT-DDEB829F -- cached matching results drop after wording-link changes.

Atlas trace:
  UN: UN-72B60B2D
  DI: DI-47D2CD86
  DO: DO-5A88E0B9
  VT: VT-DDEB829F
"""

from __future__ import annotations

import fnmatch
import sys
from unittest.mock import MagicMock

from libs.terminology.cache_invalidation import (
    RESOLVER_CACHE_INVALIDATION_PATTERN,
    RESOLVER_CACHE_KEY_FAMILY,
    _cache_patterns,
    invalidate_terminology_resolution_caches,
)
from services.terminology_api.app.services.cache import TerminologyCache


def _matches(key: str, pattern: str) -> bool:
    return fnmatch.fnmatch(key, pattern)


def _live_resolver_key() -> str:
    cache = TerminologyCache.__new__(TerminologyCache)
    return TerminologyCache.generate_key(
        cache,
        "dysphagia",
        None,
        False,
        org_id="org-A",
        package_fingerprint="fp1",
    )


def test_invalidation_covers_live_resolver_cache_keys() -> None:
    """Cached resolve results are dropped after a mapping change."""
    key = _live_resolver_key()
    assert key.startswith(f"{RESOLVER_CACHE_KEY_FAMILY}:v4:")
    assert _matches(key, RESOLVER_CACHE_INVALIDATION_PATTERN)
    assert any(_matches(key, p) for p in _cache_patterns())


def test_invalidation_covers_legacy_and_future_resolver_versions() -> None:
    """Invalidation matches leftover v1 keys and a future version bump."""
    leftovers = (
        "term_resolve:v1:abc::False",
        "term_resolve:v3:abc::False:org:fp",
    )
    for key in leftovers:
        assert _matches(key, RESOLVER_CACHE_INVALIDATION_PATTERN)


def test_invalidation_pattern_is_not_pinned_to_v1() -> None:
    """A v1-only glob would miss the live resolver cache."""
    assert RESOLVER_CACHE_INVALIDATION_PATTERN == "term_resolve:*"
    assert "term_resolve:v1:*" not in _cache_patterns()


def test_invalidate_deletes_live_resolver_keys(monkeypatch) -> None:
    """SCAN against the family pattern deletes current v2 resolver keys."""
    live_key = "term_resolve:v2:deadbeef::False:orgA:fp1"
    fake = MagicMock()
    fake.scan_iter.side_effect = lambda match=None, count=None: iter(
        [live_key] if match == RESOLVER_CACHE_INVALIDATION_PATTERN else []
    )
    fake.delete.side_effect = lambda *keys: len(keys)

    import redis

    monkeypatch.setattr(redis, "from_url", lambda *a, **k: fake)

    result = invalidate_terminology_resolution_caches(
        reason="surface_form_upsert:x"
    )
    assert result["deleted"] >= 1
    fake.delete.assert_any_call(live_key)
    assert RESOLVER_CACHE_INVALIDATION_PATTERN in result["patterns"]
