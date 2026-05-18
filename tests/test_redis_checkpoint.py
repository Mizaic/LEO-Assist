"""Tests for `libs/redis_client/checkpoint.py`.

Atlas trace:
  DO: DO-412DE1A5
  DI: DI-B884A243

The CheckpointStore wraps redis. All public methods MUST swallow Redis
errors (so a transient outage cannot bring down the pipeline) and return
sensible defaults: None for `get`, -1 for `incr`, an empty set for
`smembers`, False for `ping`.
"""

from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def fake_redis(monkeypatch):
    """Inject a fake `redis` module into sys.modules and yield the mock
    client returned from `redis.from_url`."""
    fake_module = MagicMock()
    fake_client = MagicMock()
    fake_module.from_url = MagicMock(return_value=fake_client)
    monkeypatch.setitem(sys.modules, "redis", fake_module)
    yield fake_client


@pytest.fixture
def store(fake_redis):
    from libs.redis_client.checkpoint import CheckpointStore

    return CheckpointStore(url="redis://test")


class TestGet:
    def test_returns_parsed_json(self, store, fake_redis):
        fake_redis.get.return_value = json.dumps({"a": 1, "b": [2, 3]})
        assert store.get("k") == {"a": 1, "b": [2, 3]}

    def test_returns_none_on_missing_key(self, store, fake_redis):
        fake_redis.get.return_value = None
        assert store.get("missing") is None

    def test_returns_none_on_redis_error(self, store, fake_redis):
        fake_redis.get.side_effect = RuntimeError("down")
        assert store.get("k") is None

    def test_returns_none_on_invalid_json(self, store, fake_redis):
        fake_redis.get.return_value = "not-json"
        assert store.get("k") is None


class TestSet:
    def test_writes_with_default_ttl(self, store, fake_redis):
        store.set("k", {"x": 1})
        fake_redis.setex.assert_called_once()
        call = fake_redis.setex.call_args
        assert call.args[0] == "k"
        assert call.args[1] == 86400
        assert json.loads(call.args[2]) == {"x": 1}

    def test_writes_with_custom_ttl(self, store, fake_redis):
        store.set("k", [1, 2], ttl=60)
        fake_redis.setex.assert_called_once()
        assert fake_redis.setex.call_args.args[1] == 60

    def test_swallows_set_failure(self, store, fake_redis):
        fake_redis.setex.side_effect = RuntimeError("fail")
        store.set("k", {"x": 1})

    def test_default_serialiser_handles_non_json_types(self, store, fake_redis):
        from datetime import datetime

        store.set("k", {"ts": datetime(2025, 1, 1)})
        fake_redis.setex.assert_called_once()


class TestDelete:
    def test_calls_delete(self, store, fake_redis):
        store.delete("k")
        fake_redis.delete.assert_called_once_with("k")

    def test_swallows_delete_failure(self, store, fake_redis):
        fake_redis.delete.side_effect = RuntimeError("nope")
        store.delete("k")


class TestDeletePattern:
    def test_scans_and_deletes_in_batches(self, store, fake_redis):
        fake_redis.scan.side_effect = [
            (1, ["a", "b"]),
            (0, ["c"]),
        ]
        store.delete_pattern("classify:P1:*")
        assert fake_redis.delete.call_count == 2

    def test_swallows_scan_error(self, store, fake_redis):
        fake_redis.scan.side_effect = RuntimeError("scan failed")
        store.delete_pattern("classify:*")


class TestIncr:
    def test_returns_new_value_and_sets_ttl_on_first_creation(
        self, store, fake_redis
    ):
        fake_redis.incr.return_value = 1
        n = store.incr("counter")
        assert n == 1
        fake_redis.expire.assert_called_once_with("counter", 86400)

    def test_does_not_re_set_ttl_on_subsequent_increments(
        self, store, fake_redis
    ):
        fake_redis.incr.return_value = 5
        n = store.incr("counter")
        assert n == 5
        fake_redis.expire.assert_not_called()

    def test_returns_minus_one_on_failure(self, store, fake_redis):
        fake_redis.incr.side_effect = RuntimeError("down")
        assert store.incr("counter") == -1


class TestSets:
    def test_sadd_calls_redis_sadd_and_sets_ttl(self, store, fake_redis):
        store.sadd("s", "a", "b", "c", ttl=10)
        fake_redis.sadd.assert_called_once_with("s", "a", "b", "c")
        fake_redis.expire.assert_called_once_with("s", 10)

    def test_smembers_returns_set(self, store, fake_redis):
        fake_redis.smembers.return_value = {"a", "b"}
        assert store.smembers("s") == {"a", "b"}

    def test_smembers_returns_empty_set_on_error(self, store, fake_redis):
        fake_redis.smembers.side_effect = RuntimeError("fail")
        assert store.smembers("s") == set()


class TestPing:
    def test_returns_true_when_redis_responds(self, store, fake_redis):
        fake_redis.ping.return_value = True
        assert store.ping() is True

    def test_returns_false_when_redis_raises(self, store, fake_redis):
        fake_redis.ping.side_effect = RuntimeError("down")
        assert store.ping() is False


class TestUrlResolution:
    def test_uses_env_var_when_no_url_passed(self, monkeypatch, fake_redis):
        from libs.redis_client.checkpoint import CheckpointStore

        monkeypatch.setenv("REDIS_URL", "rediss://prod-host:6380")
        CheckpointStore()
        fake_redis_call = sys.modules["redis"].from_url
        assert fake_redis_call.call_args.args[0] == "rediss://prod-host:6380"

    def test_falls_back_to_localhost_when_env_unset(
        self, monkeypatch, fake_redis
    ):
        from libs.redis_client.checkpoint import CheckpointStore

        monkeypatch.delenv("REDIS_URL", raising=False)
        CheckpointStore()
        fake_redis_call = sys.modules["redis"].from_url
        assert fake_redis_call.call_args.args[0] == "redis://localhost:6379"
