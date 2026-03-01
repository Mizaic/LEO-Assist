"""
Load secrets from Azure Key Vault into os.environ at service startup.

Call load_keyvault_secrets() as the very first statement in each service
main.py, before any other imports that read environment variables.

Locally: AZURE_KEYVAULT_URL is not set, so the function is a no-op and
secrets continue to come from the .env file.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# Maps os.environ key -> Key Vault secret name
SECRET_MAP: dict[str, str] = {
    "NEO4J_URI": "neo4j-patient-uri",
    "NEO4J_PASSWORD": "neo4j-patient-password",
    "KNOWLEDGE_GRAPH_NEO4J_URI": "neo4j-knowledge-uri",
    "KNOWLEDGE_GRAPH_NEO4J_PASSWORD": "neo4j-knowledge-password",
    "REDIS_URL": "redis-url",
    "AWS_ACCESS_KEY_ID": "aws-access-key-id",
    "AWS_SECRET_ACCESS_KEY": "aws-secret-access-key",
    "AZURE_OPENAI_API_KEY": "azure-openai-api-key",
    "SERVICE_AUTH_SECRET": "service-auth-secret",
}


def load_keyvault_secrets() -> None:
    vault_url = os.environ.get("AZURE_KEYVAULT_URL", "")
    if not vault_url:
        logger.debug("AZURE_KEYVAULT_URL not set -- skipping Key Vault secret load (local dev mode)")
        return

    from azure.keyvault.secrets import SecretClient
    from libs.azure.credentials import get_credential

    client = SecretClient(vault_url=vault_url, credential=get_credential())
    loaded = 0
    for env_key, kv_name in SECRET_MAP.items():
        try:
            secret = client.get_secret(kv_name)
            os.environ[env_key] = secret.value
            loaded += 1
        except Exception as exc:
            logger.warning("Could not load KV secret %s: %s", kv_name, exc)

    logger.info("Loaded %d/%d secrets from Key Vault", loaded, len(SECRET_MAP))
