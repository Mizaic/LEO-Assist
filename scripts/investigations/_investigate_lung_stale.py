"""
Investigation: Why are all 3 lung cancer pathway episodes stale?
2 stale_post_specialist, 1 stale_no_diagnosis, 0 completed.
"""
import sys
from pathlib import Path
from datetime import datetime, date

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()
from libs.neo4j_client.client import PatientGraphClient

KEYWORDS = [
    "lung", "pulmonary", "bronch", "pleural", "pneumon",
    "ct scan", "ct chest", "ct thorax", "pet scan", "biopsy",
    "nodule", "copd", "fibrosis", "effusion", "cancer",
    "carcinoma", "adenocarcinoma", "squamous", "small cell",
    "mesothelioma", "malignant", "malignancy", "tumour", "tumor",
    "spirometry", "oncol", "respir", "specialist", "referral",
    "discharge", "benign", "negative", "no evidence", "normal",
    "clear", "reassured", "sputum", "haemoptysis", "hemoptysis",
]


def flag_text(text: str) -> list:
    if not text:
        return []
    tl = text.lower()
    return [kw for kw in KEYWORDS if kw in tl]


def days_since(ref_date_str) -> int | None:
    if not ref_date_str:
        return None
    try:
        ref = datetime.strptime(str(ref_date_str)[:10], "%Y-%m-%d").date()
        return (date.today() - ref).days
    except Exception:
        return None


def get_lung_episodes(client: PatientGraphClient) -> list:
    """Fetch all EpisodeOfCare nodes whose cancer_type contains 'lung'."""
    query = """
    MATCH (ep:EpisodeOfCare)
    WHERE toLower(ep.cancer_type) CONTAINS 'lung'
    RETURN
        ep.patient_id           AS patient_id,
        ep.episode_id           AS episode_id,
        ep.status               AS status,
        ep.cancer_type          AS cancer_type,
        ep.referral_date        AS referral_date,
        ep.specialist_visit_date AS specialist_visit_date,
        ep.inferred_outcome     AS inferred_outcome,
        ep.inferred_confidence  AS inferred_confidence,
        ep.inference_signals    AS inference_signals,
        ep.hitl_flag            AS hitl_flag,
        ep.hitl_reason          AS hitl_reason
    ORDER BY ep.status, ep.referral_date
    """
    with client.session() as s:
        return [dict(r) for r in s.run(query)]


def get_all_cancer_types(client: PatientGraphClient) -> list:
    """Sanity-check: show every distinct cancer_type value in the graph."""
    with client.session() as s:
        return [dict(r) for r in s.run(
            "MATCH (ep:EpisodeOfCare) "
            "RETURN DISTINCT ep.cancer_type AS ct, count(*) AS n "
            "ORDER BY n DESC"
        )]


def get_encounters(client: PatientGraphClient, pid: str, since: str = "2020-01-01") -> list:
    query = """
    MATCH (p:Patient {id: $pid})-[:HAS_ENCOUNTER]->(enc:Encounter)
    WHERE enc.date >= $since
    RETURN enc.id AS enc_id, enc.date AS enc_date,
           enc.flags AS flags, enc.text AS text
    ORDER BY enc.date
    """
    with client.session() as s:
        return [dict(r) for r in s.run(query, pid=pid, since=since)]


def get_other_episodes(client: PatientGraphClient, pid: str, exclude_eid: str) -> list:
    query = """
    MATCH (ep:EpisodeOfCare)
    WHERE ep.patient_id = $pid AND ep.episode_id <> $eid
    RETURN ep.episode_id AS episode_id, ep.cancer_type AS cancer_type,
           ep.status AS status, ep.referral_date AS referral_date,
           ep.inferred_outcome AS inferred_outcome
    """
    with client.session() as s:
        return [dict(r) for r in s.run(query, pid=pid, eid=exclude_eid)]


