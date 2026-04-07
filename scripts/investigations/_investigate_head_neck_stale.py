"""
Investigation: Why are head & neck cancer pathway episodes disproportionately stale?
6 out of 12 head_and_neck episodes are stale_post_specialist.
"""
import sys
from pathlib import Path
from datetime import timedelta

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()
from libs.neo4j_client.client import PatientGraphClient

CANCER_TYPE = "head_and_neck"

# Clinical terms that indicate the encounter is outcome-relevant
OUTCOME_KEYWORDS = [
    "biopsy", "pathology", "histology", "FNA", "fine needle",
    "malignant", "benign", "cancer", "carcinoma", "tumour", "tumor",
    "lymphoma", "thyroid", "oesophageal", "barrett", "laryngeal",
    "nasopharyngeal", "tonsillitis", "hoarseness", "nodule", "cyst",
    "one-stop", "one stop", "neck lump", "salivary", "discharge",
    "clear", "normal", "no evidence", "no malignancy", "not malignant",
    "reassured", "watchful waiting", "surveillance", "follow-up",
    "radiotherapy", "chemotherapy", "surgery", "resection",
]


def flag_keywords(text: str) -> list:
    if not text:
        return []
    lower = text.lower()
    return [kw for kw in OUTCOME_KEYWORDS if kw in lower]


def get_all_head_neck_episodes(client: PatientGraphClient) -> list:
    query = """
    MATCH (ep:EpisodeOfCare {cancer_type: $ct})
    RETURN ep.patient_id AS patient_id,
           ep.episode_id AS episode_id,
           ep.status AS status,
           ep.referral_date AS referral_date,
           ep.specialist_visit_date AS specialist_visit_date,
           ep.inferred_outcome AS inferred_outcome,
           ep.inferred_outcome_date AS inferred_outcome_date,
           ep.inferred_confidence AS inferred_confidence,
           ep.inference_signals AS inference_signals,
           ep.hitl_flag AS hitl_flag,
           ep.hitl_reason AS hitl_reason
    ORDER BY ep.status, ep.referral_date
    """
    with client.session() as s:
        result = s.run(query, ct=CANCER_TYPE)
        return [dict(r) for r in result]


def get_encounters_in_window(client: PatientGraphClient, patient_id: str,
                             start_date, end_date) -> list:
    query = """
    MATCH (p:Patient {id: $pid})-[:HAS_ENCOUNTER]->(enc:Encounter)
    WHERE enc.date >= $start AND enc.date <= $end
    RETURN enc.id AS enc_id,
           enc.date AS date,
           enc.text AS text,
           enc.flags AS flags
    ORDER BY enc.date
    """
    start_str = str(start_date)[:10] if start_date else None
    end_str = str(end_date)[:10] if end_date else None
    with client.session() as s:
        result = s.run(query, pid=patient_id, start=start_str, end=end_str)
        return [dict(r) for r in result]


def get_all_encounters(client: PatientGraphClient, patient_id: str) -> list:
    query = """
    MATCH (p:Patient {id: $pid})-[:HAS_ENCOUNTER]->(enc:Encounter)
    RETURN enc.id AS enc_id,
           enc.date AS date,
           enc.text AS text,
           enc.flags AS flags
    ORDER BY enc.date
    """
    with client.session() as s:
        result = s.run(query, pid=patient_id)
        return [dict(r) for r in result]


def date_plus(d, days=365):
    if d is None:
        return None
    # Handle Neo4j Date objects and strings
    if hasattr(d, 'year'):
        from datetime import date
        base = date(d.year, d.month, d.day)
    else:
        from datetime import date
        parts = str(d)[:10].split("-")
        base = date(int(parts[0]), int(parts[1]), int(parts[2]))
    return base + timedelta(days=days)


def print_separator(char="=", width=80):
    print(char * width)


