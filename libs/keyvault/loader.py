"""Auto-stamped Atlas trace.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design_output", dc_id="DO-AA3B7FCC")

Load secrets from Azure Key Vault into os.environ at service startup.

Call load_keyvault_secrets() as the very first statement in each service
main.py, before any other imports that read environment variables.

In ACA (production): AZURE_KEYVAULT_URL is injected by the Bicep template.
When that variable is set, Key Vault must be reachable and every required
secret must load successfully -- otherwise startup fails fast so the
container does not run with missing credentials.

Locally: two supported paths.
1. Set AZURE_KEYVAULT_URL=https://mizaicai-dev-kv.vault.azure.net in your
   shell (or in secrets/.env.config) and run az login once. The function
   will pull all secrets from Key Vault into os.environ.
2. Run `scripts/sync-secrets-local.ps1` (Windows) or otherwise populate
   secrets/.env.secrets from KV. When AZURE_KEYVAULT_URL is NOT set, this
   loader falls back to reading secrets/.env.secrets (without overriding
   anything already exported in the shell). This is the path used by
   scripts/start_leo-ai-core.sh, because macOS osascript "do script"
   does not propagate env vars from the calling shell to spawned Terminal
   windows -- without this fallback, services like model-inference would
   start without SERVICE_AUTH_SECRET and inter-service auth would 401.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Repo root: libs/keyvault/loader.py -> ../../
_REPO_ROOT = Path(__file__).resolve().parents[2]
_LOCAL_SECRETS_FILE = _REPO_ROOT / "secrets" / ".env.secrets"

# Maps os.environ key -> Key Vault secret name (kebab-case)
SECRET_MAP: dict[str, str] = {
    # Neo4j (usernames are not secret -- always "neo4j", set in .env.config)
    "NEO4J_URI": "neo4j-patient-uri",
    "NEO4J_PASSWORD": "neo4j-patient-password",
    "KNOWLEDGE_GRAPH_NEO4J_URI": "neo4j-knowledge-uri",
    "KNOWLEDGE_GRAPH_NEO4J_PASSWORD": "neo4j-knowledge-password",
    "GUIDELINE_NEO4J_URI": "neo4j-guideline-uri",
    "GUIDELINE_NEO4J_PASSWORD": "neo4j-guideline-password",
    # Redis
    "REDIS_URL": "redis-url",
    # Azure AD
    "AZURE_AD_CLIENT_ID": "azure-ad-client-id",
    "AZURE_AD_CLIENT_SECRET": "azure-ad-client-secret",
    "AZURE_AD_TENANT_ID": "azure-ad-tenant-id",
    "MAIL_GRAPH_TENANT_ID": "mail-graph-tenant-id",
    "MAIL_GRAPH_CLIENT_ID": "mail-graph-client-id",
    "MAIL_GRAPH_CLIENT_SECRET": "mail-graph-client-secret",
    # Azure OpenAI
    "AZURE_OPENAI_API_KEY": "azure-openai-api-key",
    "AZURE_OPENAI_ENDPOINT": "azure-openai-endpoint",
    # Service Bus (Storage uses managed identity via AZURE_STORAGE_ACCOUNT_URL in Bicep)
    "AZURE_SERVICE_BUS_CONNECTION_STRING": "azure-service-bus-connection-string",
    # AWS Bedrock
    "AWS_ACCESS_KEY_ID": "aws-access-key-id",
    "AWS_SECRET_ACCESS_KEY": "aws-secret-access-key",
    "AWS_BIG_MODEL": "aws-big-model",
    "AWS_SMALL_MODEL": "aws-small-model",
    "AWS_MAX_MODEL": "aws-max-model",
    # NICE Syndication API
    "NICE_API_KEY": "nice-api-key",
    # Terminology / clinical APIs
    "SNOMED_API_KEY": "snomed-api-key",
    "UMLS_API_KEY": "umls-api-key",
    "NHS_TRUD_API_KEY": "nhs-trud-api-key",
    # Service client IDs (used for service-to-service auth token acquisition)
    "ANALYTICS_API_APP_ID": "analytics-api-app-id",
    "FHIR_API_APP_ID": "fhir-api-app-id",
    "MODEL_INFERENCE_APP_ID": "model-inference-app-id",
    "TERMINOLOGY_API_APP_ID": "terminology-api-app-id",
    # Auth
    "AUTH_SECRET": "auth-secret",
    "SERVICE_AUTH_SECRET": "service-auth-secret",
    # Widget SDK
    "SDK_HOST_SHARED_SECRET": "sdk-host-shared-secret",
    "SDK_WIDGET_TOKEN_SECRET": "sdk-widget-token-secret",
}

# Optional local/dev features. Missing these in Key Vault must not spam
# startup logs -- mail Graph is only needed for mailbox tooling, not the
# referral / SBAR pipeline worker.
_OPTIONAL_KV_SECRET_NAMES: frozenset[str] = frozenset(
    {
        "mail-graph-tenant-id",
        "mail-graph-client-id",
        "mail-graph-client-secret",
    }
)


class KeyVaultStartupError(RuntimeError):
    """Key Vault is required but could not supply secrets at startup."""


def _is_secret_not_found(exc: BaseException) -> bool:
    """True when Key Vault answered that the secret name does not exist."""
    name = type(exc).__name__
    if name in {"ResourceNotFoundError", "SecretNotFound"}:
        return True
    msg = str(exc)
    return "SecretNotFound" in msg or ("(name/id)" in msg and "was not found" in msg)


def _is_credential_failure(exc: BaseException) -> bool:
    """True when Key Vault access failed because auth itself is broken."""
    name = type(exc).__name__
    if name in {
        "ClientAuthenticationError",
        "CredentialUnavailableError",
        "AuthenticationRequiredError",
    }:
        return True
    msg = str(exc).lower()
    return (
        "defaultazurecredential failed" in msg
        or "aadsts70043" in msg
        or "refresh token has expired" in msg
        or "authentication failed" in msg
    )


def _abort_keyvault_startup(
    message: str, *, cause: BaseException | None = None
) -> None:
    """Log a clear ERROR and stop startup when Key Vault is mandatory."""
    logger.error(message)
    if cause is not None:
        raise KeyVaultStartupError(message) from cause
    raise KeyVaultStartupError(message)


def _load_local_secrets_fallback(only_keys: set[str] | None = None) -> int:
    """Load secrets/.env.secrets into os.environ when KV is disabled.

    Used in local development when AZURE_KEYVAULT_URL is not set. Existing
    env vars are NOT overwritten (override=False) so anything explicitly
    exported in the shell still wins.

    Returns the number of vars loaded (0 if the file does not exist).
    """
    if not _LOCAL_SECRETS_FILE.is_file():
        return 0
    loaded = 0
    try:
        with _LOCAL_SECRETS_FILE.open("r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if not key:
                    continue
                if only_keys is not None and key not in only_keys:
                    continue
                if key in os.environ:
                    continue
                os.environ[key] = value
                loaded += 1
    except OSError as exc:
        logger.warning("Could not read %s: %s", _LOCAL_SECRETS_FILE, exc)
    return loaded


def _load_local_dev_secrets() -> None:
    """Local path when AZURE_KEYVAULT_URL is not set."""
    loaded = _load_local_secrets_fallback()
    if loaded:
        logger.info(
            "AZURE_KEYVAULT_URL not set -- loaded %d secrets from %s "
            "(local dev fallback)",
            loaded,
            _LOCAL_SECRETS_FILE,
        )
    else:
        logger.debug(
            "AZURE_KEYVAULT_URL not set and no %s present -- "
            "running with shell-env secrets only",
            _LOCAL_SECRETS_FILE,
        )


def _build_secret_client(vault_url: str):
    """Import Azure SDK pieces and return a SecretClient."""
    try:
        from azure.keyvault.secrets import SecretClient
        from libs.azure.credentials import get_credential
    except ModuleNotFoundError as exc:
        _abort_keyvault_startup(
            "AZURE_KEYVAULT_URL is set but the Azure Key Vault SDK is not "
            "installed. Install azure-keyvault-secrets or unset "
            "AZURE_KEYVAULT_URL for local dev.",
            cause=exc,
        )
    return SecretClient(vault_url=vault_url, credential=get_credential())


def _handle_kv_fetch_error(
    vault_url: str,
    env_key: str,
    kv_name: str,
    exc: BaseException,
    missing_required: list[str],
) -> None:
    """Classify a Key Vault fetch failure; abort or record for later."""
    if _is_credential_failure(exc):
        _abort_keyvault_startup(
            "Key Vault is unreachable at startup: authentication failed for "
            f"{vault_url} while loading {kv_name} -> {env_key}. "
            "The service will not start without valid Key Vault access.",
            cause=exc,
        )
    if _is_secret_not_found(exc) and kv_name in _OPTIONAL_KV_SECRET_NAMES:
        logger.info(
            "Optional KV secret %s not present; skipping (%s)",
            kv_name,
            env_key,
        )
        return
    if _is_secret_not_found(exc):
        missing_required.append(f"{kv_name} -> {env_key}")
        return
    _abort_keyvault_startup(
        "Key Vault is unreachable at startup: failed to load "
        f"{kv_name} -> {env_key} from {vault_url}: {exc}. "
        "The service will not start without working Key Vault access.",
        cause=exc,
    )


def _load_from_keyvault(vault_url: str) -> None:
    """Pull every required secret from Key Vault; fail fast on any error."""
    client = _build_secret_client(vault_url)
    loaded = 0
    missing_required: list[str] = []
    for env_key, kv_name in SECRET_MAP.items():
        try:
            secret = client.get_secret(kv_name)
            os.environ[env_key] = secret.value or ""
            loaded += 1
        except Exception as exc:
            _handle_kv_fetch_error(vault_url, env_key, kv_name, exc, missing_required)

    if missing_required:
        _abort_keyvault_startup(
            "Key Vault at "
            f"{vault_url} is missing required secrets: "
            f"{', '.join(missing_required)}. "
            "The service will not start until all required secrets are present."
        )

    logger.info(
        "Loaded %d/%d secrets from Key Vault %s",
        loaded,
        len(SECRET_MAP),
        vault_url,
    )


def load_keyvault_secrets() -> None:
    """Pull secrets from Azure Key Vault into os.environ.

    When AZURE_KEYVAULT_URL is set: pull every name in SECRET_MAP from KV and
    overwrite os.environ. Startup fails if Key Vault is unreachable, auth
    fails, or any required secret is missing.

    When AZURE_KEYVAULT_URL is not set: fall back to loading
    ``secrets/.env.secrets`` (without overriding anything already in the
    environment). This is the documented local-dev path.
    """
    vault_url = os.environ.get("AZURE_KEYVAULT_URL", "")
    if not vault_url:
        _load_local_dev_secrets()
        return
    _load_from_keyvault(vault_url)
