"""Tests for BitmapStore -- VT-LEO-AI-065."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from pyroaring import BitMap

from services.terminology_api.app.services.bitmap_store import (
    BitmapStore,
    _INTIDS_KEY,
    _INTIDS_NEXT,
    _scoped_current_key,
    _scoped_ruleset_key,
)


def _make_redis_mock(get_returns=None):
    """Return a mock Redis client with configurable get return value."""
    r = MagicMock()
    r.get.return_value = get_returns
    r.set.return_value = True
    r.exists.return_value = 0
    r.incr.return_value = 1
    r.hget.return_value = None
    r.hset.return_value = 1
    r.keys.return_value = []
    return r


@pytest.fixture()
def store():
    return BitmapStore(redis_url="redis://localhost:6379")


def test_put_bitmap_returns_deterministic_id(store):
    """Same int_id set must always produce the same bitmap key."""
    with patch(
        "services.terminology_api.app.services.bitmap_store._get_client"
    ) as mock:
        mock.return_value = _make_redis_mock()
        id1 = store.put_bitmap([1, 2, 3])
        id2 = store.put_bitmap([1, 2, 3])

    assert id1 == id2


def test_put_bitmap_different_sets_produce_different_ids(store):
    """Different int_id sets produce different bitmap keys."""
    with patch(
        "services.terminology_api.app.services.bitmap_store._get_client"
    ) as mock:
        mock.return_value = _make_redis_mock()
        id1 = store.put_bitmap([1, 2, 3])
        id2 = store.put_bitmap([4, 5, 6])

    assert id1 != id2


def test_put_bitmap_skips_redis_write_if_key_exists(store):
    """put_bitmap does not overwrite an existing bitmap in Redis."""
    r = _make_redis_mock()
    r.exists.return_value = 1

    with patch(
        "services.terminology_api.app.services.bitmap_store._get_client", return_value=r
    ):
        store.put_bitmap([10, 20])

    r.set.assert_not_called()


def test_get_bitmap_returns_correct_bitmap(store):
    """get_bitmap deserialises Redis bytes to a matching BitMap."""
    bm = BitMap([100, 200, 300])
    raw = bytes(bm.serialize())

    r = _make_redis_mock(get_returns=raw)
    with patch(
        "services.terminology_api.app.services.bitmap_store._get_client", return_value=r
    ):
        result = store.get_bitmap("somedigest")

    assert result is not None
    assert 100 in result
    assert 200 in result
    assert 999 not in result


def test_get_bitmap_returns_none_on_cache_miss(store):
    """get_bitmap returns None when key is absent in Redis."""
    r = _make_redis_mock(get_returns=None)
    with patch(
        "services.terminology_api.app.services.bitmap_store._get_client", return_value=r
    ):
        result = store.get_bitmap("missing")

    assert result is None


def test_get_or_assign_int_id_returns_existing_id(store):
    """get_or_assign_int_id returns existing id without incrementing counter."""
    r = _make_redis_mock()
    r.hget.return_value = b"42"

    with patch(
        "services.terminology_api.app.services.bitmap_store._get_client", return_value=r
    ):
        result = store.get_or_assign_int_id("443416000")

    assert result == 42
    r.incr.assert_not_called()


def test_get_or_assign_int_id_assigns_new_id(store):
    """get_or_assign_int_id creates a new id when concept is not yet indexed."""
    r = _make_redis_mock()
    r.hget.return_value = None
    r.incr.return_value = 5

    with patch(
        "services.terminology_api.app.services.bitmap_store._get_client", return_value=r
    ):
        result = store.get_or_assign_int_id("new_concept")

    assert result == 5
    r.hset.assert_called_once_with(_INTIDS_KEY, "new_concept", 5)


def test_write_and_get_ruleset(store):
    """write_ruleset serialises to Redis; get_ruleset deserialises correctly."""
    ruleset = {"version": "v1", "rules": [{"rule_id": "r1"}]}

    r = _make_redis_mock()
    captured = {}

    def fake_set(key, value):
        captured[key] = value

    r.set.side_effect = fake_set
    r.get.side_effect = lambda k: captured.get(k)

    with patch(
        "services.terminology_api.app.services.bitmap_store._get_client", return_value=r
    ):
        store.write_ruleset("v1", ruleset)
        result = store.get_ruleset("v1")

    assert result is not None
    assert result["version"] == "v1"


def test_write_and_get_ruleset_scoped(store):
    """Scoped rulesets are namespaced by scope token."""
    ruleset = {"version": "v2", "rules": [{"rule_id": "r2"}]}

    r = _make_redis_mock()
    captured = {}

    def fake_set(key, value):
        captured[key] = value

    r.set.side_effect = fake_set
    r.get.side_effect = lambda k: captured.get(k)

    with patch(
        "services.terminology_api.app.services.bitmap_store._get_client", return_value=r
    ):
        store.write_ruleset("v2", ruleset, scope_type="guideline", scope_id="NG12")
        result = store.get_ruleset("v2", scope_type="guideline", scope_id="NG12")

    assert result is not None
    assert result["version"] == "v2"
    assert result["scope_type"] == "guideline"
    assert result["scope_id"] == "NG12"
    assert _scoped_ruleset_key("v2", "guideline", "NG12") in captured


def test_get_current_ruleset_returns_none_when_no_version_set(store):
    """get_current_ruleset returns None when no active version pointer exists."""
    r = _make_redis_mock(get_returns=None)
    with patch(
        "services.terminology_api.app.services.bitmap_store._get_client", return_value=r
    ):
        result = store.get_current_ruleset()

    assert result is None


def test_list_versions_excludes_current_key(store):
    """list_versions returns only versions for the requested scope."""
    r = _make_redis_mock()
    r.keys.return_value = [
        b"ruleset:guideline:NG12:v1",
        b"ruleset:guideline:NG12:v2",
        b"ruleset:guideline:NG151:v3",
    ]

    with patch(
        "services.terminology_api.app.services.bitmap_store._get_client", return_value=r
    ):
        versions = store.list_versions(scope_type="guideline", scope_id="NG12")

    assert "v1" in versions
    assert "v2" in versions
    assert "v3" not in versions


def test_set_current_version_writes_pointer(store):
    """set_current_version writes the version name to scoped pointer key."""
    r = _make_redis_mock()
    with patch(
        "services.terminology_api.app.services.bitmap_store._get_client", return_value=r
    ):
        store.set_current_version("v20260308", scope_type="guideline", scope_id="NG12")

    r.set.assert_called_once_with(
        _scoped_current_key("guideline", "NG12"),
        "v20260308",
    )


def test_get_current_version_name_scoped(store):
    """get_current_version_name reads scoped pointer key."""
    r = _make_redis_mock(get_returns=b"v20260308")
    with patch(
        "services.terminology_api.app.services.bitmap_store._get_client", return_value=r
    ):
        version = store.get_current_version_name(
            scope_type="guideline", scope_id="NG12"
        )

    assert version == "v20260308"
    r.get.assert_called_with(_scoped_current_key("guideline", "NG12"))


class TestClientCache:
    """Pin the module-level connection pooling behaviour.

    Regression guard for the `/terminology/guidelines/evaluate` 30s
    timeout: REDIS_URL points at Azure Cache for Redis over TLS, so
    constructing a new client per call adds ~100-300ms of TLS
    handshake. We MUST reuse a single client per URL.
    """

    def setup_method(self) -> None:
        from services.terminology_api.app.services.bitmap_store import (
            reset_client_cache,
        )

        reset_client_cache()

    def teardown_method(self) -> None:
        from services.terminology_api.app.services.bitmap_store import (
            reset_client_cache,
        )

        reset_client_cache()

    def test_get_client_reuses_same_instance_per_url(self):
        from services.terminology_api.app.services import bitmap_store as bs

        with patch.object(bs.redis, "from_url") as factory:
            factory.side_effect = lambda *_a, **_kw: MagicMock(name=f"c{factory.call_count}")
            first = bs._get_client("rediss://example:10000")
            second = bs._get_client("rediss://example:10000")

        assert first is second
        assert factory.call_count == 1

    def test_get_client_returns_distinct_clients_for_distinct_urls(self):
        from services.terminology_api.app.services import bitmap_store as bs

        with patch.object(bs.redis, "from_url") as factory:
            factory.side_effect = lambda *_a, **_kw: MagicMock(name=f"c{factory.call_count}")
            a = bs._get_client("rediss://primary:10000")
            b = bs._get_client("rediss://secondary:10000")

        assert a is not b
        assert factory.call_count == 2

    def test_bitmap_store_instances_share_same_client(self):
        """Two BitmapStore objects on the same URL must share the pool."""
        from services.terminology_api.app.services import bitmap_store as bs

        with patch.object(bs.redis, "from_url") as factory:
            factory.side_effect = lambda *_a, **_kw: MagicMock(name=f"c{factory.call_count}")
            store_a = BitmapStore(redis_url="rediss://shared:10000")
            store_b = BitmapStore(redis_url="rediss://shared:10000")
            client_a = store_a._client()
            client_b = store_b._client()

        assert client_a is client_b
        assert factory.call_count == 1

    def test_reset_client_cache_drops_cached_clients(self):
        from services.terminology_api.app.services import bitmap_store as bs

        with patch.object(bs.redis, "from_url") as factory:
            factory.side_effect = lambda *_a, **_kw: MagicMock(name=f"c{factory.call_count}")
            bs._get_client("rediss://reset-me:10000")
            bs.reset_client_cache()
            bs._get_client("rediss://reset-me:10000")

        assert factory.call_count == 2
