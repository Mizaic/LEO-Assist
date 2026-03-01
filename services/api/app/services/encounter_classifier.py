"""Backwards-compatible re-export. Canonical location: libs/classifiers/encounter_classifier.py"""
from libs.classifiers.encounter_classifier import (  # noqa: F401
    ClassificationResult,
    PatientEncounterIndex,
    build_patient_encounter_index,
    classify_encounter,
    persist_encounter_classification_batch,
    persist_patient_encounter_classification,
)
