"""For each 'referral only' episode (no specialist, no diagnosis coded),
pull encounters in the 1-year window after the referral and print them
for review.  Highlights lines that mention the relevant cancer site.

Run:
    python scripts/investigations/_investigate_referral_only_episodes.py
    python scripts/investigations/_investigate_referral_only_episodes.py --out referral_only_review.txt
    python scripts/investigations/_investigate_referral_only_episodes.py --pid 4185994966
"""
from __future__ import annotations

import argparse
import re
import sys
import textwrap
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()

# Look from referral date through end of 2025 (no artificial 1-year cap)
AUDIT_START_YEAR = 2024
WINDOW_END = "2025-12-31"

# Keywords per canonical site used to highlight relevant sentences
_SITE_HIGHLIGHTS: dict[str, list[str]] = {
    "breast":            ["breast", "mammogram", "mammo", "lump", "biopsy", "benign", "fibroadenoma", "dcis", "malignant", "cancer", "clinic"],
    "non_site_specific": ["2ww", "fast track", "cancer", "malignant", "benign", "clinic", "referral", "result", "biopsy"],
    "lower_gi":          ["bowel", "colonoscopy", "colorectal", "lower gi", "rectal", "colon", "polyp", "biopsy", "cancer", "fit", "ct"],
    "skin":              ["skin", "melanoma", "lesion", "excision", "biopsy", "dermatology", "mole", "cancer"],
    "urological":        ["urology", "prostate", "bladder", "renal", "psa", "kidney", "biopsy", "cancer", "mri"],
    "head_and_neck":     ["ent", "head", "neck", "throat", "larynx", "nasendoscopy", "voice", "cancer", "biopsy"],
    "upper_gi":          ["ogd", "gastroscopy", "endoscopy", "oesophag", "stomach", "upper gi", "biopsy", "cancer"],
    "gynaecological":    ["gynae", "cervix", "uterus", "endometrium", "ovarian", "hysteroscopy", "biopsy", "cancer", "smear"],
    "lung":              ["lung", "cxr", "chest", "nodule", "ct", "biopsy", "cancer", "pulmonary", "pleural"],
    "haematological":    ["haematology", "lymphoma", "lymph", "blood", "ct", "biopsy", "cancer", "leukaemia"],
    "brain":             ["brain", "neuro", "mri", "tumour", "headache", "seizure", "cancer"],
    "childrens_tumour":  ["tumour", "paediatric", "mri", "cancer", "biopsy"],
}

_Q_EPISODES = """
MATCH (ep:EpisodeOfCare)
WHERE ep.patient_id IS NOT NULL
  AND ep.specialist_seen = false
  AND ep.status <> 'completed'
  AND ep.referral_date >= $audit_start
RETURN
    ep.patient_id     AS pid,
    ep.condition_type AS cond,
    ep.referral_date  AS rd
ORDER BY ep.patient_id, ep.referral_date
"""

_Q_ENCOUNTERS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $pid
  AND e.date >= $start_date
  AND e.date <= $end_date
OPTIONAL MATCH (e)-[doc:DOCUMENTS]->(concept)
WITH e, collect(coalesce(concept.name, toString(concept.conceptId))) AS codings
RETURN
    toString(e.id)                                  AS eid,
    toString(e.date)                                AS date,
    coalesce(e.text, e.note, e.description, '')     AS enc_text,
    codings
ORDER BY e.date
"""


def _parse_date(val) -> datetime | None:
    if val is None:
        return None
    if hasattr(val, "year"):
        return datetime(val.year, val.month, val.day)
    try:
        return datetime.strptime(str(val)[:10], "%Y-%m-%d")
    except Exception:
        return None


def _highlight(text: str, keywords: list[str]) -> str:
    """Return wrapped text; lines containing keywords are marked with >>."""
    lines = text.splitlines()
    out: list[str] = []
    kw_re = re.compile("|".join(re.escape(k) for k in keywords), re.IGNORECASE)
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        wrapped = textwrap.wrap(stripped, width=100)
        marker = ">> " if kw_re.search(stripped) else "   "
        for i, wline in enumerate(wrapped[:6]):  # cap at 6 lines per sentence
            out.append(f"    {marker if i == 0 else '   '}{wline}")
    return "\n".join(out[:50])  # cap total lines per encounter


def run(episodes: list[dict], out_path: Path | None) -> None:
    from libs.neo4j_client.client import PatientGraphClient

    sink = open(out_path, "w", encoding="utf-8") if out_path else None

    def emit(line: str = "") -> None:
        print(line)
        if sink:
            sink.write(line + "\n")

    client = PatientGraphClient()
    total = len(episodes)

    for idx, ep in enumerate(episodes, 1):
        pid   = str(ep["pid"])
        cond  = str(ep["cond"] or "unknown")
        rd    = _parse_date(ep["rd"])
        keywords = _SITE_HIGHLIGHTS.get(cond, ["cancer", "biopsy", "result", "clinic"])

        emit()
        emit("=" * 80)
        emit(f"EPISODE {idx}/{total}  pid={pid}  site={cond}")
        emit("=" * 80)

        if not rd:
            emit("  [NO REFERRAL DATE - skipping]")
            continue

        emit(f"  Referral: {rd.date()}  |  Window to: {WINDOW_END}")
        emit()

        try:
            with client.session() as s:
                encounters = list(s.run(
                    _Q_ENCOUNTERS,
                    pid=pid,
                    start_date=rd.strftime("%Y-%m-%d"),
                    end_date=WINDOW_END,
                ))
        except Exception as exc:
            emit(f"  [ERROR: {exc}]")
            continue

        if not encounters:
            emit("  [No encounters in window]")
            continue

        emit(f"  {len(encounters)} encounter(s) in window"
             f"  (>> = relevant to {cond}):")
        emit()

        for enc in encounters:
            eid     = str(enc["eid"] or "")[:8]
            date    = str(enc["date"] or "")
            text    = str(enc["enc_text"] or "")
            codings = [c for c in (enc["codings"] or []) if c.strip()]

            emit(f"  -- {date}  enc={eid} --")
            if codings:
                emit(f"  Coded: {', '.join(codings)}")
            if text:
                emit(_highlight(text, keywords))
            else:
                emit("     (no text)")
            emit()

    client.close()
    if sink:
        sink.close()
        print(f"\nWritten to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--pid", default=None, help="Limit to one patient ID")
    args = parser.parse_args()

    from libs.neo4j_client.client import PatientGraphClient
    client = PatientGraphClient()
    with client.session() as s:
        episodes = [dict(r) for r in s.run(
            _Q_EPISODES, audit_start=f"{AUDIT_START_YEAR}-01-01"
        )]
    client.close()

    if args.pid:
        episodes = [e for e in episodes if str(e["pid"]) == args.pid]

    print(f"Found {len(episodes)} referral-only episodes to review.")
    run(episodes, args.out)


if __name__ == "__main__":
    main()
