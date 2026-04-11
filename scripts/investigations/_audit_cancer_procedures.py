"""Audit distinct treatments and procedures for all patients.

Queries Neo4j for every distinct Procedure node documented across all patient
encounters, then classifies each into cancer treatment categories.

Output sections:
  A - All distinct procedures (any semantic tag = procedure / regime/therapy)
  B - Procedures linked to cancer episodes (coded post-referral on an NCDA episode)
  C - Keyword-classified cancer treatment breakdown
  D - Top procedures by patient count
  E - Summary of treatment categories

Run:
    python scripts/investigations/_audit_cancer_procedures.py [--csv]

Add --csv to also write results/cancer_procedures_audit.csv.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

from libs.neo4j_client.client import PatientGraphClient

# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

# All distinct Procedure nodes that appear on at least one patient encounter.
# Includes both :Procedure label and SnomedConcept nodes tagged as
# regimetherapy (chemotherapy regimens etc. that may land as SnomedConcept).
_Q_ALL_PROCEDURES = """
MATCH (enc:Encounter)-[doc:DOCUMENTS]->(c)
WHERE c:Procedure OR c:SnomedConcept
  AND c.semanticTag IN [
    'procedure', 'regime/therapy', 'regime or therapy',
    'therapeutic procedure', 'surgical procedure',
    'administration of substance', 'substance administration'
  ]
RETURN DISTINCT
    c.conceptId          AS cid,
    c.name               AS cname,
    coalesce(c.semanticTag, 'procedure') AS stag,
    count(DISTINCT enc)  AS encounter_count,
    count(DISTINCT (enc)<-[:HAS_ENCOUNTER]-()) AS patient_count
ORDER BY patient_count DESC, cname
"""

# Broader query: any node labelled :Procedure (ignores semanticTag gap)
_Q_PROCEDURE_NODES = """
MATCH (enc:Encounter)-[doc:DOCUMENTS]->(c:Procedure)
RETURN DISTINCT
    c.conceptId          AS cid,
    c.name               AS cname,
    coalesce(c.semanticTag, 'procedure') AS stag,
    count(DISTINCT enc)  AS encounter_count
ORDER BY encounter_count DESC, cname
"""

# Procedures coded on encounters AFTER the referral date of an active/completed
# NCDA episode -- these are the oncology treatment signals.
# EpisodeOfCare stores patient_id as a property; join via that.
_Q_POST_REF_PROCEDURES = """
MATCH (ep:EpisodeOfCare)
WHERE ep.status IN [
    'in_progress', 'completed', 'stale_post_specialist',
    'stale_no_diagnosis', 'closed'
]
  AND ep.referral_date IS NOT NULL
WITH ep
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(enc:Encounter)-[doc:DOCUMENTS]->(c:Procedure)
WHERE toString(p.id) = toString(ep.patient_id)
  AND toString(enc.date) >= ep.referral_date
  AND NOT coalesce(doc.assertion, 'present') IN ['historical', 'family']
RETURN DISTINCT
    c.conceptId          AS cid,
    c.name               AS cname,
    coalesce(c.semanticTag, 'procedure') AS stag,
    ep.cancer_type       AS cancer_site,
    count(DISTINCT p)    AS patient_count,
    count(DISTINCT enc)  AS encounter_count
ORDER BY patient_count DESC, cname
"""

# Count of patients per cancer_site with at least one Procedure post-referral
_Q_TREATMENT_BY_SITE = """
MATCH (ep:EpisodeOfCare)
WHERE ep.status IN [
    'in_progress', 'completed', 'stale_post_specialist',
    'stale_no_diagnosis', 'closed'
]
  AND ep.referral_date IS NOT NULL
WITH ep
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(enc:Encounter)-[doc:DOCUMENTS]->(c:Procedure)
WHERE toString(p.id) = toString(ep.patient_id)
  AND toString(enc.date) >= ep.referral_date
  AND NOT coalesce(doc.assertion, 'present') IN ['historical', 'family']
RETURN
    coalesce(ep.cancer_type, 'unknown') AS cancer_site,
    count(DISTINCT p)    AS patients_with_procedure,
    count(DISTINCT c)    AS distinct_procedures,
    count(DISTINCT enc)  AS procedure_encounters
