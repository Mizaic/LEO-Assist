"""
Source-of-truth check: for every patient in the cohort, what do we know?

For each patient:
  - Confirmed cancer (coded SNOMED cancer diagnosis, assertion=present)
  - Confirmed benign (no evidence of cancer coded)
  - Suspected only (possible/hypothetical assertion)
  - Nothing found in coding, but cancer keywords in encounter text
  - Genuinely unknown (no evidence either way)

Cross-referenced against episode status.
"""
import re
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()
from libs.neo4j_client.client import PatientGraphClient

# All episodes per patient
_Q_EPISODES = """
MATCH (ep:EpisodeOfCare)
RETURN ep.patient_id AS pid,
       ep.episode_id  AS eid,
       ep.status      AS status,
       ep.cancer_type AS site,
       ep.referral_date AS ref_date,
       ep.hitl_flag   AS hitl
ORDER BY ep.patient_id, ep.referral_date
"""

# All coded cancer concepts for a patient (present/historical assertion)
_Q_CANCER_CODED = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(c)
WHERE toString(p.id) = $pid
  AND c.semanticTag IN ['Disease', 'disorder', 'Clinical_finding', 'Situation',
                         'disorder', 'finding']
  AND (
    toLower(c.name) CONTAINS 'malignant' OR toLower(c.name) CONTAINS 'cancer'
    OR toLower(c.name) CONTAINS 'carcinoma' OR toLower(c.name) CONTAINS 'neoplasm'
    OR toLower(c.name) CONTAINS 'lymphoma' OR toLower(c.name) CONTAINS 'leukaemia'
    OR toLower(c.name) CONTAINS 'leukemia' OR toLower(c.name) CONTAINS 'melanoma'
    OR toLower(c.name) CONTAINS 'sarcoma' OR toLower(c.name) CONTAINS 'myeloma'
    OR toLower(c.name) CONTAINS 'adenocarcinoma' OR toLower(c.name) CONTAINS 'glioblastoma'
  )
RETURN e.date AS date,
       c.name AS concept,
       c.conceptId AS cid,
       coalesce(r.assertion, 'present') AS assertion
ORDER BY e.date
"""

# Benign closure coded
_Q_BENIGN_CODED = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(c)
WHERE toString(p.id) = $pid
  AND (toLower(c.name) CONTAINS 'no evidence of cancer'
    OR toLower(c.name) CONTAINS 'benign' OR toLower(c.name) CONTAINS 'normal biopsy'
    OR toLower(c.name) CONTAINS 'not malignant' OR toLower(c.name) CONTAINS 'no cancer')
RETURN e.date AS date, c.name AS concept,
       coalesce(r.assertion, 'present') AS assertion
ORDER BY e.date
LIMIT 3
"""

# Cancer keywords in encounter TEXT (uncoded)
_RE_CONFIRMED = re.compile(
    r"\b(?:confirmed|diagnosed|diagnosis of|biopsy (?:showed|confirmed|proven)|"
    r"histolog|proven|cancer confirmed|positive for malignancy|malignancy confirmed)\b",
    re.IGNORECASE
)
_RE_CANCER_TERM = re.compile(
    r"\b(?:cancer|carcinoma|malignant|malignancy|melanoma|lymphoma|leukaemia|"
    r"leukemia|myeloma|sarcoma|adenocarcinoma|neoplasm)\b",
    re.IGNORECASE
)

_Q_TEXT_CANCER = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $pid
  AND e.text IS NOT NULL
  AND coalesce(e.classification_content_type, '') <> 'admin_only'
RETURN e.date AS date, e.text AS text,
       e.coding_status AS coding_status
