"""Run Episode Detector v2 dry-run for every patient not fully review-signed off.

A patient is *skipped* when they have at least one :EpisodeOfCare and every
such episode has ``reviewed_at`` set. Everyone else is included: no episodes
yet, or at least one episode with ``reviewed_at IS NULL``.

Atlas trace:
  DI: DI-8A5FCF4F (Defence-in-depth episode detector)

Usage::

    # List matching patient IDs and exit
    python -m scripts.episode_v2.batch_dry_run_unreviewed --list-only

    # Dry-run first 5 (smoke test)
    python -m scripts.episode_v2.batch_dry_run_unreviewed --limit 5

    # All unreviewed (or partially reviewed) patients
    python -m scripts.episode_v2.batch_dry_run_unreviewed

    # Restrict to one GP / org (same param shape as org-scoped APIs)
    python -m scripts.episode_v2.batch_dry_run_unreviewed --scope-org-ids org-abc-123
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Match Mission Control: episode sign-off is ``reviewed_at`` on :EpisodeOfCare
# (see services/analytics_api PATCH /mission-control/episodes/.../review).
# libs.auth.org_scope.ORG_PATIENT_FILTER pattern (``p`` + GP in scope list).
_UNREVIEWED_COHORT_ALL = """
MATCH (p:Patient)
OPTIONAL MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
WITH p, collect(ep) AS eps
WITH p, eps,
  size([e IN eps WHERE e IS NOT NULL]) AS n_ep,
  size([e IN eps WHERE e IS NOT NULL AND e.reviewed_at IS NULL]) AS n_unrev
WHERE n_unrev > 0 OR n_ep = 0
RETURN toString(p.id) AS patient_id
ORDER BY patient_id
"""
_UNREVIEWED_COHORT_IN_ORG = """
MATCH (p:Patient)
WHERE EXISTS {
  MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(_gp)
  WHERE _gp.id IN $scope_org_ids
}
OPTIONAL MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
WITH p, collect(ep) AS eps
WITH p, eps,
  size([e IN eps WHERE e IS NOT NULL]) AS n_ep,
  size([e IN eps WHERE e IS NOT NULL AND e.reviewed_at IS NULL]) AS n_unrev
WHERE n_unrev > 0 OR n_ep = 0
RETURN toString(p.id) AS patient_id
ORDER BY patient_id
"""


def _load_patient_ids(
    client: Any,
    *,
    scope_org_ids: list[str] | None,
) -> list[str]:
    if scope_org_ids:
        rows = client.run(
            _UNREVIEWED_COHORT_IN_ORG, scope_org_ids=scope_org_ids
        )
    else:
        rows = client.run(_UNREVIEWED_COHORT_ALL)
    return [str(r["patient_id"]) for r in rows if r.get("patient_id")]


def _write_jsonl(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, default=str) + "\n")


async def _run_batch(
    patient_ids: list[str],
    *,
    rulebook_version: str,
    text_only: bool,
    verbose: bool,
    jsonl_path: Path | None,
) -> int:
    from scripts.episode_v2.dry_run_patient import dry_run

    failed: list[str] = []
    for i, pid in enumerate(patient_ids, start=1):
        if verbose or len(patient_ids) <= 20:
            print(f"\n### [{i}/{len(patient_ids)}] patient {pid} ###\n", flush=True)
        try:
            code = await dry_run(
                pid, rulebook_version=rulebook_version, text_only=text_only
            )
            if jsonl_path is not None:
                _write_jsonl(
                    jsonl_path,
                    {
                        "patient_id": pid,
                        "ok": code == 0,
                        "ts": datetime.now(timezone.utc).isoformat(),
                    },
                )
            if code != 0:
                failed.append(pid)
        except Exception as exc:  # noqa: BLE001
            print(
                f"ERROR patient {pid}: {exc}\n{traceback.format_exc()}",
                file=sys.stderr,
                flush=True,
            )
            if jsonl_path is not None:
                _write_jsonl(
                    jsonl_path,
                    {
                        "patient_id": pid,
                        "ok": False,
                        "error": str(exc),
                        "ts": datetime.now(timezone.utc).isoformat(),
                    },
                )
            failed.append(pid)
    if failed:
        print(
            f"\nFinished with {len(failed)} failure(s) out of {len(patient_ids)}.",
            file=sys.stderr,
        )
        for pid in failed:
            print(f"  failed: {pid}", file=sys.stderr)
        return 1
    print(f"\nOK: {len(patient_ids)} patient(s) processed.", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Print matching patient IDs and exit (no dry-run).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Process at most N patients (after ordering by id).",
    )
    parser.add_argument(
        "--scope-org-ids",
        type=str,
        default="",
        help="Comma-separated GP/org ids; omit for all :Patient nodes in the graph.",
    )
    parser.add_argument(
        "--rulebook-version",
        choices=["v0", "v1"],
        default="v1",
    )
    parser.add_argument(
        "--text-only",
        action="store_true",
        help="Same as dry_run_patient: strip coded fields before the detector runs.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
    )
    parser.add_argument(
        "--jsonl",
        type=str,
        default="",
        help="Append one JSON line per patient (path under workspace or abs).",
    )
    args = parser.parse_args(argv)

    from libs.keyvault.loader import load_keyvault_secrets

    load_keyvault_secrets()
    from libs.neo4j_client.client import PatientGraphClient

    scope_org_ids = [
        x.strip()
        for x in (args.scope_org_ids or "").split(",")
        if x.strip()
    ] or None

    client = PatientGraphClient()
    try:
        patient_ids = _load_patient_ids(client, scope_org_ids=scope_org_ids)
    finally:
        client.close()

    if args.limit is not None:
        patient_ids = patient_ids[: max(0, args.limit)]

    if args.list_only:
        for pid in patient_ids:
            print(pid)
        print(f"total={len(patient_ids)}", file=sys.stderr)
        return 0

    if not patient_ids:
        print("No patients matched the cohort; nothing to do.", file=sys.stderr)
        return 0

    jsonl_path = Path(args.jsonl) if (args.jsonl or "").strip() else None
    if jsonl_path is not None:
        jsonl_path = jsonl_path.resolve()
        _write_jsonl(
            jsonl_path,
            {
                "event": "batch_start",
                "count": len(patient_ids),
                "ts": datetime.now(timezone.utc).isoformat(),
            },
        )

    return asyncio.run(
        _run_batch(
            patient_ids,
            rulebook_version=args.rulebook_version,
            text_only=args.text_only,
            verbose=args.verbose,
            jsonl_path=jsonl_path,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
