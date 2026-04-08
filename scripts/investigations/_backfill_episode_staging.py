from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / "secrets" / ".env.config", override=False)
    load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)
except Exception:
    pass

try:
    from libs.keyvault.loader import load_keyvault_secrets

    load_keyvault_secrets()
except Exception:
    pass

from libs.neo4j_client.client import PatientGraphClient
from libs.staging.engine import StagingRulesEngine
from libs.staging.tnm_parser import parse_tnm_triplet

_EXPLICIT_STAGE_RE = re.compile(
    r"\b(?:stage\s*)?([0-4]|i{1,3}|iv)(?:\s*[abc])?\b",
    re.IGNORECASE,
)

_Q_EPISODES = """
MATCH (ep:EpisodeOfCare)
OPTIONAL MATCH (enc:Encounter)-[r:IS_PART_OF]->(ep)
  WHERE r.milestone_type IN ['diagnosis', 'diagnosis_confirmed']
WITH ep, count(enc) AS dx_count
WHERE dx_count > 0
RETURN ep.episode_id AS episode_id,
       toString(ep.cancer_type) AS cancer_type,
       toString(ep.referral_date) AS referral_date,
       toString(ep.end_date) AS end_date
ORDER BY referral_date
"""

_Q_EVIDENCE = """
MATCH (ep:EpisodeOfCare {episode_id: $episode_id})
MATCH (enc:Encounter)-[:IS_PART_OF]->(ep)
WHERE toString(enc.date) >= $window_start
  AND toString(enc.date) <= $window_end
OPTIONAL MATCH (enc)-[d:DOCUMENTS]->(c)
RETURN toString(enc.date) AS encounter_date,
       coalesce(enc.text, '') AS encounter_text,
       coalesce(c.name, '') AS concept_name,
       coalesce(toString(d.assertion), 'present') AS assertion
ORDER BY encounter_date
"""

_Q_SET = """
MATCH (ep:EpisodeOfCare {episode_id: $episode_id})
SET ep.cancer_stage = $cancer_stage,
    ep.cancer_stage_raw = $cancer_stage_raw,
    ep.cancer_stage_group = $cancer_stage_group,
    ep.tnm_t = $tnm_t,
    ep.tnm_n = $tnm_n,
    ep.tnm_m = $tnm_m,
    ep.staging_system = $staging_system,
    ep.staging_source = $staging_source,
    ep.staging_confidence = $staging_confidence,
    ep.updated_at = datetime()
"""


def _extract(rows: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    explicit: str | None = None
    tnm: str | None = None
    for row in rows:
        if str(row.get("assertion") or "present").lower() not in ("present", ""):
            continue
        concept_name = str(row.get("concept_name") or "")
        text = str(row.get("encounter_text") or "")
        if explicit is None:
            m = _EXPLICIT_STAGE_RE.search(concept_name) or _EXPLICIT_STAGE_RE.search(text)
            if m:
                explicit = m.group(0)
        if tnm is None:
            parsed = parse_tnm_triplet(concept_name) or parse_tnm_triplet(text)
            if parsed:
                tnm = parsed.raw
        if explicit and tnm:
            break
    return explicit, tnm


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill EpisodeOfCare staging fields")
    ap.add_argument("--apply", action="store_true", help="Write updates (default is dry-run)")
    ap.add_argument("--limit", type=int, default=0, help="Optional max episodes to process")
    ap.add_argument(
        "--output",
        default="scripts/investigations/output/episode_staging_backfill_report.json",
    )
    args = ap.parse_args()

    client = PatientGraphClient()
    engine = StagingRulesEngine()
    engine.load_rules()
    try:
        episodes = client.run(_Q_EPISODES) or []
        if args.limit and args.limit > 0:
            episodes = episodes[: args.limit]

        processed = 0
        staged = 0
        unknown = 0
        by_source: dict[str, int] = {}
        preview: list[dict[str, Any]] = []

        for ep in episodes:
            episode_id = str(ep.get("episode_id") or "")
            start = str(ep.get("referral_date") or "")[:10]
            end = str(ep.get("end_date") or "")[:10] or start
            if not episode_id or not start:
                continue
            rows = client.run(
                _Q_EVIDENCE,
                episode_id=episode_id,
                window_start=start,
                window_end=end,
            ) or []
            explicit, tnm = _extract(rows)
            source = "coded" if (explicit or tnm) else "text_scan"
            result = engine.resolve_stage(
                cancer_type_snomed=str(ep.get("cancer_type") or ""),
                explicit_stage=explicit,
                tnm=tnm,
                source=source,
            )
            processed += 1
            if result.cancer_stage == "unknown":
                unknown += 1
            else:
                staged += 1
            by_source[result.staging_source] = by_source.get(result.staging_source, 0) + 1

            if args.apply:
                client.run(
                    _Q_SET,
                    episode_id=episode_id,
                    cancer_stage=result.cancer_stage,
                    cancer_stage_raw=result.cancer_stage_raw,
                    cancer_stage_group=result.cancer_stage_group,
                    tnm_t=result.tnm_t,
                    tnm_n=result.tnm_n,
                    tnm_m=result.tnm_m,
                    staging_system=result.staging_system,
                    staging_source=result.staging_source,
                    staging_confidence=result.staging_confidence,
                )

            if len(preview) < 30:
                preview.append(
                    {
                        "episode_id": episode_id,
                        "cancer_type": ep.get("cancer_type"),
                        "cancer_stage": result.cancer_stage,
                        "cancer_stage_group": result.cancer_stage_group,
                        "staging_system": result.staging_system,
                        "staging_source": result.staging_source,
                    }
                )

        report = {
            "mode": "apply" if args.apply else "dry_run",
            "processed": processed,
            "staged": staged,
            "unknown": unknown,
            "coverage_pct": round((staged * 100.0 / processed), 1) if processed else 0.0,
            "by_source": by_source,
            "preview": preview,
        }
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        print(f"Wrote {out_path}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