ORDER BY e.date
"""

_Q_ALL_PIDS = """
MATCH (ep:EpisodeOfCare)
RETURN DISTINCT ep.patient_id AS pid
ORDER BY ep.patient_id
"""

ASSERTION_CONFIRMED = {"present", "historical"}
ASSERTION_SUSPECTED = {"possible", "hypothetical"}


def classify_patient(pid: str, pg) -> dict:
    # Coded cancer
    with pg.session() as s:
        cancer_rows = s.run(_Q_CANCER_CODED, pid=pid).data()
    confirmed_coded = [
        r for r in cancer_rows if r["assertion"] in ASSERTION_CONFIRMED
    ]
    suspected_coded = [
        r for r in cancer_rows if r["assertion"] in ASSERTION_SUSPECTED
    ]

    # Coded benign
    with pg.session() as s:
        benign_rows = s.run(_Q_BENIGN_CODED, pid=pid).data()

    # Text evidence
    with pg.session() as s:
        text_rows = s.run(_Q_TEXT_CANCER, pid=pid).data()
    confirmed_text = []
    suspected_text = []
    for r in text_rows:
        text = r.get("text") or ""
        if _RE_CANCER_TERM.search(text):
            if _RE_CONFIRMED.search(text):
                confirmed_text.append(r)
            else:
                suspected_text.append(r)

    if confirmed_coded:
        status = "CONFIRMED_CODED"
    elif confirmed_text:
        status = "CONFIRMED_TEXT_ONLY"
    elif suspected_coded:
        status = "SUSPECTED_CODED"
    elif suspected_text:
        status = "SUSPECTED_TEXT_ONLY"
    elif benign_rows:
        status = "BENIGN_DISCHARGE"
    else:
        status = "UNKNOWN"

    return {
        "pid": pid,
        "status": status,
        "confirmed_coded": confirmed_coded[:3],
        "suspected_coded": suspected_coded[:2],
        "confirmed_text": confirmed_text[:2],
        "benign": benign_rows[:2],
    }


def main():
    pg = PatientGraphClient()
    try:
        with pg.session() as s:
            pid_rows = s.run(_Q_ALL_PIDS).data()
        pids = [r["pid"] for r in pid_rows]

        with pg.session() as s:
            ep_rows = s.run(_Q_EPISODES).data()

        # Episode status per patient
        ep_by_pid: dict[str, list] = defaultdict(list)
        for ep in ep_rows:
            ep_by_pid[str(ep["pid"])].append(ep)

        status_groups: dict[str, list] = defaultdict(list)
        results = []
        for pid in pids:
            r = classify_patient(str(pid), pg)
            results.append(r)
            status_groups[r["status"]].append(r)

        print("=" * 72)
        print("CANCER DIAGNOSIS TRUTH TABLE  --  93 patients")
        print("=" * 72)

        order = [
            "CONFIRMED_CODED",
            "CONFIRMED_TEXT_ONLY",
            "SUSPECTED_CODED",
            "SUSPECTED_TEXT_ONLY",
            "BENIGN_DISCHARGE",
            "UNKNOWN",
        ]
        labels = {
            "CONFIRMED_CODED":      "Confirmed cancer -- coded SNOMED (present/historical)",
            "CONFIRMED_TEXT_ONLY":  "Confirmed cancer -- encounter text only (uncoded)",
            "SUSPECTED_CODED":      "Suspected only   -- coded as possible/hypothetical",
            "SUSPECTED_TEXT_ONLY":  "Suspected only   -- mentioned in text, not confirmed",
            "BENIGN_DISCHARGE":     "Benign discharge -- no cancer found (coded)",
            "UNKNOWN":              "Unknown          -- no cancer evidence either way",
        }
        for grp in order:
            patients = status_groups.get(grp, [])
            print(f"\n{labels[grp]}  [{len(patients)} patients]")
            print("-" * 72)
            for r in patients:
                pid = r["pid"]
                eps = ep_by_pid.get(pid, [])
                ep_summary = ", ".join(
                    f"{ep['status']}({ep['site'] or '?'})"
                    for ep in eps[:4]
                )
                if len(eps) > 4:
                    ep_summary += f" +{len(eps)-4} more"

                if grp == "CONFIRMED_CODED" and r["confirmed_coded"]:
                    ex = r["confirmed_coded"][0]
                    detail = f"  {ex['date']} [{ex['assertion']}] {ex['concept'][:60]}"
                elif grp == "CONFIRMED_TEXT_ONLY" and r["confirmed_text"]:
                    ex = r["confirmed_text"][0]
                    detail = f"  {ex['date']} (uncoded text)"
                elif grp == "SUSPECTED_CODED" and r["suspected_coded"]:
                    ex = r["suspected_coded"][0]
                    detail = f"  {ex['date']} [possible] {ex['concept'][:60]}"
                elif grp == "BENIGN_DISCHARGE" and r["benign"]:
                    ex = r["benign"][0]
                    detail = f"  {ex['date']} {ex['concept'][:60]}"
                else:
                    detail = ""

                hitl_eps = [e for e in eps if e.get("hitl")]
                hitl_note = f"  !! {len(hitl_eps)} HITL" if hitl_eps else ""
                print(f"  {pid}  {ep_summary}{hitl_note}")
                if detail:
                    print(f"         {detail}")

        print()
        print("=" * 72)
        print("SUMMARY")
        print("=" * 72)
        total = len(results)
        for grp in order:
            n = len(status_groups.get(grp, []))
            pct = 100 * n / total if total else 0
            print(f"  {labels[grp]:<55}  {n:3d}  ({pct:.0f}%)")

        # Cross-tab: HITL episodes for patients with confirmed cancer
        print()
        print("Stale/HITL episodes for patients with CONFIRMED cancer:")
        confirmed_pids = {
            r["pid"]
            for grp in ("CONFIRMED_CODED", "CONFIRMED_TEXT_ONLY")
            for r in status_groups.get(grp, [])
        }
        hitl_for_confirmed = [
            ep for ep in ep_rows
            if str(ep["pid"]) in confirmed_pids and ep.get("hitl")
        ]
        for ep in hitl_for_confirmed:
            print(f"  {ep['pid']}  {ep['status']:25s}  {ep['site']}  ref={ep['ref_date']}")

    finally:
        pg.close()


if __name__ == "__main__":
    main()
