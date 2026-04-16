"""Build episode + coding ground truth from raw encounter text.

Reads all encounters from Neo4j, applies regex/keyword rules to identify:
  - Cancer type for each clinical episode
  - Episode milestone type per encounter (referral, first_presentation,
    diagnosis_confirmed, treatment_started)
  - Whether an episode marker exists in the GP record text (New Episode /
    Ongoing Episode)

Writes output to data/ground_truth/episode_ground_truth.json.

Usage:
    python scripts/build_episode_ground_truth.py [--out PATH] [--patient PATIENT_ID]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / "secrets" / ".env.secrets")
load_dotenv(ROOT / "secrets" / ".env.config")

from libs.neo4j_client.client import PatientGraphClient  # noqa: E402

# ---------------------------------------------------------------------------
# Cancer type patterns
# ---------------------------------------------------------------------------

_CANCER_TYPE_PATTERNS: List[Tuple[str, re.Pattern]] = [
    (
        "breast",
        re.compile(
            r"breast.{0,30}(cancer|carcinoma|neoplasm|malignant|tumour|tumor|"
            r"2ww|fast.?track)|fast.?track.{0,40}breast|"
            r"malignant.{0,20}breast|breast.{0,10}cancer|"
            r"Wide local excision of breast|sentinel lymph node",
            re.IGNORECASE,
        ),
    ),
    (
        "colorectal",
        re.compile(
            r"(colorectal|colon|rectal|bowel|lower.gi|LGI).{0,30}(cancer|"
            r"carcinoma|neoplasm|2ww|fast.?track|referral)|"
            r"fast.?track.{0,30}(lower.gi|colorectal|bowel)|"
            r"adenocarcinoma.{0,20}(colon|rectum|bowel)|"
            r"Xaalp|XaMeE",
            re.IGNORECASE,
        ),
    ),
    (
        "lung",
        re.compile(
            r"(lung|pulmonary|bronch).{0,30}(cancer|carcinoma|neoplasm|"
            r"malignant|2ww|fast.?track)|"
            r"fast.?track.{0,30}(lung|chest)|"
            r"(non.?small.?cell|small.?cell|NSCLC|SCLC)",
            re.IGNORECASE,
        ),
    ),
    (
        "prostate",
        re.compile(
            r"(prostate|prostatic).{0,30}(cancer|carcinoma|neoplasm|malignant|"
            r"2ww|fast.?track)|fast.?track.{0,30}prostate",
            re.IGNORECASE,
        ),
    ),
    (
        "upper_gi",
        re.compile(
            r"(oesophag|esophag|gastric|stomach|upper.gi).{0,30}(cancer|"
            r"carcinoma|adenocarcinoma|neoplasm|malignant|2ww|fast.?track)|"
            r"fast.?track.{0,30}upper.gi|"
            r"adenocarcinoma.{0,20}(oesophag|esophag|GOJ|gastro)|"
            r"XaMeJ|Xa0DF",
            re.IGNORECASE,
        ),
    ),
    (
        "head_neck",
        re.compile(
            r"(head.and.neck|head.neck|thyroid|laryn|pharyn|oral|tongue|"
            r"mouth|salivary).{0,30}(cancer|carcinoma|neoplasm|malignant|"
            r"2ww|fast.?track)|fast.?track.{0,30}(head.and.neck|head.neck)|"
            r"XaMkD",
            re.IGNORECASE,
        ),
    ),
    (
        "skin",
        re.compile(
            r"(skin|melanoma|basal.cell|squamous.cell|BCC|SCC).{0,30}"
            r"(cancer|carcinoma|neoplasm|malignant|2ww|fast.?track)|"
            r"fast.?track.{0,30}(skin|dermato)|"
            r"XaMeA|Xa98G",
            re.IGNORECASE,
        ),
    ),
    (
        "haematology",
        re.compile(
            r"(lymphoma|leukaemia|leukemia|myeloma|myelodysplastic|"
            r"haematolog|hematolog|CLL|CML|AML|ALL|SLL|NHL|Hodgkin).{0,30}"
            r"(cancer|neoplasm|malignant|disease|syndrome|diagnosis)",
            re.IGNORECASE,
        ),
    ),
    (
        "gynaecology",
        re.compile(
            r"(ovarian|uterine|cervical|endometrial|vulval|cervix|uterus|"
            r"womb|ovary).{0,30}(cancer|carcinoma|neoplasm|malignant|"
            r"2ww|fast.?track)|fast.?track.{0,30}(gynae|gynaecol|lower.genit)",
            re.IGNORECASE,
        ),
    ),
    (
        "urology",
        re.compile(
            r"(bladder|kidney|renal|testicular|penile|urinary).{0,30}"
            r"(cancer|carcinoma|neoplasm|malignant|2ww|fast.?track)|"
            r"fast.?track.{0,30}(urol|bladder|renal)",
            re.IGNORECASE,
        ),
    ),
]

# Non-site-specific 2WW (NSS) -- assign to "unknown" until further info
_NSS_PATTERN = re.compile(
    r"non.?site.?specific|NSS|Y3dd2",
    re.IGNORECASE,
)

# Screening / monitoring patterns -- classify score=0 episodes as negatives
_SCREENING_PATTERN = re.compile(
    r"FOBT Normal|FIT.*negative|faecal occult.*normal|BCSP.*normal|"
    r"Bowel Cancer Screening.*no further action|"
    r"Cervical smear.*negative|Cervical Screening.*normal|"
    r"Breast Screening.*normal|NHS Breast screening|"
    r"XaPkd|XaPVj",  # BCSP normal Read codes
    re.IGNORECASE,
)

_MONITORING_PATTERN = re.compile(
    r"Prostate.specific antigen|PSA.*\d+\.\d+\s*ng/ml|"
    r"Thyroid function test|Serum free T4|"
    r"cancer care review.{0,30}(review|check|follow|annual)|"
    r"surveillance|follow.up.{0,20}(cancer|oncol)|"
    r"annual cancer review|3.monthly|6.monthly",
    re.IGNORECASE,
)

# Closed / post-treatment indicators
_CLOSED_PATTERN = re.compile(
    # QOF cancer care review = patient is on the cancer register (post-treatment)
    r"Cancer v\d+|Cancer codes|Cancer care review \(XaIyc\)|XaIyc|"
    # Oncology discharging back to GP
    r"Oncology to .{3,40}Medical|discharged from oncology|"
    r"Discharged from (breast|cancer|oncology|colorectal|upper.GI|urology)|"
    r"treatment has (finished|completed|ended)|treatment (finished|complete|ended)|"
    r"active treatment (finished|completed|ended|complete)|"
    r"end of active treatment|no evidence of disease|NED\b|"
    # Maintenance hormonal therapy = acute treatment finished
    r"adjuvant letrozole|adjuvant tamoxifen|adjuvant herceptin|"
    r"Letrozole.{0,30}(5 year|adjuvant|following)|"
    r"Tamoxifen.{0,30}(5 year|adjuvant|following)|"
    r"oesophagectomy in |had oesophagectomy|had.{0,15}oesophagus removed|"
    r"post.op|post.surgery|post.treatment",
    re.IGNORECASE,
)

# Active treatment currently ongoing signals (in encounter body, not header)
_ACTIVE_TX_PATTERN = re.compile(
    r"(current|ongoing|continuing|receiving|started|having|on).{0,20}"
    r"(chemotherapy|chemo|radiotherapy|radio|immunotherapy|"
    r"Chemotherapy \(X71bL\)|X71bL)|"
    r"(cycle|round|session|dose).{0,10}(chemo|radio|immuno)|"
    r"PICC line|port.a.cath|hickman|central.line",
    re.IGNORECASE,
)

# How recent an encounter must be to count as "still active" (months from dataset end)
_ACTIVE_RECENCY_MONTHS = 6


# ---------------------------------------------------------------------------
# Milestone patterns
# ---------------------------------------------------------------------------

# NOTE: encounter text headers always begin with "Surgery: NAME" or
# "Telephone: NAME" so bare words like "surgery" and "excision" match
# every encounter.  Patterns below target specific clinical phrases or
# Read codes that only appear in the body of a cancer-pathway encounter.

_MILESTONE_PATTERNS: List[Tuple[str, re.Pattern]] = [
    (
        "treatment_started",
        re.compile(
            # Specific cancer treatment Read codes or explicit procedure names.
            # Deliberately exclude bare "surgery"/"excision" (they appear in
            # every encounter header as "Surgery: Dr Smith").
            r"Chemotherapy \(X71bL\)|chemotherapy for|"
            r"radiotherapy for|immunotherapy for|"
            r"starting.{0,20}(chemo|radio|immuno)|"
            r"first.{0,10}(cycle|session|round|dose) of.{0,20}(chemo|radio)|"
            r"mastectomy|oesophagectomy|gastrectomy|nephrectomy|"
            r"prostatectomy|orchidectomy|lumpectomy|hysterectomy|TURBT|"
            r"Wide local excision|sentinel lymph node.{0,20}biopsy|"
            r"neoadjuvant.chemo|adjuvant.chemo|"
            r"oesophagus removed|had.{0,20}oesophagectomy|"
            r"having chemotherapy|started chemotherapy|"
            r"\bchemo\b.{0,30}(cancer|CA\b|oesophag|breast|bowel|lung|prostate)|"
            r"X71bL",
            re.IGNORECASE,
        ),
    ),
    (
        "diagnosis_confirmed",
        re.compile(
            # GP record system marks new diagnoses with "(New Episode)" after
            # Major/Minor problem headers.  Also catch explicit diagnosis notes.
            r"(Major:|Minor:).{0,200}"
            r"(carcinoma|adenocarcinoma|malignant|neoplasm|"
            r"lymphoma|leukaemia|leukemia|myeloma|sarcoma|melanoma)"
            r".{0,60}\(New Episode\)|"
            r"(adenocarcinoma|carcinoma of|malignant neoplasm|malignant tumour|"
            r"cancer confirmed|diagnosed with cancer|confirmed cancer|"
            r"histology confirm|biopsy confirm|pathology confirm|"
            r"cancer care review|XaIyc|"
            r"Xa0DF|X78WM)",  # Adenocarcinoma oesophagus | Malignant breast tumour
            re.IGNORECASE,
        ),
    ),
    (
        "first_presentation",
        re.compile(
            # Specific "Seen in fast track ... clinic" Read codes from GP record.
            r"Seen in fast track|Seen in 2WW|2WW Clinic\?|"
            r"XaPyQ|XaPyj|XaPyg|XaPyd|XaPyi|XaPyk|XaPyl|XaPym|XaPyn",
            re.IGNORECASE,
        ),
    ),
    (
        "referral",
        re.compile(
            # 2WW / fast track referral Read codes and PRISM pathway markers.
            r"Fast track referral for suspected|"
            r"2ww.{0,10}referral|PRISM 2WW|"
            r"Patient awaiting OPD appt.{0,10}2ww|"
            r"XaMkD|Xaalp|XaMeE|XaMeA|XaMeJ|XaMeB|XaMeC|XaMeD|"
            r"XaMeF|XaMeG|XaMeH|XaMeI|XaMeK|XaMeL|XaMeN|Y3dd2",
            re.IGNORECASE,
        ),
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _classify_episode_status(
    completeness: int,
    milestone_map: Dict[str, str],
    encounters: List[Dict[str, Any]],
) -> str:
    """Classify an episode as active_pathway, screening, monitoring, or incidental.

    active_pathway  -- referral or diagnosis or treatment detected
    screening       -- normal screening result; no pathway evidence
    monitoring      -- ongoing blood/surveillance monitoring; no new pathway
    incidental      -- cancer type mentioned in passing; no pathway evidence
    """
    if completeness >= 1:
        return "active_pathway"
    all_text = " ".join(e.get("text_snippet", "") for e in encounters)
    if _SCREENING_PATTERN.search(all_text):
        return "screening"
    if _MONITORING_PATTERN.search(all_text):
        return "monitoring"
    return "incidental"


def _expected_episode_status(
    milestone_map: Dict[str, str],
    last_date: Optional[str],
    encounters: List[Dict[str, Any]],
    dataset_end: date,
) -> str:
    """Return the expected EpisodeOfCare status for the pipeline to produce.

    active       -- acute treatment is ongoing right now
    closed       -- treatment is complete; patient on follow-up / surveillance
    investigating -- referred / seen but no diagnosis confirmed yet
    incomplete   -- too little data to determine
    """
    all_text = " ".join(e.get("text_snippet", "") for e in encounters)
    has_dx = "diagnosis_confirmed" in milestone_map
    has_tx = "treatment_started" in milestone_map
    has_ref = "referral" in milestone_map or "first_presentation" in milestone_map

    last = _date_or_none(last_date)
    months_since_last = (dataset_end - last).days / 30 if last else 999

    # Explicit closed signals in text override recency
    if _CLOSED_PATTERN.search(all_text):
        return "closed"

    if has_tx:
        # Treatment started -- check if still actively treating
        if _ACTIVE_TX_PATTERN.search(all_text):
            return "active"
        if months_since_last <= _ACTIVE_RECENCY_MONTHS:
            return "active"
        return "closed"

    if has_dx:
        # Diagnosis without treatment in record -- may be recently diagnosed
        if months_since_last <= _ACTIVE_RECENCY_MONTHS:
            return "active"
        return "closed"

    if has_ref:
        # Referral only: if pathway was recent enough it may still be in-flight;
        # if the last GP activity was > 6 months ago the outcome (positive or
        # negative) has already been resolved, so treat as closed.
        if months_since_last <= _ACTIVE_RECENCY_MONTHS:
            return "investigating"
        return "closed"

    return "incomplete"


def _detect_cancer_type(text: str) -> Optional[str]:
    for cancer_type, pattern in _CANCER_TYPE_PATTERNS:
        if pattern.search(text):
            return cancer_type
    if _NSS_PATTERN.search(text):
        return "unknown"
    return None


def _detect_milestone(text: str) -> Optional[str]:
    # Evaluate in priority order: treatment > diagnosis > first_pres > referral
    for milestone, pattern in _MILESTONE_PATTERNS:
        if pattern.search(text):
            return milestone
    return None


def _is_admin_only(text: str) -> bool:
    """True if encounter is purely administrative (no clinical content)."""
    admin_patterns = [
        r"Record Keeping \(\d+ minutes\) Administration with No Patient",
        r"ETP2 FP10.*Not Yet Printed",
        r"Short message service text message sent",
        r"Scheduled Task Creation",
        r"Choose and book.*administration",
        r"^[^A-Za-z]*$",
    ]
    return (
        all(
            not re.search(p, text, re.IGNORECASE) or len(text) < 80
            for p in admin_patterns
        )
        is False
    )


def _date_or_none(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Episode grouping
# ---------------------------------------------------------------------------

_EPISODE_GAP_DAYS = 180  # encounters > 180 days apart -> new episode


def _group_into_episodes(
    cancer_encounters: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Group encounters sharing a cancer type into episodes by temporal proximity."""
    if not cancer_encounters:
        return []

    # Sort by date ascending
    sorted_enc = sorted(
        cancer_encounters,
        key=lambda e: _date_or_none(e["date"]) or date(1900, 1, 1),
    )

    episodes: List[Dict[str, Any]] = []
    current_episode: List[Dict[str, Any]] = [sorted_enc[0]]

    for enc in sorted_enc[1:]:
        prev_date = _date_or_none(current_episode[-1]["date"])
        this_date = _date_or_none(enc["date"])
        gap = (this_date - prev_date).days if prev_date and this_date else 0
        if gap > _EPISODE_GAP_DAYS:
            episodes.append(current_episode)
            current_episode = [enc]
        else:
            current_episode.append(enc)

    episodes.append(current_episode)
    return episodes