ORDER BY patients_with_procedure DESC
"""

# Cross-check: SnomedConcept nodes with treatment keywords (catches chemo
# coded as substance / medication rather than procedure)
_Q_TREATMENT_SUBSTANCES = """
MATCH (enc:Encounter)-[doc:DOCUMENTS]->(c)
WHERE (c:SnomedConcept OR c:Procedure)
  AND (
    toLower(c.name) CONTAINS 'chemotherapy'
    OR toLower(c.name) CONTAINS 'radiotherapy'
    OR toLower(c.name) CONTAINS 'immunotherapy'
    OR toLower(c.name) CONTAINS 'checkpoint inhibitor'
    OR toLower(c.name) CONTAINS 'targeted therapy'
    OR toLower(c.name) CONTAINS 'hormone therapy'
    OR toLower(c.name) CONTAINS 'hormonal therapy'
    OR toLower(c.name) CONTAINS 'endocrine therapy'
    OR toLower(c.name) CONTAINS 'brachytherapy'
    OR toLower(c.name) CONTAINS 'cyberknife'
    OR toLower(c.name) CONTAINS 'mastectomy'
    OR toLower(c.name) CONTAINS 'lumpectomy'
    OR toLower(c.name) CONTAINS 'prostatectomy'
    OR toLower(c.name) CONTAINS 'colectomy'
    OR toLower(c.name) CONTAINS 'hemicolectomy'
    OR toLower(c.name) CONTAINS 'gastrectomy'
    OR toLower(c.name) CONTAINS 'nephrectomy'
    OR toLower(c.name) CONTAINS 'cystectomy'
    OR toLower(c.name) CONTAINS 'pneumonectomy'
    OR toLower(c.name) CONTAINS 'lobectomy'
    OR toLower(c.name) CONTAINS 'thyroidectomy'
    OR toLower(c.name) CONTAINS 'hysterectomy'
    OR toLower(c.name) CONTAINS 'oophorectomy'
    OR toLower(c.name) CONTAINS 'salpingo'
    OR toLower(c.name) CONTAINS 'orchiectomy'
    OR toLower(c.name) CONTAINS 'orchidectomy'
    OR toLower(c.name) CONTAINS 'bone marrow transplant'
    OR toLower(c.name) CONTAINS 'stem cell transplant'
    OR toLower(c.name) CONTAINS 'haematopoietic'
    OR toLower(c.name) CONTAINS 'hematopoietic'
    OR toLower(c.name) CONTAINS 'palliative'
    OR toLower(c.name) CONTAINS 'biopsy'
    OR toLower(c.name) CONTAINS 'resection'
    OR toLower(c.name) CONTAINS 'excision'
    OR toLower(c.name) CONTAINS 'debulking'
    OR toLower(c.name) CONTAINS 'ablation'
    OR toLower(c.name) CONTAINS 'embolisation'
    OR toLower(c.name) CONTAINS 'embolization'
    OR toLower(c.name) CONTAINS 'cryotherapy'
    OR toLower(c.name) CONTAINS 'photodynamic'
    OR toLower(c.name) CONTAINS 'imatinib'
    OR toLower(c.name) CONTAINS 'erlotinib'
    OR toLower(c.name) CONTAINS 'gefitinib'
    OR toLower(c.name) CONTAINS 'sunitinib'
    OR toLower(c.name) CONTAINS 'sorafenib'
    OR toLower(c.name) CONTAINS 'vemurafenib'
    OR toLower(c.name) CONTAINS 'nivolumab'
    OR toLower(c.name) CONTAINS 'pembrolizumab'
    OR toLower(c.name) CONTAINS 'atezolizumab'
    OR toLower(c.name) CONTAINS 'durvalumab'
    OR toLower(c.name) CONTAINS 'ipilimumab'
    OR toLower(c.name) CONTAINS 'rituximab'
    OR toLower(c.name) CONTAINS 'trastuzumab'
    OR toLower(c.name) CONTAINS 'herceptin'
    OR toLower(c.name) CONTAINS 'bevacizumab'
    OR toLower(c.name) CONTAINS 'cetuximab'
    OR toLower(c.name) CONTAINS 'panitumumab'
    OR toLower(c.name) CONTAINS 'pertuzumab'
    OR toLower(c.name) CONTAINS 'tamoxifen'
    OR toLower(c.name) CONTAINS 'letrozole'
    OR toLower(c.name) CONTAINS 'anastrozole'
    OR toLower(c.name) CONTAINS 'exemestane'
    OR toLower(c.name) CONTAINS 'fulvestrant'
    OR toLower(c.name) CONTAINS 'bicalutamide'
    OR toLower(c.name) CONTAINS 'enzalutamide'
    OR toLower(c.name) CONTAINS 'abiraterone'
    OR toLower(c.name) CONTAINS 'degarelix'
    OR toLower(c.name) CONTAINS 'goserelin'
    OR toLower(c.name) CONTAINS 'leuprorelin'
    OR toLower(c.name) CONTAINS 'cyclophosphamide'
    OR toLower(c.name) CONTAINS 'doxorubicin'
    OR toLower(c.name) CONTAINS 'epirubicin'
    OR toLower(c.name) CONTAINS 'docetaxel'
    OR toLower(c.name) CONTAINS 'paclitaxel'
    OR toLower(c.name) CONTAINS 'carboplatin'
    OR toLower(c.name) CONTAINS 'cisplatin'
    OR toLower(c.name) CONTAINS 'oxaliplatin'
    OR toLower(c.name) CONTAINS 'capecitabine'
    OR toLower(c.name) CONTAINS 'fluorouracil'
    OR toLower(c.name) CONTAINS 'gemcitabine'
    OR toLower(c.name) CONTAINS 'pemetrexed'
    OR toLower(c.name) CONTAINS 'vinorelbine'
    OR toLower(c.name) CONTAINS 'etoposide'
    OR toLower(c.name) CONTAINS 'methotrexate'
    OR toLower(c.name) CONTAINS 'bleomycin'
  )
  AND NOT coalesce(doc.assertion, 'present') IN ['historical', 'family']
