"""Sign patient document blob URLs for authenticated browser access.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

Referral ingest stores plain Azure blob URLs on DocumentReference nodes.
Storage accounts with allowBlobPublicAccess=false require a SAS token
for browser opens. This module adds short-lived read SAS query params
when the analytics API returns original_url / markdown_url fields.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_BLOB_HOST_RE = re.compile(r"^([^.]+)\.blob\.core\.windows\.net$")
_ACCOUNT_URL = os.getenv("PATIENT_DOCUMENT_STORAGE_ACCOUNT_URL", "").rstrip("/")
_CONNECTION_STRING = os.getenv("PATIENT_DOCUMENT_STORAGE_CONNECTION_STRING", "")
_EXTRA_CONNECTION_STRINGS = os.getenv(
    "PATIENT_DOCUMENT_EXTRA_STORAGE_CONNECTION_STRINGS", ""
)
_SAS_TTL_MINUTES = int(os.getenv("PATIENT_DOCUMENT_SAS_TTL_MINUTES", "60"))
_CONN_STRING_PREFIX = "PATIENT_DOCUMENT_STORAGE_CONNECTION_STRING__"


def _allowed_account_host() -> Optional[str]:
    if not _ACCOUNT_URL:
        return None
    host = urlparse(_ACCOUNT_URL).netloc
    if not host:
        return None
    match = _BLOB_HOST_RE.match(host)
    return match.group(1) if match else None


def _parse_blob_url(url: str) -> Optional[tuple[str, str, str]]:
    parsed = urlparse(url)
    host_match = _BLOB_HOST_RE.match(parsed.netloc)
    if not host_match:
        return None
    account = host_match.group(1)
    parts = parsed.path.lstrip("/").split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return account, parts[0], parts[1]


def _already_signed(url: str) -> bool:
    query = urlparse(url).query.lower()
    return "sig=" in query or "sv=" in query


def _account_key_from_connection_string(connection_string: str) -> tuple[str, str]:
    account_name = ""
    account_key = ""
    for part in connection_string.split(";"):
        if part.startswith("AccountName="):
            account_name = part.split("=", 1)[1]
        elif part.startswith("AccountKey="):
            account_key = part.split("=", 1)[1]
    if not account_name or not account_key:
        raise ValueError("Connection string missing AccountName or AccountKey")
    return account_name, account_key


@lru_cache(maxsize=1)
def _connection_strings_by_account() -> dict[str, str]:
    """Map blob account name to a connection string for SAS signing."""
    by_account: dict[str, str] = {}

    def _register(connection_string: str) -> None:
        conn = connection_string.strip()
        if not conn:
            return
        account_name, _ = _account_key_from_connection_string(conn)
        by_account[account_name] = conn

    if _CONNECTION_STRING:
        _register(_CONNECTION_STRING)

    extra = _EXTRA_CONNECTION_STRINGS.strip()
    if extra:
        if extra.startswith("["):
            for item in json.loads(extra):
                if isinstance(item, str):
                    _register(item)
        else:
            for line in extra.splitlines():
                _register(line)

    for key, value in os.environ.items():
        if key.startswith(_CONN_STRING_PREFIX) and value.strip():
            _register(value)

    return by_account


def _can_sign_account(account: str) -> bool:
    if account in _connection_strings_by_account():
        return True
    primary = _allowed_account_host()
    if primary and account == primary and (_CONNECTION_STRING or _ACCOUNT_URL):
        return True
    return False


def _build_sas_token(account: str, container: str, blob_name: str) -> Optional[str]:
    from azure.storage.blob import BlobSasPermissions, generate_blob_sas

    start = datetime.now(timezone.utc)
    expiry = start + timedelta(minutes=_SAS_TTL_MINUTES)
    permission = BlobSasPermissions(read=True)

    connection_string = _connection_strings_by_account().get(account)
    if connection_string:
        account_name, account_key = _account_key_from_connection_string(
            connection_string
        )
        return generate_blob_sas(
            account_name=account_name,
            container_name=container,
            blob_name=blob_name,
            account_key=account_key,
            permission=permission,
            expiry=expiry,
            start=start,
        )

    if _CONNECTION_STRING:
        account_name, account_key = _account_key_from_connection_string(
            _CONNECTION_STRING
        )
        if account_name != account:
            return None
        return generate_blob_sas(
            account_name=account_name,
            container_name=container,
            blob_name=blob_name,
            account_key=account_key,
            permission=permission,
            expiry=expiry,
            start=start,
        )

    if not _ACCOUNT_URL:
        return None

    from azure.storage.blob import BlobServiceClient

    from libs.azure.credentials import get_credential

    account_url = f"https://{account}.blob.core.windows.net"
    if _ACCOUNT_URL.rstrip("/") != account_url:
        return None

    client = BlobServiceClient(account_url=account_url, credential=get_credential())
    delegation_key = client.get_user_delegation_key(
        key_start_time=start,
        key_expiry_time=expiry,
    )
    return generate_blob_sas(
        account_name=account,
        container_name=container,
        blob_name=blob_name,
        user_delegation_key=delegation_key,
        permission=permission,
        expiry=expiry,
        start=start,
    )


def sign_patient_document_url(url: Optional[str]) -> Optional[str]:
    """Return a read-only SAS URL, or the original URL when signing is disabled."""
    if not url or not url.startswith("https://"):
        return url
    if _already_signed(url):
        return url

    parsed = _parse_blob_url(url)
    if not parsed:
        return url

    account, container, blob_name = parsed
    if not _can_sign_account(account):
        return url

    try:
        sas = _build_sas_token(account, container, blob_name)
    except Exception:
        logger.warning(
            "patient document blob SAS signing failed for account=%s",
            account,
            exc_info=True,
        )
        return url

    if not sas:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{sas}"