def get_relevant_encounters(client: PatientGraphClient, pid: str, since: str) -> list:
    query = """
    MATCH (p:Patient {id: $pid})-[:HAS_ENCOUNTER]->(enc:Encounter)
    WHERE enc.date >= $since
      AND (
        toLower(enc.text) CONTAINS 'ct' OR
        toLower(enc.text) CONTAINS 'pet' OR
        toLower(enc.text) CONTAINS 'biopsy' OR
        toLower(enc.text) CONTAINS 'bronchoscopy' OR
        toLower(enc.text) CONTAINS 'spirometry' OR
        toLower(enc.text) CONTAINS 'nodule' OR
        toLower(enc.text) CONTAINS 'cancer' OR
        toLower(enc.text) CONTAINS 'carcinoma' OR
        toLower(enc.text) CONTAINS 'malignant' OR
        toLower(enc.text) CONTAINS 'copd' OR
        toLower(enc.text) CONTAINS 'fibrosis' OR
        toLower(enc.text) CONTAINS 'effusion' OR
        toLower(enc.text) CONTAINS 'benign' OR
        toLower(enc.text) CONTAINS 'lung' OR
        toLower(enc.text) CONTAINS 'pulmonary' OR
        toLower(enc.text) CONTAINS 'discharge' OR
        toLower(enc.text) CONTAINS 'no evidence' OR
        toLower(enc.text) CONTAINS 'reassured' OR
        toLower(enc.text) CONTAINS 'haemoptysis' OR
        toLower(enc.text) CONTAINS 'hemoptysis'
      )
    RETURN enc.id AS enc_id, enc.date AS enc_date,
           enc.flags AS flags, enc.text AS text
    ORDER BY enc.date
    """
    with client.session() as s:
        return [dict(r) for r in s.run(query, pid=pid, since=since)]


def _safe(text: str, length: int) -> str:
    return text[:length].encode("ascii", errors="replace").decode("ascii")


def print_encounters(encounters: list, max_text: int = 600) -> None:
    for enc in encounters:
        text_raw = enc.get("text") or ""
        flags_raw = str(enc.get("flags") or "")[:80]
        matched = flag_text(text_raw)
        print(f"\n  [{enc['enc_date']}]  id={enc['enc_id']}")
        print(f"    flags   : {_safe(flags_raw, 80)}")
        if matched:
            print(f"    keywords: {matched}")
        print(f"    text    : {_safe(text_raw, max_text)}")


