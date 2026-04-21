"""LEO widget pre-release gate.

Atlas trace:
  DO: DO-3B62F38E
  DI: DI-3C06AFD0
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-3B62F38E")

Refuses to print PROMOTE on stdout (and exits non-zero) unless every
disclosure-related VT in the gate input is reported as 'pass'. The
disclosure VTs are the safety-critical contract that the widget will
not let a host hide or mutate the source-record disclosure:

  VT-AD41127B - widget exposes no brand-mutation API
  VT-F6F5681E - host CSS cannot change widget-internal styling
  VT-50EE589C - source-record disclosure remains visible
  VT-265DACC1 - host JS cannot reach widget DOM

Usage:

  python scripts/widget_release_gate.py path/to/gate-input.json

The gate input is a JSON object:

  { "vts": { "VT-AD41127B": "pass", ... }, "build": "1.4.2" }
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DISCLOSURE_VTS: tuple[str, ...] = (
    "VT-AD41127B",
    "VT-F6F5681E",
    "VT-50EE589C",
    "VT-265DACC1",
)


def evaluate_gate(payload: dict) -> tuple[bool, list[str]]:
    """Return (allow_promote, reasons)."""
    vts = payload.get("vts") or {}
    reasons: list[str] = []
    for vt in DISCLOSURE_VTS:
        result = vts.get(vt)
        if result is None:
            reasons.append(f"missing VT result: {vt}")
        elif str(result).lower() != "pass":
            reasons.append(f"failing VT result: {vt} = {result}")
    return (len(reasons) == 0, reasons)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(
            "usage: widget_release_gate.py <gate-input.json>",
            file=sys.stderr,
        )
        return 2
    path = Path(argv[1])
    if not path.exists():
        print(f"gate input not found: {path}", file=sys.stderr)
        return 2
    payload = json.loads(path.read_text())
    allow, reasons = evaluate_gate(payload)
    build = payload.get("build", "<unknown>")
    if allow:
        print(f"PROMOTE build {build} - all disclosure VTs green")
        return 0
    print(f"BLOCK build {build}", file=sys.stderr)
    for reason in reasons:
        print(f"  - {reason}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
