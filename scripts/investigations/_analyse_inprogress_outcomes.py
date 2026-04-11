"""For each in_progress EpisodeOfCare, pull encounters after the referral date
and classify each episode into an outcome category:

  CANCER_CONFIRMED  -- cancer diagnosis coded post-referral
  BENIGN_CODED      -- 395100000 or specific benign diagnoses coded
  BENIGN_ALT        -- alternative benign diagnosis coded (fibroadenoma etc.)
  CANCELLED         -- referral was cancelled / patient declined
  SURVEILLANCE      -- repeated referrals consistent with surveillance pathway
  NO_FOLLOWUP       -- no encounters after referral date at all
  UNKNOWN           -- encounters exist but no clear signal

Run:
    python scripts/investigations/_analyse_inprogress_outcomes.py
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

_Q_OPEN = """
MATCH (ep:EpisodeOfCare)
WHERE ep.status = 'in_progress'
RETURN
    ep.patient_id    AS pid,
    ep.cancer_type   AS site,
    ep.referral_date AS ref_date,
    ep.episode_id    AS ep_id,
    ep.specialist_seen AS spec_seen
ORDER BY ep.patient_id, ep.referral_date
"""

_Q_POST_REF = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE p.id = $pid
  AND toString(e.date) >= $from_date
OPTIONAL MATCH (e)-[doc:DOCUMENTS]->(concept)
WITH e, collect({
    name: coalesce(concept.name, ''),
    cid:  coalesce(toString(concept.conceptId), ''),
    assertion: coalesce(doc.assertion, ''),
    evidence: coalesce(doc.evidence, '')
}) AS codings
RETURN
    toString(e.date)                              AS edate,
    coalesce(e.text, e.note, e.description, '')   AS enc_text,
    codings
ORDER BY e.date
"""

# SNOMED concept IDs for key signals
_BENIGN_CLOSURE_IDS = {"395100000"}
_CANCER_IDS = {
    "363346000",  # Malignant neoplastic disease
    "363443007",  # Malignant tumor of breast
    "187164000",  # Malignant neoplasm of prostate
    "372244006",  # Malignant melanoma of skin
    "254637007",  # Non-small cell carcinoma of lung
    "363358000",  # Malignant tumor of colon
    "188340000",  # Malignant tumor of rectum
    "188380009",  # Basal cell carcinoma of skin
    "372244006",  # Malignant melanoma
    "414028008",  # DCIS
    "254837009",  # Invasive ductal carcinoma
    "109989006",  # Malignant neoplasm of skin
    "363346000",  # Generic malignant neoplastic disease
    "420120006",  # Squamous cell carcinoma
    "189299008",  # Malignant neoplasm of upper GI
    "363418001",  # Malignant neoplasm of kidney
    "126906006",  # Malignant neoplasm of prostate
    "189002002",  # Malignant neoplasm of oesophagus
    "363354003",  # Malignant neoplasm of small intestine
    "187750001",  # Malignant neoplasm of head/neck
    "109370002",  # Malignant neoplasm of urinary bladder
    "187597004",  # Malignant neoplasm of ovary
    "363358000",  # Malignant neoplasm of intestine
    "188145008",  # CLL/SLL
    "413448000",  # Metastatic malignant neoplasm
    "3344001",  # Malignant lymphoma
}
_BENIGN_ALT_IDS = {
    "126736007",  # Fibroadenoma of breast
    "444896006",  # Tubular adenoma of colon
    "34840004",  # Haemorrhoids
    "235494005",  # Hiatus hernia
    "40121002",  # Ulcerative colitis
    "196808003",  # Benign prostatic hyperplasia
    "194786009",  # Presbycusis
}
_BENIGN_ALT_NAMES_LOWER = {
    "fibroadenoma",
    "tubular adenoma",
    "haemorrhoid",
    "hemorrhoid",
    "hiatus hernia",
    "ulcerative colitis",
    "benign prostatic",
    "presbycusis",
    "benign pathology",
    "benign histology",
    "benign on biopsy",
    "no dysplasia",
    "no malignancy",
    "no evidence of cancer",
    "confirmed benign",
    "not suspicious for malignancy",
    "normal colonoscopy",
    "normal endoscopy",
    "normal colposcopy",
    "normal mammog",
    "polyp removed but no cancer",
    "no sinister findings",
    "nad",
    "normal and discharged",
    "discharged from clinic",
    "safe to discharge",
}
_CANCEL_TERMS = {
    "cancelled by patient",
    "referral cancelled",
    "did not attend",
    "patient declined",
    "dna",
    "unable to attend",
    "withdrawn",
    "patient cancelled",
}


def _classify_encounter(edate: str, enc_text: str, codings: list[dict]) -> str | None:
    coded_ids = {c["cid"] for c in codings if c["cid"]}
    coded_names = " ".join(c["name"].lower() for c in codings if c["name"])
    assertions = {c["assertion"] for c in codings if c["assertion"]}
    text_lower = (enc_text or "").lower()

    if "395100000" in coded_ids:
        return "BENIGN_CODED"

    if coded_ids & _CANCER_IDS:
        # Confirm it is present (not historical / absent)
        for c in codings:
            if c["cid"] in _CANCER_IDS and c["assertion"] in ("present", ""):
                return "CANCER_CONFIRMED"

    for c in codings:
        if c["cid"] in _BENIGN_ALT_IDS and c["assertion"] in ("present", ""):
            return "BENIGN_ALT"

    combined = coded_names + " " + text_lower
    for term in _BENIGN_ALT_NAMES_LOWER:
        if term in combined:
            return "BENIGN_ALT"

    for term in _CANCEL_TERMS:
        if term in text_lower or term in coded_names:
            return "CANCELLED"

    return None


