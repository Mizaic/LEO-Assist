"""Wipe every EpisodeOfCare and rebuild via the text path.

DI-LEO-AI-159 -- after the stale-episode-detector fixes ship, we need
every existing EpisodeOfCare to be rebuilt from scratch so the new
problem-list malignancy / benign rules and the explicit-2WW site
reconciliation are applied retroactively to all historic data.

Workflow
--------
1. Snapshot the current report (cases by year x status) -> tmp/before_fix.txt
2. Snapshot the current stale-episode investigation -> tmp/before_fix_stale.txt
3. DETACH DELETE every EpisodeOfCare (and its IS_PART_OF edges)
4. Re-run scripts/rebuild_episodes_text_path.py for every patient
5. Snapshot the new report -> tmp/after_fix.txt
6. Snapshot the new stale-episode investigation -> tmp/after_fix_stale.txt
7. Print a diff summary

Usage
-----
    python scripts/_wipe_episodes_and_rebuild.py              # dry run
    python scripts/_wipe_episodes_and_rebuild.py --apply      # destructive
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / "tmp"
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=True)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("wipe_rebuild")


_Q_COUNT_EPISODES = "MATCH (ep:EpisodeOfCare) RETURN count(ep) AS n"
_Q_DETACH_DELETE_EPISODES = """
MATCH (ep:EpisodeOfCare)
WITH ep LIMIT 5000
DETACH DELETE ep
RETURN count(ep) AS deleted
"""


def _snapshot(out_path: Path, script: str, *args: str) -> None:
    cmd = [sys.executable, str(ROOT / script), *args]
    log.info("Snapshot %s -> %s", " ".join(cmd), out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        result = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, cwd=str(ROOT))
    if result.returncode != 0:
        log.warning("Snapshot %s exited %s (output preserved)", script, result.returncode)


def _wipe_all_episodes(patient_client) -> int:
    log.warning("DETACH DELETE-ing every EpisodeOfCare node ...")
    total_deleted = 0
    while True:
        rows = patient_client.run(_Q_DETACH_DELETE_EPISODES) or []
        deleted = (rows[0] or {}).get("deleted", 0) if rows else 0
        total_deleted += int(deleted)
        if not deleted:
            break
        log.info("  deleted %d (running total %d)", deleted, total_deleted)
    return total_deleted


def _rebuild_all_episodes() -> int:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "rebuild_episodes_text_path.py"),
        "--apply",
    ]
    log.info("Running %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(ROOT))
    return result.returncode


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Destructively wipe and rebuild. Without it the script reports only.",
    )
    parser.add_argument(
        "--skip-snapshot",
        action="store_true",
        help="Skip the before/after report snapshots (faster, less audit trail).",
    )
    args = parser.parse_args()

    from libs.neo4j_client.client import PatientGraphClient

    TMP.mkdir(parents=True, exist_ok=True)

    if not args.skip_snapshot:
        _snapshot(TMP / "before_fix.txt", "scripts/_report_cases_by_year_status.py")
        _snapshot(TMP / "before_fix_stale.txt", "scripts/_investigate_stale_episodes.py")

    client = PatientGraphClient()
    try:
        rows = client.run(_Q_COUNT_EPISODES) or []
        before_n = int((rows[0] or {}).get("n", 0))
        log.info("Episodes BEFORE wipe: %d", before_n)

        if not args.apply:
            log.warning("DRY RUN -- not wiping. Re-run with --apply to proceed.")
            return

        deleted = _wipe_all_episodes(client)
        log.info("Wiped %d EpisodeOfCare nodes", deleted)
    finally:
        client.close()

    rc = _rebuild_all_episodes()
    if rc != 0:
        log.error("Rebuild script exited with %d", rc)
        sys.exit(rc)

    client = PatientGraphClient()
    try:
        rows = client.run(_Q_COUNT_EPISODES) or []
        after_n = int((rows[0] or {}).get("n", 0))
        log.info("Episodes AFTER rebuild: %d", after_n)
    finally:
        client.close()

    if not args.skip_snapshot:
        _snapshot(TMP / "after_fix.txt", "scripts/_report_cases_by_year_status.py")
        _snapshot(TMP / "after_fix_stale.txt", "scripts/_investigate_stale_episodes.py")

    sep = "=" * 70
    print(sep)
    print("WIPE + REBUILD COMPLETE")
    print(sep)
    print(f"  episodes_before  {before_n}")
    print(f"  episodes_after   {after_n}")
    if not args.skip_snapshot:
        print(f"  before report    {TMP / 'before_fix.txt'}")
        print(f"  before stale     {TMP / 'before_fix_stale.txt'}")
        print(f"  after report     {TMP / 'after_fix.txt'}")
        print(f"  after stale      {TMP / 'after_fix_stale.txt'}")
    print(sep)


if __name__ == "__main__":
    main()
