"""Approved phrases meaning a cancer investigation found no cancer.

Atlas trace:
  UN: UN-89E2AE36
  DI: DI-F03B0113
  VT: VT-BDD72AC6
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-F03B0113")

Neo4j stays the source of truth at resolve time: these phrases are seeded as
SurfaceForm nodes with MAPS_TO edges to NO_EVIDENCE_OF_CANCER_CONCEPT_ID. This
module is the reviewed seed list that puts them there, so the set is visible in
review and testable without a graph connection.

Every phrase names what was tested or ruled out. A bare polarity word is not a
result: "benign" alone is a qualifier and belongs to plenty of harmless disorder
names, so it is held in NEVER_NO_CANCER_PHRASES instead.

Post-treatment wording ("in remission", "disease free", "no evidence of
recurrence") is deliberately absent. It implies a prior diagnosis rather than an
exclusion, and "in remission" resolves to schizophrenia or diabetes remission in
this corpus.
"""

from __future__ import annotations

NO_EVIDENCE_OF_CANCER_CONCEPT_ID = "395100000"
NO_EVIDENCE_OF_CANCER_TERM = "No evidence of cancer found (situation)"

# LONG TUPLE: reviewed clinical phrase list, one phrase per line for diffability.
NO_CANCER_RESULT_PHRASES: tuple[str, ...] = (
    # -- Definitive exclusions ---------------------------------------------
    "no evidence of cancer",
    "no evidence of cancer found",
    "no evidence of malignancy",
    "no malignancy",
    "no malignancy found",
    "no malignancy detected",
    "no malignancy seen",
    "negative for malignancy",
    "neg for malignancy",
    "negative for cancer",
    "malignancy excluded",
    "cancer excluded",
    "sarcoma excluded",
    "malignancy ruled out",
    "cancer ruled out",
    "sarcoma ruled out",
    "no malignant cells",
    "no malignant cells seen",
    "negative for malignant cells",
    "no evidence of malignant cells",
    "no evidence of neoplasm",
    "no neoplasm detected",
    "no evidence of tumour",
    "no evidence of tumor",
    "no evidence of carcinoma",
    "no evidence of sarcoma",
    "malignancy not identified",
    "cancer not identified",
    "malignancy not seen",
    "cancer not seen",
    "does not suggest malignancy",
    "does not support malignancy",
    "not in keeping with malignancy",
    "not in keeping with cancer",
    "in keeping with benign",
    "argues against malignancy",
    "inconsistent with malignancy",
    "inconsistent with cancer",
    "malignancy unlikely",
    "cancer unlikely",
    # -- Pathology and histology report wording ----------------------------
    "benign histology",
    "benign on histology",
    "benign on histopathology",
    "benign pathology",
    "benign on pathology",
    "benign cytology",
    "benign result",
    "confirmed benign",
    "biopsy benign",
    "biopsy negative for malignancy",
    "histology benign",
    "histology negative for malignancy",
    "cytology benign",
    "cytology negative for malignancy",
    "no histological evidence of malignancy",
    "no pathological evidence of malignancy",
    "no neoplastic cells",
    "no tumour cells seen",
    "no tumor cells seen",
    "features are benign",
    "findings are benign",
    # -- GP-letter wording -------------------------------------------------
    # Added for DI-F03B0113. Run 40dc9da6 lost "The biopsy was reported as
    # benign" because every phrase above reads like a histology report, and a
    # GP writes the result as plain prose instead.
    "reported as benign",
    "was reported as benign",
    "reported benign",
    "came back benign",
    "came back as benign",
    "benign biopsy",
    "biopsy was benign",
    "biopsy was reported as benign",
    "biopsy result benign",
    "biopsy result was benign",
    "histology was benign",
    "histology reported as benign",
    "result was benign",
    "results were benign",
    "proved benign",
    "proven benign",
    "turned out benign",
    "turned out to be benign",
    "shown to be benign",
    "found to be benign",
    "confirmed as benign",
    "reassuringly benign",
    "biopsy showed no cancer",
    "biopsy showed no malignancy",
    "no cancer found",
    "no cancer was found",
    "no cancer detected",
    "did not show cancer",
    "did not show any cancer",
    "did not show malignancy",
)

# Phrases that must never resolve to NO_EVIDENCE_OF_CANCER_CONCEPT_ID.
# "benign" on its own is a qualifier value (30807003). The rest are benign
# disorder names, where "benign" describes the condition rather than reporting
# that cancer was looked for and not found.
NEVER_NO_CANCER_PHRASES: frozenset[str] = frozenset(
    {
        "benign",
        "benign neoplastic disease",
        "benign prostatic hyperplasia",
        "benign prostate enlargement",
        "benign melanocytic naevi",
        "benign naevus",
        "benign breast disease",
        "benign breast change",
        "benign positional vertigo",
        "benign paroxysmal positional vertigo",
        "benign essential tremor",
        "benign familial tremor",
        "suspected benign pigmented skin lesion",
    }
)
