"""Tests for BitmapStore -- VT-LEO-AI-065."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from pyroaring import BitMap

from services.terminology_api.app.services.bitmap_store import (
    BitmapStore,
    _CURRENT_KEY,
    _INTIDS_KEY,
    _INTIDS_NEXT,
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
    with patch("services.terminology_api.app.services.bitmap_store._get_client") as mock:
        mock.return_value = _make_redis_mock()
        id1 = store.put_bitmap([1, 2, 3])
        id2 = store.put_bitmap([1, 2, 3])

    assert id1 == id2


def test_put_bitmap_different_sets_produce_different_ids(store):
    """Different int_id sets produce different bitmap keys."""
    with patch("services.terminology_api.app.services.bitmap_store._get_client") as mock:
        mock.return_value = _make_redis_mock()
        id1 = store.put_bitmap([1, 2, 3])
        id2 = store.put_bitmap([4, 5, 6])

    assert id1 != id2


def test_put_bitmap_skips_redis_write_if_key_exists(store):
    """put_bitmap does not overwrite an existing bitmap in Redis."""
    r = _make_redis_mock()
    r.exists.return_value = 1

    with patch("services.terminology_api.app.services.bitmap_store._get_client", return_value=r):
        store.put_bitmap([10, 20])

    r.set.assert_not_called()


def test_get_bitmap_returns_correct_bitmap(store):
    """get_bitmap deserialises Redis bytes to a matching BitMap."""
    bm = BitMap([100, 200, 300])
    raw = bytes(bm.serialize())

    r = _make_redis_mock(get_returns=raw)
    with patch("services.terminology_api.app.services.bitmap_store._get_client", return_value=r):
        result = store.get_bitmap("somedigest")

    assert result is not None
    assert 100 in result
    assert 200 in result
    assert 999 not in result


def test_get_bitmap_returns_none_on_cache_miss(store):
    """get_bitmap returns None when key is absent in Redis."""
    r = _make_redis_mock(get_returns=None)
    with patch("services.terminology_api.app.services.bitmap_store._get_client", return_value=r):
        result = store.get_bitmap("missing")

    assert result is None


def test_get_or_assign_int_id_returns_existing_id(store):
    """get_or_assign_int_id returns existing id without incrementing counter."""
    r = _make_redis_mock()
    r.hget.return_value = b"42"

    with patch("services.terminology_api.app.services.bitmap_store._get_client", return_value=r):
        result = store.get_or_assign_int_id("443416000")

    assert result == 42
    r.incr.assert_not_called()


def test_get_or_assign_int_id_assigns_new_id(store):
    """get_or_assign_int_id creates a new id when concept is not yet indexed."""
    r = _make_redis_mock()
    r.hget.return_value = None
    r.incr.return_value = 5

    with patch("services.terminology_api.app.services.bitmap_store._get_client", return_value=r):
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

    with patch("services.terminology_api.app.services.bitmap_store._get_client", return_value=r):
        store.write_ruleset("v1", ruleset)
        result = store.get_ruleset("v1")

    assert result is not None
    assert result["version"] == "v1"


def test_get_current_ruleset_returns_none_when_no_version_set(store):
    """get_current_ruleset returns None when no active version pointer exists."""
    r = _make_redis_mock(get_returns=None)
    with patch("services.terminology_api.app.services.bitmap_store._get_client", return_value=r):
        result = store.get_current_ruleset()

    assert result is None


def test_list_versions_excludes_current_key(store):
    """list_versions does not include the current-version pointer key."""
    r = _make_redis_mock()
    r.keys.return_value = [b"ruleset:v1", b"ruleset:v2", b"ruleset:current"]

    with patch("services.terminology_api.app.services.bitmap_store._get_client", return_value=r):
        versions = store.list_versions()

    assert "v1" in versions
    assert "v2" in versions
    assert "current" not in versions


def test_set_current_version_writes_pointer(store):
    """set_current_version writes the version name to ruleset:current."""
    r = _make_redis_mock()
    with patch("services.terminology_api.app.services.bitmap_store._get_client", return_value=r):
        store.set_current_version("v20260308")

    r.set.assert_called_once_with(_CURRENT_KEY, "v20260308")
