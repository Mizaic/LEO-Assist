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
FAST_TRACK_REFERRAL_IDS: frozenset[int] = frozenset([
    276281000000104,  # Fast track referral for suspected breast cancer
    276311000000101,  # Fast track referral for suspected colorectal cancer
    276341000000100,  # Fast track referral for suspected gynaecological cancer
    276371000000106,  # Fast track referral for suspected haematology malignancy
    276401000000108,  # Fast track referral for suspected head and neck cancer
    276431000000102,  # Fast track referral for suspected lung cancer
    276461000000107,  # Fast track referral for suspected sarcoma
    276491000000101,  # Fast track referral for suspected skin cancer
    276521000000103,  # Fast track referral for suspected upper GI cancer
    276551000000108,  # Fast track referral for suspected urological cancer
    276581000000102,  # Fast track referral for suspected brain tumour
    280521000000108,  # Fast track referral for suspected lower GI cancer
    892201000000106,  # Fast track referral for suspected children's tumour
    1556551000000104, # Fast track referral for suspected non-site-specific symptoms
])

# ---------------------------------------------------------------------------
# Malignant cancer diagnoses  (milestone_type = "diagnosis")
# Source: snomed_ncda_cancer_types_mapping.json
# ---------------------------------------------------------------------------
CANCER_TYPE_IDS: frozenset[int] = frozenset([
    93689003,   # Malignant neoplasm of kidney
    93849006,   # Malignant neoplasm of prostate
    93870000,   # Malignant neoplasm of stomach
    126598008,  # Neoplasm of breast
    128462008,  # Metastatic malignant neoplasm
    188235006,  # Malignant neoplasm of larynx
    236740006,  # Malignant neoplasm of ureter
    254837009,  # Malignant neoplasm of breast
    255056009,  # Malignant neoplasm of skin
    255080008,  # Malignant neoplasm of bladder
    269457002,  # Malignant melanoma of skin
    310504009,  # Malignant neoplasm of ovary
    363354003,  # Malignant tumour of head
    363358000,  # Malignant tumour of lung
    363367000,  # Malignant tumour of colon
    363403002,  # Malignant tumour of rectum
    363415003,  # Malignant tumour of cervix
    363418001,  # Malignant tumour of body of uterus
    363432004,  # Malignant tumour of thyroid
    363435002,  # Malignant tumour of tongue
    363443007,  # Malignant tumour of oesophagus
    363444001,  # Malignant tumour of liver
    363445000,  # Malignant tumour of pancreas
    363449006,  # Malignant tumour of kidney
    363453008,  # Malignant tumour of urinary bladder
    363454002,  # Malignant tumour of prostate
    363458004,  # Malignant tumour of testis
    363459007,  # Malignant tumour of penis
    363460002,  # Malignant tumour of vulva
    363461003,  # Malignant tumour of vagina
    363494000,  # Malignant tumour of brain
    363495004,  # Malignant tumour of spinal cord
    363508008,  # Malignant tumour of bone
    363516004,  # Malignant tumour of soft tissue
    371972005,  # Malignant tumour of appendix
    371982006,  # Malignant tumour of small intestine
    372063002,  # Malignant neoplasm of nervous system
    372130007,  # Malignant neoplasm of haematopoietic tissue
    399068003,  # Malignant neoplasm of prostate
    428281000,  # Multiple myeloma
    609519004,  # Carcinoma of unknown primary
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
SEEN_BY_SPECIALIST_IDS: frozenset[int] = frozenset([
    382361000000100,  # Seen in fast track suspected breast cancer clinic
    382401000000109,  # Seen in fast track suspected colorectal cancer clinic
    382431000000103,  # Seen in fast track suspected gynaecological cancer clinic
    382511000000105,  # Seen in fast track suspected haematology clinic
    382581000000103,  # Seen in fast track suspected head and neck clinic
    382621000000103,  # Seen in fast track suspected lung cancer clinic
    382651000000108,  # Seen in fast track suspected sarcoma clinic
    382681000000102,  # Seen in fast track suspected skin cancer clinic
    382711000000103,  # Seen in fast track suspected upper GI cancer clinic
    382811000000108,  # Seen in fast track suspected urological cancer clinic
    382841000000109,  # Seen in fast track suspected brain tumour clinic
    383201000000101,  # Seen in fast track suspected lower GI cancer clinic
])

# ---------------------------------------------------------------------------
# Convenience mapping: milestone_type → concept ID set
# ---------------------------------------------------------------------------
MILESTONE_CONCEPT_SETS: dict[str, frozenset[int]] = {
    "referral": FAST_TRACK_REFERRAL_IDS,
    "diagnosis": CANCER_TYPE_IDS,
    "treatment_start": TREATMENT_IDS,
    "specialist_visit": SEEN_BY_SPECIALIST_IDS,
}
