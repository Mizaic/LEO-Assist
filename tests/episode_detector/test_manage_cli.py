"""Integration tests for the libs.episode_detector.manage CLI.

Atlas trace:
  VT: VT-RULEBOOK-PROMOTION-GATE
  DI: DI-BF97CEAC (registry wiring)
"""

from __future__ import annotations

import json
from pathlib import Path

from libs.episode_detector.loader import load_rulebook
from libs.episode_detector.manage import main

_BREAST_V1_PATH = "libs/episode_detector/defaults/breast.v1.json"
_BREAST_V1_VERSION = load_rulebook(_BREAST_V1_PATH).rulebook_version


def _run(capsys, argv: list[str]) -> tuple[int, dict]:
    exit_code = main(argv)
    out = capsys.readouterr().out.strip()
    payload = json.loads(out) if out else {}
    return exit_code, payload


def test_register_emits_entry(capsys) -> None:
    code, payload = _run(
        capsys,
        [
            "register",
            "--path",
            "libs/episode_detector/defaults/breast.v1.json",
        ],
    )
    assert code == 0
    assert payload["ok"] is True
    assert payload["entry"]["site_key"] == "breast"
    assert payload["entry"]["state"] == "registered"


def test_promote_without_gold_pass_is_blocked(capsys) -> None:
    code, payload = _run(
        capsys,
        [
            "promote",
            "--site",
            "breast",
            "--version",
            _BREAST_V1_VERSION,
            "--path",
            _BREAST_V1_PATH,
        ],
    )
    assert code == 1
    assert payload["promoted"] is False
    assert "gold gate" in payload["reason"]


def test_promote_with_force_succeeds(capsys) -> None:
    code, payload = _run(
        capsys,
        [
            "promote",
            "--site",
            "breast",
            "--version",
            _BREAST_V1_VERSION,
            "--path",
            _BREAST_V1_PATH,
            "--force",
        ],
    )
    assert code == 0
    assert payload["promoted"] is True


def test_promote_with_gold_pass_file(capsys, tmp_path: Path) -> None:
    gate_file = tmp_path / "gate.json"
    gate_file.write_text(json.dumps({"breast": "2030-01-01T00:00:00+00:00"}))
    code, payload = _run(
        capsys,
        [
            "--gold-pass-from",
            str(gate_file),
            "promote",
            "--site",
            "breast",
            "--version",
            _BREAST_V1_VERSION,
            "--path",
            _BREAST_V1_PATH,
            "--now",
            "2030-01-02T00:00:00+00:00",
        ],
    )
    assert code == 0, payload
    assert payload["promoted"] is True
