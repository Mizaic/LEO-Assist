"""Investigate stale episode counts - hunt for bugs, missing surface forms, missing SNOMED.

Checks three hypotheses:
  A) _STALE_CLOSE_Q date-math bug: stale_post_specialist uses ref_date not
     specialist-visit date, so any ep with specialist_seen=true AND old referral
     is flagged stale regardless of when the specialist was actually seen.
  B) benign_closure bucket not firing: no_cancer_discharge ValueSet missing
     milestone_type in Neo4j FHIR extension, or simply absent from the KG.
  C) seen_by_specialist concepts not matching real GP coding patterns: actual
     specialist encounter concepts not in the domain.

Run:
    python scripts/investigations/_debug_stale_episodes.py
"""

from __future__ import annotations

import json
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

# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

# All ValueSets in the KG with their milestone type from FHIR extensions
_Q_VALUESETS = """
MATCH (v:ValueSet)
WHERE v.id STARTS WITH 'ncda-'
RETURN v.id AS vs_id,
       v.rawJson IS NOT NULL AS has_raw,
       size(coalesce(v.rawJson, '')) AS raw_len
ORDER BY vs_id
"""

# Parse rawJson for milestone domains only - check what milestone_type is configured
_Q_VALUESET_RAW = """
MATCH (v:ValueSet)
WHERE v.id IN ['ncda-seen-by-specialist', 'ncda-no-cancer-discharge',
               'ncda-cancer-types', 'ncda-fast-track-referrals']
RETURN v.id AS vs_id, v.rawJson AS raw_json
"""

# All stale episodes
_Q_STALE = """
MATCH (ep:EpisodeOfCare)
WHERE ep.status IN ['stale_post_specialist', 'stale_no_diagnosis']
RETURN ep.patient_id      AS pid,
       ep.episode_id      AS ep_id,
       ep.cancer_type     AS site,
       ep.referral_date   AS ref_date,
       ep.status          AS status,
       ep.specialist_seen AS spec_seen,
       ep.auto_close_reason AS reason,
       duration.inDays(date(ep.referral_date), date()).days AS days_since_ref
ORDER BY ep.status, ep.cancer_type, ep.referral_date
"""

# Specialist visit concepts actually coded for a patient AFTER ref_date
# (regardless of whether they are in our domain - we want to see what IS there)
_Q_ACTUAL_SPECIALIST_CONCEPTS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[:DOCUMENTS]->(c)
WHERE toString(p.id) = $pid
  AND toString(e.date) >= $ref_date
  AND (
    toLower(c.name) CONTAINS 'clinic'
    OR toLower(c.name) CONTAINS 'seen '
    OR toLower(c.name) CONTAINS 'seen by'
    OR toLower(c.name) CONTAINS 'referred'
    OR toLower(c.name) CONTAINS 'outpatient'
    OR toLower(c.name) CONTAINS 'follow up'
    OR toLower(c.name) CONTAINS 'follow-up'
    OR toLower(c.name) CONTAINS 'appointment'
    OR toLower(c.name) CONTAINS 'consultation'
    OR toLower(c.name) CONTAINS 'discharge'
    OR toLower(c.name) CONTAINS 'attend'
    OR toLower(c.name) CONTAINS 'letter'
    OR toLower(c.name) CONTAINS 'specialist'
  )
RETURN DISTINCT
    c.conceptId AS cid,
    c.name      AS cname,
    toString(e.date) AS edate
ORDER BY edate
LIMIT 15
"""

# All concepts coded for a patient after ref_date (any cancer/treatment/benign signal)
_Q_POST_REF_ALL = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[doc:DOCUMENTS]->(c)
WHERE toString(p.id) = $pid
  AND toString(e.date) >= $ref_date
  AND coalesce(doc.assertion, 'present') NOT IN ['historical', 'family']
RETURN c.conceptId         AS cid,
       c.name              AS cname,
       c.semanticTag       AS stag,
       toString(e.date)    AS edate,
       coalesce(doc.assertion, 'present') AS assertion
ORDER BY edate
LIMIT 30
"""