def print_episode_summary(ep: dict):
    print(f"  Episode ID  : {ep['episode_id']}")
    print(f"  Patient ID  : {ep['patient_id']}")
    print(f"  Status      : {ep['status']}")
    print(f"  Referral    : {ep['referral_date']}")
    print(f"  Specialist  : {ep['specialist_visit_date']}")
    print(f"  Outcome     : {ep['inferred_outcome']}")
    print(f"  Outcome date: {ep['inferred_outcome_date']}")
    print(f"  Confidence  : {ep['inferred_confidence']}")
    print(f"  Signals     : {ep['inference_signals']}")
    print(f"  HITL flag   : {ep['hitl_flag']}")
    print(f"  HITL reason : {ep['hitl_reason']}")


def analyse_stale_episode(client: PatientGraphClient, ep: dict):
    pid = ep["patient_id"]
    ref_date = ep["referral_date"]
    spec_date = ep["specialist_visit_date"]
    end_date = date_plus(ref_date, 365)

    print(f"\n{'=' * 80}")
    print(f"STALE EPISODE: {ep['episode_id']}  Patient: {pid}")
    print_separator("-")
    print_episode_summary(ep)
    print_separator("-")

    if ref_date:
        encounters = get_encounters_in_window(client, pid, ref_date, end_date)
    else:
        encounters = get_all_encounters(client, pid)

    if not encounters:
        print("  [!] NO encounters found in window (referral_date to +365d)")
        return

    print(f"\n  Encounters from {ref_date} to {end_date}  (n={len(encounters)}):")
    print_separator("-", 80)

    outcome_candidates = []

    for enc in encounters:
        date_str = str(enc["date"])[:10] if enc["date"] else "unknown"
        flags = enc["flags"] or []
        text = enc["text"] or ""
        snippet = text[:300].replace("\n", " ")
        hits = flag_keywords(text)

        marker = ""
        if hits:
            marker = " <-- KEYWORDS: " + ", ".join(hits[:6])
            outcome_candidates.append({
                "date": date_str,
                "flags": flags,
                "keywords": hits,
                "snippet": snippet,
            })

        print(f"  {date_str}  flags={flags}{marker}")
        if hits:
            print(f"    TEXT: {snippet}")
            print()

    print_separator("-", 80)
    _interpret_findings(ep, outcome_candidates, encounters)


