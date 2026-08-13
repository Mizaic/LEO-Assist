"""Tests for patient document blob URL SAS signing."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _clear_signer_env(monkeypatch):
    monkeypatch.delenv("PATIENT_DOCUMENT_STORAGE_ACCOUNT_URL", raising=False)
    monkeypatch.delenv("PATIENT_DOCUMENT_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.delenv(
        "PATIENT_DOCUMENT_EXTRA_STORAGE_CONNECTION_STRINGS", raising=False
    )
    monkeypatch.setenv("PATIENT_DOCUMENT_SAS_TTL_MINUTES", "30")
    from libs.patient_documents import blob_url_signer

    blob_url_signer._connection_strings_by_account.cache_clear()


def test_sign_patient_document_url_passthrough_when_unconfigured():
    from libs.patient_documents import blob_url_signer

    blob_url_signer._ACCOUNT_URL = ""
    blob_url_signer._CONNECTION_STRING = ""
    url = (
        "https://storagehdtnonprod.blob.core.windows.net/"
        "leo-non-prod-container/doc.pdf"
    )
    assert blob_url_signer.sign_patient_document_url(url) == url


def test_sign_patient_document_url_skips_already_signed():
    from libs.patient_documents import blob_url_signer

    blob_url_signer._ACCOUNT_URL = "https://storagehdtnonprod.blob.core.windows.net"
    url = (
        "https://storagehdtnonprod.blob.core.windows.net/"
        "leo-non-prod-container/doc.pdf?sv=2022-11-02&sig=abc"
    )
    assert blob_url_signer.sign_patient_document_url(url) == url


def test_sign_patient_document_url_uses_connection_string(monkeypatch):
    from libs.patient_documents import blob_url_signer

    conn = (
        "DefaultEndpointsProtocol=https;AccountName=storagehdtnonprod;"
        "AccountKey=dGVzdC1rZXk=;EndpointSuffix=core.windows.net"
    )
    monkeypatch.setenv(
        "PATIENT_DOCUMENT_STORAGE_ACCOUNT_URL",
        "https://storagehdtnonprod.blob.core.windows.net",
    )
    monkeypatch.setenv("PATIENT_DOCUMENT_STORAGE_CONNECTION_STRING", conn)
    blob_url_signer._ACCOUNT_URL = "https://storagehdtnonprod.blob.core.windows.net"
    blob_url_signer._CONNECTION_STRING = conn

    url = (
        "https://storagehdtnonprod.blob.core.windows.net/"
        "leo-non-prod-container/doc.pdf"
    )
    with patch.object(blob_url_signer, "_build_sas_token", return_value="sig=fake"):
        signed = blob_url_signer.sign_patient_document_url(url)

    assert signed == f"{url}?sig=fake"


def test_sign_patient_document_url_rejects_other_accounts():
    from libs.patient_documents import blob_url_signer

    blob_url_signer._connection_strings_by_account.cache_clear()
    blob_url_signer._ACCOUNT_URL = "https://storagehdtnonprod.blob.core.windows.net"
    blob_url_signer._CONNECTION_STRING = ""
    url = "https://otheraccount.blob.core.windows.net/container/doc.pdf"
    assert blob_url_signer.sign_patient_document_url(url) == url


def test_sign_patient_document_url_uses_extra_connection_string(monkeypatch):
    from libs.patient_documents import blob_url_signer

    primary = (
        "DefaultEndpointsProtocol=https;AccountName=storagehdtnonprod;"
        "AccountKey=dGVzdC1rZXk=;EndpointSuffix=core.windows.net"
    )
    extra = (
        "DefaultEndpointsProtocol=https;AccountName=leovalidationstore;"
        "AccountKey=ZXh0cmEta2V5;EndpointSuffix=core.windows.net"
    )
    monkeypatch.setenv(
        "PATIENT_DOCUMENT_STORAGE_ACCOUNT_URL",
        "https://storagehdtnonprod.blob.core.windows.net",
    )
    monkeypatch.setenv("PATIENT_DOCUMENT_STORAGE_CONNECTION_STRING", primary)
    monkeypatch.setenv("PATIENT_DOCUMENT_EXTRA_STORAGE_CONNECTION_STRINGS", extra)
    blob_url_signer._ACCOUNT_URL = "https://storagehdtnonprod.blob.core.windows.net"
    blob_url_signer._CONNECTION_STRING = primary
    blob_url_signer._EXTRA_CONNECTION_STRINGS = extra
    blob_url_signer._connection_strings_by_account.cache_clear()

    url = (
        "https://leovalidationstore.blob.core.windows.net/"
        "leo-validation-container/doc.docx"
    )
    with patch.object(blob_url_signer, "_build_sas_token", return_value="sig=extra"):
        signed = blob_url_signer.sign_patient_document_url(url)

    assert signed == f"{url}?sig=extra"


def test_subresources_router_signs_document_urls():
    import pathlib

    src = (
        pathlib.Path(__file__).resolve().parents[1]
        / "services"
        / "analytics_api"
        / "app"
        / "routers"
        / "patients_epr_subresources.py"
    ).read_text(encoding="utf-8")
    assert "sign_patient_document_url" in src
    assert "original_url=sign_patient_document_url" in src