# Encounters for a patient after ref_date that contain specialist visit SNOMED CIDs
# from our domain - checks if the domain concept IDs ARE present in the graph
_Q_SPECIALIST_IN_DOMAIN = """
MATCH (vs:ValueSet {id: 'ncda-seen-by-specialist'})-[:HAS_MEMBER]->(c)
WITH collect(c.conceptId) AS spec_ids
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[:DOCUMENTS]->(c2)
WHERE toString(p.id) = $pid
  AND c2.conceptId IN spec_ids
RETURN DISTINCT c2.conceptId AS cid, c2.name AS cname, toString(e.date) AS edate
ORDER BY edate
LIMIT 10
"""

# Benign closure concepts in the no_cancer_discharge ValueSet (if it exists)
_Q_BENIGN_IN_DOMAIN = """
MATCH (vs:ValueSet {id: 'ncda-no-cancer-discharge'})-[:HAS_MEMBER]->(c)
RETURN c.conceptId AS cid, c.name AS cname
ORDER BY cname
"""

# Check concept 395100000 specifically in patient data
_Q_NO_CANCER_CODE = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[:DOCUMENTS]->(c)
WHERE toString(p.id) = $pid
  AND toString(e.date) >= $ref_date
  AND c.conceptId = 395100000
RETURN toString(e.date) AS edate, c.name AS cname
ORDER BY edate
LIMIT 5
"""

# Common benign closures by keyword search for stale patients
_Q_BENIGN_KEYWORDS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[doc:DOCUMENTS]->(c)
WHERE toString(p.id) = $pid
  AND toString(e.date) >= $ref_date
  AND (
    toLower(c.name) CONTAINS 'benign'
    OR toLower(c.name) CONTAINS 'no evidence'
    OR toLower(c.name) CONTAINS 'no malign'
    OR toLower(c.name) CONTAINS 'fibroadenoma'
    OR toLower(c.name) CONTAINS 'polyp'
    OR toLower(c.name) CONTAINS 'adenoma'
    OR toLower(c.name) CONTAINS 'discharge'
    OR toLower(c.name) CONTAINS 'diverticular'
    OR toLower(c.name) CONTAINS 'irritable bowel'
    OR toLower(c.name) CONTAINS 'haemorrhoid'
    OR toLower(c.name) CONTAINS 'cyst'
  )
RETURN DISTINCT
    c.conceptId      AS cid,
    c.name           AS cname,
    c.semanticTag    AS stag,
    toString(e.date) AS edate
ORDER BY edate
LIMIT 10
"""