RETURN DISTINCT
    c.conceptId          AS cid,
    c.name               AS cname,
    coalesce(c.semanticTag, labels(c)[0]) AS stag,
    count(DISTINCT enc)  AS encounter_count
ORDER BY encounter_count DESC, cname
"""


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------

_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Systemic / Chemotherapy": (
        "chemotherapy",
        "cyclophosphamide",
        "doxorubicin",
        "epirubicin",
        "docetaxel",
        "paclitaxel",
        "carboplatin",
        "cisplatin",
        "oxaliplatin",
        "capecitabine",
        "fluorouracil",
        "gemcitabine",
        "pemetrexed",
        "vinorelbine",
        "etoposide",
        "methotrexate",
        "bleomycin",
        "irinotecan",
        "topotecan",
        "vinblastine",
        "vincristine",
    ),
    "Targeted Therapy": (
        "imatinib",
        "erlotinib",
        "gefitinib",
        "sunitinib",
        "sorafenib",
        "vemurafenib",
        "dabrafenib",
        "trametinib",
        "lapatinib",
        "palbociclib",
        "ribociclib",
        "abemaciclib",
        "olaparib",
        "niraparib",
        "rucaparib",
        "targeted therapy",
    ),
    "Immunotherapy": (
        "immunotherapy",
        "nivolumab",
        "pembrolizumab",
        "atezolizumab",
        "durvalumab",
        "ipilimumab",
        "checkpoint inhibitor",
        "car-t",
        "car t cell",
    ),
    "Monoclonal Antibody": (
        "rituximab",
        "trastuzumab",
        "herceptin",
        "bevacizumab",
        "cetuximab",
        "panitumumab",
        "pertuzumab",
        "ramucirumab",
        "necitumumab",
        "monoclonal antibody",
    ),
    "Hormone / Endocrine Therapy": (
        "tamoxifen",
        "letrozole",
        "anastrozole",
        "exemestane",
        "fulvestrant",
        "bicalutamide",
        "enzalutamide",
        "abiraterone",
        "degarelix",
        "goserelin",
        "leuprorelin",
        "hormone therapy",
        "hormonal therapy",
        "endocrine therapy",
        "aromatase inhibitor",
        "anti-androgen",
        "androgen deprivation",
    ),
    "Radiotherapy": (
        "radiotherapy",
        "radiation therapy",
        "stereotactic",
        "brachytherapy",
        "cyberknife",
        "gamma knife",
        "proton therapy",
        "linac",
        "external beam",
    ),
    "Surgical - Breast": (
        "mastectomy",
        "lumpectomy",
        "wide local excision",
        "sentinel lymph node",
        "axillary clearance",
    ),
    "Surgical - Colorectal": (
        "colectomy",
        "hemicolectomy",
        "anterior resection",
        "hartmann",
        "right hemicolectomy",
        "left hemicolectomy",
        "sigmoid colectomy",
        "abdominoperineal",
    ),
    "Surgical - Urological": (
        "prostatectomy",
        "nephrectomy",
        "cystectomy",
        "orchiectomy",
        "orchidectomy",
        "radical nephrectomy",
        "partial nephrectomy",
    ),
    "Surgical - Gynaecological": (
        "hysterectomy",
        "oophorectomy",
        "salpingo",
        "vulvectomy",
        "trachelectomy",
    ),
    "Surgical - Thoracic": (
        "pneumonectomy",
        "lobectomy",
        "wedge resection",
        "thoracoscopic",
        "vats",
        "mediastinoscopy",
    ),
    "Surgical - Head and Neck": (
        "thyroidectomy",
        "laryngectomy",
        "glossectomy",
        "parotidectomy",
        "neck dissection",
    ),
    "Surgical - Haematological": (
        "bone marrow transplant",
        "stem cell transplant",
        "haematopoietic",
        "hematopoietic",
        "allogenic",
        "autologous",
    ),
    "Diagnostic Procedure": (
        "biopsy",
        "fine needle",
        "endoscopy",
        "colonoscopy",
        "bronchoscopy",
        "cystoscopy",
        "laparoscopy",
        "colposcopy",
        "sigmoidoscopy",
    ),
    "Ablative / Interventional": (
        "ablation",
        "embolisation",
        "embolization",
        "cryotherapy",
        "photodynamic",
        "radiofrequency",
        "microwave ablation",
        "debulking",
        "cytoreduction",
    ),
    "Supportive / Palliative": (
        "palliative",
        "supportive care",
        "pain management",
        "hospice",
        "symptom control",
    ),
    "General Surgical Procedure": (
        "resection",
        "excision",
        "surgical procedure",
    ),
}


def _classify(name: str) -> list[str]:
    """Return list of matching treatment categories for a procedure name."""
    low = name.lower()
    cats = [
        cat for cat, kws in _CATEGORY_KEYWORDS.items() if any(k in low for k in kws)
    ]
    return cats or ["Other / Unclassified"]


# ---------------------------------------------------------------------------
# Print helpers
# ---------------------------------------------------------------------------


def _hr(char: str = "-", width: int = 72) -> None:
    print(char * width)


def _section(title: str) -> None:
    print()
    _hr("=")
    print(f"  {title}")
    _hr("=")


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


def _section_a(client: PatientGraphClient) -> list[dict]:
    """All distinct :Procedure nodes coded on any encounter."""
    _section("SECTION A: All distinct Procedure nodes across all encounters")

    rows = client.run(_Q_PROCEDURE_NODES) or []
    print(f"  Total distinct :Procedure nodes : {len(rows)}")
    _hr()
    print(f"  {'Enc':>6}  {'CID':>12}  Procedure name")
    _hr()
    for r in rows:
        cid = r.get("cid") or ""
        cname = (r.get("cname") or "(no name)")[:65]
        enc = r.get("encounter_count") or 0
        print(f"  {enc:6d}  {str(cid):>12}  {cname}")
    return rows


def _section_b(client: PatientGraphClient) -> list[dict]:
    """Procedures coded post-referral on NCDA cancer episodes."""
    _section(
        "SECTION B: Procedures coded post-referral on NCDA episodes "
        "(likely cancer treatments)"
    )

    rows = client.run(_Q_POST_REF_PROCEDURES) or []
    if not rows:
        print("  No post-referral procedures found.")
        return []

    print(f"  Total distinct procedure + cancer-site combinations : {len(rows)}")
    _hr()
    print(f"  {'Pts':>5}  {'Enc':>6}  {'Site':<18}  Procedure name")
    _hr()
    for r in rows:
        site = (r.get("cancer_site") or "unknown")[:18]
        cname = (r.get("cname") or "(no name)")[:55]
        pts = r.get("patient_count") or 0
        enc = r.get("encounter_count") or 0
        print(f"  {pts:5d}  {enc:6d}  {site:<18}  {cname}")
    return rows


def _section_c(client: PatientGraphClient) -> dict[str, list[dict]]:
    """Keyword-classified cancer treatment breakdown (all nodes, any label)."""
    _section(
        "SECTION C: Keyword-classified cancer treatments "
        "(Procedure + SnomedConcept nodes)"
    )

    rows = client.run(_Q_TREATMENT_SUBSTANCES) or []
    print(f"  Total keyword-matched treatment concepts : {len(rows)}")

    by_cat: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        cats = _classify(r.get("cname") or "")
        for cat in cats:
            by_cat[cat].append(r)

    for cat in sorted(by_cat.keys()):
        items = sorted(by_cat[cat], key=lambda x: -(x.get("encounter_count") or 0))
        _hr()
        print(f"  [{cat}]  ({len(items)} distinct concepts)")
        for r in items:
            cid = r.get("cid") or ""
            cname = (r.get("cname") or "(no name)")[:60]
            enc = r.get("encounter_count") or 0
            stag = r.get("stag") or ""
            print(f"    {enc:6d}x  CID={str(cid):>12}  [{stag}]  {cname}")

    return dict(by_cat)


def _section_d(client: PatientGraphClient) -> None:
    """Treatment coverage by cancer site."""
    _section("SECTION D: Treatment coverage by cancer site")

    rows = client.run(_Q_TREATMENT_BY_SITE) or []
    if not rows:
        print("  No data.")
        return

    _hr()
    print(
        f"  {'Cancer site':<22}  {'Patients w/ proc':>16}  "
        f"{'Distinct procs':>14}  {'Proc encounters':>15}"
    )
    _hr()
    for r in rows:
        site = (r.get("cancer_site") or "unknown")[:22]
        pts = r.get("patients_with_procedure") or 0
        dproc = r.get("distinct_procedures") or 0
        penc = r.get("procedure_encounters") or 0
        print(f"  {site:<22}  {pts:>16}  {dproc:>14}  {penc:>15}")


def _section_e_summary(
    all_procs: list[dict],
    post_ref: list[dict],
    by_cat: dict[str, list[dict]],
) -> None:
    """Print a final summary."""
    _section("SECTION E: Summary")

    unique_cats = len(by_cat)
    total_kw = sum(len(v) for v in by_cat.values())
    print(f"  Distinct :Procedure nodes in graph      : {len(all_procs)}")
    print(f"  Post-referral procedure/site combos     : {len(post_ref)}")
    print(f"  Keyword-matched treatment concepts      : {total_kw}")
    print(f"  Treatment categories identified         : {unique_cats}")
    _hr()
    print("  Treatment category sizes:")
    for cat in sorted(by_cat.keys(), key=lambda c: -len(by_cat[c])):
        print(f"    {len(by_cat[cat]):4d}  {cat}")


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------


def _write_csv(
    all_procs: list[dict],
    post_ref: list[dict],
    by_cat: dict[str, list[dict]],
) -> None:
    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "cancer_procedures_audit.csv"

    seen: dict[str, dict] = {}
    for r in all_procs:
        cid = str(r.get("cid") or "")
        name = r.get("cname") or ""
        seen[f"{cid}_{name}"] = {
            "cid": cid,
            "name": name,
            "stag": r.get("stag") or "",
            "encounter_count": r.get("encounter_count") or 0,
            "source": "procedure_node",
            "cancer_site": "",
            "categories": "|".join(_classify(name)),
        }

    for r in post_ref:
        cid = str(r.get("cid") or "")
        name = r.get("cname") or ""
        site = r.get("cancer_site") or ""
        key = f"{cid}_{name}_{site}"
        seen[key] = {
            "cid": cid,
            "name": name,
            "stag": r.get("stag") or "",
            "encounter_count": r.get("encounter_count") or 0,
            "source": "post_referral",
            "cancer_site": site,
            "categories": "|".join(_classify(name)),
        }

    for cat, items in by_cat.items():
        for r in items:
            cid = str(r.get("cid") or "")
            name = r.get("cname") or ""
            key = f"kw_{cid}_{name}"
            if key not in seen:
                seen[key] = {
                    "cid": cid,
                    "name": name,
                    "stag": r.get("stag") or "",
                    "encounter_count": r.get("encounter_count") or 0,
                    "source": "keyword_match",
                    "cancer_site": "",
                    "categories": "|".join(_classify(name)),
                }

    fields = [
        "cid",
        "name",
        "stag",
        "encounter_count",
        "source",
        "cancer_site",
        "categories",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in sorted(seen.values(), key=lambda x: -(x["encounter_count"])):
            writer.writerow(row)

    print(f"\n  CSV written to: {out_path}")
    print(f"  Rows: {len(seen)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    write_csv = "--csv" in sys.argv

    client = PatientGraphClient()
    try:
        all_procs = _section_a(client)
        post_ref = _section_b(client)
        by_cat = _section_c(client)
        _section_d(client)
        _section_e_summary(all_procs, post_ref, by_cat)

        if write_csv:
            _write_csv(all_procs, post_ref, by_cat)
        else:
            print("\n  Tip: run with --csv to export full results to CSV.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
