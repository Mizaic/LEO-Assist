"""Analysis Worker service.

Consumes analysis-job messages from the message bus. Runs:
- Anchor detection (referral / diagnosis / treatment)
- Episode building and consolidation
- Safety-net / unwarranted variation detection
- Abnormal results analysis
- KPI and quality metric calculation
"""

from __future__ import annotations

from pathlib import Path
from dotenv import load_dotenv
from libs.keyvault.loader import load_keyvault_secrets

_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_ROOT / "secrets" / ".env.config", override=False)
load_dotenv(_ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

import asyncio
import logging
import os

from libs.message_bus.factory import create_message_bus
from libs.message_bus.base import Message
from libs.utils.logging import configure_logging
from services.analysis_worker.app.services.job_handler import handle_analysis_job

configure_logging(service_name="analysis-worker")

# Suppress noisy Azure SDK internals — we only care about errors
for _ns in (
    "azure.servicebus",
    "azure.servicebus._pyamqp",
    "azure.servicebus._pyamqp.aio",
    "azure.core.pipeline.policies.http_logging_policy",
    "uamqp",
    "httpx",
    "botocore",
    "botocore.credentials",
):
    logging.getLogger(_ns).setLevel(logging.WARNING)

logger = logging.getLogger("analysis-worker")

QUEUE_NAME = os.getenv("ANALYSIS_QUEUE_NAME", "analysis-jobs")


async def main():
    logger.info("Analysis Worker starting — listening on queue: %s", QUEUE_NAME)
    bus = create_message_bus()

    async def on_message(msg: Message):
        await handle_analysis_job(msg)

    await bus.subscribe(QUEUE_NAME, on_message)
    logger.info("Analysis Worker subscribed. Waiting for messages...")

    try:
        while True:
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        logger.info("Analysis Worker shutting down")
    finally:
        await bus.close()


if __name__ == "__main__":
    asyncio.run(main())
