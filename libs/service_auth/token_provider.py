"""
Outbound service-to-service token acquisition using Managed Identity.

Usage in callers (coding_worker, core-api):
    from libs.service_auth.token_provider import get_service_token
    headers = {"Authorization": f"Bearer {get_service_token(TERMINOLOGY_API_APP_ID)}"}
"""

from __future__ import annotations

import os

from libs.azure.credentials import get_credential


def get_service_token(app_id_uri: str) -> str:
    """Return a Bearer token for the given Entra app ID URI.

    The scope format expected by Entra v2 endpoints is '<app_id_uri>/.default'.
    """
    credential = get_credential()
    token = credential.get_token(f"{app_id_uri}/.default")
    return token.token


def get_terminology_token() -> str:
    app_id = os.environ.get("TERMINOLOGY_API_APP_ID", "")
    if not app_id:
        return ""
    return get_service_token(app_id)


def get_model_inference_token() -> str:
    app_id = os.environ.get("MODEL_INFERENCE_APP_ID", "")
    if not app_id:
        return ""
    return get_service_token(app_id)
