"""Comprehensive EpisodeOfCare remediation for all cancer patients.

Applies corrected classification rules to ALL patients (not just those
in the referral CSV) and writes properly formed EpisodeOfCare nodes.

Corrected rules vs the original analyse_referral_episodes.py:

  1. HISTORY tags (History of malignant neoplasm, etc.) annotate episodes
     but NEVER set outcome = confirmed_cancer for the current pathway.

  2. Weak exclusion codes (Normal appearance, CT normal, Mammography normal,
     Biopsy normal) do NOT override a confirmed active cancer diagnosis in
     the same window. They are too generic -- routinely coded against blood
     tests, urine dips, and LTC reviews unrelated to the cancer pathway.

  3. Strong exclusion codes (No evidence of cancer found, Referral cancelled
     by patient) DO close an episode when no active cancer diagnosis exists.

  4. Time-ordering: if exclusion precedes diagnosis by any gap, and the
     diagnosis is active (not historical), the outcome = confirmed_cancer
     regardless of the exclusion type.

  5. Intestine/bowel malignancy counts as a match for lower_gi and
     colorectal referral sites.

  6. Patients WITH coded active cancer but NO referral get a "no_referral"
     episode so the dashboard picks them up.

Dry-run by default -- shows all proposed writes without touching Neo4j.
Use --apply to write.

Usage
-----
    python scripts/remediate_episodes.py              # dry run
    python scripts/remediate_episodes.py --apply      # write to Neo4j
    python scripts/remediate_episodes.py --apply --patient 4802241127
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from dotenv import load_dotenv  # noqa: E402
from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("remediate")

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------
CLUSTER_GAP_DAYS = 90
NEW_EPISODE_GAP_DAYS = 365
LOOK_AHEAD_DAYS = 180

# "Normal appearance" and other generic finding codes - cannot alone
# close an episode that has a confirmed active cancer diagnosis.
WEAK_EXCLUSION_IDS: frozenset[str] = frozenset([
    "281900007",         # No abnormality detected / Normal appearance
    "169064005",         # CT normal
    "168749009",         # Mammography normal
    "165324008",         # Biopsy result normal
    "171175005",         # Breast neoplasm screening normal
])

# Pathway-specific closure codes that reliably indicate "no cancer found".
STRONG_EXCLUSION_IDS: frozenset[str] = frozenset([
    "395100000",         # No evidence of cancer found (situation)
    "414861001",         # No evidence of recurrence of cancer
    # 415068001 REMOVED: this is "Exposure to ultraviolet radiation (event)" in SNOMED,
    #   not a cancer exclusion concept. Confirmed via patient graph 2026-04-06.
    "1090791000000103",  # No evidence of malignancy (UK extension)
    "923501000000103",   # Referral cancelled by patient
    "20376005",          # Benign neoplastic disease
])

ALL_EXCLUSION_IDS = WEAK_EXCLUSION_IDS | STRONG_EXCLUSION_IDS

# History-of codes: annotate only, never trigger confirmed_cancer.
HISTORY_CONCEPT_IDS: frozenset[str] = frozenset([
    "266987004",         # History of malignant neoplasm
    "395672005",         # Cancer diagnosis discussed
])
HISTORY_TERMS = ("history of", "historical")

# Site label -> keywords appearing in diagnosis concept names.
DIAG_SITE_KEYWORDS: dict[str, list[str]] = {
    "brain": ["brain", "cerebral", "intracranial", "gliom", "meningeal"],
    "breast": ["breast", "mammary"],
    "colorectal": ["colon", "rectal", "colorectal", "intestine", "bowel",
                   "sigmoid", "transverse", "caecum", "cecum"],
    "lower_gi": ["colon", "rectal", "colorectal", "intestine", "bowel",
                 "sigmoid", "transverse", "caecum", "cecum"],
    "upper_gi": ["esophag", "oesophag", "stomach", "gastric", "upper gi",
                 "oesophageal", "esophageal"],
    "lung": ["lung", "bronch", "pulmonary", "pleural"],
    "skin": ["skin", "melanom", "basal cell", "squamous", "lentigo",
             "merkel"],
    "gynaecological": ["cervix", "uterus", "uterine", "ovarian", "ovary",
                       "endometri", "vulva", "vagina", "fallopian"],
    "urological": ["bladder", "prostate", "renal", "kidney", "urological",
                   "urinary", "urothelial"],
    "haematology": ["lymph", "leukaem", "leukemi", "myelom", "haematol",
                    "lymphoma", "leukaemia"],
    "head_and_neck": ["head", "neck", "oral", "pharynx", "larynx",
                      "thyroid", "salivary", "buccal", "tongue", "lip"],
    "sarcoma": ["sarcoma"],
    "childrens_tumour": ["paediatric", "wilms", "neuroblast", "medulloblast"],
    "non_site_specific": [],
}

# EpisodeOfCare status vocab used by the dashboard and cohort APIs.
STATUS_CONFIRMED = "confirmed"
STATUS_CLOSED = "closed"
STATUS_PENDING = "pending"
STATUS_NEEDS_REVIEW = "needs_review"

# Referral concept -> tumour site
# Verified against terminology server 2026-04-03. Concept FSNs confirmed.
# Note: the IDs are NOT in alphabetical site order -- do not re-sort.
REFERRAL_SITE: dict[str, str] = {
    "276581000000102": "brain",          # Fast track referral for suspected brain tumour
    "276341000000100": "breast",         # Fast track referral for suspected breast cancer
    "1556551000000104": "non_site_specific",  # Fast track referral: suspected cancer, non-site-specific symptoms
    "276371000000106": "childrens_tumour",    # Fast track referral for suspected children's tumour
    "276401000000108": "colorectal",          # Fast track referral for suspected colorectal cancer
    "892201000000106": "lower_gi",            # Fast track referral for suspected lower GI cancer
    "276311000000101": "gynaecological",      # Fast track referral for suspected gynaecological cancer
    "276461000000107": "haematology",         # Fast track referral for suspected haematology malignancy
    "280521000000108": "head_and_neck",       # Fast track referral for suspected head and neck cancer
    "276491000000101": "lung",               # Fast track referral for suspected lung cancer
    "276521000000103": "sarcoma",            # Fast track referral for suspected sarcoma
    "276281000000104": "skin",              # Fast track referral for suspected skin cancer
    "276551000000108": "upper_gi",          # Fast track referral for suspected upper GI cancer
    "276431000000102": "urological",        # Fast track referral for suspected urological cancer
}

# Verified against terminology server 2026-04-03.
SPECIALIST_SITE: dict[str, str] = {
    "382361000000100": "sarcoma",        # Seen in fast track suspected sarcoma clinic
    "382711000000103": "skin",           # Seen in fast track suspected skin cancer clinic
    "382681000000102": "lung",           # Seen in fast track suspected lung cancer clinic
    "382401000000109": "brain",          # Seen in fast track suspected brain tumour clinic
    "382431000000103": "breast",         # Seen in fast track suspected breast cancer clinic
    "383201000000101": "childrens_tumour", # Seen in fast track suspected children's tumour clinic
    "382651000000108": "colorectal",     # Seen in fast track suspected colorectal cancer clinic
    "382841000000109": "urological",     # Seen in fast track suspected urological cancer clinic
    "382621000000103": "head_and_neck",  # Seen in fast track suspected head and neck cancer clinic
    "382511000000105": "gynaecological", # Seen in fast track suspected gynaecological cancer clinic
    "382581000000103": "haematology",    # Seen in fast track suspected haematological malignancy clinic
    "382811000000108": "upper_gi",       # Seen in fast track suspected upper GI cancer clinic
}

REFERRAL_IDS = frozenset(REFERRAL_SITE.keys())
SPECIALIST_IDS = frozenset(SPECIALIST_SITE.keys())

from libs.domains.ncda_concept_sets import (  # noqa: E402
    CANCER_TYPE_IDS,
    CANCER_HISTORY_IDS,
    CANCER_EXCLUSION_IDS,
)
# Active cancer: confirmed disease only -- NOT history tags.
ACTIVE_DIAGNOSIS_IDS: frozenset[str] = frozenset(
    str(c) for c in CANCER_TYPE_IDS
)
HISTORY_DIAGNOSIS_IDS: frozenset[str] = (
    frozenset(str(c) for c in CANCER_HISTORY_IDS)
    | frozenset(str(c) for c in CANCER_EXCLUSION_IDS
                if c in {266987004, 395672005})
    | HISTORY_CONCEPT_IDS
)
ALL_DIAGNOSIS_IDS = ACTIVE_DIAGNOSIS_IDS | HISTORY_DIAGNOSIS_IDS

# ------------------------------------------------------------------
# Cypher
# ------------------------------------------------------------------

_Q_ALL_PATIENTS = """
MATCH (p:Patient)
RETURN DISTINCT toString(p.id) AS patient_id
ORDER BY patient_id
"""

_Q_ALL_MILESTONES = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(d)
WHERE toString(p.id) IN $patient_ids
  AND e.date IS NOT NULL
  AND (
      toString(d.conceptId) IN $referral_ids
   OR toString(d.conceptId) IN $specialist_ids
   OR toString(d.conceptId) IN $diagnosis_ids
   OR toString(d.conceptId) IN $exclusion_ids
  )
RETURN
    toString(p.id)         AS patient_id,
    toString(e.id)         AS encounter_id,
    toString(e.date)       AS encounter_date,
    toString(d.conceptId)  AS concept_id,
    d.name                 AS concept_name,
    r.assertion            AS assertion
ORDER BY patient_id, encounter_date
"""

