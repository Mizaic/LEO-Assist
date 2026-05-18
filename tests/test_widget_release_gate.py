"""LEO widget pre-release gate verification tests.

Atlas trace:
  DI: DI-3C06AFD0
  DO: DO-3B62F38E
  VT: VT-0D241AA2 (pre-release gate refuses promotion on disclosure-VT failure)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE_SCRIPT = REPO_ROOT / "scripts" / "widget_release_gate.py"

DISCLOSURE_VTS = (
    "VT-AD41127B",
    "VT-F6F5681E",
    "VT-50EE589C",
    "VT-265DACC1",
)


def _run_gate(payload: dict, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    gate_input = tmp_path / "gate.json"
    gate_input.write_text(json.dumps(payload))
    return subprocess.run(
        [sys.executable, str(GATE_SCRIPT), str(gate_input)],
        capture_output=True,
        text=True,
    )


def _all_pass_payload() -> dict:
    return {"build": "1.4.2", "vts": {vt: "pass" for vt in DISCLOSURE_VTS}}


def test_all_disclosure_vts_pass_promotes(tmp_path: Path) -> None:
    result = _run_gate(_all_pass_payload(), tmp_path)
    assert result.returncode == 0, result.stderr
    assert "PROMOTE" in result.stdout
    assert "1.4.2" in result.stdout


@pytest.mark.parametrize("failing_vt", DISCLOSURE_VTS)
def test_any_failing_disclosure_vt_blocks_promotion(
    failing_vt: str, tmp_path: Path
) -> None:
    payload = _all_pass_payload()
    payload["vts"][failing_vt] = "fail"
    result = _run_gate(payload, tmp_path)
    assert result.returncode != 0
    assert "PROMOTE" not in result.stdout
    assert failing_vt in result.stderr


def test_missing_disclosure_vt_blocks_promotion(tmp_path: Path) -> None:
    payload = _all_pass_payload()
    del payload["vts"]["VT-AD41127B"]
    result = _run_gate(payload, tmp_path)
    assert result.returncode != 0
    assert "PROMOTE" not in result.stdout
    assert "VT-AD41127B" in result.stderr
