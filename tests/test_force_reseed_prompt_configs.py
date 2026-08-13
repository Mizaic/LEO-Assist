"""Tests for guarded PromptConfig force reseeding.

Atlas trace: DI-7B978C0C, DO-FA8FCECF, VT-06157CF6.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts import force_reseed_prompt_configs as reseed


class _Result(list):
    def consume(self) -> None:
        return None


class _Session:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.writes = 0

    def __enter__(self) -> "_Session":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def run(self, query: str, **params: Any) -> _Result:
        if query == reseed._SNAPSHOT_QUERY:
            return _Result([dict(row) for row in self.rows])
        if query == reseed.FORCE_UPSERT_SEED_PROMPT:
            self.writes += 1
            self._upsert(params)
            return _Result()
        if query == reseed._RESTORE_QUERY:
            self._upsert(params)
            return _Result()
        raise AssertionError(f"unexpected query: {query}")

    def _upsert(self, params: dict[str, Any]) -> None:
        key = (params["name"], int(params["version"]))
        row = next(
            (item for item in self.rows if (item["name"], int(item["version"])) == key),
            None,
        )
        parsed = dict(params)
        if isinstance(parsed.get("few_shot_examples"), str):
            parsed["few_shot_examples"] = json.loads(parsed["few_shot_examples"])
        if row is None:
            self.rows.append(parsed)
        else:
            row.update(parsed)


class _Driver:
    def __init__(self, session: _Session) -> None:
        self._session = session
        self.closed = False

    def session(self) -> _Session:
        return self._session

    def close(self) -> None:
        self.closed = True


def _seed(system_prompt: str = "new") -> dict[str, Any]:
    return {
        "name": "sample",
        "version": 1,
        "description": "sample",
        "system_prompt": system_prompt,
        "output_schema": "{}",
        "verification": False,
        "few_shot_examples": [],
        "max_few_shot": 0,
    }


def _stored(system_prompt: str = "old", source: str = "user") -> dict[str, Any]:
    return {
        "id": "existing-id",
        **_seed(system_prompt),
        "source": source,
    }


def test_dry_run_never_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _Session([_stored()])
    driver = _Driver(session)
    monkeypatch.setattr(reseed, "_get_driver", lambda: driver)
    monkeypatch.setattr(reseed, "SEED_PROMPTS", [_seed()])

    assert reseed.run(apply=False, confirm="") == 0
    assert session.writes == 0
    assert driver.closed


def test_apply_requires_exact_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _Session([_stored()])
    monkeypatch.setattr(reseed, "_get_driver", lambda: _Driver(session))
    monkeypatch.setattr(reseed, "SEED_PROMPTS", [_seed()])

    with pytest.raises(ValueError, match=reseed.CONFIRM_TOKEN):
        reseed.run(apply=True, confirm="wrong")
    assert session.writes == 0


def test_apply_backs_up_and_verifies(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original = _stored()
    session = _Session([dict(original)])
    monkeypatch.setattr(reseed, "_get_driver", lambda: _Driver(session))
    monkeypatch.setattr(reseed, "SEED_PROMPTS", [_seed()])
    backup = tmp_path / "prompt-config.json"

    result = reseed.run(
        apply=True,
        confirm=reseed.CONFIRM_TOKEN,
        backup_path=backup,
    )

    assert result == 0
    assert json.loads(backup.read_text(encoding="utf-8")) == [original]
    assert session.rows[0]["system_prompt"] == "new"
    assert session.rows[0]["source"] == "seed"
