"""SNOMED disorder concepts classified as malignant / cancer-pathway.

Atlas trace:
  DO: DO-7E1BAACC (concept-set portability alongside ``ncda_concept_sets``)

These IDs were derived from a DISTINCT sweep of ``(:Encounter)-[:DOCUMENTS]->(c)``
where ``c.semanticTag`` disorder concepts appeared on the patient graph, then
curated into malignant vs non-malignant groups (clinical grouping 2026-04).

Use cases:
  - Filtering disorder-coded DOCUMENTS hits when ``CANCER_TYPE_IDS`` alone is too narrow.
  - Audit scripts that need explicit malignancy disorder IDs observed in production data.

For canonical NCDA milestone diagnoses (broader/smaller sets), prefer
``libs.domains.ncda_concept_sets.CANCER_TYPE_IDS``.

Ambiguous bladder neoplasm (126885006) may represent benign bladder neoplasm in SNOMED;
see ``DOCUMENTS_DISORDER_NEOPLASM_AMBIGUOUS_IDS``.
"""

from __future__ import annotations

# Disorder-labelled SNOMED concepts treated as malignant / cancer diagnoses or
# metastasis / hematologic malignancy / DCIS / malignant skin tumors (BCC/SCC subset).
# Sorted numerically; IDs verified against terminology artefacts where cited.
DOCUMENTS_DISORDER_MALIGNANCY_IDS: frozenset[int] = frozenset(
    [
        55342001,  # Neoplastic disease (disorder)
        92814006,  # Chronic lymphoid leukemia, disease (disorder)
        109889007,  # Ductal carcinoma in situ of breast (disorder)
        118600007,  # Non-Hodgkin lymphoma (disorder) -- repo maps haematology confirmed
        1260086007,  # Endometrioid carcinoma of endometrium (disorder)
        128462008,  # Metastatic malignant neoplasm (disorder)
        1681000119102,  # Metastatic adenocarcinoma to lymph node (disorder), UK ext.
        188192002,  # Malignant neoplasm of endometrium of corpus uteri (disorder)
        254437001,  # Squamous cell carcinoma of buccal mucosa (disorder)
        254582000,  # Adenocarcinoma of rectum (disorder)
        254651007,  # Squamous cell carcinoma of skin (disorder)
        254701007,  # Basal cell carcinoma of skin (disorder)
        254837009,  # Malignant neoplasm of breast (disorder)
        254863004,  # Malignant granulosa cell tumor of ovary (disorder)
        254878006,  # Endometrial carcinoma (disorder)
        254887002,  # Adenocarcinoma of cervix (disorder)
        254900004,  # Carcinoma of prostate (disorder)
        254915003,  # Clear cell carcinoma of kidney (disorder)
        255029007,  # Papillary thyroid carcinoma (disorder)
        255079005,  # Carcinoma of esophagus (disorder)
        255081007,  # Carcinoma of cecum (disorder)
        255084004,  # Squamous cell carcinoma of anal margin (disorder)
        255109008,  # Transitional cell carcinoma of urinary bladder (disorder)
        276803003,  # Adenocarcinoma of esophagus (disorder)
        285618001,  # Metastasis to bone of unknown primary (disorder)
        302837001,  # Lentigo maligna melanoma (disorder)
        302841002,  # Malignant lymphoma - small lymphocytic (disorder)
        310498001,  # Malignant melanoma of back (disorder)
        363351006,  # Malignant neoplasm of rectum (disorder)
        363354003,  # Malignant neoplasm of cervix uteri (disorder)
        363406005,  # Malignant neoplasm of colon (disorder)
        363448003,  # Malignant tumor of prostate (disorder)
        363455001,  # Malignant tumor of urinary bladder (disorder)
        363478007,  # Malignant neoplasm of thyroid gland (disorder)
        371972005,  # Malignant neoplasm of body of uterus (disorder)
        372143007,  # Carcinoma of stomach (disorder)
        372244006,  # Malignant melanoma (disorder)
        399068003,  # Malignant neoplasm of prostate (disorder)
        402527000,  # Basal cell carcinoma - infiltrative (disorder)
        402815007,  # Squamous cell carcinoma (disorder)
        403914000,  # Superficial basal cell carcinoma (disorder)
        408643008,  # Infiltrating duct carcinoma of breast (disorder)
        416053008,  # Estrogen receptor positive tumor (disorder)
        425333006,  # Myeloproliferative disorder (disorder)
        713425003,  # Spinal cord compression due to metastasis to spine (disorder)
        713609000,  # Invasive carcinoma of breast (disorder)
        716274007,  # Nodular basal cell carcinoma of skin (disorder)
        94222008,  # Metastatic malignant neoplasm to bone (disorder)
        94381002,  # Metastatic malignant neoplasm to liver (disorder)
        94391008,  # Metastatic malignant neoplasm to lung (disorder)
        94392001,  # Metastatic malignant neoplasm to lymph node (disorder)
        1286877004,  # Site-map: colorectal malignancy descendant (patient-graph observation)
    ]
)

# Disorder concepts where SNOMED includes benign bladder neoplasm possibilities;
# exclude from strict malignancy filters unless assertion/context confirms malignant.
DOCUMENTS_DISORDER_NEOPLASM_AMBIGUOUS_IDS: frozenset[int] = frozenset(
    [
        126885006,  # Neoplasm of urinary bladder (disorder)
    ]
)
