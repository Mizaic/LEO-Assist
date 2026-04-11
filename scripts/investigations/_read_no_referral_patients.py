"""Read every encounter for all no-referral confirmed-cancer patients.

Pulls patients whose EpisodeOfCare has flags containing NO_REFERRAL,
then chronologically reads all encounters for each, highlighting any
clinical signal related to cancer, treatment, specialist visits,
referrals, imaging, and exclusions.

Output is written to scripts/investigations/no_referral_encounters/
One file per patient.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

from neo4j import GraphDatabase  # noqa: E402
from libs.domains.ncda_concept_sets import (  # noqa: E402
    CANCER_TYPE_IDS,
    TREATMENT_IDS,
    SEEN_BY_SPECIALIST_IDS,
    FAST_TRACK_REFERRAL_IDS,
    CANCER_EXCLUSION_IDS,
    CANCER_HISTORY_IDS,
)

driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI"),
    auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")),
)

OUT_DIR = Path(__file__).parent / "no_referral_encounters"
OUT_DIR.mkdir(exist_ok=True)

# -- signal concept sets ------------------------------------------------
CANCER_IDS = frozenset(str(c) for c in CANCER_TYPE_IDS)
TREAT_IDS = frozenset(str(c) for c in TREATMENT_IDS)
SPEC_IDS = frozenset(str(c) for c in SEEN_BY_SPECIALIST_IDS)
REF_IDS = frozenset(str(c) for c in FAST_TRACK_REFERRAL_IDS)
EXCL_IDS = frozenset(str(c) for c in CANCER_EXCLUSION_IDS)
HIST_IDS = frozenset(str(c) for c in CANCER_HISTORY_IDS)
ALL_SIGNAL_IDS = CANCER_IDS | TREAT_IDS | SPEC_IDS | REF_IDS | EXCL_IDS | HIST_IDS

CANCER_KEYWORDS = [
    "cancer",
    "oncol",
    "chemoth",
    "radioth",
    "mastect",
    "lumpect",
    "biopsy",
    "breast clinic",
    "staging",
    "metastas",
    "lymphoma",
    "tumour",
    "tumor",
    "hospice",
    "loros",
    "palliative",
    "herceptin",
    "tamoxifen",
    "letrozole",
    "anastrozole",
    "denosumab",
    "bisphosphon",
    "trastuzumab",
    "capecitabine",
    "paclitaxel",
    "carboplatin",
    "bevacizumab",
    "hormone therapy",
    "endocrine",
    "thyroid",
    "thyroidectomy",
    "prostat",
    "colorect",
    "bowel cancer",
    "colostomy",
    "ileostomy",
    "colonoscopy",
    "endoscopy",
    "urgent referral",
    "two week",
    "2ww",
    "2 week wait",
    "fast track",
    "suspected cancer",
    "malignant",
    "malignancy",
    "carcinoma",
    "sarcoma",
    "lymph node",
    "metastasis",
    "metastatic",
    "radiograph",
    "ct scan",
    "mri",
    "bone scan",
    "pet scan",
    "oncology clinic",
    "haematol",
    "haematology",
    "spinal cord",
    "bone pain",
    "hypercalcaemia",
    "hypercalcemia",
    "weight loss",
    "night sweat",
]

# -- queries ------------------------------------------------------------
Q_NO_REFERRAL_PATIENTS = """
MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
WHERE ep.referral_site = 'no_referral'
RETURN DISTINCT
    toString(p.id)          AS patient_id,
    toString(ep.episode_id) AS episode_id,
    ep.condition_type       AS condition_type,
    ep.diagnosis_date       AS diagnosis_date,
    ep.flags                AS flags,
    ep.status               AS status
ORDER BY ep.diagnosis_date
"""

Q_ALL_ENCOUNTERS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $pid
  AND e.date IS NOT NULL
OPTIONAL MATCH (e)-[r:DOCUMENTS]->(d)
WITH e, collect({
    cid:    toString(d.conceptId),
    name:   d.name,
    tag:    d.semanticTag,
    source: r.source
}) AS docs
RETURN
    toString(e.id)   AS eid,
    toString(e.date) AS dt,
    e.text           AS text,
    docs
ORDER BY e.date, e.id
"""


def _marker(cid: str) -> str:
    if cid in CANCER_IDS:
        return "[DIAG]"
    if cid in TREAT_IDS:
        return "[TREAT]"
    if cid in SPEC_IDS:
        return "[SPEC]"
    if cid in REF_IDS:
        return "[REF]"
    if cid in EXCL_IDS:
        return "[EXCL]"
    if cid in HIST_IDS:
        return "[HIST]"
    return "[?]"


def _has_keyword(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in CANCER_KEYWORDS)


def analyse_patient(
    session,
    pid: str,
    episode_id: str,
    condition_type: str,
    diagnosis_date: str,
    flags: str,
) -> None:
    rows = list(session.run(Q_ALL_ENCOUNTERS, pid=pid))
    out_path = OUT_DIR / f"{pid}.txt"

    lines: list[str] = []
    lines.append("=" * 72)
    lines.append(f"PATIENT:        {pid}")
    lines.append(f"EPISODE:        {episode_id}")
    lines.append(f"CONDITION TYPE: {condition_type}")
    lines.append(f"DIAGNOSIS DATE: {diagnosis_date}")
    lines.append(f"FLAGS:          {flags}")
    lines.append(f"TOTAL ENCOUNTERS: {len(rows)}")
    lines.append("=" * 72)

    signal_count = 0
    for row in rows:
        text = (row["text"] or "").strip()
        docs = [d for d in (row["docs"] or []) if d.get("name")]
        signal_docs = [d for d in docs if d.get("cid") in ALL_SIGNAL_IDS]
        kw_hit = _has_keyword(text)

        if not signal_docs and not kw_hit:
            continue

        signal_count += 1
        lines.append("")
        lines.append(f"--- {row['dt']}  {row['eid']} ---")
        snippet = text[:400].replace("\n", " | ")
        lines.append(f"TEXT: {snippet}")

        if signal_docs:
            lines.append("CODED SIGNALS:")
            for d in signal_docs:
                lines.append(
                    f"  {_marker(d['cid'])} {d['name']} "
                    f"[{d.get('tag', '')}] cid={d['cid']}"
                )

        if docs and not signal_docs:
            lines.append("ALL CODES (no direct signal):")
            for d in docs[:8]:
                lines.append(f"  - {d['name']} [{d.get('tag', '')}]")

    lines.append("")
    lines.append(f"Signal encounters shown: {signal_count} / {len(rows)} total")
    lines.append("=" * 72)

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Written: {out_path.name}  ({signal_count} signal encounters)")


def main() -> None:
    with driver.session() as session:
        patients = list(session.run(Q_NO_REFERRAL_PATIENTS))

    print(f"\nNo-referral patients found: {len(patients)}\n")
    for row in patients:
        pid = row["patient_id"]
        print(
            f"Processing {pid}  "
            f"condition={row['condition_type']}  "
            f"dx={row['diagnosis_date']}  "
            f"status={row['status']}"
        )
        with driver.session() as session:
            analyse_patient(
                session,
                pid=pid,
                episode_id=row["episode_id"],
                condition_type=row["condition_type"],
                diagnosis_date=row["diagnosis_date"],
                flags=(row["flags"] or ""),
            )

    driver.close()
    print(f"\nAll files written to: {OUT_DIR}")


if __name__ == "__main__":
    main()