def _interpret_findings(ep: dict, candidates: list, all_encounters: list):
    print("\n  INTERPRETATION:")
    if not candidates:
        print("  -> No outcome-relevant keywords found in any encounter text.")
        print("  -> Likely cause: PRIVATE letter or out-of-system follow-up.")
        print("     Consider: genuine no-outcome-yet OR discharge via non-GP pathway.")
        return

    # Check for different cancer type signals
    diff_cancers = {
        "thyroid": ["thyroid", "FNA", "fine needle"],
        "oesophageal": ["oesophageal", "barrett", "barrett's"],
        "laryngeal": ["laryngeal", "larynx"],
        "nasopharyngeal": ["nasopharyngeal", "nasopharynx"],
        "lymphoma": ["lymphoma"],
        "skin": ["melanoma", "squamous cell", "basal cell"],
    }
    benign_signals = [
        "benign", "tonsillitis", "hoarseness", "nodule", "cyst",
        "salivary", "reassured", "no malignancy", "not malignant",
        "normal", "no evidence", "clear",
    ]
    treatment_signals = [
        "radiotherapy", "chemotherapy", "surgery", "resection",
        "excision", "biopsy confirmed",
    ]

    found_diff_cancers = []
    found_benign = []
    found_treatment = []
    found_pathology = []

    for c in candidates:
        kws = [k.lower() for k in c["keywords"]]
        for cancer_name, signals in diff_cancers.items():
            if any(s in kws for s in signals):
                found_diff_cancers.append(cancer_name)
        if any(s in kws for s in benign_signals):
            found_benign.append(c["date"])
        if any(s in kws for s in treatment_signals):
            found_treatment.append(c["date"])
        if any(s in kws for s in ["biopsy", "pathology", "histology", "FNA"]):
            found_pathology.append(c["date"])

    if found_diff_cancers:
        print(f"  -> POSSIBLE WRONG CANCER TYPE: found signals for {set(found_diff_cancers)}")
        print("     Episode is classified head_and_neck but text suggests different primary.")

    if found_benign:
        print(f"  -> BENIGN OUTCOME SIGNALS on dates: {found_benign}")
        print("     Outcome may have been recorded but inference missed it.")

    if found_treatment:
        print(f"  -> TREATMENT SIGNALS on dates: {found_treatment}")
        print("     Patient may be on active treatment -- outcome should NOT be stale.")

    if found_pathology:
        print(f"  -> PATHOLOGY/BIOPSY RESULTS on dates: {found_pathology}")
        print("     Delayed pathology result may exist -- check if inferred_outcome_date")
        print("     was set before the biopsy date.")

    # Check timing
    ref_date = ep["referral_date"]
    spec_date = ep["specialist_visit_date"]
    if spec_date and ref_date:
        try:
            from datetime import date
            def to_date(d):
                if hasattr(d, 'year'):
                    return date(d.year, d.month, d.day)
                parts = str(d)[:10].split("-")
                return date(int(parts[0]), int(parts[1]), int(parts[2]))
            r = to_date(ref_date)
            s = to_date(spec_date)
            days_to_spec = (s - r).days
            print(f"\n  Days referral->specialist: {days_to_spec}d")
            if days_to_spec > 62:
                print("  -> Specialist visit was LATE (>62 days post-referral)")
        except Exception:
            pass

    if not found_diff_cancers and not found_benign and not found_treatment and not found_pathology:
        print("  -> Outcome keywords present but not definitive.")
        print("     Manual review of encounter text recommended.")

    # Check for one-stop clinic
    for c in candidates:
        if "one-stop" in " ".join(c["keywords"]) or "one stop" in " ".join(c["keywords"]) or "neck lump" in " ".join(c["keywords"]):
            print("  -> ONE-STOP / NECK LUMP CLINIC mention found:")
            print(f"     {c['date']}: {c['snippet'][:200]}")


def main():
    client = PatientGraphClient()

    print_separator()
    print("HEAD & NECK CANCER PATHWAY -- STALE EPISODE INVESTIGATION")
    print_separator()

    episodes = get_all_head_neck_episodes(client)
    print(f"\nTotal head_and_neck episodes: {len(episodes)}")

    status_counts = {}
    for ep in episodes:
        s = ep["status"] or "unknown"
        status_counts[s] = status_counts.get(s, 0) + 1
    print("\nStatus breakdown:")
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}")

    print("\n\nALL HEAD & NECK EPISODES (summary):")
    print_separator("-")
    for ep in episodes:
        ref = str(ep["referral_date"])[:10] if ep["referral_date"] else "N/A"
        spec = str(ep["specialist_visit_date"])[:10] if ep["specialist_visit_date"] else "N/A"
        out = ep["inferred_outcome"] or "None"
        print(f"  {ep['episode_id']}  pat={ep['patient_id']}  status={ep['status']}  ref={ref}  spec={spec}  outcome={out}")

    stale_episodes = [ep for ep in episodes if ep["status"] == "stale_post_specialist"]
    print(f"\n\nSTALE_POST_SPECIALIST EPISODES: {len(stale_episodes)}")
    print_separator()

    for ep in stale_episodes:
        analyse_stale_episode(client, ep)

    print("\n\nSUMMARY TABLE")
    print_separator()
    print(f"{'Episode':30} {'Patient':15} {'Ref date':12} {'Spec date':12} {'Signals found'}")
    print_separator("-")
    for ep in stale_episodes:
        ref = str(ep["referral_date"])[:10] if ep["referral_date"] else "N/A"
        spec = str(ep["specialist_visit_date"])[:10] if ep["specialist_visit_date"] else "N/A"
        sigs = str(ep["inference_signals"] or "")[:40]
        print(f"  {str(ep['episode_id']):28} {str(ep['patient_id']):15} {ref:12} {spec:12} {sigs}")

    print("\nInvestigation complete.")


if __name__ == "__main__":
    main()
