"""NCDA milestone domain concept sets.

Curated SNOMED CT concept IDs used by the analysis worker to detect
episode milestones from :DOCUMENTS relationships in the patient graph.

Each set corresponds to an NCDA domain with a ``milestone_type``:
  - FAST_TRACK_REFERRAL_IDS  → "referral"
  - CANCER_TYPE_IDS          → "diagnosis"
  - TREATMENT_IDS            → "treatment_start"
  - SEEN_BY_SPECIALIST_IDS   → "specialist_visit"

These were derived from the NCDA SNOMED mapping files in
auditor_2/agent/configs/ and should be kept in sync with whatever is
loaded into the knowledge graph (GUIDELINE_NEO4J_URI).

The primary source of truth is the FHIR/terminology server.  If the
terminology server is configured (SNOMED_TERMINOLOGY_SERVER env var),
callers can use ``enrich_from_terminology()`` to add extra concept IDs
returned for domain-specific search terms.

Usage::

    from libs.domains.ncda_concept_sets import FAST_TRACK_REFERRAL_IDS, CANCER_TYPE_IDS

    # In Cypher: WHERE c.conceptId IN $ids
    referral_rows = session.run(
        "MATCH (p:Patient {id: $pid})-[:HAS_ENCOUNTER]->(e:Encounter)"
        "-[r:DOCUMENTS]->(c) WHERE c.conceptId IN $ids ...",
        pid=patient_id, ids=list(FAST_TRACK_REFERRAL_IDS),
    )
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Fast-track / 2WW referral procedures  (milestone_type = "referral")
# Source: snomed_ncda_fast_track_referrals_mapping.json
# ---------------------------------------------------------------------------
# Verified against LEO terminology server 2026-04-03.
# IDs are in numerical order; FSNs confirmed via /terminology/search.
# Previous comments were misaligned (alphabetical labels on numerical IDs).
FAST_TRACK_REFERRAL_IDS: frozenset[int] = frozenset([
    276281000000104,  # Fast track referral for suspected skin cancer
    276311000000101,  # Fast track referral for suspected gynaecological cancer
    276341000000100,  # Fast track referral for suspected breast cancer
    276371000000106,  # Fast track referral for suspected children's tumour
    276401000000108,  # Fast track referral for suspected colorectal cancer
    276431000000102,  # Fast track referral for suspected urological cancer
    276461000000107,  # Fast track referral for suspected haematology malignancy
    276491000000101,  # Fast track referral for suspected lung cancer
    276521000000103,  # Fast track referral for suspected sarcoma
    276551000000108,  # Fast track referral for suspected upper GI cancer
    276581000000102,  # Fast track referral for suspected brain tumour
    280521000000108,  # Fast track referral for suspected head and neck cancer
    892201000000106,  # Fast track referral for suspected lower GI cancer
    1556551000000104, # Fast track referral for suspected cancer: non-site-specific symptoms
])

# ---------------------------------------------------------------------------
# Malignant cancer diagnoses  (milestone_type = "diagnosis")
# Source: snomed_ncda_cancer_types_mapping.json
# All FSNs verified against LEO terminology server 2026-04-03.
# Previous comments were misaligned (alphabetical labels on numerical IDs).
# NOTE: 255080008 and 269457002 were NOT FOUND in the knowledge graph;
#       they have been removed to avoid dead references.
# NOTE: 126598008 "Neoplasm of connective tissues" and 236740006
#       "Neoplasm of seminal vesicle" are generic neoplasm codes (not
#       explicitly malignant) -- retained for now pending clinical review.
# ---------------------------------------------------------------------------
CANCER_TYPE_IDS: frozenset[int] = frozenset([
    93689003,   # Primary malignant neoplasm of urinary bladder
    93849006,   # Primary malignant neoplasm of kidney
    93870000,   # Malignant neoplasm of liver
    126598008,  # Neoplasm of connective tissues (generic -- review needed)
    128462008,  # Metastatic malignant neoplasm
    188235006,  # Malignant neoplasm of tunica vaginalis
    236740006,  # Neoplasm of seminal vesicle (generic -- review needed)
    254837009,  # Malignant neoplasm of breast
    255056009,  # Malignant neoplasm of head and/or neck
    310504009,  # Primary malignant neoplasm of unknown site
    363349007,  # Malignant neoplasm of stomach (ADDED -- was missing)
    363354003,  # Malignant neoplasm of cervix uteri
    363358000,  # Malignant neoplasm of lung
    363367000,  # Malignant neoplasm of vulva
    363402007,  # Malignant neoplasm of oesophagus (ADDED -- was missing)
    363403002,  # Malignant neoplasm of duodenum
    363415003,  # Malignant neoplasm of biliary tract
    363418001,  # Malignant neoplasm of pancreas
    363432004,  # Malignant neoplasm of trachea
    363478007,  # Malignant neoplasm of thyroid gland (ADDED -- 363432004 is trachea, not thyroid)
    363435002,  # Malignant neoplasm of heart
    363443007,  # Malignant neoplasm of ovary
    363444001,  # Malignant neoplasm of fallopian tube
    363445000,  # Malignant neoplasm of vagina
    363449006,  # Malignant neoplasm of testis
    363453008,  # Malignant neoplasm of spermatic cord
    363454002,  # Malignant neoplasm of scrotum
    363458004,  # Malignant neoplasm of ureter
    363459007,  # Malignant neoplasm of urethra
    363460002,  # Malignant neoplasm of paraurethral gland
    363461003,  # Malignant neoplasm of eye
    363494000,  # Malignant neoplasm of mediastinum
    363495004,  # Malignant neoplasm of muscle
    363508008,  # Malignant neoplasm of intestine
    363516004,  # Malignant neoplasm of penis
    371972005,  # Malignant neoplasm of body of uterus
    371982006,  # Malignant neoplasm of endocrine gland
    372063002,  # Malignant neoplasm of nervous system
    372130007,  # Malignant neoplasm of skin
    399068003,  # Malignant neoplasm of prostate
    428281000,  # Malignant neoplasm of bone
    609519004,  # Gestational trophoblastic neoplasia
])

# ---------------------------------------------------------------------------
# Cancer treatment procedures  (milestone_type = "treatment_start")
# Source: snomed_ncda_treatment_mapping.json  (abridged to surgical/systemic)
# ---------------------------------------------------------------------------
TREATMENT_IDS: frozenset[int] = frozenset([
    # Surgical resections
    5884001,    # Mastectomy
    26294005,   # Radical prostatectomy
    36899001,   # Colectomy
    80855002,   # Pneumonectomy
    173171007,  # Total cystectomy
    173172000,  # Partial cystectomy
    173724009,  # Oesophagectomy
    175920009,  # Gastrectomy
    176761007,  # Liver resection
    177302005,  # Pancreatectomy
    178286005,  # Nephrectomy
    178923005,  # Orchidectomy
    229565001,  # Hysterectomy
    309542002,  # Thyroidectomy
    # Chemotherapy
    367336001,  # Chemotherapy
    367477001,  # Adjuvant chemotherapy
    367502008,  # Neoadjuvant chemotherapy
    373810000,  # Chemotherapy regime
    # Radiotherapy
    108290001,  # Radiation oncology
    384723003,  # Radiotherapy
    385763009,  # Brachytherapy
    386792000,  # Stereotactic radiosurgery
    # Immunotherapy / targeted therapy
    416608005,  # Drug therapy (broad)
    413648008,  # Immunotherapy
    418024000,  # Monoclonal antibody therapy
    441799006,  # Targeted drug therapy
    # Hormone therapy
    169314007,  # Hormone therapy
    169413002,  # Anti-androgen therapy
    # General surgery / interventions
    107963000,  # Excision
    115959002,  # Biopsy
    116033007,  # Lumpectomy
    # UK-specific procedure codes
    1047871000000109,  # Chemotherapy for cancer
    1084311000000107,  # Immunotherapy for cancer
    1956031000000100,  # Pembrolizumab administration (example targeted)
])

# ---------------------------------------------------------------------------
# First specialist / MDT clinic visit  (milestone_type = "specialist_visit")
# Source: snomed_ncda_seen_by_specialist_mapping.json
# ---------------------------------------------------------------------------
# Verified against LEO terminology server 2026-04-03.
# IDs are in numerical order; FSNs confirmed via /terminology/search.
# Previous comments were misaligned (alphabetical labels on numerical IDs).
SEEN_BY_SPECIALIST_IDS: frozenset[int] = frozenset([
    382361000000100,  # Seen in fast track suspected sarcoma clinic
    382401000000109,  # Seen in fast track suspected brain tumour clinic
    382431000000103,  # Seen in fast track suspected breast cancer clinic
    382511000000105,  # Seen in fast track suspected gynaecological cancer clinic
    382581000000103,  # Seen in fast track suspected haematological malignancy clinic
    382621000000103,  # Seen in fast track suspected head and neck cancer clinic
    382651000000108,  # Seen in fast track suspected colorectal cancer clinic
    382681000000102,  # Seen in fast track suspected lung cancer clinic
    382711000000103,  # Seen in fast track suspected skin cancer clinic
    382811000000108,  # Seen in fast track suspected upper GI cancer clinic
    382841000000109,  # Seen in fast track suspected urological cancer clinic
    383201000000101,  # Seen in fast track suspected children's tumour clinic
])

# ---------------------------------------------------------------------------
# Cancer exclusion / no-evidence situations  (for audit and safety-net)
#
# These SNOMED Situation concepts indicate that a cancer pathway was
# investigated and a malignancy was ruled out, or that there is no current
# evidence of cancer.  They appear as :Situation nodes in the patient graph
# via DOCUMENTS relationships and should be checked alongside CANCER_TYPE_IDS
# when auditing whether a patient has a diagnosis or an exclusion.
# ---------------------------------------------------------------------------
# Verified against LEO terminology server 2026-04-03:
#   - 395100000 and 414861001 confirmed present and correct.
#   - 415068001 and 1090791000000103 NOT FOUND in our knowledge graph;
#     retained in case the KG is later updated with these UK extension codes.
CANCER_EXCLUSION_IDS: frozenset[int] = frozenset([
    395100000,          # No evidence of cancer found (situation)
    414861001,          # No evidence of recurrence of cancer (situation)
    415068001,          # No malignancy found on biopsy (situation) -- not in KG yet
    1090791000000103,   # No evidence of malignancy (situation) -- UK ext, not in KG yet
])

# ---------------------------------------------------------------------------
# Cancer suspicion / active-pathway situations  (not yet confirmed/excluded)
#
# These indicate a suspected malignancy is under investigation.  A patient
# with one of these and no CANCER_TYPE_IDS diagnosis and no CANCER_EXCLUSION_IDS
# is still mid-pathway -- the most safety-critical state to catch.
#
# Verified against LEO terminology server 2026-04-03:
#   - 315332003 was NOT FOUND in our knowledge graph (removed).
#   - 385194003 is "Suppository (basic dose form)" -- WRONG concept,
#     removed to prevent false-positive cancer flags.
#   - 162572001 "Malignant neoplastic disease suspected" added as the
#     correct generic suspicion situation.
# ---------------------------------------------------------------------------
CANCER_SUSPECTED_IDS: frozenset[int] = frozenset([
    162572001,   # Malignant neoplastic disease suspected (situation)
    734936000,   # Malignant pigmented skin lesion suspected (situation)
])

# ---------------------------------------------------------------------------
# Cancer history / active-history situations
#
# These confirm a past or current cancer was documented.  266987004 is
# particularly important: the pipeline codes it when a patient's record
# mentions a prior cancer even without a current treatment episode.
# ---------------------------------------------------------------------------
CANCER_HISTORY_IDS: frozenset[int] = frozenset([
    266987004,   # History of malignant neoplasm (situation)
    395672005,   # Cancer diagnosis discussed with patient (situation)
])

# ---------------------------------------------------------------------------
# Convenience mapping: milestone_type → concept ID set
# ---------------------------------------------------------------------------
MILESTONE_CONCEPT_SETS: dict[str, frozenset[int]] = {
    "referral": FAST_TRACK_REFERRAL_IDS,
    "diagnosis": CANCER_TYPE_IDS,
    "treatment_start": TREATMENT_IDS,
    "specialist_visit": SEEN_BY_SPECIALIST_IDS,
    "exclusion": CANCER_EXCLUSION_IDS,
    "suspected": CANCER_SUSPECTED_IDS,
    "history": CANCER_HISTORY_IDS,
}