# Cancer concepts coded late (after referral but might be outside 180d window)
_Q_LATE_CANCER = """
MATCH (vs:ValueSet {id: 'ncda-cancer-types'})-[:HAS_MEMBER]->(ct)
WITH collect(ct.conceptId) AS cancer_ids
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[doc:DOCUMENTS]->(c)
WHERE toString(p.id) = $pid
  AND toString(e.date) >= $ref_date
  AND c.conceptId IN cancer_ids
  AND coalesce(doc.assertion, 'present') = 'present'
RETURN c.conceptId AS cid, c.name AS cname,
       toString(e.date) AS edate
ORDER BY edate
LIMIT 5
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CANCER_KW = (
    "malign",
    "carcinoma",
    "cancer",
    "adenocarcinoma",
    "sarcoma",
    "lymphoma",
    "melanoma",
    "neoplasm",
    "leukaemia",
    "leukemia",
    "myeloma",
    "metastati",
    "in situ",
)
_BENIGN_KW = (
    "no evidence of cancer",
    "no evidence of malignancy",
    "benign",
    "fibroadenoma",
    "polyp",
    "adenoma",
    "diverticular",
    "irritable bowel",
    "haemorrhoid",
    "cyst",
    "discharge",
)
_TREATMENT_KW = (
    "mastectomy",
    "chemotherapy",
    "radiotherapy",
    "excision",
    "resection",
    "biopsy",
    "letrozole",
    "tamoxifen",
    "rituximab",
)


def _classify_name(name: str) -> str:
    low = name.lower()
    if any(k in low for k in _CANCER_KW):
        return "CANCER"
    if any(k in low for k in _BENIGN_KW):
        return "BENIGN"
    if any(k in low for k in _TREATMENT_KW):
        return "TREATMENT"
    return ""


def _parse_milestone_type(raw_json: str | None) -> str:
    if not raw_json:
        return "(no rawJson)"
    try:
        vs = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
    except Exception:
        return "(json parse error)"
    for ext in vs.get("extension") or []:
        if ext.get("url", "").endswith("/domain-config"):
            for sub in ext.get("extension") or []:
                if sub.get("url") == "milestoneType":
                    return sub.get("valueCode") or "(empty)"
    return "(not configured)"


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


def _section_valueset_health(client) -> None:
    print("=" * 70)
    print("SECTION A: ValueSet health check - milestone types in Neo4j")
    print("=" * 70)

    rows = client.run(_Q_VALUESET_RAW) or []
    if not rows:
        print("  WARNING: none of the key milestone ValueSets found in Neo4j!\n")
        return

    for r in rows:
        vs_id = r["vs_id"]
        raw = r.get("raw_json")
        milestone = _parse_milestone_type(raw)
        concept_count = 0
        if raw:
            try:
                vs = json.loads(raw) if isinstance(raw, str) else raw
                concept_count = sum(
                    len(inc.get("concept") or [])
                    for inc in (vs.get("compose") or {}).get("include") or []
                )
            except Exception:
                pass
        status = (
            "OK"
            if milestone
            not in ("(not configured)", "(no rawJson)", "(json parse error)")
            else "PROBLEM"
        )
        print(f"  [{status}] {vs_id}")
        print(f"         milestone_type : {milestone}")
        print(f"         concept count  : {concept_count}")

    # Also check benign discharge domain by HAS_MEMBER edges
    benign_rows = client.run(_Q_BENIGN_IN_DOMAIN) or []
    print(f"\n  ncda-no-cancer-discharge HAS_MEMBER concept count: {len(benign_rows)}")
    if benign_rows:
        for r in benign_rows[:8]:
            print(f"    {r['cid']}  {r['cname']}")
    else:
        print(
            "  WARNING: no HAS_MEMBER concepts found - benign closure anchor bucket is empty"
        )
    print()


def _section_date_math_bug(stale_eps: list[dict], client) -> None:
    print("=" * 70)
    print("SECTION B: Date-math bug audit")
    print("  _STALE_CLOSE_Q fires when days_since_REF > 90 (post_spec) or > 365")
    print("  Bug: should be days_since_SPECIALIST_VISIT > 90 for stale_post_specialist")
    print("=" * 70)

    post_spec = [e for e in stale_eps if e["status"] == "stale_post_specialist"]
    no_diag = [e for e in stale_eps if e["status"] == "stale_no_diagnosis"]
    print(f"  stale_post_specialist total : {len(post_spec)}")
    print(f"  stale_no_diagnosis total    : {len(no_diag)}")

    if post_spec:
        days_vals = [int(e["days_since_ref"] or 0) for e in post_spec]
        within_180 = sum(1 for d in days_vals if d <= 180)
        within_90 = sum(1 for d in days_vals if d <= 90)
        print(f"\n  stale_post_specialist days_since_REFERRAL distribution:")
        print(f"    <= 90 days  (would NOT be stale if using ref_date): {within_90}")
        print(f"    <= 180 days                                        : {within_180}")
        print(
            f"    > 180 days (likely genuinely old referrals)        : {len(post_spec) - within_180}"
        )
        print()
        print(
            "  To measure real staleness we need to find the ACTUAL specialist-visit date."
        )
        print("  Querying post-referral specialist-domain concepts for each episode...")
        print()

        late_spec_count = 0
        no_spec_found_count = 0
        spec_date_deltas = []

        for ep in post_spec[:30]:  # cap to avoid very long runtime
            pid = str(ep["pid"])
            ref_date = str(ep["ref_date"])
            rows = client.run(_Q_SPECIALIST_IN_DOMAIN, pid=pid, ref_date=ref_date) or []
            if rows:
                spec_date = rows[0]["edate"]
                try:
                    from datetime import date as dt_date

                    spec_d = dt_date.fromisoformat(spec_date)
                    ref_d = dt_date.fromisoformat(ref_date)
                    from datetime import date

                    today = date.today()
                    days_since_spec = (today - spec_d).days
                    spec_date_deltas.append(days_since_spec)
                    if days_since_spec <= 90:
                        late_spec_count += 1
                        print(
                            f"  FALSE POSITIVE: PID={pid} site={ep['site']} "
                            f"ref={ref_date} spec_visit={spec_date} "
                            f"days_since_spec={days_since_spec} (<= 90d)"
                        )
                except Exception:
                    pass
            else:
                no_spec_found_count += 1

        if spec_date_deltas:
            avg = sum(spec_date_deltas) / len(spec_date_deltas)
            print(
                f"\n  Of first {min(30, len(post_spec))} stale_post_specialist episodes:"
            )
            print(f"    Specialist visit found in domain : {len(spec_date_deltas)}")
            print(f"    No specialist visit found in domain : {no_spec_found_count}")
            print(
                f"    Would NOT be stale if threshold from spec-visit date : {late_spec_count}"
            )
            print(f"    Average days since specialist visit : {avg:.0f}")
        print()


def _section_specialist_concept_gaps(stale_eps: list[dict], client) -> None:
    print("=" * 70)
    print("SECTION C: Specialist visit concept gaps")
    print("  For stale_no_diagnosis: did a specialist visit happen using a concept")
    print("  NOT in the seen_by_specialist domain?")
    print("=" * 70)

    no_diag = [e for e in stale_eps if e["status"] == "stale_no_diagnosis"]
    gap_concepts: dict[int, dict] = {}

    for ep in no_diag:
        pid = str(ep["pid"])
        ref_date = str(ep["ref_date"])

        # First confirm no domain specialist concept found
        in_domain = (
            client.run(_Q_SPECIALIST_IN_DOMAIN, pid=pid, ref_date=ref_date) or []
        )
        domain_found = bool(in_domain)

        # Look for specialist-sounding concepts outside the domain
        outside = (
            client.run(_Q_ACTUAL_SPECIALIST_CONCEPTS, pid=pid, ref_date=ref_date) or []
        )

        if outside and not domain_found:
            print(
                f"  PID={pid}  site={ep['site']}  ref={ref_date}  "
                f"days_since_ref={ep['days_since_ref']}"
            )
            print(f"    [No in-domain specialist concept found]")
            for r in outside[:5]:
                cid = r.get("cid") or 0
                print(f"    {r['edate']}  CID={cid}  {r['cname'][:70]}")
                if cid:
                    gap_concepts[int(cid)] = {
                        "name": r["cname"],
                        "dates": gap_concepts.get(int(cid), {}).get("dates", [])
                        + [r["edate"]],
                    }
            print()

    print(
        f"\n  Candidate specialist concepts NOT in domain ({len(gap_concepts)} unique):"
    )
    for cid, info in sorted(gap_concepts.items(), key=lambda x: -len(x[1]["dates"])):
        print(f"    CID={cid}  ({len(info['dates'])}x)  {info['name'][:65]}")
    print()


def _section_benign_closure_gaps(stale_eps: list[dict], client) -> None:
    print("=" * 70)
    print("SECTION D: Benign closure gaps")
    print("  For each stale episode: is a benign concept coded post-referral")
    print("  that the episode builder missed?")
    print("=" * 70)

    missed_benign: list[dict] = []
    missed_benign_concepts: dict[int, dict] = {}

    for ep in stale_eps:
        pid = str(ep["pid"])
        ref_date = str(ep["ref_date"])

        rows = client.run(_Q_BENIGN_KEYWORDS, pid=pid, ref_date=ref_date) or []
        no_cancer = client.run(_Q_NO_CANCER_CODE, pid=pid, ref_date=ref_date) or []
        all_benign = rows + no_cancer

        if all_benign:
            missed_benign.append(ep)
            print(
                f"  PID={pid}  site={ep['site']}  ref={ref_date}  status={ep['status']}"
            )
            for r in all_benign[:4]:
                cid = r.get("cid") or 0
                print(f"    [{r['edate']}] CID={cid}  {r.get('cname','')[:65]}")
                if cid:
                    missed_benign_concepts[int(cid)] = missed_benign_concepts.get(
                        int(cid), {"name": r.get("cname", ""), "count": 0}
                    )
                    missed_benign_concepts[int(cid)]["count"] += 1
            print()

    print(
        f"\n  Episodes with benign concept post-referral (missed closure) : {len(missed_benign)}"
    )
    print(f"  Benign concept IDs found ({len(missed_benign_concepts)} unique):")
    for cid, info in sorted(
        missed_benign_concepts.items(), key=lambda x: -x[1]["count"]
    ):
        print(f"    CID={cid}  ({info['count']}x)  {info['name'][:65]}")
    print()


def _section_late_cancer(stale_eps: list[dict], client) -> None:
    print("=" * 70)
    print("SECTION E: Late cancer diagnoses (coded but outside 180d lookback window)")
    print("=" * 70)

    late_dx: list[dict] = []

    for ep in stale_eps:
        pid = str(ep["pid"])
        ref_date = str(ep["ref_date"])

        rows = client.run(_Q_LATE_CANCER, pid=pid, ref_date=ref_date) or []
        if rows:
            first = rows[0]
            try:
                from datetime import date

                ref_d = date.fromisoformat(ref_date)
                dx_d = date.fromisoformat(first["edate"])
                gap = (dx_d - ref_d).days
            except Exception:
                gap = -1
            late_dx.append(
                {
                    "pid": pid,
                    "site": ep["site"],
                    "ref_date": ref_date,
                    "status": ep["status"],
                    "dx_date": first["edate"],
                    "dx_name": first["cname"],
                    "gap_days": gap,
                }
            )
            flag = "WITHIN 180d" if 0 <= gap <= 180 else f"LATE ({gap}d after ref)"
            print(f"  [{flag}] PID={pid}  site={ep['site']}  ref={ref_date}")
            print(f"    Dx: [{first['edate']}]  {first['cname'][:65]}")
            print()

    within = sum(1 for r in late_dx if 0 <= r["gap_days"] <= 180)
    late = sum(1 for r in late_dx if r["gap_days"] > 180)
    print(f"  Cancer found post-referral (should be completed)       : {len(late_dx)}")
    print(f"    -> Within 180d window (episode builder should have caught) : {within}")
    print(f"    -> After 180d window  (true late diagnosis)               : {late}")
    print()


def _section_post_ref_signal(stale_eps: list[dict], client) -> None:
    print("=" * 70)
    print("SECTION F: Full post-referral signal per stale episode (top 30)")
    print("=" * 70)

    for ep in stale_eps[:30]:
        pid = str(ep["pid"])
        ref_date = str(ep["ref_date"])
        rows = client.run(_Q_POST_REF_ALL, pid=pid, ref_date=ref_date) or []

        signals = defaultdict(list)
        for r in rows:
            cls = _classify_name(r.get("cname") or "")
            if cls:
                signals[cls].append(
                    f"[{r['edate']}] {r.get('cname','')[:55]} [{r.get('assertion','')}]"
                )

        if any(signals.values()):
            print(
                f"  PID={pid}  site={ep['site']}  ref={ref_date}  "
                f"status={ep['status']}  days_ref={ep['days_since_ref']}"
            )
            for cls in ("CANCER", "TREATMENT", "BENIGN"):
                for line in signals[cls][:3]:
                    print(f"    {cls}: {line}")
            print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()

    stale_eps = client.run(_Q_STALE) or []
    total_stale = len(stale_eps)
    post_spec = sum(1 for e in stale_eps if e["status"] == "stale_post_specialist")
    no_diag = sum(1 for e in stale_eps if e["status"] == "stale_no_diagnosis")

    print()
    print("=" * 70)
    print("STALE EPISODE DIAGNOSTIC")
    print(f"  Total stale        : {total_stale}")
    print(f"  stale_post_specialist : {post_spec}")
    print(f"  stale_no_diagnosis    : {no_diag}")
    print("=" * 70)
    print()

    _section_valueset_health(client)
    _section_date_math_bug(stale_eps, client)
    _section_specialist_concept_gaps(stale_eps, client)
    _section_benign_closure_gaps(stale_eps, client)
    _section_late_cancer(stale_eps, client)
    _section_post_ref_signal(stale_eps, client)

    client.close()


if __name__ == "__main__":
    main()
