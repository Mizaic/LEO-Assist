"""Backwards-compatible re-export. Canonical location: libs/classifiers/encounter_classifier.py

Atlas trace:
  DO: DO-92F92EFB
  DI: DI-88C1715A
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-92F92EFB")
"""

from libs.classifiers.encounter_classifier import (  # noqa: F401
    ClassificationResult,
    PatientEncounterIndex,
    build_patient_encounter_index,
    classify_encounter,
    persist_encounter_classification_batch,
    persist_patient_encounter_classification,
)
