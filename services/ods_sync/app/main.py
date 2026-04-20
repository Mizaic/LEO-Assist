"""ODS Nightly Sync Job — entrypoint.

Atlas trace:
  DO: DO-05064452
  DI: DI-20104031
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-05064452")

Loads secrets from Azure Key Vault (or environment variables for local dev),
initialises the Neo4j client, and runs the ODS sync service.

Deployed as an Azure Container Apps Job with cron schedule: 0 2 * * * UTC.
See infra/bicep/modules/ods-sync-job.bicep for the job configuration.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
from libs.keyvault.loader import load_keyvault_secrets
from libs.utils.logging import configure_logging

_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_ROOT / "secrets" / ".env.config", override=True)
load_keyvault_secrets()

configure_logging(service_name="ods-sync")

logger = logging.getLogger(__name__)


def main() -> int:
    """Run the ODS sync job. Returns 0 on success, 1 on fatal error."""

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
