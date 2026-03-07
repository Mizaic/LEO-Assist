"""ODS Nightly Sync Job — entrypoint.

Loads secrets from Azure Key Vault (or environment variables for local dev),
initialises the Neo4j client, and runs the ODS sync service.

Deployed as an Azure Container Apps Job with cron schedule: 0 2 * * * UTC.
See infra/bicep/modules/ods-sync-job.bicep for the job configuration.
"""

from __future__ import annotations

import logging
import os
import sys

from libs.utils.logging import configure_logging

configure_logging(service_name="ods-sync")

logger = logging.getLogger(__name__)


def _load_secrets_from_keyvault() -> None:
    """Attempt to load secrets from Azure Key Vault into environment variables.

    Falls back silently if Key Vault is not configured (local dev / test).
    """
    vault_url = os.environ.get("AZURE_KEYVAULT_URL", "")
    if not vault_url:
        logger.info("[ODS Sync] No AZURE_KEYVAULT_URL — using environment variables")
        return
    try:
        from azure.identity import ManagedIdentityCredential
        from azure.keyvault.secrets import SecretClient
        credential = ManagedIdentityCredential()
        client = SecretClient(vault_url=vault_url, credential=credential)
        secret_map = {
            "NEO4J-PATIENT-URI": "NEO4J_PATIENT_URI",
            "NEO4J-PATIENT-USER": "NEO4J_PATIENT_USER",
            "NEO4J-PATIENT-PASSWORD": "NEO4J_PATIENT_PASSWORD",
        }
        for kv_name, env_name in secret_map.items():
            if not os.environ.get(env_name):
                try:
                    secret = client.get_secret(kv_name)
                    os.environ[env_name] = secret.value or ""
                    logger.debug("[ODS Sync] Loaded %s from Key Vault", env_name)
                except Exception as exc:
                    logger.warning("[ODS Sync] Could not load %s from Key Vault: %s", kv_name, exc)
    except ImportError:
        logger.warning("[ODS Sync] azure-keyvault-secrets not installed — skipping Key Vault")
    except Exception as exc:
        logger.error("[ODS Sync] Key Vault initialisation failed: %s", exc)


def main() -> int:
    """Run the ODS sync job. Returns 0 on success, 1 on fatal error."""
    _load_secrets_from_keyvault()

    try:
        from libs.neo4j_client.client import PatientGraphClient
        from services.ods_sync.app.sync_service import SyncService

        neo_client = PatientGraphClient()
        svc = SyncService(neo_client=neo_client)
        svc.run()
        neo_client.close()
        return 0
    except Exception as exc:
        logger.error("[ODS Sync] Fatal error: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
