"""Tests for patient document folder labels."""

from libs.patient_documents.folder_label import resolve_document_folder_label


def test_folder_label_from_clinic_type_urology():
    assert (
        resolve_document_folder_label(
            episode_label="General",
            clinic_type="2WW_UROLOGY",
        )
        == "Urology"
    )


def test_folder_label_from_clinic_type_breast():
    assert (
        resolve_document_folder_label(
            episode_label="General",
            clinic_type="2WW_BREAST",
        )
        == "Breast"
    )


def test_folder_label_falls_back_to_episode():
    assert (
        resolve_document_folder_label(
            episode_label="lung",
            clinic_type="",
        )
        == "Lung"
    )


def test_folder_label_general_when_no_signals():
    assert resolve_document_folder_label(episode_label="General") == "General"
