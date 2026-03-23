"""
Load secrets from Azure Key Vault into os.environ at service startup.

Call load_keyvault_secrets() as the very first statement in each service
main.py, before any other imports that read environment variables.

In ACA (production): AZURE_KEYVAULT_URL is injected by the Bicep template.
The Bicep also wires secrets directly via secretRef, so this loader acts as
a belt-and-braces fallback and for the local development path.

Locally: set AZURE_KEYVAULT_URL=https://leoai-dev-kv.vault.azure.net in
your shell (or in secrets/.env.config) and run az login once. The function
will pull all secrets from Key Vault into os.environ, replacing the need for
a secrets/.env file with hard-coded credentials.

If AZURE_KEYVAULT_URL is not set the function is a no-op and secrets
continue to come from the .env file (legacy local dev path).
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# Maps os.environ key -> Key Vault secret name (kebab-case)
SECRET_MAP: dict[str, str] = {
    # Neo4j (usernames are not secret -- always "neo4j", set in .env.config)
    "NEO4J_URI":                          "neo4j-patient-uri",
    "NEO4J_PASSWORD":                     "neo4j-patient-password",
    "KNOWLEDGE_GRAPH_NEO4J_URI":          "neo4j-knowledge-uri",
    "KNOWLEDGE_GRAPH_NEO4J_PASSWORD":     "neo4j-knowledge-password",
    "GUIDELINE_NEO4J_URI":                "neo4j-guideline-uri",
    "GUIDELINE_NEO4J_PASSWORD":           "neo4j-guideline-password",
    # Redis
    "REDIS_URL":                          "redis-url",
    # Azure AD
    "AZURE_AD_CLIENT_ID":                 "azure-ad-client-id",
    "AZURE_AD_CLIENT_SECRET":             "azure-ad-client-secret",
    "AZURE_AD_TENANT_ID":                 "azure-ad-tenant-id",
    # Azure OpenAI
    "AZURE_OPENAI_API_KEY":               "azure-openai-api-key",
    "AZURE_OPENAI_ENDPOINT":              "azure-openai-endpoint",
    # Azure Storage + Service Bus
    "AZURE_STORAGE_CONNECTION_STRING":    "azure-storage-connection-string",
    "AZURE_SERVICE_BUS_CONNECTION_STRING":"azure-service-bus-connection-string",
    # AWS Bedrock
    "AWS_ACCESS_KEY_ID":                  "aws-access-key-id",
    "AWS_SECRET_ACCESS_KEY":              "aws-secret-access-key",
    "AWS_BIG_MODEL":                      "aws-big-model",
    "AWS_SMALL_MODEL":                    "aws-small-model",
    "AWS_MAX_MODEL":                      "aws-max-model",
    # NICE Syndication API
    "NICE_API_KEY":                       "nice-api-key",
    # Terminology / clinical APIs
    "SNOMED_API_KEY":                     "snomed-api-key",
    "UMLS_API_KEY":                       "umls-api-key",
    "NHS_TRUD_API_KEY":                   "nhs-trud-api-key",
    # Service client IDs (used for service-to-service auth token acquisition)
    "ANALYTICS_API_APP_ID":               "analytics-api-app-id",
    "FHIR_API_APP_ID":                    "fhir-api-app-id",
    "MODEL_INFERENCE_APP_ID":             "model-inference-app-id",
    "TERMINOLOGY_API_APP_ID":             "terminology-api-app-id",
    # Auth
    "AUTH_SECRET":                        "auth-secret",
    "SERVICE_AUTH_SECRET":                "service-auth-secret",
}


def load_keyvault_secrets() -> None:
    """Pull secrets from Azure Key Vault into os.environ.

    Safe to call even when AZURE_KEYVAULT_URL is not set -- becomes a no-op.
    KV values overwrite whatever dotenv already put into os.environ so that
    production values always win over local fallback .env files.
    """
    vault_url = os.environ.get("AZURE_KEYVAULT_URL", "")
    if not vault_url:
        logger.debug(
            "AZURE_KEYVAULT_URL not set -- skipping Key Vault load (local .env mode)"
        )
        return

    from azure.keyvault.secrets import SecretClient
    from libs.azure.credentials import get_credential

    client = SecretClient(vault_url=vault_url, credential=get_credential())
    loaded = 0
    for env_key, kv_name in SECRET_MAP.items():
        try:
            secret = client.get_secret(kv_name)
            os.environ[env_key] = secret.value or ""
            loaded += 1
        except Exception as exc:
            logger.warning("Could not load KV secret %s -> %s: %s", kv_name, env_key, exc)

    logger.info(
        "Loaded %d/%d secrets from Key Vault %s",
        loaded, len(SECRET_MAP), vault_url,
    )
