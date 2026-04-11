"""
Investigation: NSS closed_related episodes + unknown cancer_type episodes.

Run from workspace root:
    python scripts/investigations/_investigate_nss_and_unknown.py
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()
from libs.neo4j_client.client import PatientGraphClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sep(char="=", width=72):
    print(char * width)


def _run(client, cypher, params=None):
    with client._driver.session() as s:
        return list(s.run(cypher, params or {}))


# ---------------------------------------------------------------------------
# INVESTIGATION 1 -- non_site_specific closed_related episodes
# ---------------------------------------------------------------------------

_NSS_ALL_STATUSES = """
MATCH (ep:EpisodeOfCare {cancer_type: 'non_site_specific'})
RETURN ep.status AS status, count(*) AS cnt
ORDER BY cnt DESC
"""

_NSS_CLOSED_RELATED = """
MATCH (ep:EpisodeOfCare {status: 'closed_related', cancer_type: 'non_site_specific'})
RETURN
    ep.patient_id      AS patient_id,
    ep.episode_id      AS episode_id,
    ep.referral_date   AS referral_date,
    ep.auto_close_reason AS auto_close_reason
ORDER BY ep.patient_id
"""

_COMPLETED_SIBLINGS = """
MATCH (ep:EpisodeOfCare {patient_id: $pid, status: 'completed'})
RETURN
    ep.cancer_type   AS cancer_type,
    ep.referral_date AS referral_date,
    ep.episode_id    AS episode_id
ORDER BY ep.referral_date
"""

_ENCOUNTERS_AROUND = """
MATCH (p:Patient {id: $pid})-[:HAS_ENCOUNTER]->(enc:Encounter)
WHERE enc.date >= $date_from AND enc.date <= $date_to
RETURN enc.id AS enc_id, enc.date AS enc_date, enc.text AS text, enc.flags AS flags
ORDER BY enc.date
LIMIT 5
"""


def _date_window(ref_date_str, days=7):
    if not ref_date_str:
        return None, None
    try:
        ref = datetime.strptime(str(ref_date_str)[:10], "%Y-%m-%d")
        return (ref - timedelta(days=days)).strftime("%Y-%m-%d"), (
            ref + timedelta(days=days)
        ).strftime("%Y-%m-%d")
    except ValueError:
        return None, None


def investigate_nss(client):
    _sep()
    print("INVESTIGATION 1 -- non_site_specific closed_related episodes")
    _sep()

    # 1a. Status breakdown
    print("\n[1a] All non_site_specific episode statuses:")
    rows = _run(client, _NSS_ALL_STATUSES)
    for r in rows:
        print(f"  {r['status']:25s}  {r['cnt']:>4d}")

    # 1b. The 7 closed_related NSS episodes
    print("\n[1b] closed_related NSS episodes (sibling close audit):")
    nss_rows = _run(client, _NSS_CLOSED_RELATED)
    print(f"  Found {len(nss_rows)} closed_related NSS episodes\n")

    for nss in nss_rows:
        pid = nss["patient_id"]
        ref_date = nss["referral_date"]
        reason = nss["auto_close_reason"] or "(no reason stored)"

        siblings = _run(client, _COMPLETED_SIBLINGS, {"pid": pid})

        print(f"  Patient : {pid}")
        print(f"  NSS ep  : {nss['episode_id']}")
        print(f"  Ref date: {ref_date}")
        print(f"  Reason  : {reason}")

        if siblings:
            for sib in siblings:
                print(
                    f"  Sibling : {sib['cancer_type']:25s} | "
                    f"ref={sib['referral_date']} | ep={sib['episode_id']}"
                )
            best = siblings[0]
            print(
                f"  --> Patient {pid} had NSS episode closed because they had "
                f"a confirmed [{best['cancer_type']}] cancer episode"
            )
        else:
            print("  Sibling : (no completed sibling found)")

        # Show encounter text around referral date
        d_from, d_to = _date_window(ref_date, days=7)
        if d_from:
            encs = _run(
                client,
                _ENCOUNTERS_AROUND,
                {"pid": pid, "date_from": d_from, "date_to": d_to},
            )
            if encs:
                print(f"  Encounters around referral ({d_from} to {d_to}):")
                for enc in encs:
                    snippet = (enc["text"] or "")[:200].replace("\n", " ")
                    print(f"    [{enc['enc_date']}] flags={enc['flags']} | {snippet}")
            else:
                print(f"  Encounters around referral: (none in +/-7 days)")
        print()


# ---------------------------------------------------------------------------
# INVESTIGATION 2 -- unknown cancer_type episodes
# ---------------------------------------------------------------------------

_UNKNOWN_SAMPLE = """
MATCH (ep:EpisodeOfCare {cancer_type: 'unknown'})
RETURN
    ep.status           AS status,
    ep.referral_date    AS referral_date,
    ep.patient_id       AS patient_id,
    ep.episode_id       AS episode_id,
    ep.inferred_outcome AS inferred_outcome,
    ep.inference_signals AS inference_signals
LIMIT 10
"""

_UNKNOWN_STATUS_BREAKDOWN = """
MATCH (ep:EpisodeOfCare {cancer_type: 'unknown'})
RETURN ep.status AS status, count(*) AS cnt
ORDER BY cnt DESC
"""

_UNKNOWN_INFERRED_OUTCOMES = """
MATCH (ep:EpisodeOfCare {cancer_type: 'unknown', status: 'completed'})
RETURN ep.inferred_outcome AS inferred_outcome, count(*) AS cnt
ORDER BY cnt DESC
"""

_UNKNOWN_COMPLETED_DETAIL = """
MATCH (ep:EpisodeOfCare {cancer_type: 'unknown', status: 'completed'})
RETURN
    ep.patient_id        AS patient_id,
    ep.episode_id        AS episode_id,
    ep.referral_date     AS referral_date,
    ep.inferred_outcome  AS inferred_outcome,
    ep.inference_signals AS inference_signals