def main() -> None:
    client = PatientGraphClient()

    # -- Sanity check: all cancer types
    print("=" * 70)
    print("SANITY CHECK -- All distinct cancer_type values in EpisodeOfCare")
    print("=" * 70)
    for row in get_all_cancer_types(client):
        print(f"  {row['ct']:40s}  n={row['n']}")
    print()

    # -- Step 1: All lung episodes
    print("=" * 70)
    print("STEP 1 -- All lung episodes")
    print("=" * 70)
    lung_episodes = get_lung_episodes(client)

    if not lung_episodes:
        print("No lung episodes found! Trying partial match on 'lung'...")
        # Try a broader search
        with client.session() as s:
            rows = s.run(
                "MATCH (ep:EpisodeOfCare) "
                "RETURN DISTINCT ep.cancer_type AS ct LIMIT 50"
            ).data()
        print("All cancer_type values found:")
        for r in rows:
            print(f"  {r['ct']!r}")
        return

    print(f"Found {len(lung_episodes)} lung episode(s).\n")

    for ep in lung_episodes:
        pid = ep["patient_id"]
        eid = ep["episode_id"]
        status = ep["status"]
        ref_date = ep["referral_date"]
        spec_date = ep["specialist_visit_date"]
        inferred = ep["inferred_outcome"]
        confidence = ep["inferred_confidence"]
        signals = ep["inference_signals"]
        hitl = ep["hitl_flag"]
        hitl_reason = ep["hitl_reason"]

        days_ref = days_since(ref_date)
        days_spec = days_since(spec_date)

        print("-" * 70)
        print(f"Episode   : {eid}")
        print(f"Patient   : {pid}")
        print(f"Status    : {status}")
        print(f"Cancer    : {ep['cancer_type']}")
        print(f"Referral  : {ref_date}  ({days_ref} days ago)")
        print(f"Specialist: {spec_date}  ({days_spec} days ago)" if spec_date else "Specialist: None")
        print(f"Inferred  : {inferred}  (confidence={confidence})")
        print(f"Signals   : {signals}")
        print(f"HITL      : flag={hitl}  reason={hitl_reason}")

        if status == "stale_no_diagnosis":
            print(f"\n  >>> stale_no_diagnosis: {days_ref} days since referral")
            if days_ref and days_ref < 365:
                print("  >>> WARNING: <12 months - may be incorrectly classified as stale")
            else:
                print("  >>> Genuinely >=12 months since referral - classification looks correct")

        elif status == "stale_post_specialist":
            print(f"\n  >>> stale_post_specialist: specialist seen {days_spec} days ago")
            print(f"  >>> inferred_outcome = {inferred!r}")
        print()

    # -- Step 2: Full encounter list per patient
    patient_ids = list({ep["patient_id"] for ep in lung_episodes})

    for pid in patient_ids:
        print("=" * 70)
        print(f"STEP 2 -- ALL encounters from 2020+ for patient {pid}")
        print("=" * 70)
        encounters = get_encounters(client, pid, since="2020-01-01")
        if not encounters:
            print("  No encounters found.\n")
            continue
        print(f"  {len(encounters)} encounter(s) found.\n")
        print_encounters(encounters, max_text=400)
        print()

    # -- Step 3: Targeted per-episode analysis
    print("=" * 70)
    print("STEP 3 -- Targeted clinical analysis per episode")
    print("=" * 70)

    for ep in lung_episodes:
        pid = ep["patient_id"]
        eid = ep["episode_id"]
        status = ep["status"]
        ref_date = ep["referral_date"]

        print(f"\n{'=' * 50}")
        print(f"Episode {eid} | {status}")
        print(f"{'=' * 50}")

        # Other episodes for same patient
        others = get_other_episodes(client, pid, eid)
        if others:
            print("\n  Other episodes for same patient:")
            for oe in others:
                print(f"    {oe['episode_id']} | {oe['cancer_type']} | {oe['status']} | "
                      f"ref={oe['referral_date']} | inferred={oe['inferred_outcome']}")
        else:
            print("\n  No other episodes for this patient.")

        # Clinically relevant encounters from referral date onwards
        since = (ref_date or "2020-01-01")[:10]
        imaging = get_relevant_encounters(client, pid, since)
        if imaging:
            print(f"\n  Clinically relevant encounters from {since} ({len(imaging)}):")
            print_encounters(imaging, max_text=700)
        else:
            print(f"\n  No clinically relevant encounters found from {since}.")

    # -- Step 4: stale_no_diagnosis deep-dive
    no_diag = [ep for ep in lung_episodes if ep["status"] == "stale_no_diagnosis"]
    if no_diag:
        print("\n" + "=" * 70)
        print("STEP 4 -- stale_no_diagnosis deep-dive (ALL encounters after referral)")
        print("=" * 70)
        for ep in no_diag:
            pid = ep["patient_id"]
            ref_date = ep["referral_date"]
            days_ref = days_since(ref_date)
            print(f"\n  Patient : {pid}")
            print(f"  Referral: {ref_date}  ({days_ref} days = approx {(days_ref or 0)//365} yr(s))")
            verdict = "YES - genuinely stale" if (days_ref or 0) >= 365 else "NO - < 12 months, possible misclassification"
            print(f"  Genuinely >12 months: {verdict}")

            since = (ref_date or "2020-01-01")[:10]
            encs = get_encounters(client, pid, since=since)
            if encs:
                print(f"\n  All {len(encs)} encounters from referral date onwards:")
                print_encounters(encs, max_text=600)
            else:
                print("  No encounters found after referral date.")

    print("\n" + "=" * 70)
    print("Investigation complete.")
    print("=" * 70)


if __name__ == "__main__":
    main()
