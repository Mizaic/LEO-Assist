"""Dump the 90-day post-referral encounter window for every stale episode
into one file per (patient, episode) under tmp/stale_windows/.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

LIST = ROOT / "scripts" / "_stale_patient_list.json"
OUT_DIR = ROOT / "tmp" / "stale_windows"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main() -> None:
    items = json.loads(LIST.read_text())
    print(f"Dumping {len(items)} episode windows to {OUT_DIR}")
    for i, it in enumerate(items, 1):
        pid = it["pid"]
        eid = it["eid"]
        out = OUT_DIR / f"{pid}__{eid[:12]}.txt"
        cmd = [
            sys.executable, str(ROOT / "scripts" / "_pull_patient_window.py"),
            pid, "--episode", eid,
            "--days-after", "90", "--days-before", "14",
            "--max-text", "6000",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True,
                                env=os.environ)
        out.write_text(result.stdout + ("\n--STDERR--\n" + result.stderr
                                         if result.stderr else ""))
        n_enc = result.stdout.count("--- ")
        print(f"  [{i:02d}/{len(items)}] {pid} {eid[:12]} "
              f"site={it['site']:<22} encs={n_enc} -> {out.name}")


if __name__ == "__main__":
    main()
