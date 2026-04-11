from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from libs.keyvault.loader import load_keyvault_secrets
from libs.neo4j_client.client import PatientGraphClient
from libs.pipeline_graph.subgraphs.anchor import _load_registry
from services.analysis_worker.app.analyzers.anchor_detector import detect_anchors

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

OUT = (
    ROOT
    / "scripts"
    / "investigations"
    / "output"
    / "missing_first_presentation_investigation.json"
)

Q_EXCLUDED = """
MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
WHERE ep.referral_date IS NOT NULL
  AND NOT ep.status IN ['merged', 'closed_phantom', 'closed_related']
  AND EXISTS {
    MATCH (:Encounter)-[rr:IS_PART_OF]->(ep)
    WHERE rr.milestone_type = 'referral'
  }
  AND ep.first_presentation_date IS NULL
RETURN
  toString(p.id) AS patient_id,
  ep.episode_id AS episode_id,
  ep.cancer_type AS cancer_type,
  toString(ep.referral_date) AS referral_date
ORDER BY referral_date
"""

_PLACE_SEMANTIC_TAGS = {"environment", "place", "physical_object"}
_NON_COMPLAINT_SEMANTIC_TAGS = {
    "procedure",
    "qualifier value",
    "record artifact",
    "event",
    "observable entity",
}
_NON_COMPLAINT_NAME_RE = re.compile(
    r"\b("
    r"seen in|seen by|consultation|appointment|outpatient|"
    r"screening|programme|program|clinic|service|"
    r"general practitioner surgery|primary care establishment|"
    r"accident and emergency|emergency department"
    r")\b",
    re.IGNORECASE,
)
_CODE_LIKE_NAME_RE = re.compile(r"^[0-9,\s]+$")


def _parse_day(raw: str) -> date | None:
    try:
        return date.fromisoformat(str(raw)[:10])
    except Exception:
        return None


def _tag(a: dict[str, Any]) -> str:
    return str(a.get("semantic_tag") or "").strip().lower().replace("_", " ")


def _present(a: dict[str, Any]) -> bool:
    return str(a.get("assertion") or "present").strip().lower() in ("", "present")


def _is_complaint(a: dict[str, Any]) -> bool:
    if not _present(a):
        return False
    nm = str(a.get("concept_name") or "").strip()
    if not nm:
        return False
    if _CODE_LIKE_NAME_RE.fullmatch(nm):
        return False
    tg = _tag(a)
    if tg in _PLACE_SEMANTIC_TAGS or tg in _NON_COMPLAINT_SEMANTIC_TAGS:
        return False
    if _NON_COMPLAINT_NAME_RE.search(nm):
        return False
    return True


def main() -> None:
    pc = PatientGraphClient()
    try:
        excluded = pc.run(Q_EXCLUDED) or []
        registry = _load_registry("cancer_audit")
        bucket = Counter()
        by_bucket_examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
        far_terms = Counter()

        for i, ep in enumerate(excluded, 1):
            pid = str(ep["patient_id"])
            ref_raw = str(ep["referral_date"] or "")
            ref_day = _parse_day(ref_raw)
            if ref_day is None:
                bucket["bad_referral_date"] += 1
                continue

            start = (ref_day - timedelta(days=90)).isoformat()
            anchors = detect_anchors(
                patient_id=pid,
                start_date=start,
                end_date=ref_day.isoformat(),
                patient_client=pc,
                registry=registry,
            )
            pre_ref = []
            for a in anchors.first_presentation_anchors:
                d = _parse_day(str(a.get("encounter_date") or ""))
                if d and (ref_day - timedelta(days=90)) <= d < ref_day:
                    pre_ref.append(a)

            complaints = [a for a in pre_ref if _is_complaint(a)]

            rec = {
                "patient_id": pid,
                "episode_id": ep["episode_id"],
                "cancer_type": ep.get("cancer_type"),
                "referral_date": ref_raw,
                "first_presentation_anchor_count": len(pre_ref),
                "complaint_candidate_count": len(complaints),
            }

            if not pre_ref:
                k = "no_first_presentation_anchors_in_window"
            elif not complaints:
                k = "anchors_present_but_non_complaint_only"
                rec["sample_anchor_names"] = list(
                    dict.fromkeys(str(a.get("concept_name") or "") for a in pre_ref)
                )[:5]
            else:
                complaint_days = sorted(
                    {_parse_day(str(a.get("encounter_date") or "")) for a in complaints}
                )
                complaint_days = [d for d in complaint_days if d]
                has_close = any(0 <= (ref_day - d).days <= 14 for d in complaint_days)
                if has_close:
                    k = "unexpected_should_have_first_presentation"
                else:
                    k = "complaint_found_but_no_referral_within_14_days"
                    far_terms.update(
                        str(a.get("concept_name") or "") for a in complaints
                    )
                    rec["earliest_complaint_date"] = min(complaint_days).isoformat()
                    rec["days_to_referral_from_earliest"] = (
                        ref_day - min(complaint_days)
                    ).days
                    rec["sample_complaints"] = list(
                        dict.fromkeys(
                            str(a.get("concept_name") or "") for a in complaints
                        )
                    )[:5]

            bucket[k] += 1
            if len(by_bucket_examples[k]) < 15:
                by_bucket_examples[k].append(rec)

            if i % 20 == 0:
                print(f"processed {i}/{len(excluded)}")

        out = {
            "excluded_total": len(excluded),
            "bucket_counts": dict(bucket),
            "examples": by_bucket_examples,
            "top_far_complaints": far_terms.most_common(25),
        }
        OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {"excluded_total": len(excluded), "bucket_counts": dict(bucket)},
                indent=2,
            )
        )
        print(f"wrote: {OUT}")
    finally:
        pc.close()


if __name__ == "__main__":
    main()
