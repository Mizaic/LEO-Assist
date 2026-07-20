"""Auto-stamped Atlas trace.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

Load secrets from Azure Key Vault into os.environ at service startup.

Call load_keyvault_secrets() as the very first statement in each service
main.py, before any other imports that read environment variables.

In ACA (production): AZURE_KEYVAULT_URL is injected by the Bicep template.
The Bicep also wires secrets directly via secretRef, so this loader acts as
a belt-and-braces fallback and for the local development path.

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


def _is_secret_not_found(exc: BaseException) -> bool:
    """True when Key Vault answered that the secret name does not exist."""
    name = type(exc).__name__
    if name in {"ResourceNotFoundError", "SecretNotFound"}:
        return True
    msg = str(exc)
    return "SecretNotFound" in msg or ("(name/id)" in msg and "was not found" in msg)


def _is_credential_failure(exc: BaseException) -> bool:
    """True when Key Vault access failed because auth itself is broken.

    Distinguishes a one-off missing secret (keep trying other names) from an
    expired `az login` / DefaultAzureCredential collapse (abort the loop).
    """
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


def _load_local_secrets_fallback(only_keys: set[str] | None = None) -> int:
    """Load secrets/.env.secrets into os.environ when KV is disabled.

    Used in local development when AZURE_KEYVAULT_URL is not set. Existing
    env vars are NOT overwritten (override=False) so anything explicitly
    exported in the shell still wins.

    When `only_keys` is given, only those keys are considered (used by the
    KV-recovery path below, so a KV outage never leaks unrelated local-only
    values into an environment that otherwise trusts Key Vault).

    Returns the number of vars loaded (0 if the file does not exist).

    This is the local-dev fallback path called out in the module docstring;
    without it, services started under macOS Terminal.app via osascript do
    not inherit secrets exported by the start script (osascript "do script"
    does not propagate env), and inter-service auth fails with 401.
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


def load_keyvault_secrets() -> None:
    """Pull secrets from Azure Key Vault into os.environ.

    When AZURE_KEYVAULT_URL is set: pull every name in SECRET_MAP from KV and
    overwrite os.environ so production values always win over local .env files.

    When AZURE_KEYVAULT_URL is not set: fall back to loading
    ``secrets/.env.secrets`` (without overriding anything already in the
    environment). This is the documented local-dev path -- it ensures every
    service has a consistent environment, including SERVICE_AUTH_SECRET so
    that inter-service auth works.
    """
    vault_url = os.environ.get("AZURE_KEYVAULT_URL", "")
    if not vault_url:
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
        return

    try:
        from azure.keyvault.secrets import SecretClient
        from libs.azure.credentials import get_credential
    except ModuleNotFoundError as exc:
        logger.warning(
            "AZURE_KEYVAULT_URL is set but Azure SDK is not installed (%s). "
            "Install azure-keyvault-secrets or unset AZURE_KEYVAULT_URL and "
            "use secrets/.env.secrets. Falling back to local secrets file only.",
            exc,
        )
        _load_local_secrets_fallback()
        return

    client = SecretClient(vault_url=vault_url, credential=get_credential())
    loaded = 0
    failed_keys: set[str] = set()
    auth_broken = False
    for env_key, kv_name in SECRET_MAP.items():
        if auth_broken:
            failed_keys.add(env_key)
            continue
        try:
            secret = client.get_secret(kv_name)
            os.environ[env_key] = secret.value or ""
            loaded += 1
        except Exception as exc:
            failed_keys.add(env_key)
            if _is_credential_failure(exc):
                # One expired az login would otherwise retry DefaultAzureCredential
                # for every remaining secret (~30 huge stack traces). Bail out of
                # the KV loop and recover from secrets/.env.secrets once.
                auth_broken = True
                logger.warning(
                    "Key Vault authentication failed on first secret "
                    "(%s -> %s): %s. Skipping remaining KV fetches and "
                    "falling back to local secrets file if present.",
                    kv_name,
                    env_key,
                    exc,
                )
            elif _is_secret_not_found(exc) and kv_name in _OPTIONAL_KV_SECRET_NAMES:
                logger.info(
                    "Optional KV secret %s not present; skipping (%s)",
                    kv_name,
                    env_key,
                )
            elif _is_secret_not_found(exc):
                logger.warning(
                    "Could not load KV secret %s -> %s (not found in vault)",
                    kv_name,
                    env_key,
                )
            else:
                logger.warning(
                    "Could not load KV secret %s -> %s: %s",
                    kv_name,
                    env_key,
                    exc,
                )

    logger.info(
        "Loaded %d/%d secrets from Key Vault %s",
        loaded,
        len(SECRET_MAP),
        vault_url,
    )

    if failed_keys:
        # Belt-and-braces recovery: a stale az login, a revoked credential, or
        # a transient KV outage must not silently leave every downstream
        # service without Neo4j/Bedrock/etc credentials (see
        # services/analytics_api dashboards.py PatientGraphClient failures).
        # secrets/.env.secrets does not exist in any deployed environment, so
        # this is a genuine no-op there -- it only helps local dev recover
        # from an expired `az login` session.
        recovered = _load_local_secrets_fallback(only_keys=failed_keys)
        if recovered:
            logger.warning(
                "Key Vault fetch failed for %d secret(s) (%s) -- recovered %d "
                "from local %s as a fallback. This MUST NOT happen in a "
                "deployed environment; if it does, Key Vault access is "
                "broken and needs investigating (e.g. expired credential, "
                "missing RBAC, network policy).",
                len(failed_keys),
                ", ".join(sorted(failed_keys)),
                recovered,
                _LOCAL_SECRETS_FILE,
            )