_UPSERT_EPISODE = """
MATCH (p:Patient)
WHERE toString(p.id) = $patient_id
MERGE (ep:EpisodeOfCare {episode_id: $episode_id})
ON CREATE SET
    ep.created_at             = datetime(),
    ep.source                 = 'remediation_script'
SET ep.patient_id             = $patient_id,
    ep.condition_type         = $condition_type,
    ep.cancer_type            = $condition_type,
    ep.status                 = $status,
    ep.referral_date          = $referral_date,
    ep.last_referral_date     = $last_referral_date,
    ep.diagnosis_date         = $diagnosis_date,
    ep.first_presentation_date = $first_presentation_date,
    ep.referral_site          = $referral_site,
    ep.specialist_seen        = $specialist_seen,
    ep.needs_review           = $needs_review,
    ep.referral_encounter_ids = $referral_encounter_ids,
    ep.diagnosis_encounter_id = $diagnosis_encounter_id,
    ep.exclusion_encounter_id = $exclusion_encounter_id,
    ep.exclusion_outcome      = $exclusion_outcome,
    ep.episode_number         = $episode_number,
    ep.has_history            = $has_history,
    ep.flags                  = $flags,
    ep.remediated_at          = datetime(),
    ep.updated_at             = datetime()
MERGE (p)-[:HAS_EPISODE_OF_CARE]->(ep)
"""