ORDER BY ep.referral_date
LIMIT 10
"""

_ENCOUNTER_CONCEPTS = """
MATCH (p:Patient {id: $pid})-[:HAS_ENCOUNTER]->(enc:Encounter)
WHERE enc.date >= $date_from AND enc.date <= $date_to
OPTIONAL MATCH (enc)-[:HAS_CONCEPT]->(c)
RETURN
    enc.id   AS enc_id,
    enc.date AS enc_date,
    enc.text AS text,
    enc.flags AS flags,
    collect(c.name) AS concept_names
ORDER BY enc.date
LIMIT 5
"""


def investigate_unknown(client):
    _sep()
    print("INVESTIGATION 2 -- unknown cancer_type episodes")
    _sep()

    # 2a. Status breakdown
    print("\n[2a] unknown cancer_type episode statuses:")
    rows = _run(client, _UNKNOWN_STATUS_BREAKDOWN)
    total = sum(r["cnt"] for r in rows)
    for r in rows:
        print(f"  {r['status']:25s}  {r['cnt']:>4d}")
    print(f"  {'TOTAL':25s}  {total:>4d}")

    # 2b. Inferred outcomes for completed ones
    print("\n[2b] Inferred outcomes for completed unknown episodes:")
    rows = _run(client, _UNKNOWN_INFERRED_OUTCOMES)
    for r in rows:
        print(f"  {str(r['inferred_outcome']):30s}  {r['cnt']:>4d}")

    # 2c. Sample of 10 unknown episodes
    print("\n[2c] Sample unknown episodes (first 10):")
    rows = _run(client, _UNKNOWN_SAMPLE)
    for r in rows:
        print(
            f"  pid={r['patient_id']}  ep={r['episode_id']}  "
            f"status={r['status']}  ref={r['referral_date']}  "
            f"outcome={r['inferred_outcome']}"
        )
        signals = r["inference_signals"]
        if signals:
            print(f"    signals: {signals}")

    # 2d. Encounter text + concepts for 5 unknown completed episodes
    print(
        "\n[2d] Encounter text + concept names for sample unknown completed episodes:"
    )
    detail_rows = _run(client, _UNKNOWN_COMPLETED_DETAIL)

    for ep in detail_rows[:5]:
        pid = ep["patient_id"]
        ref_date = ep["referral_date"]
        d_from, d_to = _date_window(ref_date, days=7)
        print(
            f"\n  Patient {pid} | ep={ep['episode_id']} | "
            f"ref={ref_date} | outcome={ep['inferred_outcome']}"
        )
        signals = ep["inference_signals"]
        if signals:
            print(f"  signals: {signals}")

        if not d_from:
            print("  (no parseable referral date)")
            continue

        encs = _run(
            client,
            _ENCOUNTER_CONCEPTS,
            {"pid": pid, "date_from": d_from, "date_to": d_to},
        )
        if not encs:
            print(f"  (no encounters in window {d_from} to {d_to})")
            continue

        for enc in encs:
            snippet = (enc["text"] or "")[:300].replace("\n", " ")
            concepts = [c for c in (enc["concept_names"] or []) if c]
            print(f"  [{enc['enc_date']}] flags={enc['flags']}")
            if concepts:
                print(f"    concepts : {concepts}")
            if snippet:
                print(f"    text     : {snippet}")

    # 2e. Summary analysis
    _sep("-")
    print("\n[2e] ANALYSIS -- What triggers 'unknown' cancer_type?")
    print("""
  The episode_builder._extract_condition_key() maps SNOMED concept names to
  site keys using _SITE_MAP. If no keyword in the map matches the concept
  name, the function returns 'unknown'.

  Concept name keywords covered by _SITE_MAP:
    - Lower GI  : colorectal, bowel, rectal, colon, intestin, sigmoid, cecum,
                  caecum, appendix, 'anal ', anus
    - Upper GI  : pancreatic, pancrea, oesophag, esophag, gastric, stomach,
                  hepat, liver, biliary, duodenum, duodenal
    - Urological: urological, prostate, bladder, renal, kidney, testis,
                  testic, ureter, urethr, penis, scrotal, scrotum
    - Gynae     : cervix, uteri, uterus, endometr, ovary, ovarian, vagina,
                  vulva, fallopian, trophoblast
    - Haemato   : lymphoma, leukaemia, leukemia, lymphoid, haemopoietic,
                  hemopoietic, myeloma, myeloid, lymphocytic
    - Single    : breast, lung, skin, melanoma, sarcoma, brain
    - NSS       : fast, non-site-specific, non site specific
    - Other     : upper gi, gynaecological, haematological, childrens tumour

  'unknown' = INTENTIONAL FALLBACK for concept names that do not contain any
  of the above keywords. Likely triggers:
    - Generic cancer concepts e.g. "Malignant tumour", "Carcinoma NOS",
      "Suspected malignancy", "Neoplasm", "Adenocarcinoma" (no site specified)
    - Head/neck, thyroid, bone, adrenal concepts not yet in _SITE_MAP
    - SNOMED codes whose display names use uncommon synonyms

  RECOMMENDATION: Review the concept names appearing in encounter/concept
  nodes for these episodes and extend _SITE_MAP with missing site keywords,
  or add a 'head_neck' / 'thyroid' / 'other' bucket.
""")
    _sep()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    client = PatientGraphClient()
    try:
        investigate_nss(client)
        investigate_unknown(client)
    finally:
        client.close()


if __name__ == "__main__":
    main()
