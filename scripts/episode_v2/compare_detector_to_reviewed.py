"""Compare v2 detector output (reviewed replay OFF) to curator-reviewed episodes.

Usage::
    python -m scripts.episode_v2.compare_detector_to_reviewed 6142203497 4867552062
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from scripts.episode_v2.dry_run_patient import _ReadOnlyClient, _install_v1_bundle

_REVIEWED_QUERY = """
MATCH (p:Patient {id: $patient_id})-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
WHERE ep.reviewed_at IS NOT NULL
OPTIONAL MATCH (enc:Encounter)-[:IS_PART_OF]->(ep)
WITH ep.episode_id AS episode_id,
     coalesce(ep.site_key, ep.suspected_site) AS site_key,
     coalesce(ep.start_date, ep.end_date) AS sort_date,
     collect(DISTINCT enc.id) AS encounter_ids
RETURN episode_id, site_key, encounter_ids
ORDER BY sort_date, episode_id
"""


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


async def _compare_one(
    patient_id: str, inner: Any, client: _ReadOnlyClient, *, show_diff: bool
) -> dict[str, Any]:
    from services.analysis_worker.app.episode_detector_v2 import runner

    rows = [dict(r) for r in inner.run(_REVIEWED_QUERY, patient_id=patient_id)]
    reviewed_sets: list[tuple[str, str, set[str]]] = []
    for row in rows:
        eid = str(row.get("episode_id") or "")
        sk = str(row.get("site_key") or "unknown")
        ids = {str(x) for x in (row.get("encounter_ids") or []) if x}
        reviewed_sets.append((eid, sk, ids))

    original = runner.load_reviewed_episode_replay
    runner.load_reviewed_episode_replay = lambda *args, **kwargs: []
    try:
        result = await runner.build_episodes(
            patient_id=patient_id,
            patient_client=client,
            anchors=None,
            domain_id="",
        )
    finally:
        runner.load_reviewed_episode_replay = original

    by_site: dict[str, list[Any]] = {}
    for ep in result.resolved_episodes:
        by_site.setdefault(ep.site_key, []).append(ep)

    out_rows: list[dict[str, Any]] = []
    for rev_episode_id, site_key, expected in reviewed_sets:
        cands = by_site.get(site_key, [])
        if not cands:
            out_rows.append(
                {
                    "reviewed_episode_id": rev_episode_id,
                    "site_key": site_key,
                    "matched": False,
                    "jaccard": 0.0,
                    "detector_episode_id": None,
                    "reviewed_n": len(expected),
                    "detector_n": 0,
                    "missing_n": len(expected),
                    "extra_n": 0,
                }
            )
            continue
        best = max(
            cands,
            key=lambda ep: _jaccard(expected, set(ep.encounter_ids)),
        )
        actual = set(best.encounter_ids)
        jac = _jaccard(expected, actual)
        row: dict[str, Any] = {
            "reviewed_episode_id": rev_episode_id,
            "site_key": site_key,
            "matched": True,
            "jaccard": round(jac, 4),
            "detector_episode_id": best.episode_id,
            "reviewed_n": len(expected),
            "detector_n": len(actual),
            "overlap": len(expected & actual),
            "missing_n": len(expected - actual),
            "extra_n": len(actual - expected),
            "detector_tier": best.confidence_tier,
            "detector_errors": list(result.errors),
        }
        if show_diff:
            row["missing_encounter_ids"] = sorted(expected - actual)
            row["extra_encounter_ids"] = sorted(actual - expected)
        out_rows.append(row)
    return {"patient_id": patient_id, "episodes": out_rows}


async def _run(patient_ids: list[str], *, show_diff: bool) -> int:
    from libs.keyvault.loader import load_keyvault_secrets
    from libs.neo4j_client.client import PatientGraphClient

    load_keyvault_secrets()
    _install_v1_bundle()
    inner = PatientGraphClient()
    client = _ReadOnlyClient(inner)
    try:
        report = [
            await _compare_one(pid, inner, client, show_diff=show_diff)
            for pid in patient_ids
        ]
    finally:
        client.close()
    print(json.dumps(report, indent=2))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("patient_ids", nargs="+")
    p.add_argument(
        "--diff",
        action="store_true",
        help="Include missing_encounter_ids and extra_encounter_ids per episode.",
    )
    args = p.parse_args()
    return asyncio.run(_run(args.patient_ids, show_diff=args.diff))


if __name__ == "__main__":
    raise SystemExit(main())