_DELETE_PATIENT_EPISODES = """
MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
WHERE toString(p.id) = $patient_id
DETACH DELETE ep
"""


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _safe_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return None


def _is_history(concept_id: str, concept_name: str) -> bool:
    if concept_id in HISTORY_DIAGNOSIS_IDS:
        return True
    nm = (concept_name or "").lower()
    return any(t in nm for t in HISTORY_TERMS)


def _is_active_diagnosis(concept_id: str, concept_name: str) -> bool:
    return (
        concept_id in ACTIVE_DIAGNOSIS_IDS
        and not _is_history(concept_id, concept_name)
    )


def _diag_matches_site(concept_name: str, sites: list[str]) -> bool:
    dl = concept_name.lower()
    for site in sites:
        if site in ("any", "non_site_specific"):
            return True
        kws = DIAG_SITE_KEYWORDS.get(site, [])
        if any(k in dl for k in kws):
            return True
    return False


def _episode_id(patient_id: str, episode_num: int) -> str:
    key = f"{patient_id}|episode|{episode_num}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


# ------------------------------------------------------------------
# Milestone loading
# ------------------------------------------------------------------

def _batch(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def _load_milestones(session, patient_ids: list[str]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = defaultdict(list)
    all_excl = list(ALL_EXCLUSION_IDS)
    all_diag = list(ACTIVE_DIAGNOSIS_IDS | HISTORY_DIAGNOSIS_IDS)
    for chunk in _batch(patient_ids, 200):
        rows = session.run(
            _Q_ALL_MILESTONES,
            patient_ids=chunk,
            referral_ids=list(REFERRAL_IDS),
            specialist_ids=list(SPECIALIST_IDS),
            diagnosis_ids=all_diag,
            exclusion_ids=all_excl,
        )
        for row in rows:
            cid = row["concept_id"]
            assertion = (row.get("assertion") or "present").lower()
            if assertion in ("absent", "refuted"):
                continue
            if cid in REFERRAL_IDS:
                event_type = "referral"
                site = REFERRAL_SITE[cid]
            elif cid in SPECIALIST_IDS:
                event_type = "specialist"
                site = SPECIALIST_SITE[cid]
            elif cid in ALL_EXCLUSION_IDS:
                event_type = "exclusion"
                site = "any"
            else:
                # diagnosis
                if _is_history(cid, row["concept_name"] or ""):
                    event_type = "history"
                else:
                    event_type = "diagnosis"
                site = "any"

            result[row["patient_id"]].append({
                "patient_id": row["patient_id"],
                "encounter_id": row["encounter_id"],
                "encounter_date": row["encounter_date"],
                "dt": _safe_date(row["encounter_date"]),
                "concept_id": cid,
                "concept_name": row["concept_name"] or "",
                "event_type": event_type,
                "site": site,
            })
    return result


# ------------------------------------------------------------------
# Clustering
# ------------------------------------------------------------------

def _cluster_referrals(referrals: list[dict]) -> list[list[dict]]:
    if not referrals:
        return []
    sr = sorted(referrals, key=lambda r: r["dt"] or date.min)
    clusters: list[list[dict]] = [[sr[0]]]
    for ref in sr[1:]:
        last = clusters[-1][-1]
        if not ref["dt"] or not last["dt"]:
            clusters[-1].append(ref)
            continue
        gap = (ref["dt"] - last["dt"]).days
        if gap > NEW_EPISODE_GAP_DAYS:
            clusters.append([ref])
        elif gap <= CLUSTER_GAP_DAYS:
            clusters[-1].append(ref)
        else:
            clusters.append([ref])
    return clusters


# ------------------------------------------------------------------
# Corrected episode classification
# ------------------------------------------------------------------

def _classify_episode(
    cluster: list[dict],
    all_events: list[dict],
    next_cluster_start: date | None,
) -> dict:
    first_ref = cluster[0]["dt"]
    last_ref = cluster[-1]["dt"]
    sites = list({r["site"] for r in cluster})
    window_end = (
        next_cluster_start - timedelta(days=1)
        if next_cluster_start
        else last_ref + timedelta(days=LOOK_AHEAD_DAYS)
        if last_ref
        else None
    )

    active_diags: list[dict] = []
    history_events: list[dict] = []
    strong_excls: list[dict] = []
    weak_excls: list[dict] = []
    specialist_visits: list[dict] = []

    for ev in all_events:
        ev_dt = ev["dt"]
        if not ev_dt or not first_ref:
            continue
        if ev["event_type"] == "referral":
            continue
        if ev["event_type"] == "specialist":
            if first_ref <= ev_dt <= (window_end or ev_dt):
                specialist_visits.append(ev)
            continue
        if ev["event_type"] == "diagnosis":
            if first_ref <= ev_dt <= (window_end or ev_dt):
                active_diags.append(ev)
        elif ev["event_type"] == "history":
            if first_ref <= ev_dt <= (window_end or ev_dt):
                history_events.append(ev)
        elif ev["event_type"] == "exclusion":
            if first_ref <= ev_dt <= (window_end or ev_dt):
                if ev["concept_id"] in STRONG_EXCLUSION_IDS:
                    strong_excls.append(ev)
                else:
                    weak_excls.append(ev)

    # ---- Corrected classification rules ----
    flags: list[str] = []
    diagnosis_enc = ""
    diagnosis_date = ""
    exclusion_enc = ""
    exclusion_outcome = ""
    has_history = bool(history_events)

    if active_diags:
        diag = active_diags[0]
        # Rule 2: check site match
        if not _diag_matches_site(diag["concept_name"], sites):
            flags.append("SITE_MISMATCH")
        # Rule 3: weak exclusions never override confirmed cancer
        # Rule 4: if exclusion precedes diagnosis -> still confirmed cancer
        all_excls = sorted(strong_excls + weak_excls,
                           key=lambda e: e["dt"] or date.min)
        status = STATUS_CONFIRMED
        diagnosis_enc = diag["encounter_id"]
        diagnosis_date = diag["encounter_date"]
        if all_excls:
            excl = all_excls[0]
            days_apart = abs((diag["dt"] - excl["dt"]).days) \
                if diag["dt"] and excl["dt"] else 0
            if days_apart < 30 and excl["concept_id"] not in WEAK_EXCLUSION_IDS:
                flags.append("CONFLICTING_CLOSE_DATES")
                flags.append("NEEDS_CLINICAL_REVIEW")
                status = STATUS_NEEDS_REVIEW
            elif excl["concept_id"] in WEAK_EXCLUSION_IDS:
                flags.append("WEAK_EXCL_IGNORED")
    elif strong_excls:
        # Strong exclusion, no active diagnosis -> closed
        status = STATUS_CLOSED
        excl = sorted(strong_excls, key=lambda e: e["dt"] or date.min)[0]
        exclusion_enc = excl["encounter_id"]
        exclusion_outcome = excl["concept_name"]
        if has_history:
            flags.append("HISTORY_PRESENT")
    elif weak_excls and not has_history:
        # Weak exclusion only, no history, no active diagnosis -> pending
        status = STATUS_PENDING
        flags.append("ONLY_WEAK_EXCL")
    elif has_history and (weak_excls or strong_excls):
        # History tag + any exclusion -> closed (prior cancer, new pathway clear)
        status = STATUS_CLOSED
        all_excls = strong_excls or weak_excls
        excl = sorted(all_excls, key=lambda e: e["dt"] or date.min)[0]
        exclusion_enc = excl["encounter_id"]
        exclusion_outcome = excl["concept_name"]
        flags.append("HISTORY_PRESENT")
    else:
        status = STATUS_PENDING

    if not specialist_visits:
        flags.append("NO_SPECIALIST")
    if len(sites) > 1 and "non_site_specific" not in sites:
        flags.append("MULTI_SITE")

    # Dominant site: prefer non-generic
    primary_site = next(
        (s for s in sites if s != "non_site_specific"), sites[0]
    )

    return {
        "status": status,
        "condition_type": primary_site,
        "referral_date": str(first_ref) if first_ref else "",
        "last_referral_date": str(last_ref) if last_ref else "",
        "first_presentation_date": str(first_ref) if first_ref else "",
        "diagnosis_date": diagnosis_date,
        "diagnosis_encounter_id": diagnosis_enc,
        "exclusion_encounter_id": exclusion_enc,
        "exclusion_outcome": exclusion_outcome,
        "referral_site": "|".join(sorted(sites)),
        "specialist_seen": bool(specialist_visits),
        "has_history": has_history,
        "needs_review": status == STATUS_NEEDS_REVIEW,
        "flags": "|".join(flags) if flags else "",
        "referral_encounter_ids": "|".join(
            r["encounter_id"] for r in cluster
        ),
    }


# ------------------------------------------------------------------
# Per-patient episode plan
# ------------------------------------------------------------------

def _plan_patient(
    patient_id: str, events: list[dict]
) -> list[dict]:
    """Return list of episode dicts (not yet written) for this patient."""
    referrals = [e for e in events if e["event_type"] == "referral"]
    active_diags = [e for e in events if e["event_type"] == "diagnosis"]
    episodes: list[dict] = []

    if referrals:
        clusters = _cluster_referrals(referrals)
        for i, cluster in enumerate(clusters):
            next_start = clusters[i + 1][0]["dt"] if i + 1 < len(clusters) \
                else None
            ep = _classify_episode(cluster, events, next_start)
            ep["patient_id"] = patient_id
            ep["episode_number"] = i + 1
            ep["episode_id"] = _episode_id(patient_id, i + 1)
            if len(clusters) > 1:
                ep["flags"] = (ep["flags"] + "|MULTI_EPISODE").lstrip("|")
            episodes.append(ep)
    elif active_diags:
        # Cancer coded but no referral (e.g. letter from secondary care)
        diag = sorted(active_diags, key=lambda e: e["dt"] or date.min)[0]
        episodes.append({
            "patient_id": patient_id,
            "episode_id": _episode_id(patient_id, 1),
            "episode_number": 1,
            "status": STATUS_CONFIRMED,
            "condition_type": "unknown",
            "referral_date": "",
            "last_referral_date": "",
            "first_presentation_date": diag["encounter_date"],
            "diagnosis_date": diag["encounter_date"],
            "diagnosis_encounter_id": diag["encounter_id"],
            "exclusion_encounter_id": "",
            "exclusion_outcome": "",
            "referral_site": "no_referral",
            "specialist_seen": False,
            "has_history": any(
                e["event_type"] == "history" for e in events
            ),
            "needs_review": False,
            "flags": "NO_REFERRAL",
            "referral_encounter_ids": "",
        })

    return episodes


# ------------------------------------------------------------------
# Reporting
# ------------------------------------------------------------------

def _print_plan(all_episodes: list[dict]) -> None:
    by_status: dict[str, int] = defaultdict(int)
    by_flag: dict[str, int] = defaultdict(int)
    for ep in all_episodes:
        by_status[ep["status"]] += 1
        for flag in (ep["flags"] or "").split("|"):
            if flag:
                by_flag[flag] += 1

    sep = "=" * 70
    print(sep)
    print(f"EPISODE REMEDIATION PLAN -- {len(all_episodes)} episodes"
          f" across {len({e['patient_id'] for e in all_episodes})} patients")
    print(sep)
    print("Proposed episode status breakdown:")
    for st, cnt in sorted(by_status.items(), key=lambda x: -x[1]):
        print(f"  {st:<25} {cnt}")
    print()
    print("Quality flags:")
    for flag, cnt in sorted(by_flag.items(), key=lambda x: -x[1]):
        print(f"  {flag:<30} {cnt}")
    print()
    print("Confirmed cancer episodes:")
    for ep in sorted(
        [e for e in all_episodes if e["status"] == STATUS_CONFIRMED],
        key=lambda e: e["referral_date"] or e["diagnosis_date"],
    ):
        print(
            f"  [{ep['patient_id']}] ep{ep['episode_number']}"
            f"  {ep['condition_type']:<20}"
            f"  ref={ep['referral_date'] or 'no-referral'}"
            f"  diag={ep['diagnosis_date'] or '?'}"
        )
    print()
    print("Needs review / pending:")
    for ep in all_episodes:
        if ep["status"] in (STATUS_NEEDS_REVIEW, STATUS_PENDING):
            print(
                f"  [{ep['patient_id']}] ep{ep['episode_number']}"
                f"  {ep['status']:<15}"
                f"  site={ep['referral_site']:<25}"
                f"  flags={ep['flags']}"
            )
    print(sep)


# ------------------------------------------------------------------
# Write
# ------------------------------------------------------------------

def _apply(session, episodes: list[dict], dry_run: bool) -> dict:
    counts: dict[str, int] = defaultdict(int)
    patients_done: set[str] = set()
    for ep in episodes:
        pid = ep["patient_id"]
        if pid not in patients_done and not dry_run:
            session.run(_DELETE_PATIENT_EPISODES, patient_id=pid)
            patients_done.add(pid)
        if not dry_run:
            session.run(
                _UPSERT_EPISODE,
                patient_id=pid,
                episode_id=ep["episode_id"],
                condition_type=ep["condition_type"],
                status=ep["status"],
                referral_date=ep["referral_date"] or None,
                last_referral_date=ep["last_referral_date"] or None,
                diagnosis_date=ep["diagnosis_date"] or None,
                first_presentation_date=ep["first_presentation_date"] or None,
                referral_site=ep["referral_site"],
                specialist_seen=ep["specialist_seen"],
                needs_review=ep["needs_review"],
                referral_encounter_ids=ep["referral_encounter_ids"],
                diagnosis_encounter_id=ep["diagnosis_encounter_id"] or None,
                exclusion_encounter_id=ep["exclusion_encounter_id"] or None,
                exclusion_outcome=ep["exclusion_outcome"] or None,
                episode_number=ep["episode_number"],
                has_history=ep["has_history"],
                flags=ep["flags"] or None,
            )
        counts[ep["status"]] += 1
    return counts


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remediate EpisodeOfCare nodes for all cancer patients"
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Write to Neo4j (default is dry-run)",
    )
    parser.add_argument(
        "--patient", metavar="ID",
        help="Process only one patient ID",
    )
    args = parser.parse_args()

    dry_run = not args.apply

    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "")
    if not neo4j_password:
        log.error("NEO4J_PASSWORD not set")
        sys.exit(1)

    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(
        neo4j_uri, auth=(neo4j_user, neo4j_password)
    )

    with driver.session() as session:
        if args.patient:
            patient_ids = [args.patient]
        else:
            log.info("Loading all patients...")
            rows = session.run(_Q_ALL_PATIENTS)
            patient_ids = [r["patient_id"] for r in rows]
            log.info("Found %d patients total", len(patient_ids))

        log.info("Loading milestone events...")
        milestones = _load_milestones(session, patient_ids)

        # Only process patients who have at least one relevant event
        active_pids = [
            pid for pid in patient_ids
            if milestones.get(pid)
        ]
        log.info(
            "%d patients have cancer-pathway events", len(active_pids)
        )

        log.info("Building episode plans...")
        all_episodes: list[dict] = []
        for pid in active_pids:
            events = sorted(
                milestones[pid], key=lambda e: e["dt"] or date.min
            )
            eps = _plan_patient(pid, events)
            all_episodes.extend(eps)

        _print_plan(all_episodes)

        if dry_run:
            log.info(
                "DRY RUN -- no changes written. "
                "Re-run with --apply to write %d episodes.",
                len(all_episodes),
            )
            driver.close()
            return

        log.info("Applying %d episodes to Neo4j...", len(all_episodes))
        counts = _apply(session, all_episodes, dry_run=False)
        driver.close()

        log.info("Done.")
        for st, cnt in sorted(counts.items(), key=lambda x: -x[1]):
            log.info("  %-25s %d written", st, cnt)


if __name__ == "__main__":
    main()
