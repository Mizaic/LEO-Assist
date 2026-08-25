"""Teardown must not fail when redis is absent (runtime-import-guard CI)."""

from __future__ import annotations

import sys
import types

from tests.conftest import restore_real_redis_module


def test_restore_real_redis_module_skips_when_package_missing(monkeypatch) -> None:
    stub = types.ModuleType("redis")
    monkeypatch.setitem(sys.modules, "redis", stub)

    def _missing(_name: str):
        raise ModuleNotFoundError("No module named 'redis'")

    monkeypatch.setattr("tests.conftest.importlib.import_module", _missing)
    restore_real_redis_module()
    assert "redis" not in sys.modules


def test_restore_real_redis_module_keeps_real_client(monkeypatch) -> None:
    real = types.ModuleType("redis")
    real.from_url = lambda url: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "redis", real)
    restore_real_redis_module()
    assert sys.modules["redis"] is real