def main() -> None:
    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()

    open_rows = client.run(_Q_OPEN) or []
    print(f"in_progress episodes: {len(open_rows)}")
    print()

    eps_by_pid: dict[str, list[dict]] = defaultdict(list)
    for row in open_rows:
        eps_by_pid[row["pid"]].append(
            {
                "site": row["site"] or "unknown",
                "ref_date": str(row["ref_date"] or ""),
                "ep_id": row["ep_id"],
                "spec_seen": bool(row["spec_seen"]),
            }
        )

    results: list[dict] = []

    for pid in sorted(eps_by_pid.keys()):
        episodes = eps_by_pid[pid]
        # Pull all encounters from 14d before earliest referral
        min_ref = (
            min(ep["ref_date"][:10] for ep in episodes if ep["ref_date"])
            if any(ep["ref_date"] for ep in episodes)
            else "2000-01-01"
        )
        try:
            from_date = (
                date.fromisoformat(min_ref) if min_ref else date(2000, 1, 1)
            ).isoformat()
        except ValueError:
            from_date = "2000-01-01"

        enc_rows = client.run(_Q_POST_REF, pid=pid, from_date=from_date) or []

        # Classify signal from all encounters
        overall_signal = None
        cancer_enc = benign_enc = cancel_enc = None
        for enc in enc_rows:
            sig = _classify_encounter(
                enc["edate"], enc["enc_text"], enc["codings"] or []
            )
            if sig == "CANCER_CONFIRMED" and not cancer_enc:
                cancer_enc = enc["edate"]
                overall_signal = "CANCER_CONFIRMED"
            elif sig in ("BENIGN_CODED", "BENIGN_ALT") and not benign_enc:
                benign_enc = enc["edate"]
                if overall_signal != "CANCER_CONFIRMED":
                    overall_signal = sig
            elif sig == "CANCELLED" and not cancel_enc:
                cancel_enc = enc["edate"]
                if overall_signal not in (
                    "CANCER_CONFIRMED",
                    "BENIGN_CODED",
                    "BENIGN_ALT",
                ):
                    overall_signal = "CANCELLED"

        if not overall_signal:
            overall_signal = "NO_FOLLOWUP" if not enc_rows else "UNKNOWN"

        for ep in episodes:
            ref = ep["ref_date"][:10] if ep["ref_date"] else "???"
            spec = "Y" if ep["spec_seen"] else "N"
            # Age of referral
            try:
                days = (
                    (date.today() - date.fromisoformat(ref)).days
                    if ref != "???"
                    else -1
                )
                age = (
                    "<3mo"
                    if days < 90
                    else (
                        "3-6mo"
                        if days < 180
                        else (
                            "6-12mo"
                            if days < 365
                            else "1-2yr" if days < 730 else ">2yr"
                        )
                    )
                )
            except Exception:
                age = "?"

            results.append(
                {
                    "pid": pid,
                    "site": ep["site"],
                    "ref_date": ref,
                    "age": age,
                    "spec": spec,
                    "outcome": overall_signal,
                    "cancer_enc": cancer_enc or "",
                    "benign_enc": benign_enc or "",
                    "cancel_enc": cancel_enc or "",
                }
            )

    client.close()

    # Print grouped by outcome
    by_outcome: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        by_outcome[r["outcome"]].append(r)

    order = [
        "CANCER_CONFIRMED",
        "BENIGN_CODED",
        "BENIGN_ALT",
        "CANCELLED",
        "UNKNOWN",
        "NO_FOLLOWUP",
    ]
    total = len(results)

    print(f"{'='*90}")
    print(f"OUTCOME CLASSIFICATION  ({total} in_progress episodes)")
    print(f"{'='*90}")

    for outcome in order:
        items = by_outcome.get(outcome, [])
        if not items:
            continue
        print(f"\n--- {outcome} ({len(items)}) ---")
        print(
            f"  {'PID':<14} {'SITE':<22} {'REF_DATE':<12} {'AGE':<7} {'SPEC':<5} {'SIGNAL DATE'}"
        )
        for r in sorted(items, key=lambda x: x["ref_date"]):
            sig_date = r["cancer_enc"] or r["benign_enc"] or r["cancel_enc"] or ""
            print(
                f"  {r['pid']:<14} {r['site']:<22} {r['ref_date']:<12} {r['age']:<7} {r['spec']:<5} {sig_date}"
            )

    print()
    print("SUMMARY:")
    for outcome in order:
        n = len(by_outcome.get(outcome, []))
        pct = n / total * 100 if total else 0
        print(f"  {outcome:<20}: {n:3d}  ({pct:.0f}%)")


if __name__ == "__main__":
    main()
