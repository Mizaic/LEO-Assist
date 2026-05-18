"""Compare no-replay v2 detector output with reviewed prostate/urology episodes.

This is a live-graph calibration helper, not a unit test. It disables
reviewed replay so we can see whether the detector itself rediscovers
the clinician-reviewed prostate_urological episodes.

Include patients such as 4867552062 after sign-off so dry-runs here feed
the same learning loop as ``reviewed_breast_regression.py``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.episode_v2.dry_run_patient import _ReadOnlyClient, _install_v1_bundle

_SITE_KEY = "prostate_urological"

_REVIEWED_PROSTATE_QUERY = """
MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
WHERE ep.reviewed_at IS NOT NULL
  AND coalesce(ep.site_key, ep.suspected_site, ep.cancer_type,
               ep.primary_cancer_type) = $site_key
  AND ($patient_id IS NULL OR p.id = $patient_id)
OPTIONAL MATCH (enc:Encounter)-[rel:IS_PART_OF]->(ep)
RETURN p.id AS patient_id,
       ep.episode_id AS episode_id,
       ep.start_date AS start_date,
       ep.end_date AS end_date,
       ep.status AS status,
       collect(DISTINCT enc.id) AS encounter_ids,
       collect(DISTINCT {
           id: enc.id,
           date: enc.date,
           milestone_type: rel.milestone_type,
           text: left(enc.text, 240)
       }) AS reviewed_link_details
ORDER BY p.id, ep.episode_id
"""

_ENCOUNTER_DETAIL_QUERY = """
MATCH (enc:Encounter)
WHERE enc.id IN $ids
RETURN enc.id AS id,
       enc.date AS date,
       left(enc.text, 240) AS text
ORDER BY enc.date, enc.id
"""


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)[:10]


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    return len(left & right) / len(left | right)


def _default_output() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return (
        Path("artifacts")
        / "episode_v2"
        / f"reviewed_prostate_urological_regression_{stamp}.json"
    )


def _reviewed_detail_by_id(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item["id"]: item
        for item in row.get("reviewed_link_details") or []
        if item.get("id")
    }


def _serialise_reviewed_details(
    ids: set[str], details_by_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    return [
        {
            "encounter_id": enc_id,
            "date": _iso(details_by_id.get(enc_id, {}).get("date")),
            "milestone_type": details_by_id.get(enc_id, {}).get("milestone_type"),
            "text": details_by_id.get(enc_id, {}).get("text"),
        }
        for enc_id in sorted(
            ids, key=lambda item: (_iso(details_by_id.get(item, {}).get("date")) or "", item)
        )
    ]


def _serialise_detector_details(
    ids: set[str], patient_client: Any
) -> list[dict[str, Any]]:
    rows = patient_client.run(_ENCOUNTER_DETAIL_QUERY, ids=list(ids))
    return [
        {
            "encounter_id": row["id"],
            "date": _iso(row.get("date")),
            "text": row.get("text"),
        }
        for row in rows
    ]


async def _run(
    output: Path,
    *,
    patient_id: str | None,
    include_details: bool = False,
) -> int:
    from libs.keyvault.loader import load_keyvault_secrets
    from libs.neo4j_client.client import PatientGraphClient
    from services.analysis_worker.app.episode_detector_v2 import runner

    load_keyvault_secrets()
    _install_v1_bundle()
    runner.load_reviewed_episode_replay = lambda *args, **kwargs: []

    inner = PatientGraphClient()
    client = _ReadOnlyClient(inner)
    rows: list[dict[str, Any]] = []
    try:
        reviewed_rows = [
            dict(row)
            for row in inner.run(
                _REVIEWED_PROSTATE_QUERY,
                site_key=_SITE_KEY,
                patient_id=patient_id,
            )
        ]
        for row in reviewed_rows:
            result = await runner.build_episodes(
                patient_id=row["patient_id"],
                patient_client=client,
                anchors=None,
                domain_id="",
            )
            expected = set(row.get("encounter_ids") or [])
            site_eps = [
                ep
                for ep in result.resolved_episodes
                if ep.site_key == _SITE_KEY
            ]
            best = max(
                site_eps,
                key=lambda ep: _jaccard(expected, set(ep.encounter_ids)),
                default=None,
            )
            if best is None:
                rows.append(
                    {
                        "patient_id": row["patient_id"],
                        "episode_id": row["episode_id"],
                        "matched": False,
                        "candidate_count": 0,
                    }
                )
                continue
            actual = set(best.encounter_ids)
            regression_row: dict[str, Any] = {
                "patient_id": row["patient_id"],
                "episode_id": row["episode_id"],
                "matched": True,
                "candidate_count": len(site_eps),
                "reviewed_start": _iso(row.get("start_date")),
                "detector_start": _iso(best.start_date),
                "reviewed_links": len(expected),
                "detector_links": len(actual),
                "overlap": len(expected & actual),
                "missing": len(expected - actual),
                "extra": len(actual - expected),
                "jaccard": round(_jaccard(expected, actual), 4),
                "tier": best.confidence_tier,
                "review_reasons": best.review_reasons,
            }
            if include_details:
                details_by_id = _reviewed_detail_by_id(row)
                regression_row["missing_details"] = _serialise_reviewed_details(
                    expected - actual, details_by_id
                )
                regression_row["extra_details"] = _serialise_detector_details(
                    actual - expected, inner
                )
            rows.append(regression_row)
    finally:
        client.close()

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cohort": "reviewed_prostate_urological",
        "site_key": _SITE_KEY,
        "patient_filter": patient_id,
        "count": len(rows),
        "mean_jaccard": round(
            sum(row.get("jaccard", 0.0) for row in rows) / max(len(rows), 1),
            4,
        ),
        "total_missing": sum(row.get("missing", 0) for row in rows),
        "total_extra": sum(row.get("extra", 0) for row in rows),
        "rows": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=False) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=False))
    print(f"Wrote {output}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=_default_output())
    parser.add_argument(
        "--patient-id",
        type=str,
        default=None,
        help="Optional single patient id (e.g. 4867552062 after curator sign-off).",
    )
    parser.add_argument(
        "--include-details",
        action="store_true",
        help="Include missing/extra encounter dates and text snippets.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    return asyncio.run(
        _run(
            args.output,
            patient_id=args.patient_id,
            include_details=args.include_details,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
