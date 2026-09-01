"""List proposed soft-gate and FIT tags. Write only with --apply.

Usage:
  .venv/bin/python scripts/propose_soft_gates.py
  .venv/bin/python scripts/propose_soft_gates.py --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from libs.guidelines.soft_gate_backfill import ALLOW_APPLY, propose_soft_gate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply only the allow-list (1.5.13, 1.3.1, 1.3.5, 1.3.6).",
    )
    args = parser.parse_args(argv)
    print(json.dumps({"allow_apply": sorted(ALLOW_APPLY), "apply": args.apply}))
    if args.apply:
        print("Apply is a knowledge-graph edit. Run apply_rule_edit per allow-list row.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