def _assign_milestones(
    encounter_list: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Assign milestone_type to each encounter in an episode.

    Each milestone is recorded at most once (the first time it is
    detected in date order).  No strict ordering is enforced here --
    if the GP record is incomplete the earlier milestones may be absent.
    The completeness_score in the episode summary captures this.
    """
    result = []
    used: Dict[str, bool] = {
        "referral": False,
        "first_presentation": False,
        "diagnosis_confirmed": False,
        "treatment_started": False,
    }

    for enc in sorted(
        encounter_list,
        key=lambda e: _date_or_none(e["date"]) or date(1900, 1, 1),
    ):
        milestone = _detect_milestone(enc["text"])
        if milestone and used.get(milestone):
            # Already assigned -- keep the encounter but don't re-tag it
            milestone = None
        elif milestone:
            used[milestone] = True

        result.append(
            {
                "encounter_id": enc["encounter_id"],
                "date": enc["date"],
                "milestone_type": milestone,
                "cancer_type": enc.get("cancer_type"),
                "text_snippet": enc["text"][:200],
                "has_new_episode_marker": "(New Episode)" in enc["text"],
                "has_ongoing_episode_marker": "(Ongoing Episode)" in enc["text"],
            }
        )

    return result


def _summarise_episode(
    episode_encounters: List[Dict[str, Any]],
    cancer_type: str,
    episode_idx: int,
    patient_id: str,
    dataset_end: date,
) -> Dict[str, Any]:
    """Build the episode summary dict."""
    dates = [
        _date_or_none(e["date"]) for e in episode_encounters if _date_or_none(e["date"])
    ]
    first_date = str(min(dates)) if dates else None
    last_date = str(max(dates)) if dates else None

    milestoned = _assign_milestones(episode_encounters)
    milestone_map: Dict[str, str] = {}
    for enc in milestoned:
        ms = enc["milestone_type"]
        if ms and ms not in milestone_map:
            milestone_map[ms] = enc["date"]

    # Score completeness (referral + diag + treatment = full pathway)
    completeness = sum(
        [
            "referral" in milestone_map,
            "first_presentation" in milestone_map
            or "diagnosis_confirmed" in milestone_map,
            "diagnosis_confirmed" in milestone_map,
            "treatment_started" in milestone_map,
        ]
    )

    pathway_status = _classify_episode_status(completeness, milestone_map, milestoned)
    if pathway_status == "active_pathway":
        expected_status = _expected_episode_status(
            milestone_map, last_date, milestoned, dataset_end
        )
    else:
        # Screening / monitoring / incidental: no EpisodeOfCare expected
        expected_status = "not_applicable"

    return {
        "episode_key": f"{patient_id}_{cancer_type}_{episode_idx}",
        "patient_id": patient_id,
        "cancer_type": cancer_type,
        "episode_index": episode_idx,
        "first_date": first_date,
        "last_date": last_date,
        "encounter_count": len(episode_encounters),
        "milestones": milestone_map,
        "completeness_score": completeness,
        "pathway_status": pathway_status,
        "expected_episode_status": expected_status,
        "encounters": milestoned,
    }


# ---------------------------------------------------------------------------
# Main extraction
# ---------------------------------------------------------------------------

BATCH_SIZE = 500


def _fetch_all_encounters(client: PatientGraphClient) -> List[Dict[str, Any]]:
    """Fetch all encounters with text, ordered by patient + date."""
    rows = client.run(
        "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
        "WHERE e.text IS NOT NULL AND trim(e.text) <> '' "
        "RETURN p.id AS patient_id, e.id AS encounter_id, "
        "       e.date AS date, e.text AS text "
        "ORDER BY p.id, e.date"
    )
    return [dict(r) for r in rows]


def _extract_ground_truth(
    all_encounters: List[Dict[str, Any]],
    target_patient: Optional[str] = None,
) -> Dict[str, Any]:
    # Group by patient
    by_patient: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for enc in all_encounters:
        if target_patient and enc["patient_id"] != target_patient:
            continue
        by_patient[enc["patient_id"]].append(enc)

    # Determine dataset end from the latest encounter date seen
    all_enc_dates = [_date_or_none(e["date"]) for e in all_encounters if e.get("date")]
    dataset_end = max((d for d in all_enc_dates if d), default=date.today())

    patients_out: List[Dict[str, Any]] = []
    stats = {
        "total_patients": 0,
        "patients_with_cancer_episodes": 0,
        "total_episodes": 0,
        "active_pathways": 0,
        "complete_pathways": 0,
        "pathway_status_counts": defaultdict(int),
        "episode_status_counts": defaultdict(int),
        "cancer_type_counts": defaultdict(int),
        "dataset_end": str(dataset_end),
    }

    for patient_id, encounters in sorted(by_patient.items()):
        stats["total_patients"] += 1

        # Tag each encounter with detected cancer types
        cancer_enc_by_type: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for enc in encounters:
            cancer_type = _detect_cancer_type(enc["text"])
            if cancer_type:
                enc = {**enc, "cancer_type": cancer_type}
                cancer_enc_by_type[cancer_type].append(enc)

        if not cancer_enc_by_type:
            patients_out.append(
                {
                    "patient_id": patient_id,
                    "episodes": [],
                    "total_encounters": len(encounters),
                }
            )
            continue

        stats["patients_with_cancer_episodes"] += 1
        episodes_out: List[Dict[str, Any]] = []

        for cancer_type, cancer_encs in sorted(cancer_enc_by_type.items()):
            grouped = _group_into_episodes(cancer_encs)
            for idx, episode_encounters in enumerate(grouped):
                ep = _summarise_episode(
                    episode_encounters, cancer_type, idx, patient_id, dataset_end
                )
                episodes_out.append(ep)
                stats["total_episodes"] += 1
                stats["cancer_type_counts"][cancer_type] += 1
                stats["pathway_status_counts"][ep["pathway_status"]] += 1
                stats["episode_status_counts"][ep["expected_episode_status"]] += 1
                if ep["pathway_status"] == "active_pathway":
                    stats["active_pathways"] += 1
                if ep["completeness_score"] >= 3:
                    stats["complete_pathways"] += 1

        patients_out.append(
            {
                "patient_id": patient_id,
                "episodes": episodes_out,
                "total_encounters": len(encounters),
                "cancer_types_found": sorted(cancer_enc_by_type.keys()),
            }
        )

    # Convert defaultdicts for JSON serialisation
    stats["cancer_type_counts"] = dict(stats["cancer_type_counts"])
    stats["pathway_status_counts"] = dict(stats["pathway_status_counts"])
    stats["episode_status_counts"] = dict(stats["episode_status_counts"])

    return {
        "version": "1.0",
        "generated_at": str(date.today()),
        "stats": stats,
        "patients": patients_out,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=str(ROOT / "data" / "ground_truth" / "episode_ground_truth.json"),
        help="Output JSON path",
    )
    parser.add_argument(
        "--patient",
        default=None,
        help="Restrict to a single patient ID (for testing)",
    )
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print("Connecting to patient graph...")
    client = PatientGraphClient()
    try:
        print("Fetching all encounters (this may take ~20s)...")
        all_encounters = _fetch_all_encounters(client)
        print(f"Loaded {len(all_encounters):,} encounters.")
    finally:
        client.close()

    print("Extracting ground truth...")
    ground_truth = _extract_ground_truth(all_encounters, target_patient=args.patient)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(ground_truth, f, indent=2, ensure_ascii=False)

    stats = ground_truth["stats"]
    print(f"\nGround truth written to: {out_path}")
    print(f"  Patients processed     : {stats['total_patients']}")
    print(f"  With cancer episodes   : {stats['patients_with_cancer_episodes']}")
    print(f"  Total episodes         : {stats['total_episodes']}")
    print(f"  Active pathways        : {stats['active_pathways']}")
    print(f"  Complete pathways (>=3): {stats['complete_pathways']}")
    print(f"  Dataset end            : {stats['dataset_end']}")
    print("  Expected episode status (pipeline target):")
    for status, n in sorted(
        stats["episode_status_counts"].items(), key=lambda x: -x[1]
    ):
        print(f"    {status:<20} {n}")
    print("  Pathway type           :")
    for status, n in sorted(
        stats["pathway_status_counts"].items(), key=lambda x: -x[1]
    ):
        print(f"    {status:<20} {n}")
    print("  Cancer type breakdown  :")
    for ct, n in sorted(stats["cancer_type_counts"].items(), key=lambda x: -x[1]):
        print(f"    {ct:<20} {n}")


if __name__ == "__main__":
    main()
